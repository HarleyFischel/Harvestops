import csv
import io
import logging
import math
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash_ag_grid import AgGrid
from flask import Flask, has_request_context, jsonify, make_response, redirect, request, session

from .auth import EntraAuth
from .config import Settings, get_settings
from .domain import User
from .knowledge import KnowledgeService
from .logging_config import configure_logging
from .services import ALLOWED_TRANSITIONS, DomainError, InMemoryStore
from .sql_store import SqlServerStore
from .ui import empty_state, metric_card, page_heading, section_heading

SHIPMENT_PAGE_SIZE = 4

configure_logging()
log = logging.getLogger("harvestops")


def current_user(store: InMemoryStore):
    username = session.get("username")
    if not username:
        return None
    known_user = store.users.get(username)
    if known_user:
        return known_user
    # Reconstruct Entra principals from the server-side session so a request
    # routed to another worker does not depend on process-local state.
    roles = set(session.get("roles", []))
    if "viewer" not in roles:
        return None
    return User(username, session.get("display_name", username), roles)


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def valid_csrf(token: str | None, allow_cookie: bool = True) -> bool:
    expected = session.get("csrf_token")
    supplied = token or (request.cookies.get("harvestops_csrf") if allow_cookie else None)
    return bool(expected and supplied and secrets.compare_digest(supplied, expected))


