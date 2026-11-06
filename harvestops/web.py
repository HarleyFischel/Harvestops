import csv
import io
import logging
import math
import secrets
from functools import wraps
from pathlib import Path

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update
from dash_ag_grid import AgGrid
from flask import Flask, has_request_context, jsonify, make_response, redirect, request, session

from .auth import EntraAuth
from .config import Settings, get_settings
from .domain import User
from .knowledge import KnowledgeService
from .logging_config import configure_logging
from .services import DomainError, InMemoryStore
from .sql_store import SqlServerStore

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
    return html.Div([
        dcc.Location(id="url"),
        dcc.Store(id="active-user", data="demo.viewer"),
        dcc.Store(id="csrf-token", data=csrf_token() if has_request_context() else None),
        html.Div(id="csrf-status", className="visually-hidden", role="status", **{"data-csrf-token": ""}),
        html.Header([
            html.Div([html.Div("HARVESTOPS", className="brand"), html.Div("Produce operations control plane", className="tagline")], className="brand-lockup"),
            html.Div([html.Span("SYNTHETIC DATA · DEMO MODE" if demo_identity else "SYNTHETIC DATA · ENTRA IDENTITY", className="demo-pill"), html.Span(id="user-label", className="user-label")], className="header-meta"),
        ], className="topbar"),
        html.Main([
            html.Aside([
                html.Div("WORKSPACE", className="eyebrow"),
                dcc.RadioItems(id="nav", options=[
                    {"label": "Operations dashboard", "value": "dashboard"},
                    {"label": "Dock & shipment board", "value": "shipments"},
                    {"label": "Purchasing approvals", "value": "purchasing"},
                    {"label": "Knowledge assistant", "value": "knowledge"},
                ], value="dashboard", className="nav-list", labelClassName="nav-item"),
                html.Div("DEMO ACCOUNT", className="eyebrow side-space") if demo_identity else html.Div("IDENTITY", className="eyebrow side-space"),
                dcc.Dropdown(id="role-switch", options=[{"label": u.display_name, "value": u.username} for u in store.users.values()], value="demo.viewer", clearable=False) if demo_identity else html.A("Sign in with Microsoft Entra ID", href="/auth/login", className="button secondary"),
                html.Div("Role changes are development-only and enforced server-side.", className="side-note") if demo_identity else html.Div("Roles are mapped from Entra app-role claims.", className="side-note"),
            ], className="sidebar"),
            html.Section(id="page-content", className="content"),
        ], className="shell"),
        html.Footer("UTC storage · display timezone: " + settings.display_timezone + " · Portfolio application with synthetic data", className="footer"),
    ], className="app-shell")


def metric_card(label, value, suffix="", note=""):
    return html.Div([html.Div(label, className="metric-label"), html.Div([html.Span(value, className="metric-value"), html.Span(suffix, className="metric-suffix")]), html.Div(note, className="metric-note")], className="metric-card")


def csv_safe(value) -> str:
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def dashboard_view(store: InMemoryStore):
    options = store.filter_options()
    return html.Div([
        html.Div([html.Div([html.Div("Operations dashboard", className="page-kicker"), html.H1("Move today’s harvest with confidence."), html.P("A single operational view of volume, service, fill, and labor signals.")]), html.Div("Last refreshed · synthetic seed", className="refresh-note")], className="page-heading"),
        html.Div([html.Div([html.Label("Planned departure range"), dcc.DatePickerRange(id="filter-dates", start_date="2026-01-01", end_date="2026-03-31", display_format="YYYY-MM-DD", minimum_nights=0)], className="filter-control date-filter"), html.Div([html.Label("Customer"), dcc.Dropdown(id="filter-customer", options=[{"label": "All customers", "value": "All"}] + [{"label": x, "value": x} for x in options["customer"]], value="All")], className="filter-control"), html.Div([html.Label("Product"), dcc.Dropdown(id="filter-product", options=[{"label": "All products", "value": "All"}] + [{"label": x, "value": x} for x in options["product"]], value="All")], className="filter-control"), html.Div([html.Label("Facility"), dcc.Dropdown(id="filter-facility", options=[{"label": "All facilities", "value": "All"}] + [{"label": x, "value": x} for x in options["facility"]], value="All")], className="filter-control")], className="filter-row"),
        html.Div(id="kpi-row", className="metric-grid"),
        html.Div([dcc.Graph(id="volume-chart", config={"displayModeBar": False}), dcc.Graph(id="service-chart", config={"displayModeBar": False})], className="chart-grid"),
        html.Div([html.Div([html.Div("Shipment exceptions", className="section-title"), html.Div("Late departures or partial fills require an operator decision.", className="section-subtitle")], className="section-heading"), html.Div(id="exceptions-table")], className="panel"),
    ])


