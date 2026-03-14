"""Runtime configuration service for the Blair AI agent.

Provides an in-memory cache of AgentConfiguration rows with Redis
pub/sub invalidation for multi-worker consistency. Getters are
synchronous (read from cache), while cache loading and invalidation
are async.

Usage:
    from app.ai.config_service import get_agent_config

    cfg = get_agent_config()
    max_tools = cfg.get_int("agent.max_tool_calls", 50)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentConfigService:
    """Runtime configuration with in-memory cache + Redis invalidation."""

    CHANNEL = "agent_config_changed"

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._cache_loaded_at: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes
        self._lock = asyncio.Lock()
        self._db_session_factory: Any = None

    def set_db_session_factory(self, factory: Any) -> None:
        """Set the async session factory for DB access."""
        self._db_session_factory = factory

    def _is_stale(self) -> bool:
        """Check if the in-memory cache has exceeded its TTL."""
        return (time.monotonic() - self._cache_loaded_at) > self._cache_ttl

    # ------------------------------------------------------------------
    # Synchronous getters (read from in-memory cache)
    # ------------------------------------------------------------------

    def get_int(self, key: str, default: int) -> int:
        """Get an integer config value from cache.

        Args:
            key: Config key (e.g. "agent.max_tool_calls").
            default: Fallback value if key is missing or unparseable.

        Returns:
            Parsed integer value or default.
        """
        raw = self._cache.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float) -> float:
        """Get a float config value from cache.

        Args:
            key: Config key (e.g. "agent.temperature").
            default: Fallback value if key is missing or unparseable.

        Returns:
            Parsed float value or default.
        """
        raw = self._cache.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except (ValueError, TypeError):
            return default

    def get_str(self, key: str, default: str) -> str:
        """Get a string config value from cache.

        Args:
            key: Config key (e.g. "prompt.agent_name").
            default: Fallback value if key is missing.

        Returns:
            String value or default.
        """
        return self._cache.get(key, default)

    def get_rate_limit(self, key: str, default: tuple[int, int]) -> tuple[int, int]:
        """Get a rate limit config value as (limit, window_seconds) tuple.

        Args:
            key: Config key (e.g. "rate_limit.ai_chat").
            default: Fallback tuple if key is missing or unparseable.

        Returns:
            Tuple of (limit, window_seconds) or default.
        """
        raw = self._cache.get(key)
        if raw is None:
            return default
        try:
            parts = raw.split(",")
            return (int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return default

    # ------------------------------------------------------------------
    # Async cache management
    # ------------------------------------------------------------------

    async def load_all(self) -> None:
        """Load all config from DB into cache."""
        async with self._lock:
            # Re-check freshness inside lock to avoid stampede
            if self._cache and not self._is_stale():
                return  # another coroutine already refreshed
            try:
                if self._db_session_factory is None:
                    logger.warning("AgentConfigService: no DB session factory set")
                    return
                async with self._db_session_factory() as db:
                    from app.models.agent_config import AgentConfiguration

                    result = await db.execute(select(AgentConfiguration))
                    rows = result.scalars().all()
                    self._cache = {row.key: row.value for row in rows}
                    self._cache_loaded_at = time.monotonic()
                    logger.info(
                        "AgentConfigService: loaded %d configs", len(self._cache)
                    )
            except Exception:
                logger.exception(
                    "AgentConfigService: failed to load configs from DB"
                )

    async def _ensure_loaded(self) -> None:
        """Reload cache if empty or stale."""
        if not self._cache or self._is_stale():
            await self.load_all()

    async def invalidate(self) -> None:
        """Clear cache and publish invalidation to Redis."""
        self._cache.clear()
        self._cache_loaded_at = 0.0
        try:
            from app.services.redis_service import redis_service

            if redis_service.is_connected:
                await redis_service.client.publish(self.CHANNEL, "invalidate")
        except Exception:
            logger.warning(
                "AgentConfigService: failed to publish invalidation to Redis"
            )

    async def subscribe_invalidation(self) -> None:
        """Listen for Redis invalidation messages and clear cache.

        Wraps the subscription in a retry loop with backoff so that
        transient Redis disconnects don't permanently kill the listener.
        """
        while True:
            try:
                from app.services.redis_service import redis_service

                if not redis_service.is_connected:
                    await asyncio.sleep(30)
                    continue
                pubsub = redis_service.client.pubsub()
                await pubsub.subscribe(self.CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        logger.info(
                            "AgentConfigService: received invalidation, clearing cache"
                        )
                        self._cache.clear()
                        self._cache_loaded_at = 0.0
            except Exception:
                logger.warning(
                    "Config invalidation listener crashed, retrying in 30s"
                )
                await asyncio.sleep(30)

    async def set_value(
        self, key: str, value: str, user_id: Any, db: AsyncSession
    ) -> None:
        """Update a config value, validate, and invalidate cache.

        Args:
            key: Config key to update.
            value: New string value.
            user_id: UUID of the user making the change.
            db: Active database session.

        Raises:
            ValueError: If key not found, type invalid, or value out of bounds.
        """
        from app.models.agent_config import AgentConfiguration

        row = await db.scalar(
            select(AgentConfiguration).where(AgentConfiguration.key == key)
        )
        if not row:
            raise ValueError(f"Config key not found: {key}")
        # Validate type and bounds
        self._validate_value(value, row.value_type, row.min_value, row.max_value)
        # Extra validation for prompt keys
        if key.startswith("prompt."):
            if len(value) > 2000:
                raise ValueError(
                    f"Prompt config values must be 2000 characters or fewer (got {len(value)})"
                )
            import re as _re
            if _re.search(r"\[USER\s+CONTENT", value, _re.IGNORECASE):
                raise ValueError(
                    "Prompt values must not contain '[USER CONTENT' delimiter"
                )
        row.value = value
        row.updated_by = user_id
        await db.commit()
        await self.invalidate()

    @staticmethod
    def _validate_value(
        value: str,
        value_type: str,
        min_val: str | None,
        max_val: str | None,
    ) -> None:
        """Validate value against type and bounds.

        Args:
            value: String value to validate.
            value_type: Expected type ("int", "float", "str", "bool").
            min_val: Optional minimum bound string.
            max_val: Optional maximum bound string.

        Raises:
            ValueError: If validation fails.
        """
        if value_type == "int":
            try:
                v = int(value)
            except ValueError:
                raise ValueError(f"Expected integer, got: {value}")
            if min_val is not None and v < int(min_val):
                raise ValueError(f"Value {v} below minimum {min_val}")
            if max_val is not None and v > int(max_val):
                raise ValueError(f"Value {v} above maximum {max_val}")
        elif value_type == "float":
            try:
                v = float(value)
            except ValueError:
                raise ValueError(f"Expected float, got: {value}")
            if min_val is not None and v < float(min_val):
                raise ValueError(f"Value {v} below minimum {min_val}")
            if max_val is not None and v > float(max_val):
                raise ValueError(f"Value {v} above maximum {max_val}")
        elif value_type == "bool":
            if value.lower() not in ("true", "false", "1", "0"):
                raise ValueError(f"Expected bool, got: {value}")
        # str type: no further type validation needed


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: AgentConfigService | None = None


def get_agent_config() -> AgentConfigService:
    """Get the global AgentConfigService singleton.

    Returns:
        The shared AgentConfigService instance.
    """
    global _instance
    if _instance is None:
        _instance = AgentConfigService()
    return _instance
