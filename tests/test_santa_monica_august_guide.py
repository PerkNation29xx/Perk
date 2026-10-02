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

    assert "Santa Monica has five current October plans" in html
    assert 'dateModified": "2026-10-02"' in html
    assert html.count("<h2>") >= 8
    for expected in (
        "5 ranked plans",
        "Montana Avenue Art Walk",
        "https://www.santamonica.com/event/montana-avenue-art-walk-3/",
        "Continuum at Historic Belmar Park",
        "partnership-with-goldenvoice-honors-the-history-of-belmar-and-black-santa-monica",
        "Join &amp; Thrive",
        "santa-monica-public-library-and-bahala-present-join-thrive-film-screening-and-volunteer-fair",
        "Wellness &amp; Waves",
        "Pico Farmers Market",
        "Best for:",
        "/directory?city=Santa%20Monica",
        "/articles/southern-california-september-events-2026",
        "https://www.santamonica.com/event/pico-farmers-market/2026-10-03/",
    ):
        assert expected in html
    assert "Punk Night at the Pier" not in html
    assert "Wellness on the Westside" not in html
    assert "Voices of Strength" not in html
    assert "Hispanic Heritage library doubleheader" not in html
    assert "Thai Fest by the Beach" not in html
    assert "dublab Open Air" not in html
    assert "Between Darkness and Dawn" not in html
    assert "Doors Open California" not in html
    assert "Ocean Way" not in html

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
        assert "5 ranked plans" in response.text

    image = client.get("/assets/articles/santa-monica-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated October 2 · Santa Monica") == 1
        assert "Five free Santa Monica October plans, ranked." in response.text
        assert "Continuum celebration at Historic Belmar Park" in response.text
        assert "Compare Pier Locals' Night" not in response.text
        assert "Ocean Way has been canceled." not in response.text
        assert "Tongva Twilight through September 12" not in response.text
        assert "Updated August 28" in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert "<loc>https://perknation.app/articles/santa-monica-august-2026-guide</loc>" in root_sitemap.text
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/white/articles/santa-monica-august-2026-guide</loc>" not in root_sitemap.text


def test_santa_monica_roundup_link_and_public_answer_are_scoped() -> None:
    august_html = AUGUST_GUIDE.read_text(encoding="utf-8")
    assert "/articles/santa-monica-august-2026-guide" in august_html
    assert "Santa Monica wellness, movies, and park nights" in august_html
    assert 'dateModified": "2026-08-28"' in august_html

    answer = _public_review_live_query_response(
        "what current Santa Monica August events guide is covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks five free October plans" in answer
    assert "Punk Night at the Pier" not in answer
    assert "Voices of Strength" not in answer
    assert "Montana Avenue Art Walk" in answer
    assert "Join & Thrive" in answer
    assert "Continuum at Historic Belmar Park" in answer
    assert "Thai Fest by the Beach" not in answer
    assert "August 7" not in answer
    assert "Pier history talk" not in answer
    assert "Hispanic Heritage" not in answer
    assert "dublab Open Air" not in answer
    assert "Doors Open California" not in answer
    assert "has been canceled" not in answer
    assert "/articles/santa-monica-august-2026-guide" in answer
    assert "Glendale" not in answer
