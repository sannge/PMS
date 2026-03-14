"""Unit tests for application write tools (app.ai.agent.tools.application_write_tools).

Tests cover:
- create_application: validation, approval/rejection flows
- update_application: RBAC (owner/editor/viewer), at-least-one-field, TOCTOU
- delete_application: RBAC (owner only), approval/rejection, TOCTOU
- APPLICATION_WRITE_TOOLS registry
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.ai.agent.tools.application_write_tools import (
    APPLICATION_WRITE_TOOLS,
    create_application,
    delete_application,
    update_application,
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
    set_tool_context(**{k: ctx[k] for k in (
        "user_id", "accessible_app_ids", "accessible_project_ids",
        "db_session_factory", "provider_registry",
    )})
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


def _make_ctx(session):
    """Wrap a mock session as an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestApplicationWriteToolsRegistry:

    def test_has_3_tools(self):
        assert len(APPLICATION_WRITE_TOOLS) == 3

    def test_tool_names(self):
        names = {t.name for t in APPLICATION_WRITE_TOOLS}
        assert names == {
            "create_application",
            "update_application",
            "delete_application",
        }


# ---------------------------------------------------------------------------
# create_application
# ---------------------------------------------------------------------------

class TestCreateApplication:

    async def test_empty_name(self):
        _setup_context()
        result = await create_application.ainvoke({"name": ""})
        assert "required" in result.lower()
        _clear()

    async def test_name_too_long(self):
        _setup_context()
        result = await create_application.ainvoke({"name": "x" * 101})
        assert "100 characters" in result
        _clear()

    async def test_description_too_long(self):
        _setup_context()
        result = await create_application.ainvoke({
            "name": "Valid",
            "description": "x" * 501,
        })
        assert "500 characters" in result
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    async def test_user_rejection(self, mock_interrupt):
        user_id = str(uuid4())
        _setup_context(user_id=user_id)
        mock_interrupt.return_value = {"approved": False}

        result = await create_application.ainvoke({"name": "My App"})
        assert "cancelled" in result.lower()
        mock_interrupt.assert_called_once()
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    @patch("app.ai.agent.tools.application_write_tools._get_tool_session")
    async def test_user_approval(self, mock_tool_session, mock_interrupt):
        user_id = str(uuid4())
        _setup_context(user_id=user_id)

        session = _mock_db_session()
        mock_tool_session.return_value = _make_ctx(session)
        mock_interrupt.return_value = {"approved": True}

        # Mock app.id after flush
        def capture_add(obj):
            obj.id = uuid4()
        session.add.side_effect = capture_add

        result = await create_application.ainvoke({"name": "My App"})
        assert "Created application 'My App'" in result
        assert session.add.call_count == 2  # Application + ApplicationMember
        _clear()


# ---------------------------------------------------------------------------
# update_application
# ---------------------------------------------------------------------------

