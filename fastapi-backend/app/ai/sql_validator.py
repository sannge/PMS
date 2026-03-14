"""SQL validator for AI-generated queries.

Multi-layer validation pipeline:
1. Regex blocklist (mutation keywords, dangerous functions, multi-statement, comments)
2. sqlglot AST parsing (PostgreSQL dialect)
3. View allowlist (only v_* views)
4. Function allowlist (safe SQL functions only)
5. LIMIT enforcement (add/cap at 100)
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from .config_service import get_agent_config

logger = logging.getLogger(__name__)

_cfg = get_agent_config()
MAX_LIMIT = _cfg.get_int("sql.max_limit", 100)

# ---------------------------------------------------------------------------
# Layer 1 — Regex blocklist
# ---------------------------------------------------------------------------

_MUTATION_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|EXECUTE|PREPARE"
    r"|DO|CALL|SET|RESET|DISCARD|VACUUM|REINDEX|CLUSTER|REFRESH|NOTIFY|LISTEN|UNLISTEN"
    r"|EXPLAIN|LOCK)\b",
    re.IGNORECASE,
)

_DANGEROUS_FUNC_PATTERN = re.compile(
    r"\b(pg_sleep|pg_terminate_backend|pg_read_file|pg_ls_dir"
    r"|dblink|lo_import|lo_export|set_config|pg_advisory_lock)\b",
    re.IGNORECASE,
)

_MULTI_STATEMENT_PATTERN = re.compile(r";\s*\S")

_COMMENT_PATTERN = re.compile(r"--|/\*")

# Only 'app.current_user_id' is a valid current_setting() parameter.
# Reject any other invented parameters (e.g., app.current_application_id).
_CURRENT_SETTING_PATTERN = re.compile(
    r"current_setting\s*\(\s*'([^']+)'\s*\)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Layer 4 — Function allowlist
# ---------------------------------------------------------------------------

ALLOWED_FUNCTIONS: frozenset[str] = frozenset({
    "count", "sum", "avg", "min", "max",
    "coalesce", "nullif",
    "lower", "upper", "trim", "length", "substring", "replace", "concat",
    "date_trunc", "extract", "now", "current_date", "current_timestamp",
    "cast", "to_char", "to_date", "to_timestamp",
    "row_number", "rank", "dense_rank",
    "string_agg", "array_agg",
    "exists", "case", "greatest", "least",
    "bool_and", "bool_or",
    "abs", "round", "ceil", "floor",
    "current_setting",  # PostgreSQL GUC lookup (used for RBAC user context)
})


@dataclass
class ValidationResult:
    """Result of SQL validation."""

    is_valid: bool
    error: str | None = None
    sanitized_sql: str | None = None
    tables_used: list[str] = field(default_factory=list)


def _check_regex_blocklist(sql: str) -> str | None:
    """Layer 1: Check SQL against regex blocklists.

    Returns an error string if blocked, or None if OK.
    """
    match = _MUTATION_PATTERN.search(sql)
    if match:
        return f"Mutation keyword blocked: {match.group(0).upper()}"

    match = _DANGEROUS_FUNC_PATTERN.search(sql)
    if match:
        return f"Dangerous function blocked: {match.group(0)}"

    if _MULTI_STATEMENT_PATTERN.search(sql):
        return "Multi-statement SQL is not allowed."

    if _COMMENT_PATTERN.search(sql):
        return "SQL comments (-- or /* */) are not allowed."

    # Validate current_setting() parameters — only 'app.current_user_id' allowed
    for m in _CURRENT_SETTING_PATTERN.finditer(sql):
        param = m.group(1)
        if param != "app.current_user_id":
            return (
                f"Invalid current_setting parameter '{param}'. "
                f"Only 'app.current_user_id' is available."
            )

    return None


def _extract_cte_names(parsed: exp.Expression) -> set[str]:
    """Extract CTE alias names defined in WITH clauses."""
    cte_names: set[str] = set()
    for cte in parsed.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            cte_names.add(alias.lower())
    return cte_names


def _extract_tables(parsed: exp.Expression) -> list[str]:
    """Extract all table names referenced in the AST, excluding CTE aliases."""
    cte_names = _extract_cte_names(parsed)
    tables: list[str] = []
    for table in parsed.find_all(exp.Table):
        name = table.name
        if name:
            lower_name = name.lower()
            # Skip CTE alias references — they aren't real tables
            if lower_name not in cte_names:
                tables.append(lower_name)
    return tables


def _check_view_allowlist(tables: list[str]) -> str | None:
    """Layer 3: Ensure only v_* views are referenced.

    Returns an error string if a disallowed table is found, or None if OK.
    """
    for table in tables:
        if not table.startswith("v_"):
            return f"Table '{table}' is not allowed. Only v_* views are permitted."
    return None


def _extract_function_names(parsed: exp.Expression) -> set[str]:
    """Extract all function names from the AST."""
    names: set[str] = set()

    # Named/known functions (sqlglot maps them to specific exp types)
    for func in parsed.find_all(exp.Func):
        # Get the SQL name of the function
        # For specific function types, use the key attribute
        if isinstance(func, exp.Anonymous):
            names.add(func.name.lower())
        else:
            # For recognized functions, sqlglot stores them as specific types
            # The sql_name() method returns the canonical SQL function name
            sql_name = type(func).key
            if sql_name:
                names.add(sql_name.lower())

    return names


# Functions that sqlglot parses into specific AST nodes rather than
# exp.Anonymous. These are safe built-in SQL constructs we always allow.
_SQLGLOT_BUILTIN_KEYS: frozenset[str] = frozenset({
    # Aggregate functions
    "count", "sum", "avg", "min", "max",
    "arrayagg", "array_agg",
    # String functions
    "lower", "upper", "trim", "length", "substring", "replace", "concat",
    "initcap", "left", "right", "lpad", "rpad",
    # Conditional
    "coalesce", "nullif", "if", "case", "greatest", "least",
    # Type casting
    "cast", "tryCast", "trycast",
    # Date/time
    "extract", "datetrunc", "date_trunc", "currentdate", "current_date",
    "currenttimestamp", "current_timestamp",
    "tochar", "to_char", "todate", "to_date", "totimestamp", "to_timestamp",
    # Window functions
    "rownumber", "row_number", "rank", "denserank", "dense_rank",
    # Aggregation
    "stringagg", "string_agg",
    "booland", "bool_and", "boolor", "bool_or",
    # Math
    "abs", "round", "ceil", "floor",
    # Postgres-specific
    "now", "currentsetting", "current_setting",
    # Subquery predicates
    "exists", "in", "any", "all",
    # Other structural nodes sqlglot maps
    "between", "like", "ilike", "is", "not",
    "and", "or",
    "alias", "column", "star", "literal", "ordered", "subquery",
    "select", "from", "where", "group", "having", "order", "limit",
    "join", "on", "union", "except", "intersect", "with", "cte",
    "window", "windowspec", "over", "partition",
    "distinct", "parameter", "placeholder",
    "table", "schema", "database",
    "eq", "neq", "gt", "gte", "lt", "lte",
    "add", "sub", "mul", "div", "mod",
    "neg", "bitwiseand", "bitwiseor", "bitwisexor",
    "paren", "tuple",
    "null", "boolean", "true", "false",
    "asc", "desc",
    "dp", "ts", "interval",
})


def _check_function_allowlist(parsed: exp.Expression) -> str | None:
    """Layer 4: Ensure only allowed functions are used.

    Returns an error string if a disallowed function is found, or None if OK.
    """
    func_names = _extract_function_names(parsed)

    # Filter out sqlglot structural keys — these aren't real "function calls"
    real_functions = func_names - _SQLGLOT_BUILTIN_KEYS

    for name in sorted(real_functions):
        # Check against our explicit allowlist
        if name not in ALLOWED_FUNCTIONS:
            return f"Function '{name}' is not allowed."

    return None


def _enforce_limit(parsed: exp.Expression) -> exp.Expression:
    """Layer 5: Add or cap LIMIT to MAX_LIMIT.

    Handles both simple SELECT and UNION/INTERSECT/EXCEPT queries.
    For set operations, wraps in a subquery and adds LIMIT to the outer query.
    """
    if isinstance(parsed, (exp.Union, exp.Intersect, exp.Except)):
        # Set operations: wrap in subquery and apply LIMIT to outer SELECT
        limit_node = parsed.find(exp.Limit)
        if limit_node is None:
            parsed = parsed.limit(MAX_LIMIT)
        else:
            limit_expr = limit_node.expression
            if isinstance(limit_expr, exp.Literal) and limit_expr.is_int:
                current = int(limit_expr.this)
                if current > MAX_LIMIT:
                    limit_node.set(
                        "expression",
                        exp.Literal.number(MAX_LIMIT),
                    )
    elif isinstance(parsed, exp.Select):
        limit_node = parsed.find(exp.Limit)
        if limit_node is None:
            # No LIMIT — add one
            parsed = parsed.limit(MAX_LIMIT)
        else:
            # LIMIT exists — cap it
            limit_expr = limit_node.expression
            if isinstance(limit_expr, exp.Literal) and limit_expr.is_int:
                current = int(limit_expr.this)
                if current > MAX_LIMIT:
                    limit_node.set(
                        "expression",
                        exp.Literal.number(MAX_LIMIT),
                    )
    return parsed


def validate(sql: str) -> ValidationResult:
    """Validate an AI-generated SQL query through all safety layers.

    Args:
        sql: The raw SQL string to validate.

    Returns:
        ValidationResult with is_valid, optional error, sanitized SQL, and tables used.
    """
    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, error="Empty SQL query.")

    sql = sql.strip()

    # Layer 1 — Regex blocklist
    error = _check_regex_blocklist(sql)
    if error:
        logger.warning("SQL rejected (regex): %s | SQL: %s", error, sql[:200])
        return ValidationResult(is_valid=False, error=error)

    # Layer 2 — sqlglot AST parsing
    try:
        parsed_list = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.errors.ParseError as exc:
        logger.warning("SQL rejected (parse): %s | SQL: %s", exc, sql[:200])
        return ValidationResult(is_valid=False, error=f"SQL parse error: {exc}")

    if not parsed_list or parsed_list[0] is None:
        return ValidationResult(is_valid=False, error="SQL could not be parsed.")

    if len(parsed_list) > 1:
        return ValidationResult(
            is_valid=False,
            error="Multi-statement SQL is not allowed.",
        )

    parsed = parsed_list[0]

    # Ensure it's a SELECT (not a DML/DDL that slipped through regex)
    if not isinstance(parsed, exp.Select):
        # Also accept UNION/INTERSECT/EXCEPT (they wrap Selects)
        if not isinstance(parsed, (exp.Union, exp.Intersect, exp.Except)):
            return ValidationResult(
                is_valid=False,
                error="Only SELECT statements are allowed.",
            )

    # Layer 3 — View allowlist
    tables = _extract_tables(parsed)
    error = _check_view_allowlist(tables)
    if error:
        logger.warning("SQL rejected (view): %s | SQL: %s", error, sql[:200])
        return ValidationResult(is_valid=False, error=error)

    # Layer 4 — Function allowlist
    error = _check_function_allowlist(parsed)
    if error:
        logger.warning("SQL rejected (func): %s | SQL: %s", error, sql[:200])
        return ValidationResult(is_valid=False, error=error)

    # Layer 5 — LIMIT enforcement
    parsed = _enforce_limit(parsed)
    sanitized = parsed.sql(dialect="postgres")

    # Re-check regex blocklist on sanitized output (defense-in-depth:
    # sqlglot regeneration could introduce blocked patterns)
    error = _check_regex_blocklist(sanitized)
    if error:
        logger.warning("SQL rejected (regex post-sanitize): %s | SQL: %s", error, sanitized[:200])
        return ValidationResult(is_valid=False, error=error)

    logger.info("SQL validated OK. Tables: %s", tables)
    return ValidationResult(
        is_valid=True,
        sanitized_sql=sanitized,
        tables_used=sorted(set(tables)),
    )
