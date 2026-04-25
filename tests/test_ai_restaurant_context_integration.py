from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.services import ai_assistant
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory()


def test_ai_chat_includes_restaurant_context_for_restaurant_queries(monkeypatch) -> None:
    captured: dict[str, list[dict[str, str]]] = {}

    def _fake_openai(messages: list[dict[str, str]]) -> tuple[str, str]:
        captured["messages"] = messages
        return "fake-openai-model", "Top picks loaded."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_assistant, "_request_openai_chat", _fake_openai)

    with _db_session() as db:
        seed_la_restaurant_knowledge(db, force_refresh=True)

        result = ai_assistant.chat_with_assistant(
            message="best sushi in pasadena",
            history=[],
            db=db,
            current_user=None,
            user_role=None,
            requested_context="public",
        )

    assert result.answer == "Top picks loaded."
    assert result.model == "fake-openai-model"

    system_blocks = [item["content"] for item in captured["messages"] if item.get("role") == "system"]
    assert any("LA RESTAURANT KNOWLEDGE CONTEXT" in block for block in system_blocks)
