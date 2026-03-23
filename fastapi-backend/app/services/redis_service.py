"""Redis service for pub/sub, caching, and distributed state.

This module provides a centralized Redis client for:
- Pub/Sub messaging (WebSocket cross-worker communication)
- Caching (user profiles, roles)
- Distributed state (presence, rate limiting)

Designed for 5000+ concurrent users across multiple Uvicorn workers.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Optional

import redis.asyncio as aioredis
from redis.asyncio.client import PubSub

from ..config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """
    Async Redis service for multi-worker deployment.

    Features:
    - Connection pooling with automatic reconnection
    - Pub/Sub messaging for WebSocket broadcasts
    - JSON caching with TTL support
    - Sorted sets for presence tracking
    - Sliding window rate limiting
    - Background health monitor with state-change callbacks
    """

    def __init__(self) -> None:
        """Initialize the Redis service (not connected yet)."""
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False
        self._connected = False
        self._reconnect_delay: float = 1.0
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._on_state_change: Optional[Callable[[bool], Any]] = None

    async def connect(self) -> None:
        """Initialize Redis connection with connection pooling."""
        self._redis = await aioredis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            retry_on_timeout=settings.redis_retry_on_timeout,
            decode_responses=True,
        )
        # Test connection
        await self._redis.ping()
        self._connected = True
        logger.info("Redis connected successfully")

    async def disconnect(self) -> None:
        """Close Redis connection and cleanup resources."""
        self._running = False
        self._connected = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("Redis disconnected")

    @property
    def client(self) -> aioredis.Redis:
        """Get Redis client instance."""
        if self._redis is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._redis

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected and last known state is healthy."""
        return self._redis is not None and self._connected

    # =========================================================================
    # Pub/Sub Methods
    # =========================================================================

    async def subscribe(self, channel: str, handler: Callable) -> None:
        """
        Subscribe to a channel with a message handler.

        Args:
            channel: The channel name to subscribe to
            handler: Async function to call when a message is received
        """
        if channel not in self._handlers:
            self._handlers[channel] = []
            if self._pubsub:
                await self._pubsub.subscribe(channel)
        self._handlers[channel].append(handler)
        logger.debug(f"Subscribed to channel: {channel}")

    async def unsubscribe(self, channel: str, handler: Callable | None = None) -> None:
        """
        Unsubscribe a specific handler from a channel.

        If *handler* is None, removes ALL handlers for the channel (backward compat).
        If *handler* is given, removes only that handler. The Redis pubsub
        subscription is only dropped when no handlers remain for the channel.

        Args:
            channel: The channel name to unsubscribe from
            handler: Optional specific handler to remove
        """
        if channel not in self._handlers:
            return

        if handler is None:
            # Remove all handlers (backward compat)
            del self._handlers[channel]
        else:
            try:
                self._handlers[channel].remove(handler)
            except ValueError:
                pass  # Handler not in list
            # Only fully unsubscribe when list is empty
            if self._handlers[channel]:
                logger.debug(f"Removed handler from channel: {channel} ({len(self._handlers[channel])} remaining)")
                return
            del self._handlers[channel]

        if self._pubsub:
            await self._pubsub.unsubscribe(channel)
        logger.debug(f"Unsubscribed from channel: {channel}")

    async def publish(self, channel: str, message: dict) -> int:
        """
        Publish a message to a channel.

        Args:
            channel: The channel name to publish to
            message: The message dictionary to publish

        Returns:
            Number of subscribers that received the message
        """
        try:
            result = await self.client.publish(channel, json.dumps(message, default=str))
            self._connected = True
            return result
        except Exception:
            self._connected = False
            raise

    async def start_listening(self) -> None:
        """Start the pub/sub listener background task.

        Safe to call again after a Redis outage to re-establish subscriptions.
        If the listener is already running and healthy, this is a no-op.
        """
        # If listener is already running and not done, nothing to do
        if self._running and self._listener_task is not None and not self._listener_task.done():
            logger.debug("Pub/sub listener already running")
            return

        # Clean up stale pubsub/task from a previous failed session
        if self._pubsub:
            try:
                await self._pubsub.close()
            except Exception:
                pass
        if self._listener_task and self._listener_task.done():
            self._listener_task = None

        self._pubsub = self.client.pubsub()
        self._running = True

        # Subscribe to all registered channels
        for channel in self._handlers.keys():
            await self._pubsub.subscribe(channel)

        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("Redis pub/sub listener started")

    async def _listen_loop(self) -> None:
        """Background task to receive and route pub/sub messages.

        Uses ``async for message in pubsub.listen()`` for push-based delivery
        instead of polling with ``get_message(timeout=1.0)``, eliminating up to
        1 second of latency per message.
        """
        while self._running:
            try:
                if self._pubsub is None:
                    break
                async for message in self._pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] != "message":
                        continue
                    channel = message["channel"]
                    data = json.loads(message["data"])

                    # Call all handlers for this channel
                    for handler in self._handlers.get(channel, []):
                        try:
                            await handler(data)
                        except Exception as e:
                            logger.error(f"Handler error on {channel}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Only log if we're still supposed to be running
                if self._running:
                    logger.error(f"Pub/sub listener error: {e}")
                    # Close dead pubsub and recreate
                    try:
                        if self._pubsub:
                            await self._pubsub.close()
                    except Exception:
                        pass
                    # Recreate pubsub and resubscribe all channels
                    self._pubsub = self.client.pubsub()
                    channels = list(self._handlers.keys())
                    if channels:
                        await self._pubsub.subscribe(*channels)
                    # L4: Exponential backoff to prevent tight-loop on Redis outage
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, 30.0)
                else:
                    break
            else:
                # Reset backoff on successful iteration
                self._reconnect_delay = 1.0

    # =========================================================================
    # Caching Methods
    # =========================================================================

    async def get(self, key: str) -> Optional[str]:
        """
        Get a string value from cache.

        Args:
            key: The cache key

        Returns:
            The cached value or None if not found
        """
        try:
            result = await self.client.get(key)
            self._connected = True
            return result
        except Exception:
            self._connected = False
            raise

    async def get_json(self, key: str) -> Optional[dict]:
        """
        Get and deserialize JSON from cache.

        Args:
            key: The cache key

        Returns:
            The cached dictionary or None if not found
        """
        try:
            value = await self.client.get(key)
            self._connected = True
            return json.loads(value) if value else None
        except Exception:
            self._connected = False
            raise

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a value in cache with optional TTL.

        Args:
            key: The cache key
            value: The value to cache (dicts/lists will be JSON-serialized)
            ttl: Time-to-live in seconds (optional)
        """
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        try:
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)
            self._connected = True
        except Exception:
            self._connected = False
            raise

    async def delete(self, key: str) -> None:
        """
        Delete a key from cache.

        Args:
            key: The cache key to delete
        """
        try:
            await self.client.delete(key)
            self._connected = True
        except Exception:
            self._connected = False
            raise

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern using SCAN + UNLINK (non-blocking).

        Uses UNLINK instead of DEL to avoid blocking Redis when deleting
        large numbers of keys. Processes in batches of 200 to bound per-call
        memory and avoid long-running UNLINK commands.

        Args:
            pattern: The glob-style pattern to match

        Returns:
            Number of keys deleted
        """
        try:
            total_deleted = 0
            cursor = 0
            batch_size = 200
            while True:
                cursor, keys = await self.client.scan(cursor=cursor, match=pattern, count=batch_size)
                if keys:
                    total_deleted += await self.client.unlink(*keys)
                if cursor == 0:
                    break
            self._connected = True
            return total_deleted
        except Exception:
            self._connected = False
            raise

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: The cache key

        Returns:
            True if the key exists
        """
        try:
            result = await self.client.exists(key) > 0
            self._connected = True
            return result
        except Exception:
            self._connected = False
            raise

    # =========================================================================
    # Presence Methods (Sorted Sets)
    # =========================================================================

    async def presence_set(self, room_id: str, user_id: str, timestamp: float) -> None:
        """
        Set user presence in a room using sorted set.

        Args:
            room_id: The room identifier
            user_id: The user identifier
            timestamp: Unix timestamp for presence ordering
        """
        await self.client.zadd(f"presence:{room_id}", {user_id: timestamp})

    async def presence_remove(self, room_id: str, user_id: str) -> None:
        """
        Remove user presence from a room.

        Args:
            room_id: The room identifier
            user_id: The user identifier
        """
        await self.client.zrem(f"presence:{room_id}", user_id)

    async def presence_get_room(self, room_id: str, since: float = 0) -> list[str]:
        """
        Get all users in a room with timestamp >= since.

        Args:
            room_id: The room identifier
            since: Minimum timestamp (default 0 = all)

        Returns:
            List of user IDs present in the room
        """
        return await self.client.zrangebyscore(f"presence:{room_id}", min=since, max="+inf")

    async def presence_cleanup(self, room_id: str, cutoff: float) -> int:
        """
        Remove stale presence entries older than cutoff.

        Args:
            room_id: The room identifier
            cutoff: Maximum timestamp to remove (entries < cutoff are removed)

        Returns:
            Number of entries removed
        """
        return await self.client.zremrangebyscore(f"presence:{room_id}", min="-inf", max=cutoff)

    async def presence_get_score(self, room_id: str, user_id: str) -> Optional[float]:
        """
        Get the timestamp for a user's presence in a room.

        Args:
            room_id: The room identifier
            user_id: The user identifier

        Returns:
            The timestamp or None if not present
        """
        return await self.client.zscore(f"presence:{room_id}", user_id)

    async def scan_keys(self, pattern: str, count: int = 100) -> list[str]:
        """
        Iterate keys matching pattern using SCAN (non-blocking, O(1) per call).

        Unlike KEYS which is O(N) and blocks Redis, SCAN uses a cursor to
        incrementally iterate without holding the server.

        Args:
            pattern: Glob-style pattern (e.g. "presence:*")
            count: Hint for how many keys to return per iteration

        Returns:
            List of matching key strings
        """
        result: list[str] = []
        cursor = 0
        while True:
            cursor, keys = await self.client.scan(cursor=cursor, match=pattern, count=count)
            result.extend(keys)
            if cursor == 0:
                break
        return result

    # =========================================================================
    # Rate Limiting Methods
    # =========================================================================

    async def rate_limit_check(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """
        Check rate limit using sliding window counter.

        Args:
            key: The rate limit key (e.g., "ratelimit:ws:{user_id}")
            limit: Maximum allowed requests in the window
            window: Window size in seconds

        Returns:
            Tuple of (allowed: bool, current_count: int)
        """
        # H14: Atomic INCR + EXPIRE via Lua to prevent key leak if Redis
        # crashes between the two commands.
        _RATE_LIMIT_LUA = (
            "local c = redis.call('INCR', KEYS[1]) if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end return c"
        )
        current = await self.client.eval(_RATE_LIMIT_LUA, 1, key, window)
        return current <= limit, current

    # =========================================================================
    # Background Health Monitor
    # =========================================================================

    async def start_health_monitor(
        self,
        interval: int = 5,
        on_state_change: Optional[Callable[[bool], Any]] = None,
    ) -> None:
        """Start a background task that PINGs Redis every *interval* seconds.

        On state transitions (connected ↔ disconnected) the optional
        *on_state_change* callback is invoked with the new boolean state.
        The callback may be a regular function or a coroutine.
        """
        if self._health_monitor_task is not None:
            return
        self._on_state_change = on_state_change
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop(interval))
        logger.info("Redis health monitor started (interval=%ds)", interval)

    async def stop_health_monitor(self) -> None:
        """Cancel the background health monitor task."""
        if self._health_monitor_task is not None:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
            self._health_monitor_task = None
            logger.info("Redis health monitor stopped")

    async def _health_monitor_loop(self, interval: int) -> None:
        """Background loop: PING Redis and detect state transitions."""
        while True:
            try:
                await asyncio.sleep(interval)
                previous = self._connected
                try:
                    if self._redis is not None:
                        await self._redis.ping()
                        self._connected = True
                    else:
                        self._connected = False
                except Exception:
                    self._connected = False

                # Fire callback only on transitions
                if previous != self._connected and self._on_state_change is not None:
                    try:
                        result = self._on_state_change(self._connected)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error("Redis state-change callback error: %s", e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitor unexpected error: %s", e)

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> dict[str, Any]:
        """
        Get Redis health status and stats.

        Returns:
            Dictionary with connection status and memory info
        """
        try:
            if not self.is_connected:
                return {
                    "status": "disconnected",
                    "gate_active": settings.redis_required and not self._connected,
                }

            info = await self.client.info("memory")
            return {
                "status": "healthy",
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "gate_active": False,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "gate_active": settings.redis_required and not self._connected,
            }


# Global singleton instance
redis_service = RedisService()


async def get_redis() -> RedisService:
    """FastAPI dependency for Redis service."""
    return redis_service


# Export for use in other modules
__all__ = [
    "RedisService",
    "redis_service",
    "get_redis",
]