def shipments_view(store: InMemoryStore):
    options = store.filter_options()
    return html.Div([
        html.Div([html.Div([html.Div("Execution board", className="page-kicker"), html.H1("Dock & shipment board"), html.P("Server-side rules protect each status transition and export.")]), html.A("Export CSV", href="/api/shipments/export", id="export-csv", className="button secondary")], className="page-heading"),
        html.Div([html.Div([html.Label("Customer"), dcc.Dropdown(id="ship-customer", options=[{"label": "All", "value": "All"}] + [{"label": x, "value": x} for x in options["customer"]], value="All")], className="filter-control"), html.Div([html.Label("Exceptions only"), dcc.Checklist(id="ship-exceptions", options=[{"label": " Show exceptions", "value": "yes"}], className="check-control")], className="filter-control"), html.Div([html.Label("Server page"), dcc.Input(id="ship-page", type="number", min=1, value=1)], className="filter-control")], className="filter-row"),
        html.Div(id="shipment-alert", className="alert"),
        AgGrid(id="shipment-grid", columnDefs=[{"field": x, "headerName": x.replace("_", " ").title()} for x in ["shipment_id", "customer", "product", "facility", "carrier", "dock", "dock_appointment", "planned_departure", "actual_departure", "ordered_qty", "shipped_qty", "freight_cost", "status", "version"]], rowData=[], defaultColDef={"sortable": True, "filter": True, "resizable": True}, dashGridOptions={"animateRows": False, "pagination": False}, className="ag-theme-alpine", style={"height": "430px", "width": "100%"}),
        html.Div(id="shipment-page-info", className="section-subtitle"),
        dcc.Upload(id="shipment-import-upload", children=html.Div("Upload shipment CSV"), className="upload-control", multiple=False),
        html.Div([html.Label("Shipment ID"), dcc.Input(id="status-shipment-id", placeholder="SHP-1001"), html.Label("New status"), dcc.Dropdown(id="status-value", options=[{"label": x, "value": x} for x in ["Scheduled", "In Transit", "Delivered", "Exception", "Cancelled"]], clearable=False), html.Label("Expected version"), dcc.Input(id="status-version", type="number", value=1), html.Button("Apply status", id="apply-status", className="button primary")], className="inline-form"),
    ])


def purchase_cards(store, user):
    cards = [html.Div([html.Div(r.request_id, className="purchase-id"), html.Div(f"{r.facility} · {r.requester}"), html.Div(f"${r.total:,.2f} · {r.status}", className="purchase-status")], className="purchase-card") for r in store.list_purchases(user)]
    return cards or [html.Div("No purchase requests are visible for this account.", className="empty-state")]


def purchase_history_view(store, user):
    events = [html.Div(f"{event.occurred_utc.isoformat()} · {event.actor} · {event.action} · {event.entity_id}", className="section-subtitle") for event in store.purchase_history(user)]
    return events or [html.Div("No approval history is available.", className="empty-state")]


