import json
from urllib.parse import parse_qs, urlparse

import pytest

from harvestops.auth import EntraAuth
from harvestops.config import Settings
from harvestops.web import make_app


class DiscoveryResponse:
    status_code = 200
    headers = {}

    def __init__(self):
        self.text = json.dumps(
            {
                "authorization_endpoint": "https://login.test/tenant/oauth2/v2.0/authorize",
                "token_endpoint": "https://login.test/tenant/oauth2/v2.0/token",
                "issuer": "https://login.test/tenant/v2.0",
                "jwks_uri": "https://login.test/tenant/discovery/v2.0/keys",
                "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
                "end_session_endpoint": "https://login.test/tenant/oauth2/v2.0/logout",
            }
        )


class DiscoveryHttpClient:
    def get(self, *_args, **_kwargs):
        return DiscoveryResponse()

    def post(self, *_args, **_kwargs):
        return DiscoveryResponse()

    def close(self):
        return None


def entra_settings():
    return Settings(
        secret_key="test",
        demo_mode=False,
        identity_mode="entra",
        storage_mode="demo",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
    )


def test_msal_auth_code_flow_constructs_state_nonce_and_pkce_without_reserved_input_scopes():
    auth = EntraAuth(entra_settings(), http_client=DiscoveryHttpClient())
    flow = auth.begin("csrf-state")
    query = parse_qs(urlparse(flow["auth_uri"]).query)

    assert query["state"] == ["csrf-state"]
    assert query["response_mode"] == ["form_post"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    assert flow["code_verifier"]
    assert flow["nonce"]
    assert set(query["scope"][0].split()).issuperset({"openid", "profile", "offline_access"})
    assert "email" not in query["scope"][0].split()


def test_failed_token_exchange_fails_closed(monkeypatch):
    auth = EntraAuth(entra_settings(), http_client=DiscoveryHttpClient())
    flow = auth.begin("csrf-state")
    monkeypatch.setattr(
        auth.client,
        "acquire_token_by_auth_code_flow",
        lambda _flow, _response: {"error": "invalid_grant"},
    )
    with pytest.raises(PermissionError, match="authorization failed"):
        auth.redeem(flow, {"state": "csrf-state", "code": "bad-code"})


def test_entra_login_callback_maps_roles_and_logout(monkeypatch):
    class FakeEntraAuth:
        def __init__(self, _settings):
            pass

        def begin(self, state):
            return {
                "auth_uri": "https://login.test/authorize",
                "state": state,
                "nonce": "nonce",
                "code_verifier": "verifier",
            }

        def redeem(self, flow, response):
            assert flow["state"] == response["state"]
            assert response["code"] == "valid-code"
            return {
                "preferred_username": "operator@example.test",
                "name": "Operator Example",
                "roles": ["HarvestOps.Operator"],
            }

    monkeypatch.setattr("harvestops.web.EntraAuth", FakeEntraAuth)
    app = make_app(entra_settings())
    client = app.server.test_client()
    login = client.get("/auth/login")
    assert login.status_code == 302
    with client.session_transaction() as session:
        state = session["entra_flow"]["state"]

    callback = client.post(
        "/auth/callback",
        data={"state": state, "code": "valid-code"},
    )
    assert callback.status_code == 200
    assert callback.get_json()["roles"] == ["operator", "viewer"]
    csrf = client.get("/api/csrf").get_json()["csrf_token"]
    signed_out = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert signed_out.get_json()["status"] == "signed_out"
    assert client.get("/api/csrf").status_code == 403