class TestUpdateApplication:

    async def test_no_fields_provided(self):
        _setup_context()
        result = await update_application.ainvoke({"app": "test"})
        assert "at least one" in result.lower()
        _clear()

    async def test_rbac_viewer_denied(self):
        """Viewer cannot update application."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.application_write_tools._get_tool_session") as mock_ts:
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

            result = await update_application.ainvoke({"app": app_id, "name": "New Name"})
            assert "owner or editor" in result.lower()
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    @patch("app.ai.agent.tools.application_write_tools._get_tool_session")
    async def test_toctou_recheck(self, mock_tool_session, mock_interrupt):
        """After interrupt, RBAC is re-checked (TOCTOU)."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        # Pre-interrupt session: app + member (owner)
        pre_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_member = MagicMock()
        mock_member.role = "owner"
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member
        pre_session.execute = AsyncMock(side_effect=[app_result, member_result])

        # TOCTOU session: role downgraded to viewer
        toctou_session = _mock_db_session()
        toctou_member = MagicMock()
        toctou_member.role = "viewer"
        toctou_result = MagicMock()
        toctou_result.scalar_one_or_none.return_value = toctou_member
        toctou_session.execute = AsyncMock(return_value=toctou_result)

        mock_tool_session.side_effect = [
            _make_ctx(pre_session),
            _make_ctx(toctou_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await update_application.ainvoke({"app": app_id, "name": "New Name"})
        assert "no longer have permission" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# delete_application
# ---------------------------------------------------------------------------

class TestDeleteApplication:

    async def test_rbac_editor_denied(self):
        """Editor cannot delete application (owner only)."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        with patch("app.ai.agent.tools.application_write_tools._get_tool_session") as mock_ts:
            session = _mock_db_session()

            mock_app = MagicMock()
            mock_app.name = "Test App"
            app_result = MagicMock()
            app_result.scalar_one_or_none.return_value = mock_app

            mock_member = MagicMock()
            mock_member.role = "editor"
            member_result = MagicMock()
            member_result.scalar_one_or_none.return_value = mock_member

            session.execute = AsyncMock(side_effect=[app_result, member_result])
            mock_ts.return_value = _make_ctx(session)

            result = await delete_application.ainvoke({"app": app_id})
            assert "only the application owner" in result.lower()
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    @patch("app.ai.agent.tools.application_write_tools._get_tool_session")
    async def test_user_rejection(self, mock_tool_session, mock_interrupt):
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_member = MagicMock()
        mock_member.role = "owner"
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member
        session.execute = AsyncMock(side_effect=[app_result, member_result])
        mock_tool_session.return_value = _make_ctx(session)
        mock_interrupt.return_value = {"approved": False}

        result = await delete_application.ainvoke({"app": app_id})
        assert "cancelled" in result.lower()
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    @patch("app.ai.agent.tools.application_write_tools._get_tool_session")
    async def test_user_approval(self, mock_tool_session, mock_interrupt):
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        # Pre-interrupt session
        pre_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_member = MagicMock()
        mock_member.role = "owner"
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member
        pre_session.execute = AsyncMock(side_effect=[app_result, member_result])

        # TOCTOU + delete combined session
        toctou_delete_session = _mock_db_session()
        toctou_member = MagicMock()
        toctou_member.role = "owner"
        toctou_result = MagicMock()
        toctou_result.scalar_one_or_none.return_value = toctou_member
        delete_app = MagicMock()
        delete_app.name = "Test App"
        delete_result = MagicMock()
        delete_result.scalar_one_or_none.return_value = delete_app
        toctou_delete_session.execute = AsyncMock(
            side_effect=[toctou_result, delete_result]
        )

        mock_tool_session.side_effect = [
            _make_ctx(pre_session),
            _make_ctx(toctou_delete_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await delete_application.ainvoke({"app": app_id})
        assert "Deleted application" in result
        assert "all its contents" in result
        toctou_delete_session.delete.assert_called_once()
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    @patch("app.ai.agent.tools.application_write_tools._get_tool_session")
    async def test_toctou_owner_revoked(self, mock_tool_session, mock_interrupt):
        """After interrupt, ownership revoked -> denied."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        # Pre-interrupt: owner
        pre_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_member = MagicMock()
        mock_member.role = "owner"
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member
        pre_session.execute = AsyncMock(side_effect=[app_result, member_result])

        # TOCTOU: no longer owner
        toctou_session = _mock_db_session()
        toctou_member = MagicMock()
        toctou_member.role = "editor"
        toctou_result = MagicMock()
        toctou_result.scalar_one_or_none.return_value = toctou_member
        toctou_session.execute = AsyncMock(return_value=toctou_result)

        mock_tool_session.side_effect = [
            _make_ctx(pre_session),
            _make_ctx(toctou_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await delete_application.ainvoke({"app": app_id})
        assert "no longer the owner" in result.lower()
        _clear()

    @patch("app.ai.agent.tools.application_write_tools.interrupt")
    @patch("app.ai.agent.tools.application_write_tools._get_tool_session")
    async def test_update_application_rbac_denied_post_interrupt(
        self, mock_tool_session, mock_interrupt
    ):
        """If user loses access between approval and execution, deny."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        # Pre-interrupt session: app found + user is owner
        pre_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "Test App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        mock_member = MagicMock()
        mock_member.role = "owner"
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member
        pre_session.execute = AsyncMock(side_effect=[app_result, member_result])

        # Post-interrupt session: membership is None (user lost access entirely)
        toctou_session = _mock_db_session()
        toctou_result = MagicMock()
        toctou_result.scalar_one_or_none.return_value = None  # no membership
        toctou_session.execute = AsyncMock(return_value=toctou_result)

        mock_tool_session.side_effect = [
            _make_ctx(pre_session),
            _make_ctx(toctou_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await update_application.ainvoke({"app": app_id, "name": "New Name"})
        assert "no longer have permission" in result.lower()
        _clear()
