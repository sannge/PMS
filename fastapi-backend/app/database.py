"""SQL Server database connection and session management."""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings

# URL encode special characters in password
# The password contains '!' which needs to be percent-encoded
from urllib.parse import quote_plus

# Build connection string with properly encoded password
DATABASE_URL = (
    f"mssql+pyodbc://{settings.db_user}:{quote_plus(settings.db_password)}"
    f"@{settings.db_server}/{settings.db_name}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)

# Create SQLAlchemy engine
# - pool_pre_ping: Verify connections before use (handles stale connections)
# - pool_recycle: Recycle connections after 3600 seconds (1 hour)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Create session factory
# - autocommit=False: Require explicit commits
# - autoflush=False: Don't auto-flush to allow batching
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative base for ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection function for FastAPI.

    Yields a database session and ensures proper cleanup.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
