"""PostgreSQL async database connection and session management."""

import asyncio
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

logger = logging.getLogger(__name__)

# Create async engine with optimized pool settings for 5000 concurrent users
engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_size=settings.db_pool_size,      # 50 base connections
    max_overflow=settings.db_max_overflow,  # 100 overflow connections
    pool_timeout=15,  # Fail fast - let clients retry rather than hang
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base for ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async dependency injection for FastAPI.

    Auto-commits on success, rollbacks on exception.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def warmup_connection_pool(pool_size: int = None) -> None:
    """
    Pre-warm the database connection pool at startup.

    SQLAlchemy + asyncpg runs initialization queries on each new connection
    (pg_catalog.version, current_schema, standard_conforming_strings).
    With remote databases, this can take 2-3 seconds per connection.

    Pre-warming creates connections upfront so they're ready when needed,
    avoiding timeouts during load spikes.

    Args:
        pool_size: Number of connections to warm up. Defaults to settings.db_pool_size.
    """
    target_size = pool_size or settings.db_pool_size
    logger.info(f"Warming up connection pool with {target_size} connections...")

    async def create_connection(i: int):
        """Create a single connection to warm the pool."""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.debug(f"  Connection {i + 1}/{target_size} warmed")
        except Exception as e:
            logger.warning(f"  Connection {i + 1} warmup failed: {e}")

    # Create connections concurrently (but not all at once to avoid overwhelming DB)
    batch_size = 10
    for batch_start in range(0, target_size, batch_size):
        batch_end = min(batch_start + batch_size, target_size)
        tasks = [create_connection(i) for i in range(batch_start, batch_end)]
        await asyncio.gather(*tasks)

    logger.info(f"Connection pool warmup complete ({target_size} connections)")
