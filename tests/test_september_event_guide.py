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

    assert "Forty-four Southern California fall plans" in html
    assert 'dateModified": "2026-11-27"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 45))

    for expected in (
        'id="pershing-square-holiday-ice-rink"',
        "holidayicerinkdowntownla.com/ice-skating-downtown-la",
        "Spider Pavilion",
        'id="samuel-oschin-air-space-center"',
        "californiasciencecenter.org/visit/get-reservations-tickets",
        "302922833",
        'id="old-pasadena-holiday-passport"',
        "visitpasadena.com/events/old-pasadena-holiday-passport",
        'id="la-kings-holiday-ice-festival"',
        "lalive.com/events/detail/holiday-ice-26-27",
        'id="home-alone-in-concert"',
        "laphil.com/tickets-and-events/festivals-and-highlights/deck-the-hall-holiday-concerts",
        'id="glendale-post-turkey-harvest-hike"',
        "Calendar/Event/56130/17",
        'id="hollywood-christmas-parade"',
        "thehollywoodchristmasparade.org/road-closures-2026",
        'id="bob-baker-nutcracker"',
        "bobbakermarionettetheater.com/around-town/nutcracker-sierra-madre-playhouse-2026",
        'id="a-christmas-carol-pasadena"',
        "anoisewithin.org/play/a-christmas-carol-5",
        'id="nhm-nighttales"',
        "nhm.org/calendar/nighttales-museum-experience",
        'id="burbank-wild-creatures-walk"',
        "calendar/event/4420482/0",
        'id="santa-monica-held-in-trust"',
        "4v0naphs6kscmrssg0n2ejrsce/202611041100",
        'id="santa-monica-swiss-winter-village"',
        "santamonica.com/event/swiss-winter-village",
        'id="anaheim-disneyland-holidays"',
        "disneyland.disney.go.com/events-tours/holidays-at-the-disneyland-resort",
        'id="santa-monica-frost-on-fifth"',
        "downtownsm.com/holiday-happenings",
        'id="beverly-hills-monuments-of-stillness"',
        "beverlyhills.org/1839/Carole-Feurerman-Monuments-of-Stillness",
        'id="beverly-hills-holiday-lights-craft-fair"',
        "beverlyhills.org/1682/Citywide-Holiday-Festivities",
        'id="descanso-enchanted-forest-of-light"',
        "descansogardens.org/enchanted",
        'id="enchant-christmas-arcadia"',
        "visitpasadena.com/blog/the-best-holiday-shows-performances-and-christmas-festivities",
        'id="la-auto-show"',
        "laconventioncenter.com/events/detail/la-auto-show-2026",
        'id="la-zoo-lights"',
        "lazoo.org/plan-your-visit/special-experiences/zoolights",
        "lazoo.org/plan-your-visit/special-experiences/zoo-lights-faqs",
        'id="broad-has-the-myth-been-shattered"',
        "thebroad.org/art/collection-exhibitions/has-myth-been-shattered",
        'id="winter-fest-oc-costa-mesa"',
        "ocfair.com/event/winter-fest-oc-2026",
        'id="pasadena-south-lake-holidayfest"',
        "southlakeavenue.org/holiday-shop-dine-win-on-south-lake-avenue",
        'id="anime-circuit-anaheim"',
        "anaheimgardenwalk.com/event/44117-anime-circuit",
        'id="belmont-shore-small-business-saturday"',
        "belmontshore.org/events/small-business-saturday-shop-the-shore",
        'id="pasadena-mayor-tree-lighting"',
        "cityofpasadena.net/event/mayors-annual-holiday-tree-lighting-ceremony",
        'id="burbank-mayor-tree-lighting"',
        "burbankca.gov/calendar/-/calendar/event/3887566/0",
        'id="santa-monica-candy-cane-drive"',
        "santa-claus-is-coming-to-town-december-5-2026",
        'id="anaheim-nutcracker-holiday-village"',
        "anaheim.net/2767/Nutcracker-Holiday-Village-Tree-Lighting",
        'id="west-hollywood-winter-wonderland"',
        "weho.org/Home/Components/Calendar/Event/32185",
        'id="glendale-holiday-tree-lighting"',
        "Calendar/Event/55141/18",
        "Calendar/Event/55143/11798",
        'id="arcadia-tree-lighting"',
        'id="arcadia-snow-festival"',
        "arcadiaca.gov/government/recreation/events.php",
        'id="montrose-glendale-christmas-parade"',
        "montrosechristmasparade.com",
        'id="belmont-shore-christmas-parade"',
        "visitlongbeach.com/events/annual-events/belmont-shore-christmas-parade",
        'id="long-beach-christmas-tree-lighting"',
        "visitlongbeach.com/events/annual-events/tree-lighting",
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
        "Jewel City Concert Series",
        "DTLB Unfiltered photo walk",
        "Formula DRIFT Shoreline Showdown",
        "Burbank Little Pumpkins Tot Party",
        "Long Beach Open Studio Tour",
        "Bark in the Park",
        "Marina Spooktacular",
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
        "Dreamstate SoCal in Long Beach",
        "Great Los Angeles Walk",
        "The Huntington Holiday Market",
        "Burbank Winter Wine Walk",
        "Pasadena Doo Dah Love-In",
        "CTN Animation Expo in Burbank",
        "Little Women</em> at Musical Theatre West",
        "Downtown Santa Monica Tree Lighting",
        "Aquarium of the Pacific Autumn Festival",
        "Holiday Craft Fair",
        "Rose Bowl Turkey Trot",
        "Turkey Trot Los Angeles",
        "Long Beach Turkey Trot",
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
        assert "Forty-four Southern California fall plans" in response.text

    image = client.get("/assets/articles/southern-california-september-events-2026.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated November 27 · Fall guide" in response.text
        assert "Forty-four Southern California fall plans, ranked." in response.text
        for current in (
            "Old Pasadena Holiday Passport",
            "Air and Space Center, Pershing Square rink, NightTales",
            "Has the myth been shattered",
            "LA Kings Holiday Ice Festival",
            "Home Alone",
            "Walt Disney Concert Hall live score · Nov 27-28",
            "Hollywood Christmas Parade",
            "Free Hollywood parade route · Nov 29",
            "Bob Baker",
            "A Christmas Carol",
            "Post-Turkey Harvest Hike",
            "Wild Creatures Walk",
            "South Lake Holidayfest",
            "Frost on Fifth",
            "Winter Fest OC",
            "Anime Circuit",
            "Belmont Shore Small Business Saturday",
            "Santa Monica's Candy Cane Drive",
            "Anaheim's Nutcracker Holiday Village",
            "West Hollywood's Winter Wonderland",
            "tree lightings in Glendale, Arcadia, Pasadena, Burbank, and Long Beach",
            "Arcadia's Snow Festival",
            "Montrose-Glendale and Belmont Shore Christmas parades",
            "Held in Trust",
            "Enchanted Forest of Light",
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
            "Dreamstate",
            "Great Los Angeles Walk",
            "The Huntington Holiday Market",
            "Burbank Winter Wine Walk",
            "CTN Animation Expo",
            "Doo Dah Love-In",
            "free Downtown tree lighting",
            "Aquarium Autumn Festival",
            "Little Women",
            "Holiday Craft Fair",
            "Turkey Trot",
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
        "Forty-four Southern California fall plans",
        "Holiday Ice Rink at Pershing Square",
        "NightTales",
        "Samuel Oschin Air and Space Center",
        "Old Pasadena Holiday Passport",
        "LA Kings Holiday Ice Festival",
        "Home Alone in Concert",
        "Hollywood Christmas Parade",
        "Bob Baker's November 28-January 3 Nutcracker",
        "A Noise Within's November 28-December 24 A Christmas Carol",
        "Post-Turkey Harvest Hike",
        "Wild Creatures Walk",
        "South Lake Holidayfest",
        "Frost on Fifth",
        "L.A. Zoo Lights",
        "Has the myth been shattered",
        "Enchant Christmas",
        "Held in Trust",
        "Swiss Winter Village",
        "Enchanted Forest of Light",
        "LA Auto Show",
        "Winter Fest OC",
        "free November 28 Anime Circuit",
        "November 28 Belmont Shore Small Business Saturday",
        "free December 4 mayoral tree lighting",
        "free December 5 mayoral tree lighting",
        "Monuments of Stillness",
        "Holidays at the Disneyland Resort",
        "nightly holiday lights",
        "December 5 Candy Cane Drive",
        "December 6 Nutcracker Holiday Village",
        "December 12 Winter Wonderland",
        "December 2 City Hall tree lighting",
        "December 5 Montrose-Glendale Christmas Parade",
        "December 3 Tree Lighting",
        "December 5 Snow Festival",
        "December 5 Belmont Shore Christmas Parade",
        "December 7 downtown tree lighting",
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
        "Dreamstate",
        "Great Los Angeles Walk",
        "Holiday Market",
        "Winter Wine Walk",
        "CTN Animation Expo",
        "November 22 free tree lighting",
        "free November 22 Doo Dah Love-In",
        "Little Women",
        "Aquarium Autumn Festival",
        "November 22 craft fair",
        "Rose Bowl Turkey Trot",
        "Turkey Trot Los Angeles",
        "Long Beach Turkey Trot",
    ):
        assert expired not in general

    burbank = _public_review_live_query_response("What current events are covered in Burbank?", "home_local_guide")
    assert "Art Association Fall Show" not in burbank
    assert "CTN Animation Expo" not in burbank
    assert "Mayor's Tree Lighting" in burbank
    assert "Wild Creatures Walk" in burbank
    assert "#burbank-wild-creatures-walk" in burbank
    assert "#burbank-art-association-fall-show" not in burbank
    assert "#ctn-animation-expo-burbank" not in burbank
    assert "#burbank-mayor-tree-lighting" in burbank
    assert "Winter Wine Walk" not in burbank
    assert "Holiday in the Park" not in burbank
    assert "#burbank-holiday-in-the-park" not in burbank
    assert "Halloween Carnival" not in burbank
    assert "Haunted Adventure" not in burbank
    assert "Little Pumpkins" not in burbank
    assert "Halloween Skatefest" not in burbank

    pasadena = _public_review_live_query_response("What current events are covered in Pasadena?", "home_local_guide")
    assert "Old Pasadena Holiday Passport" in pasadena
    assert "#old-pasadena-holiday-passport" in pasadena
    assert "A Christmas Carol" in pasadena
    assert "#a-christmas-carol-pasadena" in pasadena
    assert "Bob Baker" in pasadena
    assert "#bob-baker-nutcracker" in pasadena
    assert "Mayor's Holiday Tree Lighting" in pasadena
    assert "#pasadena-mayor-tree-lighting" in pasadena
    assert "South Lake Holidayfest" in pasadena
    assert "#pasadena-south-lake-holidayfest" in pasadena
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
    assert "Post-Turkey Harvest Hike" in glendale
    assert "#glendale-post-turkey-harvest-hike" in glendale
    assert "City Hall tree lighting" in glendale
    assert "#glendale-holiday-tree-lighting" in glendale
    assert "Montrose-Glendale Christmas Parade" in glendale
    assert "#montrose-glendale-christmas-parade" in glendale
    assert "Forest Lawn Glendale" not in glendale
    assert "Jewel City" not in glendale

    long_beach = _public_review_live_query_response("What current events are covered in Long Beach?", "home_local_guide")
    assert "Khmer Town Night Market" not in long_beach
    assert "#khmer-town-night-market-long-beach" not in long_beach
    assert "Long Beach Turkey Trot" not in long_beach
    assert "#long-beach-turkey-trot" not in long_beach
    assert "Small Business Saturday" in long_beach
    assert "#belmont-shore-small-business-saturday" in long_beach
    assert "Belmont Shore Christmas Parade" in long_beach
    assert "#belmont-shore-christmas-parade" in long_beach
    assert "Christmas Tree Lighting" in long_beach
    assert "#long-beach-christmas-tree-lighting" in long_beach
    assert "Dreamstate" not in long_beach
    assert "#aquarium-autumn-festival" not in long_beach
    assert "Westside Night Market" not in long_beach
    assert "#long-beach-westside-night-market" not in long_beach

    huntington_beach = _public_review_live_query_response("What current events are covered in Huntington Beach?", "home_local_guide")
    assert "Darker Waves" not in huntington_beach
    assert "#darker-waves-huntington-beach" not in huntington_beach

    arcadia = _public_review_live_query_response("What current events are covered in Arcadia?", "home_local_guide")
    assert "Enchant Christmas" in arcadia
    assert "#enchant-christmas-arcadia" in arcadia
    assert "December 3 Tree Lighting" in arcadia
    assert "#arcadia-tree-lighting" in arcadia
    assert "December 5 Snow Festival" in arcadia
    assert "#arcadia-snow-festival" in arcadia


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
