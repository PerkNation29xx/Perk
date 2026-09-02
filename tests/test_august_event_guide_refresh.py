from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-august-events-2026.html"


def test_august_guide_has_fourteen_ranked_source_backed_plans() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Fourteen Southern California summer plans" in html
    assert 'dateModified": "2026-08-28"' in html
    for expected in (
        "Kidspace Campout",
        "Dine LA Restaurant Week",
        "TheFitExpo Anaheim",
        "Leimert Park Jazz Festival",
        "/articles/burbank-august-2026-guide",
        "/articles/arcadia-august-2026-guide",
        "/articles/santa-monica-august-2026-guide",
        "/articles/laguna-beach-august-2026-guide",
        "/articles/huntington-beach-august-2026-guide",
        "/articles/south-pasadena-august-2026-guide",
        "Best for:",
        "/directory?city=Pasadena",
    ):
        assert expected in html
    assert "West Hollywood Summer Sounds" not in html
    assert "626 Night Market in Arcadia" not in html
    assert "OC Fair in Costa Mesa" not in html
    assert "Nisei Week in Little Tokyo" not in html
    assert "Naples Island Concert in the Park" not in html
    assert "Surf City Nights" not in html
    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_august_guide_remains_available_but_is_replaced_on_homepages() -> None:
    client = TestClient(app)

    article = client.get("/articles/southern-california-august-events-2026")
    assert article.status_code == 200
    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated August 28" in response.text
        assert "Fourteen Southern California summer plans, ranked." not in response.text
        assert "Eighteen Southern California September plans, ranked." in response.text


def test_august_guide_leaves_sitemaps_and_current_public_ai_context() -> None:
    client = TestClient(app)

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert root_sitemap.status_code == 200
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/articles/southern-california-august-events-2026</loc>" not in root_sitemap.text
    assert "<loc>https://perknation.app/white/articles/southern-california-august-events-2026</loc>" not in root_sitemap.text

    answer = _public_review_live_query_response(
        "What current events are covered in Southern California?",
        "home_local_guide",
    )
    assert answer
    assert "Eighteen Southern California September plans" in answer
    assert "/articles/southern-california-august-events-2026" not in answer
