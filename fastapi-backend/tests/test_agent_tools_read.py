"""Unit tests for read-only Blair AI agent tools (app.ai.agent.tools_read).

Tests cover:
- set_tool_context / clear_tool_context lifecycle
- _check_app_access / _check_project_access RBAC helpers
- _resolve_application / _resolve_project fuzzy name resolvers
- _truncate output limiter
- _format_date with date, datetime, None
- _relative_time relative time formatting
- _days_overdue positive result, None when not overdue
- create_read_tools returns list of 12 tools
- query_knowledge — access denied on invalid app_id, name resolution
- sql_query — wraps sql_query_tool
- get_projects — access denied, name resolution, returns markdown table
- get_tasks — access denied, name resolution on invalid project_id
- get_task_detail — RBAC check, not found case
- get_applications — lists accessible applications
- browse_knowledge — lists documents and folders in a scope
- request_clarification — calls interrupt()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.ai.agent.tools_read import (
    _check_app_access,
    _check_project_access,
    _days_overdue,
    _format_date,
    _relative_time,
    _resolve_application,
    _resolve_project,
    _tool_context,
    _truncate,
    clear_tool_context,
    create_read_tools,
    set_tool_context,
)
from app.ai.agent_tools import MAX_TOOL_OUTPUT_CHARS


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


# ---------------------------------------------------------------------------
# Context lifecycle
# ---------------------------------------------------------------------------

class TestToolContext:

    def test_set_tool_context_populates_dict(self):
        _clear()
        uid = str(uuid4())
        factory = MagicMock()
        registry = MagicMock()

        set_tool_context(
            user_id=uid,
            accessible_app_ids=["a1"],
            accessible_project_ids=["p1"],
            db_session_factory=factory,
            provider_registry=registry,
        )

        assert _tool_context["user_id"] == uid
        assert _tool_context["accessible_app_ids"] == ["a1"]
        assert _tool_context["accessible_project_ids"] == ["p1"]
        assert _tool_context["db_session_factory"] is factory
        assert _tool_context["provider_registry"] is registry
        _clear()

    def test_clear_tool_context_empties_dict(self):
        _setup_context()
        assert len(_tool_context) > 0
        clear_tool_context()
        assert len(_tool_context) == 0


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

class TestRBACHelpers:

    def test_check_app_access_granted(self):
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id])
        assert _check_app_access(app_id) is True
        _clear()

    def test_check_app_access_denied(self):
        _setup_context(accessible_app_ids=[str(uuid4())])
        assert _check_app_access(str(uuid4())) is False
        _clear()

    def test_check_project_access_granted(self):
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])
        assert _check_project_access(proj_id) is True
        _clear()

    def test_check_project_access_denied(self):
        _setup_context(accessible_project_ids=[])
        assert _check_project_access(str(uuid4())) is False
        _clear()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

class TestTruncate:

    def test_short_text_unchanged(self):
        text = "hello"
        assert _truncate(text) == text

    def test_long_text_truncated(self):
        text = "x" * (MAX_TOOL_OUTPUT_CHARS + 100)
        result = _truncate(text)
        assert len(result) < len(text)
        assert result.endswith("... (output truncated)")

    def test_exact_length_not_truncated(self):
        text = "y" * MAX_TOOL_OUTPUT_CHARS
        assert _truncate(text) == text


class TestFormatDate:

    def test_none_returns_dash(self):
        assert _format_date(None) == "\u2014"

    def test_date_returns_iso(self):
        d = date(2026, 1, 15)
        assert _format_date(d) == "2026-01-15"

    def test_datetime_returns_formatted(self):
        dt = datetime(2026, 3, 1, 14, 30, tzinfo=timezone.utc)
        assert _format_date(dt) == "2026-03-01 14:30"


class TestDaysOverdue:

    def test_none_due_date_returns_none(self):
        assert _days_overdue(None) is None

    def test_future_date_returns_none(self):
        future = date(2099, 12, 31)
        assert _days_overdue(future) is None

    def test_past_date_returns_positive_int(self):
        past = date(2020, 1, 1)
        result = _days_overdue(past)
        assert result is not None
        assert result > 0


# ---------------------------------------------------------------------------
# create_read_tools factory
# ---------------------------------------------------------------------------

class TestCreateReadTools:

    def test_returns_12_tools(self):
        factory = MagicMock()
        registry = MagicMock()
        tools = create_read_tools(factory, registry)
        assert len(tools) == 12

    def test_tool_names(self):
        tools = create_read_tools(MagicMock(), MagicMock())
        names = {t.name for t in tools}
        expected = {
            "query_knowledge",
            "sql_query",
            "get_projects",
            "get_tasks",
            "get_task_detail",
            "get_project_status",
            "get_overdue_tasks",
            "get_team_members",
            "understand_image",
            "request_clarification",
            "get_applications",
            "browse_knowledge",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# query_knowledge tool
# ---------------------------------------------------------------------------

class TestQueryKnowledge:

    async def test_access_denied_on_invalid_app_id(self):
        """query_knowledge returns not-found when app_id is not accessible."""
        app_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        ctx = _setup_context(accessible_app_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        query_knowledge = tools[0]

        result = await query_knowledge.ainvoke(
            {"query": "test", "application_id": app_id}
        )
        assert "No application found" in result
        _clear()

    async def test_access_denied_on_invalid_project_id(self):
        """query_knowledge returns not-found when project_id is not accessible."""
        proj_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        query_knowledge = tools[0]

        result = await query_knowledge.ainvoke(
            {"query": "test", "project_id": proj_id}
        )
        assert "No project found" in result
        _clear()

    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_pushes_sources_to_accumulator(self, mock_rag):
        """query_knowledge pushes structured sources into the ContextVar accumulator."""
        from app.ai.agent.source_references import (
            get_accumulated_sources,
            reset_source_accumulator,
        )
        from app.ai.agent_tools import ToolResult

        app_id = str(uuid4())
        doc_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        mock_rag.return_value = ToolResult(
            success=True,
            data="[1] Test Doc [Intro] (score: 0.9500, source: semantic)\nhello world\n",
            metadata={
                "result_count": 1,
                "documents": [
                    {
                        "document_id": doc_id,
                        "title": "Test Doc",
                        "score": 0.95,
                        "source": "semantic",
                        "heading_context": "Intro",
                        "chunk_text": "hello world",
                        "application_id": app_id,
                        "chunk_index": 0,
                    }
                ],
            },
        )

        _setup_context(accessible_app_ids=[app_id])
        tools = create_read_tools(mock_db_factory, MagicMock())
        query_knowledge = tools[0]

        reset_source_accumulator()
        await query_knowledge.ainvoke({"query": "test"})

        sources = get_accumulated_sources()
        assert len(sources) == 1
        assert sources[0]["document_id"] == doc_id
        assert sources[0]["application_id"] == app_id
        assert sources[0]["heading_context"] == "Intro"
        assert sources[0]["chunk_text"] == "hello world"
        _clear()


# ---------------------------------------------------------------------------
# sql_query tool
# ---------------------------------------------------------------------------

class TestSqlQueryTool:

    @patch("app.ai.agent_tools.sql_query_tool", new_callable=AsyncMock)
    async def test_sql_query_wraps_sql_query_tool(self, mock_sql):
        """sql_query delegates to agent_tools.sql_query_tool."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        uid = str(uuid4())
        _setup_context(user_id=uid)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = "col1\n---\nval1"
        mock_sql.return_value = mock_result

        tools = create_read_tools(mock_db_factory, MagicMock())
        sql_query_fn = tools[1]

        result = await sql_query_fn.ainvoke(
            {"question": "How many users?"}
        )

        mock_sql.assert_awaited_once()
        assert "val1" in result
        _clear()


