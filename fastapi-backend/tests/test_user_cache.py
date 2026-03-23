"""Tests for user cache service.

Tests the in-memory caching functionality for user profiles,
application roles, and project roles.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.user_cache_service import (
    # User cache
    CachedUser,
    _app_role_cache,
    _evict_oldest,
    _get_cache_ttl,
    _get_max_size,
    _handle_user_cache_invalidation,
    _project_role_cache,
    _user_cache,
    # Helpers
    clear_all_caches,
    clear_app_role_cache,
    clear_project_role_cache,
    clear_user_cache,
    get_cache_stats,
    # App role cache
    get_cached_app_role,
    # Project role cache
    get_cached_project_role,
    get_cached_user,
    has_cached_app_role,
    has_cached_project_role,
    invalidate_all_app_roles_for_app,
    invalidate_all_app_roles_for_user,
    invalidate_all_project_roles_for_project,
    invalidate_all_project_roles_for_user,
    invalidate_app_role,
    invalidate_project_role,
    invalidate_user,
    # Cross-worker invalidation
    publish_user_cache_invalidation,
    set_cached_app_role,
    set_cached_project_role,
    set_cached_user,
)

# ============================================================================
# Fixtures
# ============================================================================


@dataclass
class MockUser:
    """Mock user object for testing."""

    id: any
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all caches before and after each test."""
    clear_all_caches()
    yield
    clear_all_caches()


# ============================================================================
# User Cache Tests
# ============================================================================


class TestUserCache:
    """Tests for user profile caching."""

    def test_get_cached_user_miss(self):
        """Test cache miss returns None."""
        user_id = uuid4()
        result = get_cached_user(user_id)
        assert result is None

    def test_set_and_get_cached_user(self):
        """Test setting and retrieving a user from cache."""
        user_id = uuid4()
        user = MockUser(
            id=user_id,
            email="test@example.com",
            display_name="Test User",
            avatar_url="https://example.com/avatar.jpg",
        )

        set_cached_user(user)
        result = get_cached_user(user_id)

        assert result is not None
        assert result.id == user_id
        assert result.email == "test@example.com"
        assert result.display_name == "Test User"
        assert result.avatar_url == "https://example.com/avatar.jpg"

    def test_get_cached_user_expired(self):
        """Test expired cache entry returns None."""
        user_id = uuid4()
        user = MockUser(id=user_id, email="test@example.com")

        set_cached_user(user)

        # Mock time to be past TTL
        with patch("app.services.user_cache_service.time") as mock_time:
            mock_time.time.return_value = time.time() + _get_cache_ttl() + 100
            result = get_cached_user(user_id)

        assert result is None

    def test_invalidate_user(self):
        """Test invalidating a user removes from cache."""
        user_id = uuid4()
        user = MockUser(id=user_id, email="test@example.com")

        set_cached_user(user)
        assert get_cached_user(user_id) is not None

        invalidate_user(user_id)
        assert get_cached_user(user_id) is None

    def test_invalidate_nonexistent_user(self):
        """Test invalidating non-existent user doesn't raise."""
        user_id = uuid4()
        invalidate_user(user_id)  # Should not raise

    def test_clear_user_cache(self):
        """Test clearing entire user cache."""
        for i in range(5):
            user = MockUser(id=uuid4(), email=f"user{i}@example.com")
            set_cached_user(user)

        assert len(_user_cache) == 5

        clear_user_cache()
        assert len(_user_cache) == 0

    def test_user_cache_without_avatar(self):
        """Test caching user without avatar_url attribute."""
        user_id = uuid4()

        @dataclass
        class UserNoAvatar:
            id: any
            email: str
            display_name: Optional[str] = None

        user = UserNoAvatar(id=user_id, email="test@example.com")
        set_cached_user(user)
        result = get_cached_user(user_id)

        assert result is not None
        assert result.avatar_url is None


# ============================================================================
# App Role Cache Tests
# ============================================================================


