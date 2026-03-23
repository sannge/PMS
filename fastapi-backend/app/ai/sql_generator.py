"""SQL generator service for AI agent.

Generates SELECT queries from natural language questions using LLM.
Pipeline: question -> build prompt (schema context + rules) -> LLM ->
parse JSON -> validate -> retry on failure (max 2) -> return GeneratedQuery.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .provider_interface import LLMProviderError
from .provider_registry import ProviderRegistry
from .schema_context import get_schema_prompt
from .sql_validator import ValidationResult, validate

from .config_service import get_agent_config

logger = logging.getLogger(__name__)

_cfg = get_agent_config()
MAX_RETRIES = _cfg.get_int("agent.sql_max_retries", 2)

# Cached system prompt — built once at first use since the schema is static.
_cached_system_prompt: str | None = None


@dataclass
class GeneratedQuery:
    """Result of SQL generation."""

    sql: str
    explanation: str
    tables_used: list[str]
    generation_attempts: int
    duration_ms: int


def _build_system_prompt() -> str:
    """Build the system prompt with schema context, rules, and examples.

    Cached after first call since the schema is static at runtime.

    Returns:
        System message string for LLM SQL generation.
    """
    global _cached_system_prompt
    if _cached_system_prompt is not None:
        return _cached_system_prompt

    schema = get_schema_prompt()

    _cached_system_prompt = f"""You are a SQL query generator for a project management application.
You generate PostgreSQL SELECT queries against scoped database views.

## Rules
1. Generate ONLY SELECT statements. No INSERT, UPDATE, DELETE, DROP, or any mutation.
2. Query ONLY from v_* views (e.g., v_tasks, v_projects). Never reference base tables directly.
3. Always include a LIMIT clause. Default to LIMIT 50, maximum LIMIT 100.
4. Return your response as JSON with this exact structure:
   {{"sql": "SELECT ...", "explanation": "...", "tables_used": ["v_tasks", ...]}}
5. JOIN v_task_statuses ON v_tasks.task_status_id = v_task_statuses.id to get human-readable status names.
6. JOIN v_users to resolve user names from ID columns (assignee_id, reporter_id, owner_id, etc.).
7. Use descriptive column aliases for clarity (e.g., AS task_title, AS assignee_name).
8. For date filters, use PostgreSQL date functions (NOW(), INTERVAL, date_trunc).
9. Do NOT use SQL comments (-- or /* */).
10. The ONLY available current_setting() parameter is 'app.current_user_id'. Do NOT invent or use any other parameters like 'app.current_application_id', 'app.current_project_id', etc. — they do NOT exist and will cause errors.

## Database Schema

{schema}

## Examples

Question: "How many tasks are there?"
{{"sql": "SELECT count(*) AS task_count FROM v_tasks LIMIT 1", "explanation": "Count all tasks visible to the current user.", "tables_used": ["v_tasks"]}}

Question: "Show all high priority tasks"
{{"sql": "SELECT t.task_key, t.title AS task_title, ts.name AS status_name, u.display_name AS assignee_name FROM v_tasks t LEFT JOIN v_task_statuses ts ON t.task_status_id = ts.id LEFT JOIN v_users u ON t.assignee_id = u.id WHERE t.priority = 'high' ORDER BY t.created_at DESC LIMIT 50", "explanation": "List all high-priority tasks with their status and assignee.", "tables_used": ["v_tasks", "v_task_statuses", "v_users"]}}

Question: "What tasks are assigned to me?"
{{"sql": "SELECT t.task_key, t.title AS task_title, ts.name AS status_name, t.priority, t.due_date FROM v_tasks t LEFT JOIN v_task_statuses ts ON t.task_status_id = ts.id WHERE t.assignee_id = current_setting('app.current_user_id')::uuid ORDER BY t.due_date ASC NULLS LAST LIMIT 50", "explanation": "List tasks assigned to the current user with status and priority.", "tables_used": ["v_tasks", "v_task_statuses"]}}

Question: "Which projects have the most tasks?"
{{"sql": "SELECT p.name AS project_name, p.key AS project_key, count(t.id) AS task_count FROM v_projects p LEFT JOIN v_tasks t ON t.project_id = p.id GROUP BY p.id, p.name, p.key ORDER BY task_count DESC LIMIT 50", "explanation": "Rank projects by number of tasks.", "tables_used": ["v_projects", "v_tasks"]}}

Question: "Show overdue tasks"
{{"sql": "SELECT t.task_key, t.title AS task_title, t.due_date, ts.name AS status_name, u.display_name AS assignee_name FROM v_tasks t LEFT JOIN v_task_statuses ts ON t.task_status_id = ts.id LEFT JOIN v_users u ON t.assignee_id = u.id WHERE t.due_date < NOW() AND ts.name NOT IN ('Done', 'Closed') ORDER BY t.due_date ASC LIMIT 50", "explanation": "List tasks that are past their due date and not yet completed.", "tables_used": ["v_tasks", "v_task_statuses", "v_users"]}}

Question: "How many tasks does each person have?"
{{"sql": "SELECT u.display_name AS assignee_name, count(t.id) AS task_count FROM v_users u JOIN v_tasks t ON t.assignee_id = u.id GROUP BY u.id, u.display_name ORDER BY task_count DESC LIMIT 50", "explanation": "Count tasks per assignee.", "tables_used": ["v_users", "v_tasks"]}}

Question: "Show recent documents"
{{"sql": "SELECT d.title, d.created_at, d.updated_at FROM v_documents d ORDER BY d.updated_at DESC LIMIT 20", "explanation": "List the most recently updated documents.", "tables_used": ["v_documents"]}}

