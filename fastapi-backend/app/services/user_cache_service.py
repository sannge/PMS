"""In-memory cache for user authentication and permissions.

This module provides high-performance caching for frequently accessed user data
to reduce database queries and support 5000+ concurrent users per instance.

Cache Strategy:
- User profile cache: 5 minute TTL, max 10,000 entries
- Application role cache: 5 minute TTL, max 10,000 entries
- Project role cache: 5 minute TTL, max 10,000 entries

Invalidation:
- User cache: On profile update, password change
- App role cache: On role change, member removal
- Project role cache: On role change, member removal
"""

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from uuid import UUID


# Cache configuration
_CACHE_TTL = 300  # 5 minutes
_MAX_SIZE = 10000  # Maximum entries per cache


# === User Profile Cache ===


@dataclass(frozen=True)
class CachedUser:
    """Immutable cached user data."""

    id: UUID
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]


# Cache storage: user_id -> (CachedUser, expiry_timestamp)
_user_cache: Dict[str, Tuple[CachedUser, float]] = {}


def get_cached_user(user_id: UUID) -> Optional[CachedUser]:
    """
    Get user from cache if present and not expired.

    Args:
        user_id: The user's UUID

    Returns:
        CachedUser if found and valid, None otherwise
    """
    cached = _user_cache.get(str(user_id))
    if cached and cached[1] > time.time():
        return cached[0]
    # Remove expired entry
    if cached:
        _user_cache.pop(str(user_id), None)
    return None


def set_cached_user(user) -> None:
    """
    Store user in cache.

    Args:
        user: User model instance with id, email, display_name, avatar_url
    """
    if len(_user_cache) >= _MAX_SIZE:
        _evict_oldest(_user_cache)

    _user_cache[str(user.id)] = (
        CachedUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=getattr(user, "avatar_url", None),
        ),
        time.time() + _CACHE_TTL,
    )


def invalidate_user(user_id: UUID) -> None:
    """
    Remove user from cache.

    Args:
        user_id: The user's UUID to invalidate
    """
    _user_cache.pop(str(user_id), None)


def clear_user_cache() -> None:
    """Clear entire user cache. Used for testing or admin operations."""
    _user_cache.clear()


# === Application Role Cache ===


# Cache storage: "user_id:app_id" -> (role, expiry_timestamp)
_app_role_cache: Dict[str, Tuple[str, float]] = {}


def get_cached_app_role(user_id: UUID, app_id: UUID) -> Optional[str]:
    """
    Get application role from cache if present and not expired.

    Args:
        user_id: The user's UUID
        app_id: The application's UUID

    Returns:
        Role string if found and valid, None otherwise
    """
    key = f"{user_id}:{app_id}"
    cached = _app_role_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]
    # Remove expired entry
    if cached:
        _app_role_cache.pop(key, None)
    return None


def set_cached_app_role(user_id: UUID, app_id: UUID, role: str) -> None:
    """
    Store application role in cache.

    Args:
        user_id: The user's UUID
        app_id: The application's UUID
        role: The role string (e.g., "owner", "admin", "editor", "viewer")
    """
    if len(_app_role_cache) >= _MAX_SIZE:
        _evict_oldest(_app_role_cache)

    key = f"{user_id}:{app_id}"
    _app_role_cache[key] = (role, time.time() + _CACHE_TTL)


def invalidate_app_role(user_id: UUID, app_id: UUID) -> None:
    """
    Remove application role from cache.

    Args:
        user_id: The user's UUID
        app_id: The application's UUID
    """
    key = f"{user_id}:{app_id}"
    _app_role_cache.pop(key, None)


def invalidate_all_app_roles_for_user(user_id: UUID) -> None:
    """
    Remove all application roles for a user from cache.

    Args:
        user_id: The user's UUID
    """
    prefix = f"{user_id}:"
    keys_to_remove = [k for k in _app_role_cache.keys() if k.startswith(prefix)]
    for key in keys_to_remove:
        _app_role_cache.pop(key, None)


def invalidate_all_app_roles_for_app(app_id: UUID) -> None:
    """
    Remove all application roles for an app from cache.

    Args:
        app_id: The application's UUID
    """
    suffix = f":{app_id}"
    keys_to_remove = [k for k in _app_role_cache.keys() if k.endswith(suffix)]
    for key in keys_to_remove:
        _app_role_cache.pop(key, None)


