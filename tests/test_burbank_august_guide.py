from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "burbank-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "burbank-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_burbank_guide_has_rankings_sources_and_directory_context() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert 'dateModified": "2026-08-28"' in html
    for expected in (
        "The Fab Four at Starlight Bowl",
        "Magnolia Park Food Truck Fridays",
        "Dine LA's Burbank finale",
        "Best for:",
        "Practical review:",
        "968 Burbank listings",
        "/directory?city=Burbank",
        "/directory?q=restaurants&amp;city=Burbank",
        "/articles/dine-la-pasadena-2026",
        "/articles/southern-california-august-events-2026",
        "burbankca.gov",
        "visitburbank.com",
        "discoverlosangeles.com/dinela",
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


def test_burbank_guide_route_image_and_homepage_cards_are_live() -> None:
    client = TestClient(app)

    assert IMAGE.exists()
    assert IMAGE.stat().st_size > 50_000
    for route in (
        "/articles/burbank-august-2026-guide",
        "/white/articles/burbank-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "Burbank's final August weekend" in response.text

    image = client.get("/assets/articles/burbank-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/jpeg")

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated August 28 · Burbank") == 1
        assert response.text.count("/articles/burbank-august-2026-guide") >= 1


def test_burbank_guide_is_in_roundup_sitemap_and_public_answers() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/burbank-august-2026-guide" in august_html
    assert "Burbank's final August weekend" in august_html

    client = TestClient(app)
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert sitemap.text.count("<loc>https://perknation.app/articles/burbank-august-2026-guide</loc>") == 1
    assert "https://perknation.app/white/articles/burbank-august-2026-guide" not in sitemap.text

    answer = _public_review_live_query_response(
        "What current Burbank events are covered?",
        "home_local_guide",
    )
    assert answer
    assert "rescheduled Fab Four concert" in answer
    assert "Magnolia Park Food Truck Fridays" in answer
    assert "/articles/burbank-august-2026-guide" in answer
    assert "968 Burbank directory listings" in answer
