import socket
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "PerkNation Backend"
    api_v1_prefix: str = "/v1"

    # Default: local SQLite for development.
    database_url: str = "sqlite:///./perknation.db"

    # Optional: configure Postgres via discrete env vars. This avoids URL-encoding
    # issues for passwords with special characters (e.g. '#' or '@'), and is
    # friendlier for Supabase connection strings.
    database_host: Optional[str] = None
    database_port: int = 5432
    database_name: Optional[str] = None
    database_user: Optional[str] = None
    database_password: Optional[str] = None
    database_sslmode: Optional[str] = None
    # Workaround for environments that cannot reach database over IPv6.
    # When enabled, resolves DATABASE_HOST to IPv4 and passes hostaddr to libpq.
    database_force_ipv4: bool = False

    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Supabase Auth (optional). If SUPABASE_URL and SUPABASE_ANON_KEY are set,
    # the backend can accept Supabase access tokens (JWTs) for authentication.
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_jwt_secret: Optional[str] = None

    # Public invite link base used for referral QR/link payloads.
    # Supports either a query-param URL (e.g. https://perknation.app/invite)
    # or a templated URL containing `{code}`.
    referral_invite_base_url: str = "https://perknation.app/invite"

    seed_default_data: bool = True
    email_verification_code_ttl_minutes: int = 30
    dev_expose_email_verification_code: bool = False

    # Public website form handling.
    # Primary write goes to DATABASE_* (or DATABASE_URL). If enabled, each form
    # submission is also mirrored to a local backup DB URL.
    forms_backup_enabled: bool = True
    forms_backup_database_url: str = "sqlite:///./perknation_forms_backup.db"

    # Local/open-source AI assistant (Ollama).
    ai_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:30b"
    ollama_timeout_seconds: int = 90
    ollama_temperature: float = 0.2

    @property
    def sqlalchemy_database_url(self) -> str:
        """
        Returns the SQLAlchemy database URL (string).

        If DATABASE_HOST/NAME/USER/PASSWORD are provided, we build a Postgres URL
        using SQLAlchemy's URL builder (handles quoting/escaping).
        """

        has_discrete = all(
            [
                self.database_host,
                self.database_name,
                self.database_user,
                self.database_password,
            ]
        )
        if not has_discrete:
            return self.database_url

        sslmode = self.database_sslmode
        if sslmode is None and self.database_host and self.database_host.endswith(".supabase.co"):
            sslmode = "require"

        query = {}
        if sslmode:
            query["sslmode"] = sslmode
        if self.database_force_ipv4 and self.database_host:
            try:
                ipv4_infos = socket.getaddrinfo(
                    self.database_host,
                    self.database_port,
                    family=socket.AF_INET,
                    type=socket.SOCK_STREAM,
                )
                if ipv4_infos:
                    query["hostaddr"] = ipv4_infos[0][4][0]
            except OSError:
                # If IPv4 resolution fails, continue with default DNS behavior.
                pass

        url = URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
            query=query or None,
        )
        return url.render_as_string(hide_password=False)


settings = Settings()
