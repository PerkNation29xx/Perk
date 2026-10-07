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

    assert "Thirty-nine Southern California fall plans" in html
    assert 'dateModified": "2026-10-07"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 40))
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
        "Long Beach Open Studio Tour",
        'id="long-beach-open-studio-tour"',
        "https://lbopenstudiotour.com/",
        "Long Beach Latino Restaurant Week",
        'id="long-beach-latino-restaurant-week"',
        "https://latinorestaurantweeklbc.com/",
        "Screamfest in Hollywood",
        'id="screamfest-hollywood"',
        "https://www.screamfestla.com/festival/attending-festival",
        "Public Broadcast Stereo",
        'id="public-broadcast-stereo-weho"',
        "Event/32227/1472",
        "Explore JPL in Pasadena",
        'id="explore-jpl-2026"',
        "https://www.jpl.nasa.gov/explore-jpl/",
        "all advance tickets are currently reserved",
        "A Great Day in the Stoke in Huntington Beach",
        'id="great-day-in-the-stoke"',
        "https://agreatdayinthestoke.com/",
        "Culver City Arts Festival",
        'id="culver-city-arts-festival"',
        "https://culvercityartsfestival.com/",
        "ArtNight Pasadena",
        'id="artnight-pasadena"',
        "Long Beach Symphony's <em>America at 250</em>",
        'id="long-beach-symphony-america-250"',
        "https://longbeachsymphony.org/concerts-events/america-at-250/",
        "Santa Monica Fire Prevention Week Open House",
        'id="santa-monica-fire-open-house"',
        "https://www.santamonica.gov/events/4qdtmwm31wjbrtpetwxs4d5zxh/202610101100",
        "Pasadena Latino Heritage Parade &amp; Festival",
        'id="pasadena-latino-heritage"',
        "https://www.cityofpasadena.net/parks-and-rec/event/latino-heritage-parade-festival/",
        "Continuum at Historic Belmar Park",
        'id="continuum-black-santa-monica"',
        "partnership-with-goldenvoice-honors-the-history-of-belmar-and-black-santa-monica",
        "Long Beach Marathon weekend",
        'id="long-beach-marathon"',
        "Indigenous Pride LA",
        'id="indigenous-pride-la"',
        "https://www.indigenouspridela.org/events-news/2026-ipla",
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
        "Irvine Global Village Festival",
        'id="irvine-global-village-festival"',
        "Gilb Museum's 25th anniversary in Arcadia",
        'id="gilb-museum-25th-anniversary"',
        "Fleurs de Villes at Greystone",
        'id="fleurs-de-villes-greystone"',
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
        assert "Updated October 7 · Fall guide" in response.text
        assert "Thirty-nine Southern California fall plans, ranked." in response.text
        for current in (
            "Halloween at Kidspace",
            "Spider Pavilion",
            "Into the Woods",
            "Long Beach Open Studio Tour",
            "Latino Restaurant Week",
            "Screamfest",
            "Public Broadcast Stereo",
            "Explore JPL",
            "A Great Day in the Stoke",
            "Culver City Arts Festival",
            "Santa Monica's fire station open house",
            "Continuum at Historic Belmar Park",
            "airport-to-park master-plan event",
            "ArtNight Pasadena",
            "Long Beach Symphony's <em>America at 250</em>",
            "Pasadena's Latino Heritage celebration",
            "Pasadena's Latino Heritage celebration and Fall Festival",
            "Indigenous Pride LA",
            "Burbank's Haunted Adventure",
            "Southeast Asia Day",
            "Long Beach Marathon weekend",
            "Anaheim's Fall Festival and Halloween Parade",
            "SoCal Corgi Beach Day",
            "Ghosts of the Miles",
            "West Hollywood Halloween Carnaval",
            "Beverly Hills Art Show",
            "Irvine Global Village Festival",
            "Gilb Museum's Arcadia anniversary",
            "Fleurs de Villes at Greystone",
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
        "Thirty-nine Southern California fall plans",
        "Halloween at Kidspace",
        "Spider Pavilion",
        "Into the Woods",
        "Screamfest in Hollywood",
        "Public Broadcast Stereo",
        "Explore JPL",
        "A Great Day in the Stoke",
        "Culver City Arts Festival",
        "ArtNight Pasadena",
        "Long Beach Symphony's America at 250",
        "Fire Prevention Week Open House",
        "Pasadena Latino Heritage Parade & Festival",
        "Continuum at Historic Belmar Park",
        "Indigenous Pride LA",
        "Burbank Haunted Adventure",
        "Southeast Asia Day",
        "airport-to-park master-plan event",
        "Long Beach Marathon weekend",
        "Beverly Hills Art Show",
        "Pasadena Fall Festival",
        "Anaheim Fall Festival and Halloween Parade",
        "SoCal Corgi Beach Day",
        "Ghosts of the Miles",
        "West Hollywood Halloween Carnaval",
        "Long Beach Open Studio Tour",
        "Latino Restaurant Week",
        "The Horror Show",
        "Artifacts from an Unborn Empire",
        "Irvine Global Village Festival",
        "Gilb Museum's Arcadia anniversary",
        "Fleurs de Villes at Greystone",
        "Portraits: Faces and Waves",
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
    ):
        assert expired not in answer


def test_orange_county_city_answers_include_current_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "A Great Day in the Stoke" in answer
    assert "#great-day-in-the-stoke" in answer
    assert "SoCal Corgi Beach Day" in answer
    assert "#socal-corgi-beach-day" in answer
    assert "Into the Woods" in answer
    assert "#into-the-woods-costa-mesa" in answer
    assert "Walt Disney Archives" in answer
    assert "Anaheim Fall Festival" in answer
    assert "#anaheim-fall-festival-parade" in answer
    assert "Westminster" not in answer
    assert "SoCal Fitness Festival" not in answer


def test_pasadena_answer_includes_artnight_and_flexible_exhibitions() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Pasadena?",
        "home_local_guide",
    )

    assert answer
    assert "ArtNight Pasadena" in answer
    assert "#artnight-pasadena" in answer
    assert "Explore JPL" in answer
    assert "#explore-jpl-2026" in answer
    assert "all reserved" in answer
    assert "Latino Heritage Parade & Festival" in answer
    assert "#pasadena-latino-heritage" in answer
    assert "Pasadena Fall Festival" in answer
    assert "#pasadena-fall-festival" in answer
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


def test_long_beach_answer_includes_dark_harbor_and_marathon() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Long Beach this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Dark Harbor" in answer
    assert "#queen-mary-dark-harbor" in answer
    assert "Long Beach Marathon weekend" in answer
    assert "#long-beach-marathon" in answer
    assert "Southeast Asia Day" in answer
    assert "#southeast-asia-day-long-beach" in answer
    assert "SteelCraft" not in answer
    assert "MOLAA" not in answer
    assert "Baja Splash" not in answer
    assert "Urban Farm Dinner" not in answer


def test_huntington_beach_answer_includes_current_oktoberfest() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Huntington Beach?",
        "home_local_guide",
    )

    assert answer
    assert "A Great Day in the Stoke" in answer
    assert "#great-day-in-the-stoke" in answer
    assert "SoCal Corgi Beach Day" in answer
    assert "#socal-corgi-beach-day" in answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "September 12-November 8" in answer
    assert "#huntington-beach-oktoberfest" in answer
    assert "SoCal Fitness Festival" not in answer
