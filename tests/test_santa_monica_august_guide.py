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

    assert "Santa Monica has nine current October plans" in html
    assert 'dateModified": "2026-10-24"' in html
    assert html.count("<h2>") >= 12
    for expected in (
        "9 ranked plans",
        "LA Times Food Bowl",
        "101-best-restaurants-in-l-a",
        "Scott Silven's <em>Wonders</em>",
        "scott-silven-wonders",
        "Party on the Pier",
        "https://partyonthepier.ucla.edu/",
        "mattel-party-pier",
        "Ghosts of the Miles",
        "https://www.santamonica.com/event/ghosts-of-the-miles/",
        "4t27nkvh7dttp1xfz22csmk9dg/202610241200",
        "free all-ages Festival of Memories",
        "ticketed 16+ Historical Haunt",
        "Pico Walk Loop ribbon cutting",
        "4zcsp3g979tqpvt024j48s6k5v/202610241000",
        "Held in Trust",
        "4m0q8xgfh3dwp01en1ykxsn3m6/202610241600",
        "Cinema by the Sea",
        "cinema-by-the-sea-2/2026-10-31/",
        "Practical Magic",
        "Portraits: Faces and Waves",
        "photography-exhibition-portraits-faces-and-waves-on-display-at-annenberg-community-beach-house-gallery",
        "Pico Farmers Market",
        "Best for:",
        "/directory?city=Santa%20Monica",
        "/articles/southern-california-september-events-2026",
        "https://www.santamonica.com/event/pico-farmers-market/2026-10-24/",
    ):
        assert expected in html
    assert "Locals' Night" not in html
    assert "Punk Night at the Pier" not in html
    assert "Wellness on the Westside" not in html
    assert "Voices of Strength" not in html
    assert "Hispanic Heritage library doubleheader" not in html
    assert "Thai Fest by the Beach" not in html
    assert "dublab Open Air" not in html
    assert "Between Darkness and Dawn" not in html
    assert "Doors Open California" not in html
    assert "Ocean Way" not in html
    assert "Montana Avenue Art Walk" not in html
    assert "Join &amp; Thrive" not in html
    assert "Fire Prevention Week Open House" not in html
    assert "Continuum at Historic Belmar Park" not in html
    assert "airport-to-park master-plan event" not in html
    assert "Carmen simulcast" not in html
    assert "Wellness &amp; Waves" not in html
    assert "Main Street Block Party + Day of the Dog" not in html
    assert "Spooky Splash" not in html

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
        assert "9 ranked plans" in response.text

    image = client.get("/assets/articles/santa-monica-august-2026-guide.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert len(image.content) > 300_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert response.text.count("Updated October 24 · Santa Monica") == 1
        assert "Nine Santa Monica October plans, ranked." in response.text
        assert "Dogtown Locals' Night drive-in" not in response.text
        assert "fire station open house" not in response.text
        assert "LA Times Food Bowl" in response.text
        assert "Scott Silven's <em>Wonders</em>" in response.text
        assert "Main Street Block Party + Day of the Dog" not in response.text
        assert "UCLA's Party on the Pier" in response.text
        assert "Ghosts of the Miles" in response.text
        assert "free Pico Walk Loop ribbon cutting" in response.text
        assert "free <em>Held in Trust</em> City Gallery opening" in response.text
        assert "Cinema by the Sea" in response.text
        assert "Portraits: Faces and Waves" in response.text
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
    assert "ranks nine October plans, including four free options" in answer
    assert "Held in Trust opening at City Gallery" in answer
    assert "Punk Night at the Pier" not in answer
    assert "Voices of Strength" not in answer
    assert "Fire Prevention Week Open House" not in answer
    assert "LA Times Food Bowl" in answer
    assert "Scott Silven's Wonders" in answer
    assert "Main Street Block Party + Day of the Dog" not in answer
    assert "Party on the Pier" in answer
    assert "Spooky Splash" not in answer
    assert "Portraits: Faces and Waves" in answer
    assert "Locals' Night drive-in at Santa Monica Pier" not in answer
    assert "Pico Walk Loop ribbon cutting" in answer
    assert "Ghosts of the Miles" in answer
    assert "Cinema by the Sea" in answer
    assert "Practical Magic" in answer
    assert "free all-ages Festival of Memories" in answer
    assert "ticketed 16+ Historical Haunt" in answer
    assert "Montana Avenue Art Walk" not in answer
    assert "Join & Thrive" not in answer
    assert "Thai Fest by the Beach" not in answer
    assert "August 7" not in answer
    assert "Pier history talk" not in answer
    assert "Hispanic Heritage" not in answer
    assert "dublab Open Air" not in answer
    assert "Doors Open California" not in answer
    assert "has been canceled" not in answer
    assert "/articles/santa-monica-august-2026-guide" in answer
    assert "Glendale" not in answer
