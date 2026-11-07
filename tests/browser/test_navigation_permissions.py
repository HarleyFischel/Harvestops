import os

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


BASE_URL = os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050")


def switch_demo_user(page, username):
    token = page.evaluate("async () => (await fetch('/api/csrf')).json().then(p => p.csrf_token)")
    status = page.evaluate(
        """async ({username, token}) => (await fetch('/auth/demo', {
            method: 'POST',
            headers: {'content-type': 'application/json', 'X-CSRF-Token': token},
            body: JSON.stringify({username})
        })).status""",
        {"username": username, "token": token},
    )
    assert status == 200
    page.reload(wait_until="networkidle")


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_exception_links_select_first_page_shipments_and_support_back_forward():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(5000)
        page.goto(BASE_URL, wait_until="networkidle")
        page.get_by_role("link", name="SHP-1002").click()
        page.get_by_text("Selected shipment", exact=True).wait_for()
        assert page.locator("#shipment-detail h2").get_by_text("SHP-1002", exact=True).count() == 1
        assert page.locator(".ag-row-selected").get_by_text("SHP-1002").count() == 1
        page.reload(wait_until="networkidle")
        assert page.locator(".ag-row-selected").get_by_text("SHP-1002").count() == 1
        page.go_back(wait_until="networkidle")
        page.get_by_role("heading", name="Run the day from one operational view.").wait_for()
        page.go_forward(wait_until="networkidle")
        page.get_by_text("Selected shipment", exact=True).wait_for()
        assert page.locator(".ag-row-selected").get_by_text("SHP-1002").count() == 1
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_later_page_deep_link_and_missing_shipment_are_safe():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(5000)
        page.goto(f"{BASE_URL}/?page=shipments&shipment=SHP-1006", wait_until="networkidle")
        page.get_by_text("Selected shipment", exact=True).wait_for()
        assert page.get_by_text("Page 2 of 2", exact=True).count() == 1
        assert page.locator(".ag-row-selected").get_by_text("SHP-1006").count() == 1
        page.goto(f"{BASE_URL}/?page=shipments&shipment=SHP-9999", wait_until="networkidle")
        page.get_by_text("That shipment is no longer available.").wait_for()
        assert page.locator(".ag-row-selected").count() == 0
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_demo_permissions_refresh_for_viewer_operator_and_approver():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(5000)
        page.goto(f"{BASE_URL}/?page=shipments", wait_until="networkidle")
        assert page.locator("#export-csv").count() == 0
        assert page.locator("#shipment-import-upload").count() == 0
        page.locator("#shipment-grid .ag-center-cols-container .ag-row").first.click()
        page.get_by_text(
            "Status changes are restricted to operators and administrators."
        ).wait_for()
        assert page.locator("#apply-status").count() == 0
        assert page.locator("#create-purchase").count() == 0
        page.get_by_role("button", name="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        assert page.locator("#create-purchase").count() == 1
        assert page.locator("#record-selected-decision").is_disabled()

        switch_demo_user(page, "demo.operator")
        page.get_by_role("button", name="Dock & shipment board").click()
        page.get_by_role("heading", name="Dock & shipment board").wait_for()
        assert page.locator("#export-csv").count() == 1
        assert page.locator("#shipment-import-upload").count() == 1

        switch_demo_user(page, "demo.approver")
        page.get_by_role("button", name="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        page.locator(".queue-row").filter(has_text="PR-1002").click()
        page.wait_for_function(
            "() => !document.querySelector('#record-selected-decision')?.disabled"
        )
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_date_formatting_and_filter_layout_at_supported_widths():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (1440, 1024, 834, 768):
            page = browser.new_page(viewport={"width": width, "height": 1024})
            page.goto(BASE_URL, wait_until="networkidle")
            assert page.locator(".DateRangePickerInput").count() == 1
            assert page.locator(".DateRangePickerInput").bounding_box()["height"] <= 44
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            page.goto(f"{BASE_URL}/?page=shipments&shipment=SHP-1002", wait_until="networkidle")
            assert (
                page.get_by_text(
                    "Times shown in America/New_York; timestamps are stored in UTC."
                ).count()
                == 1
            )
            assert page.get_by_text("Jan 8, 2026").count() >= 1
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            page.close()
        browser.close()
