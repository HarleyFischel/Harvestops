"""Read-only MCP example using the official MCP Python SDK."""
from mcp.server.fastmcp import FastMCP

from .services import InMemoryStore

mcp = FastMCP("HarvestOps read-only operations")
store = InMemoryStore()


def _require_principal(principal: str):
    user = store.users.get(principal)
    if not user:
        raise PermissionError("authenticated principal required")
    return user


@mcp.tool()
def lookup_shipment(shipment_id: str, principal: str) -> dict:
    _require_principal(principal)
    row = store.shipments.get(shipment_id)
    if not row:
        return {"found": False}
    return {"found": True, "shipment_id": row.shipment_id, "customer": row.customer, "product": row.product, "facility": row.facility, "status": row.status, "ordered_qty": str(row.ordered_qty), "shipped_qty": str(row.shipped_qty)}


@mcp.tool()
def list_shipment_exceptions(principal: str, limit: int = 20) -> list[dict]:
    _require_principal(principal)
    limit = max(1, min(limit, 20))
    return [{"shipment_id": row.shipment_id, "status": row.status, "customer": row.customer, "fill_rate": round(row.fill_rate, 4)} for row in store.shipments.values() if row.status == "Exception"][:limit]


@mcp.tool()
def approved_kpi_definitions(principal: str) -> list[dict]:
    _require_principal(principal)
    return [{"name": "fill_rate", "definition": "shipped quantity / ordered quantity"}, {"name": "on_time_rate", "definition": "on-time departures / closed shipments"}]


if __name__ == "__main__":
    mcp.run()
