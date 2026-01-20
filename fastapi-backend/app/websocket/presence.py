"""Presence management infrastructure for real-time collaboration.

Redis-based presence tracking optimized for 5000+ concurrent users.
Provides heartbeat-based presence with automatic expiration.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

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
    In-memory presence manager with Redis-like interface.

    For production with multiple server instances, replace with Redis implementation:
    - Use Redis sorted sets (ZADD) for presence tracking
    - Use Redis pub/sub for cross-instance presence updates

    This implementation is optimized for single-instance deployment (5000 concurrent users).
    """

    def __init__(self) -> None:
        """Initialize the presence manager."""
        # room_id -> {user_id: UserPresence}
        self._presence: dict[str, dict[str, UserPresence]] = {}
        # user_id -> set of room_ids (for efficient cleanup)
        self._user_rooms: dict[str, set[str]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        # Background task for cleanup
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Presence manager started")

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Presence manager stopped")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale presence entries."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._cleanup_stale_presence()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in presence cleanup: {e}")

    async def _cleanup_stale_presence(self) -> None:
        """Remove presence entries that haven't been updated within TTL."""
        cutoff = time.time() - PRESENCE_TTL
        rooms_to_update = []

        async with self._lock:
            for room_id, users in list(self._presence.items()):
                stale_users = [
                    uid for uid, presence in users.items()
                    if presence.last_seen < cutoff
                ]

                if stale_users:
                    for uid in stale_users:
                        del users[uid]
                        if uid in self._user_rooms:
                            self._user_rooms[uid].discard(room_id)
                            if not self._user_rooms[uid]:
                                del self._user_rooms[uid]

                    rooms_to_update.append(room_id)

                # Remove empty rooms
                if not users:
                    del self._presence[room_id]

        if rooms_to_update:
            logger.debug(f"Cleaned up stale presence in {len(rooms_to_update)} rooms")

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
        async with self._lock:
            if room_id not in self._presence:
                self._presence[room_id] = {}

            self._presence[room_id][user_id] = UserPresence(
                user_id=user_id,
                user_name=user_name,
                avatar_url=avatar_url,
                idle=idle,
                last_seen=time.time(),
            )

            if user_id not in self._user_rooms:
                self._user_rooms[user_id] = set()
            self._user_rooms[user_id].add(room_id)

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
        async with self._lock:
            if room_id in self._presence and user_id in self._presence[room_id]:
                del self._presence[room_id][user_id]

                # Clean up empty room
                if not self._presence[room_id]:
                    del self._presence[room_id]

            if user_id in self._user_rooms:
                self._user_rooms[user_id].discard(room_id)
                if not self._user_rooms[user_id]:
                    del self._user_rooms[user_id]

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

        async with self._lock:
            if user_id in self._user_rooms:
                rooms = list(self._user_rooms[user_id])
                for room_id in rooms:
                    if room_id in self._presence and user_id in self._presence[room_id]:
                        del self._presence[room_id][user_id]

                        if not self._presence[room_id]:
                            del self._presence[room_id]

                        rooms_left.append(room_id)

                del self._user_rooms[user_id]

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

        async with self._lock:
            users = self._presence.get(room_id, {})
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
        async with self._lock:
            return list(self._user_rooms.get(user_id, set()))

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

        async with self._lock:
            users = self._presence.get(room_id, {})
            presence = users.get(user_id)
            return presence is not None and presence.last_seen > cutoff

    def get_stats(self) -> dict[str, Any]:
        """
        Get presence manager statistics.

        Returns:
            Dictionary with stats
        """
        total_users = len(self._user_rooms)
        total_rooms = len(self._presence)
        total_presence_entries = sum(len(users) for users in self._presence.values())

        return {
            "total_users": total_users,
            "total_rooms": total_rooms,
            "total_presence_entries": total_presence_entries,
            "memory_estimate_bytes": total_presence_entries * 200,  # ~200 bytes per entry
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
