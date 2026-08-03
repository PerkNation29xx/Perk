from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app


client = TestClient(app)


def test_home_routes_share_the_shared_theme_build() -> None:
    dark = client.get("/")
    light = client.get("/white/", follow_redirects=False)

    assert dark.status_code == 200
    assert light.status_code == 308
    assert light.headers["location"] == "/"
    assert 'data-theme="dark"' in dark.text
    assert _PUBLIC_BUILD_ID in dark.text
    assert "Find your next favorite place, experience, or local story." in dark.text
    assert dark.text.index("Find your next favorite place, experience, or local story.") < dark.text.index(
        "Hollywood Sports packages are live."
    )


def test_white_asset_aliases_use_the_shared_runtime_files() -> None:
    for filename in ("app.js", "styles.css"):
        shared = client.get(f"/assets/{filename}")
        legacy_alias = client.get(f"/white/assets/{filename}", follow_redirects=False)

        assert shared.status_code == 200
        assert legacy_alias.status_code == 308
        assert legacy_alias.headers["location"] == f"/assets/{filename}"


def test_theme_toggle_changes_css_state_without_navigation() -> None:
    script = client.get("/assets/app.js").text
    styles = client.get("/assets/styles.css").text

    assert 'document.documentElement.dataset.theme = resolved' in script
    assert 'window.location.href = nextHref' not in script
    assert 'window.location.replace(href)' not in script
    assert 'html[data-theme="light"]' in styles
    assert "--surface-rgb" in styles


def test_secondary_static_routes_share_content() -> None:
    dark = client.get("/members")
    light = client.get("/white/members", follow_redirects=False)

    assert dark.status_code == 200
    assert light.status_code == 308
    assert light.headers["location"] == "/members"
