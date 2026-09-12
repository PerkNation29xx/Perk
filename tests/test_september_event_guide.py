from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-september-events-2026.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "southern-california-september-events-2026.png"


def test_september_guide_is_substantial_ranked_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Thirty-eight Southern California September plans" in html
    assert 'dateModified": "2026-09-12"' in html
    assert html.count("<h2") >= 41
    for expected in (
        "Maker Faire Orange County",
        "https://oc.makerfaire.com/tickets/",
        "BlizzCon in Anaheim",
        "Santa Ana Fiestas Patrias",
        "https://santa-ana.gov/city-of-santa-ana-to-celebrate-hispanic-heritage-at-fiestas-patrias-festival-and-parade-sept-12-13/",
        'id="santa-ana-fiestas-patrias"',
        "/directory?q=restaurants&amp;city=Santa%20Ana",
        "Dana Point Maritime Festival",
        "https://maritime-fest.org/event/festival-adventure-pass-4/",
        'id="dana-point-maritime-festival"',
        "/directory?city=Dana%20Point",
        "Original Lobster Festival in Fountain Valley",
        "https://www.originallobsterfestival.com/tickets",
        'id="original-lobster-festival"',
        "/directory?q=restaurants&amp;city=Fountain%20Valley",
        "Segerstrom Center Ruby Jubilee",
        "https://www.travelcostamesa.com/events/ruby-jubilee-40th-anniversary-celebration/",
        'id="ruby-jubilee"',
        "/directory?q=restaurants&amp;city=Costa%20Mesa",
        "Caribbean Heritage Festival in Los Angeles",
        "https://www.discoverlosangeles.com/event/2026/09/12/caribbean-heritage-festival",
        'id="caribbean-heritage-festival"',
        "Huntington Beach Oktoberfest",
        "https://www.oldworldhb.com/oktoberfest-orange-county/",
        'id="huntington-beach-oktoberfest"',
        "Gatsby Redux at Greystone",
        "https://beverlyhills.org/1327/Gatsby-Redux---Sept-16-17-19",
        'id="gatsby-redux"',
        "Baja Splash in Long Beach",
        "https://www.aquariumofpacific.org/events/info/baja_splash_cultural_festival/",
        'id="baja-splash"',
        "Pasadena ARTWalk",
        "Pasadena Chalk Festival",
        "Ocean Way Festival",
        "Walt Disney Archives and Disneyland art at Muzeo",
        "https://muzeo.org/plan-your-visit/",
        'id="muzeo-disney-exhibitions"',
        "/directory?q=restaurants&amp;city=Anaheim",
        "Orange County Children's Book Festival",
        "https://orangecoastcollege.edu/news/2026/oc-childrens-book-fest.html",
        'id="oc-childrens-book-festival"',
        "Anaheim Ducks preseason at Honda Center",
        "https://www.nhl.com/ducks/news/ducks-announce-2026-preseason-schedule",
        'id="anaheim-ducks-preseason"',
        "Lucas Museum opening in Los Angeles",
        "https://lucasmuseum.org/about/tickets",
        "/directory?q=restaurants&amp;city=Los%20Angeles",
        "Moompetam American Indian Festival",
        "https://www.aquariumofpacific.org/events/info/moompetam/",
        'id="moompetam"',
        "California Turkish Festival in Long Beach",
        "https://www.visitlongbeach.com/events/california-turkish-festival/",
        'id="california-turkish-festival"',
        "Armenian Film Festival in Glendale",
        'id="armenian-film-festival"',
        "Pasadena Greek Festival",
        "https://www.pasadenagreekfest.com/",
        "Jewel City Concert Series in Glendale",
        'id="jewel-city-concerts"',
        "Burbank Career Transitions Expo",
        "Burbank Autumn Arts Festival",
        'id="burbank-autumn-arts"',
        "Craft Beer LB Fest",
        'id="craft-beer-lb"',
        "Levitt VIBE Pasadena finale",
        "https://www.cityofpasadena.net/parks-and-rec/event/levitt-vibe-pasadena-music-series-2/2026-09-12/",
        'id="levitt-vibe"',
        "LAWineFest in Burbank",
        "https://www.lawinefest.com/",
        'id="la-winefest"',
        "Arcadia Health Fair",
        "Taste of Arcadia",
        "https://tasteofarcadia.com/",
        "Arcadia Mid-Autumn Moon Festival",
        "mooncake making",
        'id="arcadia-moon-festival"',
        "Americana in the Park",
        "Design West Hollywood",
        "Long Beach Burger Week",
        "Orange County Burger Week",
        "https://burgerweeklb.com/",
        "https://burgerweek.com/",
        "https://www.visitwesthollywood.com/events/design-west-hollywood/",
        "Best for:",
        "/directory?city=Burbank",
        "/directory?city=Pasadena",
        "/directory?city=Long%20Beach",
    ):
        assert expected in html
    for expired in ("Pasadena Fiestas Patrias", "Orange International Street Fair", "Long Beach Comic Con", "Fiesta Hermosa", "Long Beach Greek Festival", "Southern California Open in Glendale"):
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


