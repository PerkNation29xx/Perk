from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-september-events-2026.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "southern-california-september-events-2026.png"


def test_september_guide_is_substantial_ranked_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Thirty-seven Southern California September plans" in html
    assert 'dateModified": "2026-09-16"' in html
    assert html.count("<h2") >= 40
    for expected in (
        "Angels vs. Mariners in Anaheim",
        "https://www.mlb.com/angels",
        'id="angels-mariners"',
        "Punk Night at the Pier",
        "https://www.santamonica.com/event/punk-night-at-the-pier-locals-night/",
        'id="santa-monica-locals-night"',
        "Seconds at PCH Food Fest",
        "https://www.visitlongbeach.com/events/seconds-at-pch-food-fest/",
        'id="seconds-at-pch-food-fest"',
        "Halloween at Kidspace",
        "https://kidspacemuseum.org/event/halloween-at-kidspace-3/",
        'id="kidspace-halloween"',
        "Thai Fest by the Beach in Santa Monica",
        "https://www.thaifestbythebeach.com/",
        'id="thai-fest-by-the-beach"',
        "California Coastal Cleanup Day",
        "https://www.coastal.ca.gov/publiced/ccd/ccd.html",
        'id="coastal-cleanup-day"',
        "Lucha Libre Weekend at MOLAA",
        "https://molaa.org/2026-lucha-libre",
        'id="molaa-lucha-libre"',
        "Love Letters to L.A. at the Autry",
        "https://theautry.org/events/autry-outdoors/love-letters-la-autry-block-party",
        'id="autry-block-party"',
        "Los Angeles Libros Festival",
        "https://www.lapl.org/libros",
        'id="los-angeles-libros"',
        "Queen Mary's Dark Harbor",
        "https://www.queenmary.com/seasonal-events.htm",
        'id="queen-mary-dark-harbor"',
        "Casa Verdugo Library's 75th anniversary",
        'id="casa-verdugo-75"',
        "Golden State Tattoo Expo in Pasadena",
        "https://www.visitpasadena.com/events/golden-state-tattoo-expo/",
        'id="golden-state-tattoo-expo"',
        "SUGAR SKULL! at Segerstrom",
        'id="sugar-skull-segerstrom"',
        "/directory?q=restaurants&amp;city=Costa%20Mesa",
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
        "Zootoberfest at the L.A. Zoo",
        "https://lazoo.org/plan-your-visit/special-experiences/zootoberfest/",
        'id="zootoberfest"',
        "State of the Arts in Long Beach",
        "https://artslb.org/stateofthearts/",
        'id="state-of-the-arts-long-beach"',
        "Anaheim Craft &amp; Vintage Fair",
        'id="anaheim-craft-vintage"',
        "Santa Monica Hispanic Heritage programs",
        "https://www.santamonica.gov/blog/santa-monica-commemorates-hispanic-heritage-month-2026",
        'id="santa-monica-hispanic-heritage"',
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
        "Armenian Film Festival in Glendale",
        'id="armenian-film-festival"',
        "Pasadena Greek Festival",
        "https://www.pasadenagreekfest.com/",
        "Jewel City Concert Series in Glendale",
        'id="jewel-city-concerts"',
        "Burbank Career Transitions Expo",
        "Burbank Autumn Arts Festival",
        'id="burbank-autumn-arts"',
        "Taste of Arcadia",
        "https://tasteofarcadia.com/",
        "Arcadia Mid-Autumn Moon Festival",
        "mooncake making",
        'id="arcadia-moon-festival"',
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
    for expired in (
        "Caribbean Heritage Festival",
        "Ocean Way Festival",
        "Craft Beer LB Fest",
        "Levitt VIBE",
        "Arcadia Health Fair",
        "Rose Bowl home opener",
        "Tongva Twilight",
        "Pasadena Fiestas Patrias",
        "Orange International Street Fair",
        "Long Beach Comic Con",
        "Fiesta Hermosa",
        "Long Beach Greek Festival",
        "Southern California Open in Glendale",
        "Maker Faire Orange County",
        "BlizzCon in Anaheim",
        "Santa Ana Fiestas Patrias",
        "Dana Point Maritime Festival",
        "Original Lobster Festival",
        "Ruby Jubilee",
        "Moompetam",
        "California Turkish Festival",
        "LAWineFest",
        "Americana in the Park",
        "OneRepublic with fireworks",
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
        assert "Updated September 16 · September guide" in response.text
        assert "Thirty-seven Southern California September plans, ranked." in response.text
        assert "Angels' final Seattle game" in response.text
        assert "Santa Monica Pier's free Locals' Night" in response.text
        assert "Long Beach's food passport" in response.text
        assert "Kidspace Halloween" in response.text
        assert "Thai Fest by the Beach" in response.text
        assert "Long Beach Burger Week" in response.text
        assert "Coastal Cleanup Day" in response.text
        assert "MOLAA Lucha Libre" in response.text
        assert "the Autry Block Party" in response.text
        assert "Los Angeles Libros" in response.text
        assert "Dark Harbor" in response.text
        assert "Zootoberfest" in response.text
        assert "Dine LA's final day is organized" not in response.text
        assert "Fourteen Southern California summer plans, ranked." not in response.text
        assert "Free Locals' Night brings punk, salsa, vendors, and family activities to Santa Monica Pier" in response.text
        assert "J. Cole brings The Fall-Off Tour to LA" not in response.text
        assert "Thai Fest brings free food and culture programming to Santa Monica Pier" in response.text
        assert "Maker Faire OC turns invention into a hands-on weekend" not in response.text
        assert "Santa Ana Fiestas Patrias brings a free festival and parade downtown" not in response.text
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
    assert "Thirty-seven Southern California September plans" in answer
    assert "Angels-Mariners" in answer
    assert "Locals' Night" in answer
    assert "Seconds at PCH Food Fest" in answer
    assert "Halloween at Kidspace" in answer
    assert "Thai Fest by the Beach" in answer
    assert "California Coastal Cleanup Day" in answer
    assert "Lucha Libre weekend" in answer
    assert "Autry Block Party" in answer
    assert "Los Angeles Libros Festival" in answer
    assert "Dark Harbor" in answer
    assert "Casa Verdugo" in answer
    assert "Golden State Tattoo Expo" in answer
    assert "SUGAR SKULL!" in answer
    assert "Autumn Arts Festival" in answer
    assert "Taste of Arcadia" in answer
    assert "Mid-Autumn Moon Festival" in answer
    assert "Lucas Museum" in answer
    assert "Armenian Film Festival" in answer
    assert "Walt Disney Archives" in answer
    assert "Zootoberfest" in answer
    assert "State of the Arts" in answer
    assert "Craft & Vintage Fair" in answer
    assert "Santa Monica Hispanic Heritage" in answer
    assert "Orange County Children's Book Festival" in answer
    assert "Anaheim Ducks preseason" in answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "Gatsby Redux" in answer
    assert "Baja Splash" in answer
    assert "/articles/southern-california-september-events-2026" in answer
    assert "Dine LA 2026 city guides" not in answer


def test_orange_county_city_answers_include_current_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Angels-Mariners" in answer
    assert "SUGAR SKULL!" in answer
    assert "Walt Disney Archives" in answer
    assert "#angels-mariners" in answer
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
    assert "Pasadena ARTWalk" in answer
    assert "Pasadena Greek Festival" in answer
    assert "Pasadena Chalk Festival" in answer
    assert "Pasadena Fiestas Patrias" not in answer


def test_long_beach_answer_includes_food_fest_dark_harbor_cleanup_and_molaa() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Long Beach this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "Seconds at PCH" in answer
    assert "#seconds-at-pch-food-fest" in answer
    assert "Dark Harbor" in answer
    assert "September 18-November 1" in answer
    assert "#queen-mary-dark-harbor" in answer
    assert "State of the Arts" in answer
    assert "#state-of-the-arts-long-beach" in answer
    assert "California Coastal Cleanup Day" in answer
    assert "#coastal-cleanup-day" in answer
    assert "MOLAA" in answer
    assert "#molaa-lucha-libre" in answer
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
