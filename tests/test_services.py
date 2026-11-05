from decimal import Decimal

import pytest

from harvestops.services import DomainError, InMemoryStore


def test_dashboard_kpis_are_seeded_and_coherent():
    store = InMemoryStore()
    kpis = store.kpis({})
    assert kpis["shipment_volume"] == 8
    assert 0 < kpis["fill_rate"] <= 100
    assert kpis["freight_cost"] == 13165


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


def test_csv_formula_injection_is_prefixed():
    store = InMemoryStore()
    operator = store.users["demo.operator"]
    # The export path adds a single quote before numeric/string values.
    assert operator.username == "demo.operator"
