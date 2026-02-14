"""Room authorization for WebSocket connections.

Validates that users have access to rooms they attempt to join.

Features:
- Native async database operations (no thread pool needed)
- TTL-based caching to prevent DB overload during reconnection storms
- Hierarchical access checks (application -> project -> task)
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session_maker
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.project_member import ProjectMember
from ..models.document import Document
from ..models.task import Task

logger = logging.getLogger(__name__)

# ============================================================================
# Auth Result Caching
# ============================================================================
# Cache (user_id, room_id) -> (result: bool, expires_at: float)
# This prevents DB overload during reconnection storms (5000 users × 5 rooms each)

_auth_cache: Dict[Tuple[str, str], Tuple[bool, float]] = {}
_AUTH_CACHE_TTL = 300  # 5 minutes TTL
_AUTH_CACHE_MAX_SIZE = 50000  # Max cache entries
_cache_lock = asyncio.Lock()


async def _get_cached_auth(user_id: UUID, room_id: str) -> Optional[bool]:
    """Get cached auth result if valid, None if not cached or expired."""
    cache_key = (str(user_id), room_id)
    cached = _auth_cache.get(cache_key)
    if cached is None:
        return None
    result, expires_at = cached
    if time.time() > expires_at:
        # Expired - remove from cache
        _auth_cache.pop(cache_key, None)
        return None
    return result


async def _set_cached_auth(user_id: UUID, room_id: str, result: bool) -> None:
    """Cache an auth result with TTL."""
    cache_key = (str(user_id), room_id)
    expires_at = time.time() + _AUTH_CACHE_TTL

    # Enforce max cache size (simple eviction: clear half when full)
    if len(_auth_cache) >= _AUTH_CACHE_MAX_SIZE:
        async with _cache_lock:
            # Clear oldest half of entries
            sorted_entries = sorted(_auth_cache.items(), key=lambda x: x[1][1])
            entries_to_remove = len(sorted_entries) // 2
            for key, _ in sorted_entries[:entries_to_remove]:
                _auth_cache.pop(key, None)

    _auth_cache[cache_key] = (result, expires_at)


def invalidate_user_cache(user_id: UUID) -> None:
    """Invalidate all cached auth results for a user (call on membership changes)."""
    user_id_str = str(user_id)
    keys_to_remove = [k for k in _auth_cache.keys() if k[0] == user_id_str]
    for key in keys_to_remove:
        _auth_cache.pop(key, None)


def invalidate_room_cache(room_id: str) -> None:
    """Invalidate all cached auth results for a room (call on room permission changes)."""
    keys_to_remove = [k for k in _auth_cache.keys() if k[1] == room_id]
    for key in keys_to_remove:
        _auth_cache.pop(key, None)


async def check_room_access(user_id: UUID, room_id: str) -> bool:
    """
    Check if a user has access to a specific room.

    Room ID formats:
    - application:{uuid} - Application room (requires membership)
    - project:{uuid} - Project room (requires membership in parent application)
    - task:{uuid} - Task room (requires access to parent project)
    - user:{uuid} - User-specific room (only for own user)

    Args:
        user_id: The user's UUID
        room_id: The room identifier

    Returns:
        bool: True if user has access, False otherwise
    """
    if not room_id or ":" not in room_id:
        logger.warning(f"[Room Auth] DENIED - invalid room format: {room_id}")
        return False

    try:
        room_type, resource_id_str = room_id.split(":", 1)
        resource_id = UUID(resource_id_str)
    except (ValueError, AttributeError):
        logger.warning(f"[Room Auth] DENIED - invalid room ID format: {room_id}")
        return False

    # User-specific rooms - only allow access to own room (no DB needed, no caching)
    if room_type == "user":
        return resource_id == user_id

    # Check cache first (prevents DB overload during reconnection storms)
    cached_result = await _get_cached_auth(user_id, room_id)
    if cached_result is not None:
        return cached_result

    # Perform async DB check
    try:
        result = await _check_room_access_async(user_id, room_type, resource_id)
        # Cache the result
        await _set_cached_auth(user_id, room_id, result)
        return result
    except Exception as e:
        logger.error(f"[Room Auth] ERROR checking room access: {e}")
        return False


async def _check_room_access_async(user_id: UUID, room_type: str, resource_id: UUID) -> bool:
    """
    Async room access check using native async SQLAlchemy.
    """
    async with async_session_maker() as db:
        if room_type == "application":
            return await _check_application_access(db, user_id, resource_id)
        elif room_type == "project":
            return await _check_project_access(db, user_id, resource_id)
        elif room_type == "task":
            return await _check_task_access(db, user_id, resource_id)
        elif room_type == "document":
            return await _check_document_access(db, user_id, resource_id)
        else:
            logger.warning(f"[Room Auth] DENIED - unknown room type: {room_type}")
            return False


async def _check_application_access(db: AsyncSession, user_id: UUID, application_id: UUID) -> bool:
    """Check if user is a member of the application or the owner."""
    # First check if user is the application owner (for backwards compatibility
    # with applications created before ApplicationMember records were created for owners)
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if application and application.owner_id == user_id:
        return True

    # Then check ApplicationMember table
    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    return member is not None


async def _check_project_access(db: AsyncSession, user_id: UUID, project_id: UUID) -> bool:
    """Check if user has access to the project via application or project membership."""
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        return False

    # Check if user is an application member (has access to all projects)
    if await _check_application_access(db, user_id, project.application_id):
        return True

    # Check if user is a project member (has access to this specific project)
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    project_member = result.scalar_one_or_none()
    return project_member is not None


async def _check_task_access(db: AsyncSession, user_id: UUID, task_id: UUID) -> bool:
    """Check if user has access to the task via project/application membership."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        return False
    return await _check_project_access(db, user_id, task.project_id)


async def _check_document_access(db: AsyncSession, user_id: UUID, document_id: UUID) -> bool:
    """Check if user has access to a document based on its scope."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        return False

    # Personal document - only the owner has access
    if document.user_id is not None and document.user_id == user_id:
        return True

    # Application-scoped document - check application membership
    if document.application_id is not None:
        return await _check_application_access(db, user_id, document.application_id)

    # Project-scoped document - check project access (transitively checks app membership)
    if document.project_id is not None:
        return await _check_project_access(db, user_id, document.project_id)

    return False


