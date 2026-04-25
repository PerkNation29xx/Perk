from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge
from app.services.restaurant_vector_rag import ensure_restaurant_embeddings, semantic_search_restaurants


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory()


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        normalized = text.lower()
        vectors.append(
            [
                1.0 if ("pastrami" in normalized or "deli" in normalized) else 0.05,
                1.0 if ("sushi" in normalized or "japanese" in normalized) else 0.05,
                1.0 if ("pizza" in normalized or "italian" in normalized) else 0.05,
                1.0,
            ]
        )
    return vectors


def test_semantic_search_restaurants_returns_ranked_results(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_embeddings_enabled", True)
    monkeypatch.setattr(settings, "rag_auto_embed_restaurants", False)
    monkeypatch.setattr(settings, "rag_embedding_dimensions", 4)

    from app.services import restaurant_vector_rag

    monkeypatch.setattr(restaurant_vector_rag, "_embed_texts", _fake_embed_texts)

    with _db_session() as db:
        seed_la_restaurant_knowledge(db, force_refresh=True)
        upserted = ensure_restaurant_embeddings(db, limit_rows=500)
        assert upserted > 0

        matches = semantic_search_restaurants(
            db,
            query="Where can I get the best pastrami deli in Los Angeles?",
            limit=5,
        )

    assert matches
    assert "Langer" in matches[0].restaurant.name
    assert float(matches[0].similarity) > 0.5
