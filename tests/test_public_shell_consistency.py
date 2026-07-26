import re

from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app


client = TestClient(app)

PUBLIC_ROUTES = (
    "/",
    "/events",
    "/events/chargers-home-opener-2026",
    "/directory",
    "/members",
    "/merchants",
    "/how-it-works",
    "/contact-us",
    "/faq",
    "/login",
    "/create-account",
    "/privacy-policy",
    "/terms-of-use",
    "/articles/southern-california-august-events-2026",
    "/articles/dine-la-city-los-angeles-2026",
    "/white/",
    "/white/events",
    "/white/directory",
    "/white/members",
    "/white/login",
)


def _header(html: str) -> str:
    match = re.search(
        r'<header\b[^>]*class="header"[^>]*>.*?</header>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match
    return match.group(0)


def test_all_public_routes_share_one_header_and_build() -> None:
    expected_header = None

    for route in PUBLIC_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route
        assert f"/assets/styles.css?v={_PUBLIC_BUILD_ID}" in response.text, route
        assert f"/assets/app.js?v={_PUBLIC_BUILD_ID}" in response.text, route
        assert "20260302b" not in response.text, route
        assert "directory20260726" not in response.text, route

        header = _header(response.text)
        assert header.count("Explore categories") == 1, route
        assert 'href="/events"' in header, route
        assert 'href="/directory"' in header, route
        assert 'href="/members"' in header, route
        assert 'href="/merchants"' in header, route
        assert 'href="/how-it-works"' in header, route
        assert 'href="/contact-us"' in header, route
        assert 'href="/faq"' in header, route
        assert 'href="/#wellness-beauty"' in header, route
        assert 'href="/#crystal-jewelry"' in header, route

        if expected_header is None:
            expected_header = header
        assert header == expected_header, route


def test_every_public_css_and_javascript_asset_uses_the_same_build() -> None:
    response = client.get("/login")
    assert response.status_code == 200

    local_assets = re.findall(
        r'(?:href|src)=["\'](/assets/[^"\']+\.(?:css|js)(?:\?[^"\']*)?)["\']',
        response.text,
        flags=re.IGNORECASE,
    )
    assert local_assets
    assert all(asset.endswith(f"?v={_PUBLIC_BUILD_ID}") for asset in local_assets)


def test_build_endpoint_is_the_authoritative_public_build() -> None:
    response = client.get("/web/build")

    assert response.status_code == 200
    assert response.json() == {
        "label": f"Build {_PUBLIC_BUILD_ID}",
        "id": _PUBLIC_BUILD_ID,
    }


def test_internal_dashboards_do_not_receive_the_public_shell() -> None:
    response = client.get("/admin")

    assert response.status_code == 200
    assert "Explore categories" not in response.text
