from harvestops.ui import empty_state, metric_card, page_heading, section_heading


def test_shared_ui_components_render_consistent_class_names():
    components = [
        page_heading("Kicker", "Title", "Description", "Refresh"),
        metric_card("Volume", "8", " loads", "Seeded"),
        section_heading("Section", "Subtitle"),
        empty_state("Nothing here"),
    ]
    rendered = " ".join(str(component) for component in components)
    assert "page-heading" in rendered
    assert "metric-card" in rendered
    assert "section-heading" in rendered
    assert "empty-state" in rendered