def purchasing_view(store):
    user = current_user(store)
    return html.Div([
        html.Div([html.Div([html.Div("Controls & approvals", className="page-kicker"), html.H1("Purchasing approvals"), html.P("Create requests, submit for review, and preserve the decision trail.")])], className="page-heading"),
        html.Div([html.Div([html.Label("Facility"), dcc.Input(id="purchase-facility", value="Salinas")], className="filter-control"), html.Div([html.Label("Product"), dcc.Input(id="purchase-product", value="Romaine Hearts")], className="filter-control"), html.Div([html.Label("Quantity"), dcc.Input(id="purchase-qty", type="number", value=100)], className="filter-control"), html.Div([html.Label("Unit cost"), dcc.Input(id="purchase-cost", type="number", value=2.5)], className="filter-control"), html.Button("Create request", id="create-purchase", className="button primary")], className="inline-form"),
        html.Div(id="purchase-alert", className="alert"), html.Div("Request queue", className="section-title"), html.Div(id="purchase-list", children=purchase_cards(store, user), className="purchase-list"), html.Div("Approval history", className="section-title"), html.Div(id="purchase-history", children=purchase_history_view(store, user), className="purchase-history"),
        html.Div([html.Label("Request ID"), dcc.Input(id="submit-request-id", placeholder="PR-1001"), html.Label("Expected version"), dcc.Input(id="submit-version", type="number", value=1), html.Button("Submit for approval", id="submit-purchase", className="button secondary")], className="inline-form"),
        html.Div([html.Label("Request ID"), dcc.Input(id="decision-request-id", placeholder="PR-1001"), html.Label("Decision"), dcc.Dropdown(id="decision-value", options=[{"label": x, "value": x} for x in ["Approved", "Rejected"]], clearable=False), html.Label("Comment"), dcc.Input(id="decision-comment"), html.Label("Expected version"), dcc.Input(id="decision-version", type="number", value=1), html.Button("Record decision", id="record-decision", className="button primary")], className="inline-form approver-form"),
    ])


def knowledge_view():
    return html.Div([
        html.Div([html.Div([html.Div("Operating memory", className="page-kicker"), html.H1("Knowledge assistant"), html.P("Local search is always available. Generated answers require an explicitly configured provider.")])], className="page-heading"),
        html.Div([dcc.Input(id="knowledge-query", placeholder="Try: What is the fill-rate definition?", className="search-input"), dcc.Dropdown(id="knowledge-mode", options=[{"label": "Local search", "value": "search"}, {"label": "Optional Claude answer", "value": "claude"}], value="search", clearable=False), html.Button("Search", id="knowledge-submit", className="button primary")], className="knowledge-form"), html.Div(id="knowledge-result", className="knowledge-result"),
    ])


