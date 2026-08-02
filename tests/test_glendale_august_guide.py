from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "glendale-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "glendale-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_glendale_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Glendale has nine August plans" in html
    assert 'dateModified": "2026-08-02"' in html
    assert html.count("<h2>") >= 13
    for expected in (
        "9 ranked plans",
        "100 Glendale listings",
        "Night Sky Adventures",
        "Summer Concerts in the Park",
        "Wander the Wilderness Bus",
        "Classic Film Under the Stars",
        "Glendale Outdoors!",
        "Nature's Teamwork",
        "National Night Out",
        "Wilderness Workday",
        "Montrose Harvest Market",
        "Best for:",
        "/directory?city=Glendale",
        "/articles/southern-california-august-events-2026",
        "https://www.glendaleca.gov/",
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


def test_glendale_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in (
        "/articles/glendale-august-2026-guide",
        "/white/articles/glendale-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "9 ranked plans" in response.text

    image = client.get("/assets/articles/glendale-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("New August 2 · Glendale") == 1
        assert "Glendale has nine August plans that make the foothills feel close." in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml")
    assert "<loc>https://perknation.app/articles/glendale-august-2026-guide</loc>" in root_sitemap.text
    assert "<loc>https://perknation.app/white/articles/glendale-august-2026-guide</loc>" in white_sitemap.text


def test_glendale_guide_is_cross_linked_and_available_to_public_answers() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/glendale-august-2026-guide" in august_html

    answer = _public_review_live_query_response(
        "what current Glendale August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks nine August plans" in answer
    assert "/articles/glendale-august-2026-guide" in answer
    assert "Pasadena" not in answer
