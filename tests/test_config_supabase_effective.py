from app.core.config import Settings


def test_effective_supabase_values_from_settings_fields() -> None:
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon-key",
        supabase_service_role_key="service-role-key",
    )
    assert settings.effective_supabase_url == "https://example.supabase.co"
    assert settings.effective_supabase_anon_key == "anon-key"
    assert settings.effective_supabase_service_role_key == "service-role-key"


def test_effective_supabase_values_from_next_public_env(monkeypatch) -> None:
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://next-public.supabase.co")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY", "publishable-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-env-key")
    settings = Settings(
        _env_file=None,
        supabase_url=None,
        supabase_anon_key=None,
        supabase_service_role_key=None,
    )
    assert settings.effective_supabase_url == "https://next-public.supabase.co"
    assert settings.effective_supabase_anon_key == "publishable-key"
    assert settings.effective_supabase_service_role_key == "service-role-env-key"
