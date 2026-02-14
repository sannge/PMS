"""Presence management infrastructure for real-time collaboration.

Redis-based presence tracking optimized for 5000+ concurrent users
across multiple Uvicorn workers.

Uses Redis sorted sets for timestamp-based presence tracking and
Redis hashes for user metadata (name, avatar, idle status).

Cleanup is handled by ARQ worker (see app/worker.py).
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..services.redis_service import redis_service

logger = logging.getLogger(__name__)

# Presence TTL in seconds (45s allows for network jitter with 30s heartbeat)
PRESENCE_TTL = 45
HEARTBEAT_INTERVAL = 30


@dataclass
class UserPresence:
    """User presence information."""

    user_id: str
    user_name: str
    avatar_url: Optional[str] = None
    idle: bool = False
    last_seen: float = 0.0


class PresenceManager:
    """
    Redis-backed presence manager for cross-worker state.

    Uses:
    - Redis sorted sets (ZADD/ZRANGEBYSCORE) for presence tracking
    - Redis hashes for user metadata (name, avatar, idle)
    - Redis pub/sub for presence change notifications

    Cleanup of stale entries is handled by ARQ worker cron jobs.

    This enables accurate presence across multiple server instances
    (5000+ concurrent users).
    """

    # Key prefixes
    _PRESENCE_PREFIX = "presence:"
    _USER_DATA_PREFIX = "presence_data:"
    _USER_ROOMS_PREFIX = "user_rooms:"
    _PRESENCE_CHANNEL = "ws:presence"

    def __init__(self) -> None:
        """Initialize the presence manager."""
        # Fallback in-memory storage when Redis is not available
        self._local_presence: dict[str, dict[str, UserPresence]] = {}
        self._local_user_rooms: dict[str, set[str]] = {}
        # Note: asyncio.Lock is not created here to avoid event loop issues
        # It will be created lazily when needed
        self._lock: Optional[Any] = None

    def _get_lock(self):
        """Get or create the asyncio lock (lazy initialization)."""
        import asyncio
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def heartbeat(
        self,
        room_id: str,
        user_id: str,
        user_name: str,
        avatar_url: Optional[str] = None,
        idle: bool = False,
    ) -> None:
        """
        Update user presence in a room (heartbeat).

        Args:
            room_id: The room to update presence in
            user_id: The user's ID
            user_name: The user's display name
            avatar_url: Optional avatar URL
            idle: Whether the user is idle
        """
        now = time.time()

        if redis_service.is_connected:
            try:
                # Update presence timestamp in sorted set
                await redis_service.presence_set(room_id, user_id, now)

                # Store user metadata in hash
                user_data = json.dumps({
                    "name": user_name,
                    "avatar": avatar_url,
                    "idle": idle,
                })
                await redis_service.client.hset(
                    f"{self._USER_DATA_PREFIX}{room_id}",
                    user_id,
                    user_data
                )

                # Track room in user's reverse index for O(1) leave_all
                await redis_service.client.sadd(
                    f"{self._USER_ROOMS_PREFIX}{user_id}",
                    room_id
                )
            except Exception as e:
                logger.error(f"Redis heartbeat error: {e}")
                # Fall through to local storage
        else:
            # Fallback: update local storage
            async with self._get_lock():
                if room_id not in self._local_presence:
                    self._local_presence[room_id] = {}

                self._local_presence[room_id][user_id] = UserPresence(
                    user_id=user_id,
                    user_name=user_name,
                    avatar_url=avatar_url,
                    idle=idle,
                    last_seen=now,
                )

                if user_id not in self._local_user_rooms:
                    self._local_user_rooms[user_id] = set()
                self._local_user_rooms[user_id].add(room_id)

    async def leave(
        self,
        room_id: str,
        user_id: str,
    ) -> None:
        """
        Remove user presence from a room.

        Args:
            room_id: The room to leave
            user_id: The user's ID
        """
        if redis_service.is_connected:
            try:
                # Remove from sorted set
                await redis_service.presence_remove(room_id, user_id)

                # Remove user metadata
                await redis_service.client.hdel(
                    f"{self._USER_DATA_PREFIX}{room_id}",
                    user_id
                )

                # Remove room from user's reverse index
                await redis_service.client.srem(
                    f"{self._USER_ROOMS_PREFIX}{user_id}",
                    room_id
                )

                # Broadcast leave event
                await redis_service.publish(
                    self._PRESENCE_CHANNEL,
                    {
                        "type": "user_left",
                        "room_id": room_id,
                        "user_id": user_id,
                    }
                )
            except Exception as e:
                logger.error(f"Redis leave error: {e}")
        else:
            # Fallback: update local storage
            async with self._get_lock():
                if room_id in self._local_presence and user_id in self._local_presence[room_id]:
                    del self._local_presence[room_id][user_id]
                    if not self._local_presence[room_id]:
                        del self._local_presence[room_id]

                if user_id in self._local_user_rooms:
                    self._local_user_rooms[user_id].discard(room_id)
                    if not self._local_user_rooms[user_id]:
                        del self._local_user_rooms[user_id]

    async def leave_all(
        self,
        user_id: str,
    ) -> list[str]:
        """
        Remove user presence from all rooms.

        Args:
            user_id: The user's ID

        Returns:
            List of room IDs the user was removed from
        """
        rooms_left = []

        if redis_service.is_connected:
            try:
                # O(1) lookup via reverse index instead of O(N) SCAN
                room_ids = await redis_service.client.smembers(
                    f"{self._USER_ROOMS_PREFIX}{user_id}"
                )

                if room_ids:
                    # Batch-remove from all rooms in a single pipeline
                    pipe = redis_service.client.pipeline(transaction=False)
                    for room_id in room_ids:
                        pipe.zrem(f"{self._PRESENCE_PREFIX}{room_id}", user_id)
                        pipe.hdel(f"{self._USER_DATA_PREFIX}{room_id}", user_id)
                    # Delete the reverse index
                    pipe.delete(f"{self._USER_ROOMS_PREFIX}{user_id}")
                    await pipe.execute()
                    rooms_left = list(room_ids)
            except Exception as e:
                logger.error(f"Redis leave_all error: {e}")
        else:
            # Fallback: update local storage
            async with self._get_lock():
                if user_id in self._local_user_rooms:
                    rooms = list(self._local_user_rooms[user_id])
                    for room_id in rooms:
                        if room_id in self._local_presence and user_id in self._local_presence[room_id]:
                            del self._local_presence[room_id][user_id]
                            if not self._local_presence[room_id]:
                                del self._local_presence[room_id]
                            rooms_left.append(room_id)
                    del self._local_user_rooms[user_id]

        return rooms_left

    async def get_presence(
        self,
        room_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get all users present in a room.

        Args:
            room_id: The room to query

        Returns:
            List of user presence dictionaries
        """
        cutoff = time.time() - PRESENCE_TTL

        if redis_service.is_connected:
            try:
                # Get active users from sorted set
                user_ids = await redis_service.presence_get_room(room_id, cutoff)

                if not user_ids:
                    return []

                # Get user metadata from hash in single round-trip
                user_data_key = f"{self._USER_DATA_PREFIX}{room_id}"
                values = await redis_service.client.hmget(user_data_key, *user_ids)
                result = []

                for user_id, data_str in zip(user_ids, values):
                    if data_str:
                        data = json.loads(data_str)
                        result.append({
                            "id": user_id,
                            "name": data.get("name", "Unknown"),
                            "avatar": data.get("avatar"),
                            "idle": data.get("idle", False),
                        })
                    else:
                        # User in sorted set but no metadata
                        result.append({
                            "id": user_id,
                            "name": "Unknown",
                            "avatar": None,
                            "idle": False,
                        })

                return result
            except Exception as e:
                logger.error(f"Redis get_presence error: {e}")
                return []
        else:
            # Fallback: query local storage
            async with self._get_lock():
                users = self._local_presence.get(room_id, {})
                return [
                    {
                        "id": p.user_id,
                        "name": p.user_name,
                        "avatar": p.avatar_url,
                        "idle": p.idle,
                    }
                    for p in users.values()
                    if p.last_seen > cutoff
                ]

    async def get_user_rooms(
        self,
        user_id: str,
    ) -> list[str]:
        """
        Get all rooms where a user is present.

        Args:
            user_id: The user's ID

        Returns:
            List of room IDs
        """
        cutoff = time.time() - PRESENCE_TTL

        if redis_service.is_connected:
            try:
                # O(1) lookup via reverse index
                room_ids = await redis_service.client.smembers(
                    f"{self._USER_ROOMS_PREFIX}{user_id}"
                )
                if not room_ids:
                    return []

                # Verify presence is still active (not stale)
                pipe = redis_service.client.pipeline(transaction=False)
                room_list = list(room_ids)
                for room_id in room_list:
                    pipe.zscore(f"{self._PRESENCE_PREFIX}{room_id}", user_id)
                scores = await pipe.execute()

                return [
                    room_id
                    for room_id, score in zip(room_list, scores)
                    if score is not None and score > cutoff
                ]
            except Exception as e:
                logger.error(f"Redis get_user_rooms error: {e}")
                return []
        else:
            # Fallback: query local storage
            async with self._get_lock():
                return list(self._local_user_rooms.get(user_id, set()))

    async def is_present(
        self,
        room_id: str,
        user_id: str,
    ) -> bool:
        """
        Check if a user is present in a room.

        Args:
            room_id: The room to check
            user_id: The user's ID

        Returns:
            True if user is present and not stale
        """
        cutoff = time.time() - PRESENCE_TTL

        if redis_service.is_connected:
            try:
                score = await redis_service.presence_get_score(room_id, user_id)
                return score is not None and score > cutoff
            except Exception as e:
                logger.error(f"Redis is_present error: {e}")
                return False
        else:
            # Fallback: query local storage
            async with self._get_lock():
                users = self._local_presence.get(room_id, {})
                presence = users.get(user_id)
                return presence is not None and presence.last_seen > cutoff

    async def get_stats(self) -> dict[str, Any]:
        """
        Get presence manager statistics.

        Returns:
            Dictionary with stats
        """
        if redis_service.is_connected:
            try:
                keys = await redis_service.scan_keys(f"{self._PRESENCE_PREFIX}*")
                total_rooms = len(keys)
                total_entries = 0
                cutoff = time.time() - PRESENCE_TTL

                for key in keys:
                    room_id = key.replace(self._PRESENCE_PREFIX, "")
                    users = await redis_service.presence_get_room(room_id, cutoff)
                    total_entries += len(users)

                return {
                    "backend": "redis",
                    "total_rooms": total_rooms,
                    "total_presence_entries": total_entries,
                }
            except Exception as e:
                logger.error(f"Redis get_stats error: {e}")
                return {"backend": "redis", "error": str(e)}
        else:
            # Fallback: query local storage
            total_users = len(self._local_user_rooms)
            total_rooms = len(self._local_presence)
            total_entries = sum(len(users) for users in self._local_presence.values())

            return {
                "backend": "memory",
                "total_users": total_users,
                "total_rooms": total_rooms,
                "total_presence_entries": total_entries,
                "memory_estimate_bytes": total_entries * 200,
            }


# Global singleton instance
presence_manager = PresenceManager()


# Export for use in other modules
__all__ = [
    "UserPresence",
    "PresenceManager",
    "presence_manager",
    "PRESENCE_TTL",
    "HEARTBEAT_INTERVAL",
]
