from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import ExpiredSignatureError, InvalidAudienceError, InvalidSignatureError

from harvestops.token_exchange import PortalTokenExchange, RedisReplayStore


@pytest.fixture
def exchange():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return PortalTokenExchange(private_pem, public_pem, "https://portal.example", "harvestops")


def test_portal_token_is_single_use(exchange):
    token = exchange.issue("demo.operator", ["operator"])
    assert exchange.exchange(token)["sub"] == "demo.operator"
    with pytest.raises(PermissionError, match="replay"):
        exchange.exchange(token)


def test_portal_token_rejects_wrong_audience(exchange):
    token = exchange.issue("demo.operator", ["operator"])
    other = PortalTokenExchange(exchange.private_key, exchange.public_key, exchange.issuer, "other-audience")
    with pytest.raises(InvalidAudienceError):
        other.exchange(token)


def test_redis_replay_store_uses_atomic_single_use_semantics():
    class FakeRedis:
        def __init__(self):
            self.values = set()

        def set(self, key, value, nx, ex):
            assert nx is True
            assert ex > 0
            if key in self.values:
                return False
            self.values.add(key)
            return True

    store = RedisReplayStore(FakeRedis())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=2)
    assert store.consume("jti-1", expiry) is True
    assert store.consume("jti-1", expiry) is False


def test_portal_token_rejects_tampering_and_expiry(exchange):
    token = exchange.issue("demo.operator", ["operator"])
    parts = token.split(".")
    parts[-1] = ("A" if parts[-1][0] != "A" else "B") + parts[-1][1:]
    with pytest.raises(InvalidSignatureError):
        exchange.exchange(".".join(parts))
    expired = jwt.encode({"sub": "demo.operator", "roles": [], "iss": exchange.issuer, "aud": exchange.audience, "iat": datetime.now(timezone.utc) - timedelta(minutes=5), "nbf": datetime.now(timezone.utc) - timedelta(minutes=5), "exp": datetime.now(timezone.utc) - timedelta(minutes=1), "jti": "expired-jti"}, exchange.private_key, algorithm="RS256", headers={"kid": "demo-key-1"})
    with pytest.raises(ExpiredSignatureError):
        exchange.exchange(expired)
