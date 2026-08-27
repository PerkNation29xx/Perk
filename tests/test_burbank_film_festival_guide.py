from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "burbank-film-festival-2026-guide.html"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_expired_burbank_film_guide_is_removed_from_public_surfaces() -> None:
    client = TestClient(app)

    assert not ARTICLE.exists()
    for route in (
        "/articles/burbank-film-festival-2026-guide",
        "/white/articles/burbank-film-festival-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 404

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "/articles/burbank-film-festival-2026-guide" not in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "burbank-film-festival-2026-guide" not in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"


def test_burbank_film_guide_stays_retired_while_current_burbank_guide_is_answered() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert 'dateModified": "2026-08-27"' in august_html
    assert "/articles/burbank-film-festival-2026-guide" not in august_html

    answer = _public_review_live_query_response(
        "What current Burbank film festival guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "rescheduled Fab Four concert" in answer
    assert "/articles/burbank-august-2026-guide" in answer
    assert "/articles/burbank-film-festival-2026-guide" not in answer
    assert "968 Burbank directory listings" in answer
    assert "Warped Tour" not in answer
    assert "Mount Westmore" not in answer


def test_expired_kcon_event_is_removed_from_homepages_events_and_sitemap() -> None:
    client = TestClient(app)

    for route in ("/events/kcon-la-2026", "/white/events/kcon-la-2026"):
        assert client.get(route).status_code == 404

    for route in ("/", "/white/", "/events", "/white/events"):
        response = client.get(route)
        assert response.status_code == 200
        assert "kcon-la-2026" not in response.text.lower()

    assert "kcon-la-2026" not in client.get("/sitemap.xml").text.lower()
