"""Unit tests for write tools of the Blair AI agent (app.ai.agent.tools_write).

Tests cover:
- _parse_uuid valid/invalid cases
- _strip_markdown removes headings, bold, links
- _STATUS_NAME_MAP has 5 entries
- create_task — RBAC denied, name resolution, user approval/rejection flows
- update_task_status — invalid status, already in target status
- assign_task — assignee not found, not project member
- create_document — invalid scope, RBAC denied, name resolution for scope_id
- WRITE_TOOLS has 4 tools
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.ai.agent.tools_write import (
    WRITE_TOOLS,
    _STATUS_NAME_MAP,
    _parse_uuid,
    _strip_markdown,
    assign_task,
    create_document,
    create_task,
    update_task_status,
)
from app.ai.agent.tools_read import _tool_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_context(**overrides):
    """Populate _tool_context with sensible defaults + overrides."""
    ctx = {
        "user_id": str(uuid4()),
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "db_session_factory": MagicMock(),
        "provider_registry": MagicMock(),
    }
    ctx.update(overrides)
    _tool_context.update(ctx)
    return ctx


def _clear():
    _tool_context.clear()


def _mock_db_session():
    """Create a mock AsyncSession with close/rollback/commit."""
    session = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# _parse_uuid
# ---------------------------------------------------------------------------

class TestParseUuid:

    def test_valid_uuid(self):
        uid = uuid4()
        result = _parse_uuid(str(uid), "test_field")
        assert result == uid

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValueError, match="Invalid test_field"):
            _parse_uuid("not-a-uuid", "test_field")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Invalid field"):
            _parse_uuid("", "field")


# ---------------------------------------------------------------------------
# _strip_markdown
# ---------------------------------------------------------------------------

class TestStripMarkdown:

    def test_removes_headings(self):
        text = "# Heading\n## Sub\nBody text"
        result = _strip_markdown(text)
        assert "# " not in result
        assert "Heading" in result
        assert "Body text" in result

    def test_removes_bold(self):
        text = "This is **bold** and __also bold__"
        result = _strip_markdown(text)
        assert "**" not in result
        assert "__" not in result
        assert "bold" in result

    def test_removes_links_keeps_text(self):
        text = "Click [here](https://example.com) for more"
        result = _strip_markdown(text)
        assert "[here]" not in result
        assert "https://example.com" not in result
        assert "here" in result

    def test_removes_inline_code(self):
        text = "Use `npm install` to setup"
        result = _strip_markdown(text)
        assert "`" not in result
        assert "npm install" in result


# ---------------------------------------------------------------------------
# _STATUS_NAME_MAP
# ---------------------------------------------------------------------------

class TestStatusNameMap:

    def test_has_5_entries(self):
        assert len(_STATUS_NAME_MAP) == 5

    def test_expected_keys(self):
        expected = {"todo", "in_progress", "in_review", "issue", "done"}
        assert set(_STATUS_NAME_MAP.keys()) == expected

    def test_expected_values(self):
        assert _STATUS_NAME_MAP["todo"] == "Todo"
        assert _STATUS_NAME_MAP["in_progress"] == "In Progress"
        assert _STATUS_NAME_MAP["done"] == "Done"


# ---------------------------------------------------------------------------
# WRITE_TOOLS registry
# ---------------------------------------------------------------------------

class TestWriteToolsRegistry:

    def test_has_4_tools(self):
        assert len(WRITE_TOOLS) == 4

    def test_tool_names(self):
        names = {t.name for t in WRITE_TOOLS}
        assert names == {"create_task", "update_task_status", "assign_task", "create_document"}


# ---------------------------------------------------------------------------
# create_task tool
# ---------------------------------------------------------------------------

class TestCreateTask:

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_rbac_denied(self, mock_get_db):
        """create_task returns not-found when project is not accessible."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])

        # The resolver now opens a session, so mock it
        mock_session = _mock_db_session()
        mock_get_db.return_value = mock_session

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "New Task",
        })
        assert "No project found" in result
        _clear()

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_user_approval_flow(self, mock_get_db, mock_interrupt):
        """create_task creates the task when user approves."""
        proj_id = str(uuid4())
        proj_uuid = UUID(proj_id)
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        # First session: project lookup (pre-interrupt)
        pre_session = _mock_db_session()
        mock_project = MagicMock()
        mock_project.name = "My Project"
        mock_project.key = "MP"
        pre_result = MagicMock()
        pre_result.scalar_one_or_none.return_value = mock_project
        pre_session.execute.return_value = pre_result

        # Second session: task creation (post-approval)
        post_session = _mock_db_session()
        # First query: TaskStatus lookup
        mock_status = MagicMock()
        mock_status.id = uuid4()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = mock_status
        # Second query: key generation
        key_row = MagicMock()
        key_row.__getitem__ = lambda self, idx: 42
        key_result = MagicMock()
        key_result.fetchone.return_value = key_row
        post_session.execute.side_effect = [status_result, key_result]

        mock_get_db.side_effect = [pre_session, post_session]
        mock_interrupt.return_value = {"approved": True}

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "New Task",
        })

        assert "created" in result.lower()
        assert "MP-42" in result
        mock_interrupt.assert_called_once()
        post_session.commit.assert_awaited_once()
        _clear()

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_user_rejection_flow(self, mock_get_db, mock_interrupt):
        """create_task returns cancellation when user rejects."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])

        pre_session = _mock_db_session()
        mock_project = MagicMock()
        mock_project.name = "My Project"
        mock_project.key = "MP"
        pre_result = MagicMock()
        pre_result.scalar_one_or_none.return_value = mock_project
        pre_session.execute.return_value = pre_result

        mock_get_db.return_value = pre_session
        mock_interrupt.return_value = {"approved": False}

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "Should Be Cancelled",
        })

        assert "cancelled" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# update_task_status tool
# ---------------------------------------------------------------------------

class TestUpdateTaskStatus:

    async def test_invalid_status(self):
        """update_task_status rejects invalid status names."""
        _setup_context()
        result = await update_task_status.ainvoke({
            "task_id": str(uuid4()),
            "new_status": "invalid_status",
        })
        assert "Invalid status" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_already_in_target_status(self, mock_get_db):
        """update_task_status returns no-change when task is already in target status."""
        task_id = str(uuid4())
        proj_id = str(uuid4())
        status_id = uuid4()

        _setup_context(accessible_project_ids=[proj_id])

        mock_session = _mock_db_session()

        # First execute: task lookup
        mock_task = MagicMock()
        mock_task.project_id = UUID(proj_id)
        mock_task.task_key = "TEST-1"
        mock_task.title = "Some Task"
        mock_task.task_status_id = status_id
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task

        # Second execute: current status lookup
        mock_current_status = MagicMock()
        mock_current_status.name = "Todo"
        current_status_result = MagicMock()
        current_status_result.scalar_one_or_none.return_value = mock_current_status

        # Third execute: target status lookup (same id = already in target)
        mock_target_status = MagicMock()
        mock_target_status.id = status_id  # Same as current
        mock_target_status.name = "Todo"
        target_status_result = MagicMock()
        target_status_result.scalar_one_or_none.return_value = mock_target_status

        mock_session.execute.side_effect = [
            task_result,
            current_status_result,
            target_status_result,
        ]
        mock_get_db.return_value = mock_session

        result = await update_task_status.ainvoke({
            "task_id": task_id,
            "new_status": "todo",
        })
        assert "already" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# assign_task tool
# ---------------------------------------------------------------------------

class TestAssignTask:

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_assignee_not_found(self, mock_get_db):
        """assign_task returns error when assignee user does not exist."""
        task_id = str(uuid4())
        assignee_id = str(uuid4())
        proj_id = str(uuid4())

        _setup_context(accessible_project_ids=[proj_id])

        mock_session = _mock_db_session()

        # First execute: task lookup
        mock_task = MagicMock()
        mock_task.project_id = UUID(proj_id)
        mock_task.task_key = "TEST-1"
        mock_task.title = "Some Task"
        mock_task.assignee_id = None
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task

        # Second execute: assignee user lookup — not found
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [task_result, user_result]
        mock_get_db.return_value = mock_session

        result = await assign_task.ainvoke({
            "task_id": task_id,
            "assignee_id": assignee_id,
        })
        assert "not found" in result.lower()
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_assignee_not_project_member(self, mock_get_db):
        """assign_task returns error when assignee is not a project member."""
        task_id = str(uuid4())
        assignee_id = str(uuid4())
        proj_id = str(uuid4())

        _setup_context(accessible_project_ids=[proj_id])

        mock_session = _mock_db_session()

        # First execute: task lookup
        mock_task = MagicMock()
        mock_task.project_id = UUID(proj_id)
        mock_task.task_key = "TEST-1"
        mock_task.title = "Some Task"
        mock_task.assignee_id = None
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task

        # Second execute: assignee user found
        mock_user = MagicMock()
        mock_user.display_name = "John Doe"
        mock_user.email = "john@test.com"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_user

        # Third execute: project member check — not found
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None

        # Fourth execute: project name lookup for error message
        proj_name_result = MagicMock()
        proj_name_result.scalar_one_or_none.return_value = "My Project"

        mock_session.execute.side_effect = [
            task_result, user_result, member_result, proj_name_result,
        ]
        mock_get_db.return_value = mock_session

        result = await assign_task.ainvoke({
            "task_id": task_id,
            "assignee_id": assignee_id,
        })
        assert "not a member" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# create_document tool
# ---------------------------------------------------------------------------

class TestCreateDocument:

    async def test_invalid_scope(self):
        """create_document rejects invalid scope values."""
        _setup_context()
        result = await create_document.ainvoke({
            "title": "Doc",
            "content": "Body",
            "scope": "global",
            "scope_id": str(uuid4()),
        })
        assert "Scope must be" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_rbac_denied_application_scope(self, mock_get_db):
        """create_document returns not-found for application scope the user cannot reach."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[])
        mock_get_db.return_value = _mock_db_session()

        result = await create_document.ainvoke({
            "title": "Doc",
            "content": "Body",
            "scope": "application",
            "scope_id": app_id,
        })
        assert "No application found" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_rbac_denied_project_scope(self, mock_get_db):
        """create_document returns not-found for project scope the user cannot reach."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        mock_get_db.return_value = _mock_db_session()

        result = await create_document.ainvoke({
            "title": "Doc",
            "content": "Body",
            "scope": "project",
            "scope_id": proj_id,
        })
        assert "No project found" in result
        _clear()

    async def test_rbac_denied_personal_scope_wrong_user(self):
        """create_document denies access when personal scope_id != user_id."""
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        _setup_context(user_id=user_id)

        result = await create_document.ainvoke({
            "title": "Doc",
            "content": "Body",
            "scope": "personal",
            "scope_id": other_user_id,
        })
        assert "Access denied" in result
        _clear()

    async def test_empty_title_rejected(self):
        """create_document rejects empty title."""
        _setup_context()
        result = await create_document.ainvoke({
            "title": "",
            "content": "Body",
            "scope": "personal",
            "scope_id": str(uuid4()),
        })
        assert "title is required" in result.lower()
        _clear()

    async def test_empty_content_rejected(self):
        """create_document rejects empty content."""
        _setup_context()
        result = await create_document.ainvoke({
            "title": "Valid Title",
            "content": "",
            "scope": "personal",
            "scope_id": str(uuid4()),
        })
        assert "content is required" in result.lower()
        _clear()

    async def test_title_too_long_rejected(self):
        """create_document rejects title longer than 255 chars."""
        _setup_context()
        result = await create_document.ainvoke({
            "title": "X" * 256,
            "content": "Body",
            "scope": "personal",
            "scope_id": str(uuid4()),
        })
        assert "255" in result
        _clear()


# ---------------------------------------------------------------------------
# create_task — additional validation tests
# ---------------------------------------------------------------------------

class TestCreateTaskValidation:

    async def test_empty_title_rejected(self):
        """create_task rejects empty title."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "",
        })
        assert "title is required" in result.lower()
        _clear()

    async def test_title_too_long_rejected(self):
        """create_task rejects title longer than 500 chars."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "T" * 501,
        })
        assert "500" in result
        _clear()

    async def test_invalid_priority_rejected(self):
        """create_task rejects invalid priority value."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "Valid Task",
            "priority": "critical",
        })
        assert "Invalid priority" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_invalid_project_id_rejected(self, mock_get_db):
        """create_task rejects non-UUID non-name project_id (no match found)."""
        _setup_context(accessible_project_ids=[])

        mock_session = _mock_db_session()
        mock_get_db.return_value = mock_session

        result = await create_task.ainvoke({
            "project_id": "not-a-uuid",
            "title": "Some Task",
        })
        # Resolver returns "No project found" instead of "Invalid project_id"
        assert "No project found" in result or "Access denied" in result
        _clear()


