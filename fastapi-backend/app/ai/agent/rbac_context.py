"""RBAC context resolver for the Blair AI agent.

Builds and caches the set of application and project IDs a user has
access to. This context is injected into the agent state so that every
tool call can validate access without redundant DB queries.

Cache strategy: Redis with 30-second TTL. This is short enough that
permission changes propagate quickly, but long enough to avoid hammering
the DB during a multi-turn conversation (typical agent session is 5-30s).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.application import Application
from ...models.application_member import ApplicationMember
from ...models.project import Project
from ...services.redis_service import redis_service

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "agent:rbac"
CACHE_TTL_SECONDS = 30


class AgentRBACContext:
    """Resolves and caches RBAC context for the AI agent.

    Provides static methods to build the RBAC context (accessible
    application and project IDs for a user) and validate access checks.
    All methods are stateless — context is passed explicitly.
    """

    @staticmethod
    async def build_agent_context(
        user_id: str | UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Build the RBAC context for a user, with Redis caching.

        Checks Redis first. On cache miss, queries the database to find
        all applications the user owns or is a member of, and all active
        projects within those applications.

        Args:
            user_id: The user's UUID (string or UUID object).
            db: Active async database session for fallback queries.

        Returns:
            Dict with keys:
            - ``user_id``: str — the user ID
            - ``accessible_app_ids``: list[str] — application IDs
            - ``accessible_project_ids``: list[str] — project IDs
        """
        user_id_str = str(user_id)
        cache_key = f"{CACHE_KEY_PREFIX}:{user_id_str}"

        # Try Redis cache first
        try:
            cached = await redis_service.get(cache_key)
            if cached is not None:
                context = json.loads(cached)
                logger.debug(
                    "RBAC cache hit for user %s: %d apps, %d projects",
                    user_id_str,
                    len(context.get("accessible_app_ids", [])),
                    len(context.get("accessible_project_ids", [])),
                )
                return context
        except Exception:
            # Redis failure is non-fatal — fall through to DB query
            logger.warning(
                "Redis cache read failed for RBAC context, falling back to DB",
                exc_info=True,
            )

        # Cache miss — query the database
        user_uuid = UUID(user_id_str) if isinstance(user_id, str) else user_id

        # Get applications where user is the owner
        owner_query = select(Application.id).where(
            Application.owner_id == user_uuid
        )

        # Get applications where user is a member (any role)
        member_query = select(ApplicationMember.application_id).where(
            ApplicationMember.user_id == user_uuid
        )

        # Union both sets of application IDs
        combined_app_query = union_all(owner_query, member_query).subquery()
        app_result = await db.execute(
            select(combined_app_query.c.id)
        )
        accessible_app_ids = [str(row[0]) for row in app_result.all()]

        # Get all active projects in accessible applications
        accessible_project_ids: list[str] = []
        if accessible_app_ids:
            app_uuids = [UUID(aid) for aid in accessible_app_ids]
            project_query = select(Project.id).where(
                Project.application_id.in_(app_uuids),
                Project.archived_at.is_(None),
            )
            project_result = await db.execute(project_query)
            accessible_project_ids = [str(row[0]) for row in project_result.all()]

        context = {
            "user_id": user_id_str,
            "accessible_app_ids": accessible_app_ids,
            "accessible_project_ids": accessible_project_ids,
        }

        logger.info(
            "RBAC context built for user %s: %d apps, %d projects",
            user_id_str,
            len(accessible_app_ids),
            len(accessible_project_ids),
        )

        # Cache the result in Redis
        try:
            await redis_service.set(
                cache_key,
                json.dumps(context),
                ttl=CACHE_TTL_SECONDS,
            )
        except Exception:
            # Redis failure is non-fatal — context is still valid
            logger.warning(
                "Redis cache write failed for RBAC context",
                exc_info=True,
            )

        return context

    @staticmethod
    def validate_app_access(
        application_id: str | UUID,
        context: dict[str, Any],
    ) -> bool:
        """Check if the user has access to a specific application.

        Args:
            application_id: The application UUID to check.
            context: RBAC context dict from ``build_agent_context``.

        Returns:
            True if the application ID is in the user's accessible set.
        """
        app_id_str = str(application_id)
        ids = context.get("accessible_app_ids", [])
        return app_id_str in (ids if isinstance(ids, set) else set(ids))

    @staticmethod
    def validate_project_access(
        project_id: str | UUID,
        context: dict[str, Any],
    ) -> bool:
        """Check if the user has access to a specific project.

        Args:
            project_id: The project UUID to check.
            context: RBAC context dict from ``build_agent_context``.

        Returns:
            True if the project ID is in the user's accessible set.
        """
        project_id_str = str(project_id)
        ids = context.get("accessible_project_ids", [])
        return project_id_str in (ids if isinstance(ids, set) else set(ids))

    @staticmethod
    async def invalidate_cache(user_id: str | UUID) -> None:
        """Invalidate the cached RBAC context for a user.

        Call this when the user's permissions change (e.g., added to or
        removed from an application, role change).

        Args:
            user_id: The user's UUID.
        """
        cache_key = f"{CACHE_KEY_PREFIX}:{str(user_id)}"
        try:
            await redis_service.delete(cache_key)
            logger.debug("RBAC cache invalidated for user %s", user_id)
        except Exception:
            logger.warning(
                "Failed to invalidate RBAC cache for user %s",
                user_id,
                exc_info=True,
            )
