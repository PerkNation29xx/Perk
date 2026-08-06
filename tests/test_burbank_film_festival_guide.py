from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "burbank-film-festival-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "burbank-film-festival-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_burbank_film_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Burbank film week has more than 120 screenings" in html
    assert 'dateModified": "2026-07-30"' in html
    assert html.count("<h2>") >= 12
    for expected in (
        "7 ranked priorities",
        "AMC Burbank 16",
        "filmmaker Q&amp;A",
        "industry panel",
        "closing gala",
        "Best for:",
        "/directory?city=Burbank",
        "/articles/dine-la-city-burbank-2026",
        "/articles/southern-california-august-events-2026",
        "https://www.burbankfilmfest.org/",
        "https://burbankinternationalfilmfestival.eventive.org/schedule",
        "https://visitburbank.com/events/burbank-international-film-festival-2/",
        "https://www.burbankca.gov/web/community-development/public-parking",
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


def test_burbank_film_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in (
        "/articles/burbank-film-festival-2026-guide",
        "/white/articles/burbank-film-festival-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "7 ranked priorities" in response.text

    image = client.get("/assets/articles/burbank-film-festival-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("New July 30 · Burbank") == 1
        assert "Burbank film week has 120-plus screenings. Start with the right few." in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "<loc>https://perknation.app/articles/burbank-film-festival-2026-guide</loc>" in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/white/articles/burbank-film-festival-2026-guide</loc>" not in root_sitemap.text


def test_burbank_film_guide_is_cross_linked_and_available_to_public_answers() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert 'dateModified": "2026-08-06"' in august_html
    assert "/articles/burbank-film-festival-2026-guide" in august_html

    answer = _public_review_live_query_response(
        "What current Burbank film festival guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "Burbank International Film Festival 2026 practical guide" in answer
    assert "/articles/burbank-film-festival-2026-guide" in answer
    assert "Warped Tour" not in answer
    assert "Mount Westmore" not in answer
