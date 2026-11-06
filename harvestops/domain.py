from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass
class User:
    username: str
    display_name: str
    roles: set[str]


@dataclass
class Shipment:
    shipment_id: str
    customer: str
    product: str
    facility: str
    carrier: str
    dock: str
    appointment_utc: datetime
    planned_departure_utc: datetime
    actual_departure_utc: datetime | None
    ordered_qty: Decimal
    shipped_qty: Decimal
    freight_cost: Decimal
    status: str
    version: int = 1

    @property
    def fill_rate(self) -> float:
        return float(self.shipped_qty / self.ordered_qty) if self.ordered_qty else 0.0

    @property
    def on_time(self) -> bool:
        return (
            self.actual_departure_utc is not None
            and self.actual_departure_utc <= self.planned_departure_utc
        )


@dataclass
class PurchaseLine:
    product: str
    quantity: Decimal
    unit_cost: Decimal

    @property
    def total(self) -> Decimal:
        return (self.quantity * self.unit_cost).quantize(Decimal("0.01"))


@dataclass
class PurchaseRequest:
    request_id: str
    requester: str
    facility: str
    status: str
    created_utc: datetime
    comment: str = ""
    lines: list[PurchaseLine] = field(default_factory=list)
    version: int = 1

    @property
    def total(self) -> Decimal:
        return sum((line.total for line in self.lines), Decimal("0.00"))


@dataclass
class AuditEvent:
    event_id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    detail: dict[str, Any]
    occurred_utc: datetime
