"""Unit tests for presence.py PresenceManager.

Tests cover (using local in-memory fallback when Redis is not connected):
- heartbeat: stores user metadata correctly
- leave: removes user from room
- leave_all: removes user from all rooms
- get_presence: returns correct list of present users
- is_present: checks individual user presence
- get_user_rooms: returns rooms a user is in
- get_stats: returns correct statistics
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from app.websocket.presence import (
    PRESENCE_TTL,
    PresenceManager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pm():
    """Create a fresh PresenceManager with Redis disconnected (uses local storage)."""
    manager = PresenceManager()
    return manager


@pytest.fixture
def mock_redis_disconnected():
    """Ensure redis_service.is_connected returns False."""
    with patch(
        "app.websocket.presence.redis_service"
    ) as mock_rs:
        type(mock_rs).is_connected = PropertyMock(return_value=False)
        yield mock_rs


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_stores_metadata(self, pm, mock_redis_disconnected):
        """After heartbeat, user should be present in the room."""
        await pm.heartbeat("room:1", "user-a", "Alice")

        members = await pm.get_presence("room:1")
        assert len(members) == 1
        assert members[0]["id"] == "user-a"
        assert members[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_heartbeat_updates_existing(self, pm, mock_redis_disconnected):
        """Second heartbeat updates metadata (e.g., idle status)."""
        await pm.heartbeat("room:1", "user-a", "Alice", idle=False)
        await pm.heartbeat("room:1", "user-a", "Alice", idle=True)

        members = await pm.get_presence("room:1")
        assert len(members) == 1
        assert members[0]["idle"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_avatar_url(self, pm, mock_redis_disconnected):
        await pm.heartbeat("room:1", "user-a", "Alice", avatar_url="https://example.com/avatar.png")

        members = await pm.get_presence("room:1")
        assert members[0]["avatar"] == "https://example.com/avatar.png"


# ---------------------------------------------------------------------------
# leave
# ---------------------------------------------------------------------------


class TestLeave:
    @pytest.mark.asyncio
    async def test_leave_removes_user(self, pm, mock_redis_disconnected):
        """After leave, user should not be present."""
        await pm.heartbeat("room:1", "user-a", "Alice")
        await pm.leave("room:1", "user-a")

        members = await pm.get_presence("room:1")
        assert len(members) == 0

    @pytest.mark.asyncio
    async def test_leave_nonexistent_room(self, pm, mock_redis_disconnected):
        """Leaving a room that doesn't exist should not raise."""
        await pm.leave("nonexistent", "user-a")

    @pytest.mark.asyncio
    async def test_leave_cleans_up_user_rooms(self, pm, mock_redis_disconnected):
        """After leaving last room, user_rooms entry should be cleaned up."""
        await pm.heartbeat("room:1", "user-a", "Alice")
        await pm.leave("room:1", "user-a")

        rooms = await pm.get_user_rooms("user-a")
        assert rooms == []


# ---------------------------------------------------------------------------
# leave_all
# ---------------------------------------------------------------------------


class TestLeaveAll:
    @pytest.mark.asyncio
    async def test_leave_all_removes_from_all_rooms(self, pm, mock_redis_disconnected):
        """leave_all removes user from all rooms and returns room list."""
        await pm.heartbeat("room:1", "user-a", "Alice")
        await pm.heartbeat("room:2", "user-a", "Alice")
        await pm.heartbeat("room:3", "user-a", "Alice")

        rooms_left = await pm.leave_all("user-a")

        assert set(rooms_left) == {"room:1", "room:2", "room:3"}

        for room_id in ["room:1", "room:2", "room:3"]:
            members = await pm.get_presence(room_id)
            assert len(members) == 0

    @pytest.mark.asyncio
    async def test_leave_all_nonexistent_user(self, pm, mock_redis_disconnected):
        """leave_all for user with no presence should return empty list."""
        rooms_left = await pm.leave_all("nonexistent")
        assert rooms_left == []


# ---------------------------------------------------------------------------
# get_presence
# ---------------------------------------------------------------------------


class TestGetPresence:
    @pytest.mark.asyncio
    async def test_multiple_users(self, pm, mock_redis_disconnected):
        """Room with multiple users returns all of them."""
        await pm.heartbeat("room:1", "user-a", "Alice")
        await pm.heartbeat("room:1", "user-b", "Bob")

        members = await pm.get_presence("room:1")
        ids = {m["id"] for m in members}
        assert ids == {"user-a", "user-b"}

    @pytest.mark.asyncio
    async def test_empty_room(self, pm, mock_redis_disconnected):
        """Empty room returns empty list."""
        members = await pm.get_presence("empty-room")
        assert members == []

    @pytest.mark.asyncio
    async def test_stale_entries_excluded(self, pm, mock_redis_disconnected):
        """Users with last_seen older than PRESENCE_TTL should be excluded."""
        await pm.heartbeat("room:1", "user-a", "Alice")
        # Manually expire the entry
        pm._local_presence["room:1"]["user-a"].last_seen = time.time() - PRESENCE_TTL - 10

        members = await pm.get_presence("room:1")
        assert len(members) == 0


