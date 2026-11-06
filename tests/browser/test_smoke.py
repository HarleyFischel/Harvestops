import os

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_dashboard_renders():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        assert page.get_by_text("Operations dashboard").count() >= 1
        assert page.get_by_text("SYNTHETIC DATA").count() >= 1
        assert page.get_by_text("Planned departure range").count() == 1
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_mobile_dashboard_renders():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        assert (
            page.get_by_role("heading", name="Move today’s harvest with confidence.").count() == 1
        )
        assert page.get_by_text("SYNTHETIC DATA").count() >= 1
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_tablet_dashboard_renders_with_responsive_content():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 768, "height": 1024})
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        assert (
            page.get_by_role("heading", name="Move today’s harvest with confidence.").count() == 1
        )
        content = page.locator(".content").bounding_box()
        metrics = page.locator(".metric-grid").bounding_box()
        assert content is not None and content["width"] <= 768
        assert metrics is not None and metrics["width"] <= 768
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_keyboard_focus_indicator_is_visible():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        page.locator("label").filter(has_text="Dock & shipment board").click()
        button = page.get_by_role("button", name="Apply status")
        button.wait_for()
        button.focus()
        assert button.evaluate("element => getComputedStyle(element).outlineStyle") == "solid"
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_dashboard_controls_use_compact_dimensions():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        radio = page.locator(".nav-list input[type='radio']").first
        radio_box = radio.bounding_box()
        dropdown_box = page.locator(".filter-control .Select-control").first.bounding_box()
        assert radio_box is not None and radio_box["width"] <= 24 and radio_box["height"] <= 24
        assert dropdown_box is not None and dropdown_box["height"] <= 42
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_navigation_labels_do_not_wrap_at_sidebar_breakpoint():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 800, "height": 900})
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        labels = page.locator(".nav-list label")
        assert labels.count() == 4
        for index in range(labels.count()):
            label = labels.nth(index)
            assert label.evaluate("element => getComputedStyle(element).whiteSpace") == "nowrap"
            assert label.evaluate("element => element.scrollWidth <= element.clientWidth")
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_header_spans_common_ipad_widths_without_horizontal_overflow():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (744, 768, 834, 1024):
            page = browser.new_page(viewport={"width": width, "height": 1024})
            page.goto(
                os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle"
            )
            header = page.locator(".topbar").bounding_box()
            assert header is not None and round(header["width"]) == width
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            page.close()
        browser.close()
