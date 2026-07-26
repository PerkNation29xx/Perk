import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app
from app.services.ai_assistant import _public_nfl_schedule_live_query_response


ROOT = Path(__file__).resolve().parents[1]
NFL_DATA = ROOT / "app" / "web" / "home_portal" / "assets" / "nfl-2026-schedules.json"
EVENTS_SCRIPT = ROOT / "app" / "web" / "home_portal" / "assets" / "events.js"
APP_SCRIPT = ROOT / "app" / "web" / "home_portal" / "assets" / "app.js"
STYLES = ROOT / "app" / "web" / "home_portal" / "assets" / "styles.css"


def _data() -> dict:
    return json.loads(NFL_DATA.read_text(encoding="utf-8"))


def test_nfl_data_has_all_32_teams_conferences_and_announced_weeks() -> None:
    teams = _data()["teams"]

    assert len(teams) == 32
    assert sum(team["conference"] == "AFC" for team in teams) == 16
    assert sum(team["conference"] == "NFC" for team in teams) == 16
    assert {team["division"] for team in teams} == {"East", "North", "South", "West"}
    assert [team["name"] for team in teams if team["featured"]] == [
        "Los Angeles Chargers",
        "Los Angeles Rams",
        "San Francisco 49ers",
    ]
    assert all(len(team["schedule"]) == 18 for team in teams)
    assert all({game["week"] for game in team["schedule"]} == set(range(1, 19)) for team in teams)
    assert all(team["officialUrl"].startswith("https://www.nfl.com/schedules/2026/by-team/") for team in teams)


def test_every_nfl_team_has_a_public_article_route() -> None:
    client = TestClient(app)

    for team in _data()["teams"]:
        response = client.get(f"/events/{team['slug']}")
        assert response.status_code == 200, team["name"]
        assert _PUBLIC_BUILD_ID in response.text
        assert f"<title>{team['name']} 2026 Season Opener and Full Schedule | Perk Nation</title>" in response.text
        assert f'<link rel="canonical" href="/events/{team["slug"]}" />' in response.text
        assert "See all 18 weeks" in response.text
        white_response = client.get(f"/white/events/{team['slug']}")
        assert white_response.status_code == 200, team["name"]
        assert f'<link rel="canonical" href="/events/{team["slug"]}" />' in white_response.text


def test_events_hub_renders_featured_and_expandable_conference_guide() -> None:
    script = EVENTS_SCRIPT.read_text(encoding="utf-8")

    assert "3 featured · 32 teams" in script
    assert "Explore all 32 NFL teams" in script
    assert 'conferenceMarkup("AFC")' in script
    assert 'conferenceMarkup("NFC")' in script
    assert "nflDivisionGrid" in script
    assert 'scope="col">Venue' in script


def test_ai_answers_team_week_matchup_and_conference_questions() -> None:
    bills = _public_nfl_schedule_live_query_response(
        "what time do the bills play in week 1",
        "home_local_guide",
    )
    assert bills
    assert "Buffalo Bills" in bills
    assert "Week 1" in bills
    assert "Houston Texans" in bills
    assert "10:00 AM PT" in bills
    assert "/events/buffalo-bills-season-opener-2026" in bills

    matchup = _public_nfl_schedule_live_query_response(
        "when do the bills play the chargers",
        "home_local_guide",
    )
    assert matchup
    assert "Week 3" in matchup
    assert "Los Angeles Chargers" in matchup

    nfc = _public_nfl_schedule_live_query_response("show me all nfc teams", "public")
    assert nfc
    assert "NFC teams" in nfc
    assert "Philadelphia Eagles" in nfc
    assert "San Francisco 49ers" in nfc


def test_assistant_is_one_hover_and_focus_rail_on_every_public_page() -> None:
    client = TestClient(app)
    app_script = APP_SCRIPT.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    for route in ("/", "/events", "/events/buffalo-bills-season-opener-2026", "/white/events"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("data-home-ai-form") == 1
        assert response.text.count('data-ai-rail aria-label=') == 1
        assert "What time do the Bills play in Week 1?" in response.text

    assert 'rail.classList.toggle("is-open"' in app_script
    assert ".aiDiscoverySection:hover" in styles
    assert ".aiDiscoverySection:focus-within" in styles
    assert "position: fixed" in styles