# ---------------------------------------------------------------------------
# get_projects tool
# ---------------------------------------------------------------------------

class TestGetProjects:

    async def test_access_denied_on_invalid_app_id(self):
        """get_projects returns not-found when app_id is not accessible."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_projects = tools[2]

        result = await get_projects.ainvoke(
            {"application_id": str(uuid4())}
        )
        assert "No application found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_tasks tool
# ---------------------------------------------------------------------------

class TestGetTasks:

    async def test_access_denied_on_invalid_project_id(self):
        """get_tasks returns not-found when project_id is not accessible."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_tasks = tools[3]

        result = await get_tasks.ainvoke(
            {"project_id": str(uuid4())}
        )
        assert "No project found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_task_detail tool
# ---------------------------------------------------------------------------

class TestGetTaskDetail:

    async def test_task_not_found(self):
        """get_task_detail returns not-found message for missing task."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context()
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_task_detail = tools[4]

        task_id = str(uuid4())
        result = await get_task_detail.ainvoke({"task_id": task_id})
        assert "Task not found" in result
        _clear()

    async def test_rbac_denied(self):
        """get_task_detail returns not-found when project not accessible (avoids leaking existence)."""
        mock_task = MagicMock()
        mock_task.project_id = uuid4()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        # Set up context with NO accessible projects
        _setup_context(accessible_project_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_task_detail = tools[4]

        result = await get_task_detail.ainvoke(
            {"task_id": str(uuid4())}
        )
        assert "Task not found" in result
        _clear()


# ---------------------------------------------------------------------------
# request_clarification tool
# ---------------------------------------------------------------------------

class TestRequestClarification:

    @patch("app.ai.agent.tools_read.interrupt")
    async def test_calls_interrupt_and_returns_answer(self, mock_interrupt):
        """request_clarification calls interrupt() and extracts the answer."""
        mock_interrupt.return_value = {"answer": "Option B"}

        tools = create_read_tools(MagicMock(), MagicMock())
        request_clarification = tools[9]

        _setup_context()
        result = await request_clarification.ainvoke(
            {"question": "Which option?", "options": ["A", "B"]}
        )

        mock_interrupt.assert_called_once()
        payload = mock_interrupt.call_args[0][0]
        assert payload["type"] == "clarification"
        assert payload["question"] == "Which option?"
        assert result == "Option B"
        _clear()

    @patch("app.ai.agent.tools_read.interrupt")
    async def test_returns_string_response_as_fallback(self, mock_interrupt):
        """request_clarification handles plain string interrupt responses."""
        mock_interrupt.return_value = "plain text answer"

        _setup_context()
        tools = create_read_tools(MagicMock(), MagicMock())
        request_clarification = tools[9]

        result = await request_clarification.ainvoke(
            {"question": "What?"}
        )
        assert result == "plain text answer"
        _clear()


# ---------------------------------------------------------------------------
# get_project_status tool
# ---------------------------------------------------------------------------

class TestGetProjectStatus:

    async def test_access_denied(self):
        """get_project_status returns not-found when project is not accessible."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_project_status = tools[5]

        result = await get_project_status.ainvoke(
            {"project_id": str(uuid4())}
        )
        assert "No project found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_overdue_tasks tool
