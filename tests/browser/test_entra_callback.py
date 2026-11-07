import socket
import threading
from urllib.parse import urlencode

import pytest
from flask import Flask, redirect, request
from werkzeug.serving import make_server

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

from harvestops.config import Settings
from harvestops.web import make_app


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_entra_top_level_get_callback_preserves_lax_session_across_origins(monkeypatch):
    app_port = free_port()
    idp_port = free_port()
    # Use different hostnames as well as different ports.  localhost and the
    # loopback IP are different sites for cookie SameSite calculations while
    # remaining fully local and deterministic for the browser test.
    app_origin = f"http://localhost:{app_port}"
    idp_origin = f"http://127.0.0.1:{idp_port}"
    settings = Settings(
        secret_key="test-secret",
        demo_mode=False,
        identity_mode="entra",
        storage_mode="demo",
        entra_client_id="client",
        entra_client_secret="secret",
        entra_tenant_id="tenant",
        entra_redirect_uri=f"{app_origin}/auth/callback",
    )

    identity_provider = Flask("fake_identity_provider")

    @identity_provider.get("/authorize")
    def authorize():
        return redirect(
            settings.entra_redirect_uri
            + "?"
            + urlencode({"state": request.args["state"], "code": "valid-code"})
        )

    class FakeEntraAuth:
        def __init__(self, _settings):
            pass

        def begin(self, state):
            return {
                "auth_uri": f"{idp_origin}/authorize?{urlencode({'state': state})}",
                "state": state,
                "nonce": "nonce",
                "code_verifier": "verifier",
            }

        def redeem(self, flow, response):
            assert response["state"] == flow["state"]
            assert response["code"] == "valid-code"
            return {
                "preferred_username": "operator@example.test",
                "name": "Operator Example",
                "roles": ["HarvestOps.Operator"],
            }

    monkeypatch.setattr("harvestops.web.EntraAuth", FakeEntraAuth)
    application = make_app(settings)
    app_server = make_server("127.0.0.1", app_port, application.server)
    idp_server = make_server("127.0.0.1", idp_port, identity_provider)
    app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
    idp_thread = threading.Thread(target=idp_server.serve_forever, daemon=True)
    app_thread.start()
    idp_thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(app_origin + "/auth/login", wait_until="networkidle")
            page.get_by_role("heading", name="Run the day from one operational view.").wait_for()
            assert page.url == app_origin + "/"
            assert page.get_by_text("SYNTHETIC DATA · ENTRA IDENTITY").count() == 1
            cookies = context.cookies(app_origin)
            session_cookie = next(cookie for cookie in cookies if cookie["name"] == "session")
            assert session_cookie["sameSite"] == "Lax"
            assert page.evaluate("async () => (await fetch('/api/csrf')).status") == 200
            browser.close()
    finally:
        app_server.shutdown()
        idp_server.shutdown()
        app_thread.join(timeout=2)
        idp_thread.join(timeout=2)
