import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-september-events-2026.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "southern-california-september-events-2026.png"


def test_fall_guide_is_substantial_ranked_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Fifty Southern California fall plans" in html
    assert 'dateModified": "2026-10-23"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 51))
    for expected in (
        "Halloween at Kidspace",
        'id="kidspace-halloween"',
        "Spider Pavilion at the Natural History Museum",
        'id="spider-pavilion"',
        "Grand Ave Arts: All Access in Los Angeles",
        'id="grand-ave-arts-all-access"',
        "https://grandavearts.org/",
        "Huntington Beach Oktoberfest",
        'id="huntington-beach-oktoberfest"',
        "Queen Mary's Dark Harbor",
        'id="queen-mary-dark-harbor"',
        "Carved at Descanso Gardens",
        'id="carved-descanso-gardens"',
        "https://www.descansogardens.org/carved/",
        "Long Beach Open Studio Tour",
        'id="long-beach-open-studio-tour"',
        "https://lbopenstudiotour.com/",
        "Bark in the Park in Pasadena",
        'id="pasadena-bark-in-the-park"',
        "https://www.visitpasadena.com/blog/halloween/",
        "LA Times Food Bowl in Santa Monica",
        'id="la-times-food-bowl-santa-monica"',
        "101-best-restaurants-in-l-a",
        "Scott Silven's <em>Wonders</em> at BroadStage",
        'id="scott-silven-wonders-santa-monica"',
        "scott-silven-wonders",
        "Pasadena's 710 Stub Walktober",
        'id="pasadena-710-stub-walktober"',
        "Stories of Displacement",
        "Downtown Long Beach Fright Fest",
        'id="downtown-long-beach-fright-fest"',
        "downtown-fright-fest",
        "Belmont Shore Sidewalk Chalk Art Contest",
        'id="belmont-shore-sidewalk-chalk-art"',
        "belmont-shore-sidewalk-chalk-art-contest",
        "Grand Park's Downtown Día de los Muertos",
        'id="grand-park-dia-de-los-muertos"',
        "https://grandparkla.org/diadelosmuertos",
        "Scarium Family Night at the Aquarium of the Pacific",
        'id="scarium-family-night"',
        "scarium_family_night",
        "Fright Dive at the Aquarium of the Pacific",
        'id="fright-dive-aquarium"',
        "events/info/night_dive",
        "Long Beach Día de los Muertos Festival",
        'id="long-beach-dia-de-los-muertos-festival"',
        "save-the-date-city-of-long-beachs-dia-de-los-muertos-festival-returns-nov.-1",
        "Santa Monica Spooky Splash",
        'id="santa-monica-spooky-splash"',
        "45112ggwps9h1y66jw9xjewkx6/202610231700",
        "Glendale Día de Los Muertos",
        'id="glendale-dia-de-los-muertos"',
        "Event/56410/18",
        "Burbank Haunted Adventure",
        'id="burbank-haunted-adventure"',
        "https://www.burbankca.gov/calendar/-/calendar/event/4414632/0",
        "Pasadena Fall Festival",
        'id="pasadena-fall-festival"',
        "https://www.cityofpasadena.net/event/fall-festival/",
        "Boo at the L.A. Zoo",
        'id="boo-at-la-zoo"',
        "https://lazoo.org/plan-your-visit/special-experiences/boo-at-the-l-a-zoo-2026/",
        "Anaheim Fall Festival and Halloween Parade",
        'id="anaheim-fall-festival-parade"',
        "https://www.anaheimfallfestival.org/parade/",
        "SoCal Corgi Beach Day in Huntington Beach",
        'id="socal-corgi-beach-day"',
        "https://socalcorgibeachday.com/events",
        "Ghosts of the Miles in Santa Monica",
        'id="ghosts-of-the-miles"',
        "https://www.santamonica.com/event/ghosts-of-the-miles/",
        "West Hollywood Halloween Carnaval",
        'id="west-hollywood-halloween-carnaval"',
        "Event/32213/1106",
        "Walt Disney Archives and Disneyland art at Muzeo",
        'id="muzeo-disney-exhibitions"',
        "Lucas Museum opening in Los Angeles",
        'id="lucas-museum-opening"',
        "Where History Meets the Road",
        'id="pasadena-route-66-exhibition"',
        "Jewel City Concert Series in Glendale",
        'id="jewel-city-concerts"',
        "Portraits: Faces and Waves",
        'id="santa-monica-portraits-faces-waves"',
        "photography-exhibition-portraits-faces-and-waves-on-display-at-annenberg-community-beach-house-gallery",
        "Laura Aguilar: Day of the Dead at The Huntington",
        'id="laura-aguilar-day-of-the-dead"',
        "The Horror Show",
        'id="academy-museum-horror-show"',
        "Artifacts from an Unborn Empire",
        'id="artifacts-unborn-empire-glendale"',
        "Fleurs de Villes at Greystone",
        'id="fleurs-de-villes-greystone"',
        "DTLB Unfiltered photo walks",
        'id="dtlb-unfiltered-photo-walks"',
        "dtlb-unfiltered-returns-inviting-photographers-to-capture-downtown-their-way",
        "Pasadena Día de Los Muertos Festival and Altar Exhibit",
        'id="pasadena-dia-de-los-muertos"',
        "dia-de-los-muertos-festival-altar-exhibit",
        "Halloween STEMebration at Battleship IOWA",
        'id="battleship-iowa-halloween-stemebration"',
        "https://pacificbattleship.com/halloween-stemebration-at-battleship-iowa/",
        "Formula DRIFT Shoreline Showdown in Long Beach",
        'id="formula-drift-shoreline-showdown"',
        "https://www.formulad.com/schedule/2026/long-beach2",
        "Día de los Muertos at the Arboretum in Arcadia",
        'id="arcadia-dia-de-los-muertos-arboretum"',
        "https://arboretum.org/events/day-of-the-dead-dia-de-los-muertos/",
        "40 Arcadia listings",
        "Beverly Hills Fall Funtastic",
        'id="beverly-hills-fall-funtastic"',
        "Fall-Funtastic-Harvest-Festival---Octobe",
        "Burbank Little Pumpkins Tot Party",
        'id="burbank-little-pumpkins"',
        "West Hollywood Floating Pumpkin Patch",
        'id="weho-floating-pumpkin-patch"',
        "Event/32187/1472",
        "Held in Trust",
        'id="santa-monica-held-in-trust"',
        "4m0q8xgfh3dwp01en1ykxsn3m6/202610241600",
        "MOLAA Día de los Muertos Festival",
        'id="molaa-dia-de-los-muertos"',
        "https://molaa.org/2026-day-of-the-dead",
        "Día de los Muertos on Olvera Street",
        'id="olvera-street-dia-de-los-muertos"',
        "https://www.olveraevents.com/day-of-the-dead-olvera-street",
        "Burbank Halloween Skatefest",
        'id="burbank-halloween-skatefest"',
        "/calendar/-/calendar/event/3710005/0",
        "Coast Film &amp; Music Festival in Laguna Beach",
        'id="coast-film-music-festival"',
        "https://www.coastfilmfestival.com/",
        "Día De Los Muertos at Villa Parke in Pasadena",
        'id="pasadena-villa-parke-dia-de-los-muertos"',
        "city-of-pasadena-celebrates-latino-culture-heritage-and-community",
        "Halloween Horror Nights at Universal Studios Hollywood",
        'id="universal-halloween-horror-nights"',
        "https://visitburbank.com/events/halloween-horror-nights/",
        "Best for:",
        "/directory?city=Burbank",
        "/directory?city=Pasadena",
        "/directory?city=Long%20Beach",
    ):
        assert expected in html

    for expired in (
        "Seconds at PCH Food Fest",
        "Westminster Fall Festival",
        "SteelCraft Long Beach Oktoberfest",
        "Lucha Libre Weekend at MOLAA",
        "Taiwan Carnival in Anaheim",
        "Baja Splash in Long Beach",
        "Jane Austen UnScripted in West Hollywood",
        "Pasadena Chalk Festival",
        "Mariachi Meets The Smiths",
        "Long Beach Urban Farm Dinner",
        "SoCal Fitness Festival in Huntington Beach",
        "Simon Rodia Watts Towers Jazz Festival",
        "World Dog Day in West Hollywood",
        "Burbank Moonlight Hike",
        "Glendale Tech Week",
        "Orange County Burger Week",
        "Glendale International Film Festival awards night",
        "Design West Hollywood",
        "October 1 downtown kickoff",
        "Burbank Book Festival",
        "West Hollywood Movies in the Park",
        "Montana Avenue Art Walk in Santa Monica",
        "Pacific Airshow in Huntington Beach",
        "Hot Wheels Monster Trucks in Long Beach",
        "Little Women</em> Ballet in Los Angeles",
        "at Pasadena Playhouse",
        "Los Angeles Korean Festival",
        "Tustin Tiller Days",
        "Glendale Cultural Festival",
        "ArtNight Pasadena",
        "Public Broadcast Stereo",
        "A Great Day in the Stoke",
        "Culver City Arts Festival",
        "America at 250",
        "Fire Prevention Week Open House",
        "Latino Heritage Parade",
        "Irvine Global Village Festival",
        "Gilb Museum's 25th anniversary",
        "Long Beach Latino Restaurant Week",
        "CicLAvia—Heart of LA",
        "Explore JPL in Pasadena",
        "Continuum at Historic Belmar Park",
        "Long Beach Marathon weekend",
        "Indigenous Pride LA",
        "Monster Mash at Lincoln Park",
        "Shoreline Village Zombie Walk and Halloween Party",
        "LA Opera's <em>Carmen</em> at Santa Monica Pier",
        "Pasadena Route 66 Walktober tour",
        "DTLB Live Halloween edition",
        "West Hollywood Youth Halloween Carnival",
        "Southeast Asia Day in Long Beach",
        "Santa Monica airport-to-park master-plan event",
        "Howl-O-Ween at El Dorado Nature Center",
        "Holo Holo Music Festival in Long Beach",
        "Into the Woods",
        "Pasadena Craftsman Week",
        "Pasadena Gardens and Historic Homes Walktober",
        "OC Japan Fair in Costa Mesa",
        "Santa Monica Main Street Block Party and Day of the Dog",
        "AIDS Walk Los Angeles in West Hollywood",
        "Beverly Hills Art Show",
        "Burbank Harvest of Horror",
        "Newport Beach Film Festival",
        "TYPE S Night Lights",
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


def test_fall_guide_routes_image_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/southern-california-september-events-2026",
        "/white/articles/southern-california-september-events-2026",
    ):
        response = client.get(route)
        assert response.status_code == 200

    image = client.get("/assets/articles/southern-california-september-events-2026.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 500_000
    assert IMAGE.stat().st_size == len(image.content)

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Updated October 23 · Fall guide" in response.text
        assert "Fifty Southern California fall plans, ranked." in response.text
        for current in (
            "Halloween at Kidspace",
            "Spider Pavilion",
            "Grand Ave Arts: All Access",
            "Grand Park's Downtown Día de los Muertos",
            "Scarium Family Night",
            "Fright Dive",
            "Carved at Descanso Gardens",
            "Long Beach Open Studio Tour",
            "Pasadena's Bark in the Park",
            "LA Times Food Bowl",
            "Scott Silven's <em>Wonders</em>",
            "Downtown Long Beach Fright Fest",
            "Belmont Shore Sidewalk Chalk Art Contest",
            "Pasadena's remaining Walktober route",
            "Long Beach's Día de los Muertos Festival",
            "Santa Monica's Spooky Splash",
            "Pasadena's Fall Festival",
            "Burbank's Haunted Adventure",
            "Glendale Día de Los Muertos",
            "Boo at the L.A. Zoo",
            "Anaheim's Fall Festival and Halloween Parade",
            "SoCal Corgi Beach Day",
            "Ghosts of the Miles",
            "West Hollywood Halloween Carnaval",
            "Fleurs de Villes at Greystone",
            "DTLB Unfiltered photo walks",
            "Pasadena's Fall Festival and Día de Los Muertos",
            "Battleship IOWA's free Halloween STEMebration",
            "Formula DRIFT's Shoreline Showdown",
            "Arcadia's Día de los Muertos at the Arboretum",
            "Beverly Hills Fall Funtastic",
            "Burbank's Little Pumpkins Tot Party",
            "West Hollywood's Floating Pumpkin Patch",
            "Santa Monica's <em>Held in Trust</em> opening",
            "MOLAA's free Día de los Muertos festival",
            "Olvera Street's nine-night Día de los Muertos celebration",
            "Burbank Halloween Skatefest",
            "Coast Film &amp; Music Festival",
            "Villa Parke Día De Los Muertos",
            "Halloween Horror Nights",
        ):
            assert current in response.text
        for expired in (
            "Anaheim's Taiwan Carnival",
            "Simon Rodia Watts Towers Jazz Festival",
            "SoCal Fitness Festival",
            "Mariachi Meets The Smiths",
            "Westminster Fall Festival",
            "SteelCraft Long Beach Oktoberfest",
            "MOLAA Lucha Libre",
            "Glendale's final film-festival awards night",
            "Design West Hollywood",
            "Burbank Book Festival",
            "Santa Monica's Route 66 Art Walk",
            "West Hollywood's free park movie",
            "Pacific Airshow",
            "Hot Wheels Monster Trucks",
            "Little Women Ballet",
            "Los Angeles Korean Festival",
            "Tustin Tiller Days",
            "Glendale Cultural Festival",
            "ArtNight Pasadena",
            "Public Broadcast Stereo",
            "A Great Day in the Stoke",
            "Culver City Arts Festival",
            "America at 250",
            "fire station open house",
            "Latino Heritage celebration",
            "Irvine Global Village Festival",
            "Gilb Museum's Arcadia anniversary",
            "Latino Restaurant Week",
            "CicLAvia—Heart of LA",
            "Explore JPL",
            "Continuum at Historic Belmar Park",
            "Indigenous Pride LA",
            "Long Beach Marathon weekend",
            "free Monster Mash",
            "Shoreline Village Zombie Walk",
            "LA Opera's free <em>Carmen</em> simulcast",
            "DTLB Live Halloween edition",
            "West Hollywood's free Youth Halloween Carnival",
            "airport-to-park master-plan event",
            "Southeast Asia Day",
            "Long Beach's Howl-O-Ween",
            "Holo Holo Music Festival",
            "Into the Woods",
            "Pasadena Craftsman Week",
            "OC Japan Fair",
            "Main Street Block Party",
            "AIDS Walk Los Angeles",
            "Beverly Hills Art Show",
            "Burbank's Harvest of Horror",
            "Newport Beach Film Festival",
            "free TYPE S Night Lights",
        ):
            assert expired not in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert root_sitemap.status_code == 200
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/articles/southern-california-september-events-2026</loc>" in root_sitemap.text


def test_fall_guide_is_current_in_public_review_answers() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Southern California?",
        "home_local_guide",
    )

    assert answer
    for current in (
            "Fifty Southern California fall plans",
        "Halloween at Kidspace",
        "Spider Pavilion",
        "Grand Ave Arts: All Access",
        "LA Times Food Bowl",
        "Scott Silven's Wonders",
        "Downtown Long Beach Fright Fest",
        "Belmont Shore Sidewalk Chalk Art Contest",
        "Pasadena's remaining Walktober route",
        "Grand Park's Downtown Día de los Muertos",
        "Scarium Family Night",
        "Fright Dive",
            "Long Beach Día de los Muertos Festival",
            "Spooky Splash",
        "Santa Monica's Spooky Splash, Pico Walk Loop, and Held in Trust City Gallery opening",
        "Burbank Haunted Adventure",
        "Glendale Día de Los Muertos",
        "Pasadena Fall Festival",
        "Boo at the L.A. Zoo",
        "Anaheim Fall Festival and Halloween Parade",
        "SoCal Corgi Beach Day",
        "Ghosts of the Miles",
        "West Hollywood Halloween Carnaval",
        "Long Beach Open Studio Tour",
        "Pasadena's Bark in the Park",
        "The Horror Show",
        "Artifacts from an Unborn Empire",
        "Fleurs de Villes at Greystone",
        "Portraits: Faces and Waves",
        "DTLB Unfiltered photo walks",
        "Pasadena Fall Festival, the Pasadena Día de Los Muertos Festival",
        "Battleship IOWA's free Halloween STEMebration",
        "Formula DRIFT's Shoreline Showdown",
        "Día de los Muertos at the Arboretum in Arcadia",
        "Burbank's Little Pumpkins Tot Party and Halloween Skatefest",
        "West Hollywood's Floating Pumpkin Patch",
        "Beverly Hills Fall Funtastic",
        "Held in Trust City Gallery opening",
        "MOLAA's free Día de los Muertos Festival",
        "Olvera Street's nine-night Día de los Muertos celebration",
        "Halloween Skatefest",
        "Coast Film & Music Festival in Laguna Beach",
        "Villa Parke Día De Los Muertos gathering",
        "Halloween Horror Nights near Burbank",
        "/articles/southern-california-september-events-2026",
    ):
        assert current in answer
    for expired in (
        "Seconds at PCH Food Fest",
        "Jane Austen UnScripted",
        "Westminster Fall Festival",
        "SteelCraft Long Beach Oktoberfest",
        "Lucha Libre weekend",
        "Taiwan Carnival",
        "Baja Splash",
        "Urban Farm Dinner",
        "SoCal Fitness Festival",
        "Mariachi Meets The Smiths",
        "Simon Rodia Watts Towers Jazz Festival",
        "Glendale International Film Festival",
        "Design West Hollywood",
        "Burbank Book Festival",
        "Montana Avenue Art Walk",
        "West Hollywood's free Movies in the Park",
        "Pacific Airshow",
        "Long Beach's free Monster Mash",
        "Shoreline Village Zombie Walk",
        "LA Opera's free Carmen simulcast",
        "DTLB Live Halloween edition",
        "Youth Halloween Carnival",
        "Southeast Asia Day",
        "airport-to-park master-plan event",
        "Howl-O-Ween",
        "Holo Holo Music Festival",
        "Hot Wheels Monster Trucks",
        "Little Women Ballet",
        "Tustin Tiller Days",
        "Los Angeles Korean Festival",
        "Glendale Cultural Festival",
        "ArtNight Pasadena",
        "Public Broadcast Stereo",
        "A Great Day in the Stoke",
        "Culver City Arts Festival",
        "America at 250",
        "Fire Prevention Week Open House",
        "Pasadena Latino Heritage Parade",
        "Irvine Global Village Festival",
        "Gilb Museum's Arcadia anniversary",
        "Into the Woods",
        "Pasadena Craftsman Week",
        "OC Japan Fair",
        "Main Street Block Party",
        "AIDS Walk Los Angeles",
        "Beverly Hills Art Show",
        "Burbank's Harvest of Horror",
        "Newport Beach Film Festival",
        "TYPE S Night Lights",
    ):
        assert expired not in answer


