from app.main import (
    _directory_category_groups,
    _directory_category_menu,
    _directory_city_links,
)


def _facets():
    return {
        "business_types": [
            {"label": "Restaurants & Catering", "slug": "restaurants-catering", "count": 72, "icon": "🍽"},
            {"label": "Building Contractor/Const Related", "slug": "building-contractor-const-related", "count": 49, "icon": "🔧"},
            {"label": "Attorneys & Legal Services", "slug": "attorneys-legal-services", "count": 29, "icon": "⚖"},
            {"label": "Software / Technology", "slug": "software-technology", "count": 8, "icon": "⌘"},
            {"label": "Professional-Misc.", "slug": "professional-misc", "count": 180, "icon": "•"},
        ],
        "cities": [
            {"label": "Pasadena", "slug": "pasadena", "count": 562},
            {"label": "Long Beach", "slug": "long-beach", "count": 207},
        ],
    }


def test_category_groups_assign_each_business_type_once():
    groups = _directory_category_groups(_facets()["business_types"])
    assigned = [
        item["slug"]
        for group in groups
        for level in group["levels"]
        for item in level["items"]
    ]

    assert sorted(assigned) == sorted(item["slug"] for item in _facets()["business_types"])
    assert len(assigned) == len(set(assigned))


def test_category_menu_keeps_top_groups_static_and_deeper_levels_collapsible():
    html = _directory_category_menu(
        facets=_facets(),
        white=True,
        selected_city_slug=None,
        selected_type_slug="restaurants-catering",
    )

    assert 'class="directoryCategoryGroup"' in html
    assert "Food, Dining &amp; Hospitality" in html
    assert "Home, Construction &amp; Property" in html
    assert 'class="directoryCategoryLevel" open' in html
    assert 'class="directorySubcategoryLink active"' in html
    assert "directoryCategoryRail" not in html


def test_city_menu_uses_wrapping_grid_instead_of_horizontal_rail():
    html = _directory_city_links(facets=_facets(), white=True, selected_city_slug=None)

    assert 'class="directoryCityPanel"' in html
    assert 'class="directoryCityGrid"' in html
    assert "directoryCityRail" not in html
    assert "/directory/pasadena" in html
    assert "/white/directory/pasadena" not in html
