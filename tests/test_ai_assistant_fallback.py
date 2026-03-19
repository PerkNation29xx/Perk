from app.core.config import settings
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
