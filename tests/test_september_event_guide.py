from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-september-events-2026.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "southern-california-september-events-2026.png"


def test_september_guide_is_substantial_ranked_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Twenty-two Southern California September plans" in html
    assert 'dateModified": "2026-09-05"' in html
    assert html.count("<h2") >= 24
    for expected in (
        "Orange International Street Fair",
        "Long Beach Greek Festival",
        "Long Beach Comic Con",
        "https://longbeachcomiccon.com/",
        "Fiesta Hermosa",
        "BlizzCon in Anaheim",
        "Pasadena ARTWalk",
        "Pasadena Chalk Festival",
        "Ocean Way Festival",
        "Lucas Museum opening in Los Angeles",
        "https://lucasmuseum.org/about/tickets",
        "/directory?q=restaurants&amp;city=Los%20Angeles",
        "Southern California Open in Glendale",
        "Burbank Career Transitions Expo",
        "Arcadia Health Fair",
        "Taste of Arcadia",
        "https://tasteofarcadia.com/",
        "Arcadia Mid-Autumn Moon Festival",
        "mooncake making",
        'id="arcadia-moon-festival"',
        "Americana in the Park",
        "Design West Hollywood",
        "Long Beach Burger Week",
        "Orange County Burger Week",
        "https://burgerweeklb.com/",
        "https://burgerweek.com/",
        "https://www.visitwesthollywood.com/events/design-west-hollywood/",
        "Best for:",
        "/directory?city=Burbank",
        "/directory?city=Pasadena",
        "/directory?city=Long%20Beach",
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


def test_september_guide_routes_image_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/southern-california-september-events-2026",
        "/white/articles/southern-california-september-events-2026",
    ):
        response = client.get(route)
        assert response.status_code == 200

    image = client.get("/assets/articles/southern-california-september-events-2026.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated September 5 · September guide" in response.text
        assert "Twenty-two Southern California September plans, ranked." in response.text
        assert "Long Beach Comic Con" in response.text
        assert "Taste of Arcadia" in response.text
        assert "the Lucas Museum opening" in response.text
        assert "Dine LA's final day is organized" not in response.text
        assert "Fourteen Southern California summer plans, ranked." not in response.text
        assert "Orange International Street Fair opens Labor Day weekend" in response.text
        assert "Arcadia's August finale pairs Broadway music with a garden picnic." not in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert root_sitemap.status_code == 200
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/articles/southern-california-september-events-2026</loc>" in root_sitemap.text


def test_september_guide_is_current_in_public_review_answers() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Southern California?",
        "home_local_guide",
    )

    assert answer
    assert "Twenty-two Southern California September plans" in answer
    assert "Long Beach Comic Con" in answer
    assert "Taste of Arcadia" in answer
    assert "Mid-Autumn Moon Festival" in answer
    assert "Lucas Museum" in answer
    assert "/articles/southern-california-september-events-2026" in answer
    assert "Dine LA 2026 city guides" not in answer