class TestAppRoleCache:
    """Tests for application role caching."""

    def test_get_cached_app_role_miss(self):
        """Test cache miss returns None."""
        user_id, app_id = uuid4(), uuid4()
        result = get_cached_app_role(user_id, app_id)
        assert result is None

    def test_set_and_get_cached_app_role(self):
        """Test setting and retrieving an app role."""
        user_id, app_id = uuid4(), uuid4()

        set_cached_app_role(user_id, app_id, "editor")
        result = get_cached_app_role(user_id, app_id)

        assert result == "editor"

    def test_get_cached_app_role_expired(self):
        """Test expired cache entry returns None."""
        user_id, app_id = uuid4(), uuid4()

        set_cached_app_role(user_id, app_id, "admin")

        with patch("app.services.user_cache_service.time") as mock_time:
            mock_time.time.return_value = time.time() + _get_cache_ttl() + 100
            result = get_cached_app_role(user_id, app_id)

        assert result is None

    def test_invalidate_app_role(self):
        """Test invalidating an app role."""
        user_id, app_id = uuid4(), uuid4()

        set_cached_app_role(user_id, app_id, "viewer")
        assert get_cached_app_role(user_id, app_id) == "viewer"

        invalidate_app_role(user_id, app_id)
        assert get_cached_app_role(user_id, app_id) is None

    def test_invalidate_all_app_roles_for_user(self):
        """Test invalidating all app roles for a user."""
        user_id = uuid4()
        app_ids = [uuid4() for _ in range(3)]

        for app_id in app_ids:
            set_cached_app_role(user_id, app_id, "editor")

        # Also add roles for another user
        other_user_id = uuid4()
        set_cached_app_role(other_user_id, app_ids[0], "viewer")

        invalidate_all_app_roles_for_user(user_id)

        # User's roles should be gone
        for app_id in app_ids:
            assert get_cached_app_role(user_id, app_id) is None

        # Other user's role should remain
        assert get_cached_app_role(other_user_id, app_ids[0]) == "viewer"

    def test_invalidate_all_app_roles_for_app(self):
        """Test invalidating all app roles for an application."""
        app_id = uuid4()
        user_ids = [uuid4() for _ in range(3)]

        for user_id in user_ids:
            set_cached_app_role(user_id, app_id, "editor")

        # Also add role for another app
        other_app_id = uuid4()
        set_cached_app_role(user_ids[0], other_app_id, "viewer")

        invalidate_all_app_roles_for_app(app_id)

        # App's roles should be gone
        for user_id in user_ids:
            assert get_cached_app_role(user_id, app_id) is None

        # Other app's role should remain
        assert get_cached_app_role(user_ids[0], other_app_id) == "viewer"

    def test_clear_app_role_cache(self):
        """Test clearing entire app role cache."""
        for i in range(5):
            set_cached_app_role(uuid4(), uuid4(), f"role{i}")

        assert len(_app_role_cache) == 5

        clear_app_role_cache()
        assert len(_app_role_cache) == 0


# ============================================================================
# Project Role Cache Tests
# ============================================================================


