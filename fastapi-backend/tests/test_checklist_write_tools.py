"""Unit tests for checklist write tools of the Blair AI agent.

Tests cover:
1. add_checklist -- happy path
2. add_checklist -- rejected when task is Done
3. add_checklist -- RBAC denied (viewer can't add)
4. add_checklist_item -- happy path, counter updated
5. add_checklist_item -- checklist not found
6. toggle_checklist_item -- mark as complete, counter incremented
7. toggle_checklist_item -- mark as incomplete, counter decremented
8. toggle_checklist_item -- item not found
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.ai.agent.tools.checklist_write_tools import (
    CHECKLIST_WRITE_TOOLS,
    add_checklist,
    add_checklist_item,
    toggle_checklist_item,
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
    session.execute = AsyncMock()
    return session


def _make_async_ctx(session):
    """Wrap a mock session as an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _scalar_result(value):
    """Create a mock result where scalar_one_or_none returns value."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_task(task_uuid, project_id, task_key="TST-1", title="Test Task", status_name="Todo"):
    """Create a mock Task object and associated TaskStatus."""
    task_obj = MagicMock()
    task_obj.id = task_uuid
    task_obj.project_id = project_id
    task_obj.task_key = task_key
    task_obj.title = title
    task_obj.task_status_id = uuid4()

    status_obj = MagicMock()
    status_obj.id = task_obj.task_status_id
    status_obj.name = status_name

    return task_obj, status_obj


# ---------------------------------------------------------------------------
# Registry test
# ---------------------------------------------------------------------------


class TestChecklistWriteToolsRegistry:
    def test_has_3_tools(self):
        assert len(CHECKLIST_WRITE_TOOLS) == 3

    def test_tool_names(self):
        names = {t.name for t in CHECKLIST_WRITE_TOOLS}
        assert names == {"add_checklist", "add_checklist_item", "toggle_checklist_item"}


# ---------------------------------------------------------------------------
# add_checklist tests
# ---------------------------------------------------------------------------


class TestAddChecklist:
    @patch("app.ai.agent.tools.checklist_write_tools.interrupt")
    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_add_checklist_to_task(self, mock_tool_session, mock_interrupt):
        """Happy path: add a checklist to a task."""
        proj_id = str(uuid4())
        task_uuid = uuid4()
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        task_obj, status_obj = _mock_task(task_uuid, UUID(proj_id))

        # Pre-interrupt session:
        # 1. _resolve_task: task_key match -> returns task_uuid
        # 2. select(Task) -> task_obj
        # 3. select(TaskStatus) -> status_obj
        pre_session = _mock_db_session()
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),  # _resolve_task task_key match
            _scalar_result(task_obj),  # Task select
            _scalar_result(status_obj),  # TaskStatus select
        ]

        # RBAC re-check + write combined session
        combined_session = _mock_db_session()
        combined_session.execute.side_effect = [
            _scalar_result(MagicMock()),  # RBAC membership check
            _scalar_result(task_obj),  # re-load task
            _scalar_result(None),  # no existing checklists (rank query)
        ]

        mock_tool_session.side_effect = [
            _make_async_ctx(pre_session),
            _make_async_ctx(combined_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await add_checklist.ainvoke(
            {
                "task": "TST-1",
                "title": "QA Steps",
            }
        )

        assert "Added checklist" in result
        assert "QA Steps" in result
        assert "TST-1" in result
        mock_interrupt.assert_called_once()
        combined_session.add.assert_called_once()
        _clear()

    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_add_checklist_done_task_rejected(self, mock_tool_session):
        """Cannot add checklist to a task in Done status."""
        proj_id = str(uuid4())
        task_uuid = uuid4()

        _setup_context(accessible_project_ids=[proj_id])

        task_obj, status_obj = _mock_task(task_uuid, UUID(proj_id), status_name="Done")

        pre_session = _mock_db_session()
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),  # _resolve_task task_key match
            _scalar_result(task_obj),  # Task select
            _scalar_result(status_obj),  # TaskStatus select (Done)
        ]

        mock_tool_session.return_value = _make_async_ctx(pre_session)

        result = await add_checklist.ainvoke(
            {
                "task": "TST-1",
                "title": "QA Steps",
            }
        )

        assert "Done" in result
        assert "Error" in result
        _clear()

    async def test_add_checklist_rbac_denied(self):
        """Viewer cannot add checklist -- project not in accessible list."""
        _setup_context(accessible_project_ids=[])  # no access

        result = await add_checklist.ainvoke(
            {
                "task": str(uuid4()),
                "title": "QA Steps",
            }
        )

        assert "No task found" in result
        _clear()


# ---------------------------------------------------------------------------
# add_checklist_item tests
# ---------------------------------------------------------------------------


class TestAddChecklistItem:
    @patch("app.ai.agent.tools.checklist_write_tools.interrupt")
    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_add_item_to_checklist(self, mock_tool_session, mock_interrupt):
        """Happy path: add item to checklist, counter updated."""
        proj_id = str(uuid4())
        task_uuid = uuid4()
        checklist_id = uuid4()
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        task_obj, _ = _mock_task(task_uuid, UUID(proj_id))

        checklist_obj = MagicMock()
        checklist_obj.id = checklist_id
        checklist_obj.title = "QA Steps"
        checklist_obj.total_items = 2

        # Pre-interrupt session:
        # 1. _resolve_task: task_key match
        # 2. select(Task)
        # 3. select(Checklist) by title ILIKE
        pre_session = _mock_db_session()
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),  # _resolve_task
            _scalar_result(task_obj),  # Task select
            _scalar_result(checklist_obj),  # Checklist by title
        ]

        # RBAC re-check + write combined session
        combined_session = _mock_db_session()
        update_result = MagicMock()
        combined_session.execute.side_effect = [
            _scalar_result(MagicMock()),  # RBAC membership check
            _scalar_result(checklist_obj),  # re-load checklist
            _scalar_result(None),  # no existing items (rank query)
            update_result,  # update Task.checklist_total
        ]

        mock_tool_session.side_effect = [
            _make_async_ctx(pre_session),
            _make_async_ctx(combined_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await add_checklist_item.ainvoke(
            {
                "task": "TST-1",
                "checklist_title": "QA Steps",
                "item_title": "Step 1",
            }
        )

        assert "Added item" in result
        assert "Step 1" in result
        assert "QA Steps" in result
        mock_interrupt.assert_called_once()
        # Verify counter was incremented
        assert checklist_obj.total_items == 3
        _clear()

    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_add_item_checklist_not_found(self, mock_tool_session):
        """Error when checklist title doesn't match."""
        proj_id = str(uuid4())
        task_uuid = uuid4()

        _setup_context(accessible_project_ids=[proj_id])

        task_obj, _ = _mock_task(task_uuid, UUID(proj_id))

        # Pre-session:
        # 1. _resolve_task
        # 2. select(Task)
        # 3. select(Checklist) by title -> None
        # 4. select(Checklist.title) -> list of available
        pre_session = _mock_db_session()
        all_cl_result = MagicMock()
        all_cl_result.all.return_value = [("Dev Tasks",), ("QA Steps",)]
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),  # _resolve_task
            _scalar_result(task_obj),  # Task select
            _scalar_result(None),  # Checklist not found
            all_cl_result,  # available checklists
        ]

        mock_tool_session.return_value = _make_async_ctx(pre_session)

        result = await add_checklist_item.ainvoke(
            {
                "task": "TST-1",
                "checklist_title": "Nonexistent",
                "item_title": "Step 1",
            }
        )

        assert "No checklist matching" in result
        assert "Nonexistent" in result
        assert "Dev Tasks" in result
        _clear()


