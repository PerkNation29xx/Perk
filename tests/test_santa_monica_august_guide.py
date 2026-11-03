from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "santa-monica-august-2026-guide.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "santa-monica-august-2026-guide.jpg"


def test_santa_monica_guide_is_current_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Santa Monica has six current plans" in html
    assert 'dateModified": "2026-11-03"' in html
    assert "6 ranked plans" in html
    for expected in (
        "Renegade Craft",
        "renegadecraft.com/event/los-angeles-winter",
        "Held in Trust",
        "4v0naphs6kscmrssg0n2ejrsce/202611041100",
        "Swiss Winter Village",
        "santamonica.com/event/swiss-winter-village",
        "Santa Monica Veterans Day ceremony",
        "annual-nov-11-veterans-day-ceremony",
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
        "Cinema by the Sea",
        "Practical Magic",
        "Hocus Pocus",
        "October 24 Pico Farmers Market",
        "Party on the Pier",
        "Woodlawn Cemetery",
        "Santa Monica Pier Día de los Muertos",
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
        assert "6 ranked plans" in response.text

    image = client.get("/assets/articles/santa-monica-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated November 3 · Santa Monica" in response.text
        assert "Six current Santa Monica plans, ranked." in response.text
        assert "Renegade Craft" in response.text
        assert "Held in Trust" in response.text
        assert "Swiss Winter Village" in response.text
        assert "Veterans Day ceremony" in response.text
        assert "LA Times Food Bowl" not in response.text
        assert "Ghosts of the Miles" not in response.text
        assert "Practical Magic" not in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert "<loc>https://perknation.app/articles/santa-monica-august-2026-guide</loc>" in root_sitemap.text


def test_santa_monica_public_answer_is_current_and_scoped() -> None:
    answer = _public_review_live_query_response(
        "What current Santa Monica events are covered?",
        "home_local_guide",
    )

    assert answer
    assert "ranks six November and flexible long-run plans" in answer
    assert "Renegade Craft" in answer
    assert "Held in Trust" in answer
    assert "Swiss Winter Village" in answer
    assert "free Veterans Day ceremony" in answer
    assert "Portraits: Faces and Waves" in answer
    assert "Pico farmers market" in answer
    assert "LA Times Food Bowl" not in answer
    assert "Scott Silven" not in answer
    assert "Ghosts of the Miles" not in answer
    assert "Practical Magic" not in answer
    assert "Woodlawn Cemetery" not in answer
    assert "Día de los Muertos celebration" not in answer
    assert "/articles/santa-monica-august-2026-guide" in answer
