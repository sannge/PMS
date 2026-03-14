"""SQL executor for AI-generated queries.

Executes validated SQL against scoped PostgreSQL views with:
- SET LOCAL app.current_user_id for RBAC
- SET LOCAL statement_timeout for safety (5s)
- Row limit enforcement (100)
- Type serialization (UUID->str, datetime->ISO)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .config_service import get_agent_config

logger = logging.getLogger(__name__)

_cfg = get_agent_config()

MAX_ROWS = _cfg.get_int("sql.max_limit", 100)
STATEMENT_TIMEOUT_MS = _cfg.get_int("sql.statement_timeout_ms", 5000)
APP_QUERY_TIMEOUT_S = _cfg.get_float("sql.app_query_timeout_s", 6.0)


def _serialize_value(value: object) -> object:
    """Serialize a database value for JSON-safe output.

    Args:
        value: Raw value from database row.

    Returns:
        JSON-serializable value.
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


@dataclass
class QueryResult:
    """Result of executing a SQL query."""

    columns: list[str]
    rows: list[dict]
    row_count: int
    truncated: bool
    execution_ms: int

    def to_text(self) -> str:
        """Format as markdown table for LLM consumption.

        Returns:
            Markdown-formatted table string. Returns a message if no rows.
        """
        if not self.rows:
            return f"Query returned 0 rows. Columns: {', '.join(self.columns)}"

        if not self.columns:
            return "No columns in result."

        # Build header row
        header = "| " + " | ".join(self.columns) + " |"
        separator = "| " + " | ".join("---" for _ in self.columns) + " |"

        # Build data rows
        data_rows: list[str] = []
        for row in self.rows:
            cells = []
            for col in self.columns:
                val = row.get(col)
                cells.append("NULL" if val is None else str(val))
            data_rows.append("| " + " | ".join(cells) + " |")

        parts = [header, separator, *data_rows]

        if self.truncated:
            parts.append(f"\n*Results truncated to {MAX_ROWS} rows.*")

        return "\n".join(parts)


async def execute(
    sql: str,
    user_id: UUID,
    db: AsyncSession,
) -> QueryResult:
    """Execute a validated SQL query with RBAC scoping and safety limits.

    Sets transaction-local variables for user scoping and statement timeout,
    then executes the query with a hard row cap.

    Args:
        sql: Validated SQL query (must be SELECT only).
        user_id: Current user's UUID for RBAC scoping via SET LOCAL.
        db: Active database session.

    Returns:
        QueryResult with columns, rows, and execution metadata.

    Raises:
        ValueError: If query times out or execution fails.
    """
    start_time = time.monotonic()

    try:
        # Defense-in-depth: force read-only transaction FIRST so even if
        # a novel SQL-injection bypass slips past the validator, any
        # mutation attempt is blocked by PostgreSQL itself.
        await db.execute(text("SET TRANSACTION READ ONLY"))

        # Set transaction-local user context for scoped views.
        # SET LOCAL doesn't support parameter bindings ($1) in PostgreSQL,
        # so we interpolate the value directly. This is safe because user_id
        # is a validated Python UUID object (cannot contain SQL injection).
        await db.execute(
            text(f"SET LOCAL app.current_user_id = '{user_id}'")
        )

        # Set transaction-local statement timeout for safety.
        # STATEMENT_TIMEOUT_MS is a module-level integer constant.
        await db.execute(
            text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}'")
        )

        # Execute the query (with application-level timeout as safety net)
        try:
            result = await asyncio.wait_for(
                db.execute(text(sql)),
                timeout=APP_QUERY_TIMEOUT_S,
            )
        except asyncio.TimeoutError as exc:
            execution_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                "Query execution timeout (app-level, %ds) after %dms: %.100s",
                APP_QUERY_TIMEOUT_S,
                execution_ms,
                sql,
            )
            # Cancel any pending DB operations from the abandoned task
            try:
                await db.rollback()
            except Exception:
                pass
            raise ValueError(
                "Query execution timeout exceeded (application-level)"
            ) from exc

        # Get column names from result cursor
        columns = list(result.keys())

        # Fetch rows with cap
        raw_rows = result.fetchmany(MAX_ROWS + 1)
        truncated = len(raw_rows) > MAX_ROWS
        if truncated:
            raw_rows = raw_rows[:MAX_ROWS]

        # Serialize rows to dicts
        rows: list[dict] = []
        for row in raw_rows:
            serialized = {}
            for i, col in enumerate(columns):
                serialized[col] = _serialize_value(row[i])
            rows.append(serialized)

        execution_ms = int((time.monotonic() - start_time) * 1000)

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            execution_ms=execution_ms,
        )

    except DBAPIError as exc:
        execution_ms = int((time.monotonic() - start_time) * 1000)
        error_msg = str(exc.orig) if exc.orig else str(exc)

        # Check for statement timeout
        if "canceling statement due to statement timeout" in error_msg:
            logger.warning(
                "Query timed out after %dms: %.100s", execution_ms, sql
            )
            raise ValueError(
                f"Query timed out after {STATEMENT_TIMEOUT_MS}ms. "
                f"Try a simpler query or add more filters."
            ) from exc

        # SA-003: Log the raw error details server-side but return a
        # sanitized message to prevent leaking schema/internal info.
        logger.error(
            "SQL execution failed after %dms: %s | SQL: %.200s",
            execution_ms,
            error_msg,
            sql,
        )
        raise ValueError(
            "Query execution error. Please check your query syntax and try again."
        ) from exc
