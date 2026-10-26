from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "santa-monica-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "santa-monica-august-2026-guide.jpg"


def test_santa_monica_guide_is_current_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Santa Monica has five current plans" in html
    assert 'dateModified": "2026-10-26"' in html
    assert "5 ranked plans" in html
    for expected in (
        "Día de los Muertos at Woodlawn Cemetery",
        "4qs9amnfe2p00xgqe88s65zs53/202611011100",
        "Cinema by the Sea",
        "Practical Magic",
        "Santa Monica Pier Día de los Muertos",
        "https://www.santamonicapier.org/diadelosmuertos",
        "Portraits: Faces and Waves",
        "Pico Farmers Market",
        "Best for:",
        "/directory?city=Santa%20Monica",
        "/articles/southern-california-september-events-2026",
    ):
        assert expected in html

    for expired in (
        "LA Times Food Bowl",
        "Scott Silven",
        "Ghosts of the Miles",
        "Pico Walk Loop",
        "Held in Trust",
        "Hocus Pocus",
        "October 24 Pico Farmers Market",
        "Party on the Pier",
    ):
        assert expired not in html

    for forbidden in (
        "Examples from the official listing",
        "editorial image generated",
        "generated for this guide",
        "Measure next",
        "publishing workflow",
        "SEO workflow",
    ):
        assert forbidden.lower() not in html.lower()


def test_santa_monica_routes_homepages_image_and_sitemap() -> None:
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
        assert "Updated October 26 · Santa Monica" in response.text
        assert "Five current Santa Monica plans, ranked." in response.text
        assert "Día de los Muertos at Woodlawn Cemetery" in response.text
        assert "Practical Magic" in response.text
        assert "Santa Monica Pier" in response.text
        assert "LA Times Food Bowl" not in response.text
        assert "Ghosts of the Miles" not in response.text
        assert "Held in Trust" not in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert "<loc>https://perknation.app/articles/santa-monica-august-2026-guide</loc>" in root_sitemap.text


def test_santa_monica_public_answer_is_current_and_scoped() -> None:
    answer = _public_review_live_query_response(
        "What current Santa Monica events are covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks five late-October and early-November plans, including four free options" in answer
    assert "Woodlawn Cemetery" in answer
    assert "Practical Magic" in answer
    assert "Santa Monica Pier's free Día de los Muertos celebration" in answer
    assert "Portraits: Faces and Waves" in answer
    assert "Pico farmers market" in answer
    assert "LA Times Food Bowl" not in answer
    assert "Scott Silven" not in answer
    assert "Ghosts of the Miles" not in answer
    assert "Held in Trust" not in answer
    assert "/articles/santa-monica-august-2026-guide" in answer
