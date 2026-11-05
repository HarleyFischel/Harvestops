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
from flask import Flask, jsonify, make_response, redirect, request, session

from .auth import EntraAuth
from .config import Settings, get_settings
from .domain import User
from .services import DomainError, InMemoryStore
from .sql_store import SqlServerStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("harvestops")


def current_user(store: InMemoryStore):
    username = session.get("username")
    return store.users.get(username) if username else None


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


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
    return html.Div([
        dcc.Location(id="url"),
        dcc.Store(id="active-user", data="demo.viewer"),
        html.Header([
            html.Div([html.Div("HARVESTOPS", className="brand"), html.Div("Produce operations control plane", className="tagline")], className="brand-lockup"),
            html.Div([html.Span("SYNTHETIC DATA · DEMO MODE", className="demo-pill"), html.Span(id="user-label", className="user-label")], className="header-meta"),
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
                html.Div("DEMO ACCOUNT", className="eyebrow side-space"),
                dcc.Dropdown(id="role-switch", options=[{"label": u.display_name, "value": u.username} for u in store.users.values()], value="demo.viewer", clearable=False),
                html.Div("Role changes are development-only and enforced server-side.", className="side-note"),
            ], className="sidebar"),
            html.Section(id="page-content", className="content"),
        ], className="shell"),
        html.Footer("UTC storage · display timezone: " + settings.display_timezone + " · Portfolio application with synthetic data", className="footer"),
    ], className="app-shell")


def metric_card(label, value, suffix="", note=""):
    return html.Div([html.Div(label, className="metric-label"), html.Div([html.Span(value, className="metric-value"), html.Span(suffix, className="metric-suffix")]), html.Div(note, className="metric-note")], className="metric-card")


def dashboard_view(store: InMemoryStore):
    options = store.filter_options()
    return html.Div([
        html.Div([html.Div([html.Div("Operations dashboard", className="page-kicker"), html.H1("Move today’s harvest with confidence."), html.P("A single operational view of volume, service, fill, and labor signals.")]), html.Div("Last refreshed · synthetic seed", className="refresh-note")], className="page-heading"),
        html.Div([html.Div([html.Label("Customer"), dcc.Dropdown(id="filter-customer", options=[{"label": "All customers", "value": "All"}] + [{"label": x, "value": x} for x in options["customer"]], value="All")], className="filter-control"), html.Div([html.Label("Product"), dcc.Dropdown(id="filter-product", options=[{"label": "All products", "value": "All"}] + [{"label": x, "value": x} for x in options["product"]], value="All")], className="filter-control"), html.Div([html.Label("Facility"), dcc.Dropdown(id="filter-facility", options=[{"label": "All facilities", "value": "All"}] + [{"label": x, "value": x} for x in options["facility"]], value="All")], className="filter-control")], className="filter-row"),
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
        AgGrid(id="shipment-grid", columnDefs=[{"field": x, "headerName": x.replace("_", " ").title()} for x in ["shipment_id", "customer", "product", "facility", "carrier", "planned_departure", "actual_departure", "ordered_qty", "shipped_qty", "freight_cost", "status", "version"]], rowData=[], defaultColDef={"sortable": True, "filter": True, "resizable": True}, dashGridOptions={"animateRows": False, "pagination": False}, className="ag-theme-alpine", style={"height": "430px", "width": "100%"}),
        html.Div(id="shipment-page-info", className="section-subtitle"),
        dcc.Upload(id="shipment-import-upload", children=html.Div("Upload shipment CSV"), className="upload-control", multiple=False),
        html.Div([html.Label("Shipment ID"), dcc.Input(id="status-shipment-id", placeholder="SHP-1001"), html.Label("New status"), dcc.Dropdown(id="status-value", options=[{"label": x, "value": x} for x in ["Scheduled", "In Transit", "Delivered", "Exception", "Cancelled"]], clearable=False), html.Label("Expected version"), dcc.Input(id="status-version", type="number", value=1), html.Button("Apply status", id="apply-status", className="button primary")], className="inline-form"),
    ])


