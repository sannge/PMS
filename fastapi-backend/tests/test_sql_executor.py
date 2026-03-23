"""Unit tests for AI SQL executor (app.ai.sql_executor).

All database calls are mocked — no real database connections are made.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.sql_executor import (
    MAX_ROWS,
    STATEMENT_TIMEOUT_MS,
    QueryResult,
    _serialize_value,
    execute,
)


# ---------------------------------------------------------------------------
# _serialize_value
# ---------------------------------------------------------------------------


class TestSerializeValue:
    def test_uuid_serialized_as_string(self):
        uid = uuid4()
        assert _serialize_value(uid) == str(uid)

    def test_datetime_serialized_as_iso_string(self):
        dt = datetime(2026, 2, 26, 12, 30, 0, tzinfo=timezone.utc)
        result = _serialize_value(dt)
        assert isinstance(result, str)
        assert result == dt.isoformat()

    def test_decimal_serialized_as_float(self):
        d = Decimal("3.14")
        result = _serialize_value(d)
        assert isinstance(result, float)
        assert result == pytest.approx(3.14)

    def test_none_serialized_as_none(self):
        assert _serialize_value(None) is None

    def test_int_passes_through(self):
        assert _serialize_value(42) == 42
        assert isinstance(_serialize_value(42), int)

    def test_float_passes_through(self):
        assert _serialize_value(2.718) == pytest.approx(2.718)
        assert isinstance(_serialize_value(2.718), float)

    def test_bool_passes_through(self):
        assert _serialize_value(True) is True
        assert _serialize_value(False) is False

    def test_date_serialized_as_iso_string(self):
        d = date(2026, 2, 26)
        result = _serialize_value(d)
        assert isinstance(result, str)
        assert result == "2026-02-26"

    def test_str_passes_through(self):
        assert _serialize_value("hello") == "hello"

    def test_unknown_type_converted_to_str(self):
        """Types not explicitly handled fall through to str()."""
        result = _serialize_value(b"bytes")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# QueryResult.to_text
# ---------------------------------------------------------------------------


class TestQueryResultToText:
    def test_to_text_returns_markdown_table(self):
        qr = QueryResult(
            columns=["id", "name"],
            rows=[
                {"id": "aaa", "name": "Task 1"},
                {"id": "bbb", "name": "Task 2"},
            ],
            row_count=2,
            truncated=False,
            execution_ms=10,
        )
        text = qr.to_text()
        assert "| id | name |" in text
        assert "| --- | --- |" in text
        assert "| aaa | Task 1 |" in text
        assert "| bbb | Task 2 |" in text

    def test_to_text_with_no_rows(self):
        qr = QueryResult(
            columns=["id", "name"],
            rows=[],
            row_count=0,
            truncated=False,
            execution_ms=5,
        )
        text = qr.to_text()
        assert "0 rows" in text
        assert "id" in text
        assert "name" in text

    def test_to_text_with_no_columns_and_no_rows(self):
        """Empty rows checked first — returns '0 rows' message."""
        qr = QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            truncated=False,
            execution_ms=5,
        )
        text = qr.to_text()
        assert "0 rows" in text

    def test_to_text_with_no_columns_but_rows(self):
        """Rows present but no columns — returns 'No columns' message."""
        qr = QueryResult(
            columns=[],
            rows=[{"?": 1}],
            row_count=1,
            truncated=False,
            execution_ms=5,
        )
        text = qr.to_text()
        assert "No columns" in text

    def test_to_text_with_truncation_note(self):
        qr = QueryResult(
            columns=["id"],
            rows=[{"id": str(i)} for i in range(MAX_ROWS)],
            row_count=MAX_ROWS,
            truncated=True,
            execution_ms=50,
        )
        text = qr.to_text()
        assert "truncated" in text.lower()
        assert str(MAX_ROWS) in text

    def test_to_text_null_values_rendered(self):
        qr = QueryResult(
            columns=["id", "name"],
            rows=[{"id": "aaa", "name": None}],
            row_count=1,
            truncated=False,
            execution_ms=5,
        )
        text = qr.to_text()
        assert "NULL" in text


# ---------------------------------------------------------------------------
# execute — happy path
# ---------------------------------------------------------------------------


def _make_mock_db(
    columns: list[str],
    raw_rows: list[tuple],
) -> AsyncMock:
    """Build a mock AsyncSession where db.execute returns the given results.

    db.execute is called 4 times:
      1. SET LOCAL app.current_user_id
      2. SET LOCAL statement_timeout
      3. SET TRANSACTION READ ONLY
      4. The actual SELECT query
    Only the fourth call returns a result set.
    """
    mock_result = MagicMock()
    mock_result.keys.return_value = columns
    mock_result.fetchmany.return_value = raw_rows

    # First three calls (SET LOCAL + SET TRANSACTION) return a dummy; fourth returns the result set
    dummy = MagicMock()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=[dummy, dummy, dummy, mock_result])
    return mock_db


class TestExecuteHappyPath:
    async def test_simple_query_returns_results(self):
        uid1, uid2 = uuid4(), uuid4()
        mock_db = _make_mock_db(
            columns=["id", "name"],
            raw_rows=[(uid1, "Task 1"), (uid2, "Task 2")],
        )
        user_id = uuid4()

        result = await execute(
            sql="SELECT id, name FROM v_tasks LIMIT 50",
            user_id=user_id,
            db=mock_db,
        )

        assert isinstance(result, QueryResult)
        assert result.columns == ["id", "name"]
        assert result.row_count == 2
        assert result.truncated is False
        assert result.execution_ms >= 0

        # Rows are serialized dicts
        assert result.rows[0]["id"] == str(uid1)
        assert result.rows[0]["name"] == "Task 1"
        assert result.rows[1]["id"] == str(uid2)
        assert result.rows[1]["name"] == "Task 2"

    async def test_set_local_executed_before_query(self):
        """Verify SET TRANSACTION READ ONLY is first, then SET LOCAL, then the query."""
        mock_db = _make_mock_db(columns=["id"], raw_rows=[])
        user_id = uuid4()

        await execute(
            sql="SELECT id FROM v_tasks LIMIT 10",
            user_id=user_id,
            db=mock_db,
        )

        assert mock_db.execute.await_count == 4

        calls = mock_db.execute.call_args_list

        # First call: SET TRANSACTION READ ONLY (must be first for security)
        first_sql = str(calls[0].args[0].text if hasattr(calls[0].args[0], "text") else calls[0].args[0])
        assert "READ ONLY" in first_sql

        # Second call: SET LOCAL app.current_user_id
        second_sql = str(calls[1].args[0].text if hasattr(calls[1].args[0], "text") else calls[1].args[0])
        assert "app.current_user_id" in second_sql

        # Third call: SET LOCAL statement_timeout
        third_sql = str(calls[2].args[0].text if hasattr(calls[2].args[0], "text") else calls[2].args[0])
        assert "statement_timeout" in third_sql

        # Fourth call: the actual query
        fourth_sql = str(calls[3].args[0].text if hasattr(calls[3].args[0], "text") else calls[3].args[0])
        assert "v_tasks" in fourth_sql

    async def test_statement_timeout_set_to_5000ms(self):
        """Statement timeout uses the correct constant value."""
        mock_db = _make_mock_db(columns=["id"], raw_rows=[])
        user_id = uuid4()

        await execute(
            sql="SELECT id FROM v_tasks LIMIT 10",
            user_id=user_id,
            db=mock_db,
        )

        calls = mock_db.execute.call_args_list
        # Statement timeout is call index 2 (after READ ONLY and SET LOCAL user_id)
        timeout_sql = str(calls[2].args[0].text if hasattr(calls[2].args[0], "text") else calls[2].args[0])
        assert "statement_timeout" in timeout_sql
        # Value is interpolated as a literal in the SQL text
        assert str(STATEMENT_TIMEOUT_MS) in timeout_sql

    async def test_empty_result_set(self):
        mock_db = _make_mock_db(columns=["id", "name"], raw_rows=[])
        user_id = uuid4()

        result = await execute(
            sql="SELECT id, name FROM v_tasks WHERE 1=0 LIMIT 50",
            user_id=user_id,
            db=mock_db,
        )

        assert result.rows == []
        assert result.row_count == 0
        assert result.truncated is False
        assert result.columns == ["id", "name"]

    async def test_truncation_flag_when_over_max_rows(self):
        """When the DB returns > MAX_ROWS, result is truncated."""
        # Return MAX_ROWS + 1 rows to trigger truncation
        raw_rows = [(f"id-{i}",) for i in range(MAX_ROWS + 1)]
        mock_db = _make_mock_db(columns=["id"], raw_rows=raw_rows)
        user_id = uuid4()

        result = await execute(
            sql="SELECT id FROM v_tasks LIMIT 100",
            user_id=user_id,
            db=mock_db,
        )

        assert result.truncated is True
        assert result.row_count == MAX_ROWS
        assert len(result.rows) == MAX_ROWS

    async def test_no_truncation_at_exact_max_rows(self):
        """Exactly MAX_ROWS rows — truncated should be False."""
        raw_rows = [(f"id-{i}",) for i in range(MAX_ROWS)]
        mock_db = _make_mock_db(columns=["id"], raw_rows=raw_rows)
        user_id = uuid4()

        result = await execute(
            sql="SELECT id FROM v_tasks LIMIT 100",
            user_id=user_id,
            db=mock_db,
        )

        assert result.truncated is False
        assert result.row_count == MAX_ROWS

    async def test_user_id_interpolated_in_set_local(self):
        """Verify the user_id appears as a literal in the SET LOCAL SQL."""
        mock_db = _make_mock_db(columns=["id"], raw_rows=[])
        user_id = uuid4()

        await execute(
            sql="SELECT id FROM v_tasks LIMIT 10",
            user_id=user_id,
            db=mock_db,
        )

        # Second call (index 1) is SET LOCAL app.current_user_id
        second_call = mock_db.execute.call_args_list[1]
        sql_text = str(second_call.args[0].text if hasattr(second_call.args[0], "text") else second_call.args[0])
        assert str(user_id) in sql_text
        assert "app.current_user_id" in sql_text


# ---------------------------------------------------------------------------
# execute — error handling
# ---------------------------------------------------------------------------


class TestExecuteErrors:
    async def test_timeout_raises_value_error(self):
        """DBAPIError with timeout message -> ValueError about timeout."""
        mock_db = AsyncMock(spec=AsyncSession)
        # SET LOCAL calls succeed, then the query raises DBAPIError
        orig_error = Exception("canceling statement due to statement timeout")
        dbapi_error = DBAPIError(
            statement="SELECT ...",
            params={},
            orig=orig_error,
        )
        dummy = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[dummy, dummy, dummy, dbapi_error])
        user_id = uuid4()

        with pytest.raises(ValueError, match="timed out"):
            await execute(
                sql="SELECT id FROM v_tasks LIMIT 100",
                user_id=user_id,
                db=mock_db,
            )

    async def test_other_dbapi_error_raises_value_error(self):
        """DBAPIError with non-timeout message -> ValueError with error detail."""
        mock_db = AsyncMock(spec=AsyncSession)
        orig_error = Exception('relation "v_tasks" does not exist')
        dbapi_error = DBAPIError(
            statement="SELECT ...",
            params={},
            orig=orig_error,
        )
        dummy = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[dummy, dummy, dummy, dbapi_error])
        user_id = uuid4()

        with pytest.raises(ValueError, match="Query execution error"):
            await execute(
                sql="SELECT id FROM v_nonexistent LIMIT 10",
                user_id=user_id,
                db=mock_db,
            )