# ---------------------------------------------------------------------------

class TestGetOverdueTasks:

    async def test_returns_no_accessible_projects_message(self):
        """get_overdue_tasks returns message when user has no accessible projects."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_overdue_tasks = tools[6]

        result = await get_overdue_tasks.ainvoke({})
        assert "no accessible projects" in result.lower()
        _clear()

    async def test_access_denied_for_application_scope(self):
        """get_overdue_tasks returns not-found for inaccessible application."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[], accessible_project_ids=[str(uuid4())])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_overdue_tasks = tools[6]

        result = await get_overdue_tasks.ainvoke(
            {"application_id": str(uuid4())}
        )
        assert "No application found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_team_members tool
# ---------------------------------------------------------------------------

class TestGetTeamMembers:

    async def test_access_denied(self):
        """get_team_members returns not-found when app is not accessible."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_team_members = tools[7]

        result = await get_team_members.ainvoke(
            {"application_id": str(uuid4())}
        )
        assert "No application found" in result
        _clear()


# ---------------------------------------------------------------------------
# understand_image tool
# ---------------------------------------------------------------------------

class TestUnderstandImage:

    async def test_attachment_not_found(self):
        """understand_image returns not-found when attachment doesn't exist."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context()
        tools = create_read_tools(mock_db_factory, MagicMock())
        understand_image = tools[8]

        att_id = str(uuid4())
        result = await understand_image.ainvoke({"attachment_id": att_id})
        assert "not found" in result.lower()
        _clear()

    async def test_returns_result_for_image(self):
        """understand_image returns vision analysis result when given a valid image attachment."""
        att_id = uuid4()
        task_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "diagram.png"
        mock_attachment.minio_bucket = "uploads"
        mock_attachment.minio_key = "abc/diagram.png"

        mock_session = AsyncMock()

        # execute() is called twice in the first db session:
        # 1st: attachment lookup, 2nd: task.project_id RBAC lookup
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = project_id
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        call_count = 0

        @asynccontextmanager
        async def mock_db_factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: attachment lookup + RBAC check
                yield mock_session
            else:
                # Second call: vision provider lookup
                yield AsyncMock()

        mock_registry = MagicMock()
        mock_vision_provider = AsyncMock()
        mock_vision_provider.describe_image = AsyncMock(
            return_value="A flowchart showing the deployment process."
        )
        mock_registry.get_vision_provider = AsyncMock(
            return_value=(mock_vision_provider, "gpt-4o")
        )

        _setup_context(
            user_id=str(uuid4()),
            accessible_project_ids=[str(project_id)],
        )
        tools = create_read_tools(mock_db_factory, mock_registry)
        understand_image = tools[8]

        with patch("app.services.minio_service.MinIOService") as mock_minio_cls:
            mock_minio_svc = MagicMock()
            mock_minio_svc.download_file.return_value = b"\x89PNG\x00"
            mock_minio_cls.return_value = mock_minio_svc

            result = await understand_image.ainvoke(
                {"attachment_id": str(att_id), "question": "What is this diagram?"}
            )

        assert "flowchart" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# get_projects — happy-path data formatting
# ---------------------------------------------------------------------------