def purchasing_view():
    return html.Div([
        html.Div([html.Div([html.Div("Controls & approvals", className="page-kicker"), html.H1("Purchasing approvals"), html.P("Create requests, submit for review, and preserve the decision trail.")])], className="page-heading"),
        html.Div([html.Div([html.Label("Facility"), dcc.Input(id="purchase-facility", value="Salinas")], className="filter-control"), html.Div([html.Label("Product"), dcc.Input(id="purchase-product", value="Romaine Hearts")], className="filter-control"), html.Div([html.Label("Quantity"), dcc.Input(id="purchase-qty", type="number", value=100)], className="filter-control"), html.Div([html.Label("Unit cost"), dcc.Input(id="purchase-cost", type="number", value=2.5)], className="filter-control"), html.Button("Create request", id="create-purchase", className="button primary")], className="inline-form"),
        html.Div(id="purchase-alert", className="alert"), html.Div(id="purchase-list", className="purchase-list"), html.Div(id="purchase-history", className="purchase-history"),
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
    server = Flask(__name__)
    server.secret_key = settings.secret_key
    server.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=settings.app_env == "production", PERMANENT_SESSION_LIFETIME=1800)

    @server.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
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
        roles = {"viewer"} | {role_map[r] for r in claims.get("roles", []) if r in role_map}
        store.users[principal] = User(principal, claims.get("name", principal), roles)
        session["username"] = principal
        session.permanent = True
        return jsonify({"username": principal, "roles": sorted(roles), "identity": "entra"})

    @server.post("/auth/logout")
    def logout():
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
            writer.writerow([row["shipment_id"], row["customer"], row["product"], row["status"], "'" + str(row["freight_cost"])])
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv"
        response.headers["Content-Disposition"] = "attachment; filename=harvestops-shipments.csv"
        return response

    @server.post("/api/shipments/import")
    @require_role(store, "operator", "admin")
    def import_shipments():
        try:
            expected = session.get("csrf_token")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not secrets.compare_digest(supplied, expected):
                return jsonify({"error": "CSRF token required"}), 403
            actor = current_user(store)
            text = request.get_data(as_text=True)
            if not text or len(text) > 2_000_000:
                return jsonify({"error": "CSV body is required and must be under 2 MB"}), 400
            return jsonify(store.import_shipments(text, actor)), 201
        except (DomainError, PermissionError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    app = Dash(__name__, server=server, title="HarvestOps", assets_folder=str(Path(__file__).parent / "assets"), suppress_callback_exceptions=True)
    app.layout = build_layout(store, settings)

    @app.callback(Output("page-content", "children"), Input("nav", "value"))
    def switch_page(page):
        return {"dashboard": dashboard_view(store), "shipments": shipments_view(store), "purchasing": purchasing_view(), "knowledge": knowledge_view()}.get(page, dashboard_view(store))

    @app.callback(Output("user-label", "children"), Input("role-switch", "value"))
    def role_label(username):
        return f"{store.users[username].display_name} · {', '.join(sorted(store.users[username].roles))}"

    @app.callback(Output("active-user", "data"), Input("role-switch", "value"))
    def switch_user(username):
        if settings.demo_mode:
            session["username"] = username
        return username

    @app.callback(Output("kpi-row", "children"), Output("volume-chart", "figure"), Output("service-chart", "figure"), Output("exceptions-table", "children"), Input("filter-customer", "value"), Input("filter-product", "value"), Input("filter-facility", "value"))
    def refresh_dashboard(customer, product, facility):
        filters = {"customer": customer, "product": product, "facility": facility}
        k = store.kpis(filters)
        cards = [metric_card("Shipment volume", str(k["shipment_volume"]), " loads", "Seeded records in scope"), metric_card("On-time rate", f"{k['on_time_rate']:.1f}", "%", "Closed shipments only"), metric_card("Fill rate", f"{k['fill_rate']:.1f}", "%", "Shipped ÷ ordered"), metric_card("Freight cost", f"${k['freight_cost']:,.0f}", "", "Planned + actual loads"), metric_card("Production output", f"{k['production_output']:,}", " units", "Seeded output proxy"), metric_card("Labor productivity", f"{k['labor_productivity']:,.1f}", " units/load", "Output ÷ loads")]
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
        data = [{"shipment_id": r.shipment_id, "customer": r.customer, "product": r.product, "facility": r.facility, "carrier": r.carrier, "planned_departure": r.planned_departure_utc.isoformat(), "actual_departure": r.actual_departure_utc.isoformat() if r.actual_departure_utc else "", "ordered_qty": str(r.ordered_qty), "shipped_qty": str(r.shipped_qty), "freight_cost": str(r.freight_cost), "status": r.status, "version": r.version} for r in rows]
        return data, f"Page {min(page, max_page)} of {max_page} · {total} matching shipments"

    @app.callback(Output("shipment-alert", "children"), Input("apply-status", "n_clicks"), State("status-shipment-id", "value"), State("status-value", "value"), State("status-version", "value"), prevent_initial_call=True)
    def apply_status(_, shipment_id, new_status, version):
        try:
            user = current_user(store)
            updated = store.change_status(shipment_id, new_status, user, int(version))
            return f"Updated {updated.shipment_id} to {updated.status}; version {updated.version}."
        except (DomainError, PermissionError, TypeError, ValueError) as exc:
            return f"Could not apply change: {exc}"

    @app.callback(Output("shipment-alert", "children", allow_duplicate=True), Input("shipment-import-upload", "contents"), State("shipment-import-upload", "filename"), prevent_initial_call=True)
    def import_from_upload(contents, filename):
        try:
            import base64
            user = current_user(store)
            if not user or not user.roles.intersection({"operator", "admin"}):
                raise PermissionError("Operator role required")
            _, encoded = contents.split(",", 1)
            result = store.import_shipments(base64.b64decode(encoded).decode("utf-8"), user)
            return f"Imported {result['applied']} records from {filename or 'upload'}; {len(result['errors'])} rejected."
        except (DomainError, PermissionError, ValueError, UnicodeDecodeError) as exc:
            return f"Import failed: {exc}"

    @app.callback(Output("purchase-alert", "children"), Output("purchase-list", "children"), Output("purchase-history", "children"), Input("create-purchase", "n_clicks"), Input("submit-purchase", "n_clicks"), Input("record-decision", "n_clicks"), State("purchase-facility", "value"), State("purchase-product", "value"), State("purchase-qty", "value"), State("purchase-cost", "value"), State("submit-request-id", "value"), State("submit-version", "value"), State("decision-request-id", "value"), State("decision-value", "value"), State("decision-comment", "value"), State("decision-version", "value"), prevent_initial_call=True)
    def purchase_action(create_click, submit_click, decision_click, facility, product, qty, cost, submit_id, submit_version, req_id, decision, comment, version):
        from dash import ctx
        try:
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
            cards = [html.Div([html.Div(r.request_id, className="purchase-id"), html.Div(f"{r.facility} · {r.requester}"), html.Div(f"${r.total:,.2f} · {r.status}", className="purchase-status")], className="purchase-card") for r in store.list_purchases()]
            history = [html.Div(f"{event.occurred_utc.isoformat()} · {event.actor} · {event.action} · {event.entity_id}", className="section-subtitle") for event in store.purchase_history()]
            return message, cards, history
        except (DomainError, PermissionError, TypeError, ValueError) as exc:
            return f"Could not complete action: {exc}", no_update, no_update

    @app.callback(Output("knowledge-result", "children"), Input("knowledge-submit", "n_clicks"), State("knowledge-query", "value"), State("knowledge-mode", "value"), prevent_initial_call=True)
    def knowledge_search(_, query, mode):
        docs = [{"title": "KPI definitions", "body": "Fill rate is shipped quantity divided by ordered quantity. On-time rate is on-time departures divided by closed shipments.", "source": "knowledge/kpi-definitions.md"}, {"title": "Dock exception playbook", "body": "For a late departure, confirm appointment, carrier arrival, and quantity before changing status or escalating.", "source": "knowledge/dock-operations.md"}, {"title": "Purchase controls", "body": "A requester cannot approve their own request. Approval decisions require the pending state and current version.", "source": "knowledge/purchasing.md"}]
        q = (query or "").lower()
        hits = [d for d in docs if any(term in (d["title"] + " " + d["body"]).lower() for term in q.split())]
        if not hits:
            hits = docs[:1]
        label = "Local search" if mode == "search" else "Claude answer mode (optional; provider call not configured in demo)"
        return html.Div([html.Div(label, className="mode-label"), html.H3(hits[0]["title"]), html.P(hits[0]["body"]), html.Div([f"Source: {d['source']}" for d in hits], className="citation")])

    return app


app = make_app()
server = app.server

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
