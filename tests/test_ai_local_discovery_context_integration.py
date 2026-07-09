from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import BusinessDirectoryEntry, RestaurantKnowledge
from app.services import ai_assistant
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge
from app.services.local_discovery import build_local_discovery_context, is_local_discovery_query
from app.services.restaurant_vector_rag import RestaurantSemanticMatch


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    return factory()


def _add_business_directory_entry(db: Session) -> BusinessDirectoryEntry:
    row = BusinessDirectoryEntry(
        slug="acorn-creative-llc-pasadena-advertising-marketing-public-relations",
        source_file="test-directory",
        source_sheet="Directory",
        source_row=2,
        business_name="Acorn Creative LLC",
        business_name_normalized="acorn creative llc",
        business_type="Advertising, Marketing & Public Relations",
        business_type_slug="advertising-marketing-public-relations",
        business_type_icon="◆",
        search_city="Pasadena",
        search_city_slug="pasadena",
        city="Pasadena",
        state="CA",
        zip_code="91101",
        address="123 Green St, Pasadena, CA 91101",
        phone_number="(626) 555-0100",
        website="https://acorn.example",
        description="Acorn Creative LLC is listed as an advertising and marketing business in Pasadena.",
        data_source="Imported test directory",
    )
    db.add(row)
    db.flush()
    return row


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


def test_local_discovery_context_includes_business_directory_name_match() -> None:
    with _db_session() as db:
        _add_business_directory_entry(db)
        context = build_local_discovery_context(
            db,
            message="Tell me about Acorn Creative LLC",
            limit=8,
        )

    assert "LOCAL DISCOVERY CONTEXT" in context
    assert "source=business_directory" in context
    assert "Acorn Creative LLC" in context
    assert "Advertising, Marketing & Public Relations" in context
    assert "(626) 555-0100" in context
    assert "https://perknation.app/business/acorn-creative-llc-pasadena-advertising-marketing-public-relations" in context


def test_local_discovery_context_marks_missing_directory_city_and_address() -> None:
    with _db_session() as db:
        row = _add_business_directory_entry(db)
        db.add(
            BusinessDirectoryEntry(
                slug="dce-creative-group-llc-burbank-professional-misc",
                source_file="test-directory",
                source_sheet="Directory",
                source_row=3,
                business_name="DCE CREATIVE GROUP LLC",
                business_name_normalized="dce creative group llc",
                business_type="Professional-Misc.",
                business_type_slug="professional-misc",
                business_type_icon="•",
                search_city="Burbank",
                search_city_slug="burbank",
                city="Burbank",
                state="CA",
                zip_code="91505",
                address="100 S California St, Burbank, CA 91505",
                description="DCE CREATIVE GROUP LLC is listed as a professional services business in Burbank.",
                data_source="Imported test directory",
            )
        )
        row.search_city = None
        row.search_city_slug = None
        row.city = None
        row.address = None
        db.flush()
        context = build_local_discovery_context(
            db,
            message="Tell me about Acorn Creative LLC",
            limit=8,
        )

    assert "source=business_directory" in context
    assert "ranked_matches: 1" in context
    assert "city='not listed in imported directory'" in context
    assert "address='not listed in imported directory'" in context
    assert "DCE CREATIVE GROUP LLC" not in context
    assert "do not infer that value" in context


def test_ai_chat_includes_directory_context_for_home_local_guide(monkeypatch) -> None:
    captured: dict[str, list[dict[str, str]]] = {}

    def _fake_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        captured["messages"] = messages
        return "spark-model", "Acorn Creative LLC is in the PerkNation directory."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _fake_spark)
    monkeypatch.setattr(ai_assistant, "build_ai_restaurant_context", lambda *_args, **_kwargs: "")

    with _db_session() as db:
        _add_business_directory_entry(db)
        result = ai_assistant.chat_with_assistant(
            message="Acorn Creative LLC",
            history=[],
            db=db,
            current_user=None,
            user_role=None,
            requested_context="home_local_guide",
        )

    assert result.answer == "Acorn Creative LLC is in the PerkNation directory."
    system_blocks = [item["content"] for item in captured["messages"] if item.get("role") == "system"]
    assert any("LOCAL DISCOVERY CONTEXT" in block for block in system_blocks)
    assert any("source=business_directory" in block and "Acorn Creative LLC" in block for block in system_blocks)
