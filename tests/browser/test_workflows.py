import os

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_shipment_and_purchasing_workflow_surfaces_render():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        page.locator("label").filter(has_text="Dock & shipment board").click()
        page.get_by_role("heading", name="Dock & shipment board").wait_for()
        page.locator("#shipment-grid").wait_for()
        assert page.get_by_text("Upload shipment CSV").count() == 1
        assert page.get_by_role("button", name="Apply status").count() == 1
        page.locator("label").filter(has_text="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        assert page.get_by_role("button", name="Create request").count() == 1
        assert page.get_by_role("button", name="Submit for approval").count() == 1
        assert page.get_by_role("button", name="Record decision").count() == 1
        browser.close()