# ---------------------------------------------------------------------------
# update_task_status — additional tests
# ---------------------------------------------------------------------------

class TestUpdateTaskStatusAdditional:

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_rbac_denied(self, mock_get_db):
        """update_task_status returns access denied for inaccessible project."""
        task_id = str(uuid4())
        proj_id = str(uuid4())

        _setup_context(accessible_project_ids=[])

        mock_session = _mock_db_session()
        mock_task = MagicMock()
        mock_task.project_id = UUID(proj_id)
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = task_result
        mock_get_db.return_value = mock_session

        result = await update_task_status.ainvoke({
            "task_id": task_id,
            "new_status": "done",
        })
        assert "Access denied" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_task_not_found(self, mock_get_db):
        """update_task_status returns not-found for missing task."""
        _setup_context()

        mock_session = _mock_db_session()
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = task_result
        mock_get_db.return_value = mock_session

        result = await update_task_status.ainvoke({
            "task_id": str(uuid4()),
            "new_status": "done",
        })
        assert "not found" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# assign_task — additional tests
# ---------------------------------------------------------------------------

class TestAssignTaskAdditional:

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_rbac_denied(self, mock_get_db):
        """assign_task returns access denied for inaccessible project."""
        task_id = str(uuid4())
        assignee_id = str(uuid4())
        proj_id = str(uuid4())

        _setup_context(accessible_project_ids=[])

        mock_session = _mock_db_session()
        mock_task = MagicMock()
        mock_task.project_id = UUID(proj_id)
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = task_result
        mock_get_db.return_value = mock_session

        result = await assign_task.ainvoke({
            "task_id": task_id,
            "assignee_id": assignee_id,
        })
        assert "Access denied" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_already_assigned_same_user(self, mock_get_db):
        """assign_task returns no-change when task already assigned to the same user."""
        task_id = str(uuid4())
        assignee_id = str(uuid4())
        assignee_uuid = UUID(assignee_id)
        proj_id = str(uuid4())

        _setup_context(accessible_project_ids=[proj_id])

        mock_session = _mock_db_session()

        # First execute: task lookup
        mock_task = MagicMock()
        mock_task.project_id = UUID(proj_id)
        mock_task.task_key = "TEST-1"
        mock_task.title = "Some Task"
        mock_task.assignee_id = assignee_uuid  # Already assigned to this user
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task

        # Second execute: assignee user lookup
        mock_user = MagicMock()
        mock_user.display_name = "John Doe"
        mock_user.email = "john@test.com"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_user

        # Third execute: project member check — found
        mock_member = MagicMock()
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member

        # Fourth execute: current assignee lookup (same user since already assigned)
        current_assignee_user = MagicMock()
        current_assignee_user.display_name = "John Doe"
        current_assignee_user.email = "john@test.com"
        current_assignee_result = MagicMock()
        current_assignee_result.scalar_one_or_none.return_value = current_assignee_user

        mock_session.execute.side_effect = [
            task_result, user_result, member_result, current_assignee_result,
        ]
        mock_get_db.return_value = mock_session

        result = await assign_task.ainvoke({
            "task_id": task_id,
            "assignee_id": assignee_id,
        })
        assert "already assigned" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# update_task_status — approval flow (happy path)
