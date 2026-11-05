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


class PortalTokenExchange:
    def __init__(self, private_key: str, public_key: str, issuer: str, audience: str, replay: ReplayStore | None = None):
        self.private_key, self.public_key, self.issuer, self.audience = private_key, public_key, issuer, audience
        self.replay = replay or ReplayStore()

    def issue(self, subject: str, roles: list[str]) -> str:
        now = datetime.now(timezone.utc)
        claims = {"sub": subject, "roles": roles, "iss": self.issuer, "aud": self.audience, "iat": now, "nbf": now, "exp": now + timedelta(minutes=2), "jti": secrets.token_urlsafe(16)}
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "demo-key-1"})

    def exchange(self, token: str) -> dict:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or header.get("kid") != "demo-key-1":
            raise PermissionError("token algorithm or key id rejected")
        claims = jwt.decode(token, self.public_key, algorithms=["RS256"], issuer=self.issuer, audience=self.audience, options={"require": ["exp", "iat", "nbf", "iss", "aud", "jti", "sub"]})
        expiry = datetime.fromtimestamp(claims["exp"], timezone.utc)
        if not self.replay.consume(claims["jti"], expiry):
            raise PermissionError("token replay rejected")
        return claims
