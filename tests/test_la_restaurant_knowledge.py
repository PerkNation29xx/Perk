from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.services.la_restaurant_knowledge import (
    build_ai_restaurant_context,
    is_restaurant_discovery_query,
    search_restaurants,
    seed_la_restaurant_knowledge,
)


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory()


def test_seed_la_restaurant_knowledge_populates_rows() -> None:
    with _db_session() as db:
        created, updated = seed_la_restaurant_knowledge(db, force_refresh=True)

        assert created > 20
        assert updated == 0


def test_restaurant_search_matches_pasadena_sushi_query() -> None:
    with _db_session() as db:
        seed_la_restaurant_knowledge(db, force_refresh=True)

        matches = search_restaurants(db, query="best sushi in pasadena", limit=5)

        assert matches
        names = [item.name.lower() for item in matches]
        assert any("osawa" in name for name in names)


def test_ai_restaurant_context_builds_structured_block() -> None:
    with _db_session() as db:
        seed_la_restaurant_knowledge(db, force_refresh=True)

        context = build_ai_restaurant_context(db, message="where should I eat in old pasadena", limit=4)

        assert "LA RESTAURANT KNOWLEDGE CONTEXT" in context
        assert "matched_restaurants:" in context
        assert "Pasadena" in context


def test_non_restaurant_query_not_detected() -> None:
    assert is_restaurant_discovery_query("tell me a fun fact about Saturn") is False
