from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RestaurantKnowledge
from app.services.restaurant_vector_rag import semantic_search_restaurants


@dataclass(frozen=True)
class RestaurantSeed:
    slug: str
    name: str
    city: str
    neighborhood: str
    cuisine: str
    price_tier: str
    address: str
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    summary: str
    highlights: tuple[str, ...]
    website_url: str


def d(value: str) -> Decimal:
    return Decimal(value)


LA_RESTAURANT_SEED: tuple[RestaurantSeed, ...] = (
    RestaurantSeed(
        slug="providence-hollywood",
        name="Providence",
        city="Los Angeles",
        neighborhood="Hollywood",
        cuisine="Seafood tasting",
        price_tier="$$$$",
        address="5955 Melrose Ave, Los Angeles, CA 90038",
        latitude=d("34.0834571"),
        longitude=d("-118.3197689"),
        summary="Refined seafood tasting menus with deep wine pairing programs and polished service.",
        highlights=("Michelin-level dining", "Seasonal tasting", "Special-occasion destination"),
        website_url="https://www.providencela.com/",
    ),
    RestaurantSeed(
        slug="kato-arts-district",
        name="Kato",
        city="Los Angeles",
        neighborhood="Arts District",
        cuisine="Taiwanese-American tasting",
        price_tier="$$$$",
        address="777 S Alameda St Bldg 1, Los Angeles, CA 90021",
        latitude=d("34.0343000"),
        longitude=d("-118.2379000"),
        summary="Precision-driven tasting menu blending Taiwanese influence and contemporary California sourcing.",
        highlights=("Chef-driven tasting", "Modern plating", "Celebration dining"),
        website_url="https://www.katorestaurant.com/",
    ),
    RestaurantSeed(
        slug="n-naka-palms",
        name="n/naka",
        city="Los Angeles",
        neighborhood="Palms",
        cuisine="Kaiseki",
        price_tier="$$$$",
        address="3455 Overland Ave, Los Angeles, CA 90034",
        latitude=d("34.0258000"),
        longitude=d("-118.4104000"),
        summary="Contemporary kaiseki with delicate, seasonal courses and meticulous pacing.",
        highlights=("Japanese fine dining", "Seasonal menu", "Reservation-only"),
        website_url="https://www.n-naka.com/",
    ),
    RestaurantSeed(
        slug="bestia-arts-district",
        name="Bestia",
        city="Los Angeles",
        neighborhood="Arts District",
        cuisine="Italian",
        price_tier="$$$",
        address="2121 E 7th Pl, Los Angeles, CA 90021",
        latitude=d("34.0335000"),
        longitude=d("-118.2292000"),
        summary="High-energy Italian kitchen known for house-made charcuterie and wood-fired mains.",
        highlights=("Lively dining room", "House charcuterie", "Pasta and pizza"),
        website_url="https://bestiala.com/",
    ),
    RestaurantSeed(
        slug="bavel-arts-district",
        name="Bavel",
        city="Los Angeles",
        neighborhood="Arts District",
        cuisine="Middle Eastern",
        price_tier="$$$",
        address="500 Mateo St #102, Los Angeles, CA 90013",
        latitude=d("34.0402000"),
        longitude=d("-118.2301000"),
        summary="Modern Middle Eastern plates centered on open-fire cooking and shareable mezze.",
        highlights=("Wood-fire cooking", "Group-friendly", "Strong cocktail program"),
        website_url="https://baveldtla.com/",
    ),
    RestaurantSeed(
        slug="republique-hancock-park",
        name="Republique",
        city="Los Angeles",
        neighborhood="Hancock Park",
        cuisine="French-Californian",
        price_tier="$$$",
        address="624 S La Brea Ave, Los Angeles, CA 90036",
        latitude=d("34.0646000"),
        longitude=d("-118.3441000"),
        summary="Grand all-day destination for pastries, weekend brunch, and elegant dinner service.",
        highlights=("Historic building", "Pastry counter", "Date-night favorite"),
        website_url="https://www.republiquela.com/",
    ),
    RestaurantSeed(
        slug="osteria-mozza-hollywood",
        name="Osteria Mozza",
        city="Los Angeles",
        neighborhood="Hollywood",
        cuisine="Italian",
        price_tier="$$$$",
        address="6602 Melrose Ave, Los Angeles, CA 90038",
        latitude=d("34.0836000"),
        longitude=d("-118.3363000"),
        summary="Upscale Italian classic with celebrated mozzarella bar and robust wine list.",
        highlights=("Mozzarella bar", "Classic Italian", "Fine wine"),
        website_url="https://www.osteriamozza.com/",
    ),
    RestaurantSeed(
        slug="mother-wolf-hollywood",
        name="Mother Wolf",
        city="Los Angeles",
        neighborhood="Hollywood",
        cuisine="Roman Italian",
        price_tier="$$$",
        address="1545 Wilcox Ave, Los Angeles, CA 90028",
        latitude=d("34.0995000"),
        longitude=d("-118.3304000"),
        summary="Roman-style dishes in a cinematic dining room inspired by classic trattorie.",
        highlights=("Roman pizza", "Design-forward interior", "Large-group energy"),
        website_url="https://www.motherwolfla.com/",
    ),
    RestaurantSeed(
        slug="majordomo-chinatown",
        name="Majordomo",
        city="Los Angeles",
        neighborhood="Chinatown",
        cuisine="Korean-American",
        price_tier="$$$",
        address="1725 Naud St, Los Angeles, CA 90012",
        latitude=d("34.0679000"),
        longitude=d("-118.2308000"),
        summary="Large-format share plates and bold flavors from the Momofuku family kitchen.",
        highlights=("Group meals", "Large-format proteins", "Industrial-chic space"),
        website_url="https://majordomo.la/",
    ),
    RestaurantSeed(
        slug="musso-and-frank-hollywood",
        name="Musso & Frank Grill",
        city="Los Angeles",
        neighborhood="Hollywood",
        cuisine="Classic steakhouse",
        price_tier="$$$",
        address="6667 Hollywood Blvd, Hollywood, CA 90028",
        latitude=d("34.1018000"),
        longitude=d("-118.3311000"),
        summary="Historic Hollywood institution serving classic steaks, martinis, and old-school service.",
        highlights=("Iconic LA history", "Steakhouse classics", "Old Hollywood atmosphere"),
        website_url="https://mussoandfrank.com/",
    ),
    RestaurantSeed(
        slug="gjelina-venice",
        name="Gjelina",
        city="Los Angeles",
        neighborhood="Venice",
        cuisine="Californian",
        price_tier="$$$",
        address="1429 Abbot Kinney Blvd, Venice, CA 90291",
        latitude=d("33.9927000"),
        longitude=d("-118.4699000"),
        summary="Produce-driven Californian menu with wood-fired plates and bustling indoor-outdoor seating.",
        highlights=("Abbot Kinney staple", "Vegetable-forward", "All-day crowd"),
        website_url="https://www.gjelina.com/",
    ),
    RestaurantSeed(
        slug="felix-trattoria-venice",
        name="Felix Trattoria",
        city="Los Angeles",
        neighborhood="Venice",
        cuisine="Italian",
        price_tier="$$$",
        address="1023 Abbot Kinney Blvd, Venice, CA 90291",
        latitude=d("33.9925000"),
        longitude=d("-118.4726000"),
        summary="Pasta-focused Italian destination with handmade doughs and rotating seasonal sauces.",
        highlights=("Handmade pasta", "Abbot Kinney", "Chef-led menu"),
        website_url="https://felixla.com/",
    ),
    RestaurantSeed(
        slug="hatchet-hall-culver-city",
        name="Hatchet Hall",
        city="Culver City",
        neighborhood="Culver City",
        cuisine="Southern-Californian",
        price_tier="$$$",
        address="12517 W Washington Blvd, Los Angeles, CA 90066",
        latitude=d("33.9959000"),
        longitude=d("-118.4286000"),
        summary="Wood-fire Southern-Californian cooking in a warm room with strong whiskey selections.",
        highlights=("Wood-fire kitchen", "Whiskey list", "Comfort classics"),
        website_url="https://www.hatchethallla.com/",
    ),
    RestaurantSeed(
        slug="holbox-south-la",
        name="Holbox",
        city="Los Angeles",
        neighborhood="South LA",
        cuisine="Mexican seafood",
        price_tier="$$",
        address="3655 S Grand Ave C9, Los Angeles, CA 90007",
        latitude=d("34.0190000"),
        longitude=d("-118.2780000"),
        summary="Seafood counter celebrated for regional Mexican seafood, tostadas, and ceviches.",
        highlights=("Counter service", "Destination seafood", "Michelin-recognized casual"),
        website_url="https://www.holboxla.com/",
    ),
    RestaurantSeed(
        slug="guelaguetza-koreatown",
        name="Guelaguetza",
        city="Los Angeles",
        neighborhood="Koreatown",
        cuisine="Oaxacan",
        price_tier="$$",
        address="3014 W Olympic Blvd, Los Angeles, CA 90006",
        latitude=d("34.0521000"),
        longitude=d("-118.2997000"),
        summary="Landmark Oaxacan restaurant known for complex mole flights and family-style feasts.",
        highlights=("Mole specialties", "Family-style portions", "Cultural institution"),
        website_url="https://www.ilovemole.com/",
    ),
    RestaurantSeed(
        slug="parks-bbq-koreatown",
        name="Parks BBQ",
        city="Los Angeles",
        neighborhood="Koreatown",
        cuisine="Korean BBQ",
        price_tier="$$$",
        address="955 S Vermont Ave G, Los Angeles, CA 90006",
        latitude=d("34.0558000"),
        longitude=d("-118.2917000"),
        summary="Premium Korean BBQ spot known for marinated meats and attentive tabletop grilling service.",
        highlights=("Premium cuts", "KBBQ classic", "Dinner hotspot"),
        website_url="https://parksbbq.com/",
    ),
    RestaurantSeed(
        slug="quarters-kbbq-koreatown",
        name="Quarters Korean BBQ",
        city="Los Angeles",
        neighborhood="Koreatown",
        cuisine="Korean BBQ",
        price_tier="$$",
        address="3465 W 6th St #C-130, Los Angeles, CA 90020",
        latitude=d("34.0636000"),
        longitude=d("-118.2973000"),
        summary="Modern KBBQ room with lively energy and combo sets popular with groups.",
        highlights=("Group dining", "Lively atmosphere", "Central K-town"),
        website_url="https://quarterskbbq.com/",
    ),
    RestaurantSeed(
        slug="sun-nong-dan-koreatown",
        name="Sun Nong Dan",
        city="Los Angeles",
        neighborhood="Koreatown",
        cuisine="Korean soups and braises",
        price_tier="$$",
        address="3470 W 6th St #7, Los Angeles, CA 90020",
        latitude=d("34.0633000"),
        longitude=d("-118.2974000"),
        summary="Korean comfort specialist known for galbi jjim and late-night soups.",
        highlights=("Late-night option", "Braised short rib", "Comfort food"),
        website_url="https://www.sunnongdan.com/",
    ),
    RestaurantSeed(
        slug="jitlada-thai-town",
        name="Jitlada",
        city="Los Angeles",
        neighborhood="Thai Town",
        cuisine="Southern Thai",
        price_tier="$$",
        address="5233 W Sunset Blvd, Los Angeles, CA 90027",
        latitude=d("34.0981000"),
        longitude=d("-118.3009000"),
        summary="Long-running Thai Town favorite known for spicy Southern Thai specialties.",
        highlights=("Thai heat", "Deep regional menu", "LA classic"),
        website_url="https://jitladala.com/",
    ),
    RestaurantSeed(
        slug="night-market-song-silver-lake",
        name="Night + Market Song",
        city="Los Angeles",
        neighborhood="Silver Lake",
        cuisine="Thai",
        price_tier="$$",
        address="3322 W Sunset Blvd, Los Angeles, CA 90026",
        latitude=d("34.0875000"),
        longitude=d("-118.2789000"),
        summary="Party-energy Thai kitchen with bold flavors, natural wine, and share plates.",
        highlights=("Lively scene", "Thai staples", "Share plates"),
        website_url="https://www.nightmarketla.com/",
    ),
    RestaurantSeed(
        slug="langers-westlake",
        name="Langer's Delicatessen",
        city="Los Angeles",
        neighborhood="Westlake",
        cuisine="Jewish deli",
        price_tier="$$",
        address="704 S Alvarado St, Los Angeles, CA 90057",
        latitude=d("34.0603000"),
        longitude=d("-118.2763000"),
        summary="Legendary deli destination best known for hand-cut pastrami sandwiches.",
        highlights=("Iconic pastrami", "Historic deli", "Classic lunch stop"),
        website_url="https://www.langersdeli.com/",
    ),
    RestaurantSeed(
        slug="howlins-rays-chinatown",
        name="Howlin' Ray's",
        city="Los Angeles",
        neighborhood="Chinatown",
        cuisine="Hot chicken",
        price_tier="$$",
        address="727 N Broadway #128, Los Angeles, CA 90012",
        latitude=d("34.0604000"),
        longitude=d("-118.2389000"),
        summary="Cult-favorite Nashville hot chicken known for long lines and spice-forward sandwiches.",
        highlights=("Hot chicken", "Casual counter", "High demand"),
        website_url="https://www.howlinsrays.com/",
    ),
    RestaurantSeed(
        slug="sonoratown-dtla",
        name="Sonoratown",
        city="Los Angeles",
        neighborhood="Downtown LA",
        cuisine="Sonoran Mexican",
        price_tier="$",
        address="208 E 8th St, Los Angeles, CA 90014",
        latitude=d("34.0415000"),
        longitude=d("-118.2503000"),
        summary="Compact taqueria celebrated for flour tortillas and mesquite-grilled meats.",
        highlights=("Fresh tortillas", "Casual quick stop", "Fan-favorite tacos"),
        website_url="https://www.sonoratown.com/",
    ),
    RestaurantSeed(
        slug="mariscos-jalisco-boyle-heights",
        name="Mariscos Jalisco",
        city="Los Angeles",
        neighborhood="Boyle Heights",
        cuisine="Seafood truck",
        price_tier="$",
        address="3040 E Olympic Blvd, Los Angeles, CA 90023",
        latitude=d("34.0187000"),
        longitude=d("-118.2185000"),
        summary="Beloved mariscos truck known for crispy shrimp tacos and bright salsas.",
        highlights=("Street-food icon", "Shrimp tacos", "Quick service"),
        website_url="https://www.mariscosjalisco.com/",
    ),
    RestaurantSeed(
        slug="guerrilla-tacos-arts-district",
        name="Guerrilla Tacos",
        city="Los Angeles",
        neighborhood="Arts District",
        cuisine="Modern tacos",
        price_tier="$$",
        address="2000 E 7th St, Los Angeles, CA 90021",
        latitude=d("34.0349000"),
        longitude=d("-118.2309000"),
        summary="Chef-driven taco menu blending market produce and bold Mexican flavors.",
        highlights=("Creative tacos", "Arts District", "Casual chef concept"),
        website_url="https://www.guerrillatacos.com/",
    ),
    RestaurantSeed(
        slug="yangban-arts-district",
        name="Yangban",
        city="Los Angeles",
        neighborhood="Arts District",
        cuisine="Korean-American",
        price_tier="$$$",
        address="712 S Santa Fe Ave, Los Angeles, CA 90021",
        latitude=d("34.0365000"),
        longitude=d("-118.2303000"),
        summary="Contemporary Korean-American restaurant blending deli influences with polished dinner plates.",
        highlights=("Creative menu", "Korean-American", "Modern design"),
        website_url="https://www.yangbanla.com/",
    ),
    RestaurantSeed(
        slug="pine-and-crane-silver-lake",
        name="Pine & Crane",
        city="Los Angeles",
        neighborhood="Silver Lake",
        cuisine="Taiwanese",
        price_tier="$$",
        address="1521 Griffith Park Blvd, Los Angeles, CA 90026",
        latitude=d("34.0868000"),
        longitude=d("-118.2759000"),
        summary="Modern Taiwanese comfort food in a bright, fast-moving neighborhood dining room.",
        highlights=("Taiwanese staples", "Quick service", "Neighborhood favorite"),
        website_url="https://pineandcrane.com/",
    ),
    RestaurantSeed(
        slug="sqirl-east-hollywood",
        name="Sqirl",
        city="Los Angeles",
        neighborhood="East Hollywood",
        cuisine="Cafe and brunch",
        price_tier="$$",
        address="720 N Virgil Ave #4, Los Angeles, CA 90029",
        latitude=d("34.0841000"),
        longitude=d("-118.2876000"),
        summary="All-day cafe known for jam toasts, rice bowls, and light seasonal plates.",
        highlights=("Brunch favorite", "Cafe menu", "Casual vibe"),
        website_url="https://sqirlla.com/",
    ),
    RestaurantSeed(
        slug="found-oyster-east-hollywood",
        name="Found Oyster",
        city="Los Angeles",
        neighborhood="East Hollywood",
        cuisine="Seafood",
        price_tier="$$$",
        address="4880 Fountain Ave, Los Angeles, CA 90029",
        latitude=d("34.0952000"),
        longitude=d("-118.3006000"),
        summary="Small seafood room focused on oysters, lobster rolls, and bright coastal flavors.",
        highlights=("Seafood bar", "Compact dining room", "Date-night pick"),
        website_url="https://www.foundoyster.com/",
    ),
    RestaurantSeed(
        slug="quarter-sheets-echo-park",
        name="Quarter Sheets",
        city="Los Angeles",
        neighborhood="Echo Park",
        cuisine="Pizza and bakery",
        price_tier="$$",
        address="1305 Portia St, Los Angeles, CA 90026",
        latitude=d("34.0834000"),
        longitude=d("-118.2527000"),
        summary="Neighborhood pizza shop with standout grandma pies and highly rated cake slices.",
        highlights=("Pizza", "Bakery desserts", "Neighborhood gem"),
        website_url="https://www.quartersheets.com/",
    ),
    RestaurantSeed(
        slug="courage-bagels-silver-lake",
        name="Courage Bagels",
        city="Los Angeles",
        neighborhood="Silver Lake",
        cuisine="Bagels and breakfast",
        price_tier="$",
        address="749 Virgil Ave, Los Angeles, CA 90029",
        latitude=d("34.0851000"),
        longitude=d("-118.2872000"),
        summary="Popular bagel shop serving wood-fired style bagels with premium toppings.",
        highlights=("Morning lines", "Bagels", "Quick breakfast"),
        website_url="https://www.couragebagels.com/",
    ),
    RestaurantSeed(
        slug="jon-and-vinnys-fairfax",
        name="Jon & Vinny's",
        city="Los Angeles",
        neighborhood="Fairfax",
        cuisine="Italian-American",
        price_tier="$$$",
        address="412 N Fairfax Ave, Los Angeles, CA 90036",
        latitude=d("34.0789000"),
        longitude=d("-118.3618000"),
        summary="Crowd-pleasing Italian-American menu with pizza, pasta, and all-day comfort dishes.",
        highlights=("Casual upscale", "Family-friendly", "Popular brunch"),
        website_url="https://www.jonandvinnys.com/",
    ),
    RestaurantSeed(
        slug="pizzana-brentwood",
        name="Pizzana",
        city="Los Angeles",
        neighborhood="Brentwood",
        cuisine="Neo-Neapolitan pizza",
        price_tier="$$",
        address="11712 San Vicente Blvd, Los Angeles, CA 90049",
        latitude=d("34.0548000"),
        longitude=d("-118.4680000"),
        summary="Stylish pizza destination with crisp crusts and high-quality ingredients.",
        highlights=("Pizza-centric", "Date-friendly", "Brentwood staple"),
        website_url="https://www.pizzana.com/",
    ),
    RestaurantSeed(
        slug="great-white-venice",
        name="Great White",
        city="Los Angeles",
        neighborhood="Venice",
        cuisine="Coastal cafe",
        price_tier="$$",
        address="1604 Pacific Ave, Venice, CA 90291",
        latitude=d("33.9854000"),
        longitude=d("-118.4699000"),
        summary="Beach-adjacent cafe with bright all-day menu and strong brunch traffic.",
        highlights=("Beach vibe", "Brunch", "Casual all-day"),
        website_url="https://www.greatwhite.cafe/",
    ),
    RestaurantSeed(
        slug="elephante-santa-monica",
        name="Elephante",
        city="Santa Monica",
        neighborhood="Santa Monica",
        cuisine="Coastal Italian",
        price_tier="$$$",
        address="1332 2nd St, Santa Monica, CA 90401",
        latitude=d("34.0150000"),
        longitude=d("-118.4975000"),
        summary="Rooftop-adjacent coastal Italian restaurant with ocean-influenced ambiance.",
        highlights=("Scenic setting", "Coastal Italian", "Popular dinner spot"),
        website_url="https://www.elephantela.com/",
    ),
    RestaurantSeed(
        slug="birdie-gs-santa-monica",
        name="Birdie G's",
        city="Santa Monica",
        neighborhood="Santa Monica",
        cuisine="Modern American",
        price_tier="$$$",
        address="2421 Michigan Ave, Santa Monica, CA 90404",
        latitude=d("34.0284000"),
        longitude=d("-118.4700000"),
        summary="Chef-led modern American plates with bold seasonal ingredients and house specialties.",
        highlights=("Chef-driven", "Seasonal menu", "Santa Monica favorite"),
        website_url="https://www.birdiegsla.com/",
    ),
    RestaurantSeed(
        slug="rustic-canyon-santa-monica",
        name="Rustic Canyon",
        city="Santa Monica",
        neighborhood="Santa Monica",
        cuisine="Californian",
        price_tier="$$$",
        address="1119 Wilshire Blvd, Santa Monica, CA 90401",
        latitude=d("34.0222000"),
        longitude=d("-118.4931000"),
        summary="Market-driven Californian cooking with evolving seasonal tasting options.",
        highlights=("Seasonal ingredients", "Neighborhood fine dining", "Wine pairings"),
        website_url="https://www.rusticcanyon.com/",
    ),
    RestaurantSeed(
        slug="spago-beverly-hills",
        name="Spago",
        city="Beverly Hills",
        neighborhood="Beverly Hills",
        cuisine="Californian fine dining",
        price_tier="$$$$",
        address="176 N Canon Dr, Beverly Hills, CA 90210",
        latitude=d("34.0678000"),
        longitude=d("-118.3991000"),
        summary="Flagship California fine-dining restaurant combining global technique and premium sourcing.",
        highlights=("Fine dining icon", "Chef legacy", "Special occasions"),
        website_url="https://www.wolfgangpuck.com/dining/spago-beverly-hills/",
    ),
    RestaurantSeed(
        slug="gracias-madre-west-hollywood",
        name="Gracias Madre",
        city="West Hollywood",
        neighborhood="West Hollywood",
        cuisine="Plant-based Mexican",
        price_tier="$$$",
        address="8905 Melrose Ave, West Hollywood, CA 90069",
        latitude=d("34.0832000"),
        longitude=d("-118.3861000"),
        summary="Upscale vegan Mexican dining with strong cocktail program and patio energy.",
        highlights=("Plant-based", "Patio dining", "Cocktails"),
        website_url="https://www.graciasmadre.com/",
    ),
    RestaurantSeed(
        slug="catch-la-west-hollywood",
        name="Catch LA",
        city="West Hollywood",
        neighborhood="West Hollywood",
        cuisine="Seafood and sushi",
        price_tier="$$$$",
        address="8715 Melrose Ave, West Hollywood, CA 90069",
        latitude=d("34.0832000"),
        longitude=d("-118.3840000"),
        summary="Rooftop dining room with seafood-forward menu and social, high-energy atmosphere.",
        highlights=("Rooftop scene", "Sushi and seafood", "Nightlife energy"),
        website_url="https://catchrestaurants.com/",
    ),
    RestaurantSeed(
        slug="destroyer-culver-city",
        name="Destroyer",
        city="Culver City",
        neighborhood="Culver City",
        cuisine="Contemporary cafe",
        price_tier="$$",
        address="3578 Hayden Ave, Culver City, CA 90232",
        latitude=d("34.0263000"),
        longitude=d("-118.3912000"),
        summary="Design-forward cafe balancing inventive daytime plates and specialty coffee.",
        highlights=("Minimalist design", "Coffee + food", "Creative daytime menu"),
        website_url="https://www.destroyer.la/",
    ),
    RestaurantSeed(
        slug="bianca-culver-city",
        name="Bianca",
        city="Culver City",
        neighborhood="Culver City",
        cuisine="Italian and bakery",
        price_tier="$$$",
        address="8850 Washington Blvd, Culver City, CA 90232",
        latitude=d("34.0236000"),
        longitude=d("-118.3877000"),
        summary="Modern Italian with bakery roots, known for polished pasta and strong pastry offerings.",
        highlights=("Pasta", "Bakery pedigree", "Culver City dining"),
        website_url="https://www.biancala.com/",
    ),
    RestaurantSeed(
        slug="margot-culver-city",
        name="Margot",
        city="Culver City",
        neighborhood="Culver City",
        cuisine="Mediterranean",
        price_tier="$$$",
        address="8820 Washington Blvd #301, Culver City, CA 90232",
        latitude=d("34.0236000"),
        longitude=d("-118.3882000"),
        summary="Rooftop Mediterranean destination with share plates and downtown-adjacent views.",
        highlights=("Rooftop", "Mediterranean share plates", "Sunset dining"),
        website_url="https://www.margotculvercity.com/",
    ),
    RestaurantSeed(
        slug="union-pasadena",
        name="Union",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="Italian",
        price_tier="$$$",
        address="37 E Union St, Pasadena, CA 91103",
        latitude=d("34.1473556"),
        longitude=d("-118.1493598"),
        summary="Old Pasadena dining room known for handmade pasta and ingredient-driven Italian plates.",
        highlights=("Handmade pasta", "Old Pasadena", "Date-night favorite"),
        website_url="https://www.unionpasadena.com/",
    ),
    RestaurantSeed(
        slug="agnes-pasadena",
        name="Agnes Restaurant & Cheesery",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="Californian",
        price_tier="$$$",
        address="40 W Green St, Pasadena, CA 91105",
        latitude=d("34.1459290"),
        longitude=d("-118.1509660"),
        summary="Pasadena favorite for seasonal plates, artisan cheese service, and natural wine.",
        highlights=("Cheese-focused program", "Natural wine", "Seasonal menu"),
        website_url="https://www.agnesla.com/",
    ),
    RestaurantSeed(
        slug="fishwives-pasadena",
        name="Fishwives",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="Seafood",
        price_tier="$$$",
        address="88 N Fair Oaks Ave, Pasadena, CA 91103",
        latitude=d("34.1477433"),
        longitude=d("-118.1502101"),
        summary="Seafood-forward menu featuring crudo, shellfish, and modern coastal plates.",
        highlights=("Seafood-led", "Old Pasadena", "Stylish room"),
        website_url="https://www.fishwives.com/",
    ),
    RestaurantSeed(
        slug="perle-pasadena",
        name="Perle",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="French",
        price_tier="$$$",
        address="43 E Union St, Pasadena, CA 91103",
        latitude=d("34.1473755"),
        longitude=d("-118.1491020"),
        summary="French-inspired menu with polished service and intimate evening atmosphere.",
        highlights=("French technique", "Intimate dining", "Wine pairings"),
        website_url="https://www.perlerestaurant.com/",
    ),
    RestaurantSeed(
        slug="bone-kettle-pasadena",
        name="Bone Kettle",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="Southeast Asian",
        price_tier="$$$",
        address="67 N Raymond Ave, Pasadena, CA 91103",
        latitude=d("34.1475166"),
        longitude=d("-118.1504760"),
        summary="Southeast Asian destination known for rich broths, noodles, and shareable mains.",
        highlights=("Signature broths", "Flavor-forward", "Pasadena staple"),
        website_url="https://www.bonekettle.com/",
    ),
    RestaurantSeed(
        slug="osawa-pasadena",
        name="Osawa",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="Japanese",
        price_tier="$$$",
        address="77 N Raymond Ave, Pasadena, CA 91103",
        latitude=d("34.1478368"),
        longitude=d("-118.1505487"),
        summary="Japanese dining room with sushi, tempura, and balanced traditional preparations.",
        highlights=("Japanese classics", "Sushi options", "Old Pasadena"),
        website_url="https://www.theosawa.com/",
    ),
    RestaurantSeed(
        slug="pez-coastal-kitchen-pasadena",
        name="Pez Coastal Kitchen",
        city="Pasadena",
        neighborhood="Old Pasadena",
        cuisine="Coastal Mexican",
        price_tier="$$",
        address="61 N Raymond Ave, Pasadena, CA 91103",
        latitude=d("34.1473820"),
        longitude=d("-118.1504512"),
        summary="Coastal Mexican menu with ceviches, grilled seafood, and social group-friendly seating.",
        highlights=("Ceviche", "Coastal flavors", "Group-friendly"),
        website_url="https://www.pezpasadena.com/",
    ),
    RestaurantSeed(
        slug="panda-inn-pasadena",
        name="Panda Inn",
        city="Pasadena",
        neighborhood="East Pasadena",
        cuisine="Chinese",
        price_tier="$$",
        address="3488 E Foothill Blvd, Pasadena, CA 91107",
        latitude=d("34.1516880"),
        longitude=d("-118.0782526"),
        summary="Large-format Chinese menu known for group dinners and classic house specialties.",
        highlights=("Group dining", "Chinese classics", "Family-style"),
        website_url="https://www.pandainn.com/",
    ),
)


