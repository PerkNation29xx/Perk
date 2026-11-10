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

    assert "Thirty Southern California fall plans" in html
    assert 'dateModified": "2026-11-10"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 31))

    for expected in (
        "Spider Pavilion",
        'id="samuel-oschin-air-space-center"',
        "californiasciencecenter.org/visit/get-reservations-tickets",
        "302922833",
        'id="ciclavia-pasadena"',
        "cityofpasadena.net/event/ciclavia-2026-pasadena",
        'id="broad-sensory-morning"',
        "thebroad.org/events/sensory-morning-broad-16",
        'id="burbank-art-association-fall-show"',
        "2026-burbank-art-association",
        'id="nhm-nighttales"',
        "nhm.org/calendar/nighttales-museum-experience",
        'id="long-beach-little-women"',
        "musical.org/events/little-women-the-musical",
        'id="santa-monica-veterans-day"',
        "annual-nov-11-veterans-day-ceremony",
        'id="santa-monica-held-in-trust"',
        "4v0naphs6kscmrssg0n2ejrsce/202611041100",
        'id="burbank-veterans-day"',
        "/calendar/-/calendar/event/3094931/0",
        'id="pasadena-veterans-day"',
        "cityofpasadena.net/events/2026-11-11",
        'id="anaheim-veterans-day"',
        "anaheim.net/m/NewsFlash/Home/Detail/3249",
        'id="santa-monica-swiss-winter-village"',
        "santamonica.com/event/swiss-winter-village",
        'id="anaheim-native-art-acorn-festival"',
        "anaheim.net/6813/Native-Art-and-Acorn-Festival",
        'id="glendale-clothing-swap-repair-cafe"',
        "glendaleca.gov/Home/Components/Calendar/Event/56145/18",
        'id="anaheim-disneyland-holidays"',
        "disneyland.disney.go.com/events-tours/holidays-at-the-disneyland-resort",
        'id="west-hollywood-next-chapter-writers-summit"',
        "lacountylibrary.org/nextchapter",
        'id="west-hollywood-live-on-sunset"',
        "visitwesthollywood.com/events/live-on-sunset",
        'id="beverly-hills-monuments-of-stillness"',
        "beverlyhills.org/1839/Carole-Feurerman-Monuments-of-Stillness",
        'id="beverly-hills-holiday-lighting"',
        "beverlyhills.org/1682/Citywide-Holiday-Festivities",
        'id="burbank-holiday-in-the-park"',
        "visitburbank.com/events/holiday-in-the-park",
        'id="burbank-winter-wine-walk"',
        "visitburbank.com/events/burbank-winter-wine-walk",
        'id="la-auto-show"',
        "laconventioncenter.com/events/detail/la-auto-show-2026",
        'id="aquarium-autumn-festival"',
        "aquariumofpacific.org/events/info/autumn_festival",
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
        "Moonlight Hike",
        "Pasadena Trunk or Treat",
        "Fright Dive",
        "Halloween Skatefest",
        "Villa Parke",
        "Anaheim Día de los Muertos",
        "Halloween at Kidspace",
        "Burbank Halloween Carnival",
        "West Hollywood Halloween Carnaval",
        "Halloween STEMebration",
        "Strange Science",
        "Queen Mary's Dark Harbor",
        "Carved at Descanso Gardens",
        "Día de los Muertos at Woodlawn Cemetery",
        "Chrysanthemum Festival",
        "Boo at the L.A. Zoo",
        "Walt Disney Archives and Disneyland art at Muzeo",
        "Halloween Horror Nights",
        "Santa Monica Pier Día de los Muertos",
        "Forest Lawn Glendale Día de los Muertos",
        "Long Beach Día de los Muertos Festival",
        "Grand Park's Downtown Día de los Muertos",
        "Día de los Muertos on Olvera Street",
        "First Wednesdays at the Aquarium of the Pacific",
        "Fleurs de Villes at Greystone",
        "Norton Simon Museum Free First Friday",
        "Pasadena Adaptive Sports Festival",
        "Corita Day Festival",
        "Arcadia Community Cleanup Day",
        "Nature in Your Neighborhood in Glendale",
        "Anaheim Indie Author Day",
        "Self Help Graphics Día de los Muertos Celebration",
        "Huntington Beach Oktoberfest",
        "USC Pacific Asia Museum Free Second Sunday",
        "Renegade Craft at Santa Monica Airport",
        "Second Sundays: “This Land Is …”",
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
        assert "Thirty Southern California fall plans" in response.text

    image = client.get("/assets/articles/southern-california-september-events-2026.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated November 10 · Fall guide" in response.text
        assert "Thirty Southern California fall plans, ranked." in response.text
        for current in (
            "November 13 Samuel Oschin Air and Space Center opening",
            "November 12-January 10 NightTales after-dark museum experience",
            "The Broad's free November 15 Sensory Morning",
            "Santa Monica's Veterans Day ceremony",
            "Long Beach's <em>Little Women</em> and Aquarium Autumn Festival",
            "Burbank's fall art, Veterans Day ceremony, Holiday in the Park, and Winter Wine Walk",
            "Anaheim's Veterans Day ceremony, Native Art and Acorn Festival, and Holidays at the Disneyland Resort",
            "Glendale's Clothing Swap and Repair Café",
            "Held in Trust",
            "West Hollywood's Next Chapter Writers' Summit",
            "Live On Sunset",
            "Beverly Hills' long-run Rodeo Drive sculpture walk and holiday lighting",
            "Swiss Winter Village",
            "the LA Auto Show",
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
            "Moonlight Hike",
            "Trunk or Treat",
            "Fright Dive",
            "Skatefest",
            "Villa Parke",
            "Día de los Muertos night",
            "Halloween at Kidspace",
            "Halloween STEMebration",
            "West Hollywood Halloween Carnaval",
            "Dark Harbor",
            "Carved at Descanso Gardens",
            "Woodlawn Cemetery",
            "Chrysanthemum Festival",
            "Boo at the L.A. Zoo",
            "Halloween Horror Nights",
            "Forest Lawn Glendale",
            "Grand Park's final Día de los Muertos",
            "Norton Simon opens its galleries",
            "Adaptive Sports Festival",
            "Corita Day",
            "Community Cleanup Day",
            "Nature in Your Neighborhood",
            "Indie Author Day",
            "Self Help Graphics",
            "USC Pacific Asia Museum",
            "Renegade Craft",
            "Second Sundays",
            "Huntington Beach Oktoberfest",
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
        "Thirty Southern California fall plans",
        "NightTales",
        "CicLAvia",
        "Samuel Oschin Air and Space Center",
        "The Broad's free November 15 Sensory Morning",
        "Held in Trust",
        "Swiss Winter Village",
        "Little Women",
        "Aquarium Autumn Festival",
        "LA Auto Show",
        "Live On Sunset",
        "Holiday in the Park",
        "Winter Wine Walk",
        "Monuments of Stillness",
        "Art Association Fall Show",
        "Clothing Swap and Repair Café",
        "Native Art and Acorn Festival",
        "Holidays at the Disneyland Resort",
        "Veterans Day ceremony",
        "Next Chapter Writers' Summit",
        "November 19 holiday lighting",
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
        "Trunk or Treat",
        "Fright Dive",
        "Halloween Skatefest",
        "Villa Parke",
        "Día de los Muertos night",
        "Halloween at Kidspace",
        "Halloween Carnival",
        "Halloween STEMebration",
        "Strange Science",
        "Dark Harbor",
        "Carved at Descanso Gardens",
        "Woodlawn Cemetery",
        "Chrysanthemum Festival",
        "Boo at the L.A. Zoo",
        "Halloween Horror Nights",
        "Forest Lawn Glendale",
        "Grand Park's final November 2 Día de los Muertos",
        "Norton Simon",
        "Adaptive Sports Festival",
        "Corita Day Festival",
        "Community Cleanup Day",
        "Nature in Your Neighborhood",
        "Indie Author Day",
        "Self Help Graphics",
        "USC Pacific Asia Museum",
        "Renegade Craft",
        "Second Sundays",
        "Huntington Beach Oktoberfest",
    ):
        assert expired not in general

    burbank = _public_review_live_query_response("What current events are covered in Burbank?", "home_local_guide")
    assert "Art Association Fall Show" in burbank
    assert "Veterans Day ceremony" in burbank
    assert "Holiday in the Park" in burbank
    assert "Winter Wine Walk" in burbank
    assert "#burbank-art-association-fall-show" in burbank
    assert "#burbank-veterans-day" in burbank
    assert "#burbank-holiday-in-the-park" in burbank
    assert "#burbank-winter-wine-walk" in burbank
    assert "Halloween Carnival" not in burbank
    assert "Haunted Adventure" not in burbank
    assert "Little Pumpkins" not in burbank
    assert "Halloween Skatefest" not in burbank

    pasadena = _public_review_live_query_response("What current events are covered in Pasadena?", "home_local_guide")
    assert "CicLAvia" in pasadena
    assert "#ciclavia-pasadena" in pasadena
    assert "Strange Science" not in pasadena
    assert "Second Sundays" not in pasadena
    assert "USC Pacific Asia Museum" not in pasadena
    assert "Adaptive Sports Festival" not in pasadena
    assert "#pasadena-veterans-day" in pasadena
    assert "Bark in the Park" not in pasadena
    assert "Pasadena Fall Festival" not in pasadena
    assert "Trunk or Treat" not in pasadena
    assert "Villa Parke" not in pasadena

    glendale = _public_review_live_query_response("What current events are covered in Glendale?", "home_local_guide")
    assert "Clothing Swap and Repair Café" in glendale
    assert "#glendale-clothing-swap-repair-cafe" in glendale
    assert "Artifacts from an Unborn Empire" in glendale
    assert "Forest Lawn Glendale" not in glendale
    assert "Jewel City" not in glendale

    long_beach = _public_review_live_query_response("What current events are covered in Long Beach?", "home_local_guide")
    assert "Little Women" in long_beach
    assert "Autumn Festival" in long_beach
    assert "#aquarium-autumn-festival" in long_beach


def test_current_city_counts_match_live_facet_context() -> None:
    html = ARTICLE.read_text(encoding="utf-8")
    for expected in (
        "968 Burbank listings",
        "563 Pasadena listings",
        "208 Long Beach listings",
        "100 Glendale listings",
        "61 Los Angeles listings",
        "city=Huntington%20Beach\">Huntington Beach</a> (43)",
        "35 Anaheim listings",
    ):
        assert expected in html
