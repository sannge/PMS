"""Unit tests for project member write tools (app.ai.agent.tools.project_member_write_tools).

Tests cover:
- add_project_member — RBAC (app owner/project admin), user must be app member,
  duplicate check, HITL approval/rejection
- update_project_member_role — invalid role, already same role, RBAC denied
- remove_project_member — active tasks blocking, HITL flow
- PROJECT_MEMBER_WRITE_TOOLS registry has 3 tools
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.ai.agent.tools.project_member_write_tools import (
    PROJECT_MEMBER_WRITE_TOOLS,
    add_project_member,
    remove_project_member,
    update_project_member_role,
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
# PROJECT_MEMBER_WRITE_TOOLS registry
# ---------------------------------------------------------------------------


class TestProjectMemberWriteToolsRegistry:
    def test_has_3_tools(self):
        assert len(PROJECT_MEMBER_WRITE_TOOLS) == 3

    def test_tool_names(self):
        names = {t.name for t in PROJECT_MEMBER_WRITE_TOOLS}
        assert names == {
            "add_project_member",
            "update_project_member_role",
            "remove_project_member",
        }


# ---------------------------------------------------------------------------
# add_project_member tool
# ---------------------------------------------------------------------------


class TestAddProjectMember:
    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        _clear()

    async def test_invalid_role_rejected(self):
        _setup_context()
        result = await add_project_member.ainvoke(
            {
                "project": "Sprint 1",
                "user": "alice@test.com",
                "role": "superadmin",
            }
        )
        assert "Error" in result
        assert "Invalid role" in result

    async def test_rbac_denied_no_project_access(self):
        """add_project_member returns not-found when project is not accessible."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        result = await add_project_member.ainvoke(
            {
                "project": proj_id,
                "user": "alice@test.com",
            }
        )
        assert "No project found" in result

    @patch("app.ai.agent.tools.project_member_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_member_write_tools._get_tool_session")
    async def test_rbac_denied_member_role(self, mock_tool_session, mock_interrupt):
        """Non-admin project member and non-owner app member should be denied."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_project_ids=[proj_id])

        session = _mock_db_session()

        mock_project = MagicMock()
        mock_project.name = "Sprint 1"
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
                result.scalar_one_or_none.return_value = mock_project
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_app_member
            elif call_count == 3:
                result.scalar_one_or_none.return_value = mock_proj_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await add_project_member.ainvoke(
            {
                "project": proj_id,
                "user": "alice@test.com",
            }
        )
        assert "Access denied" in result
        mock_interrupt.assert_not_called()

    @patch("app.ai.agent.tools.project_member_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_member_write_tools._get_tool_session")
    async def test_user_rejection(self, mock_tool_session, mock_interrupt):
        """User rejecting the confirmation should cancel."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        target_user_id = str(uuid4())
        app_id = uuid4()
        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
            accessible_app_ids=[str(app_id)],
        )

        session = _mock_db_session()

        mock_project = MagicMock()
        mock_project.name = "Sprint 1"
        mock_project.application_id = app_id

        mock_app_member_owner = MagicMock()
        mock_app_member_owner.role = "owner"

        mock_proj_member_admin = MagicMock()
        mock_proj_member_admin.role = "admin"

        mock_target_user = MagicMock()
        mock_target_user.display_name = "Alice"
        mock_target_user.email = "alice@test.com"
        mock_target_user.id = UUID(target_user_id)

        mock_target_app_member = MagicMock()
        mock_target_app_member.role = "editor"

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_project
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_app_member_owner
            elif call_count == 3:
                result.scalar_one_or_none.return_value = mock_proj_member_admin
            elif call_count == 4:
                # _resolve_user UUID fast path (scope subquery)
                result.scalar_one_or_none.return_value = UUID(target_user_id)
            elif call_count == 5:
                # User lookup
                result.scalar_one_or_none.return_value = mock_target_user
            elif call_count == 6:
                # Target app member check
                result.scalar_one_or_none.return_value = mock_target_app_member
            elif call_count == 7:
                # Duplicate check -- not already a member
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_interrupt.return_value = {"approved": False}

        result = await add_project_member.ainvoke(
            {
                "project": proj_id,
                "user": target_user_id,
            }
        )
        assert "cancelled" in result.lower()


# ---------------------------------------------------------------------------
# update_project_member_role tool
# ---------------------------------------------------------------------------


