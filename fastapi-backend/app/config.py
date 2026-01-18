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

    # MinIO settings
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool = False

    # JWT settings
    jwt_secret: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # WebSocket settings (DDoS protection)
    ws_max_connections_per_user: int = 50  # Normal user: ~5-10, attack: 100+
    ws_max_message_size: int = 65536  # 64KB max message size (DoS protection)

    @property
    def database_url(self) -> str:
        """Build SQL Server connection string."""
        return (
            f"mssql+pyodbc://{self.db_user}:{self.db_password}"
            f"@{self.db_server}/{self.db_name}"
            "?driver=ODBC+Driver+17+for+SQL+Server"
        )


# Global settings instance
settings = Settings()
