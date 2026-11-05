import csv
import io
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .domain import AuditEvent, PurchaseLine, PurchaseRequest, Shipment, User, utc_now

STATUSES = ("Scheduled", "In Transit", "Delivered", "Exception", "Cancelled")
ALLOWED_TRANSITIONS = {
    "Scheduled": {"In Transit", "Cancelled", "Exception"},
    "In Transit": {"Delivered", "Exception"},
    "Delivered": set(),
    "Exception": {"In Transit", "Cancelled"},
    "Cancelled": set(),
}


class DomainError(ValueError):
    pass


class InMemoryStore:
    """Deterministic demo store. It is intentionally not presented as SQL Server."""

    def __init__(self) -> None:
        self.users = {
            "demo.viewer": User("demo.viewer", "Demo Viewer", {"viewer"}),
            "demo.operator": User("demo.operator", "Demo Operator", {"viewer", "operator"}),
            "demo.approver": User("demo.approver", "Demo Approver", {"viewer", "approver"}),
            "demo.admin": User("demo.admin", "Demo Admin", {"viewer", "operator", "approver", "admin"}),
        }
        self.shipments = self._seed_shipments()
        self.purchases: dict[str, PurchaseRequest] = {}
        self.audit: list[AuditEvent] = []
        self.import_runs: list[dict] = []

    @staticmethod
    def _seed_shipments() -> dict[str, Shipment]:
        base = datetime(2026, 1, 5, 13, tzinfo=timezone.utc)
        rows = [
            ("SHP-1001", "FreshMart Northeast", "Romaine Hearts", "Salinas", "GreenLine", "D-01", 1200, 1200, 1820, "Delivered", 0),
            ("SHP-1002", "Harvest Grocers", "Baby Spinach", "Yuma", "Westway", "D-04", 900, 780, 1440, "Exception", 3),
            ("SHP-1003", "City Market", "Spring Mix", "Salinas", "GreenLine", "D-02", 1500, 1500, 2100, "In Transit", 7),
            ("SHP-1004", "FreshMart Northeast", "Iceberg Lettuce", "Oxnard", "NorthStar", "D-03", 1100, 1100, 1750, "Scheduled", 10),
            ("SHP-1005", "Harvest Grocers", "Romaine Hearts", "Salinas", "Westway", "D-05", 800, 800, 1290, "Delivered", 14),
            ("SHP-1006", "City Market", "Baby Spinach", "Yuma", "NorthStar", "D-01", 1000, 920, 1605, "Exception", 17),
            ("SHP-1007", "FreshMart Northeast", "Spring Mix", "Oxnard", "GreenLine", "D-02", 1300, 1300, 1980, "Delivered", 21),
            ("SHP-1008", "Harvest Grocers", "Iceberg Lettuce", "Salinas", "Westway", "D-06", 700, 700, 1180, "Cancelled", 24),
        ]
        result = {}
        for sid, customer, product, facility, carrier, dock, ordered, shipped, freight, status, days in rows:
            planned = base + timedelta(days=days, hours=2)
            actual = None if status in {"Scheduled", "Cancelled"} else planned + timedelta(hours=2 if "1002" in sid or "1006" in sid else -1)
            result[sid] = Shipment(sid, customer, product, facility, carrier, dock, planned - timedelta(hours=2), planned, actual, Decimal(ordered), Decimal(shipped), Decimal(freight), status)
        return result

    def list_shipments(self, filters: dict, page: int = 1, page_size: int = 25) -> tuple[list[Shipment], int]:
        rows = list(self.shipments.values())
        for field in ("customer", "product", "facility"):
            value = filters.get(field)
            if value and value != "All":
                rows = [r for r in rows if getattr(r, field) == value]
        if filters.get("exceptions_only"):
            rows = [r for r in rows if r.status == "Exception"]
        rows.sort(key=lambda x: x.planned_departure_utc)
        total = len(rows)
        start = max(0, (page - 1) * page_size)
        return rows[start : start + page_size], total

    def kpis(self, filters: dict) -> dict:
        rows, _ = self.list_shipments(filters, 1, 10_000)
        total_ordered = sum((r.ordered_qty for r in rows), Decimal(0))
        total_shipped = sum((r.shipped_qty for r in rows), Decimal(0))
        closed = [r for r in rows if r.actual_departure_utc]
        on_time = sum(1 for r in closed if r.on_time)
        return {
            "shipment_volume": len(rows),
            "on_time_rate": (on_time / len(closed) * 100) if closed else 0,
            "fill_rate": (float(total_shipped / total_ordered) * 100) if total_ordered else 0,
            "freight_cost": float(sum((r.freight_cost for r in rows), Decimal(0))),
            "production_output": int(total_shipped * Decimal("1.12")),
            "labor_productivity": round(float(total_shipped / max(len(rows), 1)), 1),
        }

    def change_status(self, shipment_id: str, new_status: str, actor: User, expected_version: int) -> Shipment:
        if "operator" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Operator role required")
        if new_status not in STATUSES:
            raise DomainError("Unknown shipment status")
        shipment = self.shipments.get(shipment_id)
        if not shipment:
            raise DomainError("Shipment not found")
        if shipment.version != expected_version:
            raise DomainError("Shipment is stale; it changed since it was loaded; refresh before editing")
        if new_status not in ALLOWED_TRANSITIONS[shipment.status]:
            raise DomainError(f"Cannot change {shipment.status} to {new_status}")
        old = shipment.status
        shipment.status = new_status
        shipment.version += 1
        self.audit.append(AuditEvent(secrets.token_hex(8), actor.username, "shipment.status_changed", "shipment", shipment_id, {"from": old, "to": new_status}, utc_now()))
        return shipment

    def create_purchase(self, requester: User, facility: str, lines: list[dict]) -> PurchaseRequest:
        if not lines:
            raise DomainError("At least one request line is required")
        parsed: list[PurchaseLine] = []
        for line in lines:
            try:
                qty = Decimal(str(line["quantity"]))
                cost = Decimal(str(line["unit_cost"]))
            except (KeyError, InvalidOperation) as exc:
                raise DomainError("Quantity and unit cost must be numeric") from exc
            if qty <= 0 or cost < 0:
                raise DomainError("Quantity must be positive and cost cannot be negative")
            parsed.append(PurchaseLine(str(line["product"])[:80], qty, cost))
        request = PurchaseRequest(f"PR-{len(self.purchases) + 1001}", requester.username, facility, "Draft", utc_now(), lines=parsed)
        self.purchases[request.request_id] = request
        self.audit.append(AuditEvent(secrets.token_hex(8), requester.username, "purchase.created", "purchase_request", request.request_id, {"total": str(request.total)}, utc_now()))
        return request

    def submit_purchase(self, request_id: str, actor: User, expected_version: int) -> PurchaseRequest:
        request = self._purchase(request_id)
        if request.requester != actor.username and "admin" not in actor.roles:
            raise PermissionError("Only the requester or an admin can submit")
        if request.version != expected_version:
            raise DomainError("Purchase request changed; refresh before submitting")
        if request.status != "Draft":
            raise DomainError("Only draft requests can be submitted")
        request.status = "Pending"
        request.version += 1
        self.audit.append(AuditEvent(secrets.token_hex(8), actor.username, "purchase.submitted", "purchase_request", request_id, {}, utc_now()))
        return request

    def decide_purchase(self, request_id: str, actor: User, decision: str, comment: str, expected_version: int) -> PurchaseRequest:
        request = self._purchase(request_id)
        if request.requester == actor.username:
            raise PermissionError("Self-approval is not permitted")
        if "approver" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Approver role required")
        if request.status != "Pending" or request.version != expected_version:
            raise DomainError("Request is stale or not pending")
        if decision not in {"Approved", "Rejected"}:
            raise DomainError("Decision must be Approved or Rejected")
        request.status, request.comment, request.version = decision, comment[:500], request.version + 1
        self.audit.append(AuditEvent(secrets.token_hex(8), actor.username, f"purchase.{decision.lower()}", "purchase_request", request_id, {"comment": request.comment}, utc_now()))
        return request

    def _purchase(self, request_id: str) -> PurchaseRequest:
        if request_id not in self.purchases:
            raise DomainError("Purchase request not found")
        return self.purchases[request_id]

    def import_shipments(self, text: str, actor: User) -> dict:
        if "operator" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Operator role required")
        reader = csv.DictReader(io.StringIO(text))
        errors, applied, seen = [], 0, set()
        for line_no, row in enumerate(reader, 2):
            sid = (row.get("shipment_id") or "").strip()
            if not sid or sid in seen:
                errors.append({"line": line_no, "error": "missing or duplicate shipment_id"})
                continue
            seen.add(sid)
            if sid in self.shipments:
                continue
            try:
                qty = Decimal(row["ordered_qty"])
                shipped = Decimal(row["shipped_qty"])
                if qty <= 0 or shipped < 0 or shipped > qty:
                    raise ValueError
            except (KeyError, InvalidOperation, ValueError):
                errors.append({"line": line_no, "error": "invalid quantities"})
                continue
            planned = datetime.fromisoformat(row["planned_departure_utc"].replace("Z", "+00:00"))
            self.shipments[sid] = Shipment(sid, row["customer"], row["product"], row["facility"], row["carrier"], row.get("dock", "D-01"), planned - timedelta(hours=2), planned, None, qty, shipped, Decimal(row.get("freight_cost", "0")), row.get("status", "Scheduled"))
            applied += 1
        run = {"run_id": f"IMP-{len(self.import_runs)+1:04}", "actor": actor.username, "applied": applied, "errors": errors, "occurred_utc": utc_now().isoformat()}
        self.import_runs.append(run)
        self.audit.append(AuditEvent(secrets.token_hex(8), actor.username, "shipment.import", "import_run", run["run_id"], run, utc_now()))
        return run