# ---------------------------------------------------------------------------
# is_present
# ---------------------------------------------------------------------------


class TestIsPresent:
    @pytest.mark.asyncio
    async def test_present_user(self, pm, mock_redis_disconnected):
        await pm.heartbeat("room:1", "user-a", "Alice")
        assert await pm.is_present("room:1", "user-a") is True

    @pytest.mark.asyncio
    async def test_absent_user(self, pm, mock_redis_disconnected):
        assert await pm.is_present("room:1", "user-a") is False

    @pytest.mark.asyncio
    async def test_stale_user_not_present(self, pm, mock_redis_disconnected):
        await pm.heartbeat("room:1", "user-a", "Alice")
        pm._local_presence["room:1"]["user-a"].last_seen = time.time() - PRESENCE_TTL - 10
        assert await pm.is_present("room:1", "user-a") is False


# ---------------------------------------------------------------------------
# get_user_rooms
# ---------------------------------------------------------------------------


class TestGetUserRooms:
    @pytest.mark.asyncio
    async def test_user_in_multiple_rooms(self, pm, mock_redis_disconnected):
        await pm.heartbeat("room:1", "user-a", "Alice")
        await pm.heartbeat("room:2", "user-a", "Alice")

        rooms = await pm.get_user_rooms("user-a")
        assert set(rooms) == {"room:1", "room:2"}

    @pytest.mark.asyncio
    async def test_user_in_no_rooms(self, pm, mock_redis_disconnected):
        rooms = await pm.get_user_rooms("nonexistent")
        assert rooms == []


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    @pytest.mark.asyncio
    async def test_stats_with_local_backend(self, pm, mock_redis_disconnected):
        await pm.heartbeat("room:1", "user-a", "Alice")
        await pm.heartbeat("room:1", "user-b", "Bob")
        await pm.heartbeat("room:2", "user-a", "Alice")

        stats = await pm.get_stats()

        assert stats["backend"] == "memory"
        assert stats["total_rooms"] == 2
        assert stats["total_presence_entries"] == 3
        assert stats["total_users"] == 2

    @pytest.mark.asyncio
    async def test_stats_empty(self, pm, mock_redis_disconnected):
        stats = await pm.get_stats()
        assert stats["backend"] == "memory"
        assert stats["total_rooms"] == 0
        assert stats["total_presence_entries"] == 0


# ===========================================================================
# Redis-connected tests
# ===========================================================================


@pytest.fixture
def mock_redis_connected():
    """Mock redis_service as connected with a mock Redis client."""
    with patch("app.websocket.presence.redis_service") as mock_rs:
        type(mock_rs).is_connected = PropertyMock(return_value=True)
        mock_rs.client = AsyncMock()
        # Core Redis commands used by PresenceManager
        mock_rs.client.hset = AsyncMock()
        mock_rs.client.hdel = AsyncMock()
        mock_rs.client.hgetall = AsyncMock(return_value={})
        mock_rs.client.hmget = AsyncMock(return_value=[])
        mock_rs.client.publish = AsyncMock()
        mock_rs.client.delete = AsyncMock()
        mock_rs.client.keys = AsyncMock(return_value=[])
        mock_rs.client.sadd = AsyncMock()
        mock_rs.client.srem = AsyncMock()
        # Presence helper methods on redis_service itself
        mock_rs.presence_set = AsyncMock()
        mock_rs.presence_remove = AsyncMock()
        mock_rs.presence_get_room = AsyncMock(return_value=[])
        mock_rs.presence_get_score = AsyncMock(return_value=None)
        mock_rs.publish = AsyncMock()
        mock_rs.scan_keys = AsyncMock(return_value=[])
        yield mock_rs


# ---------------------------------------------------------------------------
# heartbeat (Redis)
# ---------------------------------------------------------------------------


