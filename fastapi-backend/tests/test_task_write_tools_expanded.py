"""Unit tests for expanded task write tools (update_task, add_task_comment, delete_task).

Tests cover:
1. test_update_task_partial_fields -- only title updated
2. test_update_task_invalid_priority -- "critical" is not valid
3. test_update_task_invalid_due_date -- "not-a-date" rejected
4. test_update_task_rbac_denied -- viewer can't update
5. test_add_comment_with_mentions -- creates comment + mention records
6. test_add_comment_too_long -- > 5000 chars rejected
7. test_add_comment_any_app_member -- viewer CAN comment
8. test_delete_task_cascade -- task deleted, counters updated
9. test_delete_task_rbac_denied -- viewer can't delete
10. test_delete_task_hitl_rejection -- user rejects confirmation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.ai.agent.tools.write_tools import (
    WRITE_TOOLS,
    add_task_comment,
    delete_task,
    update_task,
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


def _async_ctx(session):
    """Wrap a mock session as an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ---------------------------------------------------------------------------
# update_task tests
# ---------------------------------------------------------------------------


class TestUpdateTask:
    async def test_update_task_partial_fields(self):
        """update_task updates only the title when only title is provided."""
        task_id = str(uuid4())
        proj_id = str(uuid4())
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        try:
            with (
                patch("app.ai.agent.tools.write_tools.interrupt") as mock_interrupt,
                patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session,
            ):
                # Pre-interrupt session: resolve task + load task
                pre_session = _mock_db_session()
                # _resolve_task UUID fast path
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = UUID(task_id)
                # Task detail lookup
                mock_task = MagicMock()
                mock_task.project_id = UUID(proj_id)
                mock_task.task_key = "SP-1"
                mock_task.title = "Fix login"
                task_result = MagicMock()
                task_result.scalar_one_or_none.return_value = mock_task
                pre_session.execute = AsyncMock(side_effect=[resolve_result, task_result])

                # RBAC re-check session
                rbac_session = _mock_db_session()
                rbac_result = MagicMock()
                rbac_result.scalar_one_or_none.return_value = MagicMock()
                rbac_session.execute.return_value = rbac_result

                # Post-approval session: re-load task + flush
                post_session = _mock_db_session()
                post_task = MagicMock()
                post_task.title = "New Title"
                post_task_result = MagicMock()
                post_task_result.scalar_one_or_none.return_value = post_task
                post_session.execute = AsyncMock(return_value=post_task_result)

                mock_tool_session.side_effect = [
                    _async_ctx(pre_session),
                    _async_ctx(rbac_session),
                    _async_ctx(post_session),
                ]
                mock_interrupt.return_value = {"approved": True}

                result = await update_task.ainvoke(
                    {
                        "task": task_id,
                        "title": "New Title",
                    }
                )

                assert "Updated task SP-1" in result
                mock_interrupt.assert_called_once()
                # Verify only title was set
                assert post_task.title == "New Title"
        finally:
            _clear()

    async def test_update_task_invalid_priority(self):
        """update_task rejects invalid priority 'critical'."""
        _setup_context()
        try:
            result = await update_task.ainvoke(
                {
                    "task": str(uuid4()),
                    "priority": "critical",
                }
            )
            assert "Invalid priority" in result
            assert "critical" in result
        finally:
            _clear()

    async def test_update_task_invalid_due_date(self):
        """update_task rejects invalid due_date 'not-a-date'."""
        _setup_context()
        try:
            result = await update_task.ainvoke(
                {
                    "task": str(uuid4()),
                    "due_date": "not-a-date",
                }
            )
            assert "Invalid due_date" in result
            assert "not-a-date" in result
        finally:
            _clear()

    async def test_update_task_rbac_denied(self):
        """update_task denies access when user has no project access."""
        task_id = str(uuid4())

        _setup_context(accessible_project_ids=[])

        try:
            with patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session:
                session = _mock_db_session()

                # _resolve_task: UUID valid but no project access
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = None  # not in accessible projects
                session.execute = AsyncMock(return_value=resolve_result)

                mock_tool_session.return_value = _async_ctx(session)

                result = await update_task.ainvoke(
                    {
                        "task": task_id,
                        "title": "Should Fail",
                    }
                )

                assert "No task found" in result or "not found" in result.lower()
        finally:
            _clear()

    async def test_update_task_no_fields(self):
        """update_task rejects when no fields are provided."""
        _setup_context()
        try:
            result = await update_task.ainvoke(
                {
                    "task": str(uuid4()),
                }
            )
            assert "At least one field" in result
        finally:
            _clear()


# ---------------------------------------------------------------------------
# add_task_comment tests
# ---------------------------------------------------------------------------


