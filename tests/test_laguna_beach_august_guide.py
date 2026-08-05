from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "laguna-beach-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "laguna-beach-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_laguna_beach_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Laguna Beach has nine late-summer arts plans" in html
    assert 'dateModified": "2026-08-05"' in html
    assert html.count("<h2>") >= 13
    for expected in (
        "9 ranked plans",
        "24 Laguna Beach listings",
        "Pageant of the Masters",
        "Sawdust Art Festival",
        "Passport to the Arts",
        "First Thursdays Art Walk",
        "Festival of Arts Fine Art Show",
        "Laguna Art-A-Fair",
        "Laguna Art Museum",
        "Music in the Park",
        "Music at the Promenade",
        "Best for:",
        "/directory?city=Laguna%20Beach",
        "/articles/southern-california-august-events-2026",
        "https://www.foapom.com/",
        "https://www.lagunabeachcity.net/",
    ):
        assert expected in html

    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_laguna_beach_routes_image_homepage_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/laguna-beach-august-2026-guide",
        "/white/articles/laguna-beach-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "9 ranked plans" in response.text

    image = client.get("/assets/articles/laguna-beach-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("New August 5 · Laguna Beach") == 1
        assert "Laguna Beach has nine late-summer arts plans worth the trip." in response.text
        assert "Updated August 5" in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert "<loc>https://perknation.app/articles/laguna-beach-august-2026-guide</loc>" in root_sitemap.text


def test_laguna_beach_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/laguna-beach-august-2026-guide" in august_html
    assert "Laguna Beach summer arts season" in august_html
    assert 'dateModified": "2026-08-05"' in august_html

    answer = _public_review_live_query_response(
        "what current Laguna Beach August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks nine late-summer arts plans" in answer
    assert "/articles/laguna-beach-august-2026-guide" in answer
    assert "Santa Monica" not in answer
