from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from harvestops.mcp_server import (
    approved_kpi_definitions,
    list_shipment_exceptions,
    lookup_shipment,
)


def test_mcp_tools_require_principal_and_limit_results():
    result = lookup_shipment("SHP-1001", "demo.viewer")
    assert result["found"] is True
    assert approved_kpi_definitions("demo.viewer")
    assert len(list_shipment_exceptions("demo.viewer", 100)) <= 20
    with pytest.raises(PermissionError):
        lookup_shipment("SHP-1001", "unknown")
    with pytest.raises(ValueError):
        lookup_shipment("x" * 31, "demo.viewer")
    with pytest.raises(ValueError):
        list_shipment_exceptions("demo.viewer", "many")


def test_exposed_mcp_requires_verified_principal_token(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setenv("MCP_EXPOSED", "true")
    monkeypatch.setenv("MCP_AUTH_PUBLIC_KEY", public_pem)
    monkeypatch.setenv("MCP_AUTH_ISSUER", "https://issuer.example")
    monkeypatch.setenv("MCP_AUTH_AUDIENCE", "harvestops-mcp")
    with pytest.raises(PermissionError):
        lookup_shipment("SHP-1001", "demo.viewer")
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "demo.viewer", "roles": ["viewer"], "iss": "https://issuer.example", "aud": "harvestops-mcp", "iat": now, "nbf": now, "exp": now + timedelta(minutes=2)}, private_pem, algorithm="RS256")
    assert lookup_shipment("SHP-1001", "demo.viewer", token)["found"] is True
    with pytest.raises(PermissionError, match="mismatch"):
        lookup_shipment("SHP-1001", "demo.operator", token)
