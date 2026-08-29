from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "dine-la-pasadena-2026.html"


def test_dine_la_launch_copy_is_current_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert 'dateModified": "2026-08-28"' in html
    assert "Dine LA's final day is organized by Southern California city." in html
    assert "495 restaurants across 54 Southern California cities" in html
    assert "Compare menus, reserve, add nearby plans" in html
    for forbidden in (
        "SEO city pages",
        "search intent",
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_dine_la_launch_is_archived_off_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in ("/articles/dine-la-pasadena-2026", "/white/articles/dine-la-pasadena-2026"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Dine LA's final day" in response.text

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Final day · August 28" not in response.text
        assert "Dine LA's final day is organized by Southern California city." not in response.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "dine-la-pasadena-2026" not in sitemap.text
    assert "dine-la-city-" not in sitemap.text
