import json

from app.core.config import settings
from app.db.models import UserRole
from app.services import ai_assistant
from app.services.ai_assistant import chat_with_assistant


def test_ai_disabled_falls_back_to_deterministic_concierge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", False)

    result = chat_with_assistant(
        message="hello",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="public",
    )

    assert result.model == "perk-deterministic"
    assert result.role_context == "public"
    assert "temporarily unavailable" in result.answer.lower()
    assert "onboarding" in result.answer.lower()


def test_ai_provider_failure_falls_back_to_deterministic_concierge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)

    result = chat_with_assistant(
        message="hello",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="public",
    )

    assert result.model == "perk-deterministic"
    assert result.role_context == "public"
    assert "temporarily unavailable" in result.answer.lower()
    assert "status:" in result.answer.lower()


def test_home_local_guide_context_is_scoped_to_current_promos(monkeypatch) -> None:
    captured: dict[str, list[dict[str, str]]] = {}

    def _fake_openai(messages: list[dict[str, str]]) -> tuple[str, str]:
        captured["messages"] = messages
        return "fake-home-model", "El Portal and Hollywood Sports are loaded."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_assistant, "_request_openai_chat", _fake_openai)

    result = chat_with_assistant(
        message="What promos are live?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    assert result.answer == "El Portal and Hollywood Sports are loaded."
    assert result.model == "fake-home-model"
    assert result.role_context == "home_local_guide"

    system_blocks = [item["content"] for item in captured["messages"] if item.get("role") == "system"]
    assert any("Only answer questions about the current PerkNation public promos" in block for block in system_blocks)
    assert any("HOME LOCAL GUIDE CONTEXT" in block for block in system_blocks)
    assert any("Hollywood Sports paintball campaign" in block for block in system_blocks)
    assert any("Bond Collective workspace promo" in block for block in system_blocks)
    assert any("Crystal jewelry drop" in block for block in system_blocks)
    assert any("El Portal Restaurant World Cup promo" in block for block in system_blocks)


def test_home_local_guide_fallback_names_supported_topics(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", False)

    result = chat_with_assistant(
        message="hello",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    assert result.model == "perk-deterministic"
    assert result.role_context == "home_local_guide"
    assert "hollywood sports" in result.answer.lower()
    assert "bond collective" in result.answer.lower()
    assert "jewelry" in result.answer.lower()
    assert "el portal" in result.answer.lower()
    assert "pasadena restaurant" in result.answer.lower()


def test_home_local_guide_uses_nemotron_super_spark_lane(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        captured["base_url_override"] = base_url_override
        captured["model_override"] = model_override
        captured["host_id_override"] = host_id_override
        captured["system_context"] = "\n\n".join(
            item["content"] for item in messages if item.get("role") == "system"
        )
        return str(model_override), "Scoped Spark response."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _fake_spark)

    result = chat_with_assistant(
        message="Tell me about the paintball package.",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    assert result.model == "nvidia/nemotron-3-super"
    assert result.answer == "Scoped Spark response."
    assert captured["base_url_override"] == "http://chat.neonflux.co"
    assert captured["model_override"] == "nvidia/nemotron-3-super"
    assert captured["host_id_override"] == "spark"
    assert "HOME LOCAL GUIDE CONTEXT" in str(captured["system_context"])


def test_home_local_guide_includes_review_context_for_current_events(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _fake_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        captured["system_context"] = "\n\n".join(
            item["content"] for item in messages if item.get("role") == "system"
        )
        return str(model_override), "Use the LA fashion guide, SoFi openers, and Dine LA coverage."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _fake_spark)

    result = chat_with_assistant(
        message="What current fashion events, sports, concerts, and restaurants are listed for review?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    system_context = captured["system_context"]
    assert result.role_context == "home_local_guide"
    assert "PUBLIC REVIEW COVERAGE CONTEXT" in system_context
    assert "2026 Fashion Week calendar: LA, New York, Miami and the world" in system_context
    assert "Mount Westmore" not in system_context
    assert "UFC Fight Night: Hernandez vs. Rodrigues" not in system_context
    assert "KCON LA 2026" not in system_context
    assert "UFC Fight Night" not in system_context
    assert "Dine LA 2026 city guides" in system_context
    assert "not active PerkNation promotions" in system_context


def test_home_local_guide_review_listing_question_answers_directly(monkeypatch) -> None:
    def _unexpected_spark(*_args, **_kwargs) -> tuple[str, str]:
        raise AssertionError("review listing questions should not call Spark")

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _unexpected_spark)

    result = chat_with_assistant(
        message="What current fashion events, sports, concerts, and restaurants are listed for review on PerkNation?",
        history=[],
        db=object(),
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    answer = result.answer.lower()
    assert result.model == "nvidia/nemotron-3-super"
    assert "2026 fashion week calendar" in answer
    assert "mount westmore" not in answer
    assert "ufc fight night" not in answer
    assert "kcon la 2026" not in answer
    assert "dine la 2026" in answer
    assert "current perknation guides and events" in answer
    assert "ask for current promotions" in answer


def test_consumer_account_uses_nemotron_super_spark_lane(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        captured["base_url_override"] = base_url_override
        captured["model_override"] = model_override
        captured["host_id_override"] = host_id_override
        captured["system_context"] = "\n\n".join(
            item["content"] for item in messages if item.get("role") == "system"
        )
        return str(model_override), "Consumer Spark response."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _fake_spark)

    result = chat_with_assistant(
        message="Hello account assistant.",
        history=[],
        db=None,
        current_user=None,
        user_role=UserRole.consumer,
        requested_context="consumer",
    )

    assert result.model == "nvidia/nemotron-3-super"
    assert result.answer == "Consumer Spark response."
    assert result.role_context == "consumer"
    assert captured["base_url_override"] == "http://chat.neonflux.co"
    assert captured["model_override"] == "nvidia/nemotron-3-super"
    assert captured["host_id_override"] == "spark"
    assert "cashback" in str(captured["system_context"]).lower()


def test_home_local_guide_blocks_legacy_cashback_stock_claims(monkeypatch) -> None:
    def _bad_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        return (
            str(model_override),
            "Yes, you can get cashback and stock rewards at El Portal, Target, and Bone Kettle.",
        )

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _bad_spark)

    result = chat_with_assistant(
        message="that is cool. do I get a discount?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    answer = result.answer.lower()
    assert "cashback" not in answer
    assert "cash back" not in answer
    assert "stock" not in answer
    assert "target" not in answer
    assert "hollywood sports" in answer
    assert "bond collective" in answer
    assert "jewelry" in answer
    assert "el portal" in answer


def test_public_context_blocks_legacy_cashback_stock_claims(monkeypatch) -> None:
    def _bad_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        return (
            "nvidia/nemotron-3-super",
            "Target offers 3% cash / 4% stock, and Bone Kettle has stock rewards.",
        )

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _bad_spark)

    result = chat_with_assistant(
        message="Do I get a discount?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="public",
    )

    answer = result.answer.lower()
    assert result.role_context == "public"
    assert "target" not in answer
    assert "cash /" not in answer
    assert "stock" not in answer
    assert "hollywood sports" in answer
    assert "bond collective" in answer


def test_public_discount_query_stays_on_confirmed_promos(monkeypatch) -> None:
    def _restaurant_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        return (
            "nvidia/nemotron-3-super",
            "Try Sonoratown, Quarter Sheets, and Langer's for local dining picks.",
        )

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _restaurant_spark)

    result = chat_with_assistant(
        message="Do I get a discount?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="public",
    )

    answer = result.answer.lower()
    assert "sonoratown" not in answer
    assert "hollywood sports" in answer
    assert "bond collective" in answer
    assert "el portal" in answer


def test_home_local_guide_blocks_legacy_rewards_for_jewelry(monkeypatch) -> None:
    def _bad_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        return (
            str(model_override),
            "Yes, jewelry earns cashback and stock rewards if you buy through Target.",
        )

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _bad_spark)

    result = chat_with_assistant(
        message="What is the jewelry discount?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    answer = result.answer.lower()
    assert "cashback" not in answer
    assert "stock" not in answer
    assert "target" not in answer
    assert "swarovski" in answer
    assert "dior" in answer
    assert "swan" in answer


def test_public_ai_answers_strip_visible_markdown_bold(monkeypatch) -> None:
    def _markdown_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        return ("spark-model", "The **$60 package** includes **11 regular tickets** plus 1 Golden Ticket.")

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _markdown_spark)

    result = chat_with_assistant(
        message="what is the paintball package?",
        history=[],
        db=None,
        current_user=None,
        user_role=None,
        requested_context="public",
    )

    assert "**" not in result.answer
    assert "$60 package" in result.answer
    assert "11 regular tickets" in result.answer


def test_home_local_guide_allows_business_directory_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_spark(
        messages: list[dict[str, str]],
        *,
        base_url_override=None,
        model_override=None,
        host_id_override=None,
    ) -> tuple[str, str]:
        captured["system_context"] = "\n\n".join(
            item["content"] for item in messages if item.get("role") == "system"
        )
        return str(model_override), "Ask about current PerkNation promos or Pasadena picks."

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "spark")
    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(settings, "home_local_guide_spark_base_url", "http://chat.neonflux.co")
    monkeypatch.setattr(settings, "home_local_guide_model", "nvidia/nemotron-3-super")
    monkeypatch.setattr(settings, "home_local_guide_spark_host_id", "spark")
    monkeypatch.setattr(ai_assistant, "_request_spark_chat", _fake_spark)
    monkeypatch.setattr(
        ai_assistant,
        "build_local_discovery_context",
        lambda *_args, **_kwargs: (
            "LOCAL DISCOVERY CONTEXT\n"
            "query: Acorn Creative LLC\n"
            "ranked_matches: 1\n"
            "- source=business_directory; title=Acorn Creative LLC; subtitle=Advertising, Marketing & Public Relations | Pasadena; directory_url='https://perknation.app/business/acorn-creative-llc'"
        ),
    )
    monkeypatch.setattr(ai_assistant, "build_ai_restaurant_context", lambda *_args, **_kwargs: "")

    result = chat_with_assistant(
        message="Acorn Creative LLC",
        history=[],
        db=object(),
        current_user=None,
        user_role=None,
        requested_context="home_local_guide",
    )

    assert result.role_context == "home_local_guide"
    assert "LOCAL DISCOVERY CONTEXT" in str(captured["system_context"])
    assert "source=business_directory" in str(captured["system_context"])


def test_spark_messages_are_compacted_under_input_budget(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"model":"spark-model","content":"ok"}'

    def _fake_urlopen(req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        captured["messages"] = payload["messages"]
        captured["host_id"] = payload["hostId"]
        captured["model"] = payload["model"]
        captured["timeout"] = timeout
        return _FakeResponse()

    oversized_messages = [
        {"role": "system", "content": "System context. " + ("large context " * 900)},
        {"role": "system", "content": "More context. " + ("restaurant event fashion sports " * 500)},
    ]
    oversized_messages.extend(
        {"role": "assistant" if idx % 2 else "user", "content": f"old message {idx} " + ("history " * 500)}
        for idx in range(20)
    )
    oversized_messages.append({"role": "user", "content": "Final current fashion events question"})

    monkeypatch.setattr(settings, "spark_public_base_url", "http://spark.example")
    monkeypatch.setattr(ai_assistant.request, "urlopen", _fake_urlopen)

    model, answer = ai_assistant._request_spark_chat(
        oversized_messages,
        base_url_override="http://spark.example",
        model_override="nvidia/nemotron-3-super",
        host_id_override="spark",
    )

    sent_messages = captured["messages"]
    assert model == "spark-model"
    assert answer == "ok"
    assert captured["host_id"] == "spark-nemotron"
    assert captured["model"] == "nvidia/nemotron-3-super"
    assert isinstance(sent_messages, list)
    assert ai_assistant._estimate_prompt_tokens(sent_messages) <= ai_assistant._SPARK_INPUT_TOKEN_BUDGET
    assert sent_messages[-1]["content"] == "Final current fashion events question"