class TestHeartbeatRedis:
    @pytest.mark.asyncio
    async def test_heartbeat_stores_in_redis(self, pm, mock_redis_connected):
        """heartbeat() should call presence_set and hset for user data."""
        await pm.heartbeat("room:1", "user-a", "Alice", avatar_url="http://img", idle=False)

        mock_redis_connected.presence_set.assert_awaited_once()
        call_args = mock_redis_connected.presence_set.call_args
        assert call_args[0][0] == "room:1"
        assert call_args[0][1] == "user-a"

        mock_redis_connected.client.hset.assert_awaited_once()
        hset_args = mock_redis_connected.client.hset.call_args
        assert "presence_data:room:1" in hset_args[0]

        # Also tracks room in user reverse index
        mock_redis_connected.client.sadd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_heartbeat_publishes_user_data(self, pm, mock_redis_connected):
        """heartbeat() stores JSON user metadata in the hash."""
        import json as _json

        await pm.heartbeat("room:1", "user-b", "Bob", avatar_url=None, idle=True)

        hset_args = mock_redis_connected.client.hset.call_args
        stored_json = hset_args[0][2]  # third positional arg is the value
        data = _json.loads(stored_json)
        assert data["name"] == "Bob"
        assert data["idle"] is True


# ---------------------------------------------------------------------------
# leave (Redis)
# ---------------------------------------------------------------------------


class TestLeaveRedis:
    @pytest.mark.asyncio
    async def test_leave_removes_from_redis(self, pm, mock_redis_connected):
        """leave() should call presence_remove, hdel, srem, and publish."""
        await pm.leave("room:1", "user-a")

        mock_redis_connected.presence_remove.assert_awaited_once_with("room:1", "user-a")
        mock_redis_connected.client.hdel.assert_awaited_once()
        mock_redis_connected.client.srem.assert_awaited_once()
        mock_redis_connected.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_leave_publishes_user_left_event(self, pm, mock_redis_connected):
        """leave() broadcasts a user_left event on the presence channel."""
        await pm.leave("room:2", "user-x")

        publish_args = mock_redis_connected.publish.call_args
        assert publish_args[0][0] == "ws:presence"
        event = publish_args[0][1]
        assert event["type"] == "user_left"
        assert event["room_id"] == "room:2"
        assert event["user_id"] == "user-x"


# ---------------------------------------------------------------------------
# get_presence (Redis)
# ---------------------------------------------------------------------------


class TestGetPresenceRedis:
    @pytest.mark.asyncio
    async def test_get_presence_reads_from_redis(self, pm, mock_redis_connected):
        """get_presence() should read sorted set + hash for user data."""
        import json as _json

        mock_redis_connected.presence_get_room.return_value = ["user-a", "user-b"]
        mock_redis_connected.client.hmget.return_value = [
            _json.dumps({"name": "Alice", "avatar": "http://a.png", "idle": False}),
            _json.dumps({"name": "Bob", "avatar": None, "idle": True}),
        ]

        result = await pm.get_presence("room:1")

        assert len(result) == 2
        assert result[0]["id"] == "user-a"
        assert result[0]["name"] == "Alice"
        assert result[0]["avatar"] == "http://a.png"
        assert result[1]["id"] == "user-b"
        assert result[1]["idle"] is True

    @pytest.mark.asyncio
    async def test_get_presence_empty_room(self, pm, mock_redis_connected):
        """Empty room returns empty list from Redis path."""
        mock_redis_connected.presence_get_room.return_value = []

        result = await pm.get_presence("empty-room")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_presence_missing_metadata(self, pm, mock_redis_connected):
        """User in sorted set but no hash data returns 'Unknown' fallback."""
        mock_redis_connected.presence_get_room.return_value = ["user-orphan"]
        mock_redis_connected.client.hmget.return_value = [None]

        result = await pm.get_presence("room:1")
        assert len(result) == 1
        assert result[0]["name"] == "Unknown"
        assert result[0]["avatar"] is None


# ---------------------------------------------------------------------------
# get_stats (Redis)
# ---------------------------------------------------------------------------


class TestGetStatsRedis:
    @pytest.mark.asyncio
    async def test_stats_returns_redis_backend(self, pm, mock_redis_connected):
        """get_stats() returns backend: 'redis' when connected."""
        mock_redis_connected.scan_keys.return_value = ["presence:room:1", "presence:room:2"]
        mock_redis_connected.presence_get_room.side_effect = [["u1", "u2"], ["u3"]]

        stats = await pm.get_stats()

        assert stats["backend"] == "redis"
        assert stats["total_rooms"] == 2
        assert stats["total_presence_entries"] == 3

    @pytest.mark.asyncio
    async def test_stats_empty_redis(self, pm, mock_redis_connected):
        """Empty Redis returns zero rooms/entries."""
        mock_redis_connected.scan_keys.return_value = []

        stats = await pm.get_stats()
        assert stats["backend"] == "redis"
        assert stats["total_rooms"] == 0
        assert stats["total_presence_entries"] == 0
