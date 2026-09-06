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

    assert "Two Laguna Beach summer art festivals close tonight" in html
    assert 'dateModified": "2026-09-06"' in html
    assert html.count("<h2>") >= 7
    for expected in (
        "2 ranked plans",
        "24 Laguna Beach listings",
        "Sawdust Art Festival",
        "Laguna Art-A-Fair",
        "Best for:",
        "/directory?city=Laguna%20Beach",
        "/articles/southern-california-september-events-2026",
        "https://www.lagunabeachcity.net/",
    ):
        assert expected in html
    assert "Music in the Park" not in html

    for forbidden in (
        "Pageant of the Masters",
        "Passport to the Arts",
        "Festival of Arts Fine Art Show",
        "Music at the Promenade",
        "First Thursdays Art Walk",
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
        assert "2 ranked plans" in response.text

    image = client.get("/assets/articles/laguna-beach-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Final day September 6 · Laguna Beach") == 1
        assert "Laguna Beach's summer festival season closes tonight." in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert "<loc>https://perknation.app/articles/laguna-beach-august-2026-guide</loc>" in root_sitemap.text


def test_laguna_beach_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/laguna-beach-august-2026-guide" in august_html
    assert "Laguna Beach summer arts season" in august_html
    assert 'dateModified": "2026-08-28"' in august_html

    answer = _public_review_live_query_response(
        "what current Laguna Beach August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "covers the final September 6 day" in answer
    assert "Sawdust Art Festival" in answer
    assert "Laguna Art-A-Fair" in answer
    assert "Pageant of the Masters" not in answer
    assert "First Thursdays Art Walk" not in answer
    assert "/articles/laguna-beach-august-2026-guide" in answer
    assert "Santa Monica" not in answer