def require_role(store: InMemoryStore, *roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = current_user(store)
            if not user or not user.roles.intersection(roles):
                return jsonify({"error": "forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapped

    return decorator


def build_layout(store: InMemoryStore, settings: Settings):
    demo_identity = settings.demo_mode and settings.identity_mode == "demo"
    return html.Div(
        [
            dcc.Location(id="url"),
            dcc.Store(id="active-user", data="demo.viewer"),
            dcc.Store(id="csrf-token", data=csrf_token() if has_request_context() else None),
            html.Div(
                id="csrf-status",
                className="visually-hidden",
                role="status",
                **{"data-csrf-token": ""},
            ),
            html.Header(
                [
                    html.Div(
                        [
                            html.Div("HARVESTOPS", className="brand"),
                            html.Div("Produce operations control plane", className="tagline"),
                        ],
                        className="brand-lockup",
                    ),
                    html.Div(
                        [
                            html.Span(
                                "SYNTHETIC DATA · DEMO MODE"
                                if demo_identity
                                else "SYNTHETIC DATA · ENTRA IDENTITY",
                                className="demo-pill",
                            ),
                            html.Span(id="user-label", className="user-label"),
                        ],
                        className="header-meta",
                    ),
                ],
                className="topbar",
            ),
            html.Main(
                [
                    html.Aside(
                        [
                            html.Div("WORKSPACE", className="eyebrow"),
                            html.Nav(
                                [
                                    html.Button(
                                        "Operations dashboard",
                                        id="nav-dashboard",
                                        className="nav-item active",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                    html.Button(
                                        "Dock & shipment board",
                                        id="nav-shipments",
                                        className="nav-item",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                    html.Button(
                                        "Purchasing approvals",
                                        id="nav-purchasing",
                                        className="nav-item",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                    html.Button(
                                        "Knowledge assistant",
                                        id="nav-knowledge",
                                        className="nav-item",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                ],
                                className="nav-list",
                                **{"aria-label": "Primary navigation"},
                            ),
                            html.Div("DEMO ACCOUNT", className="eyebrow side-space")
                            if demo_identity
                            else html.Div("IDENTITY", className="eyebrow side-space"),
                            dcc.Dropdown(
                                id="role-switch",
                                options=[
                                    {"label": u.display_name, "value": u.username}
                                    for u in store.users.values()
                                ],
                                value=session.get("username", "demo.viewer")
                                if has_request_context()
                                else "demo.viewer",
                                clearable=False,
                            )
                            if demo_identity
                            else html.Div(
                                [
                                    html.A(
                                        "Sign in with Microsoft Entra ID",
                                        href="/auth/login",
                                        className="button secondary",
                                    ),
                                    html.Form(
                                        [
                                            dcc.Input(
                                                type="hidden",
                                                name="csrf_token",
                                                value=csrf_token() if has_request_context() else "",
                                            ),
                                            html.Button(
                                                "Sign out",
                                                type="submit",
                                                className="button quiet",
                                            ),
                                        ],
                                        action="/auth/logout",
                                        method="post",
                                        className="signout-form",
                                    ),
                                ],
                                className="identity-actions",
                            ),
                            html.Div(
                                "Role changes are development-only and enforced server-side.",
                                className="side-note",
                            )
                            if demo_identity
                            else html.Div(
                                "Roles are mapped from Entra app-role claims.",
                                className="side-note",
                            ),
                        ],
                        className="sidebar",
                    ),
                    dcc.Loading(
                        id="page-loading",
                        type="dot",
                        color="#0f766e",
                        fullscreen=False,
                        children=html.Section(id="page-content", className="content"),
                    ),
                ],
                className="shell",
            ),
            html.Footer(
                "UTC storage · display timezone: "
                + settings.display_timezone
                + " · Portfolio application with synthetic data",
                className="footer",
            ),
        ],
        className="app-shell",
    )


def csv_safe(value) -> str:
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def freshness_text(metadata: dict) -> str:
    return f"Data freshness · {metadata['source']} · {metadata['status']} · {metadata['occurred_utc']} UTC · {metadata['applied']} applied · {metadata['errors']} rejected"


def import_report_children(history: list[dict]):
    if not history:
        return [empty_state("No shipment import runs have been recorded yet.")]
    runs = []
    for run in history:
        errors = run.get("errors", [])
        error_list = (
            html.Ul(
                [html.Li(f"Row {error['line']}: {error['error']}") for error in errors],
                className="import-errors",
            )
            if errors
            else html.Div("No rejected rows", className="section-subtitle")
        )
        runs.append(
            html.Div(
                [
                    html.Strong(f"{run['run_id']} · {run['source']}"),
                    html.Div(
                        f"{run['status']} · {run['occurred_utc']} UTC · {run['applied']} applied · {len(errors)} rejected",
                        className="section-subtitle",
                    ),
                    error_list,
                ],
                className="import-run",
            )
        )
    return [
        section_heading("Import history", "Validation runs and rejected records"),
        html.Div(runs, className="import-runs"),
    ]


def display_datetime(value: datetime | None, settings: Settings) -> str:
    """Format a UTC timestamp for people while preserving UTC in the data model."""
    if value is None:
        return "—"
    try:
        zone = ZoneInfo(settings.display_timezone)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    local = value.astimezone(zone)
    return local.strftime("%b %-d, %Y %I:%M %p %Z")


def display_date(value: datetime | None, settings: Settings) -> str:
    if value is None:
        return "—"
    try:
        zone = ZoneInfo(settings.display_timezone)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return value.astimezone(zone).strftime("%b %-d, %Y")


def grid_sort_comparator(sort_field: str, numeric: bool = False) -> dict:
    comparison = (
        f"Number(nodeA.data.{sort_field}) - Number(nodeB.data.{sort_field})"
        if numeric
        else f"String(nodeA.data.{sort_field}).localeCompare(String(nodeB.data.{sort_field}))"
    )
    return {"comparator": {"function": f"(_a, _b, nodeA, nodeB) => {comparison}"}}


def shipment_grid_rows(rows, settings: Settings | None = None):
    settings = settings or get_settings()
    return [
        {
            "shipment_id": row.shipment_id,
            "customer": row.customer,
            "product": row.product,
            "facility": row.facility,
            "carrier": row.carrier,
            "dock": row.dock,
            "dock_appointment": display_datetime(row.appointment_utc, settings),
            "dock_appointment_sort": row.appointment_utc.isoformat(),
            "planned_departure": display_datetime(row.planned_departure_utc, settings),
            "planned_departure_sort": row.planned_departure_utc.isoformat(),
            "actual_departure": display_datetime(row.actual_departure_utc, settings),
            "actual_departure_sort": row.actual_departure_utc.isoformat()
            if row.actual_departure_utc
            else "",
            "ordered_qty": f"{row.ordered_qty:,.2f}".rstrip("0").rstrip("."),
            "ordered_qty_sort": str(row.ordered_qty),
            "shipped_qty": f"{row.shipped_qty:,.2f}".rstrip("0").rstrip("."),
            "shipped_qty_sort": str(row.shipped_qty),
            "freight_cost": f"${row.freight_cost:,.2f}",
            "freight_cost_sort": str(row.freight_cost),
            "status": row.status,
            "version": row.version,
        }
        for row in rows
    ]


def operational_freshness(store) -> str:
    metadata = store.import_freshness()
    if metadata.get("status") == "Seeded":
        return "Data freshness · deterministic synthetic seed · no file import has run"
    return freshness_text(metadata)


def status_badge(status: str):
    safe_status = status.lower().replace(" ", "-")
    return html.Span(status, className=f"status-badge status-{safe_status}")


def shipment_detail_view(store, user, shipment_id: str | None, settings: Settings | None = None):
    settings = settings or get_settings()
    if not shipment_id:
        return empty_state(
            "Select one shipment to review its timing, audit history, and available actions."
        )
    shipment = store.get_shipment(shipment_id)
    if not shipment:
        return empty_state(
            "That shipment is no longer available. Refresh the board and select another record."
        )
    transitions = sorted(ALLOWED_TRANSITIONS.get(shipment.status, set()))
    audit = store.shipment_audit_history(shipment.shipment_id)
    fields = [
        ("Customer", shipment.customer),
        ("Product", shipment.product),
        ("Facility", shipment.facility),
        ("Carrier", shipment.carrier),
        ("Dock", shipment.dock),
        ("Appointment", display_datetime(shipment.appointment_utc, settings)),
        ("Planned departure", display_datetime(shipment.planned_departure_utc, settings)),
        (
            "Actual departure",
            display_datetime(shipment.actual_departure_utc, settings),
        ),
        ("Quantity", f"{shipment.shipped_qty} / {shipment.ordered_qty}"),
        ("Freight", f"${shipment.freight_cost:,.2f}"),
        ("Record version", str(shipment.version)),
    ]
    audit_items = [
        html.Li(
            f"{display_datetime(event.occurred_utc, settings)} · {event.actor} · {event.action}",
            className="audit-item",
        )
        for event in audit[:8]
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Selected shipment", className="page-kicker"),
                            html.H2(shipment.shipment_id),
                        ],
                        className="detail-title",
                    ),
                    status_badge(shipment.status),
                ],
                className="detail-header",
            ),
            html.Div(
                [
                    html.Div(
                        [html.Span(label, className="detail-label"), html.Span(value)],
                        className="detail-field",
                    )
                    for label, value in fields
                ],
                className="detail-grid",
            ),
            (
                html.Div(
                    [
                        html.Label("Next valid status", htmlFor="selected-status"),
                        dcc.Dropdown(
                            id="selected-status",
                            options=[{"label": value, "value": value} for value in transitions],
                            placeholder="No transition selected",
                            clearable=True,
                            disabled=not transitions,
                        ),
                        html.Button(
                            "Apply status",
                            id="apply-status",
                            className="button primary",
                            n_clicks=0,
                            disabled=not transitions,
                        ),
                        html.Button(
                            "Refresh selection",
                            id="refresh-selection",
                            className="button secondary",
                            n_clicks=0,
                        ),
                    ],
                    className="detail-actions",
                )
                if user and user.roles.intersection({"operator", "admin"})
                else html.Div(
                    "Status changes are restricted to operators and administrators.",
                    className="permission-note",
                    role="status",
                )
            ),
            html.Div(
                [
                    html.Div("Audit history", className="section-title"),
                    html.Ul(audit_items, className="audit-list")
                    if audit_items
                    else empty_state("No shipment audit events yet."),
                ],
                className="audit-panel",
            ),
        ],
        className="shipment-detail",
    )


def purchase_queue(store, user, status_filter="All", settings: Settings | None = None):
    settings = settings or get_settings()
    requests = store.list_purchases(user)
    if status_filter and status_filter != "All":
        requests = [request for request in requests if request.status == status_filter]
    if not requests:
        return empty_state("No purchase requests match this queue filter.")
    return [
        html.Button(
            [
                html.Span(request.request_id, className="queue-id"),
                html.Span(request.requester, className="queue-requester"),
                html.Span(request.facility, className="queue-facility"),
                html.Span(f"${request.total:,.2f}", className="queue-total"),
                status_badge(request.status),
                html.Span(display_date(request.created_utc, settings), className="queue-date"),
            ],
            id={"type": "purchase-select", "request_id": request.request_id},
            className="queue-row",
            n_clicks=0,
            type="button",
        )
        for request in requests
    ]


def purchase_detail_view(store, user, request_id: str | None, settings: Settings | None = None):
    settings = settings or get_settings()
    if not request_id:
        return empty_state("Select a request to review its lines, history, and available actions.")
    request = store.get_purchase(request_id, user)
    if not request:
        return empty_state("That request is not available to this account.")
    lines = html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Product"),
                        html.Th("Quantity"),
                        html.Th("Unit cost"),
                        html.Th("Line total"),
                    ]
                )
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(line.product),
                            html.Td(str(line.quantity)),
                            html.Td(f"${line.unit_cost:,.2f}"),
                            html.Td(f"${line.total:,.2f}"),
                        ]
                    )
                    for line in request.lines
                ]
            ),
        ],
        className="detail-table",
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Selected request", className="page-kicker"),
                            html.H2(request.request_id),
                        ],
                        className="detail-title",
                    ),
                    status_badge(request.status),
                ],
                className="detail-header",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Requester", className="detail-label"),
                            html.Span(request.requester),
                        ],
                        className="detail-field",
                    ),
                    html.Div(
                        [
                            html.Span("Facility", className="detail-label"),
                            html.Span(request.facility),
                        ],
                        className="detail-field",
                    ),
                    html.Div(
                        [
                            html.Span("Created", className="detail-label"),
                            html.Span(display_datetime(request.created_utc, settings)),
                        ],
                        className="detail-field",
                    ),
                    html.Div(
                        [
                            html.Span("Total", className="detail-label"),
                            html.Span(f"${request.total:,.2f}"),
                        ],
                        className="detail-field",
                    ),
                ],
                className="detail-grid purchase-summary",
            ),
            lines,
            html.P(request.comment or "No request comment.", className="detail-comment"),
        ],
        className="purchase-detail",
    )


