from pathlib import Path

from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app


ROOT = Path(__file__).resolve().parents[1]
EVENTS_DATA = ROOT / "app" / "web" / "home_portal" / "assets" / "events-data.js"
EVENTS_SCRIPT = ROOT / "app" / "web" / "home_portal" / "assets" / "events.js"
STYLES = ROOT / "app" / "web" / "home_portal" / "assets" / "styles.css"
SEASON_OPENER_SLUGS = (
    "chargers-home-opener-2026",
    "49ers-home-opener-2026",
    "rams-home-opener-2026",
)


def _event_block(source: str, slug: str) -> str:
    start = source.index(f'slug: "{slug}"')
    next_event = source.find("\n  {\n    slug:", start + 1)
    return source[start:] if next_event == -1 else source[start:next_event]


def test_each_season_opener_has_all_18_regular_season_weeks() -> None:
    source = EVENTS_DATA.read_text(encoding="utf-8")

    for slug in SEASON_OPENER_SLUGS:
        block = _event_block(source, slug)
        assert 'scheduleTitle: "' in block
        assert "scheduleNote:" in block
        assert block.count('{ week: "') == 18
        assert 'week: "18"' in block


def test_event_articles_render_the_announced_schedule_table() -> None:
    script = EVENTS_SCRIPT.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "function scheduleMarkup(event)" in script
    assert "${scheduleMarkup(event)}" in script
    assert 'scope="col">Week' in script
    assert 'scope="col">Matchup' in script
    assert ".eventScheduleTableWrap" in styles
    assert ".eventScheduleSite.neutral" in styles


def test_season_opener_routes_load_the_new_versioned_assets() -> None:
    client = TestClient(app)

    for slug in SEASON_OPENER_SLUGS:
        response = client.get(f"/events/{slug}")
        assert response.status_code == 200
        assert _PUBLIC_BUILD_ID in response.text


def test_expired_mount_westmore_is_removed_from_current_event_surfaces() -> None:
    source = EVENTS_DATA.read_text(encoding="utf-8")
    assert "mount-westmore-san-jose" not in source

    client = TestClient(app)
    assert client.get("/events/mount-westmore-san-jose").status_code == 404
    assert "mount-westmore-san-jose" not in client.get("/sitemap.xml").text

    for route in ("/", "/white/", "/events"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Mount Westmore" not in response.text
