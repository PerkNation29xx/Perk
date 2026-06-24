from fastapi.testclient import TestClient

from app.main import _GOOGLE_ANALYTICS_ID, _inject_google_analytics, app


def test_google_analytics_injects_before_head_close_once():
    html = "<html><head><title>Perk Nation</title></head><body>Hi</body></html>"

    injected = _inject_google_analytics(html)
    reinjected = _inject_google_analytics(injected)

    assert _GOOGLE_ANALYTICS_ID in injected
    assert injected.index(_GOOGLE_ANALYTICS_ID) < injected.lower().index("</head>")
    assert reinjected.count(_GOOGLE_ANALYTICS_ID) == injected.count(_GOOGLE_ANALYTICS_ID)


def test_rendered_homepage_includes_google_analytics_tag():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert _GOOGLE_ANALYTICS_ID in response.text


def test_json_health_response_does_not_get_google_analytics_tag():
    with TestClient(app) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert _GOOGLE_ANALYTICS_ID not in response.text