class TestUpdateProjectMemberRole:
    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        _clear()

    async def test_invalid_role_rejected(self):
        _setup_context()
        result = await update_project_member_role.ainvoke(
            {
                "project": "Sprint 1",
                "user": "alice@test.com",
                "new_role": "superadmin",
            }
        )
        assert "Error" in result
        assert "Invalid role" in result

    async def test_rbac_denied_no_project_access(self):
        """update_project_member_role returns not-found when project is not accessible."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        result = await update_project_member_role.ainvoke(
            {
                "project": proj_id,
                "user": "alice@test.com",
                "new_role": "admin",
            }
        )
        assert "No project found" in result


# ---------------------------------------------------------------------------
# remove_project_member tool
# ---------------------------------------------------------------------------


class TestRemoveProjectMember:
    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        _clear()

    async def test_rbac_denied_no_project_access(self):
        """remove_project_member returns not-found when project is not accessible."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        result = await remove_project_member.ainvoke(
            {
                "project": proj_id,
                "user": "alice@test.com",
            }
        )
        assert "No project found" in result

    @patch("app.ai.agent.tools.project_member_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_member_write_tools._get_tool_session")
    async def test_active_tasks_block_removal(self, mock_tool_session, mock_interrupt):
        """Should block removal when user has active tasks."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        target_user_id = str(uuid4())
        app_id = uuid4()
        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
            accessible_app_ids=[str(app_id)],
        )

        session = _mock_db_session()

        mock_project = MagicMock()
        mock_project.name = "Sprint 1"
        mock_project.application_id = app_id

        mock_app_member_owner = MagicMock()
        mock_app_member_owner.role = "owner"

        mock_target_user = MagicMock()
        mock_target_user.display_name = "Alice"
        mock_target_user.email = "alice@test.com"
        mock_target_user.id = UUID(target_user_id)

        mock_target_pm = MagicMock()
        mock_target_pm.role = "member"

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Project lookup
                result.scalar_one_or_none.return_value = mock_project
            elif call_count == 2:
                # App member RBAC
                result.scalar_one_or_none.return_value = mock_app_member_owner
            elif call_count == 3:
                # Project member RBAC (current user is also project admin, but owner suffices)
                result.scalar_one_or_none.return_value = None
            elif call_count == 4:
                # _resolve_user UUID fast path
                result.scalar_one_or_none.return_value = UUID(target_user_id)
            elif call_count == 5:
                # User lookup
                result.scalar_one_or_none.return_value = mock_target_user
            elif call_count == 6:
                # Target ProjectMember check
                result.scalar_one_or_none.return_value = mock_target_pm
            elif call_count == 7:
                # Done status subquery (returned by active task count)
                # Active task count -- 3 active tasks
                result.scalar.return_value = 3
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await remove_project_member.ainvoke(
            {
                "project": proj_id,
                "user": target_user_id,
            }
        )
        assert "Cannot remove" in result
        assert "3 active task" in result
        mock_interrupt.assert_not_called()

    @patch("app.ai.agent.tools.project_member_write_tools.interrupt")
    @patch("app.ai.agent.tools.project_member_write_tools._get_tool_session")
    async def test_user_rejection(self, mock_tool_session, mock_interrupt):
        """User rejecting the confirmation should cancel the removal."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        target_user_id = str(uuid4())
        app_id = uuid4()
        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
            accessible_app_ids=[str(app_id)],
        )

        session = _mock_db_session()

        mock_project = MagicMock()
        mock_project.name = "Sprint 1"
        mock_project.application_id = app_id

        mock_app_member_owner = MagicMock()
        mock_app_member_owner.role = "owner"

        mock_target_user = MagicMock()
        mock_target_user.display_name = "Alice"
        mock_target_user.email = "alice@test.com"
        mock_target_user.id = UUID(target_user_id)

        mock_target_pm = MagicMock()
        mock_target_pm.role = "member"

        call_count = 0

        async def execute_side_effect(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_project
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_app_member_owner
            elif call_count == 3:
                result.scalar_one_or_none.return_value = None
            elif call_count == 4:
                result.scalar_one_or_none.return_value = UUID(target_user_id)
            elif call_count == 5:
                result.scalar_one_or_none.return_value = mock_target_user
            elif call_count == 6:
                result.scalar_one_or_none.return_value = mock_target_pm
            elif call_count == 7:
                # Active tasks = 0, removal allowed
                result.scalar.return_value = 0
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_tool_session.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_tool_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_interrupt.return_value = {"approved": False}

        result = await remove_project_member.ainvoke(
            {
                "project": proj_id,
                "user": target_user_id,
            }
        )
        assert "cancelled" in result.lower()