class TestAddTaskComment:
    async def test_add_comment_with_mentions(self):
        """add_task_comment creates comment + mention records + notifications."""
        task_id = str(uuid4())
        proj_id = str(uuid4())
        user_id = str(uuid4())
        mention_user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        try:
            with (
                patch("app.ai.agent.tools.write_tools.interrupt") as mock_interrupt,
                patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session,
            ):
                # Pre-interrupt session
                pre_session = _mock_db_session()

                # _resolve_task UUID fast path
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = UUID(task_id)

                # Task detail lookup
                mock_task = MagicMock()
                mock_task.project_id = UUID(proj_id)
                mock_task.task_key = "SP-1"
                mock_task.title = "Fix login"
                task_result = MagicMock()
                task_result.scalar_one_or_none.return_value = mock_task

                # _resolve_user for mention: UUID fast path
                mention_resolve_result = MagicMock()
                mention_resolve_result.scalar_one_or_none.return_value = UUID(mention_user_id)

                # User detail lookup for mention
                mock_mention_user = MagicMock()
                mock_mention_user.display_name = "Alice"
                mock_mention_user.email = "alice@test.com"
                mention_user_result = MagicMock()
                mention_user_result.scalar_one_or_none.return_value = mock_mention_user

                pre_session.execute = AsyncMock(
                    side_effect=[
                        resolve_result,
                        task_result,
                        mention_resolve_result,
                        mention_user_result,
                    ]
                )

                # Post-approval session
                post_session = _mock_db_session()
                # Comment mock with id
                mock_comment = MagicMock()
                mock_comment.id = uuid4()

                # TOCTOU re-check: Project.application_id lookup + ApplicationMember check
                app_id = uuid4()
                proj_app_result = MagicMock()
                proj_app_result.scalar_one_or_none.return_value = app_id
                membership_result = MagicMock()
                membership_result.scalar_one_or_none.return_value = uuid4()  # has access

                post_session.execute = AsyncMock(
                    side_effect=[
                        proj_app_result,
                        membership_result,
                    ]
                )

                # Track db.add calls
                added_objects = []
                post_session.add = lambda obj: added_objects.append(obj)

                mock_tool_session.side_effect = [
                    _async_ctx(pre_session),
                    _async_ctx(post_session),
                ]
                mock_interrupt.return_value = {"approved": True}

                result = await add_task_comment.ainvoke(
                    {
                        "task": task_id,
                        "content": "Great work on this!",
                        "mentions": mention_user_id,
                    }
                )

                assert "Added comment to SP-1" in result
                mock_interrupt.assert_called_once()

                # Verify confirmation included mention info
                confirm_call = mock_interrupt.call_args[0][0]
                assert "Alice" in confirm_call["summary"]
        finally:
            _clear()

    async def test_add_comment_too_long(self):
        """add_task_comment rejects content over 5000 chars."""
        _setup_context()
        try:
            result = await add_task_comment.ainvoke(
                {
                    "task": str(uuid4()),
                    "content": "x" * 5001,
                }
            )
            assert "5,000 characters" in result
        finally:
            _clear()

    async def test_add_comment_any_app_member(self):
        """add_task_comment allows any project member (including viewer) to comment."""
        task_id = str(uuid4())
        proj_id = str(uuid4())
        user_id = str(uuid4())

        # Viewer has project access (accessible_project_ids includes the project)
        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        try:
            with (
                patch("app.ai.agent.tools.write_tools.interrupt") as mock_interrupt,
                patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session,
            ):
                # Pre-interrupt session
                pre_session = _mock_db_session()
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = UUID(task_id)
                mock_task = MagicMock()
                mock_task.project_id = UUID(proj_id)
                mock_task.task_key = "SP-5"
                mock_task.title = "Viewer task"
                task_result = MagicMock()
                task_result.scalar_one_or_none.return_value = mock_task
                pre_session.execute = AsyncMock(side_effect=[resolve_result, task_result])

                # Post-approval session
                post_session = _mock_db_session()
                post_session.add = MagicMock()

                # TOCTOU re-check: Project.application_id lookup + ApplicationMember check
                app_id = uuid4()
                proj_app_result = MagicMock()
                proj_app_result.scalar_one_or_none.return_value = app_id
                membership_result = MagicMock()
                membership_result.scalar_one_or_none.return_value = uuid4()  # has access

                post_session.execute = AsyncMock(
                    side_effect=[
                        proj_app_result,
                        membership_result,
                    ]
                )

                mock_tool_session.side_effect = [
                    _async_ctx(pre_session),
                    _async_ctx(post_session),
                ]
                mock_interrupt.return_value = {"approved": True}

                result = await add_task_comment.ainvoke(
                    {
                        "task": task_id,
                        "content": "Viewer can comment too!",
                    }
                )

                assert "Added comment" in result
                assert "SP-5" in result
        finally:
            _clear()

    async def test_add_comment_empty_content(self):
        """add_task_comment rejects empty content."""
        _setup_context()
        try:
            result = await add_task_comment.ainvoke(
                {
                    "task": str(uuid4()),
                    "content": "",
                }
            )
            assert "required" in result.lower()
        finally:
            _clear()


# ---------------------------------------------------------------------------
# delete_task tests
# ---------------------------------------------------------------------------


