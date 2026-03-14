"""Unit tests for room_auth.py WebSocket room authorization.

Tests cover:
- check_room_access: application owner allowed, non-member denied,
  project member allowed, user-specific rooms, invalid room IDs
- Cache: hit returns result without DB query, expired entry triggers fresh query,
  cache eviction when max size exceeded
- invalidate_user_cache / invalidate_room_cache
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

from app.websocket.room_auth import (
    _AUTH_CACHE_MAX_SIZE,
    _AUTH_CACHE_TTL,
    _auth_cache,
    _get_cached_auth,
    _set_cached_auth,
    check_room_access,
    invalidate_room_cache,
    invalidate_user_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_auth_cache():
    """Ensure the auth cache is empty before/after each test."""
    _auth_cache.clear()
    yield
    _auth_cache.clear()


# ---------------------------------------------------------------------------
# Cache unit tests
# ---------------------------------------------------------------------------


class TestAuthCache:
    @pytest.mark.asyncio
    async def test_get_cached_returns_none_when_empty(self):
        uid = uuid4()
        result = await _get_cached_auth(uid, "application:123")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_cached(self):
        uid = uuid4()
        room_id = "application:test"
        await _set_cached_auth(uid, room_id, True)
        result = await _get_cached_auth(uid, room_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self):
        uid = uuid4()
        room_id = "project:test"
        # Manually insert an expired entry
        cache_key = (str(uid), room_id)
        _auth_cache[cache_key] = (True, time.time() - 10)
        result = await _get_cached_auth(uid, room_id)
        assert result is None
        # Entry should be removed
        assert cache_key not in _auth_cache

    @pytest.mark.asyncio
    async def test_cache_eviction_when_max_size_exceeded(self):
        """When cache hits max size, half of entries should be evicted."""
        # Fill cache to max size
        for i in range(_AUTH_CACHE_MAX_SIZE):
            key = (f"user-{i}", f"room-{i}")
            _auth_cache[key] = (True, time.time() + _AUTH_CACHE_TTL)

        assert len(_auth_cache) >= _AUTH_CACHE_MAX_SIZE

        # Setting one more should trigger eviction
        uid = uuid4()
        await _set_cached_auth(uid, "new-room", True)

        # Cache should have been trimmed (roughly half + 1 new entry)
        assert len(_auth_cache) < _AUTH_CACHE_MAX_SIZE


class TestInvalidateCache:
    @pytest.mark.asyncio
    async def test_invalidate_user_cache(self):
        uid = uuid4()
        await _set_cached_auth(uid, "room-1", True)
        await _set_cached_auth(uid, "room-2", False)
        other_uid = uuid4()
        await _set_cached_auth(other_uid, "room-1", True)

        invalidate_user_cache(uid)

        # User's entries should be gone
        assert await _get_cached_auth(uid, "room-1") is None
        assert await _get_cached_auth(uid, "room-2") is None
        # Other user's entry should remain
        assert await _get_cached_auth(other_uid, "room-1") is True

    @pytest.mark.asyncio
    async def test_invalidate_room_cache(self):
        uid_a = uuid4()
        uid_b = uuid4()
        room = "application:abc"
        await _set_cached_auth(uid_a, room, True)
        await _set_cached_auth(uid_b, room, False)
        await _set_cached_auth(uid_a, "other-room", True)

        invalidate_room_cache(room)

        assert await _get_cached_auth(uid_a, room) is None
        assert await _get_cached_auth(uid_b, room) is None
        # Other room should remain
        assert await _get_cached_auth(uid_a, "other-room") is True


# ---------------------------------------------------------------------------
# check_room_access
# ---------------------------------------------------------------------------


class TestCheckRoomAccess:
    @pytest.mark.asyncio
    async def test_invalid_room_format_no_colon(self):
        result = await check_room_access(uuid4(), "noformat")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_room_format_empty(self):
        result = await check_room_access(uuid4(), "")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_resource_id(self):
        result = await check_room_access(uuid4(), "application:not-a-uuid")
        assert result is False

    @pytest.mark.asyncio
    async def test_user_room_own_user(self):
        """User-specific room: own user_id -> True (no DB query)."""
        uid = uuid4()
        result = await check_room_access(uid, f"user:{uid}")
        assert result is True

    @pytest.mark.asyncio
    async def test_user_room_other_user(self):
        """User-specific room: other user_id -> False."""
        uid = uuid4()
        other = uuid4()
        result = await check_room_access(uid, f"user:{other}")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self):
        """Cached result should be returned without calling _check_room_access_async."""
        uid = uuid4()
        app_id = uuid4()
        room_id = f"application:{app_id}"
        await _set_cached_auth(uid, room_id, True)

        with patch(
            "app.websocket.room_auth._check_room_access_async",
            new_callable=AsyncMock,
        ) as mock_check:
            result = await check_room_access(uid, room_id)

        assert result is True
        mock_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_db_and_caches(self):
        """Cache miss -> calls DB check and stores result in cache."""
        uid = uuid4()
        app_id = uuid4()
        room_id = f"application:{app_id}"

        with patch(
            "app.websocket.room_auth._check_room_access_async",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_check:
            result = await check_room_access(uid, room_id)

        assert result is True
        mock_check.assert_called_once_with(uid, "application", app_id)
        # Should now be cached
        cached = await _get_cached_auth(uid, room_id)
        assert cached is True

    @pytest.mark.asyncio
    async def test_db_error_returns_false(self):
        """When _check_room_access_async raises, returns False."""
        uid = uuid4()
        app_id = uuid4()
        room_id = f"application:{app_id}"

        with patch(
            "app.websocket.room_auth._check_room_access_async",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection error"),
        ):
            result = await check_room_access(uid, room_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_room_type_returns_false(self):
        """Unknown room type (valid UUID) -> False."""
        uid = uuid4()
        resource = uuid4()

        with patch(
            "app.websocket.room_auth._check_room_access_async",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await check_room_access(uid, f"unknown_type:{resource}")

        assert result is False


# ---------------------------------------------------------------------------
# Integration tests with DB (application/project access)
# ---------------------------------------------------------------------------


class TestApplicationAccess:
    @pytest.mark.asyncio
    async def test_application_owner_can_join(self, db_session, test_user, test_application):
        """Application owner should have access to the application room."""
        from app.websocket.room_auth import _check_application_access

        result = await _check_application_access(db_session, test_user.id, test_application.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_non_member_denied(self, db_session, test_user_2, test_application):
        """Non-member, non-owner should be denied."""
        from app.websocket.room_auth import _check_application_access

        result = await _check_application_access(db_session, test_user_2.id, test_application.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_application_member_allowed(self, db_session, test_user_2, test_application):
        """ApplicationMember record grants access."""
        from app.models.application_member import ApplicationMember
        from app.websocket.room_auth import _check_application_access

        member = ApplicationMember(
            application_id=test_application.id,
            user_id=test_user_2.id,
            role="member",
        )
        db_session.add(member)
        await db_session.flush()

        result = await _check_application_access(db_session, test_user_2.id, test_application.id)
        assert result is True


class TestProjectAccess:
    @pytest.mark.asyncio
    async def test_project_member_via_app_owner(self, db_session, test_user, test_project):
        """App owner has access to all projects in the app."""
        from app.websocket.room_auth import _check_project_access

        result = await _check_project_access(db_session, test_user.id, test_project.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_project_nonexistent_returns_false(self, db_session, test_user):
        """Non-existent project -> False."""
        from app.websocket.room_auth import _check_project_access

        result = await _check_project_access(db_session, test_user.id, uuid4())
        assert result is False
