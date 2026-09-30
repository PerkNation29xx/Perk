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

    assert "Twenty-eight Southern California fall plans" in html
    assert 'dateModified": "2026-09-30"' in html
    assert [int(value) for value in re.findall(r'<h2 id="[^"]+">(\d+)\.', html)] == list(range(1, 29))
    for expected in (
        "Design West Hollywood",
        'id="design-west-hollywood"',
        "Halloween at Kidspace",
        'id="kidspace-halloween"',
        "Spider Pavilion at the Natural History Museum",
        'id="spider-pavilion"',
        "Into the Woods",
        'id="into-the-woods-costa-mesa"',
        "at Pasadena Playhouse",
        'id="the-visit-pasadena"',
        "Huntington Beach Oktoberfest",
        'id="huntington-beach-oktoberfest"',
        "Queen Mary's Dark Harbor",
        'id="queen-mary-dark-harbor"',
        "Los Angeles Korean Festival",
        'id="los-angeles-korean-festival"',
        "Tustin Tiller Days",
        'id="tustin-tiller-days"',
        "https://www.tustinca.org/637/Tustin-Tiller-Days",
        "Burbank Book Festival",
        'id="burbank-book-festival"',
        "Long Beach Open Studio Tour",
        'id="long-beach-open-studio-tour"',
        "https://lbopenstudiotour.com/",
        "Long Beach Latino Restaurant Week",
        'id="long-beach-latino-restaurant-week"',
        "https://latinorestaurantweeklbc.com/",
        "West Hollywood Movies in the Park",
        'id="weho-princess-and-the-frog"',
        "Montana Avenue Art Walk in Santa Monica",
        'id="santa-monica-montana-art-walk"',
        "Glendale Cultural Festival",
        'id="glendale-cultural-festival"',
        "ArtNight Pasadena",
        'id="artnight-pasadena"',
        "Pasadena Latino Heritage Parade &amp; Festival",
        'id="pasadena-latino-heritage"',
        "https://www.cityofpasadena.net/parks-and-rec/event/latino-heritage-parade-festival/",
        "Long Beach Marathon weekend",
        'id="long-beach-marathon"',
        "Indigenous Pride LA",
        'id="indigenous-pride-la"',
        "https://www.indigenouspridela.org/events-news/2026-ipla",
        "Burbank Haunted Adventure",
        'id="burbank-haunted-adventure"',
        "https://www.burbankca.gov/calendar/-/calendar/event/4414632/0",
        "Beverly Hills Art Show",
        'id="beverly-hills-art-show"',
        "Walt Disney Archives and Disneyland art at Muzeo",
        'id="muzeo-disney-exhibitions"',
        "Lucas Museum opening in Los Angeles",
        'id="lucas-museum-opening"',
        "Where History Meets the Road",
        'id="pasadena-route-66-exhibition"',
        "Jewel City Concert Series in Glendale",
        'id="jewel-city-concerts"',
        "Laura Aguilar: Day of the Dead at The Huntington",
        'id="laura-aguilar-day-of-the-dead"',
        "The Horror Show",
        'id="academy-museum-horror-show"',
        "Artifacts from an Unborn Empire",
        'id="artifacts-unborn-empire-glendale"',
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
        assert "Updated September 30 · Fall guide" in response.text
        assert "Twenty-eight Southern California fall plans, ranked." in response.text
        for current in (
            "Design West Hollywood",
            "Los Angeles Korean Festival",
            "Tustin Tiller Days",
            "Burbank Book Festival",
            "Long Beach Open Studio Tour",
            "Latino Restaurant Week",
            "Santa Monica's Route 66 Art Walk",
            "West Hollywood's free park movie",
            "Glendale Cultural Festival",
            "ArtNight Pasadena",
            "Pasadena's Latino Heritage celebration",
            "Indigenous Pride LA",
            "Burbank's Haunted Adventure",
            "Long Beach Marathon weekend",
            "Beverly Hills Art Show",
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
        "Twenty-eight Southern California fall plans",
        "Design West Hollywood",
        "Tustin Tiller Days",
        "West Hollywood's free Movies in the Park",
        "Montana Avenue Art Walk",
        "ArtNight Pasadena",
        "Pasadena Latino Heritage Parade & Festival",
        "Indigenous Pride LA",
        "Burbank Haunted Adventure",
        "Long Beach Marathon weekend",
        "Beverly Hills Art Show",
        "Los Angeles Korean Festival",
        "Burbank Book Festival",
        "Long Beach Open Studio Tour",
        "Latino Restaurant Week",
        "The Horror Show",
        "Artifacts from an Unborn Empire",
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
    ):
        assert expired not in answer


def test_orange_county_city_answers_include_current_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Tustin Tiller Days" in answer
    assert "#tustin-tiller-days" in answer
    assert "Into the Woods" in answer
    assert "#into-the-woods-costa-mesa" in answer
    assert "Walt Disney Archives" in answer
    assert "Westminster" not in answer
    assert "SoCal Fitness Festival" not in answer


def test_pasadena_answer_includes_artnight_and_flexible_exhibitions() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Pasadena?",
        "home_local_guide",
    )

    assert answer
    assert "The Visit" in answer
    assert "#the-visit-pasadena" in answer
    assert "ArtNight Pasadena" in answer
    assert "#artnight-pasadena" in answer
    assert "Latino Heritage Parade & Festival" in answer
    assert "#pasadena-latino-heritage" in answer
    assert "Where History Meets the Road" in answer
    assert "Laura Aguilar" in answer
    assert "Pasadena Chalk Festival" not in answer


def test_burbank_answer_includes_book_festival_and_haunted_adventure() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Burbank?",
        "home_local_guide",
    )

    assert answer
    assert "Burbank Book Festival" in answer
    assert "Haunted Adventure" in answer
    assert "#burbank-book-festival" in answer
    assert "#burbank-haunted-adventure" in answer
    assert "children under 6 are not admitted" in answer


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
    assert "Huntington Beach Oktoberfest" in answer
    assert "September 12-November 8" in answer
    assert "#huntington-beach-oktoberfest" in answer
    assert "SoCal Fitness Festival" not in answer