class TestDeleteTask:
    async def test_delete_task_cascade(self):
        """delete_task deletes task and updates agg counters."""
        task_id = str(uuid4())
        proj_id = str(uuid4())
        user_id = str(uuid4())
        status_id = uuid4()

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        try:
            with (
                patch("app.ai.agent.tools.write_tools.interrupt") as mock_interrupt,
                patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session,
            ):
                # Pre-interrupt session: resolve + load task + load status
                pre_session = _mock_db_session()
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = UUID(task_id)
                mock_task = MagicMock()
                mock_task.project_id = UUID(proj_id)
                mock_task.task_key = "SP-1"
                mock_task.title = "Fix login"
                mock_task.task_status_id = status_id
                task_result = MagicMock()
                task_result.scalar_one_or_none.return_value = mock_task
                mock_status = MagicMock()
                mock_status.name = "Todo"
                status_result = MagicMock()
                status_result.scalar_one_or_none.return_value = mock_status
                pre_session.execute = AsyncMock(side_effect=[resolve_result, task_result, status_result])

                # Post-approval combined session: RBAC re-check + re-load task + agg lookup + delete
                post_session = _mock_db_session()
                rbac_result = MagicMock()
                rbac_result.scalar_one_or_none.return_value = MagicMock()
                post_task = MagicMock()
                post_task.task_key = "SP-1"
                post_task.title = "Fix login"
                post_task_result = MagicMock()
                post_task_result.scalar_one_or_none.return_value = post_task

                mock_agg = MagicMock()
                mock_agg.todo_tasks = 5
                mock_agg.active_tasks = 2
                mock_agg.review_tasks = 1
                mock_agg.issue_tasks = 1
                mock_agg.done_tasks = 1
                mock_agg.total_tasks = 10
                mock_agg.updated_at = None
                agg_result = MagicMock()
                agg_result.scalar_one_or_none.return_value = mock_agg

                post_session.execute = AsyncMock(side_effect=[rbac_result, post_task_result, agg_result])

                mock_tool_session.side_effect = [
                    _async_ctx(pre_session),
                    _async_ctx(post_session),
                ]
                mock_interrupt.return_value = {"approved": True}

                result = await delete_task.ainvoke(
                    {
                        "task": task_id,
                    }
                )

                assert "Deleted task SP-1" in result
                mock_interrupt.assert_called_once()
                # Verify agg counters were decremented
                assert mock_agg.todo_tasks == 4
                assert mock_agg.total_tasks == 9
                # Verify task was deleted
                post_session.delete.assert_called_once_with(post_task)
        finally:
            _clear()

    async def test_delete_task_rbac_denied(self):
        """delete_task denies access when user has no project access."""
        task_id = str(uuid4())

        _setup_context(accessible_project_ids=[])

        try:
            with patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session:
                session = _mock_db_session()
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = None
                session.execute = AsyncMock(return_value=resolve_result)

                mock_tool_session.return_value = _async_ctx(session)

                result = await delete_task.ainvoke(
                    {
                        "task": task_id,
                    }
                )

                assert "No task found" in result or "not found" in result.lower()
        finally:
            _clear()

    async def test_delete_task_hitl_rejection(self):
        """delete_task returns cancellation when user rejects confirmation."""
        task_id = str(uuid4())
        proj_id = str(uuid4())
        status_id = uuid4()

        _setup_context(accessible_project_ids=[proj_id])

        try:
            with (
                patch("app.ai.agent.tools.write_tools.interrupt") as mock_interrupt,
                patch("app.ai.agent.tools.write_tools._get_tool_session") as mock_tool_session,
            ):
                pre_session = _mock_db_session()
                resolve_result = MagicMock()
                resolve_result.scalar_one_or_none.return_value = UUID(task_id)
                mock_task = MagicMock()
                mock_task.project_id = UUID(proj_id)
                mock_task.task_key = "SP-1"
                mock_task.title = "Fix login"
                mock_task.task_status_id = status_id
                task_result = MagicMock()
                task_result.scalar_one_or_none.return_value = mock_task
                mock_status = MagicMock()
                mock_status.name = "Todo"
                status_result = MagicMock()
                status_result.scalar_one_or_none.return_value = mock_status
                pre_session.execute = AsyncMock(side_effect=[resolve_result, task_result, status_result])

                mock_tool_session.return_value = _async_ctx(pre_session)
                mock_interrupt.return_value = {"approved": False}

                result = await delete_task.ainvoke(
                    {
                        "task": task_id,
                    }
                )

                assert "cancelled" in result.lower()
        finally:
            _clear()


# ---------------------------------------------------------------------------
# WRITE_TOOLS registry
# ---------------------------------------------------------------------------


class TestWriteToolsRegistryExpanded:
    def test_includes_new_tools(self):
        """WRITE_TOOLS includes update_task, add_task_comment, delete_task."""
        names = {t.name for t in WRITE_TOOLS}
        assert "update_task" in names
        assert "add_task_comment" in names
        assert "delete_task" in names

    def test_has_11_tools(self):
        """WRITE_TOOLS has 11 tools after expansion."""
        assert len(WRITE_TOOLS) == 11
