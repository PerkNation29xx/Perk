from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_homepage_has_one_h1_and_no_unfilled_advertising_placeholders() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text.lower().count("<h1") == 1
    assert "siteAdSection" not in response.text
    assert "data-ad-client" not in response.text
    assert "PerkNation sponsor banner" not in response.text


def test_editorial_trust_pages_are_public_and_linked() -> None:
    with TestClient(app) as client:
        about = client.get("/about")
        standards = client.get("/editorial-standards")
        homepage = client.get("/")

    assert about.status_code == 200
    assert standards.status_code == 200
    assert "Local discovery should help you make a better plan" in about.text
    assert "Perk Nation editorial standards" in standards.text
    assert 'href="/about"' in homepage.text
    assert 'href="/editorial-standards"' in homepage.text


def test_thin_dine_la_pages_are_noindex_and_strong_guides_remain_indexable() -> None:
    thin = main._render_dine_la_city_article("dine-la-city-agoura-hills-2026")
    strong = main._render_dine_la_city_article("dine-la-city-los-angeles-2026")

    assert thin is not None
    assert strong is not None
    assert '<meta name="robots" content="noindex,follow"' in thin
    assert '<meta name="robots" content="index,follow"' in strong


def test_primary_sitemap_retires_expired_dine_la_city_guides() -> None:
    content = (main._HOME_PORTAL_DIR / "sitemap.xml").read_text(encoding="utf-8")

    assert "/articles/dine-la-city-los-angeles-2026" not in content
    assert "/articles/dine-la-city-long-beach-2026" not in content
    assert "/articles/dine-la-city-agoura-hills-2026" not in content
    assert "/articles/dine-la-city-south-pasadena-2026" not in content
    assert "/articles/southern-california-september-events-2026" in content
    assert "/about" in content
    assert "/editorial-standards" in content


def test_directory_sitemap_contains_only_qualified_southern_california_hubs(monkeypatch) -> None:
    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(main, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(
        main,
        "directory_facets",
        lambda _db: {
            "cities": [
                {"slug": "pasadena", "label": "Pasadena", "count": 563},
                {"slug": "irvine", "label": "Irvine", "count": 17},
                {"slug": "aberdeen", "label": "Aberdeen", "count": 70},
            ],
            "business_types": [
                {"slug": "restaurant", "label": "Restaurant", "count": 600},
            ],
        },
    )

    content = main._directory_sitemap_xml()

    assert "https://perknation.app/directory</loc>" in content
    assert "https://perknation.app/directory/pasadena" in content
    assert "/directory/irvine" not in content
    assert "/directory/aberdeen" not in content
    assert "/directory/type/" not in content
    assert "/business/" not in content


def test_directory_shell_supports_noindex_follow() -> None:
    content = main._directory_shell(
        title="Example",
        description="Example page",
        canonical_path="/business/example",
        body="<p>Example</p>",
        white=False,
        robots="noindex,follow",
    )

    assert '<meta name="robots" content="noindex,follow"' in content
    assert 'href="/editorial-standards"' in content


def test_raw_directory_import_coordinates_are_not_reader_visible() -> None:
    source = (main._BASE_DIR / "main.py").read_text(encoding="utf-8")

    assert "Imported from {_escape(row.source_file)}" not in source
    assert "row {_escape(row.source_row)}" not in source
