"""Admin endpoints for AgentConfigurations management.

Provides CRUD operations for runtime agent configuration values.
All endpoints require developer access (is_developer=True on User).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.config_service import get_agent_config
from ..database import get_db
from ..models.agent_config import AgentConfiguration
from ..models.user import User
from ..routers.ai_config import require_developer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-config"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConfigEntry(BaseModel):
    """Single configuration entry response."""

    key: str
    value: str
    value_type: str
    category: str
    description: str | None = None
    min_value: str | None = None
    max_value: str | None = None


class ConfigUpdateRequest(BaseModel):
    """Request body for updating a config value."""

    value: str


class ConfigGroupResponse(BaseModel):
    """Grouped configuration response."""

    category: str
    configs: list[ConfigEntry]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/agent-config",
    response_model=list[ConfigGroupResponse],
)
async def list_agent_configs(
    current_user: User = Depends(require_developer),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> list[ConfigGroupResponse]:
    """List all agent configurations grouped by category.

    Requires developer access.
    """
    result = await db.execute(
        select(AgentConfiguration).order_by(
            AgentConfiguration.category, AgentConfiguration.key
        )
    )
    rows = result.scalars().all()

    # Group by category
    groups: dict[str, list[ConfigEntry]] = {}
    for row in rows:
        entry = ConfigEntry(
            key=row.key,
            value=row.value,
            value_type=row.value_type,
            category=row.category,
            description=row.description,
            min_value=row.min_value,
            max_value=row.max_value,
        )
        groups.setdefault(row.category, []).append(entry)

    return [
        ConfigGroupResponse(category=cat, configs=entries)
        for cat, entries in sorted(groups.items())
    ]


@router.put(
    "/agent-config/{key:path}",
    response_model=ConfigEntry,
)
async def update_agent_config(
    key: str,
    body: ConfigUpdateRequest,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> ConfigEntry:
    """Update a single agent configuration value.

    Validates type and bounds before saving. Requires developer access.
    """
    # Validate key format
    if not re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$', key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid config key format",
        )

    # Enforce min_value / max_value constraints from DB record
    existing = await db.scalar(
        select(AgentConfiguration).where(AgentConfiguration.key == key)
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Config key not found: {key}",
        )
    if existing.value_type in ("int", "float"):
        try:
            numeric_val = float(body.value)
            if existing.min_value is not None and numeric_val < float(existing.min_value):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Value {body.value} is below minimum {existing.min_value}",
                )
            if existing.max_value is not None and numeric_val > float(existing.max_value):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Value {body.value} is above maximum {existing.max_value}",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Value {body.value!r} is not a valid {existing.value_type}",
            )

    cfg_service = get_agent_config()
    try:
        await cfg_service.set_value(key, body.value, current_user.id, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Return updated row
    row = await db.scalar(
        select(AgentConfiguration).where(AgentConfiguration.key == key)
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Config key not found: {key}",
        )
    return ConfigEntry(
        key=row.key,
        value=row.value,
        value_type=row.value_type,
        category=row.category,
        description=row.description,
        min_value=row.min_value,
        max_value=row.max_value,
    )


@router.post("/agent-config/reset")
async def reset_agent_configs(
    current_user: User = Depends(require_developer),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reset all agent configurations to their seed defaults.

    Deletes all existing rows and re-inserts the default seed data.
    Requires developer access.
    """
    from sqlalchemy import delete

    # Delete all existing configs
    await db.execute(delete(AgentConfiguration))

    # Re-insert seed defaults
    for row_data in _SEED_DEFAULTS:
        db.add(AgentConfiguration(**row_data))

    await db.commit()

    # Invalidate cache
    cfg_service = get_agent_config()
    await cfg_service.invalidate()

    return {"status": "ok", "message": f"Reset {len(_SEED_DEFAULTS)} configurations to defaults"}


# ---------------------------------------------------------------------------
# Seed defaults (shared with migration for reset endpoint)
# ---------------------------------------------------------------------------