class TestProjectRoleCache:
    """Tests for project role caching."""

    def test_get_cached_project_role_miss(self):
        """Test cache miss returns None."""
        user_id, project_id = uuid4(), uuid4()
        result = get_cached_project_role(user_id, project_id)
        assert result is None

    def test_has_cached_project_role_miss(self):
        """Test has_cached returns False for miss."""
        user_id, project_id = uuid4(), uuid4()
        assert has_cached_project_role(user_id, project_id) is False

    def test_set_and_get_cached_project_role(self):
        """Test setting and retrieving a project role."""
        user_id, project_id = uuid4(), uuid4()

        set_cached_project_role(user_id, project_id, "admin")
        result = get_cached_project_role(user_id, project_id)

        assert result == "admin"
        assert has_cached_project_role(user_id, project_id) is True

    def test_cached_project_role_none_value(self):
        """Test caching None role (user has no role in project)."""
        user_id, project_id = uuid4(), uuid4()

        set_cached_project_role(user_id, project_id, None)

        # get returns None, but has_cached returns True
        assert get_cached_project_role(user_id, project_id) is None
        assert has_cached_project_role(user_id, project_id) is True

    def test_get_cached_project_role_expired(self):
        """Test expired cache entry returns None."""
        user_id, project_id = uuid4(), uuid4()

        set_cached_project_role(user_id, project_id, "editor")

        with patch("app.services.user_cache_service.time") as mock_time:
            mock_time.time.return_value = time.time() + _get_cache_ttl() + 100
            result = get_cached_project_role(user_id, project_id)
            has_result = has_cached_project_role(user_id, project_id)

        assert result is None
        assert has_result is False

    def test_invalidate_project_role(self):
        """Test invalidating a project role."""
        user_id, project_id = uuid4(), uuid4()

        set_cached_project_role(user_id, project_id, "viewer")
        assert get_cached_project_role(user_id, project_id) == "viewer"

        invalidate_project_role(user_id, project_id)
        assert get_cached_project_role(user_id, project_id) is None
        assert has_cached_project_role(user_id, project_id) is False

    def test_invalidate_all_project_roles_for_user(self):
        """Test invalidating all project roles for a user."""
        user_id = uuid4()
        project_ids = [uuid4() for _ in range(3)]

        for project_id in project_ids:
            set_cached_project_role(user_id, project_id, "editor")

        # Also add roles for another user
        other_user_id = uuid4()
        set_cached_project_role(other_user_id, project_ids[0], "viewer")

        invalidate_all_project_roles_for_user(user_id)

        # User's roles should be gone
        for project_id in project_ids:
            assert has_cached_project_role(user_id, project_id) is False

        # Other user's role should remain
        assert get_cached_project_role(other_user_id, project_ids[0]) == "viewer"

    def test_invalidate_all_project_roles_for_project(self):
        """Test invalidating all project roles for a project."""
        project_id = uuid4()
        user_ids = [uuid4() for _ in range(3)]

        for user_id in user_ids:
            set_cached_project_role(user_id, project_id, "editor")

        # Also add role for another project
        other_project_id = uuid4()
        set_cached_project_role(user_ids[0], other_project_id, "viewer")

        invalidate_all_project_roles_for_project(project_id)

        # Project's roles should be gone
        for user_id in user_ids:
            assert has_cached_project_role(user_id, project_id) is False

        # Other project's role should remain
        assert get_cached_project_role(user_ids[0], other_project_id) == "viewer"

    def test_clear_project_role_cache(self):
        """Test clearing entire project role cache."""
        for i in range(5):
            set_cached_project_role(uuid4(), uuid4(), f"role{i}")

        assert len(_project_role_cache) == 5

        clear_project_role_cache()
        assert len(_project_role_cache) == 0


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestCacheHelpers:
    """Tests for cache helper functions."""

    def test_evict_oldest(self):
        """Test evicting least recently used entries from OrderedDict cache."""
        cache: OrderedDict = OrderedDict()
        base_time = time.time()

        # Add 10 entries — OrderedDict tracks insertion order for LRU
        for i in range(10):
            cache[f"key{i}"] = ("value", base_time + 1000, base_time + i * 10)

        original_size = len(cache)
        _evict_oldest(cache)

        # Should evict 10% (1 entry)
        assert len(cache) == original_size - 1
        # Oldest inserted entry (key0) should be gone (popitem(last=False))
        assert "key0" not in cache
        # Most recently inserted entry (key9) should remain
        assert "key9" in cache

    def test_evict_oldest_empty_cache(self):
        """Test evicting from empty cache doesn't raise."""
        cache: OrderedDict = OrderedDict()
        _evict_oldest(cache)  # Should not raise
        assert len(cache) == 0

    def test_evict_oldest_single_entry(self):
        """Test evicting from cache with single entry."""
        cache: OrderedDict = OrderedDict({"key": ("value", time.time(), time.time())})
        _evict_oldest(cache)
        # Should evict at least 1
        assert len(cache) == 0

    def test_clear_all_caches(self):
        """Test clearing all caches at once."""
        # Populate all caches
        set_cached_user(MockUser(id=uuid4(), email="test@example.com"))
        set_cached_app_role(uuid4(), uuid4(), "editor")
        set_cached_project_role(uuid4(), uuid4(), "viewer")

        assert len(_user_cache) > 0
        assert len(_app_role_cache) > 0
        assert len(_project_role_cache) > 0

        clear_all_caches()

        assert len(_user_cache) == 0
        assert len(_app_role_cache) == 0
        assert len(_project_role_cache) == 0

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        # Add some entries
        set_cached_user(MockUser(id=uuid4(), email="test@example.com"))
        set_cached_app_role(uuid4(), uuid4(), "editor")
        set_cached_project_role(uuid4(), uuid4(), "viewer")

        stats = get_cache_stats()

        assert "user_cache" in stats
        assert "app_role_cache" in stats
        assert "project_role_cache" in stats
        assert "ttl_seconds" in stats

        assert stats["user_cache"]["total"] == 1
        assert stats["user_cache"]["valid"] == 1
        assert stats["user_cache"]["max_size"] == _get_max_size()

        assert stats["app_role_cache"]["total"] == 1
        assert stats["project_role_cache"]["total"] == 1
        assert stats["ttl_seconds"] == _get_cache_ttl()

    def test_get_cache_stats_with_expired(self):
        """Test cache stats correctly count valid entries."""
        user_id = uuid4()
        set_cached_user(MockUser(id=user_id, email="test@example.com"))

        # Get stats with simulated expired entry
        with patch("app.services.user_cache_service.time") as mock_time:
            # First call for set_cached_user uses real time
            # Stats check will use mocked future time
            mock_time.time.return_value = time.time() + _get_cache_ttl() + 100
            stats = get_cache_stats()

        # Entry exists but is expired
        assert stats["user_cache"]["total"] == 1
        assert stats["user_cache"]["valid"] == 0


