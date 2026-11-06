"""Small, dependency-light Dash components used across the application."""

from dash import html


def page_heading(kicker: str, title: str, description: str, refresh_note: str | None = None):
    """Return the consistent screen heading used by operational pages."""
    heading = [
        html.Div([html.Div(kicker, className="page-kicker"), html.H1(title), html.P(description)])
    ]
    if refresh_note:
        heading.append(html.Div(refresh_note, className="refresh-note"))
    return html.Div(heading, className="page-heading")


def metric_card(label: str, value: str, suffix: str = "", note: str = ""):
    """Return a KPI card with an accessible text hierarchy."""
    return html.Div(
        [
            html.Div(label, className="metric-label"),
            html.Div(
                [
                    html.Span(value, className="metric-value"),
                    html.Span(suffix, className="metric-suffix"),
                ]
            ),
            html.Div(note, className="metric-note"),
        ],
        className="metric-card",
    )


def section_heading(title: str, subtitle: str | None = None):
    """Return a reusable section heading for panels and queues."""
    children = [html.Div(title, className="section-title")]
    if subtitle:
        children.append(html.Div(subtitle, className="section-subtitle"))
    return html.Div(children, className="section-heading")


def empty_state(message: str):
    """Return the standard readable empty state."""
    return html.Div(message, className="empty-state")
