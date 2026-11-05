"""Read-only MCP example using the official MCP Python SDK."""
import os

import jwt
from mcp.server.fastmcp import FastMCP

from .domain import User
from .knowledge import KnowledgeService
from .services import InMemoryStore

mcp = FastMCP("HarvestOps read-only operations")
store = InMemoryStore()
knowledge = KnowledgeService()


def _validate_principal(principal: str) -> None:
    if not isinstance(principal, str) or not principal or len(principal) > 200:
        raise ValueError("principal must be a non-empty value under 200 characters")


def _bounded_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    return max(1, min(value, 20))


def _require_principal(principal: str, auth_token: str = ""):
    _validate_principal(principal)
    public_key = os.getenv("MCP_AUTH_PUBLIC_KEY", "")
    exposed = os.getenv("MCP_EXPOSED", "false").lower() == "true" or bool(public_key)
    if exposed:
        issuer = os.getenv("MCP_AUTH_ISSUER", "")
        audience = os.getenv("MCP_AUTH_AUDIENCE", "")
        if not public_key or not issuer or not audience or not auth_token:
            raise PermissionError("verified MCP authentication is required")
        try:
            header = jwt.get_unverified_header(auth_token)
            if header.get("alg") != "RS256":
                raise PermissionError("MCP token algorithm rejected")
            claims = jwt.decode(auth_token, public_key, algorithms=["RS256"], issuer=issuer, audience=audience, options={"require": ["exp", "nbf", "iat", "iss", "aud", "sub"]})
        except (jwt.PyJWTError, ValueError) as exc:
            raise PermissionError("verified MCP authentication is required") from exc
        if claims.get("sub") != principal:
            raise PermissionError("MCP principal mismatch")
        claim_roles = claims.get("roles", [])
        if isinstance(claim_roles, str):
            claim_roles = [claim_roles]
        roles = {role.removeprefix("HarvestOps.").lower() for role in claim_roles}
        if not roles.intersection({"viewer", "operator", "approver", "admin"}):
            raise PermissionError("MCP principal has no permitted role")
        return User(principal, claims.get("name", principal), roles)
    user = store.users.get(principal)
    if not user:
        raise PermissionError("authenticated principal required")
    return user


@mcp.tool()
def lookup_shipment(shipment_id: str, principal: str, auth_token: str = "") -> dict:
    _require_principal(principal, auth_token)
    if not isinstance(shipment_id, str) or not shipment_id or len(shipment_id) > 30:
        raise ValueError("shipment_id must be a non-empty value under 30 characters")
    row = store.get_shipment(shipment_id)
    if not row:
        return {"found": False}
    return {"found": True, "shipment_id": row.shipment_id, "customer": row.customer, "product": row.product, "facility": row.facility, "status": row.status, "ordered_qty": str(row.ordered_qty), "shipped_qty": str(row.shipped_qty)}


@mcp.tool()
def list_shipment_exceptions(principal: str, limit: int = 20, auth_token: str = "") -> list[dict]:
    _require_principal(principal, auth_token)
    limit = _bounded_limit(limit)
    rows, _ = store.list_shipments({"exceptions_only": True}, 1, limit)
    return [{"shipment_id": row.shipment_id, "status": row.status, "customer": row.customer, "fill_rate": round(row.fill_rate, 4)} for row in rows]


@mcp.tool()
def approved_kpi_definitions(principal: str, auth_token: str = "") -> list[dict]:
    user = _require_principal(principal, auth_token)
    return knowledge.approved_kpi_definitions(user)


if __name__ == "__main__":
    mcp.run()
