from harvestops.config import Settings
from harvestops.web import make_app


def test_health_and_readiness():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").get_json()["status"] == "ready"
    headers = client.get("/healthz").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_export_requires_operator_role():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/api/shipments/export").status_code == 403
    client.post("/auth/demo", json={"username": "demo.operator"})
    response = client.get("/api/shipments/export")
    assert response.status_code == 200
    assert "shipment_id" in response.text


def test_export_prefixes_formula_like_cells():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    client.post("/auth/demo", json={"username": "demo.operator"})
    # Mutate only this test's isolated demo store through its closure-backed service.
    store = next(cell.cell_contents for cell in app.server.view_functions["export_shipments"].__closure__ if hasattr(cell.cell_contents, "shipments"))
    store.shipments["SHP-1001"].customer = "=HYPERLINK(\"https://example.test\")"
    response = client.get("/api/shipments/export")
    assert "'=HYPERLINK" in response.text


def test_demo_identity_cannot_be_enabled_in_production():
    try:
        make_app(Settings(secret_key="test", app_env="production", demo_mode=True, storage_mode="demo"))
    except RuntimeError as exc:
        assert "DEMO_MODE" in str(exc)
    else:
        raise AssertionError("production demo mode must fail closed")


def test_production_rejects_demo_identity_even_when_demo_mode_is_false():
    try:
        make_app(Settings(app_env="production", demo_mode=False, storage_mode="demo", identity_mode="demo"))
    except RuntimeError as exc:
        assert "IDENTITY_MODE" in str(exc)
    else:
        raise AssertionError("production must reject demo identity")


def test_production_requires_server_side_session_backend():
    settings = Settings(app_env="production", demo_mode=False, storage_mode="demo", identity_mode="entra", entra_client_id="client", entra_client_secret="secret", entra_tenant_id="tenant")
    try:
        make_app(settings)
    except RuntimeError as exc:
        assert "SESSION_REDIS_URL" in str(exc)
    else:
        raise AssertionError("production must require distributed session storage")


def test_production_rejects_default_secret():
    settings = Settings(app_env="production", demo_mode=False, identity_mode="entra", storage_mode="demo", entra_client_id="client", entra_client_secret="secret", entra_tenant_id="tenant", session_redis_url="redis://localhost:6379/0")
    try:
        make_app(settings)
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
    else:
        raise AssertionError("production must reject the default secret")


def test_entra_layout_does_not_expose_demo_role_switch():
    settings = Settings(identity_mode="entra", demo_mode=False, storage_mode="demo", entra_client_id="client", entra_client_secret="secret", entra_tenant_id="tenant", session_redis_url="redis://localhost:6379/0")
    app = make_app(settings)
    assert "role-switch" not in str(app.layout())


def test_session_claims_reconstruct_entra_principal_across_workers():
    app = make_app(Settings(secret_key="test", demo_mode=False, identity_mode="entra", storage_mode="demo", entra_client_id="client", entra_client_secret="secret", entra_tenant_id="tenant"))
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
    callback_keys = set(app.callback_map)
    assert any("shipment-grid.rowData" in key for key in callback_keys)
    assert any("purchase-history.children" in key for key in callback_keys)


def test_entra_routes_are_closed_in_demo_mode():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo", identity_mode="demo"))
    client = app.server.test_client()
    assert client.get("/auth/login").status_code == 403
    client.post("/auth/demo", json={"username": "demo.viewer"})
    assert client.post("/auth/logout").get_json()["status"] == "signed_out"


def test_dash_surface_redirects_unauthenticated_entra_requests():
    settings = Settings(identity_mode="entra", demo_mode=False, storage_mode="demo", entra_client_id="client", entra_client_secret="secret", entra_tenant_id="tenant")
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
