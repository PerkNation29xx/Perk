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
    assert 'dateModified": "2026-11-21"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 31))

    for expected in (
        'id="pershing-square-holiday-ice-rink"',
        "holidayicerinkdowntownla.com/ice-skating-downtown-la",
        "Spider Pavilion",
        'id="samuel-oschin-air-space-center"',
        "californiasciencecenter.org/visit/get-reservations-tickets",
        "302922833",
        'id="old-pasadena-holiday-passport"',
        "visitpasadena.com/events/old-pasadena-holiday-passport",
        'id="pasadena-doo-dah-love-in"',
        "pasadenadoodahparade.info/parade-info",
        "visitpasadena.com/events/pasadena-doo-dah-love-in",
        'id="dreamstate-socal-long-beach"',
        "socal.dreamstateusa.com/hours-and-info",
        "socal.dreamstateusa.com/lineup/set-times",
        'id="ctn-animation-expo-burbank"',
        "ctn-events.com/ctnx2026",
        "visitburbank.com/events/ctn-animation-expo",
        'id="great-los-angeles-walk-route-66"',
        "the-21st-annual-great-los-angeles-walk-celebrates-the-route-66-centennial-in-santa-monica",
        'id="nhm-nighttales"',
        "nhm.org/calendar/nighttales-museum-experience",
        'id="long-beach-little-women"',
        "musical.org/events/little-women-the-musical",
        'id="santa-monica-held-in-trust"',
        "4v0naphs6kscmrssg0n2ejrsce/202611041100",
        'id="santa-monica-swiss-winter-village"',
        "santamonica.com/event/swiss-winter-village",
        'id="anaheim-disneyland-holidays"',
        "disneyland.disney.go.com/events-tours/holidays-at-the-disneyland-resort",
        'id="santa-monica-tree-lighting"',
        "santamonica.com/event/downtown-santa-monica-tree-lighting-ceremony",
        'id="beverly-hills-monuments-of-stillness"',
        "beverlyhills.org/1839/Carole-Feurerman-Monuments-of-Stillness",
        'id="beverly-hills-holiday-lights-craft-fair"',
        "beverlyhills.org/1682/Citywide-Holiday-Festivities",
        'id="burbank-winter-wine-walk"',
        "visitburbank.com/events/burbank-winter-wine-walk",
        'id="descanso-enchanted-forest-of-light"',
        "descansogardens.org/enchanted",
        'id="enchant-christmas-arcadia"',
        "visitpasadena.com/blog/the-best-holiday-shows-performances-and-christmas-festivities",
        'id="la-auto-show"',
        "laconventioncenter.com/events/detail/la-auto-show-2026",
        'id="la-zoo-lights"',
        "lazoo.org/plan-your-visit/special-experiences/zoolights",
        "lazoo.org/plan-your-visit/special-experiences/zoo-lights-faqs",
        'id="aquarium-autumn-festival"',
        "aquariumofpacific.org/events/info/autumn_festival",
        'id="huntington-holiday-market"',
        "visitpasadena.com/events/the-huntington-holiday-market",
        'id="broad-has-the-myth-been-shattered"',
        "thebroad.org/art/collection-exhibitions/has-myth-been-shattered",
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
        "Veterans Day",
        "annual-nov-11-veterans-day-ceremony",
        "anaheim-veterans-day",
        "burbank-veterans-day",
        "pasadena-veterans-day",
        "Darker Waves",
        "Khmer Town Night Market",
        "Native Art and Acorn Festival",
        "Clothing Swap and Repair Café",
        "Art in Motion",
        "Next Chapter Writers' Summit",
        "Live On Sunset",
        "Jackalope Art Festival",
        "CicLAvia Pasadena",
        "Sensory Morning at The Broad",
        "Burbank Art Association Fall Show",
        "Santa Monica Pier Locals' Night",
        "Union Station Tree Lighting",
        "Rodeo Drive Holiday Lighting Celebration",
        "Regent Santa Monica Holiday Tree Lighting",
        "Westside Night Market",
        "Pasko Holiday Market",
        "Holiday in the Park",
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
        assert "Updated November 21 · Fall guide" in response.text
        assert "Thirty Southern California fall plans, ranked." in response.text
        for current in (
            "Old Pasadena Holiday Passport",
            "Dreamstate",
            "Great Los Angeles Walk",
            "The Huntington Holiday Market",
            "Air and Space Center, Pershing Square rink, NightTales",
            "Has the myth been shattered",
            "CTN Animation Expo",
            "Animation and visual storytelling · Nov 19-22",
            "Burbank Winter Wine Walk",
            "Doo Dah Love-In",
            "Free Pasadena arts and music gathering · Nov 22",
            "Santa Monica's free tree lighting",
            "Free Downtown Santa Monica holiday kickoff · Nov 22",
            "Held in Trust",
            "Enchanted Forest of Light",
            "Beverly Hills' free Holiday Craft Fair",
            "Swiss Winter Village",
            "LA Auto Show",
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
            "Veterans Day",
            "Darker Waves",
            "Khmer Town Night Market",
            "Native Art and Acorn Festival",
            "Clothing Swap and Repair Café",
            "Art in Motion",
            "Next Chapter Writers' Summit",
            "Live On Sunset",
            "CicLAvia",
            "Jackalope Art Festival",
            "Sensory Morning",
            "Pier Locals' Night",
            "Regent tree lighting",
            "Union Station's free tree lighting",
            "fall show's final day",
            "Westside Night Market",
            "Pasko Holiday Market",
            "Holiday in the Park",
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
        "Holiday Ice Rink at Pershing Square",
        "NightTales",
        "Samuel Oschin Air and Space Center",
        "Old Pasadena Holiday Passport",
        "CTN Animation Expo",
        "November 20-21 Dreamstate festival",
        "November 21 Route 66 Great Los Angeles Walk",
        "November 22 free tree lighting",
        "free November 22 Doo Dah Love-In",
        "free November 21 Holiday Market",
        "L.A. Zoo Lights",
        "Has the myth been shattered",
        "Enchant Christmas",
        "Held in Trust",
        "Swiss Winter Village",
        "Little Women",
        "Aquarium Autumn Festival",
        "Enchanted Forest of Light",
        "LA Auto Show",
        "Winter Wine Walk",
        "Monuments of Stillness",
        "Holidays at the Disneyland Resort",
        "nightly holiday lights",
        "November 22 craft fair",
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
        "Veterans Day",
        "Darker Waves",
        "Khmer Town Night Market",
        "Native Art and Acorn Festival",
        "Clothing Swap and Repair Café",
        "Art in Motion",
        "Next Chapter Writers' Summit",
        "Live On Sunset",
        "CicLAvia",
        "Jackalope Art Festival",
        "Sensory Morning",
        "Union Station's free November 19 Tree Lighting",
        "free November 19 Pier Locals' Night",
        "Art Association Fall Show",
        "November 19 holiday lighting",
        "Regent Holiday Tree Lighting",
        "Westside Night Market",
        "Pasko Holiday Market",
        "Holiday in the Park",
    ):
        assert expired not in general

    burbank = _public_review_live_query_response("What current events are covered in Burbank?", "home_local_guide")
    assert "Art Association Fall Show" not in burbank
    assert "CTN Animation Expo" in burbank
    assert "Winter Wine Walk" in burbank
    assert "#burbank-art-association-fall-show" not in burbank
    assert "#ctn-animation-expo-burbank" in burbank
    assert "#burbank-winter-wine-walk" in burbank
    assert "Holiday in the Park" not in burbank
    assert "#burbank-holiday-in-the-park" not in burbank
    assert "Halloween Carnival" not in burbank
    assert "Haunted Adventure" not in burbank
    assert "Little Pumpkins" not in burbank
    assert "Halloween Skatefest" not in burbank

    pasadena = _public_review_live_query_response("What current events are covered in Pasadena?", "home_local_guide")
    assert "Old Pasadena Holiday Passport" in pasadena
    assert "#old-pasadena-holiday-passport" in pasadena
    assert "Doo Dah Love-In" in pasadena
    assert "#pasadena-doo-dah-love-in" in pasadena
    assert "Strange Science" not in pasadena
    assert "Second Sundays" not in pasadena
    assert "USC Pacific Asia Museum" not in pasadena
    assert "Adaptive Sports Festival" not in pasadena
    assert "Bark in the Park" not in pasadena
    assert "Pasadena Fall Festival" not in pasadena
    assert "Trunk or Treat" not in pasadena
    assert "Villa Parke" not in pasadena
    assert "Jackalope Art Festival" not in pasadena
    assert "CicLAvia" not in pasadena

    glendale = _public_review_live_query_response("What current events are covered in Glendale?", "home_local_guide")
    assert "Clothing Swap and Repair Café" not in glendale
    assert "#glendale-clothing-swap-repair-cafe" not in glendale
    assert "Artifacts from an Unborn Empire" in glendale
    assert "Forest Lawn Glendale" not in glendale
    assert "Jewel City" not in glendale

    long_beach = _public_review_live_query_response("What current events are covered in Long Beach?", "home_local_guide")
    assert "Khmer Town Night Market" not in long_beach
    assert "#khmer-town-night-market-long-beach" not in long_beach
    assert "Little Women" in long_beach
    assert "Autumn Festival" in long_beach
    assert "Dreamstate" in long_beach
    assert "#dreamstate-socal-long-beach" in long_beach
    assert "#aquarium-autumn-festival" in long_beach
    assert "Westside Night Market" not in long_beach
    assert "#long-beach-westside-night-market" not in long_beach

    huntington_beach = _public_review_live_query_response("What current events are covered in Huntington Beach?", "home_local_guide")
    assert "Darker Waves" not in huntington_beach
    assert "#darker-waves-huntington-beach" not in huntington_beach

    arcadia = _public_review_live_query_response("What current events are covered in Arcadia?", "home_local_guide")
    assert "Enchant Christmas" in arcadia
    assert "#enchant-christmas-arcadia" in arcadia


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