# ============================================================================
# Cache Size Limit Tests
# ============================================================================


class TestCacheSizeLimits:
    """Tests for cache size limit enforcement."""

    def test_user_cache_eviction_at_max_size(self):
        """Test user cache evicts when reaching max size."""
        with patch("app.services.user_cache_service._get_max_size", return_value=10):
            for i in range(12):
                user = MockUser(id=uuid4(), email=f"user{i}@example.com")
                set_cached_user(user)

            # Should have evicted some entries
            assert len(_user_cache) <= 10

    def test_app_role_cache_eviction_at_max_size(self):
        """Test app role cache evicts when reaching max size."""
        with patch("app.services.user_cache_service._get_max_size", return_value=10):
            for i in range(12):
                set_cached_app_role(uuid4(), uuid4(), f"role{i}")

            assert len(_app_role_cache) <= 10

    def test_project_role_cache_eviction_at_max_size(self):
        """Test project role cache evicts when reaching max size."""
        with patch("app.services.user_cache_service._get_max_size", return_value=10):
            for i in range(12):
                set_cached_project_role(uuid4(), uuid4(), f"role{i}")

            assert len(_project_role_cache) <= 10


# ============================================================================
# CachedUser Tests
# ============================================================================


class TestCachedUser:
    """Tests for CachedUser dataclass."""

    def test_cached_user_immutable(self):
        """Test CachedUser is immutable (frozen)."""
        user = CachedUser(
            id=uuid4(),
            email="test@example.com",
            display_name="Test",
            avatar_url=None,
        )

        with pytest.raises(AttributeError):
            user.email = "new@example.com"

    def test_cached_user_hashable(self):
        """Test CachedUser can be used in sets/dicts (hashable)."""
        user1 = CachedUser(
            id=uuid4(),
            email="test@example.com",
            display_name="Test",
            avatar_url=None,
        )
        user2 = CachedUser(
            id=uuid4(),
            email="test2@example.com",
            display_name="Test 2",
            avatar_url=None,
        )

        user_set = {user1, user2}
        assert len(user_set) == 2


# ============================================================================
# T1: Tests for publish_user_cache_invalidation
# ============================================================================


