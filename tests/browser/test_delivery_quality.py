import os

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


BASE_URL = os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050")


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_delivery_quality_page_renders_traceability_and_safe_states():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(7000)
        page.goto(f"{BASE_URL}/?page=delivery", wait_until="networkidle")
        page.get_by_role("heading", name="Delivery & Quality").wait_for()
        assert page.get_by_text("GitHub remains authoritative", exact=False).count() == 1
        assert page.get_by_text("OPS-002", exact=True).count() == 1
        assert (
            page.get_by_text(
                "No formal release or deployment history is recorded yet.", exact=False
            ).count()
            == 1
        )
        assert page.get_by_text("server-only", exact=False).count() == 0
        page.locator("#delivery-requirement-search").fill("OPS-002")
        page.wait_for_function(
            "() => !document.querySelector('#delivery-requirements-table')?.textContent.includes('PUR-001')"
        )
        assert (
            page.locator("#delivery-requirements-table").get_by_text("OPS-002", exact=True).count()
            == 1
        )
        assert (
            page.locator("#delivery-requirements-table").get_by_text("PUR-001", exact=True).count()
            == 0
        )
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_delivery_quality_page_has_no_document_overflow_on_tablet():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (1440, 1024, 834, 768):
            page = browser.new_page(viewport={"width": width, "height": 1024})
            page.goto(f"{BASE_URL}/?page=delivery", wait_until="networkidle")
            page.get_by_role("heading", name="Delivery & Quality").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            assert page.locator(".evidence-table-panel .table-scroll").count() == 1
            page.close()
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_allowlisted_document_view_is_readable_after_authenticated_navigation():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/?page=delivery", wait_until="networkidle")
        page.get_by_role("link", name="Architecture").click()
        page.get_by_role("heading", name="Architecture").wait_for()
        assert page.get_by_text("← Delivery & Quality", exact=False).count() == 1
        assert page.locator("pre").count() == 1
        browser.close()