# ---------------------------------------------------------------------------

class TestUpdateTaskStatusApproval:
    """Test the approval flow for update_task_status when user approves."""

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_approval_updates_status(self, mock_tool_session, mock_interrupt):
        """update_task_status updates the task when user approves."""
        task_id = str(uuid4())
        task_uuid = UUID(task_id)
        proj_id = str(uuid4())
        current_status_id = uuid4()
        target_status_id = uuid4()

        _setup_context(accessible_project_ids=[proj_id])

        # Pre-interrupt session: loads task, current status, target status
        pre_session = _mock_db_session()
        mock_task_pre = MagicMock()
        mock_task_pre.project_id = UUID(proj_id)
        mock_task_pre.task_key = "TEST-5"
        mock_task_pre.title = "Fix Bug"
        mock_task_pre.task_status_id = current_status_id
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task_pre

        mock_current_status = MagicMock()
        mock_current_status.name = "Todo"
        mock_current_status.id = current_status_id
        current_status_result = MagicMock()
        current_status_result.scalar_one_or_none.return_value = mock_current_status

        mock_target_status_pre = MagicMock()
        mock_target_status_pre.id = target_status_id
        mock_target_status_pre.name = "Done"
        target_status_result_pre = MagicMock()
        target_status_result_pre.scalar_one_or_none.return_value = mock_target_status_pre

        pre_session.execute.side_effect = [
            task_result,
            current_status_result,
            target_status_result_pre,
        ]

        # Post-approval session: re-loads task, re-resolves target status
        post_session = _mock_db_session()
        mock_task_post = MagicMock()
        mock_task_post.project_id = UUID(proj_id)
        mock_task_post.task_key = "TEST-5"
        mock_task_post.task_status_id = current_status_id
        task_result_post = MagicMock()
        task_result_post.scalar_one_or_none.return_value = mock_task_post

        mock_target_status_post = MagicMock()
        mock_target_status_post.id = target_status_id
        mock_target_status_post.name = "Done"
        target_status_result_post = MagicMock()
        target_status_result_post.scalar_one_or_none.return_value = mock_target_status_post

        post_session.execute.side_effect = [
            task_result_post,
            target_status_result_post,
        ]

        # Setup context managers for _get_tool_session
        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)

        post_ctx = AsyncMock()
        post_ctx.__aenter__ = AsyncMock(return_value=post_session)
        post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_tool_session.side_effect = [pre_ctx, post_ctx]
        mock_interrupt.return_value = {"approved": True}

        result = await update_task_status.ainvoke({
            "task_id": task_id,
            "new_status": "done",
        })

        assert "updated" in result.lower()
        assert "Done" in result
        assert mock_task_post.task_status_id == target_status_id
        post_session.commit.assert_awaited_once()
        mock_interrupt.assert_called_once()
        _clear()