class TestGetProjectsHappyPath:

    async def test_returns_markdown_table_with_project_data(self):
        """get_projects returns a markdown table with project names and completion."""
        app_id = str(uuid4())
        proj1_id = uuid4()
        proj2_id = uuid4()

        # Create mock project objects
        mock_proj1 = MagicMock()
        mock_proj1.id = proj1_id
        mock_proj1.name = "Alpha Project"
        mock_proj1.archived_at = None
        mock_derived1 = MagicMock()
        mock_derived1.name = "In Progress"
        mock_proj1.derived_status = mock_derived1

        mock_proj2 = MagicMock()
        mock_proj2.id = proj2_id
        mock_proj2.name = "Beta Project"
        mock_proj2.archived_at = None
        mock_derived2 = MagicMock()
        mock_derived2.name = "Done"
        mock_proj2.derived_status = mock_derived2

        # Create mock aggregation data
        mock_agg1 = MagicMock()
        mock_agg1.project_id = proj1_id
        mock_agg1.total_tasks = 10
        mock_agg1.done_tasks = 3

        mock_agg2 = MagicMock()
        mock_agg2.project_id = proj2_id
        mock_agg2.total_tasks = 5
        mock_agg2.done_tasks = 5

        mock_session = AsyncMock()

        # First execute: project query (scalars().unique().all())
        proj_result = MagicMock()
        proj_scalars = MagicMock()
        proj_unique = MagicMock()
        proj_unique.all.return_value = [mock_proj1, mock_proj2]
        proj_scalars.unique.return_value = proj_unique
        proj_result.scalars.return_value = proj_scalars

        # Second execute: aggregation query (scalars().all())
        agg_result = MagicMock()
        agg_scalars = MagicMock()
        agg_scalars.all.return_value = [mock_agg1, mock_agg2]
        agg_result.scalars.return_value = agg_scalars

        mock_session.execute.side_effect = [proj_result, agg_result]

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[app_id])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_projects = tools[2]

        result = await get_projects.ainvoke({"application_id": app_id})

        # Verify markdown table structure
        assert "| Project | Status | Tasks (done/total) | % Complete |" in result
        assert "Alpha Project" in result
        assert "Beta Project" in result
        assert "In Progress" in result
        assert "3/10" in result
        assert "30%" in result
        assert "5/5" in result
        assert "100%" in result
        assert "2 project(s) found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_task_detail — happy-path data formatting
# ---------------------------------------------------------------------------

