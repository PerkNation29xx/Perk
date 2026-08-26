from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "arcadia-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "arcadia-august-2026-guide.jpg"
AUGUST_GUIDE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_arcadia_guide_is_substantial_source_backed_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Arcadia's August finale pairs Broadway music with a garden picnic" in html
    assert 'dateModified": "2026-08-26"' in html
    assert html.count("<h2>") >= 6
    for expected in (
        "1 marquee outing",
        "40 Arcadia listings",
        "Pasadena POPS",
        "Best for:",
        "/directory?city=Arcadia",
        "/articles/dine-la-city-arcadia-2026",
        "/articles/southern-california-august-events-2026",
        "https://arboretum.org/",
    ):
        assert expected in html
    assert "626 Night Market" not in html

    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_arcadia_routes_image_homepage_cards_and_sitemaps() -> None:
    client = TestClient(app)

    for route in (
        "/articles/arcadia-august-2026-guide",
        "/white/articles/arcadia-august-2026-guide",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "1 marquee outing" in response.text

    image = client.get("/assets/articles/arcadia-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated August 26 · Arcadia") == 1
        assert "Arcadia's August finale pairs Broadway music with a garden picnic." in response.text
        assert "Updated August 26" in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "<loc>https://perknation.app/articles/arcadia-august-2026-guide</loc>" in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/white/articles/arcadia-august-2026-guide</loc>" not in root_sitemap.text


def test_arcadia_guide_replaces_expired_roundup_copy_and_scopes_public_answer() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/arcadia-august-2026-guide" in august_html
    assert "626 Night Market in Arcadia" not in august_html
    assert "Thursday evenings through August at the City Hall Lawn" not in august_html
    assert 'dateModified": "2026-08-26"' in august_html
    assert "National Night Out" not in ARTICLE.read_text(encoding="utf-8")

    answer = _public_review_live_query_response(
        "what current Arcadia August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "centers one marquee August outing" in answer
    assert "August 7" not in answer
    assert "/articles/arcadia-august-2026-guide" in answer
    assert "Glendale" not in answer
