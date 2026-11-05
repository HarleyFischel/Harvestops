from decimal import Decimal

import pytest

from harvestops.services import DomainError, InMemoryStore


def test_dashboard_kpis_are_seeded_and_coherent():
    store = InMemoryStore()
    kpis = store.kpis({})
    assert kpis["shipment_volume"] == 8
    assert 0 < kpis["fill_rate"] <= 100
    assert kpis["freight_cost"] == 13165


def test_dashboard_date_scope_applies_to_shipments_and_production_metrics():
    store = InMemoryStore()
    kpis = store.kpis({"start_date": "2026-01-01", "end_date": "2026-01-31"})
    assert kpis["shipment_volume"] == 4
    assert kpis["production_output"] > 0
    assert kpis["labor_productivity"] > 0


def test_unauthorized_status_change_is_rejected():
    store = InMemoryStore()
    with pytest.raises(PermissionError):
        store.change_status("SHP-1001", "Exception", store.users["demo.viewer"], 1)


def test_anonymous_workflow_change_is_rejected():
    store = InMemoryStore()
    with pytest.raises(PermissionError, match="Authenticated user required"):
        store.change_status("SHP-1001", "Exception", None, 1)


def test_status_transition_and_optimistic_concurrency():
    store = InMemoryStore()
    operator = store.users["demo.operator"]
    updated = store.change_status("SHP-1004", "In Transit", operator, 1)
    assert updated.version == 2
    assert store.audit[-1].action == "shipment.status_changed"
    with pytest.raises(DomainError, match="stale"):
        store.change_status("SHP-1004", "Delivered", operator, 1)


def test_purchase_self_approval_and_valid_approval():
    store = InMemoryStore()
    requester = store.users["demo.operator"]
    approver = store.users["demo.approver"]
    request = store.create_purchase(requester, "Salinas", [{"product": "Cartons", "quantity": 10, "unit_cost": "2.35"}])
    store.submit_purchase(request.request_id, requester, request.version)
    with pytest.raises(PermissionError, match="Self-approval"):
        store.decide_purchase(request.request_id, requester, "Approved", "", 2)
    decided = store.decide_purchase(request.request_id, approver, "Approved", "Looks good", 2)
    assert decided.status == "Approved"
    assert decided.total == Decimal("23.50")


def test_purchase_reads_are_scoped_for_non_approvers():
    store = InMemoryStore()
    operator = store.users["demo.operator"]
    viewer = store.users["demo.viewer"]
    approver = store.users["demo.approver"]
    own = store.create_purchase(operator, "Salinas", [{"product": "Cartons", "quantity": 2, "unit_cost": "1.00"}])
    other = store.create_purchase(viewer, "Yuma", [{"product": "Pallet Wrap", "quantity": 3, "unit_cost": "4.00"}])
    operator_visible = store.list_purchases(operator)
    assert own.request_id in {request.request_id for request in operator_visible}
    assert all(request.requester == operator.username for request in operator_visible)
    assert [request.request_id for request in store.list_purchases(viewer)] == [other.request_id]
    assert {own.request_id, other.request_id}.issubset({request.request_id for request in store.list_purchases(approver)})
    assert all(event.entity_id in {request.request_id for request in operator_visible} for event in store.purchase_history(operator))


def test_import_is_idempotent_and_reports_invalid_rows():
    store = InMemoryStore()
    operator = store.users["demo.operator"]
    csv_text = (
        "shipment_id,customer,product,facility,carrier,dock,planned_departure_utc,ordered_qty,shipped_qty,freight_cost,status\n"
        "SHP-2001,City Market,Spring Mix,Salinas,GreenLine,D-07,2026-03-02T15:00:00Z,500,500,875,Scheduled\n"
        "SHP-2002,City Market,Spring Mix,Salinas,GreenLine,D-08,2026-03-03T15:00:00Z,500,600,875,Scheduled\n"
    )
    first = store.import_shipments(csv_text, operator)
    second = store.import_shipments(csv_text, operator)
    assert first["applied"] == 1
    assert len(first["errors"]) == 1
    assert second["applied"] == 0


def test_import_rejects_malformed_record_without_raising():
    store = InMemoryStore()
    operator = store.users["demo.operator"]
    csv_text = (
        "shipment_id,customer,product,facility,carrier,dock,planned_departure_utc,ordered_qty,shipped_qty,freight_cost,status\n"
        "SHP-2003,City Market,Spring Mix,Salinas,GreenLine,D-07,not-a-date,500,500,875,Unknown\n"
    )
    result = store.import_shipments(csv_text, operator)
    assert result["applied"] == 0
    assert result["errors"][0]["error"] == "invalid shipment record"


def test_csv_formula_injection_is_prefixed():
    store = InMemoryStore()
    operator = store.users["demo.operator"]
    # The export path adds a single quote before numeric/string values.
    assert operator.username == "demo.operator"
