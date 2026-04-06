import os
import socket
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("PERKNATION_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    # Public website base URL used for auth email redirects.
    # Example: https://perknation.net
    public_web_base_url: str = "https://perknation.net"
    # Paths (or full URLs) for Supabase confirmation and password reset links.
    supabase_email_redirect_path: str = "/login"
    supabase_password_reset_redirect_path: str = "/reset-password"

    # Public invite link base used for referral QR/link payloads.
    # Supports either a query-param URL (e.g. https://perknation.app/invite)
    # or a templated URL containing `{code}`.
    referral_invite_base_url: str = "https://perknation.app/invite"

    # Apple Wallet pass support.
    # If configured, /v1/wallet/pass redirects the app to a signed pass service
    # that returns a valid .pkpass binary.
    wallet_pass_service_url: Optional[str] = None
    wallet_pass_type_identifier: Optional[str] = None
    wallet_team_identifier: Optional[str] = None
    wallet_organization_name: str = "PerkNation"
    wallet_signer_certificate_path: Optional[str] = None
    wallet_signer_key_path: Optional[str] = None
    wallet_wwdr_certificate_path: Optional[str] = None

    seed_default_data: bool = True
    email_verification_code_ttl_minutes: int = 30
    dev_expose_email_verification_code: bool = False

    # Public website form handling.
    # Primary write goes to DATABASE_* (or DATABASE_URL). If enabled, each form
    # submission is also mirrored to a local backup DB URL.
    forms_backup_enabled: bool = True
    forms_backup_database_url: str = "sqlite:///./perknation_forms_backup.db"

    # Contact form notifications.
    # If SMTP is configured, new contact submissions can be emailed to support.
    contact_email_forwarding_enabled: bool = True
    contact_form_notify_email: str = "perknation29@icloud.com"
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 20

    # AI assistant provider.
    ai_enabled: bool = True
    # "ollama" (local) or "openai" (public hosted API).
    # If set to a non-recognized value, we auto-select openai when an API key
    # exists, otherwise ollama.
    ai_provider: str = "ollama"

    # Local/open-source AI assistant (Ollama).
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:30b"
    ollama_timeout_seconds: int = 90
    ollama_temperature: float = 0.2

    # Hosted AI (OpenAI-compatible REST API).
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: int = 60
    openai_temperature: float = 0.2

    # Private message-box allowlist (owner/operator channels).
    owner_admin_message_email: str = "billy@neonflux.net"
    owner_ios_message_email: str = "billynavidad@icloud.com"

    @property
    def sqlalchemy_database_url(self) -> str:
        """
        Returns the SQLAlchemy database URL (string).

        If DATABASE_HOST/NAME/USER/PASSWORD are provided, we build a Postgres URL
        using SQLAlchemy's URL builder (handles quoting/escaping).
        """
        normalized_url = (self.database_url or "").strip()
        if normalized_url and normalized_url != "sqlite:///./perknation.db":
            # If an explicit DATABASE_URL is provided (e.g., Supabase pooler),
            # prefer it over discrete DATABASE_* vars. Still normalize it so
            # Supabase direct hosts can be forced onto IPv4 in cloud runtimes.
            return self._normalize_explicit_database_url(normalized_url)

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

        host_value = self.database_host
        query = {}
        if sslmode:
            query["sslmode"] = sslmode
        # Some cloud runtimes (including specific Render regions) can fail
        # routing to Supabase over IPv6. Resolve and use an IPv4 address.
        should_force_ipv4 = bool(self.database_host) and (
            self.database_force_ipv4 or (self.database_host or "").endswith(".supabase.co")
        )
        if should_force_ipv4 and self.database_host:
            try:
                ipv4_infos = socket.getaddrinfo(
                    self.database_host,
                    self.database_port,
                    family=socket.AF_INET,
                    type=socket.SOCK_STREAM,
                )
                if ipv4_infos:
                    host_value = ipv4_infos[0][4][0]
            except OSError:
                # If IPv4 resolution fails, continue with default DNS behavior.
                pass

        url = URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=self.database_password,
            host=host_value,
            port=self.database_port,
            database=self.database_name,
            query=query or None,
        )
        return url.render_as_string(hide_password=False)

    @staticmethod
    def _resolve_ipv4_host(host: str, port: int) -> Optional[str]:
        try:
            ipv4_infos = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
            )
            if ipv4_infos:
                return ipv4_infos[0][4][0]
        except OSError:
            return None
        return None

    def _normalize_explicit_database_url(self, raw_url: str) -> str:
        normalized_url = raw_url
        if normalized_url.startswith("postgres://"):
            normalized_url = normalized_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif normalized_url.startswith("postgresql://"):
            normalized_url = normalized_url.replace("postgresql://", "postgresql+psycopg://", 1)

        if not normalized_url.startswith("postgresql+psycopg://"):
            return normalized_url

        try:
            url = make_url(normalized_url)
        except Exception:
            return normalized_url

        host = url.host or ""
        should_force_ipv4 = bool(host) and (
            self.database_force_ipv4 or host.endswith(".supabase.co")
        )
        if not should_force_ipv4:
            return normalized_url

        resolved_host = self._resolve_ipv4_host(host, url.port or self.database_port)
        if not resolved_host:
            return normalized_url

        query = dict(url.query) if url.query else {}
        if "sslmode" not in query and host.endswith(".supabase.co"):
            query["sslmode"] = "require"

        ipv4_url = URL.create(
            drivername=url.drivername,
            username=url.username,
            password=url.password,
            host=resolved_host,
            port=url.port,
            database=url.database,
            query=query or None,
        )
        return ipv4_url.render_as_string(hide_password=False)

    @staticmethod
    def _join_public_url(base_url: str, path_or_url: str) -> str:
        raw = (path_or_url or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw

        base = (base_url or "").strip() or "https://perknation.net"
        if raw.startswith("/"):
            return f"{base.rstrip('/')}{raw}"
        return f"{base.rstrip('/')}/{raw}"

    @property
    def supabase_email_redirect_url(self) -> str:
        return self._join_public_url(self.public_web_base_url, self.supabase_email_redirect_path)

    @property
    def supabase_password_reset_redirect_url(self) -> str:
        return self._join_public_url(
            self.public_web_base_url,
            self.supabase_password_reset_redirect_path,
        )


settings = Settings()
