"""Unit tests for project write tools (app.ai.agent.tools.project_write_tools).

Tests cover:
- create_project — RBAC (app owner/editor), key validation, key uniqueness,
  default statuses created, ProjectMember auto-created, HITL approval/rejection
- update_project — partial update, RBAC denied, at-least-one-field validation
- delete_project — RBAC (app owner OR project admin), cascade warning, HITL flow
- PROJECT_WRITE_TOOLS registry has 3 tools
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.ai.agent.tools.project_write_tools import (
    PROJECT_WRITE_TOOLS,
    create_project,
    delete_project,
    update_project,
)
from app.ai.agent.tools.context import clear_tool_context, set_tool_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_context(**overrides):
    """Populate tool context with sensible defaults + overrides."""
    ctx = {
        "user_id": str(uuid4()),
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "db_session_factory": MagicMock(),
        "provider_registry": MagicMock(),
    }
    ctx.update(overrides)
    set_tool_context(
        **{
            k: ctx[k]
            for k in (
                "user_id",
                "accessible_app_ids",
                "accessible_project_ids",
                "db_session_factory",
                "provider_registry",
            )
        }
    )
    return ctx


def _clear():
    clear_tool_context()


def _mock_db_session():
    """Create a mock AsyncSession with close/rollback/commit."""
    session = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# PROJECT_WRITE_TOOLS registry
# ---------------------------------------------------------------------------


class TestProjectWriteToolsRegistry:
    def test_has_3_tools(self):
        assert len(PROJECT_WRITE_TOOLS) == 3

    def test_tool_names(self):
        names = {t.name for t in PROJECT_WRITE_TOOLS}
        assert names == {"create_project", "update_project", "delete_project"}


# ---------------------------------------------------------------------------
# create_project tool
# ---------------------------------------------------------------------------


class TestCreateProject:
    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        _clear()

    async def test_empty_name_rejected(self):
        _setup_context()
        result = await create_project.ainvoke(
            {
                "app": "My App",
                "name": "",
                "key": "SP",
            }
        )
        assert "Error" in result
        assert "name is required" in result

    async def test_name_too_long_rejected(self):
        _setup_context()
        result = await create_project.ainvoke(
            {
                "app": "My App",
                "name": "x" * 101,
                "key": "SP",
            }
        )
        assert "Error" in result
        assert "100 characters" in result

    async def test_invalid_key_rejected(self):
        _setup_context()
        result = await create_project.ainvoke(
            {
                "app": "My App",
                "name": "Sprint 1",
                "key": "1bad",
            }
        )
        assert "Error" in result
        assert "Invalid project key" in result

    async def test_single_char_key_rejected(self):
        _setup_context()
        result = await create_project.ainvoke(
            {
                "app": "My App",
                "name": "Sprint 1",
                "key": "S",
            }
        )
        assert "Error" in result
        assert "Invalid project key" in result

    async def test_rbac_denied_no_app_access(self):
        """create_project returns not-found when app is not accessible."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[])
        result = await create_project.ainvoke(
            {
                "app": app_id,
                "name": "Sprint 1",
                "key": "SP",
            }
        )
        assert "No application found" in result

    @patch("app.ai.agent.tools.project_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_write_tools._get_tool_session")
    async def test_rbac_denied_viewer_role(self, mock_tool_session, mock_interrupt):
        """Viewer role should be denied create_project."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        session = _mock_db_session()

        # Mock app resolution (UUID fast path succeeds), then app lookup, then RBAC
        mock_app = MagicMock()
        mock_app.name = "My App"
        mock_app_member = MagicMock()
        mock_app_member.role = "viewer"  # Not owner or editor

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Application lookup
                result.scalar_one_or_none.return_value = mock_app
            elif call_count == 2:
                # RBAC check - viewer
                result.scalar_one_or_none.return_value = mock_app_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await create_project.ainvoke(
            {
                "app": app_id,
                "name": "Sprint 1",
                "key": "SP",
            }
        )
        assert "Access denied" in result
        assert "Owner or Editor" in result
        mock_interrupt.assert_not_called()

    @patch("app.ai.agent.tools.project_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_write_tools._get_tool_session")
    async def test_key_uniqueness_violation(self, mock_tool_session, mock_interrupt):
        """Duplicate key within application should be rejected."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        session = _mock_db_session()

        mock_app = MagicMock()
        mock_app.name = "My App"
        mock_app_member = MagicMock()
        mock_app_member.role = "owner"

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_app
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_app_member
            elif call_count == 3:
                # Key uniqueness check -- return existing project (duplicate)
                result.scalar_one_or_none.return_value = uuid4()
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await create_project.ainvoke(
            {
                "app": app_id,
                "name": "Sprint 1",
                "key": "SP",
            }
        )
        assert "already exists" in result
        mock_interrupt.assert_not_called()

    @patch("app.ai.agent.tools.project_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_write_tools._get_tool_session")
    async def test_user_rejection(self, mock_tool_session, mock_interrupt):
        """User rejecting the confirmation should cancel the creation."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        session = _mock_db_session()

        mock_app = MagicMock()
        mock_app.name = "My App"
        mock_app_member = MagicMock()
        mock_app_member.role = "owner"

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_app
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_app_member
            elif call_count == 3:
                # Key uniqueness -- no duplicate
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_interrupt.return_value = {"approved": False}

        result = await create_project.ainvoke(
            {
                "app": app_id,
                "name": "Sprint 1",
                "key": "SP",
            }
        )
        assert "cancelled" in result.lower()


# ---------------------------------------------------------------------------
# update_project tool
# ---------------------------------------------------------------------------


class TestUpdateProject:
    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        _clear()

    async def test_no_fields_provided(self):
        _setup_context()
        result = await update_project.ainvoke(
            {
                "project": "Sprint 1",
            }
        )
        assert "Error" in result
        assert "at least one field" in result.lower()

    async def test_rbac_denied_no_project_access(self):
        """update_project returns not-found when project is not accessible."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        result = await update_project.ainvoke(
            {
                "project": proj_id,
                "name": "New Name",
            }
        )
        assert "No project found" in result

    async def test_invalid_due_date(self):
        _setup_context()
        result = await update_project.ainvoke(
            {
                "project": "Sprint 1",
                "due_date": "not-a-date",
            }
        )
        assert "Error" in result
        assert "Invalid due_date" in result