# ---------------------------------------------------------------------------
# assign_task — approval flow (happy path)
# ---------------------------------------------------------------------------

class TestAssignTaskApproval:
    """Test the approval flow for assign_task when user approves."""

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_approval_assigns_task(self, mock_tool_session, mock_interrupt):
        """assign_task sets the assignee when user approves."""
        task_id = str(uuid4())
        task_uuid = UUID(task_id)
        assignee_id = str(uuid4())
        assignee_uuid = UUID(assignee_id)
        proj_id = str(uuid4())

        _setup_context(accessible_project_ids=[proj_id])

        # Pre-interrupt session: task, assignee user, member check, no current assignee
        pre_session = _mock_db_session()
        mock_task_pre = MagicMock()
        mock_task_pre.project_id = UUID(proj_id)
        mock_task_pre.task_key = "TEST-7"
        mock_task_pre.title = "Implement Feature"
        mock_task_pre.assignee_id = None  # Unassigned
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task_pre

        mock_assignee_user = MagicMock()
        mock_assignee_user.display_name = "Jane Smith"
        mock_assignee_user.email = "jane@test.com"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_assignee_user

        mock_member = MagicMock()
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = mock_member

        pre_session.execute.side_effect = [
            task_result,
            user_result,
            member_result,
        ]

        # Post-approval session: re-loads task
        post_session = _mock_db_session()
        mock_task_post = MagicMock()
        mock_task_post.project_id = UUID(proj_id)
        mock_task_post.task_key = "TEST-7"
        mock_task_post.assignee_id = None  # Will be set by the tool
        task_result_post = MagicMock()
        task_result_post.scalar_one_or_none.return_value = mock_task_post

        post_session.execute.side_effect = [task_result_post]

        # Setup context managers for _get_tool_session
        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)

        post_ctx = AsyncMock()
        post_ctx.__aenter__ = AsyncMock(return_value=post_session)
        post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_tool_session.side_effect = [pre_ctx, post_ctx]
        mock_interrupt.return_value = {"approved": True}

        result = await assign_task.ainvoke({
            "task_id": task_id,
            "assignee_id": assignee_id,
        })

        assert "assigned" in result.lower()
        assert "Jane Smith" in result
        assert mock_task_post.assignee_id == assignee_uuid
        post_session.commit.assert_awaited_once()
        mock_interrupt.assert_called_once()
        _clear()


