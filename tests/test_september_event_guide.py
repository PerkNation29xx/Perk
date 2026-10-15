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

    assert "Forty-eight Southern California fall plans" in html
    assert 'dateModified": "2026-10-15"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 49))
    for expected in (
        "Halloween at Kidspace",
        'id="kidspace-halloween"',
        "Spider Pavilion at the Natural History Museum",
        'id="spider-pavilion"',
        "Into the Woods",
        'id="into-the-woods-costa-mesa"',
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
        "Newport Beach Film Festival",
        'id="newport-beach-film-festival"',
        "your-guide-to-the-newport-beach-film-festival",
        "Screamfest in Hollywood",
        'id="screamfest-hollywood"',
        "https://www.screamfestla.com/festival/attending-festival",
        "Santa Monica Locals' Night drive-in",
        'id="santa-monica-locals-night"',
        "4xktb5jextrp31pbja4x19m8cd/202610151530",
        "Pasadena Craftsman Week",
        'id="pasadena-craftsman-week"',
        "https://www.pasadenaheritage.org/craftsman-week",
        "LA Opera's <em>Carmen</em> at Santa Monica Pier",
        'id="carmen-santa-monica-pier"',
        "opera-at-the-beach-%28santa-monica-pier%29",
        "Pasadena Gardens and Historic Homes Walktober",
        'id="pasadena-gardens-walktober"',
        "walktober-pasadena-gardens-and-historic-homes",
        "Pasadena Route 66 Walktober tour",
        'id="pasadena-route-66-walktober"',
        "https://www.cityofpasadena.net/event/walktober-99-years-and-11-months-of-route-66/",
        "OC Japan Fair in Costa Mesa",
        'id="oc-japan-fair"',
        "https://ocfair.com/event/oc-japan-fair-october-2026",
        "DTLB Live Halloween edition",
        'id="dtlb-live-halloween"',
        "https://downtownlongbeach.org/event/dtlb-live-halloween-edition-an-ez-sip-event/",
        "Burbank Harvest of Horror",
        'id="burbank-harvest-of-horror"',
        "West Hollywood Youth Halloween Carnival",
        'id="weho-youth-halloween-carnival"',
        "Santa Monica Spooky Splash",
        'id="santa-monica-spooky-splash"',
        "45112ggwps9h1y66jw9xjewkx6/202610231700",
        "Santa Monica Main Street Block Party and Day of the Dog",
        'id="santa-monica-main-street-block-party"',
        "main-street-block-party-day-of-the-dog",
        "Glendale Día de Los Muertos",
        'id="glendale-dia-de-los-muertos"',
        "Event/56410/18",
        "AIDS Walk Los Angeles in West Hollywood",
        'id="aids-walk-los-angeles"',
        "https://aidswalkla.org/faq/",
        "Burbank Haunted Adventure",
        'id="burbank-haunted-adventure"',
        "https://www.burbankca.gov/calendar/-/calendar/event/4414632/0",
        "Southeast Asia Day in Long Beach",
        'id="southeast-asia-day-long-beach"',
        "https://www.aquariumofpacific.org/events/info/southeast_asia_day",
        "Santa Monica airport-to-park master-plan event",
        'id="santa-monica-airport-park-plan"',
        "santa-monica-airport-conversion-project-to-hold-community-event-on-oct-17",
        "Beverly Hills Art Show",
        'id="beverly-hills-art-show"',
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
        "Howl-O-Ween at El Dorado Nature Center",
        'id="howl-o-ween-el-dorado"',
        "nc-special-events",
        "Pasadena Día de Los Muertos Festival and Altar Exhibit",
        'id="pasadena-dia-de-los-muertos"',
        "dia-de-los-muertos-festival-altar-exhibit",
        "Holo Holo Music Festival in Long Beach",
        'id="holo-holo-long-beach"',
        "https://www.holoholofestival.com/long-beach/",
        "TYPE S Night Lights in Long Beach",
        'id="type-s-night-lights"',
        "https://www.lbentertainmentcenter.com/events/type-s-2026/",
        "Formula DRIFT Shoreline Showdown in Long Beach",
        'id="formula-drift-shoreline-showdown"',
        "https://www.formulad.com/schedule/2026/long-beach2",
        "Día de los Muertos at the Arboretum in Arcadia",
        'id="arcadia-dia-de-los-muertos-arboretum"',
        "https://arboretum.org/events/day-of-the-dead-dia-de-los-muertos/",
        "40 Arcadia listings",
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
        assert "Updated October 15 · Fall guide" in response.text
        assert "Forty-eight Southern California fall plans, ranked." in response.text
        for current in (
            "Halloween at Kidspace",
            "Spider Pavilion",
            "Into the Woods",
            "Carved at Descanso Gardens",
            "Long Beach Open Studio Tour",
            "Newport Beach Film Festival",
            "Screamfest",
            "Locals' Night drive-in",
            "Pasadena Craftsman Week",
            "LA Opera's free <em>Carmen</em> simulcast at Santa Monica Pier",
            "two Pasadena Walktober routes",
            "OC Japan Fair",
            "DTLB Live Halloween edition",
            "Burbank's Harvest of Horror",
            "West Hollywood's free Youth Halloween Carnival",
            "Santa Monica's Spooky Splash",
            "Main Street Block Party",
            "airport-to-park master-plan event",
            "Pasadena's Fall Festival",
            "AIDS Walk Los Angeles",
            "Burbank's Haunted Adventure",
            "Southeast Asia Day",
            "Glendale Día de Los Muertos",
            "Boo at the L.A. Zoo",
            "Anaheim's Fall Festival and Halloween Parade",
            "SoCal Corgi Beach Day",
            "Ghosts of the Miles",
            "West Hollywood Halloween Carnaval",
            "Beverly Hills Art Show",
            "Fleurs de Villes at Greystone",
            "DTLB Unfiltered photo walks",
            "Long Beach's Howl-O-Ween",
            "Pasadena's Fall Festival and Día de Los Muertos",
            "Holo Holo Music Festival",
            "free TYPE S Night Lights",
            "Formula DRIFT's Shoreline Showdown",
            "Arcadia's Día de los Muertos at the Arboretum",
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
            "Forty-eight Southern California fall plans",
        "Halloween at Kidspace",
        "Spider Pavilion",
        "Into the Woods",
        "Screamfest in Hollywood",
        "Santa Monica's free Locals' Night drive-in",
        "Pasadena Craftsman Week",
        "LA Opera's free Carmen simulcast at Santa Monica Pier",
        "two free Pasadena Walktober routes",
            "OC Japan Fair",
            "DTLB Live Halloween edition",
            "Burbank's Harvest of Horror",
            "Youth Halloween Carnival",
            "Spooky Splash",
        "Santa Monica's Spooky Splash and Main Street Block Party",
        "AIDS Walk Los Angeles",
        "Burbank Haunted Adventure",
        "Southeast Asia Day",
        "airport-to-park master-plan event",
        "Glendale Día de Los Muertos",
        "Beverly Hills Art Show",
        "Pasadena Fall Festival",
        "Boo at the L.A. Zoo",
        "Anaheim Fall Festival and Halloween Parade",
        "SoCal Corgi Beach Day",
        "Ghosts of the Miles",
        "West Hollywood Halloween Carnaval",
        "Long Beach Open Studio Tour",
        "Newport Beach Film Festival",
        "The Horror Show",
        "Artifacts from an Unborn Empire",
        "Fleurs de Villes at Greystone",
        "Portraits: Faces and Waves",
        "DTLB Unfiltered photo walks",
        "Howl-O-Ween at El Dorado Nature Center",
        "Pasadena Fall Festival and Día de Los Muertos Festival",
        "Holo Holo Music Festival",
        "TYPE S Night Lights",
        "Formula DRIFT's Shoreline Showdown",
        "Día de los Muertos at the Arboretum in Arcadia",
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
    ):
        assert expired not in answer


def test_orange_county_city_answers_include_current_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "OC Japan Fair" in answer
    assert "#oc-japan-fair" in answer
    assert "SoCal Corgi Beach Day" in answer
    assert "#socal-corgi-beach-day" in answer
    assert "Into the Woods" in answer
    assert "#into-the-woods-costa-mesa" in answer
    assert "Walt Disney Archives" in answer
    assert "Anaheim Fall Festival" in answer
    assert "#anaheim-fall-festival-parade" in answer
    assert "Westminster" not in answer
    assert "SoCal Fitness Festival" not in answer


def test_pasadena_answer_includes_walktober_and_flexible_exhibitions() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Pasadena?",
        "home_local_guide",
    )

    assert answer
    assert "Route 66 Walktober tour" in answer
    assert "#pasadena-route-66-walktober" in answer
    assert "Gardens and Historic Homes Walktober" in answer
    assert "#pasadena-gardens-walktober" in answer
    assert "Pasadena Fall Festival" in answer
    assert "#pasadena-fall-festival" in answer
    assert "Día de Los Muertos Festival" in answer
    assert "#pasadena-dia-de-los-muertos" in answer
    assert "Where History Meets the Road" in answer
    assert "Laura Aguilar" in answer
    assert "Pasadena Chalk Festival" not in answer