_RESTAURANT_KEYWORDS = {
    "restaurant",
    "restaurants",
    "eat",
    "eating",
    "dining",
    "food",
    "brunch",
    "dinner",
    "lunch",
    "sushi",
    "pizza",
    "taco",
    "tacos",
    "seafood",
    "steak",
    "pasadena",
    "los angeles",
    "la",
    "where should i eat",
    "best places",
}

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "near",
    "from",
    "that",
    "this",
    "what",
    "where",
    "should",
    "could",
    "would",
    "about",
    "please",
    "show",
    "find",
    "give",
    "best",
    "good",
    "great",
    "top",
}


def seed_la_restaurant_knowledge(db: Session, *, force_refresh: bool = False) -> tuple[int, int]:
    existing_count = db.scalar(select(func.count()).select_from(RestaurantKnowledge)) or 0
    if existing_count and not force_refresh:
        return 0, 0

    created = 0
    updated = 0

    for seed in LA_RESTAURANT_SEED:
        row = db.scalar(select(RestaurantKnowledge).where(RestaurantKnowledge.slug == seed.slug))
        highlights = " | ".join(item.strip() for item in seed.highlights if item.strip())

        if row is None:
            row = RestaurantKnowledge(
                slug=seed.slug,
                name=seed.name,
                city=seed.city,
                neighborhood=seed.neighborhood,
                cuisine=seed.cuisine,
                price_tier=seed.price_tier,
                address=seed.address,
                latitude=seed.latitude,
                longitude=seed.longitude,
                summary=seed.summary,
                highlights=highlights,
                website_url=seed.website_url,
                source_label="PerkNation LA guide",
                source_url=seed.website_url,
                is_active=True,
            )
            db.add(row)
            created += 1
            continue

        row.name = seed.name
        row.city = seed.city
        row.neighborhood = seed.neighborhood
        row.cuisine = seed.cuisine
        row.price_tier = seed.price_tier
        row.address = seed.address
        row.latitude = seed.latitude
        row.longitude = seed.longitude
        row.summary = seed.summary
        row.highlights = highlights
        row.website_url = seed.website_url
        row.source_label = "PerkNation LA guide"
        row.source_url = seed.website_url
        row.is_active = True
        updated += 1

    db.commit()
    return created, updated