# ---------------------------------------------------------------------------
# create_document — approval flow (happy path)
# ---------------------------------------------------------------------------

class TestCreateDocumentApproval:
    """Test the approval flow for create_document when user approves."""

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_approval_creates_document_personal_scope(
        self, mock_tool_session, mock_interrupt
    ):
        """create_document creates the document with correct scope when user approves."""
        user_id = str(uuid4())
        _setup_context(user_id=user_id)

        # Pre-interrupt session: personal scope check (no DB queries for personal)
        pre_session = _mock_db_session()
        # No execute calls expected for personal scope — it just checks user_id match
        pre_session.execute.side_effect = []

        # Post-approval session: creates the document
        post_session = _mock_db_session()
        # No execute calls needed — db.add + flush + commit
        post_session.execute.side_effect = []

        # Mock document id assignment on flush
        doc_id = uuid4()

        def mock_add(obj):
            # Simulate SQLAlchemy assigning id on add
            obj.id = doc_id

        post_session.add = mock_add

        # Setup context managers for _get_tool_session
        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)

        post_ctx = AsyncMock()
        post_ctx.__aenter__ = AsyncMock(return_value=post_session)
        post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_tool_session.side_effect = [pre_ctx, post_ctx]
        mock_interrupt.return_value = {"approved": True}

        with patch("app.ai.agent.tools_write.Document") as MockDocument:
            mock_doc_instance = MagicMock()
            mock_doc_instance.id = doc_id
            MockDocument.return_value = mock_doc_instance

            result = await create_document.ainvoke({
                "title": "Meeting Notes",
                "content": "# Sprint Retro\n\nGood sprint overall.",
                "scope": "personal",
                "scope_id": user_id,
            })

        assert "created" in result.lower()
        assert "Meeting Notes" in result
        mock_interrupt.assert_called_once()
        post_session.commit.assert_awaited_once()

        # Verify Document constructor received correct scope fields
        call_kwargs = MockDocument.call_args[1]
        assert call_kwargs["user_id"] == UUID(user_id)
        assert call_kwargs["application_id"] is None
        assert call_kwargs["project_id"] is None
        assert call_kwargs["title"] == "Meeting Notes"
        _clear()

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_approval_creates_document_application_scope(
        self, mock_tool_session, mock_interrupt
    ):
        """create_document creates the document scoped to an application."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        # Pre-interrupt session: application lookup
        pre_session = _mock_db_session()
        mock_app = MagicMock()
        mock_app.name = "My Application"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app
        pre_session.execute.side_effect = [app_result]

        # Post-approval session: creates the document
        post_session = _mock_db_session()
        post_session.execute.side_effect = []

        doc_id = uuid4()

        # Setup context managers for _get_tool_session
        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)

        post_ctx = AsyncMock()
        post_ctx.__aenter__ = AsyncMock(return_value=post_session)
        post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_tool_session.side_effect = [pre_ctx, post_ctx]
        mock_interrupt.return_value = {"approved": True}

        with patch("app.ai.agent.tools_write.Document") as MockDocument:
            mock_doc_instance = MagicMock()
            mock_doc_instance.id = doc_id
            MockDocument.return_value = mock_doc_instance

            result = await create_document.ainvoke({
                "title": "API Spec",
                "content": "Endpoint definitions...",
                "scope": "application",
                "scope_id": app_id,
            })

        assert "created" in result.lower()
        post_session.commit.assert_awaited_once()

        # Verify Document constructor received correct scope fields
        call_kwargs = MockDocument.call_args[1]
        assert call_kwargs["application_id"] == UUID(app_id)
        assert call_kwargs["project_id"] is None
        assert call_kwargs["user_id"] is None
        _clear()


# ---------------------------------------------------------------------------
# create_task — name resolution tests
# ---------------------------------------------------------------------------

class TestCreateTaskNameResolution:

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_resolves_project_by_name(self, mock_get_db, mock_interrupt):
        """create_task resolves project name and creates task."""
        proj_id = uuid4()
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[str(proj_id)],
        )

        # First session: resolve + project lookup (pre-interrupt)
        pre_session = _mock_db_session()
        # Resolver query: name → UUID
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = proj_id
        mock_row.name = "Backend API"
        resolver_result.all.return_value = [mock_row]

        # Project lookup
        mock_project = MagicMock()
        mock_project.name = "Backend API"
        mock_project.key = "BE"
        project_result = MagicMock()
        project_result.scalar_one_or_none.return_value = mock_project

        pre_session.execute = AsyncMock(side_effect=[
            resolver_result,
            project_result,
        ])

        # Second session: task creation (post-approval)
        post_session = _mock_db_session()
        mock_status = MagicMock()
        mock_status.id = uuid4()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = mock_status
        key_row = MagicMock()
        key_row.__getitem__ = lambda self, idx: 7
        key_result = MagicMock()
        key_result.fetchone.return_value = key_row
        post_session.execute.side_effect = [status_result, key_result]

        mock_get_db.side_effect = [pre_session, post_session]
        mock_interrupt.return_value = {"approved": True}

        result = await create_task.ainvoke({
            "project_id": "Backend",
            "title": "New Feature",
        })

        assert "created" in result.lower()
        assert "BE-7" in result
        mock_interrupt.assert_called_once()
        _clear()


# ---------------------------------------------------------------------------
# create_document — name resolution tests
# ---------------------------------------------------------------------------

class TestCreateDocumentNameResolution:

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_resolves_app_name_for_scope(
        self, mock_tool_session, mock_interrupt
    ):
        """create_document resolves application name for scope_id."""
        app_id = uuid4()
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[str(app_id)])

        # Pre-interrupt session: resolve app + lookup
        pre_session = _mock_db_session()

        # Resolver: name match
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "PMS Application"
        resolver_result.all.return_value = [mock_row]

        # App lookup for display
        mock_app = MagicMock()
        mock_app.name = "PMS Application"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app

        pre_session.execute = AsyncMock(side_effect=[
            resolver_result,
            app_result,
        ])

        # Post-approval session
        post_session = _mock_db_session()
        post_session.execute.side_effect = []
        doc_id = uuid4()

        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)

        post_ctx = AsyncMock()
        post_ctx.__aenter__ = AsyncMock(return_value=post_session)
        post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_tool_session.side_effect = [pre_ctx, post_ctx]
        mock_interrupt.return_value = {"approved": True}

        with patch("app.ai.agent.tools_write.Document") as MockDocument:
            mock_doc_instance = MagicMock()
            mock_doc_instance.id = doc_id
            MockDocument.return_value = mock_doc_instance

            result = await create_document.ainvoke({
                "title": "Test Doc",
                "content": "Some content here.",
                "scope": "application",
                "scope_id": "PMS",
            })

        assert "created" in result.lower()
        assert "PMS Application" in result
        mock_interrupt.assert_called_once()
        _clear()


# ---------------------------------------------------------------------------
# create_task — name resolution error cases
# ---------------------------------------------------------------------------

class TestCreateTaskNameResolutionErrors:

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_name_no_match(self, mock_get_db):
        """create_task returns error when project name has no match."""
        proj_id = uuid4()
        _setup_context(accessible_project_ids=[str(proj_id)])

        mock_session = _mock_db_session()
        resolver_result = MagicMock()
        resolver_result.all.return_value = []
        mock_session.execute.return_value = resolver_result
        mock_get_db.return_value = mock_session

        result = await create_task.ainvoke({
            "project_id": "NonExistentProject",
            "title": "New Task",
        })
        assert "No project found" in result
        _clear()

    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_name_multiple_matches(self, mock_get_db):
        """create_task returns disambiguation error when multiple projects match."""
        proj1 = uuid4()
        proj2 = uuid4()
        _setup_context(accessible_project_ids=[str(proj1), str(proj2)])

        mock_session = _mock_db_session()
        resolver_result = MagicMock()
        row1 = MagicMock()
        row1.id = proj1
        row1.name = "API v1"
        row2 = MagicMock()
        row2.id = proj2
        row2.name = "API v2"
        resolver_result.all.return_value = [row1, row2]
        mock_session.execute.return_value = resolver_result
        mock_get_db.return_value = mock_session

        result = await create_task.ainvoke({
            "project_id": "API",
            "title": "New Task",
        })
        assert "Multiple projects" in result
        assert "API v1" in result
        assert "API v2" in result
        _clear()


# ---------------------------------------------------------------------------
# create_document — folder scope validation
# ---------------------------------------------------------------------------

class TestCreateDocumentFolderScopeValidation:

    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_folder_wrong_scope_rejected(self, mock_tool_session):
        """create_document rejects folder_id from a different scope."""
        app_id = str(uuid4())
        user_id = str(uuid4())
        folder_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_app_ids=[app_id])

        pre_session = _mock_db_session()
        # Resolver: direct UUID match (fast path)
        # App name lookup
        mock_app = MagicMock()
        mock_app.name = "My App"
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = mock_app

        # Folder scope check: not found in this scope
        folder_result = MagicMock()
        folder_result.scalar_one_or_none.return_value = None

        pre_session.execute = AsyncMock(side_effect=[app_result, folder_result])

        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_tool_session.return_value = pre_ctx

        result = await create_document.ainvoke({
            "title": "Doc",
            "content": "Body",
            "scope": "application",
            "scope_id": app_id,
            "folder_id": folder_id,
        })
        assert "not found in this scope" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# assign_task — task not found (TE R2 gap 3)
# ---------------------------------------------------------------------------

class TestAssignTaskTaskNotFound:

    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_task_not_found(self, mock_tool_session):
        """assign_task returns not-found when task doesn't exist."""
        task_id = str(uuid4())
        assignee_id = str(uuid4())
        _setup_context(accessible_project_ids=[str(uuid4())])

        pre_session = _mock_db_session()
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        pre_session.execute.return_value = task_result

        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_tool_session.return_value = pre_ctx

        result = await assign_task.ainvoke({
            "task_id": task_id,
            "assignee_id": assignee_id,
        })
        assert "not found" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# create_task — no Todo status configured (TE R2 gap 4)