# ---------------------------------------------------------------------------
# toggle_checklist_item tests
# ---------------------------------------------------------------------------


class TestToggleChecklistItem:
    @patch("app.ai.agent.tools.checklist_write_tools.interrupt")
    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_toggle_item_complete(self, mock_tool_session, mock_interrupt):
        """Toggle item from incomplete to complete, counter incremented."""
        proj_id = str(uuid4())
        task_uuid = uuid4()
        checklist_id = uuid4()
        item_id = uuid4()
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        task_obj, _ = _mock_task(task_uuid, UUID(proj_id))

        checklist_obj = MagicMock()
        checklist_obj.id = checklist_id
        checklist_obj.title = "QA Steps"
        checklist_obj.completed_items = 0

        item_obj = MagicMock()
        item_obj.id = item_id
        item_obj.content = "Step 1"
        item_obj.is_done = False

        # Pre-interrupt session:
        # 1. _resolve_task
        # 2. select(Task)
        # 3. select(Checklist) by title
        # 4. select(ChecklistItem) by content
        pre_session = _mock_db_session()
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),
            _scalar_result(task_obj),
            _scalar_result(checklist_obj),
            _scalar_result(item_obj),
        ]

        # RBAC re-check + write combined session
        write_item_obj = MagicMock()
        write_item_obj.id = item_id
        write_item_obj.is_done = False

        def toggle_side_effect(user_id=None):
            write_item_obj.is_done = True

        write_item_obj.toggle = MagicMock(side_effect=toggle_side_effect)

        write_checklist_obj = MagicMock()
        write_checklist_obj.id = checklist_id
        write_checklist_obj.completed_items = 0

        combined_session = _mock_db_session()
        combined_session.execute.side_effect = [
            _scalar_result(MagicMock()),  # RBAC membership check
            _scalar_result(write_item_obj),  # re-load item
            _scalar_result(write_checklist_obj),  # re-load checklist
            MagicMock(),  # update Task.checklist_done
        ]

        mock_tool_session.side_effect = [
            _make_async_ctx(pre_session),
            _make_async_ctx(combined_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await toggle_checklist_item.ainvoke(
            {
                "task": "TST-1",
                "checklist_title": "QA Steps",
                "item_title": "Step 1",
            }
        )

        assert "complete" in result.lower()
        assert "Step 1" in result
        mock_interrupt.assert_called_once()
        # Verify counter was incremented
        assert write_checklist_obj.completed_items == 1
        write_item_obj.toggle.assert_called_once()
        _clear()

    @patch("app.ai.agent.tools.checklist_write_tools.interrupt")
    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_toggle_item_incomplete(self, mock_tool_session, mock_interrupt):
        """Toggle item from complete to incomplete, counter decremented."""
        proj_id = str(uuid4())
        task_uuid = uuid4()
        checklist_id = uuid4()
        item_id = uuid4()
        user_id = str(uuid4())

        _setup_context(
            user_id=user_id,
            accessible_project_ids=[proj_id],
        )

        task_obj, _ = _mock_task(task_uuid, UUID(proj_id))

        checklist_obj = MagicMock()
        checklist_obj.id = checklist_id
        checklist_obj.title = "QA Steps"
        checklist_obj.completed_items = 2

        item_obj = MagicMock()
        item_obj.id = item_id
        item_obj.content = "Step 1"
        item_obj.is_done = True  # currently complete

        # Pre-interrupt session
        pre_session = _mock_db_session()
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),
            _scalar_result(task_obj),
            _scalar_result(checklist_obj),
            _scalar_result(item_obj),
        ]

        # RBAC re-check + write combined session
        write_item_obj = MagicMock()
        write_item_obj.id = item_id
        write_item_obj.is_done = True

        def toggle_side_effect(user_id=None):
            write_item_obj.is_done = False

        write_item_obj.toggle = MagicMock(side_effect=toggle_side_effect)

        write_checklist_obj = MagicMock()
        write_checklist_obj.id = checklist_id
        write_checklist_obj.completed_items = 2

        combined_session = _mock_db_session()
        combined_session.execute.side_effect = [
            _scalar_result(MagicMock()),  # RBAC membership check
            _scalar_result(write_item_obj),  # re-load item
            _scalar_result(write_checklist_obj),  # re-load checklist
            MagicMock(),  # update Task.checklist_done
        ]

        mock_tool_session.side_effect = [
            _make_async_ctx(pre_session),
            _make_async_ctx(combined_session),
        ]
        mock_interrupt.return_value = {"approved": True}

        result = await toggle_checklist_item.ainvoke(
            {
                "task": "TST-1",
                "checklist_title": "QA Steps",
                "item_title": "Step 1",
            }
        )

        assert "incomplete" in result.lower()
        assert "Step 1" in result
        # Verify counter was decremented
        assert write_checklist_obj.completed_items == 1
        _clear()

    @patch("app.ai.agent.tools.checklist_write_tools._get_tool_session")
    async def test_toggle_item_not_found(self, mock_tool_session):
        """Error when item title doesn't match any item in the checklist."""
        proj_id = str(uuid4())
        task_uuid = uuid4()
        checklist_id = uuid4()

        _setup_context(accessible_project_ids=[proj_id])

        task_obj, _ = _mock_task(task_uuid, UUID(proj_id))

        checklist_obj = MagicMock()
        checklist_obj.id = checklist_id
        checklist_obj.title = "QA Steps"

        # Pre-session:
        # 1. _resolve_task
        # 2. select(Task)
        # 3. select(Checklist)
        # 4. select(ChecklistItem) -> None
        # 5. select(ChecklistItem.content) -> available items
        pre_session = _mock_db_session()
        all_items_result = MagicMock()
        all_items_result.all.return_value = [("Step A",), ("Step B",)]
        pre_session.execute.side_effect = [
            _scalar_result(task_uuid),
            _scalar_result(task_obj),
            _scalar_result(checklist_obj),
            _scalar_result(None),  # item not found
            all_items_result,  # available items
        ]

        mock_tool_session.return_value = _make_async_ctx(pre_session)

        result = await toggle_checklist_item.ainvoke(
            {
                "task": "TST-1",
                "checklist_title": "QA Steps",
                "item_title": "Nonexistent Step",
            }
        )

        assert "No item matching" in result
        assert "Nonexistent Step" in result
        assert "Step A" in result
        _clear()