class TestGetTaskDetailHappyPath:

    async def test_returns_formatted_task_with_checklists_and_comments(self):
        """get_task_detail returns a formatted task with title, status, checklists."""
        task_id = str(uuid4())
        proj_id = uuid4()

        # Mock the RBAC check (project_id lookup)
        mock_session = AsyncMock()

        # First execute: project_id lookup for RBAC
        proj_check_result = MagicMock()
        proj_check_result.scalar_one_or_none.return_value = proj_id

        # Second execute: full task load with eager loading
        mock_task = MagicMock()
        mock_task.task_key = "PROJ-42"
        mock_task.title = "Implement Search"
        mock_task.project_id = proj_id
        mock_task.priority = "high"
        mock_task.task_type = "story"
        mock_task.due_date = None
        mock_task.story_points = 5
        mock_task.description = "Add full-text search to the knowledge base"
        mock_task.created_at = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
        mock_task.updated_at = datetime(2026, 2, 20, 14, 30, tzinfo=timezone.utc)

        # Mock status
        mock_status = MagicMock()
        mock_status.name = "In Progress"
        mock_task.task_status = mock_status

        # Mock assignee
        mock_assignee = MagicMock()
        mock_assignee.display_name = "Alice Dev"
        mock_task.assignee = mock_assignee

        # Mock reporter
        mock_reporter = MagicMock()
        mock_reporter.display_name = "Bob PM"
        mock_task.reporter = mock_reporter

        # Mock project
        mock_project = MagicMock()
        mock_project.name = "Search Project"
        mock_task.project = mock_project

        # Mock checklists with items
        mock_item1 = MagicMock()
        mock_item1.is_done = True
        mock_item1.content = "Write unit tests"

        mock_item2 = MagicMock()
        mock_item2.is_done = False
        mock_item2.content = "Add integration tests"

        mock_checklist = MagicMock()
        mock_checklist.title = "Testing Checklist"
        mock_checklist.completed_items = 1
        mock_checklist.total_items = 2
        mock_checklist.items = [mock_item1, mock_item2]

        mock_task.checklists = [mock_checklist]

        # Mock comments
        mock_comment_author = MagicMock()
        mock_comment_author.display_name = "Carol"
        mock_comment = MagicMock()
        mock_comment.author = mock_comment_author
        mock_comment.body_text = "Looks good so far!"
        mock_comment.created_at = datetime(2026, 2, 15, 9, 0, tzinfo=timezone.utc)
        mock_comment.is_deleted = False

        mock_task.comments = [mock_comment]

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task

        mock_session.execute.side_effect = [proj_check_result, task_result]

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(proj_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_task_detail = tools[4]

        result = await get_task_detail.ainvoke({"task_id": task_id})

        # Verify task header and metadata
        assert "PROJ-42" in result
        assert "Implement Search" in result
        assert "In Progress" in result
        assert "high" in result
        assert "Alice Dev" in result
        assert "Bob PM" in result
        assert "Search Project" in result
        assert "5" in result  # story points

        # Verify description
        assert "Add full-text search" in result

        # Verify checklist
        assert "Testing Checklist" in result
        assert "[x] Write unit tests" in result
        assert "[ ] Add integration tests" in result

        # Verify comments
        assert "Carol" in result
        assert "Looks good so far!" in result
        _clear()


# ---------------------------------------------------------------------------
# _relative_time helper
# ---------------------------------------------------------------------------

class TestRelativeTime:

    def test_none_returns_unknown(self):
        assert _relative_time(None) == "unknown"

    def test_today(self):
        now = datetime.now(timezone.utc)
        assert _relative_time(now) == "today"

    def test_yesterday(self):
        from datetime import timedelta
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert _relative_time(yesterday) == "yesterday"

    def test_days_ago(self):
        from datetime import timedelta
        three_days = datetime.now(timezone.utc) - timedelta(days=3)
        assert _relative_time(three_days) == "3 days ago"

    def test_weeks_ago(self):
        from datetime import timedelta
        two_weeks = datetime.now(timezone.utc) - timedelta(days=14)
        assert _relative_time(two_weeks) == "2 weeks ago"

    def test_old_date_falls_back_to_format_date(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(days=60)
        result = _relative_time(old)
        # Should fall back to _format_date which returns YYYY-MM-DD HH:MM
        assert len(result) > 0
        assert result != "unknown"


# ---------------------------------------------------------------------------
# _resolve_application tests
# ---------------------------------------------------------------------------

class TestResolveApplication:

    async def test_valid_uuid_with_access(self):
        """Resolves immediately when identifier is a valid UUID with access."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id])
        db = AsyncMock()

        resolved, error = await _resolve_application(app_id, db)
        assert resolved == app_id
        assert error is None
        # No DB query needed for UUID fast path
        db.execute.assert_not_awaited()
        _clear()

    async def test_valid_uuid_without_access(self):
        """Returns not-found for valid UUID without access (avoids leaking existence)."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[])
        db = AsyncMock()

        resolved, error = await _resolve_application(app_id, db)
        assert resolved is None
        assert "No application found" in error
        _clear()

    async def test_name_single_match(self):
        """Resolves name to UUID when exactly one match."""
        app_id = uuid4()
        _setup_context(accessible_app_ids=[str(app_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "PMS Application"
        mock_result.all.return_value = [mock_row]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("PMS", db)
        assert resolved == str(app_id)
        assert error is None
        _clear()

    async def test_name_no_match(self):
        """Returns error when no applications match the name."""
        app_id = uuid4()
        _setup_context(accessible_app_ids=[str(app_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("NonExistent", db)
        assert resolved is None
        assert "No application found" in error
        _clear()

    async def test_name_multiple_matches(self):
        """Returns disambiguation error when multiple apps match."""
        app1 = uuid4()
        app2 = uuid4()
        _setup_context(accessible_app_ids=[str(app1), str(app2)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row1 = MagicMock()
        mock_row1.id = app1
        mock_row1.name = "PM System"
        mock_row2 = MagicMock()
        mock_row2.id = app2
        mock_row2.name = "PM Suite"
        mock_result.all.return_value = [mock_row1, mock_row2]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("PM", db)
        assert resolved is None
        assert "Multiple applications" in error
        assert "PM System" in error
        assert "PM Suite" in error
        _clear()

    async def test_no_accessible_apps(self):
        """Returns error when user has no accessible apps."""
        _setup_context(accessible_app_ids=[])
        db = AsyncMock()

        resolved, error = await _resolve_application("anything", db)
        assert resolved is None
        assert "No application found" in error
        _clear()


# ---------------------------------------------------------------------------
# _resolve_project tests
# ---------------------------------------------------------------------------

class TestResolveProject:

    async def test_valid_uuid_with_access(self):
        """Resolves immediately when identifier is a valid UUID with access."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])
        db = AsyncMock()

        resolved, error = await _resolve_project(proj_id, db)
        assert resolved == proj_id
        assert error is None
        db.execute.assert_not_awaited()
        _clear()

    async def test_valid_uuid_without_access(self):
        """Returns not-found for valid UUID without access (avoids leaking existence)."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        db = AsyncMock()

        resolved, error = await _resolve_project(proj_id, db)
        assert resolved is None
        assert "No project found" in error
        _clear()

    async def test_name_single_match(self):
        """Resolves name to UUID when exactly one match."""
        proj_id = uuid4()
        _setup_context(accessible_project_ids=[str(proj_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = proj_id
        mock_row.name = "Backend API"
        mock_result.all.return_value = [mock_row]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_project("Backend", db)
        assert resolved == str(proj_id)
        assert error is None
        _clear()

    async def test_name_no_match(self):
        """Returns error when no projects match the name."""
        proj_id = uuid4()
        _setup_context(accessible_project_ids=[str(proj_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        resolved, error = await _resolve_project("NonExistent", db)
        assert resolved is None
        assert "No project found" in error
        _clear()

    async def test_name_multiple_matches(self):
        """Returns disambiguation error when multiple projects match."""
        proj1 = uuid4()
        proj2 = uuid4()
        _setup_context(accessible_project_ids=[str(proj1), str(proj2)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row1 = MagicMock()
        mock_row1.id = proj1
        mock_row1.name = "API v1"
        mock_row2 = MagicMock()
        mock_row2.id = proj2
        mock_row2.name = "API v2"
        mock_result.all.return_value = [mock_row1, mock_row2]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_project("API", db)
        assert resolved is None
        assert "Multiple projects" in error
        assert "API v1" in error
        assert "API v2" in error
        _clear()


# ---------------------------------------------------------------------------
# get_applications tool
# ---------------------------------------------------------------------------

class TestGetApplications:

    async def test_no_accessible_apps(self):
        """get_applications returns message when user has no apps."""
        _setup_context(accessible_app_ids=[])
        tools = create_read_tools(MagicMock(), MagicMock())
        get_applications = tools[10]

        result = await get_applications.ainvoke({})
        assert "no accessible applications" in result.lower()
        _clear()

    async def test_lists_applications_with_role(self):
        """get_applications returns table with app names and roles."""
        app_id = uuid4()
        user_id = str(uuid4())

        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.name = "My App"
        mock_app.description = "Test application"
        mock_app.owner_id = uuid4()  # Different from user → role = member

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = [mock_app]
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            user_id=user_id,
            accessible_app_ids=[str(app_id)],
        )
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_applications = tools[10]

        result = await get_applications.ainvoke({})
        assert "My App" in result
        assert "member" in result
        assert "1 application(s)" in result
        _clear()


# ---------------------------------------------------------------------------
# browse_knowledge tool
# ---------------------------------------------------------------------------

class TestBrowseKnowledge:

    async def test_invalid_scope(self):
        """browse_knowledge rejects invalid scope values."""
        _setup_context()
        tools = create_read_tools(MagicMock(), MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({"scope": "global"})
        assert "scope must be" in result.lower()
        _clear()

    async def test_application_scope_missing_scope_id(self):
        """browse_knowledge requires scope_id for application scope."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context()
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({"scope": "application"})
        assert "scope_id is required" in result.lower()
        _clear()

    async def test_access_denied_for_inaccessible_app(self):
        """browse_knowledge returns not-found for inaccessible application."""
        app_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[])
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({
            "scope": "application",
            "scope_id": app_id,
        })
        assert "No application found" in result
        _clear()

    async def test_name_resolution_for_scope_id(self):
        """browse_knowledge resolves application name to UUID."""
        app_id = uuid4()
        mock_session = AsyncMock()

        # Resolver query returns 1 match
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "PMS Application"
        resolver_result.all.return_value = [mock_row]

        # App name query
        app_name_result = MagicMock()
        app_name_result.scalar_one_or_none.return_value = "PMS Application"

        # Folder query (empty)
        folder_result = MagicMock()
        folder_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        # Doc query (empty)
        doc_result = MagicMock()
        doc_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        # Total docs count
        total_docs_result = MagicMock()
        total_docs_result.scalar.return_value = 0

        # Total folders count
        total_folders_result = MagicMock()
        total_folders_result.scalar.return_value = 0

        mock_session.execute = AsyncMock(side_effect=[
            resolver_result,
            app_name_result,
            folder_result,
            doc_result,
            total_docs_result,
            total_folders_result,
        ])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[str(app_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({
            "scope": "application",
            "scope_id": "PMS",
        })
        assert "PMS Application" in result
        assert "0 document(s)" in result
        _clear()

    async def test_personal_scope(self):
        """browse_knowledge lists personal documents."""
        user_id = str(uuid4())
        mock_session = AsyncMock()

        # Folder query (empty)
        folder_result = MagicMock()
        folder_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        # Doc query (empty)
        doc_result = MagicMock()
        doc_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        # Total docs count
        total_docs_result = MagicMock()
        total_docs_result.scalar.return_value = 0

        # Total folders count
        total_folders_result = MagicMock()
        total_folders_result.scalar.return_value = 0

        mock_session.execute = AsyncMock(side_effect=[
            folder_result,
            doc_result,
            total_docs_result,
            total_folders_result,
        ])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(user_id=user_id)
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({"scope": "personal"})
        assert "Personal" in result
        _clear()


# ---------------------------------------------------------------------------
# get_projects with name resolution
# ---------------------------------------------------------------------------

class TestGetProjectsNameResolution:

    async def test_resolves_app_by_name(self):
        """get_projects resolves application name and returns projects."""
        app_id = uuid4()
        proj_id = uuid4()

        # Resolver query returns 1 match
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "My App"
        resolver_result.all.return_value = [mock_row]

        # Project query
        mock_proj = MagicMock()
        mock_proj.id = proj_id
        mock_proj.name = "Alpha"
        mock_proj.archived_at = None
        mock_derived = MagicMock()
        mock_derived.name = "In Progress"
        mock_proj.derived_status = mock_derived

        proj_result = MagicMock()
        proj_scalars = MagicMock()
        proj_unique = MagicMock()
        proj_unique.all.return_value = [mock_proj]
        proj_scalars.unique.return_value = proj_unique
        proj_result.scalars.return_value = proj_scalars

        # Aggregation query
        mock_agg = MagicMock()
        mock_agg.project_id = proj_id
        mock_agg.total_tasks = 5
        mock_agg.done_tasks = 2
        agg_result = MagicMock()
        agg_scalars = MagicMock()
        agg_scalars.all.return_value = [mock_agg]
        agg_result.scalars.return_value = agg_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[
            resolver_result,
            proj_result,
            agg_result,
        ])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[str(app_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_projects = tools[2]

        result = await get_projects.ainvoke({"application_id": "My App"})
        assert "Alpha" in result
        assert "2/5" in result
        _clear()


# ---------------------------------------------------------------------------
# get_tasks with name resolution
# ---------------------------------------------------------------------------

class TestGetTasksNameResolution:

    async def test_resolves_project_by_name(self):
        """get_tasks resolves project name and returns tasks."""
        proj_id = uuid4()
        task_id = uuid4()

        # Resolver query returns 1 match
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = proj_id
        mock_row.name = "Backend API"
        resolver_result.all.return_value = [mock_row]

        # Task query
        mock_task = MagicMock()
        mock_task.task_key = "BE-1"
        mock_task.title = "Fix bug"
        mock_task.priority = "high"
        mock_task.due_date = None
        mock_status = MagicMock()
        mock_status.name = "Todo"
        mock_status.category = "Todo"
        mock_task.task_status = mock_status
        mock_task.assignee = None

        task_result = MagicMock()
        task_scalars = MagicMock()
        task_unique = MagicMock()
        task_unique.all.return_value = [mock_task]
        task_scalars.unique.return_value = task_unique
        task_result.scalars.return_value = task_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[
            resolver_result,
            task_result,
        ])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(proj_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_tasks = tools[3]

        result = await get_tasks.ainvoke({"project_id": "Backend"})
        assert "BE-1" in result
        assert "Fix bug" in result
        _clear()


# ---------------------------------------------------------------------------
# Resolver edge case tests (Round 1 review gaps)
# ---------------------------------------------------------------------------

class TestResolverEdgeCases:

    async def test_resolve_application_empty_string(self):
        """Empty string identifier is rejected."""
        _setup_context(accessible_app_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_application("", db)
        assert resolved is None
        assert "cannot be empty" in error
        _clear()

    async def test_resolve_project_empty_string(self):
        """Empty string identifier is rejected."""
        _setup_context(accessible_project_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_project("", db)
        assert resolved is None
        assert "cannot be empty" in error
        _clear()

    async def test_resolve_application_whitespace_only(self):
        """Whitespace-only identifier is rejected."""
        _setup_context(accessible_app_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_application("   ", db)
        assert resolved is None
        assert "cannot be empty" in error
        _clear()

    async def test_resolve_application_too_long(self):
        """Identifier exceeding 255 chars is rejected."""
        _setup_context(accessible_app_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_application("A" * 256, db)
        assert resolved is None
        assert "too long" in error
        _clear()

    async def test_resolve_project_too_long(self):
        """Identifier exceeding 255 chars is rejected."""
        _setup_context(accessible_project_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_project("A" * 256, db)
        assert resolved is None
        assert "too long" in error
        _clear()

    async def test_resolve_application_wildcard_escaped(self):
        """Percent and underscore are escaped before ILIKE query."""
        app_id = uuid4()
        _setup_context(accessible_app_ids=[str(app_id)])
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("test%100_app", db)
        assert resolved is None
        # Ensure the query was called (not short-circuited)
        db.execute.assert_awaited_once()
        _clear()

    async def test_resolve_project_no_accessible(self):
        """Returns error when user has no accessible projects (name path)."""
        _setup_context(accessible_project_ids=[])
        db = AsyncMock()
        resolved, error = await _resolve_project("anything", db)
        assert resolved is None
        assert "No project found" in error
        db.execute.assert_not_awaited()
        _clear()


# ---------------------------------------------------------------------------
# get_task_detail — invalid UUID
# ---------------------------------------------------------------------------

class TestGetTaskDetailInvalidUuid:

    async def test_invalid_uuid_returns_error(self):
        """get_task_detail returns user-friendly error for non-UUID task_id."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context()
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_task_detail = tools[4]

        result = await get_task_detail.ainvoke({"task_id": "not-a-uuid"})
        assert "not a valid task UUID" in result
        _clear()


# ---------------------------------------------------------------------------
# browse_knowledge — with folders and documents
# ---------------------------------------------------------------------------

class TestBrowseKnowledgeFormatting:

    async def test_with_folders_and_documents(self):
        """browse_knowledge formats folders and documents correctly."""
        app_id = uuid4()
        folder_id = uuid4()
        doc_id = uuid4()

        mock_session = AsyncMock()

        # Resolver query
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "Test App"
        resolver_result.all.return_value = [mock_row]

        # App name query
        app_name_result = MagicMock()
        app_name_result.scalar_one_or_none.return_value = "Test App"

        # Folder scope check (for folder_id validation)
        folder_check_result = MagicMock()
        mock_folder_check = MagicMock()
        mock_folder_check.id = folder_id
        folder_check_result.scalar_one_or_none.return_value = mock_folder_check

        # Folder query (1 subfolder)
        mock_subfolder = MagicMock()
        mock_subfolder.id = uuid4()
        mock_subfolder.name = "Architecture"
        folder_result = MagicMock()
        folder_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[mock_subfolder]))

        # Doc count per folder
        doc_count_result = MagicMock()
        doc_count_result.all.return_value = [(mock_subfolder.id, 3)]

        # Doc query (1 document)
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.title = "Setup Guide"
        mock_doc.updated_at = datetime.now(timezone.utc)
        doc_result = MagicMock()
        doc_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[mock_doc]))

        # Total docs count
        total_docs_result = MagicMock()
        total_docs_result.scalar.return_value = 4

        # Total folders count
        total_folders_result = MagicMock()
        total_folders_result.scalar.return_value = 1

        mock_session.execute = AsyncMock(side_effect=[
            resolver_result,      # resolver
            app_name_result,      # app name
            folder_check_result,  # folder scope check
            folder_result,        # subfolder list
            doc_count_result,     # doc counts
            doc_result,           # document list
            total_docs_result,    # total docs
            total_folders_result, # total folders
        ])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[str(app_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({
            "scope": "application",
            "scope_id": "Test App",
            "folder_id": str(folder_id),
        })
        assert "Test App" in result
        assert "Architecture" in result
        assert "Setup Guide" in result
        assert "4 document(s)" in result
        _clear()

    async def test_invalid_folder_id(self):
        """browse_knowledge rejects invalid folder_id."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id])
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({
            "scope": "application",
            "scope_id": app_id,
            "folder_id": "not-a-uuid",
        })
        assert "Invalid folder_id" in result
        _clear()

    async def test_personal_scope_wrong_user_denied(self):
        """browse_knowledge denies access to another user's personal scope."""
        user_id = str(uuid4())
        other_user = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(user_id=user_id)
        tools = create_read_tools(mock_db_factory, MagicMock())
        browse_knowledge = tools[11]

        result = await browse_knowledge.ainvoke({
            "scope": "personal",
            "scope_id": other_user,
        })
        assert "Access denied" in result
        _clear()


# ---------------------------------------------------------------------------
# get_applications — owner role
# ---------------------------------------------------------------------------

class TestGetApplicationsOwnerRole:

    async def test_shows_owner_role(self):
        """get_applications shows 'owner' role when user is the app owner."""
        user_id = str(uuid4())
        app_id = uuid4()

        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.name = "My Owned App"
        mock_app.description = "Test"
        mock_app.owner_id = UUID(user_id)  # Same as current user

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = [mock_app]
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(user_id=user_id, accessible_app_ids=[str(app_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        get_applications = tools[10]

        result = await get_applications.ainvoke({})
        assert "owner" in result
        assert "My Owned App" in result
        _clear()


# ---------------------------------------------------------------------------
# understand_image — error branch tests (TE R2 gaps 1 & 2)
# ---------------------------------------------------------------------------

class TestUnderstandImageErrorBranches:

    async def test_non_image_file_rejected(self):
        """understand_image rejects non-image file types."""
        att_id = uuid4()
        task_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "application/pdf"
        mock_attachment.file_name = "report.pdf"

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = project_id
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(project_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        understand_image = tools[8]

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "not an image" in result.lower()
        assert "application/pdf" in result
        _clear()

    async def test_no_storage_reference(self):
        """understand_image rejects attachment with no minio bucket/key."""
        att_id = uuid4()
        task_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "photo.png"
        mock_attachment.minio_bucket = None
        mock_attachment.minio_key = None

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = project_id
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(project_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        understand_image = tools[8]

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "no storage reference" in result.lower()
        _clear()

    async def test_orphaned_comment_attachment_denied(self):
        """understand_image denies access when comment has no task_id."""
        att_id = uuid4()
        comment_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = None
        mock_attachment.comment_id = comment_id
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "orphan.png"

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        # comment lookup returns None task_id (orphaned comment)
        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(side_effect=[att_result, comment_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(project_id)])
        tools = create_read_tools(mock_db_factory, MagicMock())
        understand_image = tools[8]

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "access denied" in result.lower()
        _clear()

    async def test_null_project_id_on_task_attachment_denied(self):
        """understand_image denies access when task has no project_id (deleted task)."""
        att_id = uuid4()
        task_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "ghost.png"

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        # Task project_id query returns None (task deleted or no project)
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(uuid4())])
        tools = create_read_tools(mock_db_factory, MagicMock())
        understand_image = tools[8]

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "access denied" in result.lower()
        _clear()


class TestGetTasksAssigneeEmailFallback:

    async def test_assignee_name_search_includes_email(self):
        """get_tasks assignee filter searches both display_name and email."""
        from sqlalchemy import or_

        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        tools = create_read_tools(mock_db_factory, MagicMock())
        get_tasks = tools[3]

        result = await get_tasks.ainvoke({
            "project_id": proj_id,
            "assignee": "john",
        })

        # Verify the query was executed
        assert mock_session.execute.await_count == 1

        # Check that the query includes the or_ clause for email fallback
        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": False}))
        # The compiled SQL should contain ILIKE on both display_name and email
        assert "display_name" in compiled.lower()
        assert "email" in compiled.lower()
        _clear()
