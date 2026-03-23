"""Unit tests for member write tools (app.ai.agent.tools.member_write_tools).

Tests cover:
- add_application_member: RBAC hierarchy, user lookup, already-a-member, approval/rejection
- update_application_member_role: RBAC, last-owner protection, editor restrictions
- remove_application_member: RBAC (owner only + self-removal), last-owner, active tasks blocking
- MEMBER_WRITE_TOOLS registry
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.ai.agent.tools.member_write_tools import (
    MEMBER_WRITE_TOOLS,
    add_application_member,
    remove_application_member,
    update_application_member_role,
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
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


def _make_ctx(session):
    """Wrap a mock session as an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestMemberWriteToolsRegistry:
    def test_has_3_tools(self):
        assert len(MEMBER_WRITE_TOOLS) == 3

    def test_tool_names(self):
        names = {t.name for t in MEMBER_WRITE_TOOLS}
        assert names == {
            "add_application_member",
            "update_application_member_role",
            "remove_application_member",
        }


# ---------------------------------------------------------------------------
# add_application_member
# ---------------------------------------------------------------------------


class TestAddApplicationMember:
    async def test_invalid_role(self):
        _setup_context()
        result = await add_application_member.ainvoke(
            {
                "app": str(uuid4()),
                "email": "test@example.com",
                "role": "admin",
            }
        )
        assert "Invalid role" in result
        _clear()

    async def test_viewer_denied(self):
        """Viewers cannot add members."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            # App lookup
            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            # Actor membership (viewer)
            mock_member = MagicMock()
            mock_member.role = "viewer"
            member_result = MagicMock()
            member_result.scalar_one_or_none.return_value = mock_member

            session.execute = AsyncMock(side_effect=[app_result, member_result])
            mock_ts.return_value = _make_ctx(session)

            result = await add_application_member.ainvoke(
                {
                    "app": app_id,
                    "email": "new@example.com",
                    "role": "viewer",
                }
            )
            assert "don't have permission" in result.lower()
        _clear()

    async def test_user_not_found(self):
        """Email not found returns invitation guidance."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_member = MagicMock()
            mock_member.role = "owner"
            member_result = MagicMock()
            member_result.scalar_one_or_none.return_value = mock_member

            # User lookup: not found
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = None

            session.execute = AsyncMock(side_effect=[app_result, member_result, user_result])
            mock_ts.return_value = _make_ctx(session)

            result = await add_application_member.ainvoke(
                {
                    "app": app_id,
                    "email": "noone@example.com",
                    "role": "viewer",
                }
            )
            assert "No user found" in result
            assert "invitation system" in result
        _clear()

    async def test_already_a_member(self):
        """User already a member returns guidance to use role update."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_actor = MagicMock()
            mock_actor.role = "owner"
            actor_result = MagicMock()
            actor_result.scalar_one_or_none.return_value = mock_actor

            mock_user = MagicMock()
            mock_user.id = uuid4()
            mock_user.display_name = "Alice"
            mock_user.email = "alice@example.com"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = mock_user

            # Already a member
            existing_result = MagicMock()
            existing_result.scalar_one_or_none.return_value = MagicMock()

            session.execute = AsyncMock(
                side_effect=[
                    app_result,
                    actor_result,
                    user_result,
                    existing_result,
                ]
            )
            mock_ts.return_value = _make_ctx(session)

            result = await add_application_member.ainvoke(
                {
                    "app": app_id,
                    "email": "alice@example.com",
                    "role": "editor",
                }
            )
            assert "already a member" in result.lower()
            assert "update_application_member_role" in result
        _clear()

    @patch("app.ai.agent.tools.member_write_tools.interrupt")
    @patch("app.ai.agent.tools.member_write_tools._get_tool_session")
    async def test_approval_flow(self, mock_tool_session, mock_interrupt):
        """Successful add member flow with approval."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_user_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        # Pre-interrupt session
        pre_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_actor = MagicMock()
        mock_actor.role = "owner"
        actor_result = MagicMock()
        actor_result.scalar_one_or_none.return_value = mock_actor
        mock_user = MagicMock()
        mock_user.id = target_user_id
        mock_user.display_name = "Bob"
        mock_user.email = "bob@example.com"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_user
        # Not already a member
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        pre_session.execute = AsyncMock(
            side_effect=[
                app_result,
                actor_result,
                user_result,
                existing_result,
            ]
        )

        # TOCTOU + write combined session
        toctou_write_session = _mock_db_session()
        toctou_member = MagicMock()
        toctou_member.role = "owner"
        toctou_result = MagicMock()
        toctou_result.scalar_one_or_none.return_value = toctou_member
        # Not already a member check
        existing_check = MagicMock()
        existing_check.scalar_one_or_none.return_value = None
        toctou_write_session.execute = AsyncMock(side_effect=[toctou_result, existing_check])

        mock_tool_session.side_effect = [
            _make_ctx(pre_session),
            _make_ctx(toctou_write_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await add_application_member.ainvoke(
            {
                "app": app_id,
                "email": "bob@example.com",
                "role": "editor",
            }
        )
        assert "Added Bob as Editor" in result
        toctou_write_session.add.assert_called_once()
        _clear()


# ---------------------------------------------------------------------------
# update_application_member_role
# ---------------------------------------------------------------------------


class TestUpdateApplicationMemberRole:
    async def test_invalid_role(self):
        _setup_context()
        result = await update_application_member_role.ainvoke(
            {
                "app": str(uuid4()),
                "user": "alice@example.com",
                "new_role": "superadmin",
            }
        )
        assert "Invalid role" in result
        _clear()

    async def test_viewer_denied(self):
        """Viewers cannot change roles."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_member = MagicMock()
            mock_member.role = "viewer"
            member_result = MagicMock()
            member_result.scalar_one_or_none.return_value = mock_member

            session.execute = AsyncMock(side_effect=[app_result, member_result])
            mock_ts.return_value = _make_ctx(session)

            result = await update_application_member_role.ainvoke(
                {
                    "app": app_id,
                    "user": "alice@example.com",
                    "new_role": "editor",
                }
            )
            assert "viewers cannot" in result.lower()
        _clear()

    async def test_last_owner_protection(self):
        """Cannot downgrade the last owner."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_actor = MagicMock()
            mock_actor.role = "owner"
            actor_result = MagicMock()
            actor_result.scalar_one_or_none.return_value = mock_actor

            # Target user found by UUID
            mock_user = MagicMock()
            mock_user.id = target_id
            mock_user.display_name = "Alice"
            mock_user.email = "alice@example.com"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = mock_user

            # Target membership (owner)
            mock_target_member = MagicMock()
            mock_target_member.role = "owner"
            target_member_result = MagicMock()
            target_member_result.scalar_one_or_none.return_value = mock_target_member

            # Owner count = 1
            count_result = MagicMock()
            count_result.scalar.return_value = 1

            session.execute = AsyncMock(
                side_effect=[
                    app_result,
                    actor_result,
                    user_result,
                    target_member_result,
                    count_result,
                ]
            )
            mock_ts.return_value = _make_ctx(session)

            result = await update_application_member_role.ainvoke(
                {
                    "app": app_id,
                    "user": str(target_id),
                    "new_role": "editor",
                }
            )
            assert "last owner" in result.lower()
        _clear()

    async def test_editor_restriction(self):
        """Editors can only promote viewer -> editor, nothing else."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_actor = MagicMock()
            mock_actor.role = "editor"
            actor_result = MagicMock()
            actor_result.scalar_one_or_none.return_value = mock_actor

            mock_user = MagicMock()
            mock_user.id = target_id
            mock_user.display_name = "Bob"
            mock_user.email = "bob@example.com"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = mock_user

            # Target is an editor, trying to make owner
            mock_target_member = MagicMock()
            mock_target_member.role = "editor"
            target_member_result = MagicMock()
            target_member_result.scalar_one_or_none.return_value = mock_target_member

            session.execute = AsyncMock(
                side_effect=[
                    app_result,
                    actor_result,
                    user_result,
                    target_member_result,
                ]
            )
            mock_ts.return_value = _make_ctx(session)

            result = await update_application_member_role.ainvoke(
                {
                    "app": app_id,
                    "user": str(target_id),
                    "new_role": "owner",
                }
            )
            assert "only promote viewers to editors" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# remove_application_member
# ---------------------------------------------------------------------------


class TestRemoveApplicationMember:
    async def test_non_owner_denied(self):
        """Editor cannot remove others (only owners can)."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_actor = MagicMock()
            mock_actor.role = "editor"
            actor_result = MagicMock()
            actor_result.scalar_one_or_none.return_value = mock_actor

            # Target user found
            mock_user = MagicMock()
            mock_user.id = target_id
            mock_user.display_name = "Bob"
            mock_user.email = "bob@example.com"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = mock_user

            session.execute = AsyncMock(side_effect=[app_result, actor_result, user_result])
            mock_ts.return_value = _make_ctx(session)

            result = await remove_application_member.ainvoke(
                {
                    "app": app_id,
                    "user": str(target_id),
                }
            )
            assert "only owners" in result.lower()
        _clear()

    async def test_last_owner_cannot_be_removed(self):
        """Cannot remove the last owner."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_actor = MagicMock()
            mock_actor.role = "owner"
            actor_result = MagicMock()
            actor_result.scalar_one_or_none.return_value = mock_actor

            mock_user = MagicMock()
            mock_user.id = target_id
            mock_user.display_name = "Alice"
            mock_user.email = "alice@example.com"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = mock_user

            # Target membership (owner)
            mock_target_member = MagicMock()
            mock_target_member.role = "owner"
            target_member_result = MagicMock()
            target_member_result.scalar_one_or_none.return_value = mock_target_member

            # Owner count = 1
            count_result = MagicMock()
            count_result.scalar.return_value = 1

            session.execute = AsyncMock(
                side_effect=[
                    app_result,
                    actor_result,
                    user_result,
                    target_member_result,
                    count_result,
                ]
            )
            mock_ts.return_value = _make_ctx(session)

            result = await remove_application_member.ainvoke(
                {
                    "app": app_id,
                    "user": str(target_id),
                }
            )
            assert "last owner" in result.lower()
        _clear()

    async def test_active_tasks_blocking(self):
        """Cannot remove member with active tasks."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.member_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_actor = MagicMock()
            mock_actor.role = "owner"
            actor_result = MagicMock()
            actor_result.scalar_one_or_none.return_value = mock_actor

            mock_user = MagicMock()
            mock_user.id = target_id
            mock_user.display_name = "Bob"
            mock_user.email = "bob@example.com"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = mock_user

            # Target membership (editor, not owner)
            mock_target_member = MagicMock()
            mock_target_member.role = "editor"
            target_member_result = MagicMock()
            target_member_result.scalar_one_or_none.return_value = mock_target_member

            # Project IDs in the app
            proj_id = uuid4()
            project_ids_result = MagicMock()
            project_ids_result.all.return_value = [(proj_id,)]

            # Done status IDs
            done_status_id = uuid4()
            done_result = MagicMock()
            done_result.all.return_value = [(done_status_id,)]

            # Active task count = 3
            active_count_result = MagicMock()
            active_count_result.scalar.return_value = 3

            session.execute = AsyncMock(
                side_effect=[
                    app_result,
                    actor_result,
                    user_result,
                    target_member_result,
                    project_ids_result,
                    done_result,
                    active_count_result,
                ]
            )
            mock_ts.return_value = _make_ctx(session)

            result = await remove_application_member.ainvoke(
                {
                    "app": app_id,
                    "user": str(target_id),
                }
            )
            assert "3 active tasks" in result
            assert "Reassign" in result
        _clear()

    @patch("app.ai.agent.tools.member_write_tools.interrupt")
    @patch("app.ai.agent.tools.member_write_tools._get_tool_session")
    async def test_rejection_flow(self, mock_tool_session, mock_interrupt):
        """User rejects member removal."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        target_id = uuid4()
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_actor = MagicMock()
        mock_actor.role = "owner"
        actor_result = MagicMock()
        actor_result.scalar_one_or_none.return_value = mock_actor
        mock_user = MagicMock()
        mock_user.id = target_id
        mock_user.display_name = "Alice"
        mock_user.email = "alice@example.com"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_user
        mock_target_member = MagicMock()
        mock_target_member.role = "editor"
        target_member_result = MagicMock()
        target_member_result.scalar_one_or_none.return_value = mock_target_member
        # No projects in app
        project_ids_result = MagicMock()
        project_ids_result.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[
                app_result,
                actor_result,
                user_result,
                target_member_result,
                project_ids_result,
            ]
        )
        mock_tool_session.return_value = _make_ctx(session)
        mock_interrupt.return_value = {"approved": False}

        result = await remove_application_member.ainvoke(
            {
                "app": app_id,
                "user": str(target_id),
            }
        )
        assert "cancelled" in result.lower()
        _clear()