def test_orange_county_city_answers_include_current_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "SoCal Corgi Beach Day" in answer
    assert "#socal-corgi-beach-day" in answer
    assert "Walt Disney Archives" in answer
    assert "Anaheim Fall Festival" in answer
    assert "#anaheim-fall-festival-parade" in answer
    assert "OC Japan Fair" not in answer
    assert "Into the Woods" not in answer
    assert "Westminster" not in answer
    assert "SoCal Fitness Festival" not in answer


def test_pasadena_answer_includes_walktober_and_flexible_exhibitions() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Pasadena?",
        "home_local_guide",
    )

    assert answer
    assert "Stories of Displacement: the 710 Stub" in answer
    assert "#pasadena-710-stub-walktober" in answer
    assert "Pasadena Fall Festival" in answer
    assert "#pasadena-fall-festival" in answer
    assert "Día de Los Muertos Festival" in answer
    assert "#pasadena-dia-de-los-muertos" in answer
    assert "Bark in the Park" in answer
    assert "#pasadena-bark-in-the-park" in answer
    assert "Where History Meets the Road" in answer
    assert "Laura Aguilar" in answer
    assert "Pasadena Chalk Festival" not in answer
    assert "Gardens and Historic Homes Walktober" not in answer


def test_burbank_answer_includes_current_haunted_adventure() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Burbank?",
        "home_local_guide",
    )

    assert answer
    assert "Haunted Adventure" in answer
    assert "#burbank-haunted-adventure" in answer
    assert "children under 6 are not admitted" in answer
    assert "Halloween Skatefest" in answer
    assert "#burbank-halloween-skatefest" in answer
    assert "Burbank Book Festival" not in answer


