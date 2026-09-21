from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "southern-california-september-events-2026.html"
IMAGE = ROOT / "app" / "web" / "home_portal" / "assets" / "articles" / "southern-california-september-events-2026.png"


def test_september_guide_is_substantial_ranked_and_reader_facing() -> None:
    html = ARTICLE.read_text(encoding="utf-8")

    assert "Thirty Southern California September plans" in html
    assert 'dateModified": "2026-09-21"' in html
    assert html.count("<h2") >= 33
    for expected in (
        "Seconds at PCH Food Fest",
        "https://www.visitlongbeach.com/events/seconds-at-pch-food-fest/",
        'id="seconds-at-pch-food-fest"',
        "Halloween at Kidspace",
        "https://kidspacemuseum.org/event/halloween-at-kidspace-3/",
        'id="kidspace-halloween"',
        "Spider Pavilion at the Natural History Museum",
        "https://nhm.org/experience-nhm/exhibitions-natural-history-museum/spider-pavilion",
        'id="spider-pavilion"',
        "Into the Woods",
        "https://www.scr.org/plays/productions/26-27-season/into-the-woods/",
        'id="into-the-woods-costa-mesa"',
        "at Pasadena Playhouse",
        "https://www.pasadenaplayhouse.org/event/the-visit/",
        'id="the-visit-pasadena"',
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
        "Westminster Fall Festival",
        "https://www.westminster-ca.gov/departments/community-services/fall-festival",
        'id="westminster-fall-festival"',
        "SteelCraft Long Beach Oktoberfest",
        "https://steelcraftlb.com/events/oktoberfest-at-steelcraft-long-beach/",
        'id="steelcraft-long-beach-oktoberfest"',
        "Laura Aguilar: Day of the Dead at The Huntington",
        "https://www.huntington.org/exhibitions",
        'id="laura-aguilar-day-of-the-dead"',
        "Ranchos Walk in Long Beach",
        "https://longbeach.gov/sustainability/about-us/events/ranchos-walk/",
        'id="ranchos-walk"',
        "Spinal Dread at Anaheim Central Library",
        "https://www.anaheim.net/6686/Spinal-Dread-Horror-Literature-and-Cultu",
        'id="spinal-dread-anaheim"',
        "/directory?q=restaurants&amp;city=Costa%20Mesa",
        "Huntington Beach Oktoberfest",
        "https://www.oldworldhb.com/oktoberfest-orange-county/",
        'id="huntington-beach-oktoberfest"',
        "Baja Splash in Long Beach",
        "https://www.aquariumofpacific.org/events/info/baja_splash_cultural_festival/",
        'id="baja-splash"',
        "Jane Austen UnScripted in West Hollywood",
        "https://www.weho.org/Home/Components/Calendar/Event/32133/1106",
        'id="weho-jane-austen"',
        "Pasadena Chalk Festival",
        "dublab Open Air in Santa Monica",
        'id="santa-monica-dublab"',
        "Walt Disney Archives and Disneyland art at Muzeo",
        "https://muzeo.org/plan-your-visit/",
        'id="muzeo-disney-exhibitions"',
        "/directory?q=restaurants&amp;city=Anaheim",
        "Anaheim Ducks preseason at Honda Center",
        "https://www.nhl.com/ducks/news/ducks-announce-2026-preseason-schedule",
        'id="anaheim-ducks-preseason"',
        "Lucas Museum opening in Los Angeles",
        "https://lucasmuseum.org/about/tickets",
        "/directory?q=restaurants&amp;city=Los%20Angeles",
        "Jewel City Concert Series in Glendale",
        'id="jewel-city-concerts"',
        "Arcadia Mid-Autumn Moon Festival",
        "mooncake making",
        'id="arcadia-moon-festival"',
        "Design West Hollywood",
        "Orange County Burger Week",
        "https://burgerweek.com/",
        "https://www.visitwesthollywood.com/events/design-west-hollywood/",
        "Glendale Tech Week",
        "https://www.glendaletechweek.com/",
        'id="glendale-tech-week"',
        "/directory?q=technology&amp;city=Glendale",
        "Glendale International Film Festival",
        "https://glendaleiff.org/festival-schedule-26/",
        'id="glendale-international-film-festival"',
        "/directory?q=entertainment&amp;city=Glendale",
        "Classic Film Under the Stars in Glendale",
        "https://www.glendaleca.gov/Home/Components/Calendar/Event/55835/18",
        'id="classic-film-glendale"',
        "Long Beach Urban Farm Dinner",
        "https://primalalchemy.com/",
        'id="long-beach-urban-farm-dinner"',
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
        "Angels vs. Mariners in Anaheim",
        'id="angels-mariners"',
        "Punk Night at the Pier",
        'id="santa-monica-locals-night"',
        "Casa Verdugo Library's 75th anniversary",
        'id="casa-verdugo-75"',
        "Burbank Career Transitions Expo",
        'id="burbank-careers"',
        "California Coastal Cleanup Day",
        'id="coastal-cleanup-day"',
        "Gatsby Redux at Greystone",
        'id="gatsby-redux"',
        "State of the Arts in Long Beach",
        'id="state-of-the-arts-long-beach"',
        "Anaheim Craft &amp; Vintage Fair",
        'id="anaheim-craft-vintage"',
        "Burbank Autumn Arts Festival",
        'id="burbank-autumn-arts"',
        "Taste of Arcadia",
        'id="taste-of-arcadia"',
        "The Great Outdoors at Greystone",
        'id="greystone-outdoors"',
        "Thai Fest by the Beach",
        'id="thai-fest-by-the-beach"',
        "Dodgers vs. Giants",
        'id="dodgers-giants"',
        "Long Beach Burger Week",
        'id="long-beach-burger-week"',
        "Zootoberfest",
        'id="zootoberfest"',
        "San Clemente Car Show",
        'id="san-clemente-car-show"',
        "Pasadena ARTWalk",
        'id="pasadena-artwalk"',
        "Orange County Children's Book Festival",
        'id="oc-childrens-book-festival"',
        "SUGAR SKULL!",
        'id="sugar-skull-segerstrom"',
        "Armenian Film Festival",
        'id="armenian-film-festival"',
        "Pasadena Greek Festival",
        'id="pasadena-greek-festival"',
        "Golden State Tattoo Expo",
        'id="golden-state-tattoo-expo"',
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
        assert "Updated September 21 · September guide" in response.text
        assert "Thirty Southern California September plans, ranked." in response.text
        assert "Angels' final Seattle game" not in response.text
        assert "Santa Monica Pier's free Locals' Night" not in response.text
        assert "Long Beach's food passport" in response.text
        assert "Kidspace Halloween" in response.text
        assert "Thai Fest by the Beach" not in response.text
        assert "Dodgers-Giants" not in response.text
        assert "Spider Pavilion" in response.text
        assert "Into the Woods" in response.text
        assert "Pasadena Playhouse's The Visit" in response.text
        assert "Westminster Fall Festival" in response.text
        assert "SteelCraft Long Beach Oktoberfest" in response.text
        assert "MOLAA Lucha Libre" in response.text
        assert "the Autry Block Party" in response.text
        assert "Los Angeles Libros" in response.text
        assert "Dark Harbor" in response.text
        assert "Glendale Tech Week and film festival" in response.text
        assert "Laura Aguilar exhibition" in response.text
        assert "Ranchos Walk" in response.text
        assert "Spinal Dread" in response.text
        assert "Urban Farm Dinner" in response.text
        assert "Dine LA's final day is organized" not in response.text
        assert "Fourteen Southern California summer plans, ranked." not in response.text
        assert "Free Locals' Night brings punk, salsa, vendors, and family activities to Santa Monica Pier" not in response.text
        assert "Spider Pavilion opens with hundreds of orb weavers, webs, and educator-led science" in response.text
        assert "J. Cole brings The Fall-Off Tour to LA" not in response.text
        assert "Thai Fest brings free food and culture programming to Santa Monica Pier" not in response.text
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
    assert "Thirty Southern California September plans" in answer
    assert "Angels-Mariners" not in answer
    assert "Locals' Night" not in answer
    assert "Seconds at PCH Food Fest" in answer
    assert "Halloween at Kidspace" in answer
    assert "Thai Fest by the Beach" not in answer
    assert "Dodgers-Giants" not in answer
    assert "Spider Pavilion" in answer
    assert "San Clemente Car Show" not in answer
    assert "Jane Austen UnScripted" in answer
    assert "Into the Woods" in answer
    assert "Westminster Fall Festival" in answer
    assert "SteelCraft Long Beach Oktoberfest" in answer
    assert "Lucha Libre weekend" in answer
    assert "Autry Block Party" in answer
    assert "Los Angeles Libros Festival" in answer
    assert "Dark Harbor" in answer
    assert "Casa Verdugo" not in answer
    assert "Laura Aguilar" in answer
    assert "Ranchos Walk" in answer
    assert "Spinal Dread" in answer
    assert "Golden State Tattoo Expo" not in answer
    assert "SUGAR SKULL!" not in answer
    assert "Into the Woods" in answer
    assert "Autumn Arts Festival" not in answer
    assert "Taste of Arcadia" not in answer
    assert "Mid-Autumn Moon Festival" in answer
    assert "Lucas Museum" in answer
    assert "Armenian Film Festival" not in answer
    assert "Walt Disney Archives" in answer
    assert "Zootoberfest" not in answer
    assert "State of the Arts" not in answer
    assert "Craft & Vintage Fair" not in answer
    assert "dublab Open Air" in answer
    assert "Orange County Children's Book Festival" not in answer
    assert "Anaheim Ducks preseason" in answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "Gatsby Redux" not in answer
    assert "Baja Splash" in answer
    assert "Glendale Tech Week" in answer
    assert "Glendale International Film Festival" in answer
    assert "The Visit" in answer
    assert "Classic Film Under the Stars" in answer
    assert "Urban Farm Dinner" in answer
    assert "/articles/southern-california-september-events-2026" in answer
    assert "Dine LA 2026 city guides" not in answer


def test_orange_county_city_answers_include_current_plans() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Santa Ana and Costa Mesa this weekend?",
        "home_local_guide",
    )

    assert answer
    assert "San Clemente Car Show" not in answer
    assert "SUGAR SKULL!" not in answer
    assert "Into the Woods" in answer
    assert "#into-the-woods-costa-mesa" in answer
    assert "Walt Disney Archives" in answer
    assert "#san-clemente-car-show" not in answer
    assert "Orange County Children's Book Festival" not in answer
    assert "#oc-childrens-book-festival" not in answer
    assert "Anaheim Ducks' remaining preseason" in answer
    assert "#anaheim-ducks-preseason" in answer
    assert "Westminster" in answer
    assert "#westminster-fall-festival" in answer
    assert "Spinal Dread" in answer
    assert "#spinal-dread-anaheim" in answer