def is_restaurant_discovery_query(message: str) -> bool:
    text = _normalize(message)
    if not text:
        return False
    return any(keyword in text for keyword in _RESTAURANT_KEYWORDS)


def search_restaurants(
    db: Session,
    *,
    query: str,
    city_hint: Optional[str] = None,
    neighborhood_hint: Optional[str] = None,
    cuisine_hint: Optional[str] = None,
    limit: int = 12,
) -> list[RestaurantKnowledge]:
    limit = max(1, min(int(limit), 50))

    if not city_hint:
        city_hint = _infer_city_hint(query)
    if not neighborhood_hint:
        neighborhood_hint = _infer_neighborhood_hint(query)
    if not cuisine_hint:
        cuisine_hint = _infer_cuisine_hint(query)

    stmt = select(RestaurantKnowledge).where(RestaurantKnowledge.is_active.is_(True))
    if city_hint:
        stmt = stmt.where(func.lower(RestaurantKnowledge.city) == city_hint.strip().lower())
    if neighborhood_hint:
        stmt = stmt.where(RestaurantKnowledge.neighborhood.ilike(f"%{neighborhood_hint.strip()}%"))
    if cuisine_hint:
        stmt = stmt.where(RestaurantKnowledge.cuisine.ilike(f"%{cuisine_hint.strip()}%"))

    rows = db.scalars(stmt).all()
    if not rows:
        return []

    normalized_query = _normalize(query)
    tokens = _tokenize_query(normalized_query)

    scored: list[tuple[int, RestaurantKnowledge]] = []
    for row in rows:
        score = _score_row(row, normalized_query, tokens)
        if score > 0:
            scored.append((score, row))

    if not scored:
        # Return a strong default shortlist when query has no clear filters.
        fallback = sorted(rows, key=lambda item: (item.city.lower(), item.name.lower()))
        return fallback[:limit]

    scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return [row for _, row in scored[:limit]]


