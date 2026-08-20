from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "orange-county-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "orange-county-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"
HOME = ROOT / "app" / "web" / "home_portal" / "index.html"
WHITE_HOME = ROOT / "app" / "web" / "home_portal_white" / "index.html"


def test_orange_county_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Orange County has seven current late-summer plans" in html
    assert 'dateModified": "2026-08-20"' in html
    assert html.count("<h2>") >= 11
    for expected in (
        "7 ranked plans",
        "Laguna Beach arts season",
        "OC Parks concerts and movies",
        "Huntington Beach surf and nature",
        "Sea Country Festival",
        "La Habra Corn Festival",
        "TheFitExpo Anaheim",
        "Orange International Street Fair",
        "Best for:",
        "/directory?city=Orange",
        "/articles/southern-california-august-events-2026",
        "https://www.ocparks.com/",
        "https://www.cityoflagunaniguel.org/",
        "https://www.thefitexpo.com/",
    ):
        assert expected in html
    assert "OC Fair" not in html
    assert "D23" not in html

    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_orange_county_routes_image_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/orange-county-august-2026-guide",
        "/white/articles/orange-county-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "7 ranked plans" in response.text

    image = client.get("/assets/articles/orange-county-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    home_html = HOME.read_text(encoding="utf-8")
    white_html = WHITE_HOME.read_text(encoding="utf-8")
    assert home_html.count("Updated August 20 · Orange County") == 1
    assert white_html.count("Updated August 20 · Orange County") == 1
    assert "Orange County has seven current late-summer plans worth building a day around." in home_html
    assert "Orange County has seven current late-summer plans worth building a day around." in white_html
    assert "/white/articles/orange-county-august-2026-guide" in white_html

    root_sitemap = client.get("/sitemap.xml")
    assert "<loc>https://perknation.app/articles/orange-county-august-2026-guide</loc>" in root_sitemap.text


def test_orange_county_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/orange-county-august-2026-guide" in august_html
    assert 'dateModified": "2026-08-20"' in august_html

    answer = _public_review_live_query_response(
        "what current Orange County August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks seven late-summer plans" in answer
    assert "/articles/orange-county-august-2026-guide" in answer
    assert "Pasadena" not in answer
