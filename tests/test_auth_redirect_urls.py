from app.core.config import Settings


def test_supabase_auth_redirects_canonicalize_old_domains() -> None:
    settings = Settings(
        _env_file=None,
        public_web_base_url="https://perknation.net",
        supabase_email_redirect_path="/login",
        supabase_password_reset_redirect_path="/reset-password",
    )

    assert settings.supabase_email_redirect_url == "https://perknation.app/login"
    assert settings.supabase_password_reset_redirect_url == "https://perknation.app/reset-password"


def test_full_supabase_auth_redirect_urls_canonicalize_old_domains() -> None:
    settings = Settings(
        _env_file=None,
        public_web_base_url="https://perknation.app",
        supabase_email_redirect_path="https://perknation.dev/login",
        supabase_password_reset_redirect_path="https://www.perknation.net/reset-password",
    )

    assert settings.supabase_email_redirect_url == "https://perknation.app/login"
    assert settings.supabase_password_reset_redirect_url == "https://perknation.app/reset-password"
