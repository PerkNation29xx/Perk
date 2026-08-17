from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_assistant import _public_review_live_query_response


ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "app" / "web" / "home_portal" / "articles" / "d23-anaheim-2026-guide.html"


def test_expired_d23_guide_is_removed_from_public_surfaces() -> None:
    client = TestClient(app)

    assert not ARTICLE.exists()
    for route in ("/articles/d23-anaheim-2026-guide", "/white/articles/d23-anaheim-2026-guide"):
        assert client.get(route).status_code == 404

    for route in ("/", "/white/"):
        response = client.get(route)
        assert response.status_code == 200
        assert "D23's final convention day is active today" not in response.text
        assert "/articles/d23-anaheim-2026-guide" not in response.text

    root_sitemap = client.get("/sitemap.xml")
    assert "d23-anaheim-2026-guide" not in root_sitemap.text


def test_public_answer_marks_d23_as_concluded() -> None:
    answer = _public_review_live_query_response(
        "What current Anaheim fan events are covered?",
        "home_local_guide",
    )

    assert answer
    assert "concluded on August 16" in answer
    assert "/directory?city=Anaheim" in answer
    assert "/articles/d23-anaheim-2026-guide" not in answer
    assert "active today" not in answer