def test_long_beach_answer_includes_dark_harbor_and_fright_fest() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Long Beach this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Dark Harbor" in answer
    assert "#queen-mary-dark-harbor" in answer
    assert "Fright Fest" in answer
    assert "#downtown-long-beach-fright-fest" in answer
    assert "Belmont Shore Sidewalk Chalk Art Contest" in answer
    assert "#belmont-shore-sidewalk-chalk-art" in answer
    assert "DTLB Unfiltered" in answer
    assert "#dtlb-unfiltered-photo-walks" in answer
    assert "Scarium Family Night" in answer
    assert "#scarium-family-night" in answer
    assert "Fright Dive" in answer
    assert "#fright-dive-aquarium" in answer
    assert "TYPE S Night Lights" not in answer
    assert "#type-s-night-lights" not in answer
    assert "Formula DRIFT's Shoreline Showdown" in answer
    assert "#formula-drift-shoreline-showdown" in answer
    assert "MOLAA's Día de los Muertos Festival" in answer
    assert "#molaa-dia-de-los-muertos" in answer
    assert "SteelCraft" not in answer
    assert "Lucha Libre" not in answer
    assert "Baja Splash" not in answer
    assert "Urban Farm Dinner" not in answer
    assert "Latino Restaurant Week" not in answer
    assert "Long Beach Marathon weekend" not in answer


def test_huntington_beach_answer_includes_current_oktoberfest() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Huntington Beach?",
        "home_local_guide",
    )

    assert answer
    assert "SoCal Corgi Beach Day" in answer
    assert "#socal-corgi-beach-day" in answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "September 12-November 8" in answer
    assert "#huntington-beach-oktoberfest" in answer
    assert "SoCal Fitness Festival" not in answer


def test_arcadia_answer_includes_current_arboretum_event() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Arcadia?",
        "home_local_guide",
    )

    assert answer
    assert "Día de los Muertos" in answer
    assert "Los Angeles County Arboretum" in answer
    assert "October 25" in answer
    assert "#arcadia-dia-de-los-muertos-arboretum" in answer
    assert "40 local listings" in answer
    assert "Gilb Museum" not in answer
