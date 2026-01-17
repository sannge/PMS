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
    db_server: str = "10.18.138.240"
    db_name: str = "PMDB"
    db_user: str = "pmdbuser"
    db_password: str = "never!again"

    # MinIO settings
    minio_endpoint: str = "10.18.136.10:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "Windows2"
    minio_secure: bool = False

    # JWT settings
    jwt_secret: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

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
