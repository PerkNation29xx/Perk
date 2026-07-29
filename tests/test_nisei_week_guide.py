from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "nisei-week-little-tokyo-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "nisei-week-little-tokyo-2026-guide.jpg"


def test_nisei_week_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Nisei Week brings two weekends of Japanese American culture" in html
    assert 'dateModified": "2026-07-29"' in html
    assert html.count("<h2>") >= 11
    for expected in (
        "JANM's Natsumatsuri Family Festival",
        "JACCC's August 15-16 arts weekend",
        "JACCC's August 22-23 Plaza Festival",
        "Little Tokyo Farmers' Market",
        "Parade and street-dance practice",
        "Best for:",
        "/directory?city=Los%20Angeles",
        "/articles/southern-california-august-events-2026",
        "https://niseiweek.org/",
        "https://jaccc.org/events/84th-annual-nisei-week-jaccc/",
        "https://www.janm.org/events/2026-08-15/2026-natsumatsuri-family-festival",
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


def test_nisei_week_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in (
        "/articles/nisei-week-little-tokyo-2026-guide",
        "/white/articles/nisei-week-little-tokyo-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "6 ranked priorities" in response.text

    image = client.get("/assets/articles/nisei-week-little-tokyo-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "New July 29 · Los Angeles" in response.text
        assert "Nisei Week brings two weekends of culture to Little Tokyo." in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml")
    assert "<loc>https://perknation.app/articles/nisei-week-little-tokyo-2026-guide</loc>" in root_sitemap.text
    assert "<loc>https://perknation.app/white/articles/nisei-week-little-tokyo-2026-guide</loc>" in white_sitemap.text


def test_nisei_week_is_available_to_public_review_answers() -> None:
    answer = _public_review_live_query_response(
        "What current Little Tokyo cultural events are covered?",
        "home_local_guide",
    )

    assert answer
    assert "Nisei Week 2026 Little Tokyo guide" in answer
    assert "/articles/nisei-week-little-tokyo-2026-guide" in answer
