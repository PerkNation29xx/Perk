from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import RestaurantKnowledge
from app.services import ai_assistant
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge
from app.services.local_discovery import build_local_discovery_context, is_local_discovery_query
from app.services.restaurant_vector_rag import RestaurantSemanticMatch


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory()


def test_is_local_discovery_query_detects_general_local_prompt() -> None:
    assert is_local_discovery_query("What are local things to do in Pasadena tonight?")
    assert is_local_discovery_query("Any nearby restaurants?")
    assert not is_local_discovery_query("Explain JWT expiration behavior")


def test_ai_chat_includes_local_discovery_context_for_general_local_queries(monkeypatch) -> None:
    captured: dict[str, list[dict[str, str]]] = {}

    def _fake_openai(messages: list[dict[str, str]]) -> tuple[str, str]:
        captured["messages"] = messages
        return "fake-openai-model", "Local picks loaded."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_assistant, "_request_openai_chat", _fake_openai)

    with _db_session() as db:
        seed_la_restaurant_knowledge(db, force_refresh=True)

        result = ai_assistant.chat_with_assistant(
            message="What are local things to do in Pasadena tonight?",
            history=[],
            db=db,
            current_user=None,
            user_role=None,
            requested_context="public",
            user_latitude=34.1478,
            user_longitude=-118.1445,
        )

    assert result.answer == "Local picks loaded."
    assert result.model == "fake-openai-model"

    system_blocks = [item["content"] for item in captured["messages"] if item.get("role") == "system"]
    assert any("LOCAL DISCOVERY CONTEXT" in block for block in system_blocks)
    assert any("user_location: lat=34.147800, lon=-118.144500" in block for block in system_blocks)


def test_local_discovery_context_includes_semantic_similarity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_embeddings_enabled", True)
    monkeypatch.setattr(settings, "rag_semantic_weight", 6.5)
    monkeypatch.setattr(settings, "rag_semantic_min_similarity", 0.1)

    from app.services import local_discovery

    with _db_session() as db:
        seed_la_restaurant_knowledge(db, force_refresh=True)
        target = db.query(RestaurantKnowledge).filter(RestaurantKnowledge.slug == "langers-westlake").one()

        def _fake_semantic(*_args, **_kwargs) -> list[RestaurantSemanticMatch]:
            return [RestaurantSemanticMatch(restaurant=target, similarity=0.93)]

        monkeypatch.setattr(local_discovery, "semantic_search_restaurants", _fake_semantic)
        context = build_local_discovery_context(
            db,
            message="Any good local spots tonight?",
            user_latitude=34.0558,
            user_longitude=-118.2917,
            limit=8,
        )

    assert "LOCAL DISCOVERY CONTEXT" in context
    assert "Langer's Delicatessen" in context
    assert "semantic_similarity=0.930" in context