def build_ai_restaurant_context(db: Session, *, message: str, limit: int = 10) -> str:
    if not is_restaurant_discovery_query(message):
        return ""

    city_hint = _infer_city_hint(message)
    neighborhood_hint = _infer_neighborhood_hint(message)
    cuisine_hint = _infer_cuisine_hint(message)

    lexical_matches = search_restaurants(
        db,
        query=message,
        city_hint=city_hint,
        neighborhood_hint=neighborhood_hint,
        cuisine_hint=cuisine_hint,
        limit=limit,
    )
    try:
        semantic_matches = semantic_search_restaurants(
            db,
            query=message,
            limit=limit,
        )
    except Exception:
        semantic_matches = []

    semantic_similarity_by_id: dict[int, float] = {}
    ordered: list[RestaurantKnowledge] = []
    seen: set[int] = set()
    for match in semantic_matches:
        rid = int(match.restaurant.id)
        semantic_similarity_by_id[rid] = max(
            semantic_similarity_by_id.get(rid, 0.0),
            float(match.similarity or 0.0),
        )
        if rid in seen:
            continue
        ordered.append(match.restaurant)
        seen.add(rid)

    for row in lexical_matches:
        rid = int(row.id)
        if rid in seen:
            continue
        ordered.append(row)
        seen.add(rid)

    matches = ordered[:limit]
    if not matches:
        return ""

    lines = [
        "LA RESTAURANT KNOWLEDGE CONTEXT",
        f"query: {message.strip()}",
        f"matched_restaurants: {len(matches)}",
    ]

    for row in matches:
        location = ", ".join(part for part in [row.neighborhood, row.city] if part)
        price = row.price_tier or "n/a"
        highlight_text = ""
        if row.highlights:
            parts = [part.strip() for part in str(row.highlights).split("|") if part.strip()]
            if parts:
                highlight_text = "; highlights=" + ", ".join(parts[:3])

        semantic_note = ""
        similarity = semantic_similarity_by_id.get(int(row.id))
        if similarity is not None:
            semantic_note = f"; semantic_similarity={float(similarity):.3f}"

        lines.append(
            f"- {row.name} | location={location} | cuisine={row.cuisine} | price={price} | "
            f"summary={row.summary}{highlight_text}{semantic_note}"
        )

    lines.append(
        "When user asks for recommendations, prioritize these matches and suggest filters "
        "(neighborhood, cuisine, budget, date vibe) for follow-up."
    )
    return "\n".join(lines)


