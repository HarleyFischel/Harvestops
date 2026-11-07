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
        page.set_default_timeout(5000)
        page.goto(os.getenv("HARVESTOPS_URL", "http://127.0.0.1:8050"), wait_until="networkidle")
        page.locator(".nav-list .nav-item").filter(has_text="Dock & shipment board").click()
        page.get_by_role("heading", name="Dock & shipment board").wait_for()
        page.locator("#shipment-grid").wait_for()
        assert page.locator("#ship-product").count() == 1
        assert page.locator("#ship-facility").count() == 1
        assert (
            page.get_by_text(
                "Shipment import is restricted to operators and administrators."
            ).count()
            == 1
        )
        page.locator("#shipment-grid .ag-center-cols-container .ag-row").first.click()
        page.get_by_text("Selected shipment", exact=True).wait_for()
        assert page.locator("#apply-status").count() == 0
        assert (
            page.get_by_text(
                "Status changes are restricted to operators and administrators."
            ).count()
            == 1
        )
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
        token = page.evaluate(
            """async () => (await fetch('/api/csrf')).json().then(payload => payload.csrf_token)"""
        )
        assert (
            page.evaluate(
                """async ({token}) => (await fetch('/auth/demo', {method: 'POST', headers: {'content-type': 'application/json', 'X-CSRF-Token': token}, body: JSON.stringify({username: 'demo.operator'})})).status""",
                {"token": token},
            )
            == 200
        )
        page.reload(wait_until="networkidle")
        page.locator(".nav-list .nav-item").filter(has_text="Dock & shipment board").click()
        page.get_by_role("heading", name="Dock & shipment board").wait_for()
        assert page.locator("#export-csv").count() == 1
        assert page.get_by_text("Upload shipment CSV").count() == 1
        page.locator(".nav-list .nav-item").filter(has_text="Purchasing approvals").click()
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        assert page.locator("#create-purchase").count() == 1
        page.get_by_role("button", name=re.compile("PR-1002")).click()
        assert page.locator("#submit-selected-purchase").count() == 1
        assert page.locator("#record-selected-decision").count() == 1
        browser.close()


@pytest.mark.skipif(sync_playwright is None, reason="Playwright is not installed")
def test_demo_user_can_change_shipment_and_complete_purchase_approval():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(5000)
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
        page.locator(".nav-list .nav-item").filter(has_text="Dock & shipment board").click()
        page.get_by_role("heading", name="Dock & shipment board").wait_for()
        shipment = page.evaluate("""async () => (await fetch('/api/shipments/SHP-1004')).json()""")
        assert shipment["shipment_id"] == "SHP-1004"
        next_status = {
            "Scheduled": "In Transit",
            "In Transit": "Exception",
            "Exception": "In Transit",
        }.get(shipment["status"])
        assert next_status is not None
        page.locator("#shipment-grid .ag-center-cols-container .ag-row").filter(
            has_text="SHP-1004"
        ).click()
        page.get_by_text("Selected shipment", exact=True).wait_for()
        page.locator("#selected-status").click()
        page.get_by_text(next_status, exact=True).last.click()
        page.on("dialog", lambda dialog: dialog.accept())
        page.locator("#shipment-detail .button.primary").click()
        page.wait_for_timeout(1200)
        assert re.search(
            r"Updated SHP-1004 to (In Transit|Exception|Cancelled)",
            page.locator("#shipment-alert").inner_text(),
        )
        page.wait_for_function(
            "() => document.querySelector('#shipment-grid')?.getAttribute('data-dash-is-loading') !== 'true'"
        )

        # Start the approval flow from a clean page state so the prior shipment
        # refresh cannot race the dynamic purchasing layout.
        page.goto(
            f"{os.getenv('HARVESTOPS_URL', 'http://127.0.0.1:8050')}/?page=purchasing",
            wait_until="networkidle",
        )
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        assert page.get_by_text("PR-1002", exact=True).count() >= 1
        page.locator("#purchase-qty").fill("4")
        page.locator("#purchase-cost").fill("3.25")
        page.locator("#create-purchase").click()
        alert = page.locator("#purchase-alert")
        alert.get_by_text(re.compile("Created PR-")).wait_for()
        page.wait_for_function(
            "() => document.querySelector('#purchase-list')?.getAttribute('data-dash-is-loading') !== 'true'"
        )
        request_id = re.search(r"PR-[A-Z0-9]+", alert.inner_text()).group(0)
        page.get_by_role("button", name=re.compile(request_id)).wait_for()
        page.get_by_role("button", name=re.compile(request_id)).click()
        page.wait_for_function(
            "() => !document.querySelector('#submit-selected-purchase')?.disabled"
        )
        page.locator("#submit-selected-purchase").click()
        alert.get_by_text(re.compile("Submitted " + request_id)).wait_for()

        login_demo("demo.approver")
        page.goto(
            f"{os.getenv('HARVESTOPS_URL', 'http://127.0.0.1:8050')}/?page=purchasing",
            wait_until="networkidle",
        )
        page.get_by_role("heading", name="Purchasing approvals").wait_for()
        page.locator(".queue-row").filter(has_text=request_id).wait_for()
        page.locator(".queue-row").filter(has_text=request_id).click()
        page.wait_for_function(
            "() => !document.querySelector('#record-selected-decision')?.disabled"
        )
        page.locator("#selected-decision").click()
        page.get_by_text("Approved", exact=True).last.click()
        page.locator("#purchase-decision-comment").fill("Verified by browser smoke test")
        page.locator("#record-selected-decision").click()
        alert.get_by_text(re.compile("approved decision")).wait_for()
        assert (
            page.locator("#purchase-history").get_by_text(re.compile("purchase.approved")).count()
            >= 1
        )
        browser.close()