_SEED_DEFAULTS: list[dict[str, Any]] = [
    # agent
    {"key": "agent.max_iterations", "value": "25", "value_type": "int", "category": "agent", "description": "Max ReAct loop iterations per request", "min_value": "1", "max_value": "100"},
    {"key": "agent.max_tool_calls", "value": "50", "value_type": "int", "category": "agent", "description": "Max total tool invocations per request", "min_value": "1", "max_value": "200"},
    {"key": "agent.max_llm_calls", "value": "25", "value_type": "int", "category": "agent", "description": "Max LLM invocations per request", "min_value": "1", "max_value": "100"},
    {"key": "agent.max_clarify_rounds", "value": "3", "value_type": "int", "category": "agent", "description": "Max clarification rounds", "min_value": "0", "max_value": "10"},
    {"key": "agent.temperature", "value": "0.1", "value_type": "float", "category": "agent", "description": "LLM temperature", "min_value": "0.0", "max_value": "2.0"},
    {"key": "agent.max_tokens", "value": "4096", "value_type": "int", "category": "agent", "description": "LLM max output tokens", "min_value": "100", "max_value": "32000"},
    {"key": "agent.request_timeout", "value": "30", "value_type": "int", "category": "agent", "description": "LLM request timeout (seconds)", "min_value": "5", "max_value": "120"},
    {"key": "agent.context_summarize_threshold", "value": "0.90", "value_type": "float", "category": "agent", "description": "Trigger summarization at this % of context", "min_value": "0.5", "max_value": "0.99"},
    {"key": "agent.recent_window", "value": "12", "value_type": "int", "category": "agent", "description": "Messages to keep unsummarized", "min_value": "4", "max_value": "50"},
    {"key": "agent.summary_max_tokens", "value": "1000", "value_type": "int", "category": "agent", "description": "Max summary output tokens", "min_value": "200", "max_value": "4000"},
    {"key": "agent.summary_timeout", "value": "30", "value_type": "int", "category": "agent", "description": "Summarization LLM call timeout (seconds)", "min_value": "5", "max_value": "120"},
    {"key": "agent.context_window", "value": "128000", "value_type": "int", "category": "agent", "description": "LLM context window size (tokens)", "min_value": "4096", "max_value": "1000000"},
    {"key": "agent.max_tool_output_chars", "value": "8000", "value_type": "int", "category": "agent", "description": "Max chars per tool output", "min_value": "1000", "max_value": "50000"},
    {"key": "agent.max_knowledge_output_chars", "value": "16000", "value_type": "int", "category": "agent", "description": "Max chars for knowledge search output", "min_value": "1000", "max_value": "100000"},
    {"key": "agent.max_concurrent_agents", "value": "50", "value_type": "int", "category": "agent", "description": "Max simultaneous agent graph executions", "min_value": "1", "max_value": "200"},
    {"key": "agent.sql_max_retries", "value": "2", "value_type": "int", "category": "agent", "description": "Max SQL generation retries", "min_value": "0", "max_value": "5"},
    {"key": "agent.selection_threshold", "value": "5", "value_type": "int", "category": "agent", "description": "Knowledge search selection UI threshold", "min_value": "1", "max_value": "20"},
    {"key": "agent.selection_max_items", "value": "20", "value_type": "int", "category": "agent", "description": "Max items in knowledge search selection UI", "min_value": "5", "max_value": "50"},
    {"key": "agent.max_synthesize_rounds", "value": "2", "value_type": "int", "category": "agent", "description": "Maximum re-routing through synthesize node before forcing respond", "min_value": "0", "max_value": "10"},
    # agent_tool
    {"key": "agent_tool.list_tasks_limit", "value": "200", "value_type": "int", "category": "agent_tool", "description": "Max tasks returned by list_tasks", "min_value": "10", "max_value": "1000"},
    {"key": "agent_tool.comments_limit", "value": "200", "value_type": "int", "category": "agent_tool", "description": "Max comments returned", "min_value": "10", "max_value": "1000"},
    {"key": "agent_tool.workload_limit", "value": "200", "value_type": "int", "category": "agent_tool", "description": "Max workload items returned", "min_value": "10", "max_value": "1000"},
    {"key": "agent_tool.match_limit", "value": "20", "value_type": "int", "category": "agent_tool", "description": "Max entity name matches", "min_value": "5", "max_value": "100"},
    # sql
    {"key": "sql.statement_timeout_ms", "value": "5000", "value_type": "int", "category": "sql", "description": "PostgreSQL statement timeout (ms)", "min_value": "1000", "max_value": "30000"},
    {"key": "sql.app_query_timeout_s", "value": "6.0", "value_type": "float", "category": "sql", "description": "App-level query timeout (seconds)", "min_value": "1.0", "max_value": "30.0"},
    {"key": "sql.max_limit", "value": "100", "value_type": "int", "category": "sql", "description": "Max LIMIT in generated queries", "min_value": "10", "max_value": "1000"},
    # embedding
    {"key": "embedding.min_chunk_tokens", "value": "500", "value_type": "int", "category": "embedding", "description": "Min tokens per chunk", "min_value": "100", "max_value": "2000"},
    {"key": "embedding.max_chunk_tokens", "value": "800", "value_type": "int", "category": "embedding", "description": "Max tokens per chunk", "min_value": "200", "max_value": "4000"},
    {"key": "embedding.canvas_proximity_threshold", "value": "300.0", "value_type": "float", "category": "embedding", "description": "Canvas proximity grouping (pixels)", "min_value": "50.0", "max_value": "1000.0"},
    {"key": "embedding.max_cluster_elements", "value": "500", "value_type": "int", "category": "embedding", "description": "Max elements per canvas cluster", "min_value": "50", "max_value": "5000"},
    {"key": "embedding.max_images_per_document", "value": "10", "value_type": "int", "category": "embedding", "description": "Max images to process per document", "min_value": "1", "max_value": "50"},
    # rate_limit
    {"key": "rate_limit.ai_chat", "value": "30,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.ai_query", "value": "30,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.ai_embed", "value": "100,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.ai_import", "value": "10,3600", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.ai_reindex", "value": "20,3600", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.ai_test", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.session_crud", "value": "120,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.session_summarize", "value": "5,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.auth_login", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.auth_register", "value": "5,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.auth_verify", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.auth_reset", "value": "5,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.web_search", "value": "20,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    {"key": "rate_limit.web_scrape", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds"},
    # stream
    {"key": "stream.overall_timeout_s", "value": "300", "value_type": "int", "category": "stream", "description": "Max total stream duration (5 min)", "min_value": "60", "max_value": "600"},
    {"key": "stream.idle_timeout_s", "value": "60", "value_type": "int", "category": "stream", "description": "Max gap between stream chunks", "min_value": "10", "max_value": "120"},
    {"key": "stream.max_chunks", "value": "2000", "value_type": "int", "category": "stream", "description": "Max chunks per streamed response", "min_value": "100", "max_value": "10000"},
    {"key": "stream.thread_owner_ttl", "value": "86400", "value_type": "int", "category": "stream", "description": "Thread ownership TTL (24h)", "min_value": "3600", "max_value": "604800"},
    # websocket
    {"key": "websocket.receive_timeout", "value": "45", "value_type": "int", "category": "websocket", "description": "Message receive timeout (seconds)", "min_value": "10", "max_value": "120"},
    {"key": "websocket.ping_interval", "value": "30", "value_type": "int", "category": "websocket", "description": "Server ping interval (seconds)", "min_value": "10", "max_value": "60"},
    {"key": "websocket.token_revalidation_interval", "value": "1800", "value_type": "int", "category": "websocket", "description": "Token re-validation (30 min)", "min_value": "300", "max_value": "7200"},
    {"key": "websocket.rate_limit_messages", "value": "100", "value_type": "int", "category": "websocket", "description": "Max messages per rate window", "min_value": "10", "max_value": "1000"},
    {"key": "websocket.rate_limit_window", "value": "10", "value_type": "int", "category": "websocket", "description": "Rate limit window (seconds)", "min_value": "1", "max_value": "60"},
    {"key": "websocket.presence_ttl", "value": "45", "value_type": "int", "category": "websocket", "description": "Presence TTL in Redis", "min_value": "10", "max_value": "120"},
    {"key": "websocket.batch_size", "value": "50", "value_type": "int", "category": "websocket", "description": "Messages per broadcast batch", "min_value": "10", "max_value": "200"},
    # search
    {"key": "search.max_content_length", "value": "300000", "value_type": "int", "category": "search", "description": "Max content for indexing", "min_value": "10000", "max_value": "1000000"},
    {"key": "search.scope_cache_ttl", "value": "30", "value_type": "int", "category": "search", "description": "RBAC scope filter cache TTL", "min_value": "5", "max_value": "300"},
    {"key": "search.snippet_context_chars", "value": "60", "value_type": "int", "category": "search", "description": "Context chars for snippets", "min_value": "20", "max_value": "200"},
    {"key": "search.circuit_failure_threshold", "value": "3", "value_type": "int", "category": "search", "description": "Failures before circuit opens", "min_value": "1", "max_value": "10"},
    {"key": "search.circuit_open_seconds", "value": "30", "value_type": "int", "category": "search", "description": "Circuit breaker open duration", "min_value": "5", "max_value": "120"},
    # file
    {"key": "file.max_upload_size", "value": "104857600", "value_type": "int", "category": "file", "description": "Max file upload (100MB)", "min_value": "1048576", "max_value": "524288000"},
    {"key": "file.max_image_size", "value": "10485760", "value_type": "int", "category": "file", "description": "Max image upload (10MB)", "min_value": "1048576", "max_value": "52428800"},
    {"key": "file.max_import_size", "value": "52428800", "value_type": "int", "category": "file", "description": "Max import file (50MB)", "min_value": "1048576", "max_value": "524288000"},
    {"key": "file.max_chat_images", "value": "5", "value_type": "int", "category": "file", "description": "Max images per chat request", "min_value": "1", "max_value": "20"},
    # worker
    {"key": "worker.archive_after_days", "value": "7", "value_type": "int", "category": "worker", "description": "Archive Done tasks after N days", "min_value": "1", "max_value": "90"},
    {"key": "worker.embed_timeout_s", "value": "30", "value_type": "int", "category": "worker", "description": "Per-document embedding timeout", "min_value": "5", "max_value": "120"},
    {"key": "worker.max_embed_retries", "value": "3", "value_type": "int", "category": "worker", "description": "Embedding retry attempts", "min_value": "0", "max_value": "10"},
    {"key": "worker.nightly_embed_batch_size", "value": "10", "value_type": "int", "category": "worker", "description": "Nightly embedding batch size", "min_value": "1", "max_value": "100"},
    {"key": "worker.nightly_embed_batch_delay_s", "value": "5", "value_type": "int", "category": "worker", "description": "Delay between batches", "min_value": "1", "max_value": "60"},
    {"key": "worker.max_nightly_embed", "value": "500", "value_type": "int", "category": "worker", "description": "Max docs per nightly embed", "min_value": "10", "max_value": "5000"},
    {"key": "worker.max_concurrent_imports", "value": "5", "value_type": "int", "category": "worker", "description": "Max concurrent import jobs", "min_value": "1", "max_value": "20"},
    # cache
    {"key": "cache.document_lock_ttl", "value": "300", "value_type": "int", "category": "cache", "description": "Document lock TTL (5 min)", "min_value": "30", "max_value": "1800"},
    {"key": "cache.user_cache_ttl", "value": "300", "value_type": "int", "category": "cache", "description": "User/role cache TTL (5 min)", "min_value": "30", "max_value": "1800"},
    {"key": "cache.user_cache_max_size", "value": "10000", "value_type": "int", "category": "cache", "description": "Max cache entries", "min_value": "100", "max_value": "100000"},
    {"key": "cache.room_auth_ttl", "value": "300", "value_type": "int", "category": "cache", "description": "Room auth cache TTL", "min_value": "30", "max_value": "1800"},
    {"key": "cache.room_auth_max_size", "value": "50000", "value_type": "int", "category": "cache", "description": "Room auth max entries", "min_value": "1000", "max_value": "200000"},
    {"key": "cache.rbac_context_ttl", "value": "30", "value_type": "int", "category": "cache", "description": "Agent RBAC context cache TTL", "min_value": "5", "max_value": "300"},
    # web
    {"key": "web.scrape_timeout", "value": "10", "value_type": "int", "category": "web", "description": "URL fetch timeout (seconds)", "min_value": "3", "max_value": "30"},
    {"key": "web.scrape_max_bytes", "value": "2097152", "value_type": "int", "category": "web", "description": "Max response body (2MB)", "min_value": "102400", "max_value": "10485760"},
    # prompt
    {"key": "prompt.custom_addendum", "value": "", "value_type": "str", "category": "prompt", "description": "Custom instructions appended to system prompt"},
    {"key": "prompt.agent_name", "value": "Blair", "value_type": "str", "category": "prompt", "description": "AI agent display name"},
    {"key": "prompt.communication_style", "value": "concise", "value_type": "str", "category": "prompt", "description": "Style: concise, detailed, friendly"},
    # export
    {"key": "export.excel_ttl_seconds", "value": "3600", "value_type": "int", "category": "export", "description": "Excel download TTL (1 hour)", "min_value": "300", "max_value": "86400"},
    {"key": "export.pdf_ttl_seconds", "value": "3600", "value_type": "int", "category": "export", "description": "PDF download TTL (1 hour)", "min_value": "300", "max_value": "86400"},
    # content
    {"key": "content.max_recursion_depth", "value": "100", "value_type": "int", "category": "content", "description": "Max recursion for content tree", "min_value": "10", "max_value": "500"},
    {"key": "content.max_node_count", "value": "50000", "value_type": "int", "category": "content", "description": "Max nodes in document tree", "min_value": "1000", "max_value": "200000"},
]
