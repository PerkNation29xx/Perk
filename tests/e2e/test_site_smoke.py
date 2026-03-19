from __future__ import annotations

from playwright.sync_api import Page, expect


def test_home_nav_and_footer_links(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/", wait_until="domcontentloaded")

    expect(page.locator('header a[href="/members"]').first).to_be_visible()
    expect(page.locator('header a[href="/merchants"]').first).to_be_visible()
    expect(page.locator('header a[href="/how-it-works"]').first).to_be_visible()
    expect(page.locator('header a[href="/contact-us"]').first).to_be_visible()
    expect(page.locator('header a[href="/faq"]').first).to_be_visible()

    for href in [
        "/members",
        "/merchants",
        "/how-it-works",
        "/contact-us",
        "/faq",
        "/privacy-policy",
        "/terms-of-use",
        "/merchant-terms",
        "/login",
        "/create-account",
    ]:
        resp = page.request.get(f"{base_url}{href}")
        assert resp.ok, f"Expected {href} to load, got {resp.status}"


def test_contact_form_validation_and_success(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/contact-us", wait_until="domcontentloaded")

    is_valid = page.locator('form[data-form="contact"]').evaluate("form => form.reportValidity()")
    assert is_valid is False

    page.locator('input[name="name"]').fill("Playwright QA")
    page.locator('input[name="email"]').fill("playwright-contact@example.com")
    page.locator('textarea[name="inquiry"]').fill("Smoke test contact submission.")
    page.get_by_role("button", name="Send Message").click()

    expect(page.locator("[data-toast]")).to_contain_text("Submitted securely. Reference #")


def test_signed_out_portals_hide_dashboard_sections(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/user", wait_until="domcontentloaded")
    expect(page.locator("#authCard")).to_be_visible()
    assert page.locator("#appSection").is_hidden()

    page.goto(f"{base_url}/merchant", wait_until="domcontentloaded")
    expect(page.locator("#loginCard")).to_be_visible()
    assert page.locator("#portalSection").is_hidden()


def test_admin_portal_exposes_message_box_and_private_message_route(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/admin", wait_until="domcontentloaded")
    expect(page.locator('.navitem[data-view="messageBox"]')).to_be_visible()

    response = page.request.get(f"{base_url}/v1/ai/messages")
    assert response.status == 401


def test_legacy_route_redirects(page: Page, base_url: str) -> None:
    response = page.request.get(f"{base_url}/index.html", max_redirects=0)
    assert response.status in (307, 308)
    assert response.headers.get("location") == "/"

    response = page.request.get(f"{base_url}/login.html", max_redirects=0)
    assert response.status in (307, 308)
    assert response.headers.get("location") == "/login"

    response = page.request.get(f"{base_url}/create-account.html", max_redirects=0)
    assert response.status in (307, 308)
    assert response.headers.get("location") == "/create-account"

    response = page.request.get(f"{base_url}/guests.html", max_redirects=0)
    assert response.status in (307, 308)
    assert response.headers.get("location") == "/members"
