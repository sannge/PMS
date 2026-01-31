"""Presence management infrastructure for real-time collaboration.

Redis-based presence tracking optimized for 5000+ concurrent users
across multiple Uvicorn workers.

Uses Redis sorted sets for timestamp-based presence tracking and
Redis hashes for user metadata (name, avatar, idle status).
"""

import asyncio
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

    This enables accurate presence across multiple server instances
    (5000+ concurrent users).
    """

    # Key prefixes
    _PRESENCE_PREFIX = "presence:"
    _USER_DATA_PREFIX = "presence_data:"
    _PRESENCE_CHANNEL = "ws:presence"

    def __init__(self) -> None:
        """Initialize the presence manager."""
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        # Fallback in-memory storage when Redis is not available
        self._local_presence: dict[str, dict[str, UserPresence]] = {}
        self._local_user_rooms: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the background cleanup task."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Presence manager started")

    async def stop(self) -> None:
        """Stop the presence manager."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("Presence manager stopped")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up stale presence entries."""
        while self._running:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._cleanup_stale_presence()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Presence cleanup error: {e}")

    async def _cleanup_stale_presence(self) -> None:
        """Remove presence entries older than PRESENCE_TTL."""
        cutoff = time.time() - PRESENCE_TTL

        if redis_service.is_connected:
            # Clean up Redis presence entries
            try:
                keys = await redis_service.client.keys(f"{self._PRESENCE_PREFIX}*")
                for key in keys:
                    room_id = key.replace(self._PRESENCE_PREFIX, "")
                    removed = await redis_service.presence_cleanup(room_id, cutoff)
                    if removed > 0:
                        logger.debug(f"Cleaned {removed} stale entries from room {room_id}")
            except Exception as e:
                logger.error(f"Redis presence cleanup error: {e}")
        else:
            # Fallback: clean up local storage
            async with self._lock:
                for room_id, users in list(self._local_presence.items()):
                    stale_users = [
                        uid for uid, p in users.items()
                        if p.last_seen < cutoff
                    ]
                    for uid in stale_users:
                        del users[uid]
                        if uid in self._local_user_rooms:
                            self._local_user_rooms[uid].discard(room_id)
                            if not self._local_user_rooms[uid]:
                                del self._local_user_rooms[uid]
                    if not users:
                        del self._local_presence[room_id]

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
            except Exception as e:
                logger.error(f"Redis heartbeat error: {e}")
                # Fall through to local storage
        else:
            # Fallback: update local storage
            async with self._lock:
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
            async with self._lock:
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
                # Find all rooms where user has presence
                keys = await redis_service.client.keys(f"{self._PRESENCE_PREFIX}*")
                for key in keys:
                    room_id = key.replace(self._PRESENCE_PREFIX, "")
                    score = await redis_service.presence_get_score(room_id, user_id)
                    if score is not None:
                        await redis_service.presence_remove(room_id, user_id)
                        await redis_service.client.hdel(
                            f"{self._USER_DATA_PREFIX}{room_id}",
                            user_id
                        )
                        rooms_left.append(room_id)
            except Exception as e:
                logger.error(f"Redis leave_all error: {e}")
        else:
            # Fallback: update local storage
            async with self._lock:
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

                # Get user metadata from hash
                user_data_key = f"{self._USER_DATA_PREFIX}{room_id}"
                result = []

                for user_id in user_ids:
                    data_str = await redis_service.client.hget(user_data_key, user_id)
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
            async with self._lock:
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
                rooms = []
                keys = await redis_service.client.keys(f"{self._PRESENCE_PREFIX}*")
                for key in keys:
                    room_id = key.replace(self._PRESENCE_PREFIX, "")
                    score = await redis_service.presence_get_score(room_id, user_id)
                    if score is not None and score > cutoff:
                        rooms.append(room_id)
                return rooms
            except Exception as e:
                logger.error(f"Redis get_user_rooms error: {e}")
                return []
        else:
            # Fallback: query local storage
            async with self._lock:
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
            async with self._lock:
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
                keys = await redis_service.client.keys(f"{self._PRESENCE_PREFIX}*")
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
