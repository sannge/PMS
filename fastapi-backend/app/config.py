"""Configuration management using pydantic-settings."""

import logging
import os
import re
import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)

# APP_ENV selects which env file to load: "dev" → .env.dev, "prod" → .env.prod
# Default: "prod"
_app_env = os.getenv("APP_ENV", "prod")
if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", _app_env):
    raise ValueError(
        f"APP_ENV contains invalid characters: {_app_env!r}. Only alphanumerics, hyphens, and underscores are allowed."
    )
_env_file = f".env.{_app_env}"
_config_logger.info("Loading config from %s (APP_ENV=%s)", _env_file, _app_env)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database settings
    db_server: str
    db_name: str
    db_user: str
    db_password: str
    db_port: int = 5432
    # Pool sized for 50+100=150 connections per worker (matches main.py target).
    # PgBouncer in transaction mode recommended for production.
    db_pool_size: int = 50
    db_max_overflow: int = 100
    sql_echo: bool = False

    # MinIO settings
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool = False
    minio_attachments_bucket: str = "pm-attachments"
    minio_images_bucket: str = "pm-images"

    # JWT settings
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # Legacy: used as default if access not set
    jwt_access_expiration_minutes: int = 15
    jwt_refresh_expiration_days: int = 14
    jwt_refresh_secret: str = ""  # Separate secret for refresh tokens; falls back to jwt_secret

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "production"  # "development" | "production"

    # WebSocket settings (DDoS protection)
    ws_max_connections_per_user: int = 15  # Normal user: ~5-10, attack: 100+
    ws_max_message_size: int = 65536  # 64KB max message size (DoS protection)

    # Redis settings (for WebSocket pub/sub and distributed caching)
    redis_url: str = "redis://localhost:6379/0"
    # H13: Increased from 50 to 200 for 5K-user broadcast storms
    redis_max_connections: int = 200
    redis_socket_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    # H8: Default to True so token blacklist fails closed in production.
    # Set to False only for single-worker dev/test environments.
    redis_required: bool = True

    # ARQ Worker settings (background job scheduling)
    # Archive job: runs at these hours (comma-separated, 24h format)
    # Default "0,12" = midnight and noon
    # Set to empty string "" to use arq_archive_minutes instead
    arq_archive_hours: str = "0,12"

    # Archive job: runs at these minutes (comma-separated, 0-59)
    # Only used if arq_archive_hours is empty
    # Example: "0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54,56,58" = every 2 mins
    arq_archive_minutes: str = ""

    # Presence cleanup job: runs at these seconds within each minute (comma-separated)
    # Default "0,30" = every 30 seconds (at :00 and :30 of each minute)
    arq_presence_cleanup_seconds: str = "0,30"

    # Legacy setting (deprecated, use arq_archive_hours instead)
    archive_test_mode: bool = False

    @property
    def database_url(self) -> str:
        """Build PostgreSQL async connection string."""
        from urllib.parse import quote_plus

        return (
            f"postgresql+asyncpg://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_server}:{self.db_port}/{self.db_name}"
        )

    @property
    def sync_database_url(self) -> str:
        """Build PostgreSQL sync connection string for Alembic."""
        from urllib.parse import quote_plus

        return (
            f"postgresql+psycopg2://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_server}:{self.db_port}/{self.db_name}"
        )

    # AI settings
    ai_encryption_key: str = ""
    ai_default_embedding_dimensions: int = 1536
    ai_default_provider: str = "openai"

    # Meilisearch settings
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_api_key: str = ""  # Scoped API key for "documents" index
    meilisearch_index_name: str = "documents"
    meilisearch_timeout: float = 5.0  # Client HTTP timeout in seconds

    # SMTP settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_encryption: str = "starttls"  # starttls | ssl | none
    smtp_from_email: str = "noreply@yourapp.com"
    smtp_from_name: str = "PM Desktop"
    smtp_timeout: int = 30
    smtp_validate_certs: bool = True
    smtp_enabled: bool = False  # Master switch (false = log codes to console)

    # Email verification settings
    email_verification_code_expiry_minutes: int = 15
    email_verification_resend_cooldown_seconds: int = 60
    password_reset_code_expiry_minutes: int = 15

    # OAuth settings (registered with AI providers)
    openai_oauth_client_id: str = ""
    anthropic_oauth_client_id: str = ""
    oauth_state_ttl_seconds: int = 600  # 10 minutes

    # M11: Trusted proxy IPs for X-Forwarded-For extraction (comma-separated)
    # Only set this when running behind a known reverse proxy (nginx, ALB, etc.)
    trusted_proxy_ips: str = ""

    # CORS settings
    cors_origins: str = "http://localhost:5173,http://localhost:8001"  # Comma-separated origins

    @property
    def use_tls(self) -> bool:
        """True for implicit TLS (port 465)."""
        return self.smtp_encryption == "ssl"

    @property
    def start_tls(self) -> bool:
        """True for STARTTLS upgrade (port 587)."""
        return self.smtp_encryption == "starttls"

    # Test database settings
    test_db_user: str = "pmsdbtestuser"
    test_db_password: str = ""

    @property
    def test_database_url(self) -> str:
        """Build test database connection string."""
        from urllib.parse import quote_plus

        return (
            f"postgresql+asyncpg://{self.test_db_user}:{quote_plus(self.test_db_password)}"
            f"@{self.db_server}:{self.db_port}/pmsdb_test"
        )


# Global settings instance
settings = Settings()

import os as _os

# Enforce AI encryption key when AI provider is configured
if not settings.ai_encryption_key and settings.ai_default_provider:
    if _os.environ.get("TESTING") == "1":
        _config_logger.warning("AI_ENCRYPTION_KEY is empty (test mode)")
    else:
        raise ValueError(
            "AI_ENCRYPTION_KEY must be set when AI_DEFAULT_PROVIDER is configured. "
            "AI provider credentials cannot be stored without encryption."
        )

# H8: Warn if redis_required is False outside test mode
if not settings.redis_required and _os.environ.get("TESTING") != "1":
    _config_logger.warning(
        "SECURITY: REDIS_REQUIRED is False — token blacklist will fail-open "
        "during Redis outages.  Set REDIS_REQUIRED=true for production."
    )

# M12: Enforce separate JWT_REFRESH_SECRET in production
if not settings.jwt_refresh_secret:
    if settings.redis_required and _os.environ.get("TESTING") != "1":
        _config_logger.warning(
            "SECURITY: JWT_REFRESH_SECRET is not set — refresh tokens share the "
            "access token signing secret. Set JWT_REFRESH_SECRET for production."
        )
    elif _os.environ.get("TESTING") != "1":
        _config_logger.info("JWT_REFRESH_SECRET not set — falling back to JWT_SECRET for refresh tokens.")

# M14: Warn about insecure defaults in production-like environments
if settings.redis_required and _os.environ.get("TESTING") != "1":
    _weak: list[str] = []
    if settings.minio_access_key == "minioadmin":
        _weak.append("MINIO_ACCESS_KEY is still 'minioadmin'")
    if settings.minio_secret_key == "minioadmin":
        _weak.append("MINIO_SECRET_KEY is still 'minioadmin'")
    if not settings.ai_encryption_key:
        _weak.append("AI_ENCRYPTION_KEY is empty")
    if _weak:
        _config_logger.warning(
            "SECURITY: Insecure defaults detected in production config: %s",
            "; ".join(_weak),
        )
