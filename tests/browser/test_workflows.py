import os
import re

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
        assert page.locator("#ship-product").count() == 1
        assert page.locator("#ship-facility").count() == 1
        assert page.get_by_text("Upload shipment CSV").count() == 1
        assert page.get_by_role("button", name="Apply status").count() == 1
        next_page = page.get_by_role("button", name="Next page")
        next_page.wait_for()
        assert next_page.is_enabled()
        next_page.click()
        page.get_by_text("Page 2 of 2", exact=True).wait_for()
        page.locator("#shipment-lookup-id").fill("shp-1001")
        page.get_by_role("button", name="Find shipment").click()
        page.get_by_text("SHP-1001", exact=True).last.wait_for()
        assert page.get_by_text("FreshMart Northeast", exact=True).count() >= 1
        page.locator("#ship-product").click()
        page.get_by_text("Romaine Hearts", exact=True).first.click()
        page.get_by_text(re.compile("2 matching shipments")).wait_for()
        page.locator("label").filter(has_text="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        assert page.get_by_role("button", name="Create request").count() == 1
        assert page.get_by_role("button", name="Submit for approval").count() == 1
        assert page.get_by_role("button", name="Record decision").count() == 1
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_demo_user_can_change_shipment_and_complete_purchase_approval():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")

        def login_demo(username):
            token = page.evaluate(
                """async () => (await fetch('/api/csrf')).json().then(payload => payload.csrf_token)"""
            )
            status = page.evaluate(
                """async ({username, token}) => (await fetch('/auth/demo', {method: 'POST', headers: {'content-type': 'application/json', 'X-CSRF-Token': token}, body: JSON.stringify({username})})).status""",
                {"username": username, "token": token},
            )
            assert status == 200
            page.reload(wait_until="networkidle")
            page.locator("#csrf-status").get_by_text("ready").wait_for()

        login_demo("demo.operator")
        page.locator("label").filter(has_text="Dock & shipment board").click()
        page.get_by_role("heading", name="Dock & shipment board").wait_for()
        shipment = page.evaluate("""async () => (await fetch('/api/shipments/SHP-1004')).json()""")
        assert shipment["shipment_id"] == "SHP-1004"
        next_status = {
            "Scheduled": "In Transit",
            "In Transit": "Exception",
            "Exception": "In Transit",
        }.get(shipment["status"])
        assert next_status is not None
        page.locator("#status-shipment-id").fill("SHP-1004")
        page.locator("#status-value").click()
        page.get_by_text(next_status, exact=True).last.click()
        page.locator("#status-version").fill(str(shipment["version"]))
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Apply status").click()
        page.wait_for_function(
            "() => document.querySelector('#shipment-alert')?.textContent.trim().length > 0"
        )
        assert f"Updated SHP-1004 to {next_status}" in page.locator("#shipment-alert").inner_text()

        page.locator("label").filter(has_text="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        assert page.get_by_text("PR-1002", exact=True).count() >= 1
        page.locator("#purchase-qty").fill("4")
        page.locator("#purchase-cost").fill("3.25")
        page.get_by_role("button", name="Create request").click()
        alert = page.locator("#purchase-alert")
        alert.get_by_text(re.compile("Created PR-")).wait_for()
        request_id = re.search(r"PR-\d+", alert.inner_text()).group(0)
        page.locator("#submit-request-id").fill(request_id)
        page.locator("#submit-version").fill("1")
        page.get_by_role("button", name="Submit for approval").click()
        alert.get_by_text(re.compile("Submitted " + request_id)).wait_for()

        login_demo("demo.approver")
        page.locator("label").filter(has_text="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        page.locator("#decision-request-id").fill(request_id)
        page.locator("#decision-value").click()
        page.get_by_text("Approved", exact=True).last.click()
        page.locator("#decision-comment").fill("Verified by browser smoke test")
        page.locator("#decision-version").fill("2")
        page.get_by_role("button", name="Record decision").click()
        alert.get_by_text(re.compile("approved decision")).wait_for()
        assert (
            page.locator("#purchase-history").get_by_text(re.compile("purchase.approved")).count()
            >= 1
        )
        browser.close()
