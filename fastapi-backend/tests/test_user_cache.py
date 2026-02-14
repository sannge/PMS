"""Tests for user cache service.

Tests the in-memory caching functionality for user profiles,
application roles, and project roles.
"""

import time
from dataclasses import dataclass
from typing import Optional
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.services.user_cache_service import (
    # User cache
    CachedUser,
    get_cached_user,
    set_cached_user,
    invalidate_user,
    clear_user_cache,
    # App role cache
    get_cached_app_role,
    set_cached_app_role,
    invalidate_app_role,
    invalidate_all_app_roles_for_user,
    invalidate_all_app_roles_for_app,
    clear_app_role_cache,
    # Project role cache
    get_cached_project_role,
    has_cached_project_role,
    set_cached_project_role,
    invalidate_project_role,
    invalidate_all_project_roles_for_user,
    invalidate_all_project_roles_for_project,
    clear_project_role_cache,
    # Helpers
    clear_all_caches,
    get_cache_stats,
    _evict_oldest,
    _user_cache,
    _app_role_cache,
    _project_role_cache,
    _CACHE_TTL,
    _MAX_SIZE,
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
            mock_time.time.return_value = time.time() + _CACHE_TTL + 100
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
            mock_time.time.return_value = time.time() + _CACHE_TTL + 100
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
            mock_time.time.return_value = time.time() + _CACHE_TTL + 100
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
        """Test evicting oldest entries from cache."""
        cache = {}
        base_time = time.time()

        # Add 10 entries with different expiry times
        for i in range(10):
            cache[f"key{i}"] = ("value", base_time + i * 10)

        original_size = len(cache)
        _evict_oldest(cache)

        # Should evict 10% (1 entry)
        assert len(cache) == original_size - 1
        # Oldest entry (key0) should be gone
        assert "key0" not in cache
        # Newest entry (key9) should remain
        assert "key9" in cache

    def test_evict_oldest_empty_cache(self):
        """Test evicting from empty cache doesn't raise."""
        cache = {}
        _evict_oldest(cache)  # Should not raise
        assert len(cache) == 0

    def test_evict_oldest_single_entry(self):
        """Test evicting from cache with single entry."""
        cache = {"key": ("value", time.time())}
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
        assert stats["user_cache"]["max_size"] == _MAX_SIZE

        assert stats["app_role_cache"]["total"] == 1
        assert stats["project_role_cache"]["total"] == 1
        assert stats["ttl_seconds"] == _CACHE_TTL

    def test_get_cache_stats_with_expired(self):
        """Test cache stats correctly count valid entries."""
        user_id = uuid4()
        set_cached_user(MockUser(id=user_id, email="test@example.com"))

        # Get stats with simulated expired entry
        with patch("app.services.user_cache_service.time") as mock_time:
            # First call for set_cached_user uses real time
            # Stats check will use mocked future time
            mock_time.time.return_value = time.time() + _CACHE_TTL + 100
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
        # Note: This test would be slow with actual _MAX_SIZE
        # We'll test the eviction logic is called correctly

        # Fill cache to near max
        original_max = _MAX_SIZE
        try:
            # Temporarily reduce max for testing
            import app.services.user_cache_service as cache_module

            cache_module._MAX_SIZE = 10

            for i in range(12):
                user = MockUser(id=uuid4(), email=f"user{i}@example.com")
                set_cached_user(user)

            # Should have evicted some entries
            assert len(_user_cache) <= 10

        finally:
            cache_module._MAX_SIZE = original_max

    def test_app_role_cache_eviction_at_max_size(self):
        """Test app role cache evicts when reaching max size."""
        import app.services.user_cache_service as cache_module

        original_max = cache_module._MAX_SIZE
        try:
            cache_module._MAX_SIZE = 10

            for i in range(12):
                set_cached_app_role(uuid4(), uuid4(), f"role{i}")

            assert len(_app_role_cache) <= 10

        finally:
            cache_module._MAX_SIZE = original_max

    def test_project_role_cache_eviction_at_max_size(self):
        """Test project role cache evicts when reaching max size."""
        import app.services.user_cache_service as cache_module

        original_max = cache_module._MAX_SIZE
        try:
            cache_module._MAX_SIZE = 10

            for i in range(12):
                set_cached_project_role(uuid4(), uuid4(), f"role{i}")

            assert len(_project_role_cache) <= 10

        finally:
            cache_module._MAX_SIZE = original_max


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
