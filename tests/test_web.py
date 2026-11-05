from harvestops.config import Settings
from harvestops.web import make_app


def test_health_and_readiness():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").get_json()["status"] == "ready"


def test_export_requires_operator_role():
    app = make_app(Settings(secret_key="test", demo_mode=True, storage_mode="demo"))
    client = app.server.test_client()
    assert client.get("/api/shipments/export").status_code == 403
    client.post("/auth/demo", json={"username": "demo.operator"})
    response = client.get("/api/shipments/export")
    assert response.status_code == 200
    assert "shipment_id" in response.text


def test_demo_identity_cannot_be_enabled_in_production():
    try:
        make_app(Settings(secret_key="test", app_env="production", demo_mode=True, storage_mode="demo"))
    except RuntimeError as exc:
        assert "DEMO_MODE" in str(exc)
    else:
        raise AssertionError("production demo mode must fail closed")
