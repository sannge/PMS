"""Unit tests for AI agent RBAC context (app.ai.agent.rbac_context).

Tests cover:
- AgentRBACContext.build_agent_context with Redis cache hit
- AgentRBACContext.build_agent_context with Redis cache miss (DB query)
- AgentRBACContext.build_agent_context with Redis failure (non-fatal)
- validate_app_access true/false
- validate_project_access true/false
- invalidate_cache deletes Redis key
- CACHE_TTL_SECONDS constant
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.ai.agent.rbac_context import (
    CACHE_KEY_PREFIX,
    CACHE_TTL_SECONDS,
    AgentRBACContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(app_ids: list[str] | None = None,
                  project_ids: list[str] | None = None) -> AsyncMock:
    """Build a mock AsyncSession that returns given app and project IDs.

    The first db.execute() call returns app IDs (union_all query).
    The second call returns project IDs.
    """
    db = AsyncMock()
    app_rows = [(uid,) for uid in (app_ids or [])]
    project_rows = [(uid,) for uid in (project_ids or [])]

    app_result = MagicMock()
    app_result.all.return_value = app_rows

    project_result = MagicMock()
    project_result.all.return_value = project_rows

    db.execute = AsyncMock(side_effect=[app_result, project_result])
    return db


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------

class TestRBACConstants:

    def test_cache_ttl_seconds_is_30(self):
        assert CACHE_TTL_SECONDS == 30

    def test_cache_key_prefix(self):
        assert CACHE_KEY_PREFIX == "agent:rbac"


# ---------------------------------------------------------------------------
# Tests: build_agent_context
# ---------------------------------------------------------------------------

class TestBuildAgentContext:

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_cache_hit_returns_cached_context(self, mock_redis):
        user_id = str(uuid4())
        cached = {
            "user_id": user_id,
            "accessible_app_ids": ["app-1", "app-2"],
            "accessible_project_ids": ["proj-1"],
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(cached))

        db = AsyncMock()
        result = await AgentRBACContext.build_agent_context(user_id, db)

        assert result == cached
        # DB should NOT be queried on cache hit
        db.execute.assert_not_called()
        mock_redis.get.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}:{user_id}")

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_cache_miss_queries_db_and_caches_result(self, mock_redis):
        user_id = str(uuid4())
        app_id = str(uuid4())
        proj_id = str(uuid4())

        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        db = _make_mock_db(app_ids=[app_id], project_ids=[proj_id])

        result = await AgentRBACContext.build_agent_context(user_id, db)

        assert result["user_id"] == user_id
        assert app_id in result["accessible_app_ids"]
        assert proj_id in result["accessible_project_ids"]

        # Verify Redis set was called with correct TTL
        mock_redis.set.assert_awaited_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("ttl") == CACHE_TTL_SECONDS

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_redis_get_failure_falls_through_to_db(self, mock_redis):
        user_id = str(uuid4())
        app_id = str(uuid4())

        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))

        db = _make_mock_db(app_ids=[app_id], project_ids=[])

        result = await AgentRBACContext.build_agent_context(user_id, db)

        # Should still return valid context from DB despite Redis failure
        assert result["user_id"] == user_id
        assert app_id in result["accessible_app_ids"]
        # DB was queried (at least once for apps)
        assert db.execute.await_count >= 1

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_cache_miss_no_apps_returns_empty_projects(self, mock_redis):
        user_id = str(uuid4())

        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        # User has no apps -> project query should not run
        db = AsyncMock()
        app_result = MagicMock()
        app_result.all.return_value = []
        db.execute = AsyncMock(return_value=app_result)

        result = await AgentRBACContext.build_agent_context(user_id, db)

        assert result["accessible_app_ids"] == []
        assert result["accessible_project_ids"] == []
        # Only one DB call (apps), no project query since no apps
        db.execute.assert_awaited_once()

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_accepts_uuid_object(self, mock_redis):
        user_uuid = uuid4()
        cached = {
            "user_id": str(user_uuid),
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(cached))
        db = AsyncMock()

        result = await AgentRBACContext.build_agent_context(user_uuid, db)

        assert result["user_id"] == str(user_uuid)


# ---------------------------------------------------------------------------
# Tests: validate_app_access
# ---------------------------------------------------------------------------

class TestValidateAppAccess:

    def test_returns_true_for_accessible_app(self):
        app_id = str(uuid4())
        context = {"accessible_app_ids": [app_id]}
        assert AgentRBACContext.validate_app_access(app_id, context) is True

    def test_returns_false_for_inaccessible_app(self):
        context = {"accessible_app_ids": [str(uuid4())]}
        assert AgentRBACContext.validate_app_access(str(uuid4()), context) is False

    def test_returns_false_for_empty_context(self):
        context: dict = {}
        assert AgentRBACContext.validate_app_access(str(uuid4()), context) is False

    def test_accepts_uuid_object(self):
        app_uuid = uuid4()
        context = {"accessible_app_ids": [str(app_uuid)]}
        assert AgentRBACContext.validate_app_access(app_uuid, context) is True


# ---------------------------------------------------------------------------
# Tests: validate_project_access
# ---------------------------------------------------------------------------

class TestValidateProjectAccess:

    def test_returns_true_for_accessible_project(self):
        proj_id = str(uuid4())
        context = {"accessible_project_ids": [proj_id]}
        assert AgentRBACContext.validate_project_access(proj_id, context) is True

    def test_returns_false_for_inaccessible_project(self):
        context = {"accessible_project_ids": [str(uuid4())]}
        assert AgentRBACContext.validate_project_access(str(uuid4()), context) is False

    def test_returns_false_for_empty_context(self):
        context: dict = {}
        assert AgentRBACContext.validate_project_access(str(uuid4()), context) is False

    def test_accepts_uuid_object(self):
        proj_uuid = uuid4()
        context = {"accessible_project_ids": [str(proj_uuid)]}
        assert AgentRBACContext.validate_project_access(proj_uuid, context) is True


# ---------------------------------------------------------------------------
# Tests: invalidate_cache
# ---------------------------------------------------------------------------

class TestInvalidateCache:

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_deletes_correct_key(self, mock_redis):
        user_id = str(uuid4())
        mock_redis.delete = AsyncMock()

        await AgentRBACContext.invalidate_cache(user_id)

        mock_redis.delete.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}:{user_id}")

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_redis_failure_is_non_fatal(self, mock_redis):
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))

        # Should NOT raise
        await AgentRBACContext.invalidate_cache(str(uuid4()))

    @patch("app.ai.agent.rbac_context.redis_service")
    async def test_accepts_uuid_object(self, mock_redis):
        user_uuid = uuid4()
        mock_redis.delete = AsyncMock()

        await AgentRBACContext.invalidate_cache(user_uuid)

        mock_redis.delete.assert_awaited_once_with(f"{CACHE_KEY_PREFIX}:{str(user_uuid)}")