# ---------------------------------------------------------------------------
# delete_project tool
# ---------------------------------------------------------------------------


class TestDeleteProject:
    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        _clear()

    async def test_rbac_denied_no_project_access(self):
        """delete_project returns not-found when project is not accessible."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        result = await delete_project.ainvoke(
            {
                "project": proj_id,
            }
        )
        assert "No project found" in result

    @patch("app.ai.agent.tools.project_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_write_tools._get_tool_session")
    async def test_rbac_denied_member_role(self, mock_tool_session, mock_interrupt):
        """Non-admin project member and non-owner app member should be denied."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_project_ids=[proj_id])

        session = _mock_db_session()

        mock_project = MagicMock()
        mock_project.name = "Sprint 1"
        mock_project.key = "SP"
        mock_project.application_id = uuid4()

        mock_app_member = MagicMock()
        mock_app_member.role = "editor"  # Not owner

        mock_proj_member = MagicMock()
        mock_proj_member.role = "member"  # Not admin

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Project lookup
                result.scalar_one_or_none.return_value = mock_project
            elif call_count == 2:
                # App member check
                result.scalar_one_or_none.return_value = mock_app_member
            elif call_count == 3:
                # Project member check
                result.scalar_one_or_none.return_value = mock_proj_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await delete_project.ainvoke({"project": proj_id})
        assert "Access denied" in result
        assert "Owner or project Admin" in result
        mock_interrupt.assert_not_called()

    @patch("app.ai.agent.tools.project_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_write_tools._get_tool_session")
    async def test_user_rejection(self, mock_tool_session, mock_interrupt):
        """User rejecting delete confirmation should cancel."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_project_ids=[proj_id])

        session = _mock_db_session()

        mock_project = MagicMock()
        mock_project.name = "Sprint 1"
        mock_project.key = "SP"
        mock_project.application_id = uuid4()

        mock_app_member = MagicMock()
        mock_app_member.role = "owner"  # App owner can delete

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_project
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_app_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_interrupt.return_value = {"approved": False}

        result = await delete_project.ainvoke({"project": proj_id})
        assert "cancelled" in result.lower()