Question: "List all applications"
{{"sql": "SELECT a.name AS app_name, a.description, u.display_name AS owner_name, a.created_at FROM v_applications a LEFT JOIN v_users u ON a.owner_id = u.id ORDER BY a.name ASC LIMIT 50", "explanation": "List all applications visible to the current user with their owners.", "tables_used": ["v_applications", "v_users"]}}

Question: "What applications am I in?"
{{"sql": "SELECT a.name AS app_name, a.description FROM v_applications a ORDER BY a.name ASC LIMIT 50", "explanation": "The v_applications view already filters to applications the current user owns or is a member of.", "tables_used": ["v_applications"]}}

Question: "Who am I?" or "What is my email?"
{{"sql": "SELECT u.display_name, u.email FROM v_users u WHERE u.id = current_setting('app.current_user_id')::uuid LIMIT 1", "explanation": "Look up the current user's profile.", "tables_used": ["v_users"]}}

Question: "Who are the members of my applications?"
{{"sql": "SELECT a.name AS app_name, u.display_name AS member_name, u.email, am.role FROM v_application_members am JOIN v_applications a ON am.application_id = a.id JOIN v_users u ON am.user_id = u.id ORDER BY a.name, u.display_name LIMIT 50", "explanation": "List all members across the user's accessible applications. The views are already RBAC-scoped — no current_setting() needed.", "tables_used": ["v_application_members", "v_applications", "v_users"]}}

## Important Notes
- All v_* views are RBAC-scoped: they automatically filter to data the current user can access. You do NOT need current_setting() to query them. Just SELECT from the view directly.
"""
    return _cached_system_prompt


def _parse_llm_json(text: str) -> dict:
    """Parse LLM response text as JSON, handling common quirks.

    Handles:
    - Markdown code fences (```json ... ```)
    - Trailing commas before closing braces/brackets
    - Whitespace/newline variations

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If JSON cannot be parsed after cleanup.
    """
    cleaned = text.strip()

    # Strip markdown code fences
    fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
    match = fence_pattern.match(cleaned)
    if match:
        cleaned = match.group(1).strip()

    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Try to extract JSON object from surrounding text
        obj_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if obj_match:
            try:
                extracted = obj_match.group(0)
                extracted = re.sub(r",\s*([}\]])", r"\1", extracted)
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Failed to parse LLM JSON response: {exc}") from exc


async def generate_query(
    question: str,
    db: AsyncSession,
    provider_registry: ProviderRegistry,
    application_id: UUID | None = None,
    project_id: UUID | None = None,
) -> GeneratedQuery:
    """Generate a SQL query from a natural language question.

    Pipeline: build prompt -> LLM call -> parse JSON -> validate SQL ->
    retry on failure (up to MAX_RETRIES) -> return GeneratedQuery.

    Args:
        question: Natural language question from the user.
        db: Active database session.
        provider_registry: Registry for resolving LLM providers.
        application_id: Optional application scope filter.
        project_id: Optional project scope filter.

    Returns:
        GeneratedQuery with the validated SQL, explanation, and metadata.

    Raises:
        ValueError: If SQL generation fails after all retries.
        LLMProviderError: If the LLM provider is unavailable.
    """
    start_time = time.monotonic()

    provider, model_id = await provider_registry.get_chat_provider(db)
    system_prompt = _build_system_prompt()

    # Build user message with optional scope context
    user_message = question
    if application_id:
        user_message += f"\n\nContext: Focus on application_id = '{application_id}'"
    if project_id:
        user_message += f"\n\nContext: Focus on project_id = '{project_id}'"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    last_error: str | None = None
    response: str = ""
    attempts = 0

    for attempt in range(1, MAX_RETRIES + 2):  # 1 initial + MAX_RETRIES retries
        attempts = attempt
        try:
            response = await provider.chat_completion(
                messages=messages,
                model=model_id,
                temperature=0.1,
                max_tokens=1024,
            )

            parsed = _parse_llm_json(response)

            sql = parsed.get("sql", "").strip()
            explanation = parsed.get("explanation", "").strip()
            tables_used = parsed.get("tables_used", [])

            if not sql:
                last_error = "LLM returned empty SQL"
                logger.warning("SQL generation attempt %d: empty SQL", attempt)
                # Feed error back to LLM for correction
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Error: {last_error}. Please generate a valid SQL query.",
                    }
                )
                continue

            # Validate the generated SQL
            validation: ValidationResult = validate(sql)

            if not validation.is_valid:
                last_error = validation.error
                logger.warning(
                    "SQL generation attempt %d: validation failed: %s",
                    attempt,
                    validation.error,
                )
                # Feed validation error back to LLM for correction
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The SQL you generated failed validation: {validation.error}\n"
                            f"Please fix the SQL and return valid JSON."
                        ),
                    }
                )
                continue

            # Use sanitized SQL (LIMIT may have been adjusted)
            final_sql = validation.sanitized_sql or sql

            duration_ms = int((time.monotonic() - start_time) * 1000)

            return GeneratedQuery(
                sql=final_sql,
                explanation=explanation,
                tables_used=tables_used,
                generation_attempts=attempts,
                duration_ms=duration_ms,
            )

        except ValueError as exc:
            last_error = str(exc)
            logger.warning(
                "SQL generation attempt %d: JSON parse error: %s",
                attempt,
                exc,
            )
            # Feed parse error back to LLM
            if response:
                messages.append({"role": "assistant", "content": response})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Error parsing your response: {exc}\n"
                        f"Please return ONLY a valid JSON object with keys: "
                        f"sql, explanation, tables_used."
                    ),
                }
            )
            continue

        except LLMProviderError:
            # Re-raise provider errors (no point retrying config issues)
            raise

    duration_ms = int((time.monotonic() - start_time) * 1000)
    raise ValueError(f"SQL generation failed after {attempts} attempts. Last error: {last_error}")
