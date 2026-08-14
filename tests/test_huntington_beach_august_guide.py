from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "huntington-beach-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "huntington-beach-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_huntington_beach_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Huntington Beach has six late-August plans" in html
    assert 'dateModified": "2026-08-12"' in html
    assert "remaining August dates are August 18 and 25" in html
    assert "remaining August dates are August 11" not in html
    assert html.count("<h2>") >= 11
    for expected in (
        "6 ranked plans",
        "43 Huntington Beach listings",
        "Life Rolls On",
        "Huntington Beach Pier Swim",
        "Bolsa Chica Grunion Runs",
        "WSL50",
        "Surf City Nights",
        "Junior Rangers",
        "Litter Getters",
        "Best for:",
        "/directory?city=Huntington%20Beach",
        "/articles/southern-california-august-events-2026",
        "https://liferollson.org/huntingtonbeach",
        "https://www.surfcityusa.com/",
        "https://www.parks.ca.gov/",
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


def test_huntington_beach_routes_image_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/huntington-beach-august-2026-guide",
        "/white/articles/huntington-beach-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "6 ranked plans" in response.text

    image = client.get("/assets/articles/huntington-beach-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated August 12 · Huntington Beach") == 1
        assert "Huntington Beach has six late-August plans that go beyond a beach day." in response.text
        assert "Updated August 12" in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert "<loc>https://perknation.app/articles/huntington-beach-august-2026-guide</loc>" in root_sitemap.text


def test_huntington_beach_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/huntington-beach-august-2026-guide" in august_html
    assert "Huntington Beach late-August surf, swim, and nature" in august_html
    assert 'dateModified": "2026-08-14"' in august_html

    answer = _public_review_live_query_response(
        "what current Huntington Beach August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks six coastal plans" in answer
    assert "Barefoot Ball" not in answer
    assert "/articles/huntington-beach-august-2026-guide" in answer
    assert "Laguna Beach" not in answer