def test_burbank_answer_includes_current_haunted_adventure() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Burbank?",
        "home_local_guide",
    )

    assert answer
    assert "Haunted Adventure" in answer
    assert "#burbank-haunted-adventure" in answer
    assert "children under 6 are not admitted" in answer
    assert "Burbank Book Festival" not in answer


def test_long_beach_answer_includes_dark_harbor_and_dtlb_live() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Long Beach this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Dark Harbor" in answer
    assert "#queen-mary-dark-harbor" in answer
    assert "DTLB Live" in answer
    assert "#dtlb-live-halloween" in answer
    assert "Southeast Asia Day" in answer
    assert "#southeast-asia-day-long-beach" in answer
    assert "DTLB Unfiltered" in answer
    assert "#dtlb-unfiltered-photo-walks" in answer
    assert "Howl-O-Ween" in answer
    assert "#howl-o-ween-el-dorado" in answer
    assert "Holo Holo Music Festival" in answer
    assert "#holo-holo-long-beach" in answer
    assert "TYPE S Night Lights" in answer
    assert "#type-s-night-lights" in answer
    assert "Formula DRIFT's Shoreline Showdown" in answer
    assert "#formula-drift-shoreline-showdown" in answer
    assert "SteelCraft" not in answer
    assert "MOLAA" not in answer
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
