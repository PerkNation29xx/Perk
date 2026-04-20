from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_discrete_database_settings_override_sqlite_default_url() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite:////tmp/perknation.db",
        database_host="db.example.com",
        database_port=5432,
        database_name="postgres",
        database_user="postgres",
        database_password="secret-pass",
        database_sslmode="require",
    )

    parsed = make_url(settings.sqlalchemy_database_url)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host == "db.example.com"
    assert parsed.port == 5432
    assert parsed.database == "postgres"
    assert parsed.username == "postgres"
    assert parsed.password == "secret-pass"
    assert parsed.query.get("sslmode") == "require"


def test_explicit_database_url_still_takes_precedence() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://url_user:url_pass@url-host:5432/url_db",
        database_host="db.example.com",
        database_port=5432,
        database_name="postgres",
        database_user="postgres",
        database_password="secret-pass",
        database_sslmode="require",
    )

    parsed = make_url(settings.sqlalchemy_database_url)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host == "url-host"
    assert parsed.port == 5432
    assert parsed.database == "url_db"
    assert parsed.username == "url_user"
    assert parsed.password == "url_pass"
