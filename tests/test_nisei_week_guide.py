from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


def test_nisei_week_is_retired_from_routes_homepages_and_sitemap() -> None:
    client = TestClient(app)

    for route in (
        "/articles/nisei-week-little-tokyo-2026-guide",
        "/white/articles/nisei-week-little-tokyo-2026-guide",
    ):
        assert client.get(route).status_code == 404

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Nisei Week closes today" not in response.text
        assert "/articles/nisei-week-little-tokyo-2026-guide" not in response.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "nisei-week-little-tokyo-2026-guide" not in sitemap.text


def test_nisei_week_public_answer_marks_the_festival_concluded() -> None:
    answer = _public_review_live_query_response(
        "What current Little Tokyo cultural events are covered?",
        "home_local_guide",
    )

    assert answer
    assert "concluded on August 23" in answer
    assert "no longer presents its event guide as active" in answer
    assert "/articles/nisei-week-little-tokyo-2026-guide" not in answer
