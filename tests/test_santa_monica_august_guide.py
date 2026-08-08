from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "santa-monica-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "santa-monica-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_santa_monica_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Santa Monica has seven late-summer plans" in html
    assert 'dateModified": "2026-08-08"' in html
    assert html.count("<h2>") >= 12
    for expected in (
        "7 ranked plans",
        "Art on Ocean",
        "Sunset Swim",
        "Cinema by the Sea",
        "Wellness &amp; Waves",
        "A Talk Through Pier History",
        "Downtown Farmers Market",
        "Ocean Way Festival",
        "Best for:",
        "/articles/dine-la-city-santa-monica-2026",
        "/articles/southern-california-august-events-2026",
        "https://www.santamonica.gov/",
        "https://www.santamonica.com/",
        "https://www.downtownsm.com/",
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


def test_santa_monica_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in (
        "/articles/santa-monica-august-2026-guide",
        "/white/articles/santa-monica-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "7 ranked plans" in response.text

    image = client.get("/assets/articles/santa-monica-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated August 8 · Santa Monica") == 1
        assert "Santa Monica has seven late-summer plans that work from morning through night." in response.text
        assert "Updated August 8" in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "<loc>https://perknation.app/articles/santa-monica-august-2026-guide</loc>" in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/white/articles/santa-monica-august-2026-guide</loc>" not in root_sitemap.text


def test_santa_monica_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/santa-monica-august-2026-guide" in august_html
    assert "Art on Ocean, swims, and movies" in august_html
    assert 'dateModified": "2026-08-08"' in august_html

    answer = _public_review_live_query_response(
        "what current Santa Monica August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks seven late-summer plans" in answer
    assert "August 7" not in answer
    assert "/articles/santa-monica-august-2026-guide" in answer
    assert "Glendale" not in answer