def dashboard_view(store: InMemoryStore):
    options = store.filter_options()
    return html.Div(
        [
            page_heading(
                "Operations overview",
                "Run the day from one operational view.",
                "Volume, service, fill, freight, production, and labor signals in the selected scope.",
                operational_freshness(store),
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Planned departure range"),
                            dcc.DatePickerRange(
                                id="filter-dates",
                                start_date="2026-01-01",
                                end_date="2026-03-31",
                                display_format="YYYY-MM-DD",
                                minimum_nights=0,
                            ),
                        ],
                        className="filter-control date-filter",
                    ),
                    html.Div(
                        [
                            html.Label("Customer"),
                            dcc.Dropdown(
                                id="filter-customer",
                                options=[{"label": "All customers", "value": "All"}]
                                + [{"label": x, "value": x} for x in options["customer"]],
                                value="All",
                            ),
                        ],
                        className="filter-control",
                    ),
                    html.Div(
                        [
                            html.Label("Product"),
                            dcc.Dropdown(
                                id="filter-product",
                                options=[{"label": "All products", "value": "All"}]
                                + [{"label": x, "value": x} for x in options["product"]],
                                value="All",
                            ),
                        ],
                        className="filter-control",
                    ),
                    html.Div(
                        [
                            html.Label("Facility"),
                            dcc.Dropdown(
                                id="filter-facility",
                                options=[{"label": "All facilities", "value": "All"}]
                                + [{"label": x, "value": x} for x in options["facility"]],
                                value="All",
                            ),
                        ],
                        className="filter-control",
                    ),
                ],
                className="filter-row",
            ),
            html.Div(id="kpi-row", className="metric-grid"),
            html.Div(
                [
                    dcc.Graph(id="volume-chart", config={"displayModeBar": False}),
                    dcc.Graph(id="service-chart", config={"displayModeBar": False}),
                ],
                className="chart-grid",
            ),
            html.Div(
                [
                    section_heading(
                        "Shipment exceptions",
                        "Late departures or partial fills require an operator decision.",
                    ),
                    html.Div(id="exceptions-table"),
                ],
                className="panel",
            ),
        ]
    )


def shipments_view(
    store: InMemoryStore,
    requested_shipment: str | None = None,
    settings: Settings | None = None,
):
    settings = settings or get_settings()
    options = store.filter_options()
    requested_page = (
        store.shipment_page_for_id(requested_shipment, SHIPMENT_PAGE_SIZE)
        if requested_shipment
        else 1
    ) or 1
    initial_rows, initial_total = store.list_shipments({}, requested_page, SHIPMENT_PAGE_SIZE)
    initial_selected_id = (
        requested_shipment
        if requested_shipment and store.get_shipment(requested_shipment)
        else None
    )
    initial_selected_rows = [
        row for row in shipment_grid_rows(initial_rows) if row["shipment_id"] == initial_selected_id
    ]
    max_page = max(1, math.ceil(initial_total / SHIPMENT_PAGE_SIZE))
    user = current_user(store)
    can_manage_shipments = bool(user and user.roles.intersection({"operator", "admin"}))
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Execution board", className="page-kicker"),
                            html.H1("Dock & shipment board"),
                            html.P(
                                "Select a load to review timing, audit history, and valid next actions."
                            ),
                        ]
                    ),
                    (
                        html.A(
                            "Export CSV",
                            href="/api/shipments/export",
                            id="export-csv",
                            className="button secondary",
                        )
                        if can_manage_shipments
                        else html.Span(
                            "Export restricted to operators and administrators.",
                            className="permission-note",
                            role="status",
                        )
                    ),
                ],
                className="page-heading",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Customer"),
                            dcc.Dropdown(
                                id="ship-customer",
                                options=[{"label": "All", "value": "All"}]
                                + [{"label": x, "value": x} for x in options["customer"]],
                                value="All",
                            ),
                        ],
                        className="filter-control",
                    ),
                    html.Div(
                        [
                            html.Label("Product"),
                            dcc.Dropdown(
                                id="ship-product",
                                options=[{"label": "All", "value": "All"}]
                                + [{"label": x, "value": x} for x in options["product"]],
                                value="All",
                            ),
                        ],
                        className="filter-control",
                    ),
                    html.Div(
                        [
                            html.Label("Facility"),
                            dcc.Dropdown(
                                id="ship-facility",
                                options=[{"label": "All", "value": "All"}]
                                + [{"label": x, "value": x} for x in options["facility"]],
                                value="All",
                            ),
                        ],
                        className="filter-control",
                    ),
                    html.Div(
                        [
                            html.Label("Exceptions only"),
                            dcc.Checklist(
                                id="ship-exceptions",
                                options=[{"label": " Show exceptions", "value": "yes"}],
                                className="check-control",
                            ),
                        ],
                        className="filter-control",
                    ),
                ],
                className="filter-row",
            ),
            html.Div(
                f"Times shown in {settings.display_timezone}; timestamps are stored in UTC.",
                className="timezone-note",
            ),
            html.Div(id="shipment-alert", className="alert"),
            dcc.ConfirmDialog(id="confirm-status", message="Apply this shipment status change?"),
            AgGrid(
                id="shipment-grid",
                columnDefs=[
                    {"field": "shipment_id", "headerName": "Shipment", "width": 130},
                    {"field": "customer", "headerName": "Customer", "width": 190},
                    {"field": "product", "headerName": "Product", "width": 170},
                    {"field": "status", "headerName": "Status", "width": 130},
                    {
                        "field": "planned_departure",
                        "headerName": "Planned departure",
                        "width": 190,
                        **grid_sort_comparator("planned_departure_sort"),
                    },
                    {
                        "field": "actual_departure",
                        "headerName": "Actual departure",
                        "width": 190,
                        **grid_sort_comparator("actual_departure_sort"),
                    },
                    {"field": "facility", "headerName": "Facility", "width": 130},
                    {"field": "carrier", "headerName": "Carrier", "width": 140},
                    {"field": "dock", "headerName": "Dock", "width": 90},
                    {"field": "dock_appointment", "headerName": "Appointment", "width": 190},
                    {
                        "field": "ordered_qty",
                        "headerName": "Ordered",
                        "width": 110,
                        "type": "rightAligned",
                        **grid_sort_comparator("ordered_qty_sort", numeric=True),
                    },
                    {
                        "field": "shipped_qty",
                        "headerName": "Shipped",
                        "width": 110,
                        "type": "rightAligned",
                        **grid_sort_comparator("shipped_qty_sort", numeric=True),
                    },
                    {
                        "field": "freight_cost",
                        "headerName": "Freight",
                        "width": 110,
                        "type": "rightAligned",
                        **grid_sort_comparator("freight_cost_sort", numeric=True),
                    },
                ],
                rowData=shipment_grid_rows(initial_rows),
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                dashGridOptions={
                    "animateRows": False,
                    "pagination": False,
                    "rowSelection": {"mode": "singleRow", "enableClickSelection": True},
                },
                selectedRows=initial_selected_rows,
                className="ag-theme-alpine",
                style={"height": "430px", "width": "100%"},
            ),
            html.Div(
                f"Page {requested_page} of {max_page} · {initial_total} matching shipments",
                id="shipment-page-info",
                className="section-subtitle",
            ),
            html.Div(
                "That shipment is no longer available. Refresh the board and select another record.",
                id="shipment-link-status",
                className="permission-note",
                role="status",
            )
            if requested_shipment and not initial_selected_id
            else html.Div(id="shipment-link-status", className="visually-hidden"),
            dcc.Store(id="ship-page", data=requested_page),
            html.Div(
                [
                    html.Button(
                        "Previous page",
                        id="ship-prev",
                        className="button secondary",
                        disabled=requested_page <= 1,
                    ),
                    html.Span(
                        f"Page {requested_page} of {max_page}",
                        id="ship-pagination-label",
                        role="status",
                    ),
                    html.Button(
                        "Next page",
                        id="ship-next",
                        className="button secondary",
                        disabled=requested_page >= max_page,
                    ),
                ],
                id="ship-pagination",
                className="pagination-control",
                **{"aria-label": "Shipment board pages"},
            ),
            dcc.Store(id="selected-shipment-id", data=initial_selected_id),
            dcc.Store(
                id="selected-shipment-version",
                data=initial_selected_rows[0]["version"] if initial_selected_rows else None,
            ),
            dcc.Store(id="shipment-refresh", data=0),
            html.Div(
                shipment_detail_view(store, user, requested_shipment, settings),
                id="shipment-detail",
                className="panel",
            ),
            html.Details(
                [
                    html.Summary("Import shipment updates", className="details-summary"),
                    html.Div(
                        [
                            html.P(
                                "Validate before applying. Duplicate shipment IDs are ignored and rejected rows remain in import history."
                            ),
                            dcc.Upload(
                                id="shipment-import-upload",
                                children=html.Div("Upload shipment CSV"),
                                className="upload-control",
                                multiple=False,
                            ),
                            html.Div(
                                operational_freshness(store),
                                id="import-freshness",
                                className="freshness-note",
                                role="status",
                            ),
                            html.Div(
                                import_report_children(store.import_history()),
                                id="import-report",
                                className="import-report",
                            ),
                        ],
                        className="import-panel",
                    ),
                ],
                className="panel import-details",
            )
            if can_manage_shipments
            else html.Div(
                "Shipment import is restricted to operators and administrators.",
                className="panel permission-note",
                role="status",
            ),
            html.Div(
                [
                    section_heading(
                        "Shipment lookup",
                        "Use lookup when you have an ID; the selected board row remains the primary workflow.",
                    ),
                    html.Div(
                        [
                            html.Label("Shipment ID", htmlFor="shipment-lookup-id"),
                            dcc.Input(id="shipment-lookup-id", placeholder="SHP-1001"),
                            html.Button(
                                "Find shipment",
                                id="shipment-lookup-submit",
                                className="button secondary",
                            ),
                        ],
                        className="inline-form",
                    ),
                    html.Div(id="shipment-lookup-result", role="status"),
                ],
                className="panel lookup-panel",
            ),
        ]
    )