class TestPublishUserCacheInvalidation:
    """Tests for cross-worker cache invalidation via Redis pub/sub."""

    @pytest.mark.asyncio
    async def test_publish_when_redis_connected(self):
        """Verify publish calls redis_service.publish with correct channel and payload."""
        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.publish = AsyncMock()

        with patch("app.services.redis_service.redis_service", mock_redis):
            await publish_user_cache_invalidation(user_id="abc", app_id="def")

        # Payload strips None values via dict comprehension in source
        mock_redis.publish.assert_awaited_once_with(
            "ws:user_cache_invalidate",
            {"user_id": "abc", "app_id": "def"},
        )

    @pytest.mark.asyncio
    async def test_publish_when_redis_disconnected(self):
        """Verify publish is silently skipped when Redis is down."""
        mock_redis = MagicMock()
        mock_redis.is_connected = False
        mock_redis.publish = AsyncMock()

        with patch("app.services.redis_service.redis_service", mock_redis):
            await publish_user_cache_invalidation(user_id="abc")

        mock_redis.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_swallows_redis_exception(self):
        """Verify publish swallows exceptions (best-effort contract)."""
        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.publish = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch("app.services.redis_service.redis_service", mock_redis):
            # Should NOT raise
            await publish_user_cache_invalidation(user_id="abc")

    @pytest.mark.asyncio
    async def test_publish_with_project_id(self):
        """Verify publish includes project_id in payload."""
        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.publish = AsyncMock()

        with patch("app.services.redis_service.redis_service", mock_redis):
            await publish_user_cache_invalidation(user_id="u1", project_id="p1")

        # Payload strips None values via dict comprehension in source
        mock_redis.publish.assert_awaited_once_with(
            "ws:user_cache_invalidate",
            {"user_id": "u1", "project_id": "p1"},
        )

    @pytest.mark.asyncio
    async def test_publish_with_no_ids(self):
        """Verify publish sends empty payload when no IDs specified (None values stripped)."""
        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.publish = AsyncMock()

        with patch("app.services.redis_service.redis_service", mock_redis):
            await publish_user_cache_invalidation()

        # Payload strips None values via dict comprehension in source
        mock_redis.publish.assert_awaited_once_with(
            "ws:user_cache_invalidate",
            {},
        )


# ============================================================================
# T2: Tests for _handle_user_cache_invalidation
# ============================================================================


