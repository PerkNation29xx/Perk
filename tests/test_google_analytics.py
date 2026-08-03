from fastapi.testclient import TestClient

from app.main import (
    _GOOGLE_ANALYTICS_ID,
    _INDEXNOW_KEY,
    _INDEXNOW_KEY_PATH,
    _append_directory_sitemap,
    _inject_google_analytics,
    _inject_social_meta,
    _public_url,
    _robots_txt,
    app,
)


def test_google_analytics_injects_before_head_close_once():
    html = "<html><head><title>Perk Nation</title></head><body>Hi</body></html>"

    injected = _inject_google_analytics(html)
    reinjected = _inject_google_analytics(injected)

    assert _GOOGLE_ANALYTICS_ID in injected
    assert injected.index(_GOOGLE_ANALYTICS_ID) < injected.lower().index("</head>")
    assert reinjected.count(_GOOGLE_ANALYTICS_ID) == injected.count(_GOOGLE_ANALYTICS_ID)


def test_social_meta_injects_before_head_close_once():
    html = (
        '<html><head><title>Perk Nation Test</title>'
        '<meta name="description" content="Local perks." />'
        '<link rel="canonical" href="/directory" />'
        "</head><body>Hi</body></html>"
    )

    injected = _inject_social_meta(html)
    reinjected = _inject_social_meta(injected)

    assert 'property="og:title" content="Perk Nation Test"' in injected
    assert 'property="og:description" content="Local perks."' in injected
    assert 'property="og:url" content="https://perknation.app/directory"' in injected
    assert 'name="twitter:card" content="summary_large_image"' in injected
    assert injected.index('property="og:title"') < injected.lower().index("</head>")
    assert reinjected.count('property="og:title"') == 1


def test_rendered_homepage_includes_google_analytics_tag():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert _GOOGLE_ANALYTICS_ID in response.text
    assert 'property="og:title"' in response.text
    assert 'name="twitter:card"' in response.text


def test_json_health_response_does_not_get_google_analytics_tag():
    with TestClient(app) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert _GOOGLE_ANALYTICS_ID not in response.text


def test_public_url_canonicalizes_legacy_domains(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "public_web_base_url", "https://perknation.net")

    assert _public_url("/business/example") == "https://perknation.app/business/example"


def test_sitemap_output_uses_absolute_perknation_app_urls(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "_directory_sitemap_xml", lambda *, white=False: "")
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>index.html</loc></url>
  <url><loc>how-it-works.html</loc></url>
  <url><loc>/white/how-it-works</loc></url>
  <url><loc>/jewelry/christian-dior-necklace</loc></url>
  <url><loc>https://perknation.net/business/example</loc></url>
  <url><loc>login.html</loc></url>
</urlset>"""

    sitemap = _append_directory_sitemap(content)

    assert "<loc>https://perknation.app/</loc>" in sitemap
    assert "<loc>https://perknation.app/how-it-works</loc>" in sitemap
    assert "<loc>https://perknation.app/jewelry/christian-dior-necklace</loc>" in sitemap
    assert "<loc>https://perknation.app/business/example</loc>" in sitemap
    assert "perknation.net" not in sitemap
    assert "https://perknation.app/white/" not in sitemap
    assert "index.html" not in sitemap
    assert "login" not in sitemap


def test_robots_points_to_live_sitemaps():
    robots = _robots_txt()

    assert "Allow: /" in robots
    assert "Disallow: /white/" in robots
    assert "Sitemap: https://perknation.app/sitemap.xml" in robots
    assert "Sitemap: https://perknation.app/business-directory-sitemap.xml" in robots


def test_indexnow_key_file_is_served_from_root():
    with TestClient(app) as client:
        response = client.get(_INDEXNOW_KEY_PATH)

    assert response.status_code == 200
    assert response.text == _INDEXNOW_KEY
    assert response.headers["content-type"].startswith("text/plain")


def test_white_namespace_redirects_to_canonical_routes():
    with TestClient(app) as client:
        checks = {
            "/white": "/",
            "/white/": "/",
            "/white/sitemap.xml": "/sitemap.xml",
            "/white/robots.txt": "/robots.txt",
            "/white/articles/pasadena-august-2026-guide": "/articles/pasadena-august-2026-guide",
            "/white/directory/pasadena?category=food": "/directory/pasadena?category=food",
        }
        for request_path, expected_location in checks.items():
            response = client.get(request_path, follow_redirects=False)
            assert response.status_code == 308
            assert response.headers["location"] == expected_location
