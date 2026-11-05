"""SQL Server implementation of the service contract used by the Dash UI.

The demo store remains intentionally separate. This adapter keeps authorization and
workflow rules in Python while using parameterized T-SQL transactions for persistence.
"""

import csv
import io
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .config import Settings
from .domain import AuditEvent, PurchaseLine, PurchaseRequest, Shipment, User, utc_now
from .repository import SqlServerRepository
from .services import ALLOWED_TRANSITIONS, STATUSES, DomainError


class SqlServerStore:
    def __init__(self, settings: Settings):
        self.repository = SqlServerRepository(settings)
        self.users = {
            "demo.viewer": User("demo.viewer", "Demo Viewer", {"viewer"}),
            "demo.operator": User("demo.operator", "Demo Operator", {"viewer", "operator"}),
            "demo.approver": User("demo.approver", "Demo Approver", {"viewer", "approver"}),
            "demo.admin": User("demo.admin", "Demo Admin", {"viewer", "operator", "approver", "admin"}),
        }

    @staticmethod
    def _shipment(row: dict) -> Shipment:
        version = int.from_bytes(row["row_version"], "big") if isinstance(row["row_version"], bytes) else int(row["row_version"])
        return Shipment(row["shipment_id"], row["customer_name"], row["product_name"], row["facility_name"], row["carrier_name"], row["dock_code"], row["appointment_utc"].replace(tzinfo=timezone.utc), row["planned_departure_utc"].replace(tzinfo=timezone.utc), row["actual_departure_utc"].replace(tzinfo=timezone.utc) if row["actual_departure_utc"] else None, Decimal(row["ordered_qty"]), Decimal(row["shipped_qty"]), Decimal(row["freight_cost"]), row["status"], version)

    def filter_options(self) -> dict[str, list[str]]:
        return {key: [row["value"] for row in self.repository.query(f"SELECT DISTINCT {column} AS value FROM dbo.v_shipment_board ORDER BY {column}")]
                for key, column in (("customer", "customer_name"), ("product", "product_name"), ("facility", "facility_name"))}

    def list_shipments(self, filters: dict, page: int = 1, page_size: int = 25) -> tuple[list[Shipment], int]:
        rows = self.repository.shipment_rows(filters, page, page_size)
        return [self._shipment(row) for row in rows], self.repository.shipment_count(filters)

    def export_shipments(self) -> list[dict]:
        rows = self.repository.query("SELECT shipment_id, customer_name AS customer, product_name AS product, status, freight_cost FROM dbo.v_shipment_board ORDER BY planned_departure_utc")
        return rows

    def kpis(self, filters: dict) -> dict:
        rows, _ = self.list_shipments(filters, 1, 100000)
        total_ordered = sum((r.ordered_qty for r in rows), Decimal(0))
        total_shipped = sum((r.shipped_qty for r in rows), Decimal(0))
        closed = [r for r in rows if r.actual_departure_utc]
        return {"shipment_volume": len(rows), "on_time_rate": (sum(1 for r in closed if r.on_time) / len(closed) * 100) if closed else 0, "fill_rate": (float(total_shipped / total_ordered) * 100) if total_ordered else 0, "freight_cost": float(sum((r.freight_cost for r in rows), Decimal(0))), "production_output": int(total_shipped * Decimal("1.12")), "labor_productivity": round(float(total_shipped / max(len(rows), 1)), 1)}

    def change_status(self, shipment_id: str, new_status: str, actor: User, expected_version: int) -> Shipment:
        if "operator" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Operator role required")
        if new_status not in STATUSES:
            raise DomainError("Unknown shipment status")
        with self.repository.connect() as conn:
            current = self.repository.rows(conn.execute("SELECT status, row_version FROM dbo.shipments WHERE shipment_id = ?", shipment_id))
            if not current:
                raise DomainError("Shipment not found")
            old_status = current[0]["status"]
            version = int.from_bytes(current[0]["row_version"], "big")
            if version != expected_version:
                raise DomainError("Shipment is stale; it changed since it was loaded; refresh before editing")
            if new_status not in ALLOWED_TRANSITIONS[old_status]:
                raise DomainError(f"Cannot change {old_status} to {new_status}")
            cursor = conn.execute("UPDATE dbo.shipments SET status = ?, actual_departure_utc = CASE WHEN ? IN ('In Transit','Delivered') AND actual_departure_utc IS NULL THEN SYSUTCDATETIME() ELSE actual_departure_utc END WHERE shipment_id = ? AND row_version = ?", new_status, new_status, shipment_id, current[0]["row_version"])
            if cursor.rowcount != 1:
                raise DomainError("Shipment is stale; it changed since it was loaded; refresh before editing")
            conn.execute("INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, ?, ?, ?, ?)", actor.username, "shipment.status_changed", "shipment", shipment_id, f'{{"from":"{old_status}","to":"{new_status}"}}')
            conn.commit()
        rows, _ = self.list_shipments({"shipment_id": shipment_id}, 1, 1)
        if rows:
            return rows[0]
        raise DomainError("Shipment disappeared after update")

    def _purchase(self, request_id: str) -> PurchaseRequest:
        rows = self.repository.query("""SELECT r.request_id, r.requester, f.facility_name, r.status, r.comment, r.version_no, r.created_utc, p.product_name, l.quantity, l.unit_cost
            FROM dbo.purchase_requests r JOIN dbo.facilities f ON f.facility_id = r.facility_id
            LEFT JOIN dbo.purchase_request_lines l ON l.request_id = r.request_id
            LEFT JOIN dbo.products p ON p.product_id = l.product_id WHERE r.request_id = ? ORDER BY l.request_line_id""", (request_id,))
        if not rows:
            raise DomainError("Purchase request not found")
        first = rows[0]
        lines = [PurchaseLine(row["product_name"], Decimal(row["quantity"]), Decimal(row["unit_cost"])) for row in rows if row["product_name"]]
        return PurchaseRequest(first["request_id"], first["requester"], first["facility_name"], first["status"], first["created_utc"].replace(tzinfo=timezone.utc), first["comment"], lines, first["version_no"])

    def list_purchases(self) -> list[PurchaseRequest]:
        ids = self.repository.query("SELECT request_id FROM dbo.purchase_requests ORDER BY created_utc DESC")
        return [self._purchase(row["request_id"]) for row in ids]

    def purchase_history(self) -> list[AuditEvent]:
        rows = self.repository.query("SELECT CONVERT(varchar(32), audit_event_id) AS event_id, actor, action_name, entity_type, entity_id, detail_json, occurred_utc FROM dbo.audit_events WHERE entity_type = 'purchase_request' ORDER BY occurred_utc")
        return [AuditEvent(row["event_id"], row["actor"], row["action_name"], row["entity_type"], row["entity_id"], {"raw": row["detail_json"]}, row["occurred_utc"].replace(tzinfo=timezone.utc)) for row in rows]

    def create_purchase(self, requester: User, facility: str, lines: list[dict]) -> PurchaseRequest:
        if not lines:
            raise DomainError("At least one request line is required")
        parsed = []
        for line in lines:
            try:
                qty, cost = Decimal(str(line["quantity"])), Decimal(str(line["unit_cost"]))
            except (KeyError, InvalidOperation) as exc:
                raise DomainError("Quantity and unit cost must be numeric") from exc
            if qty <= 0 or cost < 0:
                raise DomainError("Quantity must be positive and cost cannot be negative")
            parsed.append((str(line["product"])[:80], qty, cost))
        request_id = "PR-" + secrets.token_hex(5).upper()
        with self.repository.connect() as conn:
            facility_row = self.repository.rows(conn.execute("SELECT facility_id FROM dbo.facilities WHERE facility_name = ?", facility))
            if not facility_row:
                raise DomainError("Facility not found")
            conn.execute("INSERT dbo.purchase_requests(request_id, requester, facility_id, status) VALUES (?, ?, ?, 'Draft')", request_id, requester.username, facility_row[0]["facility_id"])
            for product, qty, cost in parsed:
                product_row = self.repository.rows(conn.execute("SELECT product_id FROM dbo.products WHERE product_name = ?", product))
                if not product_row:
                    raise DomainError(f"Product not found: {product}")
                conn.execute("INSERT dbo.purchase_request_lines(request_id, product_id, quantity, unit_cost) VALUES (?, ?, ?, ?)", request_id, product_row[0]["product_id"], qty, cost)
            conn.execute("INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, 'purchase.created', 'purchase_request', ?, ?)", requester.username, request_id, "{}")
            conn.commit()
        return self._purchase(request_id)

    def submit_purchase(self, request_id: str, actor: User, expected_version: int) -> PurchaseRequest:
        request = self._purchase(request_id)
        if request.requester != actor.username and "admin" not in actor.roles:
            raise PermissionError("Only the requester or an admin can submit")
        if request.status != "Draft" or request.version != expected_version:
            raise DomainError("Purchase request changed; refresh before submitting")
        self._update_purchase(request_id, "Pending", "", actor, expected_version, "purchase.submitted")
        return self._purchase(request_id)

    def decide_purchase(self, request_id: str, actor: User, decision: str, comment: str, expected_version: int) -> PurchaseRequest:
        request = self._purchase(request_id)
        if request.requester == actor.username:
            raise PermissionError("Self-approval is not permitted")
        if "approver" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Approver role required")
        if decision not in {"Approved", "Rejected"} or request.status != "Pending" or request.version != expected_version:
            raise DomainError("Request is stale or not pending")
        self._update_purchase(request_id, decision, comment[:500], actor, expected_version, f"purchase.{decision.lower()}")
        return self._purchase(request_id)

    def _update_purchase(self, request_id: str, status: str, comment: str, actor: User, version: int, action: str) -> None:
        with self.repository.connect() as conn:
            cursor = conn.execute("UPDATE dbo.purchase_requests SET status = ?, comment = ?, version_no = version_no + 1, updated_utc = SYSUTCDATETIME() WHERE request_id = ? AND version_no = ?", status, comment, request_id, version)
            if cursor.rowcount != 1:
                raise DomainError("Request is stale or not pending")
            conn.execute("INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, ?, 'purchase_request', ?, ?)", actor.username, action, request_id, "{}")
            conn.commit()

    def import_shipments(self, text: str, actor: User) -> dict:
        if "operator" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Operator role required")
        reader = csv.DictReader(io.StringIO(text))
        errors, valid = [], []
        for line_no, row in enumerate(reader, 2):
            try:
                qty, shipped = Decimal(row["ordered_qty"]), Decimal(row["shipped_qty"])
                planned = datetime.fromisoformat(row["planned_departure_utc"].replace("Z", "+00:00"))
                if not row.get("shipment_id") or qty <= 0 or shipped < 0 or shipped > qty:
                    raise ValueError
                valid.append((line_no, row, qty, shipped, planned))
            except (KeyError, InvalidOperation, ValueError):
                errors.append({"line": line_no, "error": "invalid shipment record"})
        run_id = "SQL-" + secrets.token_hex(5).upper()
        applied = 0
        with self.repository.connect() as conn:
            conn.execute("INSERT dbo.import_runs(source_name, status) VALUES ('shipment-update.csv', 'Started')")
            for line_no, row, qty, shipped, planned in valid:
                exists = self.repository.rows(conn.execute("SELECT 1 AS found FROM dbo.shipments WHERE shipment_id = ?", row["shipment_id"]))
                if exists:
                    continue
                refs = self.repository.rows(conn.execute("""SELECT c.customer_id, p.product_id, f.facility_id, ca.carrier_id FROM dbo.customers c CROSS JOIN dbo.products p CROSS JOIN dbo.facilities f CROSS JOIN dbo.carriers ca WHERE c.customer_name=? AND p.product_name=? AND f.facility_name=? AND ca.carrier_name=?""", row["customer"], row["product"], row["facility"], row["carrier"]))
                if not refs:
                    errors.append({"line": line_no, "error": "unknown customer, product, facility, or carrier"})
                    continue
                ref = refs[0]
                conn.execute("""INSERT dbo.shipments(shipment_id, customer_id, product_id, facility_id, carrier_id, dock_code, appointment_utc, planned_departure_utc, ordered_qty, shipped_qty, freight_cost, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", row["shipment_id"], ref["customer_id"], ref["product_id"], ref["facility_id"], ref["carrier_id"], row.get("dock", "D-01"), planned - timedelta(hours=2), planned, qty, shipped, Decimal(row.get("freight_cost", "0")), row.get("status", "Scheduled"))
                applied += 1
            conn.commit()
        return {"run_id": run_id, "actor": actor.username, "applied": applied, "errors": errors, "occurred_utc": utc_now().isoformat()}
