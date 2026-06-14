from app.core.config import settings
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
