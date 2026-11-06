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