def test_september_guide_routes_image_homepages_and_sitemap() -> None:
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
        assert "Updated September 12 · September guide" in response.text
        assert "Thirty-eight Southern California September plans, ranked." in response.text
        assert "today's free Caribbean Heritage Festival in Los Angeles" in response.text
        assert "Orange County Children's Book Festival" in response.text
        assert "Anaheim Ducks preseason" in response.text
        assert "Huntington Beach Oktoberfest" in response.text
        assert "Gatsby Redux at Greystone" in response.text
        assert "Long Beach's Baja Splash" in response.text
        assert "Santa Ana Fiestas Patrias" in response.text
        assert "Dana Point's Maritime Festival" in response.text
        assert "Segerstrom's free Ruby Jubilee" in response.text
        assert "Fountain Valley's Original Lobster Festival" in response.text
        assert "free California Turkish Festival" in response.text
        assert "the Walt Disney Archives at Muzeo" in response.text
        assert "Maker Faire OC" in response.text
        assert "the Lucas Museum opening" in response.text
        assert "Dine LA's final day is organized" not in response.text
        assert "Fourteen Southern California summer plans, ranked." not in response.text
        assert "Maker Faire OC turns invention into a hands-on weekend" in response.text
        assert "J. Cole brings The Fall-Off Tour to LA" not in response.text
        assert "Santa Ana Fiestas Patrias brings a free festival and parade downtown" in response.text
        assert "Arcadia's August finale pairs Broadway music with a garden picnic." not in response.text
        assert '<template>\n  <section class="section homeArticleSection" id="pasadena-august-2026-guide">' in response.text
        assert '<template>\n  <section class="section homeArticleSection" id="long-beach-august-2026-guide">' in response.text

    root_sitemap = client.get("/sitemap.xml")
    white_sitemap = client.get("/white/sitemap.xml", follow_redirects=False)
    assert root_sitemap.status_code == 200
    assert white_sitemap.status_code == 308
    assert white_sitemap.headers["location"] == "/sitemap.xml"
    assert "<loc>https://perknation.app/articles/southern-california-september-events-2026</loc>" in root_sitemap.text
    assert "/events/j-cole-los-angeles" not in root_sitemap.text

    events_data = client.get("/assets/events-data.js")
    assert events_data.status_code == 200
    assert "j-cole-los-angeles" not in events_data.text


def test_september_guide_is_current_in_public_review_answers() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Southern California?",
        "home_local_guide",
    )

    assert answer
    assert "Thirty-eight Southern California September plans" in answer
    assert "Santa Ana Fiestas Patrias" in answer
    assert "Dana Point Maritime Festival" in answer
    assert "Ruby Jubilee" in answer
    assert "Moompetam" in answer
    assert "Levitt VIBE" in answer
    assert "LAWineFest" in answer
    assert "Craft Beer LB Fest" in answer
    assert "Autumn Arts Festival" in answer
    assert "Taste of Arcadia" in answer
    assert "Mid-Autumn Moon Festival" in answer
    assert "Lucas Museum" in answer
    assert "Maker Faire Orange County" in answer
    assert "Armenian Film Festival" in answer
    assert "Original Lobster Festival" in answer
    assert "California Turkish Festival" in answer
    assert "Walt Disney Archives" in answer
    assert "Caribbean Heritage Festival" in answer
    assert "Orange County Children's Book Festival" in answer
    assert "Anaheim Ducks preseason" in answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "Gatsby Redux" in answer
    assert "Baja Splash" in answer
    assert "/articles/southern-california-september-events-2026" in answer
    assert "Dine LA 2026 city guides" not in answer


def test_orange_county_city_answers_include_new_immediate_weekend_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Santa Ana Fiestas Patrias" in answer
    assert "Dana Point's Maritime Festival" in answer
    assert "Ruby Jubilee" in answer
    assert "Original Lobster Festival" in answer
    assert "Walt Disney Archives" in answer
    assert "#santa-ana-fiestas-patrias" in answer
    assert "Orange County Children's Book Festival" in answer
    assert "#oc-childrens-book-festival" in answer
    assert "Anaheim Ducks preseason" in answer
    assert "#anaheim-ducks-preseason" in answer


def test_pasadena_answer_no_longer_promotes_expired_fiestas_patrias() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Pasadena?",
        "home_local_guide",
    )

    assert answer
    assert "Levitt VIBE" in answer
    assert "#levitt-vibe" in answer
    assert "Pasadena Fiestas Patrias" not in answer


def test_long_beach_answer_includes_free_turkish_festival() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Long Beach this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "California Turkish Festival" in answer
    assert "September 13" in answer
    assert "#california-turkish-festival" in answer
    assert "Baja Splash" in answer
    assert "#baja-splash" in answer


def test_huntington_beach_answer_includes_current_oktoberfest() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Huntington Beach?",
        "home_local_guide",
    )

    assert answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "September 12-November 8" in answer
    assert "#huntington-beach-oktoberfest" in answer