def make_app(settings: Settings | None = None):
    settings = settings or get_settings()
    errors = settings.validate_for_runtime()
    if errors:
        raise RuntimeError("Invalid configuration: " + "; ".join(errors))
    store = SqlServerStore(settings) if settings.storage_mode == "sqlserver" else InMemoryStore()
    knowledge = KnowledgeService(settings.claude_api_key, settings.claude_model)
    server = Flask(__name__)
    server.secret_key = settings.secret_key
    server.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=settings.app_env == "production", PERMANENT_SESSION_LIFETIME=1800)
    if settings.session_redis_url:
        from flask_session import Session
        from redis import Redis

        server.config.update(SESSION_TYPE="redis", SESSION_REDIS=Redis.from_url(settings.session_redis_url), SESSION_KEY_PREFIX="harvestops:")
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
            response.set_cookie("harvestops_csrf", csrf_token(), httponly=False, secure=settings.app_env == "production", samesite="Lax", max_age=1800)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.app_env == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
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
        if session.get("username") and not valid_csrf(request.headers.get("X-CSRF-Token", ""), allow_cookie=False):
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
        session["entra_state"] = state
        return redirect(EntraAuth(settings).login_url(state))

    @server.get("/auth/callback")
    def entra_callback():
        if settings.identity_mode != "entra":
            return jsonify({"error": "Entra identity is disabled"}), 403
        supplied_state = request.args.get("state", "")
        expected_state = session.pop("entra_state", "")
        if not expected_state or not secrets.compare_digest(supplied_state, expected_state):
            return jsonify({"error": "invalid identity state"}), 400
        claims = EntraAuth(settings).redeem(request.args.to_dict())
        principal = claims.get("preferred_username") or claims.get("email") or claims.get("sub")
        role_map = {"HarvestOps.Operator": "operator", "HarvestOps.Approver": "approver", "HarvestOps.Admin": "admin"}
        claim_roles = claims.get("roles", [])
        if isinstance(claim_roles, str):
            claim_roles = [claim_roles]
        roles = {"viewer"} | {role_map[r] for r in claim_roles if r in role_map}
        display_name = claims.get("name", principal)
        session["roles"] = sorted(roles)
        session["display_name"] = display_name
        session["identity"] = "entra"
        store.users[principal] = User(principal, display_name, roles)
        session["username"] = principal
        session.permanent = True
        return jsonify({"username": principal, "roles": sorted(roles), "identity": "entra"})

    @server.post("/auth/logout")
    def logout():
        if current_user(store) and not valid_csrf(request.headers.get("X-CSRF-Token", ""), allow_cookie=False):
            return jsonify({"error": "CSRF token required"}), 403
        session.clear()
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
            writer.writerow([csv_safe(row["shipment_id"]), csv_safe(row["customer"]), csv_safe(row["product"]), csv_safe(row["status"]), csv_safe(row["freight_cost"])])
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv"
        response.headers["Content-Disposition"] = "attachment; filename=harvestops-shipments.csv"
        return response

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

    app = Dash(__name__, server=server, title="HarvestOps", assets_folder=str(Path(__file__).parent / "assets"), suppress_callback_exceptions=True)
    app.layout = lambda: build_layout(store, settings)

    @app.callback(Output("page-content", "children"), Input("nav", "value"))
    def switch_page(page):
        return {"dashboard": dashboard_view(store), "shipments": shipments_view(store), "purchasing": purchasing_view(store), "knowledge": knowledge_view()}.get(page, dashboard_view(store))

    @app.callback(Output("csrf-token", "data"), Output("csrf-status", "children"), Output("csrf-status", "data-csrf-token"), Input("url", "pathname"))
    def initialize_csrf(_):
        token = csrf_token()
        return token, "ready", token

    @app.callback(Output("user-label", "children"), Input("role-switch", "value"))
    def role_label(username):
        user = current_user(store)
        if not user:
            return ""
        return f"{user.display_name} · {', '.join(sorted(user.roles))}"

    @app.callback(Output("active-user", "data"), Input("role-switch", "value"), State("csrf-token", "data"), State("csrf-status", "data-csrf-token"))
    def switch_user(username, token, status_token):
        if settings.demo_mode and (valid_csrf(token) or valid_csrf(status_token)) and username in store.users:
            session["username"] = username
            return username
        return no_update

    @app.callback(Output("kpi-row", "children"), Output("volume-chart", "figure"), Output("service-chart", "figure"), Output("exceptions-table", "children"), Input("filter-dates", "start_date"), Input("filter-dates", "end_date"), Input("filter-customer", "value"), Input("filter-product", "value"), Input("filter-facility", "value"))
    def refresh_dashboard(start_date, end_date, customer, product, facility):
        filters = {"start_date": start_date, "end_date": end_date, "customer": customer, "product": product, "facility": facility}
        k = store.kpis(filters)
        cards = [metric_card("Shipment volume", str(k["shipment_volume"]), " loads", "Seeded records in scope"), metric_card("On-time rate", f"{k['on_time_rate']:.1f}", "%", "Closed shipments only"), metric_card("Fill rate", f"{k['fill_rate']:.1f}", "%", "Shipped ÷ ordered"), metric_card("Freight cost", f"${k['freight_cost']:,.0f}", "", "Shipment freight in scope"), metric_card("Production output", f"{k['production_output']:,}", " units", "Production runs in scope"), metric_card("Labor productivity", f"{k['labor_productivity']:,.1f}", " units/hour", "Output ÷ labor hours")]
        rows, _ = store.list_shipments(filters, 1, 100)
        volume = go.Figure(go.Bar(x=[r.shipment_id for r in rows], y=[float(r.shipped_qty) for r in rows], marker_color="#0f766e"))
        volume.update_layout(title="Shipped quantity by load", height=300, margin={"l": 30, "r": 20, "t": 55, "b": 30}, plot_bgcolor="white", paper_bgcolor="white")
        service = go.Figure(go.Pie(labels=["On time", "Late / open"], values=[sum(1 for r in rows if r.on_time), sum(1 for r in rows if not r.on_time)], hole=.65, marker_colors=["#2f855a", "#f59e0b"]))
        service.update_layout(title="Service signal", height=300, margin={"l": 20, "r": 20, "t": 55, "b": 20}, plot_bgcolor="white", paper_bgcolor="white", showlegend=True)
        exceptions = [r for r in rows if r.status == "Exception" or (r.actual_departure_utc and not r.on_time) or r.fill_rate < .95]
        table = dash_table.DataTable(data=[{"Shipment": r.shipment_id, "Customer": r.customer, "Issue": "Late departure" if r.actual_departure_utc and not r.on_time else "Partial fill", "Fill": f"{r.fill_rate:.0%}", "Status": r.status} for r in exceptions], columns=[{"name": x, "id": x} for x in ["Shipment", "Customer", "Issue", "Fill", "Status"]], style_cell={"padding": "10px", "fontFamily": "Inter, sans-serif"}, style_header={"fontWeight": "700", "backgroundColor": "#edf2f2"})
        return cards, volume, service, table

    @app.callback(Output("shipment-grid", "rowData"), Output("shipment-page-info", "children"), Input("ship-customer", "value"), Input("ship-exceptions", "value"), Input("ship-page", "value"))
    def refresh_shipments(customer, exception, page):
        page = max(1, int(page or 1))
        rows, total = store.list_shipments({"customer": customer, "exceptions_only": bool(exception)}, page, 8)
        max_page = max(1, math.ceil(total / 8))
        data = [{"shipment_id": r.shipment_id, "customer": r.customer, "product": r.product, "facility": r.facility, "carrier": r.carrier, "dock": r.dock, "dock_appointment": r.appointment_utc.isoformat(), "planned_departure": r.planned_departure_utc.isoformat(), "actual_departure": r.actual_departure_utc.isoformat() if r.actual_departure_utc else "", "ordered_qty": str(r.ordered_qty), "shipped_qty": str(r.shipped_qty), "freight_cost": str(r.freight_cost), "status": r.status, "version": r.version} for r in rows]
        return data, f"Page {min(page, max_page)} of {max_page} · {total} matching shipments"

    @app.callback(Output("shipment-alert", "children"), Input("apply-status", "n_clicks"), State("status-shipment-id", "value"), State("status-value", "value"), State("status-version", "value"), State("csrf-token", "data"), State("csrf-status", "data-csrf-token"), prevent_initial_call=True)
    def apply_status(_, shipment_id, new_status, version, token, status_token):
        try:
            if not (valid_csrf(token) or valid_csrf(status_token)):
                raise PermissionError("CSRF token required")
            user = current_user(store)
            updated = store.change_status(shipment_id, new_status, user, int(version))
            return f"Updated {updated.shipment_id} to {updated.status}; version {updated.version}."
        except (DomainError, PermissionError, TypeError, ValueError) as exc:
            return f"Could not apply change: {exc}"

    @app.callback(Output("shipment-alert", "children", allow_duplicate=True), Input("shipment-import-upload", "contents"), State("shipment-import-upload", "filename"), State("csrf-token", "data"), State("csrf-status", "data-csrf-token"), prevent_initial_call=True)
    def import_from_upload(contents, filename, token, status_token):
        try:
            import base64
            if not (valid_csrf(token) or valid_csrf(status_token)):
                raise PermissionError("CSRF token required")
            user = current_user(store)
            if not user or not user.roles.intersection({"operator", "admin"}):
                raise PermissionError("Operator role required")
            _, encoded = contents.split(",", 1)
            result = store.import_shipments(base64.b64decode(encoded).decode("utf-8"), user)
            return f"Imported {result['applied']} records from {filename or 'upload'}; {len(result['errors'])} rejected. Run {result['run_id']} at {result['occurred_utc']} UTC."
        except (DomainError, PermissionError, ValueError, UnicodeDecodeError) as exc:
            return f"Import failed: {exc}"

    @app.callback(Output("purchase-alert", "children"), Output("purchase-list", "children"), Output("purchase-history", "children"), Input("create-purchase", "n_clicks"), Input("submit-purchase", "n_clicks"), Input("record-decision", "n_clicks"), State("purchase-facility", "value"), State("purchase-product", "value"), State("purchase-qty", "value"), State("purchase-cost", "value"), State("submit-request-id", "value"), State("submit-version", "value"), State("decision-request-id", "value"), State("decision-value", "value"), State("decision-comment", "value"), State("decision-version", "value"), State("csrf-token", "data"), State("csrf-status", "data-csrf-token"), prevent_initial_call=True)
    def purchase_action(create_click, submit_click, decision_click, facility, product, qty, cost, submit_id, submit_version, req_id, decision, comment, version, token, status_token):
        from dash import ctx
        try:
            if not (valid_csrf(token) or valid_csrf(status_token)):
                raise PermissionError("CSRF token required")
            user = current_user(store)
            if ctx.triggered_id == "create-purchase":
                req = store.create_purchase(user, facility, [{"product": product, "quantity": qty, "unit_cost": cost}])
                message = f"Created {req.request_id} as draft for ${req.total:,.2f}."
            elif ctx.triggered_id == "submit-purchase":
                req = store.submit_purchase(submit_id, user, int(submit_version))
                message = f"Submitted {req.request_id} for approval."
            else:
                req = store.decide_purchase(req_id, user, decision, comment or "", int(version))
                message = f"Recorded {req.status.lower()} decision for {req.request_id}."
            cards = purchase_cards(store, user)
            history = purchase_history_view(store, user)
            return message, cards, history
        except (DomainError, PermissionError, TypeError, ValueError) as exc:
            return f"Could not complete action: {exc}", no_update, no_update

    @app.callback(Output("knowledge-result", "children"), Input("knowledge-submit", "n_clicks"), State("knowledge-query", "value"), State("knowledge-mode", "value"), prevent_initial_call=True)
    def knowledge_search(_, query, mode):
        hits = knowledge.search(query, current_user(store))
        if not hits:
            return html.Div([html.Div("No permitted operating document matched that query.", className="empty-state")])
        if mode == "claude":
            result = knowledge.answer_with_claude(query, hits)
            return html.Div([html.Div("Claude answer mode · optional provider", className="mode-label"), html.P(result["message"]), html.Div(f"Usage metadata: {result['usage'] or 'not available'}", className="section-subtitle"), html.Div([f"Source: {doc.source}" for doc in hits], className="citation")])
        return html.Div([html.Div("Local search", className="mode-label"), html.H3(hits[0].title), html.P(hits[0].body), html.Div([f"Source: {doc.source}" for doc in hits], className="citation")])

    return app


app = make_app()
server = app.server

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