def clear_app_role_cache() -> None:
    """Clear entire application role cache. Used for testing."""
    _app_role_cache.clear()


# === Project Role Cache ===


# Cache storage: "user_id:project_id" -> (role or None, expiry_timestamp)
_project_role_cache: Dict[str, Tuple[Optional[str], float]] = {}


def get_cached_project_role(user_id: UUID, project_id: UUID) -> Optional[str]:
    """
    Get project role from cache if present and not expired.

    Args:
        user_id: The user's UUID
        project_id: The project's UUID

    Returns:
        Role string if found and valid, None otherwise.
        Note: Returns None both for "not in cache" and "cached as no-role".
        Use has_cached_project_role() to distinguish.
    """
    key = f"{user_id}:{project_id}"
    cached = _project_role_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]
    # Remove expired entry
    if cached:
        _project_role_cache.pop(key, None)
    return None


def has_cached_project_role(user_id: UUID, project_id: UUID) -> bool:
    """
    Check if project role is in cache (regardless of value).

    Args:
        user_id: The user's UUID
        project_id: The project's UUID

    Returns:
        True if in cache and not expired, False otherwise
    """
    key = f"{user_id}:{project_id}"
    cached = _project_role_cache.get(key)
    if cached and cached[1] > time.time():
        return True
    return False


def set_cached_project_role(
    user_id: UUID, project_id: UUID, role: Optional[str]
) -> None:
    """
    Store project role in cache.

    Args:
        user_id: The user's UUID
        project_id: The project's UUID
        role: The role string, or None if user has no role in project
    """
    if len(_project_role_cache) >= _MAX_SIZE:
        _evict_oldest(_project_role_cache)

    key = f"{user_id}:{project_id}"
    _project_role_cache[key] = (role, time.time() + _CACHE_TTL)


def invalidate_project_role(user_id: UUID, project_id: UUID) -> None:
    """
    Remove project role from cache.

    Args:
        user_id: The user's UUID
        project_id: The project's UUID
    """
    key = f"{user_id}:{project_id}"
    _project_role_cache.pop(key, None)


def invalidate_all_project_roles_for_user(user_id: UUID) -> None:
    """
    Remove all project roles for a user from cache.

    Args:
        user_id: The user's UUID
    """
    prefix = f"{user_id}:"
    keys_to_remove = [k for k in _project_role_cache.keys() if k.startswith(prefix)]
    for key in keys_to_remove:
        _project_role_cache.pop(key, None)


def invalidate_all_project_roles_for_project(project_id: UUID) -> None:
    """
    Remove all project roles for a project from cache.

    Args:
        project_id: The project's UUID
    """
    suffix = f":{project_id}"
    keys_to_remove = [k for k in _project_role_cache.keys() if k.endswith(suffix)]
    for key in keys_to_remove:
        _project_role_cache.pop(key, None)


def clear_project_role_cache() -> None:
    """Clear entire project role cache. Used for testing."""
    _project_role_cache.clear()


# === Helper Functions ===


def _evict_oldest(cache: dict) -> None:
    """
    Remove oldest 10% of entries from cache.

    Args:
        cache: The cache dictionary to evict from
    """
    if not cache:
        return

    # Sort by expiry time (second element of tuple)
    sorted_items = sorted(cache.items(), key=lambda x: x[1][1])
    evict_count = max(1, len(sorted_items) // 10)

    for key, _ in sorted_items[:evict_count]:
        cache.pop(key, None)


def clear_all_caches() -> None:
    """Clear all caches. Used for testing or admin operations."""
    clear_user_cache()
    clear_app_role_cache()
    clear_project_role_cache()


def get_cache_stats() -> dict:
    """
    Get cache statistics for monitoring.

    Returns:
        Dictionary with cache sizes and other stats
    """
    now = time.time()

    def count_valid(cache: dict) -> int:
        return sum(1 for _, (_, expiry) in cache.items() if expiry > now)

    return {
        "user_cache": {
            "total": len(_user_cache),
            "valid": count_valid(_user_cache),
            "max_size": _MAX_SIZE,
        },
        "app_role_cache": {
            "total": len(_app_role_cache),
            "valid": count_valid(_app_role_cache),
            "max_size": _MAX_SIZE,
        },
        "project_role_cache": {
            "total": len(_project_role_cache),
            "valid": count_valid(_project_role_cache),
            "max_size": _MAX_SIZE,
        },
        "ttl_seconds": _CACHE_TTL,
    }
