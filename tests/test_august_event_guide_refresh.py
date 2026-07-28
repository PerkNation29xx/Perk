from pathlib import Path

from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_august_guide_has_fifteen_ranked_source_backed_plans() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Fifteen Southern California summer plans" in html
    assert 'dateModified": "2026-07-28"' in html
    for expected in (
        "West Hollywood Summer Sounds",
        "Just Like Heaven in Pasadena",
        "Noah Kahan at the Rose Bowl",
        "Best for:",
        "/articles/dine-la-city-west-hollywood-2026",
        "/directory?city=Pasadena",
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


def test_august_guide_card_is_current_on_both_homepages() -> None:
    client = TestClient(app)

    article = client.get("/articles/southern-california-august-events-2026")
    assert article.status_code == 200
    assert _PUBLIC_BUILD_ID in article.text

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated July 28" in response.text
        assert "Fifteen Southern California summer plans, ranked." in response.text
        assert _PUBLIC_BUILD_ID in response.text


def test_august_guide_stays_in_sitemaps_and_public_ai_context() -> None:
    client = TestClient(app)

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml")
    assert root_sitemap.status_code == 200
    assert white_sitemap.status_code == 200
    assert "<loc>https://perknation.app/articles/southern-california-august-events-2026</loc>" in root_sitemap.text
    assert "<loc>https://perknation.app/white/articles/southern-california-august-events-2026</loc>" in white_sitemap.text

    answer = _public_review_live_query_response(
        "What current events are covered in Southern California?",
        "home_local_guide",
    )
    assert answer
    assert "Fifteen Southern California summer plans" in answer
    assert "/articles/southern-california-august-events-2026" in answer
