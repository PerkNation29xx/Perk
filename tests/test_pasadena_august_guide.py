from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "pasadena-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "pasadena-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_pasadena_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Pasadena has six current August plans" in html
    assert 'dateModified": "2026-08-19"' in html
    assert html.count("<h2>") >= 10
    for expected in (
        "6 ranked plans",
        "563 Pasadena listings",
        "Pasadena POPS",
        "Friday Nights at The Gamble House",
        "America's Got Talent",
        "Power Morphicon",
        "Best for:",
        "/directory?city=Pasadena",
        "/articles/dine-la-city-pasadena-2026",
        "/articles/southern-california-august-events-2026",
        "https://www.visitpasadena.com/events/summer-guide/",
    ):
        assert expected in html

    for forbidden in (
        "Rose Bowl Flea Market",
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_pasadena_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in (
        "/articles/pasadena-august-2026-guide",
        "/white/articles/pasadena-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "6 ranked plans" in response.text

    image = client.get("/assets/articles/pasadena-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated August 19 · Pasadena") == 1
        assert "Pasadena has six current August plans worth putting on the calendar." in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "<loc>https://perknation.app/articles/pasadena-august-2026-guide</loc>" in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/white/articles/pasadena-august-2026-guide</loc>" not in root_sitemap.text


def test_pasadena_guide_is_cross_linked_and_available_to_public_answers() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/pasadena-august-2026-guide" in august_html

    answer = _public_review_live_query_response(
        "what current Pasadena August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks six August plans" in answer
    assert "/articles/pasadena-august-2026-guide" in answer
    assert "Rose Bowl Flea Market" not in answer
    assert "Long Beach" not in answer
