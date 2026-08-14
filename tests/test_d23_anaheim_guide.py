from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "d23-anaheim-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "d23-anaheim-2026-guide.jpg"


def test_d23_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "D23's convention weekend is active now" in html
    assert 'dateModified": "2026-08-14"' in html
    assert "Sunday D23 Fan Pass and Sunday Afternoon Only Fan Pass" in html
    assert "August 7-10 assignment window have ended" in html
    assert "valid activated badge" in html
    assert "overnight queuing is not available" in html
    assert html.count("<h2>") >= 9
    for expected in (
        "Afternoon Only Fan Pass",
        "The Ultimate Disney Fan Event",
        "Capturing Life, Creating Character at Muzeo",
        "4 ranked priorities",
        "Best for:",
        "/directory?city=Anaheim",
        "/articles/southern-california-august-events-2026",
    ):
        assert expected in html
    assert "Angel Stadium" not in html
    assert "D23 Day at Disneyland Resort" not in html
    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_d23_guide_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in ("/articles/d23-anaheim-2026-guide", "/white/articles/d23-anaheim-2026-guide"):
        response = client.get(route)
        assert response.status_code == 200
        assert "eight-part" not in response.text.lower()

    image = client.get("/assets/articles/d23-anaheim-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated August 14 · Anaheim" in response.text
        assert "D23's convention weekend is active now, with four plans worth prioritizing." in response.text
        assert "/articles/d23-anaheim-2026-guide" in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "<loc>https://perknation.app/articles/d23-anaheim-2026-guide</loc>" in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/white/articles/d23-anaheim-2026-guide</loc>" not in root_sitemap.text


def test_d23_guide_is_available_to_public_review_answers() -> None:
    answer = _public_review_live_query_response(
        "What current Anaheim fan events are covered?",
        "home_local_guide",
    )

    assert answer
    assert "D23 Anaheim guide" in answer
    assert "Sunday D23 Fan Pass" in answer
    assert "reservation-assignment window has ended" in answer
    assert "Ultimate Disney Fan Event is active August 14-16" in answer
    assert "Angel Stadium" not in answer
    assert "/articles/d23-anaheim-2026-guide" in answer
    assert "KCON" not in answer
    assert "Pasadena" not in answer
