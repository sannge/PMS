"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
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
    db_pool_size: int = 50
    db_max_overflow: int = 100
    sql_echo: bool = False

    # MinIO settings
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool = False

    # JWT settings
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # WebSocket settings (DDoS protection)
    ws_max_connections_per_user: int = 50  # Normal user: ~5-10, attack: 100+
    ws_max_message_size: int = 65536  # 64KB max message size (DoS protection)

    # Redis settings (for WebSocket pub/sub and distributed caching)
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    redis_socket_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_required: bool = False  # Set True for multi-worker deployment

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
