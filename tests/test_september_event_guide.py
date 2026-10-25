import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-september-events-2026.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "southern-california-september-events-2026.png"


def test_fall_guide_is_current_substantial_and_source_backed() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Forty Southern California fall plans" in html
    assert 'dateModified": "2026-10-25"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 41))

    for expected in (
        "Halloween at Kidspace",
        "Spider Pavilion",
        "Huntington Beach Oktoberfest",
        "Long Beach Open Studio Tour",
        "Bark in the Park",
        'id="marina-spooktacular"',
        "visitmdr.com/events-marina-del-rey/halloween-spooktacular",
        'id="burbank-wild-creatures-walk"',
        "/calendar/-/calendar/event/4397152/0",
        'id="la-plaza-dia-de-los-muertos-family-day"',
        "lapca.org/event/ddlm/",
        'id="santa-monica-party-on-the-pier"',
        "partyonthepier.ucla.edu",
        "MOLAA Día de los Muertos Festival",
        "Día de los Muertos on Olvera Street",
        "Halloween STEMebration",
        "Día de los Muertos at the Arboretum",
        'id="huntington-strange-science"',
        "huntington.org/event/strange-science",
        'id="santa-monica-pier-dia-de-los-muertos"',
        "santamonicapier.org/diadelosmuertos",
        'id="forest-lawn-glendale-dia-de-los-muertos"',
        "forestlawn.com/events/dia-de-los-muertos",
        'id="self-help-graphics-dia-de-los-muertos"',
        "selfhelpgraphics.com/diadelosmuertos",
        "Best for:",
        "/directory?city=Burbank",
        "/directory?city=Pasadena",
        "/directory?city=Long%20Beach",
    ):
        assert expected in html

    for expired in (
        "Grand Ave Arts: All Access in Los Angeles",
        "LA Times Food Bowl in Santa Monica",
        "Scott Silven's <em>Wonders</em>",
        "Pasadena's 710 Stub Walktober",
        "Downtown Long Beach Fright Fest",
        "Belmont Shore Sidewalk Chalk Art Contest",
        "Glendale Día de Los Muertos",
        "Burbank Haunted Adventure",
        "Pasadena Fall Festival",
        "Anaheim Fall Festival and Halloween Parade",
        "SoCal Corgi Beach Day",
        "Ghosts of the Miles",
        "Jewel City Concert Series",
        "DTLB Unfiltered photo walk",
        "Formula DRIFT Shoreline Showdown",
        "Burbank Little Pumpkins Tot Party",
        "Held in Trust",
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


def test_fall_guide_routes_homepages_image_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/southern-california-september-events-2026",
        "/white/articles/southern-california-september-events-2026",
    ):
        response = client.get(route)
        assert response.status_code == 200
        assert "Forty Southern California fall plans" in response.text

    image = client.get("/assets/articles/southern-california-september-events-2026.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated October 25 · Fall guide" in response.text
        assert "Forty Southern California fall plans, ranked." in response.text
        for current in (
            "Marina Spooktacular",
            "Burbank's Wild Creatures Walk",
            "LA Plaza's Día de los Muertos Family Day",
            "UCLA's Party on the Pier",
            "Strange Science",
            "Santa Monica Pier's Día de los Muertos celebration",
            "Forest Lawn Glendale",
            "Self Help Graphics",
        ):
            assert current in response.text
        for expired in (
            "Grand Ave Arts",
            "LA Times Food Bowl",
            "Scott Silven",
            "Walktober",
            "Fright Fest",
            "Formula DRIFT",
            "Little Pumpkins",
            "Held in Trust",
        ):
            assert expired not in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert root_sitemap.status_code == 200
    assert white_sitemap.status_code == 308
    assert "<loc>https://perknation.app/articles/southern-california-september-events-2026</loc>" in root_sitemap.text


def test_public_answers_use_only_current_fall_recommendations() -> None:
    general = _public_review_live_query_response(
        "What current events are covered in Southern California?",
        "home_local_guide",
    )
    assert general
    for current in (
        "Forty Southern California fall plans",
        "Marina Spooktacular",
        "Wild Creatures Walk",
        "LA Plaza's Día de los Muertos Family Day",
        "Party on the Pier",
        "Strange Science",
        "Santa Monica Pier's Día de los Muertos",
        "Forest Lawn Glendale",
        "Self Help Graphics",
    ):
        assert current in general
    for expired in (
        "Grand Ave Arts",
        "LA Times Food Bowl",
        "Scott Silven",
        "Fright Fest",
        "Formula DRIFT",
        "Ghosts of the Miles",
    ):
        assert expired not in general

    burbank = _public_review_live_query_response("What current events are covered in Burbank?", "home_local_guide")
    assert "Wild Creatures Walk" in burbank
    assert "#burbank-wild-creatures-walk" in burbank
    assert "Haunted Adventure" not in burbank
    assert "Little Pumpkins" not in burbank

    pasadena = _public_review_live_query_response("What current events are covered in Pasadena?", "home_local_guide")
    assert "Bark in the Park" in pasadena
    assert "Strange Science" in pasadena
    assert "Walktober" not in pasadena
    assert "Pasadena Fall Festival" not in pasadena

    glendale = _public_review_live_query_response("What current events are covered in Glendale?", "home_local_guide")
    assert "Forest Lawn Glendale" in glendale
    assert "Jewel City" not in glendale


def test_current_city_counts_match_live_facet_context() -> None:
    html = ARTICLE.read_text(encoding="utf-8")
    for expected in (
        "968 Burbank listings",
        "563 Pasadena listings",
        "208 Long Beach listings",
        "100 Glendale listings",
        "61 Los Angeles listings",
        "43 Huntington Beach listings",
        "40 Arcadia listings",
        "35 Anaheim listings",
    ):
        assert expected in html
