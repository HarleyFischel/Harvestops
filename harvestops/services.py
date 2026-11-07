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
            "demo.admin": User(
                "demo.admin", "Demo Admin", {"viewer", "operator", "approver", "admin"}
            ),
        }
        self.shipments = self._seed_shipments()
        self.production_runs = self._seed_production_runs()
        self.labor_records = self._seed_labor_records(self.production_runs)
        self.audit: list[AuditEvent] = []
        self.import_runs: list[dict] = []
        self.purchases: dict[str, PurchaseRequest] = {}
        self._seed_purchases()

    @staticmethod
    def _seed_shipments() -> dict[str, Shipment]:
        base = datetime(2026, 1, 5, 13, tzinfo=timezone.utc)
        rows = [
            (
                "SHP-1001",
                "FreshMart Northeast",
                "Romaine Hearts",
                "Salinas",
                "GreenLine",
                "D-01",
                1200,
                1200,
                1820,
                "Delivered",
                0,
            ),
            (
                "SHP-1002",
                "Harvest Grocers",
                "Baby Spinach",
                "Yuma",
                "Westway",
                "D-04",
                900,
                780,
                1440,
                "Exception",
                3,
            ),
            (
                "SHP-1003",
                "City Market",
                "Spring Mix",
                "Salinas",
                "GreenLine",
                "D-02",
                1500,
                1500,
                2100,
                "In Transit",
                7,
            ),
            (
                "SHP-1004",
                "FreshMart Northeast",
                "Iceberg Lettuce",
                "Oxnard",
                "NorthStar",
                "D-03",
                1100,
                1100,
                1750,
                "Scheduled",
                10,
            ),
            (
                "SHP-1005",
                "Harvest Grocers",
                "Romaine Hearts",
                "Salinas",
                "Westway",
                "D-05",
                800,
                800,
                1290,
                "Delivered",
                35,
            ),
            (
                "SHP-1006",
                "City Market",
                "Baby Spinach",
                "Yuma",
                "NorthStar",
                "D-01",
                1000,
                920,
                1605,
                "Exception",
                38,
            ),
            (
                "SHP-1007",
                "FreshMart Northeast",
                "Spring Mix",
                "Oxnard",
                "GreenLine",
                "D-02",
                1300,
                1300,
                1980,
                "Delivered",
                42,
            ),
            (
                "SHP-1008",
                "Harvest Grocers",
                "Iceberg Lettuce",
                "Salinas",
                "Westway",
                "D-06",
                700,
                700,
                1180,
                "Cancelled",
                56,
            ),
        ]
        result = {}
        for (
            sid,
            customer,
            product,
            facility,
            carrier,
            dock,
            ordered,
            shipped,
            freight,
            status,
            days,
        ) in rows:
            planned = base + timedelta(days=days, hours=2)
            actual = (
                None
                if status in {"Scheduled", "Cancelled"}
                else planned + timedelta(hours=2 if "1002" in sid or "1006" in sid else -1)
            )
            result[sid] = Shipment(
                sid,
                customer,
                product,
                facility,
                carrier,
                dock,
                planned - timedelta(hours=2),
                planned,
                actual,
                Decimal(ordered),
                Decimal(shipped),
                Decimal(freight),
                status,
            )
        return result

    @staticmethod
    def _seed_production_runs() -> list[dict]:
        facilities = ("Salinas", "Yuma", "Oxnard")
        products = ("Romaine Hearts", "Baby Spinach", "Spring Mix", "Iceberg Lettuce")
        months = (1, 2, 3)
        return [
            {
                "facility": facility,
                "product": product,
                "run_date": datetime(2026, month, 15, tzinfo=timezone.utc),
                "output_qty": Decimal(1700 + facility_index * 90 + product_index * 35 + month * 20),
                "labor_hours": Decimal("42.50") + Decimal(facility_index * 2),
            }
            for facility_index, facility in enumerate(facilities)
            for product_index, product in enumerate(products)
            for month in months
        ]

    @staticmethod
    def _seed_labor_records(production_runs: list[dict]) -> list[dict]:
        return [
            {
                "facility": run["facility"],
                "product": run["product"],
                "work_date": run["run_date"],
                "labor_group": "Packing crew",
                "labor_hours": run["labor_hours"],
            }
            for run in production_runs
        ]

    def _seed_purchases(self) -> None:
        seeded_at = datetime(2026, 3, 3, 15, tzinfo=timezone.utc)
        rejected = PurchaseRequest(
            "PR-1001",
            "demo.operator",
            "Salinas",
            "Rejected",
            seeded_at,
            "Synthetic seed: price exceeded budget",
            [PurchaseLine("Romaine Hearts", Decimal("40"), Decimal("2.3500"))],
            2,
        )
        pending = PurchaseRequest(
            "PR-1002",
            "demo.operator",
            "Yuma",
            "Pending",
            seeded_at,
            "",
            [PurchaseLine("Baby Spinach", Decimal("80"), Decimal("1.8500"))],
            2,
        )
        self.purchases.update({rejected.request_id: rejected, pending.request_id: pending})
        self.audit.extend(
            [
                AuditEvent(
                    "seed-purchase-created",
                    "demo.operator",
                    "purchase.created",
                    "purchase_request",
                    rejected.request_id,
                    {"total": str(rejected.total)},
                    seeded_at,
                ),
                AuditEvent(
                    "seed-purchase-rejected",
                    "demo.approver",
                    "purchase.rejected",
                    "purchase_request",
                    rejected.request_id,
                    {"comment": rejected.comment},
                    seeded_at,
                ),
                AuditEvent(
                    "seed-purchase-pending",
                    "demo.operator",
                    "purchase.submitted",
                    "purchase_request",
                    pending.request_id,
                    {},
                    seeded_at,
                ),
            ]
        )

    def list_shipments(
        self, filters: dict, page: int = 1, page_size: int = 25
    ) -> tuple[list[Shipment], int]:
        rows = list(self.shipments.values())
        for field in ("customer", "product", "facility"):
            value = filters.get(field)
            if value and value != "All":
                rows = [r for r in rows if getattr(r, field) == value]
        if filters.get("exceptions_only"):
            rows = [r for r in rows if r.status == "Exception"]
        start_date = self._filter_date(filters.get("start_date"))
        end_date = self._filter_date(filters.get("end_date"))
        if start_date:
            rows = [r for r in rows if r.planned_departure_utc.date() >= start_date]
        if end_date:
            rows = [r for r in rows if r.planned_departure_utc.date() <= end_date]
        rows.sort(key=lambda x: x.planned_departure_utc)
        total = len(rows)
        start = max(0, (page - 1) * page_size)
        return rows[start : start + page_size], total

    def filter_options(self) -> dict[str, list[str]]:
        return {
            field: sorted({getattr(row, field) for row in self.shipments.values()})
            for field in ("customer", "product", "facility")
        }

    def get_shipment(self, shipment_id: str) -> Shipment | None:
        return self.shipments.get(shipment_id)

    def export_shipments(self) -> list[dict]:
        return [
            {
                "shipment_id": row.shipment_id,
                "customer": row.customer,
                "product": row.product,
                "status": row.status,
                "freight_cost": row.freight_cost,
            }
            for row in self.shipments.values()
        ]

    def import_freshness(self) -> dict:
        if not self.import_runs:
            return {
                "source": "synthetic seed",
                "status": "Seeded",
                "occurred_utc": "2026-03-03T15:00:00+00:00",
                "applied": 0,
                "errors": 0,
            }
        run = self.import_runs[-1]
        return {
            "source": "shipment-update.csv",
            "status": "Completed",
            "occurred_utc": run["occurred_utc"],
            "applied": run["applied"],
            "errors": len(run["errors"]),
        }

    def import_history(self, limit: int = 5) -> list[dict]:
        return list(reversed(self.import_runs))[: max(1, min(limit, 20))]

    def list_purchases(self, actor: User | None) -> list[PurchaseRequest]:
        if not actor:
            return []
        if actor.roles.intersection({"approver", "admin"}):
            return list(self.purchases.values())
        return [
            request for request in self.purchases.values() if request.requester == actor.username
        ]

    def purchase_history(self, actor: User | None) -> list[AuditEvent]:
        visible = {request.request_id for request in self.list_purchases(actor)}
        return [
            event
            for event in self.audit
            if event.entity_type == "purchase_request" and event.entity_id in visible
        ]

    def get_purchase(self, request_id: str, actor: User | None) -> PurchaseRequest | None:
        if not actor:
            return None
        return next(
            (request for request in self.list_purchases(actor) if request.request_id == request_id),
            None,
        )

    def shipment_audit_history(self, shipment_id: str) -> list[AuditEvent]:
        return [
            event
            for event in self.audit
            if event.entity_type == "shipment" and event.entity_id == shipment_id
        ]

    def kpis(self, filters: dict) -> dict:
        rows, _ = self.list_shipments(filters, 1, 10_000)
        total_ordered = sum((r.ordered_qty for r in rows), Decimal(0))
        total_shipped = sum((r.shipped_qty for r in rows), Decimal(0))
        closed = [r for r in rows if r.actual_departure_utc and r.status != "Cancelled"]
        on_time = sum(1 for r in closed if r.on_time)
        keys = {(row.facility, row.product) for row in rows}
        start_date = self._filter_date(filters.get("start_date"))
        end_date = self._filter_date(filters.get("end_date"))
        production = [
            run
            for run in self.production_runs
            if (run["facility"], run["product"]) in keys
            and (not start_date or run["run_date"].date() >= start_date)
            and (not end_date or run["run_date"].date() <= end_date)
        ]
        production_output = sum((run["output_qty"] for run in production), Decimal(0))
        labor_hours = sum(
            (
                record["labor_hours"]
                for record in self.labor_records
                if (record["facility"], record["product"]) in keys
                and (not start_date or record["work_date"].date() >= start_date)
                and (not end_date or record["work_date"].date() <= end_date)
            ),
            Decimal(0),
        )
        return {
            "shipment_volume": len(rows),
            "on_time_rate": (on_time / len(closed) * 100) if closed else 0,
            "fill_rate": (float(total_shipped / total_ordered) * 100) if total_ordered else 0,
            "freight_cost": float(sum((r.freight_cost for r in rows), Decimal(0))),
            "production_output": int(production_output),
            "labor_productivity": round(float(production_output / labor_hours), 1)
            if labor_hours
            else 0,
        }

    def dashboard_volume(self, filters: dict) -> list[dict]:
        rows, _ = self.list_shipments(filters, 1, 10_000)
        totals: dict[str, Decimal] = {}
        for row in rows:
            totals[row.facility] = totals.get(row.facility, Decimal("0")) + row.shipped_qty
        return [
            {"label": facility, "shipped_qty": float(totals[facility])}
            for facility in sorted(totals)
        ]

    def dashboard_service(self, filters: dict) -> dict[str, int]:
        rows, _ = self.list_shipments(filters, 1, 10_000)
        open_scheduled = sum(
            1 for row in rows if row.status == "Scheduled" and row.actual_departure_utc is None
        )
        departed_on_time = sum(
            1
            for row in rows
            if row.actual_departure_utc is not None and row.status != "Cancelled" and row.on_time
        )
        departed_late = sum(
            1
            for row in rows
            if row.actual_departure_utc is not None
            and row.status != "Cancelled"
            and not row.on_time
        )
        cancelled = sum(1 for row in rows if row.status == "Cancelled")
        return {
            "open_scheduled": open_scheduled,
            "departed_on_time": departed_on_time,
            "departed_late": departed_late,
            "cancelled": cancelled,
            "on_time_denominator": departed_on_time + departed_late,
        }

    def shipment_exceptions(self, filters: dict, limit: int = 50) -> list[Shipment]:
        rows, _ = self.list_shipments(filters, 1, 10_000)
        exceptions = [
            row
            for row in rows
            if row.status == "Exception"
            or (row.actual_departure_utc and not row.on_time)
            or row.fill_rate < 0.95
        ]
        return exceptions[: max(1, min(limit, 100))]

    @staticmethod
    def _filter_date(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
        except ValueError as exc:
            raise DomainError("Date filters must use YYYY-MM-DD") from exc

    def change_status(
        self, shipment_id: str, new_status: str, actor: User, expected_version: int
    ) -> Shipment:
        if not actor:
            raise PermissionError("Authenticated user required")
        if "operator" not in actor.roles and "admin" not in actor.roles:
            raise PermissionError("Operator role required")
        if new_status not in STATUSES:
            raise DomainError("Unknown shipment status")
        shipment = self.shipments.get(shipment_id)
        if not shipment:
            raise DomainError("Shipment not found")
        if shipment.version != expected_version:
            raise DomainError(
                "Shipment is stale; it changed since it was loaded; refresh before editing"
            )
        if new_status not in ALLOWED_TRANSITIONS[shipment.status]:
            raise DomainError(f"Cannot change {shipment.status} to {new_status}")
        old = shipment.status
        shipment.status = new_status
        shipment.version += 1
        self.audit.append(
            AuditEvent(
                secrets.token_hex(8),
                actor.username,
                "shipment.status_changed",
                "shipment",
                shipment_id,
                {"from": old, "to": new_status},
                utc_now(),
            )
        )
        return shipment

    def create_purchase(self, requester: User, facility: str, lines: list[dict]) -> PurchaseRequest:
        if not requester:
            raise PermissionError("Authenticated user required")
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
        request = PurchaseRequest(
            f"PR-{len(self.purchases) + 1001}",
            requester.username,
            facility,
            "Draft",
            utc_now(),
            lines=parsed,
        )
        self.purchases[request.request_id] = request
        self.audit.append(
            AuditEvent(
                secrets.token_hex(8),
                requester.username,
                "purchase.created",
                "purchase_request",
                request.request_id,
                {"total": str(request.total)},
                utc_now(),
            )
        )
        return request

    def submit_purchase(
        self, request_id: str, actor: User, expected_version: int
    ) -> PurchaseRequest:
        if not actor:
            raise PermissionError("Authenticated user required")
        request = self._purchase(request_id)
        if request.requester != actor.username and "admin" not in actor.roles:
            raise PermissionError("Only the requester or an admin can submit")
        if request.version != expected_version:
            raise DomainError("Purchase request changed; refresh before submitting")
        if request.status != "Draft":
            raise DomainError("Only draft requests can be submitted")
        request.status = "Pending"
        request.version += 1
        self.audit.append(
            AuditEvent(
                secrets.token_hex(8),
                actor.username,
                "purchase.submitted",
                "purchase_request",
                request_id,
                {},
                utc_now(),
            )
        )
        return request

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
        if request.status != "Pending" or request.version != expected_version:
            raise DomainError("Request is stale or not pending")
        if decision not in {"Approved", "Rejected"}:
            raise DomainError("Decision must be Approved or Rejected")
        request.status, request.comment, request.version = (
            decision,
            comment[:500],
            request.version + 1,
        )
        self.audit.append(
            AuditEvent(
                secrets.token_hex(8),
                actor.username,
                f"purchase.{decision.lower()}",
                "purchase_request",
                request_id,
                {"comment": request.comment},
                utc_now(),
            )
        )
        return request

    def _purchase(self, request_id: str) -> PurchaseRequest:
        if request_id not in self.purchases:
            raise DomainError("Purchase request not found")
        return self.purchases[request_id]

    def import_shipments(self, text: str, actor: User) -> dict:
        if not actor or ("operator" not in actor.roles and "admin" not in actor.roles):
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
                planned = datetime.fromisoformat(
                    row["planned_departure_utc"].replace("Z", "+00:00")
                )
                status = (row.get("status") or "Scheduled").strip()
                freight = Decimal(row.get("freight_cost", "0"))
                required = tuple(
                    (row.get(field) or "").strip()
                    for field in ("customer", "product", "facility", "carrier")
                )
                if (
                    not all(required)
                    or planned.tzinfo is None
                    or not qty.is_finite()
                    or not shipped.is_finite()
                    or not freight.is_finite()
                    or qty <= 0
                    or shipped < 0
                    or shipped > qty
                    or freight < 0
                    or status not in STATUSES
                ):
                    raise ValueError
            except (KeyError, InvalidOperation, ValueError):
                errors.append({"line": line_no, "error": "invalid shipment record"})
                continue
            planned = planned.astimezone(timezone.utc)
            dock = (row.get("dock") or "D-01").strip()
            self.shipments[sid] = Shipment(
                sid,
                required[0],
                required[1],
                required[2],
                required[3],
                dock,
                planned - timedelta(hours=2),
                planned,
                None,
                qty,
                shipped,
                freight,
                status,
            )
            applied += 1
        run = {
            "run_id": f"IMP-{len(self.import_runs)+1:04}",
            "actor": actor.username,
            "applied": applied,
            "errors": errors,
            "occurred_utc": utc_now().isoformat(),
        }
        self.import_runs.append(run)
        self.audit.append(
            AuditEvent(
                secrets.token_hex(8),
                actor.username,
                "shipment.import",
                "import_run",
                run["run_id"],
                run,
                utc_now(),
            )
        )
        return run