def _score_row(row: RestaurantKnowledge, query: str, tokens: list[str]) -> int:
    corpus_parts = [
        row.name,
        row.city,
        row.neighborhood or "",
        row.cuisine,
        row.summary,
        row.highlights or "",
        row.address or "",
    ]
    corpus = _normalize(" ".join(corpus_parts))

    score = 0
    if query and row.name and _normalize(row.name) in query:
        score += 12
    if query and row.neighborhood and _normalize(row.neighborhood) in query:
        score += 7
    if query and row.cuisine and _normalize(row.cuisine) in query:
        score += 8
    if query and row.city and _normalize(row.city) in query:
        score += 4

    for token in tokens:
        if token in _normalize(row.name):
            score += 6
        elif token in _normalize(row.cuisine):
            score += 5
        elif row.neighborhood and token in _normalize(row.neighborhood):
            score += 4
        elif token in corpus:
            score += 2

    return score


def _tokenize_query(text: str) -> list[str]:
    if not text:
        return []

    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    tokens = [token for token in cleaned.split() if len(token) > 1 and token not in _STOPWORDS]
    # Keep a deterministic compact window for scoring.
    return tokens[:20]


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _infer_city_hint(text: str) -> Optional[str]:
    normalized = _normalize(text)
    if "pasadena" in normalized:
        return "pasadena"
    if "santa monica" in normalized:
        return "santa monica"
    if "culver city" in normalized:
        return "culver city"
    if "beverly hills" in normalized:
        return "beverly hills"
    if "west hollywood" in normalized:
        return "west hollywood"
    if "los angeles" in normalized or " la " in f" {normalized} ":
        return "los angeles"
    return None


def _infer_neighborhood_hint(text: str) -> Optional[str]:
    normalized = _normalize(text)
    known = [
        "hollywood",
        "arts district",
        "downtown",
        "downtown la",
        "silver lake",
        "echo park",
        "venice",
        "koreatown",
        "thai town",
        "old pasadena",
        "pasadena",
        "chinatown",
        "westlake",
        "fairfax",
        "brentwood",
    ]
    for item in known:
        if item in normalized:
            return item
    return None


def _infer_cuisine_hint(text: str) -> Optional[str]:
    normalized = _normalize(text)
    cuisine_tokens = {
        "sushi": "Japanese",
        "japanese": "Japanese",
        "italian": "Italian",
        "thai": "Thai",
        "korean": "Korean",
        "bbq": "BBQ",
        "mexican": "Mexican",
        "seafood": "Seafood",
        "pizza": "Pizza",
        "brunch": "Cafe",
        "steak": "Steakhouse",
        "vegan": "Plant-based",
    }
    for token, hint in cuisine_tokens.items():
        if token in normalized:
            return hint
    return None
