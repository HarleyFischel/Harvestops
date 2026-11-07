"""SQL Server implementation of the service contract used by the Dash UI.

The demo store remains intentionally separate. This adapter keeps authorization and
workflow rules in Python while using parameterized T-SQL transactions for persistence.
"""

import csv
import io
import json
import secrets
from datetime import datetime, timezone
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
            "demo.admin": User(
                "demo.admin", "Demo Admin", {"viewer", "operator", "approver", "admin"}
            ),
        }

    @staticmethod
    def _shipment(row: dict) -> Shipment:
        version = (
            int.from_bytes(row["row_version"], "big")
            if isinstance(row["row_version"], bytes)
            else int(row["row_version"])
        )
        return Shipment(
            row["shipment_id"],
            row["customer_name"],
            row["product_name"],
            row["facility_name"],
            row["carrier_name"],
            row["dock_code"],
            row["appointment_utc"].replace(tzinfo=timezone.utc),
            row["planned_departure_utc"].replace(tzinfo=timezone.utc),
            row["actual_departure_utc"].replace(tzinfo=timezone.utc)
            if row["actual_departure_utc"]
            else None,
            Decimal(row["ordered_qty"]),
            Decimal(row["shipped_qty"]),
            Decimal(row["freight_cost"]),
            row["status"],
            version,
        )

    def filter_options(self) -> dict[str, list[str]]:
        return {
            key: [
                row["value"]
                for row in self.repository.query(
                    f"SELECT DISTINCT {column} AS value FROM dbo.v_shipment_board ORDER BY {column}"
                )
            ]
            for key, column in (
                ("customer", "customer_name"),
                ("product", "product_name"),
                ("facility", "facility_name"),
            )
        }

    def list_shipments(
        self, filters: dict, page: int = 1, page_size: int = 25
    ) -> tuple[list[Shipment], int]:
        rows = self.repository.shipment_rows(filters, page, page_size)
        return [self._shipment(row) for row in rows], self.repository.shipment_count(filters)

    def get_shipment(self, shipment_id: str) -> Shipment | None:
        row = self.repository.shipment_by_id(shipment_id)
        return self._shipment(row) if row else None

    def export_shipments(self) -> list[dict]:
        rows = self.repository.query(
            "SELECT shipment_id, customer_name AS customer, product_name AS product, status, freight_cost FROM dbo.v_shipment_board ORDER BY planned_departure_utc"
        )
        return rows

    def import_freshness(self) -> dict:
        rows = self.repository.query(
            "SELECT TOP (1) source_name, status, started_utc, completed_utc, applied_count, rejected_count "
            "FROM dbo.import_runs ORDER BY import_run_id DESC"
        )
        if not rows:
            return {
                "source": "synthetic seed",
                "status": "Seeded",
                "occurred_utc": "unknown",
                "applied": 0,
                "errors": 0,
            }
        row = rows[0]
        occurred = row["completed_utc"] or row["started_utc"]
        return {
            "source": row["source_name"],
            "status": row["status"],
            "occurred_utc": occurred.replace(tzinfo=timezone.utc).isoformat(),
            "applied": int(row["applied_count"]),
            "errors": int(row["rejected_count"]),
        }

    def import_history(self, limit: int = 5) -> list[dict]:
        limit = max(1, min(int(limit), 20))
        runs = self.repository.query(
            f"SELECT TOP ({limit}) import_run_id, source_name, status, started_utc, completed_utc, applied_count, rejected_count "
            "FROM dbo.import_runs ORDER BY import_run_id DESC"
        )
        history = []
        for row in runs:
            errors = self.repository.query(
                "SELECT TOP (20) source_row_no AS line, error_message AS error "
                "FROM dbo.import_errors WHERE import_run_id = ? ORDER BY import_error_id",
                (row["import_run_id"],),
            )
            history.append(
                {
                    "run_id": f"IMP-{int(row['import_run_id']):04d}",
                    "source": row["source_name"],
                    "status": row["status"],
                    "occurred_utc": (row["completed_utc"] or row["started_utc"])
                    .replace(tzinfo=timezone.utc)
                    .isoformat(),
                    "applied": int(row["applied_count"]),
                    "errors": errors,
                }
            )
        return history

    def kpis(self, filters: dict) -> dict:
        shipment = self.repository.shipment_kpis(filters)
        production = self.repository.production_kpis(filters)
        total_ordered = Decimal(str(shipment["ordered_qty"]))
        total_shipped = Decimal(str(shipment["shipped_qty"]))
        closed = int(shipment["closed_count"])
        production_output = Decimal(str(production["production_output"]))
        labor_hours = Decimal(str(production["labor_hours"]))
        return {
            "shipment_volume": int(shipment["shipment_volume"]),
            "on_time_rate": (int(shipment["on_time_count"]) / closed * 100) if closed else 0,
            "fill_rate": (float(total_shipped / total_ordered) * 100) if total_ordered else 0,
            "freight_cost": float(Decimal(str(shipment["freight_cost"]))),
            "production_output": int(production_output),
            "labor_productivity": round(float(production_output / labor_hours), 1)
            if labor_hours
            else 0,
        }

    def dashboard_volume(self, filters: dict) -> list[dict]:
        return self.repository.dashboard_volume(filters)

    def dashboard_service(self, filters: dict) -> dict[str, int]:
        return self.repository.dashboard_service(filters)

    def get_purchase(self, request_id: str, actor: User | None) -> PurchaseRequest | None:
        if not actor:
            return None
        return next(
            (request for request in self.list_purchases(actor) if request.request_id == request_id),
            None,
        )

    def shipment_audit_history(self, shipment_id: str) -> list[AuditEvent]:
        rows = self.repository.query(
            """SELECT CONVERT(varchar(32), audit_event_id) AS event_id, actor,
                      action_name, entity_type, entity_id, detail_json, occurred_utc
               FROM dbo.audit_events
               WHERE entity_type = 'shipment' AND entity_id = ?
               ORDER BY occurred_utc DESC""",
            (shipment_id,),
        )
        return [
            AuditEvent(
                row["event_id"],
                row["actor"],
                row["action_name"],
                row["entity_type"],
                row["entity_id"],
                {"raw": row["detail_json"]},
                row["occurred_utc"].replace(tzinfo=timezone.utc),
            )
            for row in rows
        ]

    def shipment_exceptions(self, filters: dict, limit: int = 50) -> list[Shipment]:
        return [self._shipment(row) for row in self.repository.shipment_exceptions(filters, limit)]

    def change_status(
        self, shipment_id: str, new_status: str, actor: User, expected_version: int
    ) -> Shipment:
        if not actor:
            raise PermissionError("Authenticated user required")
        if "operator" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Operator role required")
        if new_status not in STATUSES:
            raise DomainError("Unknown shipment status")
        with self.repository.connect() as conn:
            current = self.repository.rows(
                conn.execute(
                    "SELECT status, row_version FROM dbo.shipments WHERE shipment_id = ?",
                    shipment_id,
                )
            )
            if not current:
                raise DomainError("Shipment not found")
            old_status = current[0]["status"]
            version = int.from_bytes(current[0]["row_version"], "big")
            if version != expected_version:
                raise DomainError(
                    "Shipment is stale; it changed since it was loaded; refresh before editing"
                )
            if new_status not in ALLOWED_TRANSITIONS[old_status]:
                raise DomainError(f"Cannot change {old_status} to {new_status}")
            cursor = conn.execute(
                "UPDATE dbo.shipments SET status = ?, actual_departure_utc = CASE WHEN ? IN ('In Transit','Delivered') AND actual_departure_utc IS NULL THEN SYSUTCDATETIME() ELSE actual_departure_utc END WHERE shipment_id = ? AND row_version = ?",
                new_status,
                new_status,
                shipment_id,
                current[0]["row_version"],
            )
            if cursor.rowcount != 1:
                raise DomainError(
                    "Shipment is stale; it changed since it was loaded; refresh before editing"
                )
            conn.execute(
                "INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, ?, ?, ?, ?)",
                actor.username,
                "shipment.status_changed",
                "shipment",
                shipment_id,
                f'{{"from":"{old_status}","to":"{new_status}"}}',
            )
            conn.commit()
        rows, _ = self.list_shipments({"shipment_id": shipment_id}, 1, 1)
        if rows:
            return rows[0]
        raise DomainError("Shipment disappeared after update")

    def _purchase(self, request_id: str) -> PurchaseRequest:
        rows = self.repository.query(
            """SELECT r.request_id, r.requester, f.facility_name, r.status, r.comment, r.version_no, r.created_utc, p.product_name, l.quantity, l.unit_cost
            FROM dbo.purchase_requests r JOIN dbo.facilities f ON f.facility_id = r.facility_id
            LEFT JOIN dbo.purchase_request_lines l ON l.request_id = r.request_id
            LEFT JOIN dbo.products p ON p.product_id = l.product_id WHERE r.request_id = ? ORDER BY l.request_line_id""",
            (request_id,),
        )
        if not rows:
            raise DomainError("Purchase request not found")
        first = rows[0]
        lines = [
            PurchaseLine(row["product_name"], Decimal(row["quantity"]), Decimal(row["unit_cost"]))
            for row in rows
            if row["product_name"]
        ]
        return PurchaseRequest(
            first["request_id"],
            first["requester"],
            first["facility_name"],
            first["status"],
            first["created_utc"].replace(tzinfo=timezone.utc),
            first["comment"],
            lines,
            first["version_no"],
        )

    def list_purchases(self, actor: User | None) -> list[PurchaseRequest]:
        if not actor:
            return []
        if actor.roles.intersection({"approver", "admin"}):
            ids = self.repository.query(
                "SELECT request_id FROM dbo.purchase_requests ORDER BY created_utc DESC"
            )
        else:
            ids = self.repository.query(
                "SELECT request_id FROM dbo.purchase_requests WHERE requester = ? ORDER BY created_utc DESC",
                (actor.username,),
            )
        return [self._purchase(row["request_id"]) for row in ids]

    def purchase_history(self, actor: User | None) -> list[AuditEvent]:
        if not actor:
            return []
        query = "SELECT CONVERT(varchar(32), a.audit_event_id) AS event_id, a.actor, a.action_name, a.entity_type, a.entity_id, a.detail_json, a.occurred_utc FROM dbo.audit_events a JOIN dbo.purchase_requests r ON r.request_id = a.entity_id WHERE a.entity_type = 'purchase_request'"
        params = ()
        if not actor.roles.intersection({"approver", "admin"}):
            query += " AND r.requester = ?"
            params = (actor.username,)
        query += " ORDER BY a.occurred_utc"
        rows = self.repository.query(query, params)
        return [
            AuditEvent(
                row["event_id"],
                row["actor"],
                row["action_name"],
                row["entity_type"],
                row["entity_id"],
                {"raw": row["detail_json"]},
                row["occurred_utc"].replace(tzinfo=timezone.utc),
            )
            for row in rows
        ]

    def create_purchase(self, requester: User, facility: str, lines: list[dict]) -> PurchaseRequest:
        if not requester:
            raise PermissionError("Authenticated user required")
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
            facility_row = self.repository.rows(
                conn.execute(
                    "SELECT facility_id FROM dbo.facilities WHERE facility_name = ?", facility
                )
            )
            if not facility_row:
                raise DomainError("Facility not found")
            conn.execute(
                "INSERT dbo.purchase_requests(request_id, requester, facility_id, status) VALUES (?, ?, ?, 'Draft')",
                request_id,
                requester.username,
                facility_row[0]["facility_id"],
            )
            for product, qty, cost in parsed:
                product_row = self.repository.rows(
                    conn.execute(
                        "SELECT product_id FROM dbo.products WHERE product_name = ?", product
                    )
                )
                if not product_row:
                    raise DomainError(f"Product not found: {product}")
                conn.execute(
                    "INSERT dbo.purchase_request_lines(request_id, product_id, quantity, unit_cost) VALUES (?, ?, ?, ?)",
                    request_id,
                    product_row[0]["product_id"],
                    qty,
                    cost,
                )
            conn.execute(
                "INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, 'purchase.created', 'purchase_request', ?, ?)",
                requester.username,
                request_id,
                "{}",
            )
            conn.commit()
        return self._purchase(request_id)

    def submit_purchase(
        self, request_id: str, actor: User, expected_version: int
    ) -> PurchaseRequest:
        if not actor:
            raise PermissionError("Authenticated user required")
        request = self._purchase(request_id)
        if request.requester != actor.username and "admin" not in actor.roles:
            raise PermissionError("Only the requester or an admin can submit")
        if request.status != "Draft" or request.version != expected_version:
            raise DomainError("Purchase request changed; refresh before submitting")
        self._update_purchase(
            request_id, "Pending", "", actor, expected_version, "purchase.submitted"
        )
        return self._purchase(request_id)

    def decide_purchase(
        self, request_id: str, actor: User, decision: str, comment: str, expected_version: int
    ) -> PurchaseRequest:
        if not actor:
            raise PermissionError("Authenticated user required")
        request = self._purchase(request_id)
        if request.requester == actor.username:
            raise PermissionError("Self-approval is not permitted")
        if "approver" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Approver role required")
        if (
            decision not in {"Approved", "Rejected"}
            or request.status != "Pending"
            or request.version != expected_version
        ):
            raise DomainError("Request is stale or not pending")
        self._update_purchase(
            request_id,
            decision,
            comment[:500],
            actor,
            expected_version,
            f"purchase.{decision.lower()}",
        )
        return self._purchase(request_id)

    def _update_purchase(
        self, request_id: str, status: str, comment: str, actor: User, version: int, action: str
    ) -> None:
        with self.repository.connect() as conn:
            cursor = conn.execute(
                "UPDATE dbo.purchase_requests SET status = ?, comment = ?, version_no = version_no + 1, updated_utc = SYSUTCDATETIME() WHERE request_id = ? AND version_no = ?",
                status,
                comment,
                request_id,
                version,
            )
            if cursor.rowcount != 1:
                raise DomainError("Request is stale or not pending")
            conn.execute(
                "INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, ?, 'purchase_request', ?, ?)",
                actor.username,
                action,
                request_id,
                "{}",
            )
            conn.commit()

    def import_shipments(self, text: str, actor: User) -> dict:
        if not actor or ("operator" not in actor.roles and "admin" not in actor.roles):
            raise PermissionError("Operator role required")
        reader = csv.DictReader(io.StringIO(text))
        staged, seen = [], set()
        for line_no, row in enumerate(reader, 2):
            shipment_id = (row.get("shipment_id") or "").strip()
            references = {
                field: (row.get(field) or "").strip()
                for field in ("customer", "product", "facility", "carrier")
            }
            dock = (row.get("dock") or "D-01").strip()
            status = (row.get("status") or "Scheduled").strip()
            validation_error = None
            qty = shipped = freight = planned = None
            try:
                qty, shipped = Decimal(row["ordered_qty"]), Decimal(row["shipped_qty"])
                planned = datetime.fromisoformat(
                    row["planned_departure_utc"].replace("Z", "+00:00")
                )
                freight = Decimal(row.get("freight_cost", "0"))
            except (KeyError, InvalidOperation, TypeError, ValueError):
                validation_error = "invalid shipment record"
            if not shipment_id:
                validation_error = validation_error or "missing shipment_id"
            elif shipment_id in seen:
                validation_error = validation_error or "duplicate shipment_id"
            else:
                seen.add(shipment_id)
            if validation_error is None and (
                not all(references.values())
                or planned is None
                or planned.tzinfo is None
                or qty is None
                or shipped is None
                or freight is None
                or not qty.is_finite()
                or not shipped.is_finite()
                or not freight.is_finite()
                or qty <= 0
                or shipped < 0
                or shipped > qty
                or freight < 0
                or status not in STATUSES
            ):
                validation_error = "invalid shipment record"
            staged.append(
                (
                    line_no,
                    shipment_id or None,
                    references["customer"] or None,
                    references["product"] or None,
                    references["facility"] or None,
                    references["carrier"] or None,
                    dock or None,
                    planned.astimezone(timezone.utc).replace(tzinfo=None)
                    if planned and planned.tzinfo
                    else None,
                    qty,
                    shipped,
                    freight,
                    status or None,
                    validation_error,
                )
            )
        with self.repository.connect() as conn:
            run_row = self.repository.rows(
                conn.execute(
                    "INSERT dbo.import_runs(source_name, status) OUTPUT INSERTED.import_run_id VALUES ('shipment-update.csv', 'Started')"
                )
            )[0]
            import_run_id = run_row["import_run_id"]
            for row in staged:
                conn.execute(
                    """INSERT staging.shipment_updates(
                        import_run_id, source_row_no, shipment_id, customer_name, product_name,
                        facility_name, carrier_name, dock_code, planned_departure_utc,
                        ordered_qty, shipped_qty, freight_cost, status, validation_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    import_run_id,
                    *row,
                )
            conn.execute("EXEC dbo.usp_apply_shipment_import ?", import_run_id)
            import_summary = self.repository.rows(
                conn.execute(
                    "SELECT applied_count, rejected_count FROM dbo.import_runs WHERE import_run_id = ?",
                    import_run_id,
                )
            )[0]
            errors = [
                {"line": row["source_row_no"], "error": row["error_message"]}
                for row in self.repository.rows(
                    conn.execute(
                        "SELECT source_row_no, error_message FROM dbo.import_errors WHERE import_run_id = ? ORDER BY import_error_id",
                        import_run_id,
                    )
                )
            ]
            applied = int(import_summary["applied_count"])
            run_id = f"IMP-{import_run_id:04d}"
            conn.execute(
                "INSERT dbo.audit_events(actor, action_name, entity_type, entity_id, detail_json) VALUES (?, 'shipment.import', 'import_run', ?, ?)",
                actor.username,
                run_id,
                json.dumps({"applied": applied, "errors": len(errors)}),
            )
            conn.commit()
        return {
            "run_id": run_id,
            "actor": actor.username,
            "applied": applied,
            "errors": errors,
            "occurred_utc": utc_now().isoformat(),
        }
