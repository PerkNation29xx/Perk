from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "south-pasadena-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "south-pasadena-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_south_pasadena_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "South Pasadena has five August plans" in html
    assert 'dateModified": "2026-08-19"' in html
    assert html.count("<h2>") >= 9
    for expected in (
        "5 ranked plans",
        "97 South Pasadena listings",
        "South Pasadena Farmers Market",
        "Open Mic on Mission",
        "Broadway on Mission",
        "Eat! Shop! Enjoy! South Pasadena Crawl",
        "LEGO Free Play",
        "Best for:",
        "/directory?city=South%20Pasadena",
        "/articles/dine-la-city-south-pasadena-2026",
        "/articles/southern-california-august-events-2026",
        "https://www.southpasadenaca.gov/",
        "https://southpasadena.net/",
    ):
        assert expected in html
    assert "New Romantics" not in html

    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_south_pasadena_routes_image_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/south-pasadena-august-2026-guide",
        "/white/articles/south-pasadena-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "5 ranked plans" in response.text

    image = client.get("/assets/articles/south-pasadena-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated August 19 · South Pasadena") == 1
        assert "South Pasadena has five August plans that make a small city feel full." in response.text
        assert "New July 30 · Burbank" not in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert root_sitemap.text.count(
        "<loc>https://perknation.app/articles/south-pasadena-august-2026-guide</loc>"
    ) == 1


def test_south_pasadena_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/south-pasadena-august-2026-guide" in august_html
    assert "South Pasadena crawl, market, and performance nights" in august_html

    answer = _public_review_live_query_response(
        "what current South Pasadena August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks five local plans" in answer
    assert "/articles/south-pasadena-august-2026-guide" in answer
    assert "97 South Pasadena directory listings" in answer
    assert "Glendale" not in answer
