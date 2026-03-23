"""Unit tests for AI schema context provider.

Tests ViewDescription catalog, prompt generation, and DB validation.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.schema_context import (
    VIEW_DESCRIPTIONS,
    VALID_VIEW_NAMES,
    get_schema_prompt,
    get_schema_prompt_for_views,
    validate_schema_against_db,
)


# ---------------------------------------------------------------------------
# Expected view names (alphabetical)
# ---------------------------------------------------------------------------

EXPECTED_VIEWS = frozenset(
    {
        "v_applications",
        "v_projects",
        "v_tasks",
        "v_task_statuses",
        "v_documents",
        "v_document_folders",
        "v_comments",
        "v_application_members",
        "v_project_members",
        "v_project_assignments",
        "v_users",
        "v_attachments",
        "v_checklists",
        "v_checklist_items",
    }
)


# ---------------------------------------------------------------------------
# VIEW_DESCRIPTIONS catalog
# ---------------------------------------------------------------------------


class TestViewDescriptionsCatalog:
    def test_all_14_views_present(self):
        """All 14 views from v_applications through v_checklist_items must exist."""
        assert len(VIEW_DESCRIPTIONS) == 14
        actual_names = {v.name for v in VIEW_DESCRIPTIONS}
        assert actual_names == EXPECTED_VIEWS

    def test_valid_view_names_matches_descriptions(self):
        """VALID_VIEW_NAMES frozenset matches the VIEW_DESCRIPTIONS list."""
        assert VALID_VIEW_NAMES == EXPECTED_VIEWS

    def test_each_view_has_at_least_3_columns(self):
        """Every view description must have at least 3 columns."""
        for view in VIEW_DESCRIPTIONS:
            assert len(view.columns) >= 3, f"View '{view.name}' has only {len(view.columns)} column(s)"

    def test_password_hash_not_in_v_users(self):
        """v_users must NOT expose password_hash for security."""
        users_view = next(v for v in VIEW_DESCRIPTIONS if v.name == "v_users")
        column_names = [col.name for col in users_view.columns]
        assert "password_hash" not in column_names


# ---------------------------------------------------------------------------
# get_schema_prompt()
# ---------------------------------------------------------------------------


class TestGetSchemaPrompt:
    def test_returns_non_empty_string(self):
        result = get_schema_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_all_view_names(self):
        """Full prompt must mention every view name."""
        result = get_schema_prompt()
        for view in VIEW_DESCRIPTIONS:
            assert view.name in result, f"Missing view '{view.name}' in prompt"

    def test_under_8000_tokens(self):
        """Rough token estimate: words / 0.75 must be < 8000."""
        result = get_schema_prompt()
        word_count = len(result.split())
        estimated_tokens = word_count / 0.75
        assert estimated_tokens < 8000, f"Schema prompt too large: ~{estimated_tokens:.0f} tokens ({word_count} words)"

    def test_contains_header_text(self):
        result = get_schema_prompt()
        assert "Database Schema" in result
        assert "read-only" in result.lower()


# ---------------------------------------------------------------------------
# get_schema_prompt_for_views()
# ---------------------------------------------------------------------------


class TestGetSchemaPromptForViews:
    def test_subset_contains_only_requested_views(self):
        """Only the requested view section headers should appear in the output."""
        result = get_schema_prompt_for_views(["v_tasks", "v_users"])
        # Requested views should have their own section headers
        assert "### v_tasks" in result
        assert "### v_users" in result
        # Other views should NOT have section headers (they may appear in
        # relationship text of included views, which is fine)
        assert "### v_projects" not in result
        assert "### v_comments" not in result
        assert "### v_applications" not in result

    def test_empty_list_returns_header_only(self):
        """Empty view list should return just the header text with no view blocks."""
        result = get_schema_prompt_for_views([])
        assert "Database Schema" in result
        # None of the actual view names should appear
        for view_name in EXPECTED_VIEWS:
            assert view_name not in result, f"View '{view_name}' should not appear in empty-list output"

    def test_nonexistent_view_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown view names"):
            get_schema_prompt_for_views(["nonexistent"])

    def test_mixed_valid_and_invalid_raises(self):
        """Even one invalid name among valid ones should raise."""
        with pytest.raises(ValueError, match="Unknown view names"):
            get_schema_prompt_for_views(["v_tasks", "bad_view"])

    def test_single_view(self):
        result = get_schema_prompt_for_views(["v_applications"])
        assert "v_applications" in result
        assert "v_tasks" not in result


# ---------------------------------------------------------------------------
# validate_schema_against_db()
# ---------------------------------------------------------------------------


class TestValidateSchemaAgainstDb:
    async def _build_mock_db(self, rows: list[tuple]) -> AsyncMock:
        """Build a mock AsyncSession that returns the given rows."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        return mock_db

    async def test_matching_columns_returns_empty_warnings(self):
        """When DB matches static schema exactly, no warnings should be produced."""
        # Build rows matching ALL views and columns from VIEW_DESCRIPTIONS
        rows = []
        for view in VIEW_DESCRIPTIONS:
            for col in view.columns:
                is_nullable = "YES" if col.nullable else "NO"
                rows.append((view.name, col.name, col.type, is_nullable))

        mock_db = await self._build_mock_db(rows)
        warnings = await validate_schema_against_db(mock_db)
        assert warnings == []

    async def test_missing_column_produces_warning(self):
        """If DB is missing a column, a warning should be produced."""
        # Build rows for v_applications but omit the 'description' column
        rows = []
        for view in VIEW_DESCRIPTIONS:
            for col in view.columns:
                if view.name == "v_applications" and col.name == "description":
                    continue  # Skip this column
                is_nullable = "YES" if col.nullable else "NO"
                rows.append((view.name, col.name, col.type, is_nullable))

        mock_db = await self._build_mock_db(rows)
        warnings = await validate_schema_against_db(mock_db)
        assert len(warnings) >= 1
        assert any("description" in w and "v_applications" in w for w in warnings)

    async def test_missing_view_produces_warning(self):
        """If DB is missing an entire view, a warning should be produced."""
        # Build rows for all views EXCEPT v_users
        rows = []
        for view in VIEW_DESCRIPTIONS:
            if view.name == "v_users":
                continue
            for col in view.columns:
                is_nullable = "YES" if col.nullable else "NO"
                rows.append((view.name, col.name, col.type, is_nullable))

        mock_db = await self._build_mock_db(rows)
        warnings = await validate_schema_against_db(mock_db)
        assert any("v_users" in w and "not found" in w for w in warnings)

    async def test_extra_column_in_db_produces_warning(self):
        """If DB has a column not in static schema, warn about it."""
        rows = []
        for view in VIEW_DESCRIPTIONS:
            for col in view.columns:
                is_nullable = "YES" if col.nullable else "NO"
                rows.append((view.name, col.name, col.type, is_nullable))
        # Add an extra column to v_tasks
        rows.append(("v_tasks", "extra_col", "text", "YES"))

        mock_db = await self._build_mock_db(rows)
        warnings = await validate_schema_against_db(mock_db)
        assert any("extra_col" in w and "v_tasks" in w for w in warnings)

    async def test_extra_db_view_produces_warning(self):
        """A v_* view in DB not in static schema should warn."""
        rows = []
        for view in VIEW_DESCRIPTIONS:
            for col in view.columns:
                is_nullable = "YES" if col.nullable else "NO"
                rows.append((view.name, col.name, col.type, is_nullable))
        # Add an unknown view
        rows.append(("v_unknown_new", "id", "uuid", "NO"))

        mock_db = await self._build_mock_db(rows)
        warnings = await validate_schema_against_db(mock_db)
        assert any("v_unknown_new" in w for w in warnings)

    async def test_nullable_mismatch_produces_warning(self):
        """If DB says a column is nullable but static says NOT NULL, warn."""
        rows = []
        for view in VIEW_DESCRIPTIONS:
            for col in view.columns:
                # Flip nullable for v_tasks.title (should be NOT NULL)
                if view.name == "v_tasks" and col.name == "title":
                    rows.append((view.name, col.name, col.type, "YES"))
                else:
                    is_nullable = "YES" if col.nullable else "NO"
                    rows.append((view.name, col.name, col.type, is_nullable))

        mock_db = await self._build_mock_db(rows)
        warnings = await validate_schema_against_db(mock_db)
        assert any("nullable" in w.lower() and "title" in w for w in warnings)