class TestHandleUserCacheInvalidation:
    """Tests for pub/sub message dispatch to local invalidation functions."""

    @pytest.mark.asyncio
    async def test_uid_and_aid_invalidates_app_role(self):
        """uid + aid -> invalidate_app_role(uid, aid)."""
        uid = uuid4()
        aid = uuid4()
        other_aid = uuid4()

        set_cached_app_role(uid, aid, "editor")
        set_cached_app_role(uid, other_aid, "viewer")

        await _handle_user_cache_invalidation({"user_id": str(uid), "app_id": str(aid)})

        assert get_cached_app_role(uid, aid) is None
        assert not has_cached_app_role(uid, aid)
        # Other app role should remain
        assert get_cached_app_role(uid, other_aid) == "viewer"

    @pytest.mark.asyncio
    async def test_uid_and_pid_invalidates_project_role(self):
        """uid + pid -> invalidate_project_role(uid, pid)."""
        uid = uuid4()
        pid = uuid4()
        other_pid = uuid4()

        set_cached_project_role(uid, pid, "admin")
        set_cached_project_role(uid, other_pid, "viewer")

        await _handle_user_cache_invalidation({"user_id": str(uid), "project_id": str(pid)})

        assert get_cached_project_role(uid, pid) is None
        assert not has_cached_project_role(uid, pid)
        # Other project role should remain
        assert get_cached_project_role(uid, other_pid) == "viewer"

    @pytest.mark.asyncio
    async def test_uid_only_invalidates_user_and_all_roles(self):
        """uid only -> invalidate_user + invalidate_all_app_roles_for_user + invalidate_all_project_roles_for_user."""
        uid = uuid4()
        other_uid = uuid4()
        aid1, aid2 = uuid4(), uuid4()
        pid1, pid2 = uuid4(), uuid4()

        # Populate caches for the target user
        user = MockUser(id=uid, email="target@example.com")
        set_cached_user(user)
        set_cached_app_role(uid, aid1, "editor")
        set_cached_app_role(uid, aid2, "admin")
        set_cached_project_role(uid, pid1, "viewer")
        set_cached_project_role(uid, pid2, "editor")

        # Populate caches for another user (should not be affected)
        other_user = MockUser(id=other_uid, email="other@example.com")
        set_cached_user(other_user)
        set_cached_app_role(other_uid, aid1, "viewer")
        set_cached_project_role(other_uid, pid1, "admin")

        await _handle_user_cache_invalidation({"user_id": str(uid)})

        # Target user's entries should be gone
        assert get_cached_user(uid) is None
        assert get_cached_app_role(uid, aid1) is None
        assert get_cached_app_role(uid, aid2) is None
        assert get_cached_project_role(uid, pid1) is None
        assert get_cached_project_role(uid, pid2) is None

        # Other user's entries should remain
        assert get_cached_user(other_uid) is not None
        assert get_cached_app_role(other_uid, aid1) == "viewer"
        assert get_cached_project_role(other_uid, pid1) == "admin"

    @pytest.mark.asyncio
    async def test_aid_only_invalidates_all_app_roles_for_app(self):
        """aid only -> invalidate_all_app_roles_for_app(aid)."""
        aid = uuid4()
        other_aid = uuid4()
        uid1, uid2 = uuid4(), uuid4()

        set_cached_app_role(uid1, aid, "editor")
        set_cached_app_role(uid2, aid, "viewer")
        set_cached_app_role(uid1, other_aid, "admin")

        await _handle_user_cache_invalidation({"app_id": str(aid)})

        # All roles for aid should be gone
        assert get_cached_app_role(uid1, aid) is None
        assert get_cached_app_role(uid2, aid) is None
        # Other app role should remain
        assert get_cached_app_role(uid1, other_aid) == "admin"

    @pytest.mark.asyncio
    async def test_pid_only_invalidates_all_project_roles_for_project(self):
        """pid only -> invalidate_all_project_roles_for_project(pid)."""
        pid = uuid4()
        other_pid = uuid4()
        uid1, uid2 = uuid4(), uuid4()

        set_cached_project_role(uid1, pid, "editor")
        set_cached_project_role(uid2, pid, "viewer")
        set_cached_project_role(uid1, other_pid, "admin")

        await _handle_user_cache_invalidation({"project_id": str(pid)})

        # All roles for pid should be gone
        assert get_cached_project_role(uid1, pid) is None
        assert get_cached_project_role(uid2, pid) is None
        # Other project role should remain
        assert get_cached_project_role(uid1, other_pid) == "admin"

    @pytest.mark.asyncio
    async def test_invalid_uid_does_not_crash(self):
        """Invalid UUID string for uid returns early without crash."""
        aid = uuid4()
        uid = uuid4()
        set_cached_app_role(uid, aid, "editor")

        # Should not raise, and should not modify anything
        await _handle_user_cache_invalidation({"user_id": "not-a-valid-uuid", "app_id": str(aid)})

        # Existing entries should remain untouched
        assert get_cached_app_role(uid, aid) == "editor"

    @pytest.mark.asyncio
    async def test_empty_payload_is_noop(self):
        """Empty dict does nothing."""
        uid = uuid4()
        aid = uuid4()
        pid = uuid4()

        user = MockUser(id=uid, email="test@example.com")
        set_cached_user(user)
        set_cached_app_role(uid, aid, "editor")
        set_cached_project_role(uid, pid, "viewer")

        await _handle_user_cache_invalidation({})

        # All entries should remain
        assert get_cached_user(uid) is not None
        assert get_cached_app_role(uid, aid) == "editor"
        assert get_cached_project_role(uid, pid) == "viewer"

    @pytest.mark.asyncio
    async def test_uid_with_aid_takes_priority_over_pid(self):
        """When uid + aid are both present, pid is ignored (elif branch)."""
        uid = uuid4()
        aid = uuid4()
        pid = uuid4()

        set_cached_app_role(uid, aid, "editor")
        set_cached_project_role(uid, pid, "viewer")

        await _handle_user_cache_invalidation({"user_id": str(uid), "app_id": str(aid), "project_id": str(pid)})

        # App role should be invalidated (aid branch taken)
        assert get_cached_app_role(uid, aid) is None
        # Project role should remain (pid branch not taken when aid present)
        assert get_cached_project_role(uid, pid) == "viewer"

    @pytest.mark.asyncio
    async def test_invalid_aid_with_valid_uid_does_not_crash(self):
        """Invalid UUID for aid with valid uid should not crash (caught by except)."""
        uid = uuid4()
        aid = uuid4()
        set_cached_app_role(uid, aid, "editor")

        # Should not raise
        await _handle_user_cache_invalidation({"user_id": str(uid), "app_id": "bad-uuid"})

        # Existing entries should remain (bad UUID caught and passed)
        assert get_cached_app_role(uid, aid) == "editor"


