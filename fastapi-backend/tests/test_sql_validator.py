"""Unit tests for AI SQL validator.

Tests multi-layer validation: regex blocklist, AST parsing, view allowlist,
function allowlist, and LIMIT enforcement.
"""

from app.ai.sql_validator import (
    MAX_LIMIT,
    ALLOWED_FUNCTIONS,
    validate,
)


# ---------------------------------------------------------------------------
# Valid SELECT statements
# ---------------------------------------------------------------------------


class TestValidSelects:

    def test_simple_select_star(self):
        result = validate("SELECT * FROM v_tasks")
        assert result.is_valid is True
        assert result.error is None
        assert result.sanitized_sql is not None

    def test_select_with_where(self):
        result = validate("SELECT * FROM v_tasks WHERE priority = 'high'")
        assert result.is_valid is True
        assert result.error is None

    def test_select_with_join(self):
        sql = (
            "SELECT t.*, ts.name FROM v_tasks t "
            "JOIN v_task_statuses ts ON t.task_status_id = ts.id"
        )
        result = validate(sql)
        assert result.is_valid is True
        assert "v_tasks" in result.tables_used
        assert "v_task_statuses" in result.tables_used

    def test_select_with_aggregation(self):
        result = validate("SELECT count(*) FROM v_tasks GROUP BY project_id")
        assert result.is_valid is True

    def test_select_with_cte(self):
        sql = (
            "WITH active AS (SELECT * FROM v_tasks WHERE task_status_id IS NOT NULL) "
            "SELECT * FROM active"
        )
        result = validate(sql)
        assert result.is_valid is True
        # CTE alias 'active' should NOT appear in tables_used
        assert "active" not in result.tables_used
        assert "v_tasks" in result.tables_used

    def test_select_with_window_function(self):
        sql = "SELECT *, row_number() OVER (ORDER BY created_at) FROM v_tasks"
        result = validate(sql)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Mutation keywords rejected
# ---------------------------------------------------------------------------


class TestMutationRejected:

    def test_insert_rejected(self):
        result = validate("INSERT INTO v_tasks (title) VALUES ('test')")
        assert result.is_valid is False
        assert "INSERT" in result.error

    def test_update_rejected(self):
        result = validate("UPDATE v_tasks SET title = 'test'")
        assert result.is_valid is False
        assert "UPDATE" in result.error

    def test_delete_rejected(self):
        result = validate("DELETE FROM v_tasks")
        assert result.is_valid is False
        assert "DELETE" in result.error

    def test_drop_table_rejected(self):
        result = validate("DROP TABLE v_tasks")
        assert result.is_valid is False
        assert "DROP" in result.error

    def test_alter_table_rejected(self):
        result = validate("ALTER TABLE v_tasks ADD COLUMN x text")
        assert result.is_valid is False
        assert "ALTER" in result.error


# ---------------------------------------------------------------------------
# Injection and dangerous patterns rejected
# ---------------------------------------------------------------------------


class TestInjectionRejected:

    def test_multi_statement_rejected(self):
        result = validate("SELECT 1; DROP TABLE Users")
        assert result.is_valid is False
        # Could be caught by regex multi-statement or mutation blocklist
        assert result.error is not None

    def test_sql_comment_rejected(self):
        result = validate("SELECT * FROM v_tasks -- injected")
        assert result.is_valid is False
        assert "comment" in result.error.lower()

    def test_block_comment_rejected(self):
        result = validate("SELECT * FROM v_tasks /* injected */")
        assert result.is_valid is False
        assert "comment" in result.error.lower()

    def test_pg_sleep_rejected(self):
        result = validate("SELECT pg_sleep(10) FROM v_tasks")
        assert result.is_valid is False
        assert "pg_sleep" in result.error.lower()


# ---------------------------------------------------------------------------
# View allowlist
# ---------------------------------------------------------------------------


class TestViewAllowlist:

    def test_base_table_rejected(self):
        """Direct table references (not v_* views) must be rejected."""
        result = validate("SELECT * FROM Tasks")
        assert result.is_valid is False
        assert "not allowed" in result.error.lower()
        assert "tasks" in result.error.lower()

    def test_pg_catalog_rejected(self):
        result = validate("SELECT * FROM pg_catalog.pg_tables")
        assert result.is_valid is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# LIMIT enforcement
# ---------------------------------------------------------------------------


class TestLimitEnforcement:

    def test_limit_added_when_missing(self):
        result = validate("SELECT * FROM v_tasks")
        assert result.is_valid is True
        assert result.sanitized_sql is not None
        # Sanitized SQL should include LIMIT 100
        sanitized_upper = result.sanitized_sql.upper()
        assert "LIMIT" in sanitized_upper
        assert str(MAX_LIMIT) in result.sanitized_sql

    def test_excessive_limit_capped(self):
        result = validate("SELECT * FROM v_tasks LIMIT 10000")
        assert result.is_valid is True
        assert result.sanitized_sql is not None
        # LIMIT should be capped to MAX_LIMIT (100), not 10000
        assert "10000" not in result.sanitized_sql
        assert str(MAX_LIMIT) in result.sanitized_sql

    def test_small_limit_preserved(self):
        result = validate("SELECT * FROM v_tasks LIMIT 5")
        assert result.is_valid is True
        assert result.sanitized_sql is not None
        assert "5" in result.sanitized_sql


# ---------------------------------------------------------------------------
# Malformed / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_syntactically_invalid_sql_rejected(self):
        result = validate("SLECT * FORM v_tasks")
        assert result.is_valid is False
        assert result.error is not None

    def test_empty_sql_rejected(self):
        result = validate("")
        assert result.is_valid is False
        assert "empty" in result.error.lower()

    def test_whitespace_only_rejected(self):
        result = validate("   \n  ")
        assert result.is_valid is False
        assert "empty" in result.error.lower()

    def test_none_like_string_rejected(self):
        """A string with just whitespace should be treated as empty."""
        result = validate("  \t  ")
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# tables_used populated correctly
# ---------------------------------------------------------------------------


class TestTablesUsed:

    def test_single_table(self):
        result = validate("SELECT * FROM v_tasks")
        assert result.is_valid is True
        assert result.tables_used == ["v_tasks"]

    def test_multiple_tables_sorted(self):
        sql = (
            "SELECT t.title, u.display_name FROM v_tasks t "
            "JOIN v_users u ON t.assignee_id = u.id"
        )
        result = validate(sql)
        assert result.is_valid is True
        assert result.tables_used == ["v_tasks", "v_users"]

    def test_duplicate_table_deduplicated(self):
        sql = (
            "SELECT * FROM v_tasks t1 "
            "JOIN v_tasks t2 ON t1.parent_id = t2.id"
        )
        result = validate(sql)
        assert result.is_valid is True
        assert result.tables_used == ["v_tasks"]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:

    def test_max_limit_is_100(self):
        assert MAX_LIMIT == 100

    def test_allowed_functions_is_frozenset(self):
        assert isinstance(ALLOWED_FUNCTIONS, frozenset)
        assert len(ALLOWED_FUNCTIONS) > 0

    def test_common_functions_in_allowlist(self):
        """Commonly needed SQL functions should be in the allowlist."""
        expected = {"count", "sum", "avg", "min", "max", "coalesce", "lower", "upper"}
        assert expected.issubset(ALLOWED_FUNCTIONS)
