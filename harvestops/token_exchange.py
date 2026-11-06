import secrets
from datetime import datetime, timedelta, timezone

import jwt


class ReplayStore:
    def __init__(self):
        self.used: dict[str, datetime] = {}

    def consume(self, jti: str, expiry: datetime) -> bool:
        now = datetime.now(timezone.utc)
        self.used = {key: value for key, value in self.used.items() if value > now}
        if jti in self.used:
            return False
        self.used[jti] = expiry
        return True


class RedisReplayStore:
    """Shared, atomic replay protection for multi-worker deployments."""

    def __init__(self, redis_client, prefix: str = "harvestops:portal-replay:"):
        self.redis = redis_client
        self.prefix = prefix

    def consume(self, jti: str, expiry: datetime) -> bool:
        ttl = max(1, int((expiry - datetime.now(timezone.utc)).total_seconds()))
        return bool(self.redis.set(f"{self.prefix}{jti}", "1", nx=True, ex=ttl))


class PortalTokenExchange:
    def __init__(
        self,
        private_key: str,
        public_key: str,
        issuer: str,
        audience: str,
        replay: ReplayStore | None = None,
        key_id: str = "demo-key-1",
        verification_keys: dict[str, str] | None = None,
    ):
        self.private_key, self.public_key, self.issuer, self.audience = (
            private_key,
            public_key,
            issuer,
            audience,
        )
        self.replay = replay or ReplayStore()
        self.key_id = key_id
        self.verification_keys = dict(verification_keys or {})
        self.verification_keys.setdefault(key_id, public_key)

    def issue(self, subject: str, roles: list[str]) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "sub": subject,
            "roles": roles,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=2),
            "jti": secrets.token_urlsafe(16),
        }
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.key_id})

    def exchange(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise PermissionError("token algorithm or key id rejected") from exc
        key_id = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(key_id, str):
            raise PermissionError("token algorithm or key id rejected")
        verification_key = self.verification_keys.get(key_id)
        if not verification_key:
            raise PermissionError("token algorithm or key id rejected")
        claims = jwt.decode(
            token,
            verification_key,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.audience,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "jti", "sub"]},
        )
        expiry = datetime.fromtimestamp(claims["exp"], timezone.utc)
        if not self.replay.consume(claims["jti"], expiry):
            raise PermissionError("token replay rejected")
        return claims
