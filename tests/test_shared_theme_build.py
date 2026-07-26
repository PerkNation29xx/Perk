import re

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _without_theme_marker(html: str) -> str:
    return re.sub(r'\sdata-theme="(?:light|dark)"', "", html, count=1)


def test_home_routes_share_the_category_hierarchy_build() -> None:
    dark = client.get("/")
    light = client.get("/white/")

    assert dark.status_code == 200
    assert light.status_code == 200
    assert 'data-theme="dark"' in dark.text
    assert 'data-theme="light"' in light.text
    assert "20260715-category-hierarchy" in dark.text
    assert "Find your next favorite place, experience, or local story." in dark.text
    assert dark.text.index("Find your next favorite place, experience, or local story.") < dark.text.index(
        "Hollywood Sports packages are live."
    )
    assert _without_theme_marker(dark.text) == _without_theme_marker(light.text)


def test_white_asset_aliases_use_the_shared_runtime_files() -> None:
    for filename in ("app.js", "styles.css"):
        shared = client.get(f"/assets/{filename}")
        legacy_alias = client.get(f"/white/assets/{filename}")

        assert shared.status_code == 200
        assert legacy_alias.status_code == 200
        assert shared.content == legacy_alias.content


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
    light = client.get("/white/members")

    assert dark.status_code == 200
    assert light.status_code == 200
    assert _without_theme_marker(dark.text) == _without_theme_marker(light.text)
