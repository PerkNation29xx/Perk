from pathlib import Path

from fastapi.testclient import TestClient

from app.main import _PUBLIC_BUILD_ID, app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "la-fashion-events-2026.html"
APP_SCRIPT = ROOT / "app" / "web" / "home_portal" / "assets" / "app.js"


def test_global_fashion_guide_has_verified_calendar_rankings_and_access_notes() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "2026 Fashion Week calendar: LA, New York, Miami and the world" in html
    assert 'dateModified": "2026-10-07"' in html
    assert html.count('class="fashionRankCard') == 8
    assert html.count("<tr><td>") == 6
    for city, dates in (
        ("New York", "Sep 10–15"),
        ("London", "Sep 17–21"),
        ("Milan", "Sep 22–28"),
        ("Paris", "Sep 28–Oct 6"),
        ("Miami", "Oct 13–17"),
        ("Los Angeles", "Oct 12–15"),
    ):
        assert city in html
        assert dates in html
    assert "Fashion Week is not one public ticket." in html
    assert "Concluded October 6" in html
    assert "Upcoming; credentialed trade access only" in html
    assert "October 30, November 6, 13, and 20" in html
    assert "trade-only" in html
    assert "Best for:" in html
    assert "/directory?q=fashion&amp;city=Los%20Angeles" in html
    assert "For SEO:" not in html
    assert "official listing" not in html.lower()
    assert "generated for this guide" not in html.lower()


def test_fashion_guide_and_homepage_card_are_live_in_both_themes() -> None:
    client = TestClient(app)

    article = client.get("/articles/la-fashion-events-2026")
    assert article.status_code == 200
    assert _PUBLIC_BUILD_ID in article.text
    assert '<footer class="footer">' in article.text
    assert '<link rel="canonical" href="/articles/la-fashion-events-2026" />' in article.text
    assert 'data-ai-category="fashion"' in article.text

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "2026 Fashion Weeks: LA, New York, Miami and the world." in response.text
        assert "Updated October 7 · Fashion calendar" in response.text
        assert "LA Market Week October 12-15" in response.text
        assert "CMC sample sale October 30" in response.text
        assert "Follow New York starting September 10" not in response.text
        assert "Copenhagen, Tokyo" not in response.text
        assert _PUBLIC_BUILD_ID in response.text


def test_fashion_assistant_context_and_questions_cover_global_calendar() -> None:
    answer = _public_review_live_query_response(
        "Which 2026 fashion weeks are coming up?",
        "home_local_guide",
    )
    assert answer
    assert "Los Angeles Market Week" in answer
    assert "Miami" in answer
    assert "CMC's next public sample-sale Friday" in answer
    assert "New York Fashion Week: September 10-15" not in answer
    assert "Paris Fashion Week Womenswear: September 28-October 6" not in answer
    assert "/articles/la-fashion-events-2026" in answer
    assert "review/editorial coverage" not in answer
    assert "listed for review" not in answer

    app_script = APP_SCRIPT.read_text(encoding="utf-8")
    assert "Which 2026 fashion weeks are coming up?" in app_script
    assert "When are New York, Miami, and Paris Fashion Week?" in app_script


def test_fashion_guide_stays_in_primary_sitemap() -> None:
    client = TestClient(app)
    sitemap = client.get("/sitemap.xml")

    assert sitemap.status_code == 200
    assert "<loc>https://perknation.app/articles/la-fashion-events-2026</loc>" in sitemap.text