# ============================================================================
# T3: Tests for has_cached_app_role
# ============================================================================


class TestHasCachedAppRole:
    """Tests for has_cached_app_role distinguishing cache miss from negative cache."""

    def test_miss_returns_false(self):
        """Cache miss returns False."""
        user_id, app_id = uuid4(), uuid4()
        assert has_cached_app_role(user_id, app_id) is False

    def test_hit_with_role_returns_true(self):
        """Cached role returns True."""
        user_id, app_id = uuid4(), uuid4()
        set_cached_app_role(user_id, app_id, "editor")
        assert has_cached_app_role(user_id, app_id) is True

    def test_hit_with_none_role_returns_true(self):
        """Cached None (negative cache) returns True."""
        user_id, app_id = uuid4(), uuid4()
        set_cached_app_role(user_id, app_id, None)
        # get_cached_app_role returns None, but has_cached_app_role returns True
        assert get_cached_app_role(user_id, app_id) is None
        assert has_cached_app_role(user_id, app_id) is True

    def test_expired_returns_false(self):
        """Expired entry returns False."""
        user_id, app_id = uuid4(), uuid4()
        set_cached_app_role(user_id, app_id, "viewer")

        with patch("app.services.user_cache_service.time") as mock_time:
            mock_time.time.return_value = time.time() + _get_cache_ttl() + 100
            assert has_cached_app_role(user_id, app_id) is False

    def test_different_app_ids_are_independent(self):
        """Roles for different app_ids don't interfere."""
        user_id = uuid4()
        app_id_1, app_id_2 = uuid4(), uuid4()

        set_cached_app_role(user_id, app_id_1, "editor")
        # app_id_2 has no cache entry
        assert has_cached_app_role(user_id, app_id_1) is True
        assert has_cached_app_role(user_id, app_id_2) is False


# ============================================================================
# T5: LRU Promotion Test
# ============================================================================


class TestLRUPromotion:
    """Tests for LRU promotion via get access."""

    def test_get_promotes_entry_survives_eviction(self):
        """Reading an entry promotes it in LRU order, surviving eviction."""
        with patch("app.services.user_cache_service._get_max_size", return_value=5):
            # Insert 5 entries (cache full)
            user_ids = []
            for i in range(5):
                uid = uuid4()
                user_ids.append(uid)
                user = MockUser(id=uid, email=f"user{i}@example.com")
                set_cached_user(user)
                # Small delay to ensure distinct last_accessed timestamps
                time.sleep(0.001)

            assert len(_user_cache) == 5

            # Read (get) entry #0 — this promotes it to most-recently-used
            result = get_cached_user(user_ids[0])
            assert result is not None
            assert result.email == "user0@example.com"

            # Insert entry #5 — triggers eviction of oldest UNREAD entry
            new_uid = uuid4()
            new_user = MockUser(id=new_uid, email="user5@example.com")
            set_cached_user(new_user)

            # Entry #0 should still exist (was promoted by read)
            assert get_cached_user(user_ids[0]) is not None
            # Entry #1 should have been evicted (oldest unread)
            assert get_cached_user(user_ids[1]) is None

    def test_app_role_get_promotes_lru(self):
        """Reading an app role entry promotes it in LRU order."""
        with patch("app.services.user_cache_service._get_max_size", return_value=5):
            keys = []
            for i in range(5):
                uid, aid = uuid4(), uuid4()
                keys.append((uid, aid))
                set_cached_app_role(uid, aid, f"role{i}")
                time.sleep(0.001)

            assert len(_app_role_cache) == 5

            # Read entry #0 to promote it
            result = get_cached_app_role(keys[0][0], keys[0][1])
            assert result == "role0"

            # Insert entry #5 — triggers eviction
            set_cached_app_role(uuid4(), uuid4(), "role5")

            # Entry #0 should survive (promoted by read)
            assert get_cached_app_role(keys[0][0], keys[0][1]) == "role0"
            # Entry #1 should be evicted (oldest unread)
            assert get_cached_app_role(keys[1][0], keys[1][1]) is None