def test_pasadena_answer_no_longer_promotes_expired_fiestas_patrias() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Pasadena?",
        "home_local_guide",
    )

    assert answer
    assert "Pasadena ARTWalk" not in answer
    assert "Pasadena Greek Festival" not in answer
    assert "The Visit" in answer
    assert "#the-visit-pasadena" in answer
    assert "Pasadena Chalk Festival" in answer
    assert "Laura Aguilar" in answer
    assert "#laura-aguilar-day-of-the-dead" in answer
    assert "Pasadena Fiestas Patrias" not in answer


def test_long_beach_answer_includes_food_fest_dark_harbor_steelcraft_and_molaa() -> None:
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
    assert "SteelCraft" in answer
    assert "#steelcraft-long-beach-oktoberfest" in answer
    assert "MOLAA" in answer
    assert "#molaa-lucha-libre" in answer
    assert "Baja Splash" in answer
    assert "#baja-splash" in answer
    assert "Ranchos Walk" in answer
    assert "#ranchos-walk" in answer
    assert "Urban Farm Dinner" in answer
    assert "#long-beach-urban-farm-dinner" in answer


def test_huntington_beach_answer_includes_current_oktoberfest() -> None:
    answer = _public_review_live_query_response(
        "What current events are covered in Huntington Beach?",
        "home_local_guide",
    )

    assert answer
    assert "Huntington Beach Oktoberfest" in answer
    assert "September 12-November 8" in answer
    assert "#huntington-beach-oktoberfest" in answer
