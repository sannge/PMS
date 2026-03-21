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
- Cross-worker: Redis pub/sub on ws:user_cache_invalidate channel
"""

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import UUID

# Cache configuration — runtime getter functions (never freeze at import time)
from ..ai.config_service import get_agent_config


def _get_cache_ttl() -> int:
    """Return cache TTL at call time from runtime config."""
    return max(1, get_agent_config().get_int("cache.user_cache_ttl", 300))


def _get_max_size() -> int:
    """Return max cache size at call time from runtime config."""
    return max(1, get_agent_config().get_int("cache.user_cache_max_size", 10000))


# === User Profile Cache ===


@dataclass(frozen=True)
class CachedUser:
    """Immutable cached user data."""

    id: UUID
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    email_verified: bool = True
    is_developer: bool = False


# Cache storage: user_id -> (CachedUser, expiry_timestamp, last_accessed)
# OrderedDict tracks insertion/move order for O(1) LRU eviction.
_user_cache: OrderedDict[str, Tuple[CachedUser, float, float]] = OrderedDict()


def get_cached_user(user_id: UUID) -> Optional[CachedUser]:
    """
    Get user from cache if present and not expired.

    Args:
        user_id: The user's UUID

    Returns:
        CachedUser if found and valid, None otherwise
    """
    key = str(user_id)
    cached = _user_cache.get(key)
    if cached and cached[1] > time.time():
        _user_cache.move_to_end(key)  # O(1) LRU promotion
        return cached[0]
    # Remove expired entry
    if cached:
        _user_cache.pop(key, None)
    return None


def set_cached_user(user) -> None:
    """
    Store user in cache.

    Args:
        user: User model instance with id, email, display_name, avatar_url
    """
    if len(_user_cache) >= _get_max_size():
        _evict_oldest(_user_cache)

    now = time.time()
    _user_cache[str(user.id)] = (
        CachedUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=getattr(user, "avatar_url", None),
            email_verified=getattr(user, "email_verified", True),
            is_developer=getattr(user, "is_developer", False),
        ),
        now + _get_cache_ttl(),
        now,
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


# Cache storage: "user_id:app_id" -> (role or None, expiry_timestamp, last_accessed)
# OrderedDict tracks insertion/move order for O(1) LRU eviction.
_app_role_cache: OrderedDict[str, Tuple[Optional[str], float, float]] = OrderedDict()


def get_cached_app_role(user_id: UUID, app_id: UUID) -> Optional[str]:
    """
    Get application role from cache if present and not expired.

    Args:
        user_id: The user's UUID
        app_id: The application's UUID

    Returns:
        Role string if found and valid, None otherwise.
        Note: Returns None both for "not in cache" and "cached as no-role".
        Use has_cached_app_role() to distinguish.
    """
    key = f"{user_id}:{app_id}"
    cached = _app_role_cache.get(key)
    if cached and cached[1] > time.time():
        _app_role_cache.move_to_end(key)  # O(1) LRU promotion
        return cached[0]
    # Remove expired entry
    if cached:
        _app_role_cache.pop(key, None)
    return None


def has_cached_app_role(user_id: UUID, app_id: UUID) -> bool:
    """
    Check if application role is in cache (regardless of value).

    Args:
        user_id: The user's UUID
        app_id: The application's UUID

    Returns:
        True if in cache and not expired, False otherwise
    """
    key = f"{user_id}:{app_id}"
    cached = _app_role_cache.get(key)
    if cached and cached[1] > time.time():
        _app_role_cache.move_to_end(key)  # O(1) LRU promotion
        return True
    if cached:
        _app_role_cache.pop(key, None)  # Evict expired entry
    return False


def set_cached_app_role(
    user_id: UUID, app_id: UUID, role: Optional[str]
) -> None:
    """
    Store application role in cache.

    Args:
        user_id: The user's UUID
        app_id: The application's UUID
        role: The role string (e.g., "owner", "admin", "editor", "viewer"),
              or None if user has no role in application
    """
    if len(_app_role_cache) >= _get_max_size():
        _evict_oldest(_app_role_cache)

    now = time.time()
    key = f"{user_id}:{app_id}"
    _app_role_cache[key] = (role, now + _get_cache_ttl(), now)


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


# Cache storage: "user_id:project_id" -> (role or None, expiry_timestamp, last_accessed)
# OrderedDict tracks insertion/move order for O(1) LRU eviction.
_project_role_cache: OrderedDict[str, Tuple[Optional[str], float, float]] = OrderedDict()


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
        _project_role_cache.move_to_end(key)  # O(1) LRU promotion
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
        _project_role_cache.move_to_end(key)  # O(1) LRU promotion
        return True
    if cached:
        _project_role_cache.pop(key, None)  # Evict expired entry
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
    if len(_project_role_cache) >= _get_max_size():
        _evict_oldest(_project_role_cache)

    now = time.time()
    key = f"{user_id}:{project_id}"
    _project_role_cache[key] = (role, now + _get_cache_ttl(), now)


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


def _evict_oldest(cache: OrderedDict) -> None:
    """
    Remove least recently used 10% of entries from cache.

    Uses OrderedDict.popitem(last=False) for O(1) eviction of the oldest
    (least recently used) entries.

    Args:
        cache: The OrderedDict cache to evict from
    """
    if not cache:
        return

    evict_count = max(1, len(cache) // 10)
    for _ in range(evict_count):
        if cache:
            cache.popitem(last=False)  # O(1) — removes oldest (least recently used)


def clear_all_caches() -> None:
    """Clear all in-memory caches. Used for testing or admin operations.

    Clears user/role caches from this module plus other module-level caches
    that could leak state between tests.
    """
    clear_user_cache()
    clear_app_role_cache()
    clear_project_role_cache()

    # Clear WebSocket room authorization cache
    from ..websocket.room_auth import _auth_cache
    _auth_cache.clear()

    # Clear AI health check cache (keyed by fixed strings "embedding"/"chat")
    from ..main import _ai_health_cache
    _ai_health_cache.clear()

    # Note: auto-archive throttle is now Redis-based (no in-memory dict to clear)


# === Cross-Worker Cache Invalidation via Redis pub/sub ===

_USER_CACHE_INVALIDATE_CHANNEL = "ws:user_cache_invalidate"


async def publish_user_cache_invalidation(
    *,
    user_id: str | None = None,
    app_id: str | None = None,
    project_id: str | None = None,
) -> None:
    """Publish a user cache invalidation event to all workers.

    Best-effort: silently ignores errors (same pattern as room_auth.py).
    """
    from ..services.redis_service import redis_service
    if redis_service.is_connected:
        try:
            payload = {k: v for k, v in {
                "user_id": user_id, "app_id": app_id, "project_id": project_id,
            }.items() if v is not None}
            await redis_service.publish(
                _USER_CACHE_INVALIDATE_CHANNEL,
                payload,
            )
        except Exception:
            pass  # Best-effort


async def _handle_user_cache_invalidation(data: dict) -> None:
    """Handle cross-worker user cache invalidation."""
    uid = data.get("user_id")
    aid = data.get("app_id")
    pid = data.get("project_id")

    if uid:
        try:
            _uid = UUID(uid)
        except (ValueError, AttributeError):
            return
        if aid:
            try:
                invalidate_app_role(_uid, UUID(aid))
            except (ValueError, AttributeError):
                pass
        elif pid:
            try:
                invalidate_project_role(_uid, UUID(pid))
            except (ValueError, AttributeError):
                pass
        else:
            # User-level invalidation: clear user + all roles
            invalidate_user(_uid)
            invalidate_all_app_roles_for_user(_uid)
            invalidate_all_project_roles_for_user(_uid)
    elif aid:
        try:
            invalidate_all_app_roles_for_app(UUID(aid))
        except (ValueError, AttributeError):
            pass
    elif pid:
        try:
            invalidate_all_project_roles_for_project(UUID(pid))
        except (ValueError, AttributeError):
            pass


async def setup_user_cache_pubsub() -> None:
    """Subscribe to user cache invalidation channel (call at startup)."""
    from ..services.redis_service import redis_service
    if redis_service.is_connected:
        await redis_service.subscribe(
            _USER_CACHE_INVALIDATE_CHANNEL, _handle_user_cache_invalidation
        )


def get_cache_stats() -> dict:
    """
    Get cache statistics for monitoring.

    Returns:
        Dictionary with cache sizes and other stats
    """
    now = time.time()

    def count_valid(cache: dict) -> int:
        return sum(1 for _, v in cache.items() if v[1] > now)

    return {
        "user_cache": {
            "total": len(_user_cache),
            "valid": count_valid(_user_cache),
            "max_size": _get_max_size(),
        },
        "app_role_cache": {
            "total": len(_app_role_cache),
            "valid": count_valid(_app_role_cache),
            "max_size": _get_max_size(),
        },
        "project_role_cache": {
            "total": len(_project_role_cache),
            "valid": count_valid(_project_role_cache),
            "max_size": _get_max_size(),
        },
        "ttl_seconds": _get_cache_ttl(),
    }