# ============================================================================
# T6: Cross-Worker Invalidation E2E
# ============================================================================


class TestCrossWorkerInvalidationE2E:
    """End-to-end tests simulating pub/sub message -> cache clearing."""

    @pytest.mark.asyncio
    async def test_handler_clears_correct_app_role_entry(self):
        """Simulate pub/sub message -> verify correct app role entry cleared."""
        uid = uuid4()
        aid_target = uuid4()
        aid_other = uuid4()

        # Populate caches
        user = MockUser(id=uid, email="e2e@example.com")
        set_cached_user(user)
        set_cached_app_role(uid, aid_target, "editor")
        set_cached_app_role(uid, aid_other, "admin")
        set_cached_project_role(uid, uuid4(), "viewer")

        # Simulate pub/sub message for specific uid+aid
        await _handle_user_cache_invalidation({"user_id": str(uid), "app_id": str(aid_target)})

        # Targeted entry is gone
        assert get_cached_app_role(uid, aid_target) is None
        assert not has_cached_app_role(uid, aid_target)

        # Unrelated entries remain
        assert get_cached_user(uid) is not None
        assert get_cached_app_role(uid, aid_other) == "admin"

    @pytest.mark.asyncio
    async def test_handler_clears_correct_project_role_entry(self):
        """Simulate pub/sub message -> verify correct project role entry cleared."""
        uid = uuid4()
        pid_target = uuid4()
        pid_other = uuid4()

        set_cached_project_role(uid, pid_target, "editor")
        set_cached_project_role(uid, pid_other, "viewer")

        await _handle_user_cache_invalidation({"user_id": str(uid), "project_id": str(pid_target)})

        assert get_cached_project_role(uid, pid_target) is None
        assert get_cached_project_role(uid, pid_other) == "viewer"

    @pytest.mark.asyncio
    async def test_handler_user_level_clears_all_caches_for_user(self):
        """Simulate user-level invalidation -> all caches for user cleared."""
        uid = uuid4()
        other_uid = uuid4()
        aid1, aid2 = uuid4(), uuid4()
        pid1 = uuid4()

        user = MockUser(id=uid, email="target@example.com")
        set_cached_user(user)
        set_cached_app_role(uid, aid1, "editor")
        set_cached_app_role(uid, aid2, "admin")
        set_cached_project_role(uid, pid1, "viewer")

        # Other user entries
        other_user = MockUser(id=other_uid, email="safe@example.com")
        set_cached_user(other_user)
        set_cached_app_role(other_uid, aid1, "viewer")

        await _handle_user_cache_invalidation({"user_id": str(uid)})

        # All target user entries gone
        assert get_cached_user(uid) is None
        assert get_cached_app_role(uid, aid1) is None
        assert get_cached_app_role(uid, aid2) is None
        assert get_cached_project_role(uid, pid1) is None

        # Other user entries intact
        assert get_cached_user(other_uid) is not None
        assert get_cached_app_role(other_uid, aid1) == "viewer"

    @pytest.mark.asyncio
    async def test_handler_app_level_clears_all_users_for_app(self):
        """Simulate app-level invalidation -> all user roles for that app cleared."""
        aid = uuid4()
        uid1, uid2 = uuid4(), uuid4()
        other_aid = uuid4()

        set_cached_app_role(uid1, aid, "editor")
        set_cached_app_role(uid2, aid, "viewer")
        set_cached_app_role(uid1, other_aid, "admin")

        await _handle_user_cache_invalidation({"app_id": str(aid)})

        assert get_cached_app_role(uid1, aid) is None
        assert get_cached_app_role(uid2, aid) is None
        assert get_cached_app_role(uid1, other_aid) == "admin"