def purchase_cards(store, user, settings: Settings | None = None):
    return purchase_queue(store, user, settings=settings)


def purchase_history_view(store, user, settings: Settings | None = None):
    settings = settings or get_settings()
    events = [
        html.Div(
            f"{display_datetime(event.occurred_utc, settings)} · {event.actor} · {event.action} · {event.entity_id}",
            className="section-subtitle",
        )
        for event in store.purchase_history(user)
    ]
    return events or [empty_state("No approval history is available.")]


def purchasing_view(store, settings: Settings | None = None):
    settings = settings or get_settings()
    user = current_user(store)
    return html.Div(
        [
            page_heading(
                "Controls & approvals",
                "Purchasing approvals",
                "Work from a queue, then review the complete request before acting.",
            ),
            html.Div(id="purchase-alert", className="alert"),
            html.Div(
                [
                    section_heading(
                        "New purchase request",
                        "Create a draft request with one or more supported line items.",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Facility"),
                                    dcc.Input(id="purchase-facility", value="Salinas"),
                                ],
                                className="filter-control",
                            ),
                            html.Div(
                                [
                                    html.Label("Product"),
                                    dcc.Input(id="purchase-product", value="Romaine Hearts"),
                                ],
                                className="filter-control",
                            ),
                            html.Div(
                                [
                                    html.Label("Quantity"),
                                    dcc.Input(
                                        id="purchase-qty", type="number", value=100, min=0.01
                                    ),
                                ],
                                className="filter-control",
                            ),
                            html.Div(
                                [
                                    html.Label("Unit cost"),
                                    dcc.Input(
                                        id="purchase-cost", type="number", value=2.5, min=0.01
                                    ),
                                ],
                                className="filter-control",
                            ),
                            html.Button(
                                "Create request",
                                id="create-purchase",
                                className="button primary",
                                n_clicks=0,
                                type="button",
                            ),
                        ],
                        className="inline-form",
                    ),
                ],
                className="panel create-request-panel",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            section_heading(
                                "Request queue",
                                "Select a row to review details. Your role controls available actions.",
                            ),
                            dcc.Dropdown(
                                id="purchase-status-filter",
                                options=[{"label": "All statuses", "value": "All"}]
                                + [
                                    {"label": value, "value": value}
                                    for value in ["Draft", "Pending", "Approved", "Rejected"]
                                ],
                                value="All",
                                clearable=False,
                            ),
                        ],
                        className="queue-header",
                    ),
                    html.Div(
                        id="purchase-list",
                        children=purchase_queue(store, user, settings=settings),
                        className="purchase-list",
                    ),
                ],
                className="panel",
            ),
            dcc.Store(id="selected-purchase-id", data=None),
            dcc.Store(id="purchase-refresh", data=0),
            html.Div(
                id="purchase-detail",
                children=purchase_detail_view(store, user, None, settings),
                className="panel",
            ),
            html.Div(
                [
                    html.Button(
                        "Submit for approval",
                        id="submit-selected-purchase",
                        className="button secondary",
                        n_clicks=0,
                        disabled=True,
                    ),
                    dcc.Dropdown(
                        id="selected-decision",
                        options=[
                            {"label": value, "value": value} for value in ["Approved", "Rejected"]
                        ],
                        placeholder="Decision",
                        clearable=True,
                        disabled=True,
                    ),
                    dcc.Textarea(
                        id="purchase-decision-comment",
                        placeholder="Decision comment",
                        disabled=True,
                    ),
                    html.Button(
                        "Record decision",
                        id="record-selected-decision",
                        className="button primary",
                        n_clicks=0,
                        disabled=True,
                    ),
                ],
                className="panel detail-actions purchase-actions",
            ),
            html.Div(
                [
                    section_heading(
                        "Approval history", "Recent audit events visible to this account."
                    ),
                    html.Div(
                        id="purchase-history",
                        children=purchase_history_view(store, user, settings),
                        className="purchase-history",
                    ),
                ],
                className="panel",
            ),
        ]
    )


