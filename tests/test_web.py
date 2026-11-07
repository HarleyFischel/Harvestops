import json
import logging

from harvestops.config import Settings
from harvestops.logging_config import JsonFormatter, redact_message
from harvestops.web import delivery_requirements, make_app


def test_health_and_readiness():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").get_json()["status"] == "ready"
    headers = client.get("/healthz").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_structured_log_formatter_emits_safe_json():
    record = logging.LogRecord(
        "harvestops.test", logging.INFO, __file__, 1, "workflow %s", ("ok",), None
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["logger"] == "harvestops.test"
    assert payload["message"] == "workflow ok"
    assert payload["timestamp"].endswith("+00:00")
    assert (
        redact_message("password=topsecret token: abc123")
        == "password=[REDACTED] token: [REDACTED]"
    )


def test_export_requires_operator_role():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/api/shipments/export").status_code == 403
    client.post("/auth/demo", json={"username": "demo.operator"})
    response = client.get("/api/shipments/export")
    assert response.status_code == 200
    assert "shipment_id" in response.text


def test_shipment_detail_requires_viewer_and_returns_version():
    app = make_app(Settings(app_env="development", demo_mode=True, identity_mode="demo"))
    client = app.server.test_client()
    assert client.get("/api/shipments/SHP-1004").status_code == 403
    client.post("/auth/demo", json={"username": "demo.viewer"})
    response = client.get("/api/shipments/SHP-1004")
    assert response.status_code == 200
    assert response.get_json()["version"] == 1
    assert client.get("/api/shipments/unknown").status_code == 404


def test_export_prefixes_formula_like_cells():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    client.post("/auth/demo", json={"username": "demo.operator"})
    # Mutate only this test's isolated demo store through its closure-backed service.
    store = next(
        cell.cell_contents
        for cell in app.server.view_functions["export_shipments"].__closure__
        if hasattr(cell.cell_contents, "shipments")
    )
    store.shipments["SHP-1001"].customer = '=HYPERLINK("https://example.test")'
    response = client.get("/api/shipments/export")
    assert "'=HYPERLINK" in response.text


def test_demo_session_role_injection_cannot_escalate_known_account():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    client.post("/auth/demo", json={"username": "demo.viewer"})
    with client.session_transaction() as session:
        session["roles"] = ["viewer", "admin"]
    assert client.get("/api/shipments/export").status_code == 403


def test_demo_identity_cannot_be_enabled_in_production():
    try:
        make_app(
            Settings(secret_key="test", app_env="production", demo_mode=True, storage_mode="demo")
        )
    except RuntimeError as exc:
        assert "DEMO_MODE" in str(exc)
    else:
        raise AssertionError("production demo mode must fail closed")


def test_production_rejects_demo_identity_even_when_demo_mode_is_false():
    try:
        make_app(
            Settings(
                app_env="production", demo_mode=False, storage_mode="demo", identity_mode="demo"
            )
        )
    except RuntimeError as exc:
        assert "IDENTITY_MODE" in str(exc)
    else:
        raise AssertionError("production must reject demo identity")


def test_production_requires_server_side_session_backend():
    settings = Settings(
        app_env="production",
        demo_mode=False,
        storage_mode="demo",
        identity_mode="entra",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
    )
    try:
        make_app(settings)
    except RuntimeError as exc:
        assert "SESSION_REDIS_URL" in str(exc)
    else:
        raise AssertionError("production must require distributed session storage")


def test_production_rejects_default_secret():
    settings = Settings(
        app_env="production",
        demo_mode=False,
        identity_mode="entra",
        storage_mode="demo",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
        session_redis_url="redis://localhost:6379/0",
    )
    try:
        make_app(settings)
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
    else:
        raise AssertionError("production must reject the default secret")


def test_production_requires_verified_sql_connections():
    settings = Settings(
        app_env="production",
        demo_mode=False,
        identity_mode="entra",
        storage_mode="sqlserver",
        secret_key="x" * 48,
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
        session_redis_url="redis://localhost:6379/0",
        sql_server="sql.example",
        sql_database="HarvestOps",
        sql_user="app",
        sql_password="secret",
        sql_encrypt=False,
        sql_trust_server_certificate=True,
    )
    errors = settings.validate_for_runtime()
    assert "SQL_ENCRYPT must be true in production" in errors
    assert "SQL_TRUST_SERVER_CERTIFICATE must be false in production" in errors


def test_azure_identity_sql_mode_does_not_require_sql_password():
    settings = Settings(
        app_env="production",
        demo_mode=False,
        identity_mode="entra",
        storage_mode="sqlserver",
        sql_auth_mode="azure_identity",
        secret_key="x" * 48,
        sql_server="azure-sql.database.windows.net",
        sql_database="HarvestOps",
        azure_client_id="managed-identity-client-id",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
        session_redis_url="redis://localhost:6379/0",
    )
    assert settings.validate_for_runtime() == []


def test_entra_layout_does_not_expose_demo_role_switch():
    settings = Settings(
        identity_mode="entra",
        demo_mode=False,
        storage_mode="demo",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
        session_redis_url="redis://localhost:6379/0",
    )
    app = make_app(settings)
    assert "role-switch" not in str(app.layout())


def test_session_claims_reconstruct_entra_principal_across_workers():
    app = make_app(
        Settings(
            secret_key="test",
            demo_mode=False,
            identity_mode="entra",
            storage_mode="demo",
            entra_client_id="client",
            entra_client_secret="secret",
            entra_tenant_id="tenant",
        )
    )
    client = app.server.test_client()
    with client.session_transaction() as session:
        session["username"] = "entra.user@example.test"
        session["display_name"] = "Entra User"
        session["roles"] = ["viewer", "operator"]
        session["identity"] = "entra"
    response = client.get("/api/shipments/export")
    assert response.status_code == 200
    assert "shipment_id" in response.text


def test_required_grid_and_purchase_callbacks_exist():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    assert "page-loading" in str(app.layout())
    callback_keys = set(app.callback_map)
    assert any("shipment-grid.rowData" in key for key in callback_keys)
    assert any("ship-page.data" in key for key in callback_keys)
    callback_inputs = [
        input_item
        for callback in app.callback_map.values()
        for input_item in callback.get("inputs", [])
    ]
    assert {item["id"] for item in callback_inputs}.issuperset({"ship-product", "ship-facility"})
    assert any("shipment-lookup-result.children" in key for key in callback_keys)
    assert any("confirm-status.displayed" in key for key in callback_keys)
    assert any("purchase-history.children" in key for key in callback_keys)
    assert any("import-report.children" in key for key in callback_keys)


def test_entra_routes_are_closed_in_demo_mode():
    app = make_app(
        Settings(secret_key="test", demo_mode=True, storage_mode="demo", identity_mode="demo")
    )
    client = app.server.test_client()
    assert client.get("/auth/login").status_code == 403
    client.post("/auth/demo", json={"username": "demo.viewer"})
    assert client.post("/auth/logout").status_code == 403
    token = client.get("/api/csrf").get_json()["csrf_token"]
    assert (
        client.post("/auth/logout", headers={"X-CSRF-Token": token}).get_json()["status"]
        == "signed_out"
    )


def test_entra_callback_rejects_invalid_state_before_redeeming_code():
    settings = Settings(
        secret_key="test",
        demo_mode=False,
        identity_mode="entra",
        storage_mode="demo",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
    )
    app = make_app(settings)
    client = app.server.test_client()
    with client.session_transaction() as session:
        session["entra_state"] = "expected-state"
    response = client.get("/auth/callback?state=wrong-state&code=unused")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid identity state"


def test_knowledge_document_route_enforces_document_roles_and_blocks_static_paths():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    client.get("/")

    forbidden = client.get("/knowledge/documents/purchasing.md")
    assert forbidden.status_code == 403
    assert b"requester cannot approve" not in forbidden.data
    former_static = client.get("/assets/knowledge/purchasing.md")
    assert former_static.status_code == 404
    assert b"requester cannot approve" not in former_static.data
    assert client.get("/knowledge/documents/../purchasing.md").status_code == 404

    csrf = client.get("/api/csrf").get_json()["csrf_token"]
    assert (
        client.post(
            "/auth/demo",
            json={"username": "demo.approver"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 200
    )
    permitted = client.get("/knowledge/documents/purchasing.md")
    assert permitted.status_code == 200
    assert b"requester cannot approve" in permitted.data


def test_dash_surface_redirects_unauthenticated_entra_requests():
    settings = Settings(
        identity_mode="entra",
        demo_mode=False,
        storage_mode="demo",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
    )
    app = make_app(settings)
    client = app.server.test_client()
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")
    assert client.post("/_dash-update-component", json={}).status_code == 401


def test_demo_dash_surface_gets_a_server_side_viewer_session():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/").status_code == 200
    response = client.get("/api/csrf")
    assert response.status_code == 200
    assert response.get_json()["csrf_token"]


def test_demo_account_switch_requires_csrf_after_session_exists():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/").status_code == 200
    assert client.post("/auth/demo", json={"username": "demo.operator"}).status_code == 403
    token = client.get("/api/csrf").get_json()["csrf_token"]
    assert (
        client.post(
            "/auth/demo", json={"username": "demo.operator"}, headers={"X-CSRF-Token": token}
        ).status_code
        == 200
    )


def test_direct_dash_write_callback_without_csrf_does_not_mutate_state():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.post("/auth/demo", json={"username": "demo.operator"}).status_code == 200
    client.delete_cookie("harvestops_csrf")
    callback_output = next(
        key
        for key in app.callback_map
        if key.startswith("..shipment-alert.children...shipment-refresh.data")
    )

    payload = {
        "output": callback_output,
        "outputs": [
            {"id": "shipment-alert", "property": "children"},
            {"id": "shipment-refresh", "property": "data"},
        ],
        "inputs": [{"id": "confirm-status", "property": "submit_n_clicks", "value": 1}],
        "state": [
            {"id": "selected-shipment-id", "property": "data", "value": "SHP-1004"},
            {"id": "selected-status", "property": "value", "value": "In Transit"},
            {"id": "selected-shipment-version", "property": "data", "value": 1},
            {"id": "csrf-token", "property": "data", "value": ""},
            {"id": "csrf-status", "property": "data-csrf-token", "value": ""},
        ],
        "changedPropIds": ["confirm-status.submit_n_clicks"],
    }

    response = client.post("/_dash-update-component", json=payload)
    assert response.status_code == 200
    assert response.get_json()["response"]["shipment-alert"]["children"] == (
        "Could not apply change: CSRF token required"
    )

    detail = client.get("/api/shipments/SHP-1004")
    assert detail.get_json()["status"] == "Scheduled"
    assert detail.get_json()["version"] == 1


def test_direct_dash_write_callback_viewer_cannot_mutate_with_valid_csrf():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    client.post("/auth/demo", json={"username": "demo.viewer"})
    token = client.get("/api/csrf").get_json()["csrf_token"]
    callback_output = next(
        key
        for key in app.callback_map
        if key.startswith("..shipment-alert.children...shipment-refresh.data")
    )
    payload = {
        "output": callback_output,
        "outputs": [
            {"id": "shipment-alert", "property": "children"},
            {"id": "shipment-refresh", "property": "data"},
        ],
        "inputs": [{"id": "confirm-status", "property": "submit_n_clicks", "value": 1}],
        "state": [
            {"id": "selected-shipment-id", "property": "data", "value": "SHP-1004"},
            {"id": "selected-status", "property": "value", "value": "In Transit"},
            {"id": "selected-shipment-version", "property": "data", "value": 1},
            {"id": "csrf-token", "property": "data", "value": token},
            {"id": "csrf-status", "property": "data-csrf-token", "value": token},
        ],
        "changedPropIds": ["confirm-status.submit_n_clicks"],
    }

    response = client.post("/_dash-update-component", json=payload)
    assert response.status_code == 200
    assert response.get_json()["response"]["shipment-alert"]["children"] == (
        "Could not apply change: Operator role required"
    )
    detail = client.get("/api/shipments/SHP-1004")
    assert detail.get_json()["status"] == "Scheduled"


def test_import_endpoint_is_authorized_and_idempotent():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    csv_text = "shipment_id,customer,product,facility,carrier,dock,planned_departure_utc,ordered_qty,shipped_qty,freight_cost,status\nSHP-2099,City Market,Spring Mix,Salinas,GreenLine,D-07,2026-03-02T15:00:00Z,500,500,875,Scheduled\n"
    assert client.post("/api/shipments/import", data=csv_text).status_code == 403
    client.post("/auth/demo", json={"username": "demo.operator"})
    token = client.get("/api/csrf").get_json()["csrf_token"]
    first = client.post("/api/shipments/import", data=csv_text, headers={"X-CSRF-Token": token})
    second = client.post("/api/shipments/import", data=csv_text, headers={"X-CSRF-Token": token})
    assert first.status_code == 201
    assert first.get_json()["applied"] == 1
    assert second.get_json()["applied"] == 0


def test_delivery_evidence_is_sanitized_and_role_protected():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/api/delivery-evidence").status_code == 403
    client.post("/auth/demo", json={"username": "demo.viewer"})
    response = client.get("/api/delivery-evidence")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["repository"] == "HarleyFischel/Harvestops"
    assert all(source["visibility"] == "public" for source in payload["sources"])
    assert client.get("/api/delivery-evidence/details").status_code == 403
    operator_client = app.server.test_client()
    operator_client.post("/auth/demo", json={"username": "demo.operator"})
    assert operator_client.get("/api/delivery-evidence/details").status_code == 200


def test_delivery_document_route_is_allowlisted_escaped_and_authenticated():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/delivery/documents/architecture").status_code == 401
    client.post("/auth/demo", json={"username": "demo.viewer"})
    response = client.get("/delivery/documents/architecture")
    assert response.status_code == 200
    assert "Architecture" in response.text
    assert "&lt;script&gt;" not in response.text
    assert client.get("/delivery/documents/%2e%2e/%2eenv").status_code == 404
    assert client.get("/delivery/documents/not-allowlisted").status_code == 404


def test_delivery_navigation_and_requirement_manifest_are_present():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    layout = str(app.layout())
    assert "Delivery &amp; Quality" in layout or "Delivery & Quality" in layout
    assert "delivery" in str(app.callback_map)
    assert any(item["id"] == "OPS-002" for item in delivery_requirements())