# ---------------------------------------------------------------------------

class TestCreateTaskNoTodoStatus:

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_db_session")
    async def test_no_todo_status(self, mock_get_db, mock_interrupt):
        """create_task returns error when project has no default Todo status."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_project_ids=[proj_id])

        # Pre-interrupt session: resolve + project lookup
        pre_session = _mock_db_session()
        mock_project = MagicMock()
        mock_project.name = "Alpha"
        mock_project.key = "AL"
        project_result = MagicMock()
        project_result.scalar_one_or_none.return_value = mock_project
        pre_session.execute.side_effect = [project_result]

        # Post-approval session: status lookup returns None
        post_session = _mock_db_session()
        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = None
        post_session.execute.side_effect = [status_result]

        mock_get_db.side_effect = [pre_session, post_session]
        mock_interrupt.return_value = {"approved": True}

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "New Task",
        })
        assert "no default" in result.lower() or "Todo" in result
        _clear()


# ---------------------------------------------------------------------------
# create_document — project scope approval (TE R2 gap 5)
# ---------------------------------------------------------------------------

class TestCreateDocumentProjectScopeApproval:

    @patch("app.ai.agent.tools_write.interrupt")
    @patch("app.ai.agent.tools_write._get_tool_session")
    async def test_approval_creates_document_project_scope(
        self, mock_tool_session, mock_interrupt
    ):
        """create_document creates the document scoped to a project."""
        proj_id = str(uuid4())
        user_id = str(uuid4())
        _setup_context(user_id=user_id, accessible_project_ids=[proj_id])

        # Pre-interrupt session: project lookup
        pre_session = _mock_db_session()
        mock_proj = MagicMock()
        mock_proj.name = "Backend API"
        proj_result = MagicMock()
        proj_result.scalar_one_or_none.return_value = mock_proj
        pre_session.execute.side_effect = [proj_result]

        # Post-approval session: creates the document
        post_session = _mock_db_session()
        post_session.execute.side_effect = []
        doc_id = uuid4()

        pre_ctx = AsyncMock()
        pre_ctx.__aenter__ = AsyncMock(return_value=pre_session)
        pre_ctx.__aexit__ = AsyncMock(return_value=None)

        post_ctx = AsyncMock()
        post_ctx.__aenter__ = AsyncMock(return_value=post_session)
        post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_tool_session.side_effect = [pre_ctx, post_ctx]
        mock_interrupt.return_value = {"approved": True}

        with patch("app.ai.agent.tools_write.Document") as MockDocument:
            mock_doc_instance = MagicMock()
            mock_doc_instance.id = doc_id
            MockDocument.return_value = mock_doc_instance

            result = await create_document.ainvoke({
                "title": "API Spec",
                "content": "Endpoints...",
                "scope": "project",
                "scope_id": proj_id,
            })

        assert "created" in result.lower()
        post_session.commit.assert_awaited_once()

        # Verify Document constructor received correct scope fields
        call_kwargs = MockDocument.call_args[1]
        assert call_kwargs["project_id"] == UUID(proj_id)
        assert call_kwargs["application_id"] is None
        assert call_kwargs["user_id"] is None
        _clear()


class TestCreateDocumentContentSizeCap:

    async def test_oversized_content_rejected(self):
        """create_document rejects content exceeding 100,000 characters."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id])

        result = await create_document.ainvoke({
            "title": "Big Doc",
            "content": "x" * 100_001,
            "scope": "application",
            "scope_id": app_id,
        })

        assert "too large" in result.lower()
        assert "100,000" in result
        _clear()


class TestCreateTaskDescriptionSizeCap:

    async def test_oversized_description_rejected(self):
        """create_task rejects description exceeding 50,000 characters."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])

        result = await create_task.ainvoke({
            "project_id": proj_id,
            "title": "Normal title",
            "description": "d" * 50_001,
        })

        assert "too large" in result.lower()
        assert "50,000" in result
        _clear()