def knowledge_view():
    return html.Div(
        [
            page_heading(
                "Operating memory",
                "Knowledge assistant",
                "Local search is always available. Generated answers require an explicitly configured provider.",
            ),
            html.Div(
                [
                    dcc.Input(
                        id="knowledge-query",
                        placeholder="Try: What is the fill-rate definition?",
                        className="search-input",
                    ),
                    dcc.Dropdown(
                        id="knowledge-mode",
                        options=[
                            {"label": "Local search", "value": "search"},
                            {"label": "Optional Claude answer", "value": "claude"},
                        ],
                        value="search",
                        clearable=False,
                    ),
                    html.Button("Search", id="knowledge-submit", className="button primary"),
                ],
                className="knowledge-form",
            ),
            html.Div(id="knowledge-result", className="knowledge-result"),
        ]
    )


def knowledge_citations(documents):
    return [
        html.Div(
            [
                "Source: ",
                html.A(
                    document.source,
                    href=f"/knowledge/documents/{quote(Path(document.source).name)}",
                    target="_blank",
                    rel="noreferrer",
                ),
            ]
        )
        for document in documents
    ]


def make_app(settings: Settings | None = None):
    settings = settings or get_settings()
    errors = settings.validate_for_runtime()
    if errors:
        raise RuntimeError("Invalid configuration: " + "; ".join(errors))
    store = SqlServerStore(settings) if settings.storage_mode == "sqlserver" else InMemoryStore()
    knowledge = KnowledgeService(settings.claude_api_key, settings.claude_model)
    server = Flask(__name__)
    server.secret_key = settings.secret_key
    server.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.app_env == "production",
        SESSION_COOKIE_PATH="/",
        PERMANENT_SESSION_LIFETIME=1800,
    )
    if settings.session_redis_url:
        from flask_session import Session
        from redis import Redis

        server.config.update(
            SESSION_TYPE="redis",
            SESSION_REDIS=Redis.from_url(settings.session_redis_url),
            SESSION_KEY_PREFIX="harvestops:",
        )
        Session(server)

    @server.before_request
    def protect_dash_surface():
        protected = request.path == "/" or request.path.startswith(("/_dash-", "/assets/"))
        if not protected:
            return None
        if settings.demo_mode and settings.identity_mode == "demo" and not session.get("username"):
            session["username"] = "demo.viewer"
            session.permanent = True
        if current_user(store):
            return None
        if request.path == "/":
            return redirect("/auth/login")
        return jsonify({"error": "authentication required"}), 401

    @server.after_request
    def security_headers(response):
        if current_user(store):
            response.set_cookie(
                "harvestops_csrf",
                csrf_token(),
                httponly=False,
                secure=settings.app_env == "production",
                samesite="Lax",
                max_age=1800,
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if settings.app_env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @server.get("/healthz")
    def healthz():
        return jsonify({"status": "ok", "service": "harvestops", "mode": settings.storage_mode})

    @server.get("/readyz")
    def readyz():
        if settings.storage_mode == "sqlserver":
            try:
                from .repository import SqlServerRepository

                SqlServerRepository(settings).ping()
            except Exception as exc:  # readiness should not leak the connection string
                log.warning("database readiness failed: %s", type(exc).__name__)
                return jsonify({"status": "not_ready", "reason": "database unavailable"}), 503
        return jsonify({"status": "ready", "synthetic_data": settings.storage_mode == "demo"})

    @server.post("/auth/demo")
    def demo_login():
        if not settings.demo_mode or settings.identity_mode != "demo":
            return jsonify({"error": "demo identity is disabled"}), 403
        if session.get("username") and not valid_csrf(
            request.headers.get("X-CSRF-Token", ""), allow_cookie=False
        ):
            return jsonify({"error": "CSRF token required"}), 403
        username = request.json.get("username", "") if request.is_json else ""
        if username not in store.users:
            return jsonify({"error": "unknown demo account"}), 400
        session["username"] = username
        session.permanent = True
        return jsonify({"username": username, "roles": sorted(store.users[username].roles)})

    @server.get("/auth/login")
    def entra_login():
        if settings.identity_mode != "entra":
            return jsonify({"error": "Entra identity is disabled"}), 403
        state = secrets.token_urlsafe(32)
        flow = EntraAuth(settings).begin(state)
        session["entra_flow"] = flow
        session["entra_state"] = flow.get("state", state)
        session.permanent = True
        return redirect(flow["auth_uri"])

    @server.route("/auth/callback", methods=["GET", "POST"])
    def entra_callback():
        if settings.identity_mode != "entra":
            return jsonify({"error": "Entra identity is disabled"}), 403
        auth_response = (
            request.form.to_dict(flat=True)
            if request.method == "POST"
            else request.args.to_dict(flat=True)
        )
        flow = session.pop("entra_flow", None)
        stored_state = session.pop("entra_state", "")
        expected_state = (flow or {}).get("state") or stored_state
        supplied_state = auth_response.get("state", "")
        if not expected_state or not secrets.compare_digest(supplied_state, expected_state):
            return jsonify({"error": "invalid identity state"}), 400
        if not flow:
            return jsonify({"error": "invalid identity flow"}), 400
        try:
            claims = EntraAuth(settings).redeem(flow, auth_response)
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 401
        principal = claims.get("preferred_username") or claims.get("email") or claims.get("sub")
        if not principal:
            return jsonify({"error": "Entra identity did not include a principal"}), 401
        role_map = {
            "HarvestOps.Operator": "operator",
            "HarvestOps.Approver": "approver",
            "HarvestOps.Admin": "admin",
        }
        claim_roles = claims.get("roles", [])
        if isinstance(claim_roles, str):
            claim_roles = [claim_roles]
        roles = {"viewer"} | {role_map[r] for r in claim_roles if r in role_map}
        display_name = claims.get("name", principal)
        if hasattr(server.session_interface, "regenerate"):
            server.session_interface.regenerate(session)
        session.clear()
        session["roles"] = sorted(roles)
        session["display_name"] = display_name
        session["identity"] = "entra"
        store.users[principal] = User(principal, display_name, roles)
        session["username"] = principal
        session.permanent = True
        return redirect("/")

    @server.get("/knowledge/documents/<path:document_name>")
    def knowledge_document(document_name):
        user = current_user(store)
        if not user:
            return jsonify({"error": "authentication required"}), 401
        if Path(document_name).name != document_name or "\\" in document_name:
            return jsonify({"error": "document not found"}), 404
        document = knowledge.document_for_name(document_name)
        if not document:
            return jsonify({"error": "document not found"}), 404
        if not knowledge._allowed(user, document):
            return jsonify({"error": "forbidden"}), 403
        response = make_response(knowledge.document_text(document))
        response.headers["Content-Type"] = "text/markdown; charset=utf-8"
        response.headers["Content-Disposition"] = "inline"
        return response

    @server.post("/auth/logout")
    def logout():
        if current_user(store) and not valid_csrf(
            request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", ""),
            allow_cookie=False,
        ):
            return jsonify({"error": "CSRF token required"}), 403
        session.clear()
        if request.form:
            return redirect("/")
        return jsonify({"status": "signed_out"})

    @server.get("/api/csrf")
    def get_csrf():
        if not current_user(store):
            return jsonify({"error": "authentication required"}), 403
        return jsonify({"csrf_token": csrf_token()})

    @server.get("/api/shipments/export")
    @require_role(store, "operator", "admin")
    def export_shipments():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["shipment_id", "customer", "product", "status", "freight_cost"])
        for row in store.export_shipments():
            writer.writerow(
                [
                    csv_safe(row["shipment_id"]),
                    csv_safe(row["customer"]),
                    csv_safe(row["product"]),
                    csv_safe(row["status"]),
                    csv_safe(row["freight_cost"]),
                ]
            )
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv"
        response.headers["Content-Disposition"] = "attachment; filename=harvestops-shipments.csv"
        return response

    @server.get("/api/shipments/<shipment_id>")
    @require_role(store, "viewer", "operator", "admin")
    def get_shipment(shipment_id):
        shipment = store.get_shipment(shipment_id)
        if not shipment:
            return jsonify({"error": "shipment not found"}), 404
        return jsonify(
            {
                "shipment_id": shipment.shipment_id,
                "customer": shipment.customer,
                "product": shipment.product,
                "facility": shipment.facility,
                "status": shipment.status,
                "version": shipment.version,
            }
        )

    @server.post("/api/shipments/import")
    @require_role(store, "operator", "admin")
    def import_shipments():
        try:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not valid_csrf(supplied, allow_cookie=False):
                return jsonify({"error": "CSRF token required"}), 403
            actor = current_user(store)
            text = request.get_data(as_text=True)
            if not text or len(text) > 2_000_000:
                return jsonify({"error": "CSV body is required and must be under 2 MB"}), 400
            return jsonify(store.import_shipments(text, actor)), 201
        except (DomainError, PermissionError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    app = Dash(
        __name__,
        server=server,
        title="HarvestOps",
        assets_folder=str(Path(__file__).parent / "assets"),
        suppress_callback_exceptions=True,
    )
    app.layout = lambda: build_layout(store, settings)

    @app.callback(
        Output("page-content", "children"),
        Output("nav-dashboard", "className"),
        Output("nav-shipments", "className"),
        Output("nav-purchasing", "className"),
        Output("nav-knowledge", "className"),
        Input("nav-dashboard", "n_clicks"),
        Input("nav-shipments", "n_clicks"),
        Input("nav-purchasing", "n_clicks"),
        Input("nav-knowledge", "n_clicks"),
        Input("active-user", "data"),
        Input("url", "search"),
    )
    def switch_page(*_clicks):
        search = _clicks[-1] or ""
        query = parse_qs(search.lstrip("?"))
        requested_page = query.get("page", [None])[0]
        page = {
            "nav-dashboard": "dashboard",
            "nav-shipments": "shipments",
            "nav-purchasing": "purchasing",
            "nav-knowledge": "knowledge",
        }.get(ctx.triggered_id, requested_page or "dashboard")
        requested_shipment = query.get("shipment", [None])[0] if page == "shipments" else None
        view = {
            "dashboard": dashboard_view(store),
            "shipments": shipments_view(store, requested_shipment, settings),
            "purchasing": purchasing_view(store, settings),
            "knowledge": knowledge_view(),
        }.get(page, dashboard_view(store))
        classes = [
            f"nav-item{' active' if selected == page else ''}"
            for selected in ("dashboard", "shipments", "purchasing", "knowledge")
        ]
        return view, *classes

    @app.callback(
        Output("csrf-token", "data"),
        Output("csrf-status", "children"),
        Output("csrf-status", "data-csrf-token"),
        Input("url", "pathname"),
    )
    def initialize_csrf(_):
        token = csrf_token()
        return token, "ready", token

    @app.callback(Output("user-label", "children"), Input("role-switch", "value"))
    def role_label(username):
        user = current_user(store)
        if not user:
            return ""
        return f"{user.display_name} · {', '.join(sorted(user.roles))}"

    @app.callback(
        Output("active-user", "data"),
        Input("role-switch", "value"),
        State("csrf-token", "data"),
        State("csrf-status", "data-csrf-token"),
    )
    def switch_user(username, token, status_token):
        if (
            settings.demo_mode
            and (valid_csrf(token) or valid_csrf(status_token))
            and username in store.users
        ):
            session["username"] = username
            return username
        return no_update

    @app.callback(
        Output("kpi-row", "children"),
        Output("volume-chart", "figure"),
        Output("service-chart", "figure"),
        Output("exceptions-table", "children"),
        Input("filter-dates", "start_date"),
        Input("filter-dates", "end_date"),
        Input("filter-customer", "value"),
        Input("filter-product", "value"),
        Input("filter-facility", "value"),
    )
    def refresh_dashboard(start_date, end_date, customer, product, facility):
        filters = {
            "start_date": start_date,
            "end_date": end_date,
            "customer": customer,
            "product": product,
            "facility": facility,
        }
        k = store.kpis(filters)
        cards = [
            metric_card(
                "Shipment volume",
                str(k["shipment_volume"]),
                " loads",
                "All shipments matching the selected filters",
            ),
            metric_card(
                "On-time rate",
                f"{k['on_time_rate']:.1f}",
                "%",
                "Departed shipments only; Scheduled and Cancelled are excluded",
            ),
            metric_card(
                "Fill rate",
                f"{k['fill_rate']:.1f}",
                "%",
                "Shipped quantity ÷ ordered quantity in scope",
            ),
            metric_card(
                "Freight cost",
                f"${k['freight_cost']:,.0f}",
                "",
                "Freight cost for shipments matching the selected filters",
            ),
            metric_card(
                "Production output",
                f"{k['production_output']:,}",
                " units",
                "Production runs in date and facility scope; customer does not attribute production",
            ),
            metric_card(
                "Labor productivity",
                f"{k['labor_productivity']:,.1f}",
                " units/hour",
                "Output ÷ labor hours; customer does not attribute production",
            ),
        ]
        volume_rows = store.dashboard_volume(filters)
        service_counts = store.dashboard_service(filters)
        volume = go.Figure(
            go.Bar(
                x=[row["label"] for row in volume_rows],
                y=[float(row["shipped_qty"]) for row in volume_rows],
                marker_color="#0f766e",
            )
        )
        volume.update_layout(
            title="Shipped quantity by facility",
            height=300,
            margin={"l": 30, "r": 20, "t": 55, "b": 30},
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        service = go.Figure(
            go.Pie(
                labels=["Open / scheduled", "Departed on time", "Departed late", "Cancelled"],
                values=[
                    service_counts["open_scheduled"],
                    service_counts["departed_on_time"],
                    service_counts["departed_late"],
                    service_counts["cancelled"],
                ],
                hole=0.65,
                marker_colors=["#64748b", "#2f855a", "#d97706", "#b91c1c"],
            )
        )
        service.update_layout(
            title="Shipment service categories",
            height=300,
            margin={"l": 20, "r": 20, "t": 55, "b": 20},
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=True,
        )
        exceptions = store.shipment_exceptions(filters)
        table = (
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(label)
                                for label in ["Shipment", "Customer", "Issue", "Fill", "Status"]
                            ]
                        )
                    ),
                    html.Tbody(
                        [
                            html.Tr(
                                [
                                    html.Td(
                                        html.A(
                                            r.shipment_id,
                                            href="/?"
                                            + urlencode(
                                                {"page": "shipments", "shipment": r.shipment_id}
                                            ),
                                            className="table-link",
                                        )
                                    ),
                                    html.Td(r.customer),
                                    html.Td(
                                        "Late departure"
                                        if r.actual_departure_utc and not r.on_time
                                        else "Partial fill"
                                    ),
                                    html.Td(f"{r.fill_rate:.0%}"),
                                    html.Td(status_badge(r.status)),
                                ]
                            )
                            for r in exceptions
                        ]
                    ),
                ],
                className="data-table",
            )
            if exceptions
            else empty_state("No exceptions in the selected scope.")
        )
        return cards, volume, service, table

    @app.callback(
        Output("ship-page", "data"),
        Output("shipment-grid", "rowData"),
        Output("shipment-page-info", "children"),
        Output("ship-prev", "disabled"),
        Output("ship-next", "disabled"),
        Output("ship-pagination-label", "children"),
        Output("shipment-grid", "selectedRows"),
        Input("ship-customer", "value"),
        Input("ship-product", "value"),
        Input("ship-facility", "value"),
        Input("ship-exceptions", "value"),
        Input("ship-prev", "n_clicks"),
        Input("ship-next", "n_clicks"),
        Input("shipment-refresh", "data"),
        Input("active-user", "data"),
        State("ship-page", "data"),
        State("selected-shipment-id", "data"),
    )
    def refresh_shipments(
        customer,
        product,
        facility,
        exception,
        _,
        __,
        _refresh,
        _active_user,
        stored_page,
        selected_id,
    ):
        from dash import ctx

        page = max(1, int(stored_page or 1))
        if ctx.triggered_id == "ship-prev":
            page = max(1, page - 1)
        elif ctx.triggered_id == "ship-next":
            page += 1
        rows, total = store.list_shipments(
            {
                "customer": customer,
                "product": product,
                "facility": facility,
                "exceptions_only": bool(exception),
            },
            page,
            SHIPMENT_PAGE_SIZE,
        )
        max_page = max(1, math.ceil(total / SHIPMENT_PAGE_SIZE))
        safe_page = min(page, max_page)
        if safe_page != page:
            rows, total = store.list_shipments(
                {
                    "customer": customer,
                    "product": product,
                    "facility": facility,
                    "exceptions_only": bool(exception),
                },
                safe_page,
                SHIPMENT_PAGE_SIZE,
            )
        selected_rows = [
            row
            for row in shipment_grid_rows(rows)
            if selected_id and row["shipment_id"] == selected_id
        ]
        return (
            safe_page,
            shipment_grid_rows(rows),
            f"Page {safe_page} of {max_page} · {total} matching shipments",
            safe_page <= 1,
            safe_page >= max_page,
            f"Page {safe_page} of {max_page}",
            selected_rows,
        )

    @app.callback(
        Output("selected-shipment-id", "data"),
        Output("selected-shipment-version", "data"),
        Output("shipment-detail", "children"),
        Input("shipment-grid", "selectedRows"),
        prevent_initial_call=True,
    )
    def select_shipment(rows):
        selected = rows[0] if rows else None
        shipment_id = selected.get("shipment_id") if selected else None
        shipment = store.get_shipment(shipment_id) if shipment_id else None
        return (
            shipment_id,
            shipment.version if shipment else None,
            shipment_detail_view(store, current_user(store), shipment_id, settings),
        )

    @app.callback(
        Output("shipment-refresh", "data"),
        Input("refresh-selection", "n_clicks"),
        State("shipment-refresh", "data"),
        prevent_initial_call=True,
    )
    def refresh_selected_shipment(_, refresh):
        return int(refresh or 0) + 1

    @app.callback(
        Output("shipment-lookup-result", "children"),
        Input("shipment-lookup-submit", "n_clicks"),
        State("shipment-lookup-id", "value"),
        prevent_initial_call=True,
    )
    def lookup_shipment_details(_, shipment_id):
        try:
            user = current_user(store)
            if not user or not user.roles.intersection({"viewer", "operator", "admin"}):
                raise PermissionError("Viewer role required")
            normalized_id = str(shipment_id or "").strip().upper()
            if not normalized_id or len(normalized_id) > 30:
                raise ValueError("Enter a shipment ID under 30 characters")
            shipment = store.get_shipment(normalized_id)
            if not shipment:
                return empty_state("No shipment found for that ID.")
            return html.Div(
                [
                    html.Strong(shipment.shipment_id),
                    html.Span(" · "),
                    html.Span(shipment.customer),
                    html.Span(" · "),
                    html.Span(shipment.product),
                    html.Div(f"{shipment.facility} · {shipment.status}"),
                ],
                className="lookup-detail",
            )
        except (PermissionError, ValueError) as exc:
            return empty_state(f"Lookup failed: {exc}")

    @app.callback(
        Output("confirm-status", "displayed"),
        Input("apply-status", "n_clicks"),
        prevent_initial_call=True,
    )
    def ask_status_confirmation(n_clicks):
        return bool(n_clicks)

    @app.callback(
        Output("shipment-alert", "children"),
        Output("shipment-refresh", "data", allow_duplicate=True),
        Input("confirm-status", "submit_n_clicks"),
        State("selected-shipment-id", "data"),
        State("selected-status", "value"),
        State("selected-shipment-version", "data"),
        State("csrf-token", "data"),
        State("csrf-status", "data-csrf-token"),
        prevent_initial_call=True,
    )
    def apply_status(_, shipment_id, new_status, version, token, status_token):
        try:
            if not (valid_csrf(token) or valid_csrf(status_token)):
                raise PermissionError("CSRF token required")
            user = current_user(store)
            if not shipment_id or not new_status:
                raise ValueError("Select a shipment and a valid next status")
            updated = store.change_status(shipment_id, new_status, user, int(version))
            return (
                f"Updated {updated.shipment_id} to {updated.status}; version {updated.version}. Refreshing the selected record.",
                1,
            )
        except (DomainError, PermissionError, TypeError, ValueError) as exc:
            return f"Could not apply change: {exc}", no_update

    @app.callback(
        Output("shipment-alert", "children", allow_duplicate=True),
        Output("import-freshness", "children"),
        Output("import-report", "children"),
        Input("shipment-import-upload", "contents"),
        State("shipment-import-upload", "filename"),
        State("csrf-token", "data"),
        State("csrf-status", "data-csrf-token"),
        prevent_initial_call=True,
    )
    def import_from_upload(contents, filename, token, status_token):
        try:
            import base64

            if not (valid_csrf(token) or valid_csrf(status_token)):
                raise PermissionError("CSRF token required")
            user = current_user(store)
            if not user or not user.roles.intersection({"operator", "admin"}):
                raise PermissionError("Operator role required")
            if not contents:
                raise ValueError("CSV content is required")
            _, encoded = contents.split(",", 1)
            result = store.import_shipments(base64.b64decode(encoded).decode("utf-8"), user)
            return (
                f"Imported {result['applied']} records from {filename or 'upload'}; {len(result['errors'])} rejected. Run {result['run_id']} at {result['occurred_utc']} UTC.",
                freshness_text(store.import_freshness()),
                import_report_children(store.import_history()),
            )
        except (DomainError, PermissionError, ValueError, UnicodeDecodeError) as exc:
            return f"Import failed: {exc}", no_update, no_update

    @app.callback(
        Output("purchase-list", "children"),
        Output("selected-purchase-id", "data"),
        Output("purchase-detail", "children"),
        Output("submit-selected-purchase", "disabled"),
        Output("selected-decision", "disabled"),
        Output("purchase-decision-comment", "disabled"),
        Output("record-selected-decision", "disabled"),
        Output("purchase-alert", "children"),
        Output("purchase-history", "children"),
        Input("purchase-status-filter", "value"),
        Input({"type": "purchase-select", "request_id": ALL}, "n_clicks"),
        Input("create-purchase", "n_clicks"),
        Input("submit-selected-purchase", "n_clicks"),
        Input("record-selected-decision", "n_clicks"),
        State("purchase-facility", "value"),
        State("purchase-product", "value"),
        State("purchase-qty", "value"),
        State("purchase-cost", "value"),
        State("selected-purchase-id", "data"),
        State("selected-decision", "value"),
        State("purchase-decision-comment", "value"),
        State("purchase-status-filter", "value"),
        State("csrf-token", "data"),
        State("csrf-status", "data-csrf-token"),
    )
    def refresh_purchase_queue(
        status_filter,
        _clicks,
        _create_click,
        _submit_click,
        _decision_click,
        facility,
        product,
        qty,
        cost,
        selected_id,
        decision,
        comment,
        action_status_filter,
        token,
        status_token,
    ):
        triggered = ctx.triggered_id
        if isinstance(triggered, dict):
            selected_id = triggered.get("request_id")
        elif triggered == "purchase-status-filter":
            selected_id = None
        user = current_user(store)
        alert = no_update
        is_action = isinstance(triggered, str) and triggered in {
            "create-purchase",
            "submit-selected-purchase",
            "record-selected-decision",
        }
        if is_action:
            try:
                if not (valid_csrf(token) or valid_csrf(status_token)):
                    raise PermissionError("CSRF token required")
                if triggered == "create-purchase":
                    request = store.create_purchase(
                        user, facility, [{"product": product, "quantity": qty, "unit_cost": cost}]
                    )
                    selected_id = request.request_id
                    alert = f"Created {request.request_id} as draft for ${request.total:,.2f}."
                else:
                    request = store.get_purchase(selected_id, user) if selected_id else None
                    if not request:
                        raise PermissionError("Selected request is not available")
                    if triggered == "submit-selected-purchase":
                        request = store.submit_purchase(request.request_id, user, request.version)
                        alert = f"Submitted {request.request_id} for approval."
                    else:
                        request = store.decide_purchase(
                            request.request_id, user, decision, comment or "", request.version
                        )
                        alert = (
                            f"Recorded {request.status.lower()} decision for {request.request_id}."
                        )
            except (DomainError, PermissionError, TypeError, ValueError) as exc:
                alert = f"Could not complete action: {exc}"

        status_filter = action_status_filter if is_action else status_filter
        selected_request = store.get_purchase(selected_id, user) if selected_id else None
        can_submit = bool(
            selected_request
            and selected_request.status == "Draft"
            and selected_request.requester == user.username
        )
        can_decide = bool(
            selected_request
            and selected_request.status == "Pending"
            and user.roles.intersection({"approver", "admin"})
            and selected_request.requester != user.username
        )
        return (
            purchase_queue(store, user, status_filter, settings),
            selected_id,
            purchase_detail_view(store, user, selected_id, settings),
            not can_submit,
            not can_decide,
            not can_decide,
            not can_decide,
            alert,
            purchase_history_view(store, user, settings),
        )

    @app.callback(
        Output("knowledge-result", "children"),
        Input("knowledge-submit", "n_clicks"),
        State("knowledge-query", "value"),
        State("knowledge-mode", "value"),
        prevent_initial_call=True,
    )
    def knowledge_search(_, query, mode):
        hits = knowledge.search(query, current_user(store))
        if not hits:
            return html.Div(
                [
                    html.Div(
                        "No permitted operating document matched that query.",
                        className="empty-state",
                    )
                ]
            )
        if mode == "claude":
            result = knowledge.answer_with_claude(query, hits, current_user(store))
            return html.Div(
                [
                    html.Div("Claude answer mode · optional provider", className="mode-label"),
                    html.P(result["message"]),
                    html.Div(
                        f"Usage metadata: {result['usage'] or 'not available'}",
                        className="section-subtitle",
                    ),
                    html.Div(knowledge_citations(hits), className="citation"),
                ]
            )
        return html.Div(
            [
                html.Div("Local search", className="mode-label"),
                html.H3(hits[0].title),
                html.P(hits[0].body),
                html.Div(knowledge_citations(hits), className="citation"),
            ]
        )

    return app


app = make_app()
server = app.server

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
