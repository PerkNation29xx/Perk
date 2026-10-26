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

    assert "Thirty-two Southern California fall plans" in html
    assert 'dateModified": "2026-10-26"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 33))

    for expected in (
        "Halloween at Kidspace",
        "Spider Pavilion",
        "Huntington Beach Oktoberfest",
        'id="burbank-moonlight-hike"',
        "/calendar/-/calendar/event/4397112/0",
        'id="pasadena-trunk-or-treat"',
        "trunk-or-treat-halloween-extravaganza",
        'id="santa-monica-woodlawn-dia-de-los-muertos"',
        "4qs9amnfe2p00xgqe88s65zs53/202611011100",
        "Día de los Muertos on Olvera Street",
        "Halloween STEMebration",
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
        "Party on the Pier",
        "Marina Spooktacular",
        "Wild Creatures Walk",
        "Jewel City Concert Series",
        "DTLB Unfiltered photo walk",
        "Formula DRIFT Shoreline Showdown",
        "Burbank Little Pumpkins Tot Party",
        "Held in Trust",
        "Long Beach Open Studio Tour",
        "Bark in the Park",
        "Marina Spooktacular",
        "Wild Creatures Walk",
        "LA Plaza Día de los Muertos Family Day",
        "Party on the Pier",
        "Día de los Muertos at the Arboretum",
        "Beverly Hills Fall Funtastic",
        "Floating Pumpkin Patch",
        "MOLAA Día de los Muertos Festival",
        "Coast Film &amp; Music Festival",
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
        assert "Thirty-two Southern California fall plans" in response.text

    image = client.get("/assets/articles/southern-california-september-events-2026.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated October 26 · Fall guide" in response.text
        assert "Thirty-two Southern California fall plans, ranked." in response.text
        for current in (
            "Burbank's October 27 Moonlight Hike",
            "Pasadena's October 29 Trunk or Treat",
            "Woodlawn Cemetery",
            "Strange Science",
            "Santa Monica's Pier and Woodlawn Cemetery celebrations",
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
        "Thirty-two Southern California fall plans",
        "Moonlight Hike",
        "Trunk or Treat",
        "Woodlawn Cemetery",
        "Strange Science",
        "Santa Monica's Pier and Woodlawn Cemetery",
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
        "Marina Spooktacular",
        "Wild Creatures Walk",
        "Party on the Pier",
    ):
        assert expired not in general

    burbank = _public_review_live_query_response("What current events are covered in Burbank?", "home_local_guide")
    assert "Moonlight Hike" in burbank
    assert "#burbank-moonlight-hike" in burbank
    assert "Haunted Adventure" not in burbank
    assert "Little Pumpkins" not in burbank

    pasadena = _public_review_live_query_response("What current events are covered in Pasadena?", "home_local_guide")
    assert "Trunk or Treat" in pasadena
    assert "Strange Science" in pasadena
    assert "Bark in the Park" not in pasadena
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
        "35 Anaheim listings",
    ):
        assert expected in html
