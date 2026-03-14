"""Add AgentConfigurations table with seed data.

Revision ID: 20260307_add_agent_config
Revises: 20260306_add_chat_sessions
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260307_add_agent_config"
down_revision = "20260306_add_chat_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    agent_configs = op.create_table(
        "AgentConfigurations",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("value_type", sa.String(10), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("min_value", sa.String(50)),
        sa.Column("max_value", sa.String(50)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("Users.id")),
        sa.CheckConstraint(
            "value_type IN ('int', 'float', 'str', 'bool')",
            name="ck_agent_config_value_type",
        ),
    )

    # Seed rows
    op.bulk_insert(agent_configs, [
        # ── agent (14 rows) ──
        {"key": "agent.max_iterations", "value": "25", "value_type": "int", "category": "agent", "description": "Max ReAct loop iterations per request", "min_value": "1", "max_value": "100"},
        {"key": "agent.max_tool_calls", "value": "50", "value_type": "int", "category": "agent", "description": "Max total tool invocations per request", "min_value": "1", "max_value": "200"},
        {"key": "agent.max_llm_calls", "value": "25", "value_type": "int", "category": "agent", "description": "Max LLM invocations per request", "min_value": "1", "max_value": "100"},
        {"key": "agent.max_clarify_rounds", "value": "3", "value_type": "int", "category": "agent", "description": "Max clarification rounds", "min_value": "1", "max_value": "10"},
        {"key": "agent.temperature", "value": "0.1", "value_type": "float", "category": "agent", "description": "LLM temperature", "min_value": "0.0", "max_value": "2.0"},
        {"key": "agent.max_tokens", "value": "4096", "value_type": "int", "category": "agent", "description": "LLM max output tokens", "min_value": "100", "max_value": "32000"},
        {"key": "agent.request_timeout", "value": "30", "value_type": "int", "category": "agent", "description": "LLM request timeout (seconds)", "min_value": "5", "max_value": "120"},
        {"key": "agent.context_summarize_threshold", "value": "0.90", "value_type": "float", "category": "agent", "description": "Trigger summarization at this % of context", "min_value": "0.5", "max_value": "0.99"},
        {"key": "agent.recent_window", "value": "12", "value_type": "int", "category": "agent", "description": "Messages to keep unsummarized", "min_value": "4", "max_value": "50"},
        {"key": "agent.summary_max_tokens", "value": "1000", "value_type": "int", "category": "agent", "description": "Max summary output tokens", "min_value": "200", "max_value": "4000"},
        {"key": "agent.max_tool_output_chars", "value": "8000", "value_type": "int", "category": "agent", "description": "Max chars per tool output", "min_value": "1000", "max_value": "50000"},
        {"key": "agent.max_knowledge_output_chars", "value": "16000", "value_type": "int", "category": "agent", "description": "Max chars for knowledge search output", "min_value": "1000", "max_value": "100000"},
        {"key": "agent.max_concurrent_agents", "value": "50", "value_type": "int", "category": "agent", "description": "Max simultaneous agent graph executions", "min_value": "1", "max_value": "200"},
        {"key": "agent.sql_max_retries", "value": "2", "value_type": "int", "category": "agent", "description": "Max SQL generation retries", "min_value": "0", "max_value": "5"},
        # ── agent_tool (4 rows) ──
        {"key": "agent_tool.list_tasks_limit", "value": "200", "value_type": "int", "category": "agent_tool", "description": "Max tasks returned by list_tasks", "min_value": "10", "max_value": "1000"},
        {"key": "agent_tool.comments_limit", "value": "200", "value_type": "int", "category": "agent_tool", "description": "Max comments returned", "min_value": "10", "max_value": "1000"},
        {"key": "agent_tool.workload_limit", "value": "200", "value_type": "int", "category": "agent_tool", "description": "Max workload items returned", "min_value": "10", "max_value": "1000"},
        {"key": "agent_tool.match_limit", "value": "20", "value_type": "int", "category": "agent_tool", "description": "Max entity name matches", "min_value": "5", "max_value": "100"},
        # ── sql (3 rows) ──
        {"key": "sql.statement_timeout_ms", "value": "5000", "value_type": "int", "category": "sql", "description": "PostgreSQL statement timeout (ms)", "min_value": "1000", "max_value": "30000"},
        {"key": "sql.app_query_timeout_s", "value": "6.0", "value_type": "float", "category": "sql", "description": "App-level query timeout (seconds)", "min_value": "1.0", "max_value": "30.0"},
        {"key": "sql.max_limit", "value": "100", "value_type": "int", "category": "sql", "description": "Max LIMIT in generated queries", "min_value": "10", "max_value": "1000"},
        # ── embedding (5 rows) ──
        {"key": "embedding.min_chunk_tokens", "value": "500", "value_type": "int", "category": "embedding", "description": "Min tokens per chunk", "min_value": "100", "max_value": "2000"},
        {"key": "embedding.max_chunk_tokens", "value": "800", "value_type": "int", "category": "embedding", "description": "Max tokens per chunk", "min_value": "200", "max_value": "4000"},
        {"key": "embedding.canvas_proximity_threshold", "value": "300.0", "value_type": "float", "category": "embedding", "description": "Canvas proximity grouping (pixels)", "min_value": "50.0", "max_value": "1000.0"},
        {"key": "embedding.max_cluster_elements", "value": "500", "value_type": "int", "category": "embedding", "description": "Max elements per canvas cluster", "min_value": "50", "max_value": "5000"},
        {"key": "embedding.max_images_per_document", "value": "10", "value_type": "int", "category": "embedding", "description": "Max images to process per document", "min_value": "1", "max_value": "50"},
        # ── rate_limit (14 rows) ──
        {"key": "rate_limit.ai_chat", "value": "30,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.ai_query", "value": "30,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.ai_embed", "value": "100,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.ai_import", "value": "10,3600", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.ai_reindex", "value": "20,3600", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.ai_test", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.session_crud", "value": "120,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.session_summarize", "value": "5,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.auth_login", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.auth_register", "value": "5,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.auth_verify", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.auth_reset", "value": "5,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.web_search", "value": "20,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        {"key": "rate_limit.web_scrape", "value": "10,60", "value_type": "str", "category": "rate_limit", "description": "limit,window_seconds", "min_value": None, "max_value": None},
        # ── stream (4 rows) ──
        {"key": "stream.overall_timeout_s", "value": "300", "value_type": "int", "category": "stream", "description": "Max total stream duration (5 min)", "min_value": "60", "max_value": "600"},
        {"key": "stream.idle_timeout_s", "value": "60", "value_type": "int", "category": "stream", "description": "Max gap between stream chunks", "min_value": "10", "max_value": "120"},
        {"key": "stream.max_chunks", "value": "2000", "value_type": "int", "category": "stream", "description": "Max chunks per streamed response", "min_value": "100", "max_value": "10000"},
        {"key": "stream.thread_owner_ttl", "value": "86400", "value_type": "int", "category": "stream", "description": "Thread ownership TTL (24h)", "min_value": "3600", "max_value": "604800"},
        # ── websocket (7 rows) ──
        {"key": "websocket.receive_timeout", "value": "45", "value_type": "int", "category": "websocket", "description": "Message receive timeout (seconds)", "min_value": "10", "max_value": "120"},
        {"key": "websocket.ping_interval", "value": "30", "value_type": "int", "category": "websocket", "description": "Server ping interval (seconds)", "min_value": "10", "max_value": "60"},
        {"key": "websocket.token_revalidation_interval", "value": "1800", "value_type": "int", "category": "websocket", "description": "Token re-validation (30 min)", "min_value": "300", "max_value": "7200"},
        {"key": "websocket.rate_limit_messages", "value": "100", "value_type": "int", "category": "websocket", "description": "Max messages per rate window", "min_value": "10", "max_value": "1000"},
        {"key": "websocket.rate_limit_window", "value": "10", "value_type": "int", "category": "websocket", "description": "Rate limit window (seconds)", "min_value": "1", "max_value": "60"},
        {"key": "websocket.presence_ttl", "value": "45", "value_type": "int", "category": "websocket", "description": "Presence TTL in Redis", "min_value": "10", "max_value": "120"},
        {"key": "websocket.batch_size", "value": "50", "value_type": "int", "category": "websocket", "description": "Messages per broadcast batch", "min_value": "10", "max_value": "200"},
        # ── search (5 rows) ──
        {"key": "search.max_content_length", "value": "300000", "value_type": "int", "category": "search", "description": "Max content for indexing", "min_value": "10000", "max_value": "1000000"},
        {"key": "search.scope_cache_ttl", "value": "30", "value_type": "int", "category": "search", "description": "RBAC scope filter cache TTL", "min_value": "5", "max_value": "300"},
        {"key": "search.snippet_context_chars", "value": "60", "value_type": "int", "category": "search", "description": "Context chars for snippets", "min_value": "20", "max_value": "200"},
        {"key": "search.circuit_failure_threshold", "value": "3", "value_type": "int", "category": "search", "description": "Failures before circuit opens", "min_value": "1", "max_value": "10"},
        {"key": "search.circuit_open_seconds", "value": "30", "value_type": "int", "category": "search", "description": "Circuit breaker open duration", "min_value": "5", "max_value": "120"},
        # ── file (4 rows) ──
        {"key": "file.max_upload_size", "value": "104857600", "value_type": "int", "category": "file", "description": "Max file upload (100MB)", "min_value": "1048576", "max_value": "524288000"},
        {"key": "file.max_image_size", "value": "10485760", "value_type": "int", "category": "file", "description": "Max image upload (10MB)", "min_value": "1048576", "max_value": "52428800"},
        {"key": "file.max_import_size", "value": "52428800", "value_type": "int", "category": "file", "description": "Max import file (50MB)", "min_value": "1048576", "max_value": "524288000"},
        {"key": "file.max_chat_images", "value": "5", "value_type": "int", "category": "file", "description": "Max images per chat request", "min_value": "1", "max_value": "20"},
        # ── worker (7 rows) ──
        {"key": "worker.archive_after_days", "value": "7", "value_type": "int", "category": "worker", "description": "Archive Done tasks after N days", "min_value": "1", "max_value": "90"},
        {"key": "worker.embed_timeout_s", "value": "30", "value_type": "int", "category": "worker", "description": "Per-document embedding timeout", "min_value": "5", "max_value": "120"},
        {"key": "worker.max_embed_retries", "value": "3", "value_type": "int", "category": "worker", "description": "Embedding retry attempts", "min_value": "0", "max_value": "10"},
        {"key": "worker.nightly_embed_batch_size", "value": "10", "value_type": "int", "category": "worker", "description": "Nightly embedding batch size", "min_value": "1", "max_value": "100"},
        {"key": "worker.nightly_embed_batch_delay_s", "value": "5", "value_type": "int", "category": "worker", "description": "Delay between batches", "min_value": "1", "max_value": "60"},
        {"key": "worker.max_nightly_embed", "value": "500", "value_type": "int", "category": "worker", "description": "Max docs per nightly embed", "min_value": "10", "max_value": "5000"},
        {"key": "worker.max_concurrent_imports", "value": "5", "value_type": "int", "category": "worker", "description": "Max concurrent import jobs", "min_value": "1", "max_value": "20"},
        # ── cache (6 rows) ──
        {"key": "cache.document_lock_ttl", "value": "300", "value_type": "int", "category": "cache", "description": "Document lock TTL (5 min)", "min_value": "30", "max_value": "1800"},
        {"key": "cache.user_cache_ttl", "value": "300", "value_type": "int", "category": "cache", "description": "User/role cache TTL (5 min)", "min_value": "30", "max_value": "1800"},
        {"key": "cache.user_cache_max_size", "value": "10000", "value_type": "int", "category": "cache", "description": "Max cache entries", "min_value": "100", "max_value": "100000"},
        {"key": "cache.room_auth_ttl", "value": "300", "value_type": "int", "category": "cache", "description": "Room auth cache TTL", "min_value": "30", "max_value": "1800"},
        {"key": "cache.room_auth_max_size", "value": "50000", "value_type": "int", "category": "cache", "description": "Room auth max entries", "min_value": "1000", "max_value": "200000"},
        {"key": "cache.rbac_context_ttl", "value": "30", "value_type": "int", "category": "cache", "description": "Agent RBAC context cache TTL", "min_value": "5", "max_value": "300"},
        # ── web (2 rows) ──
        {"key": "web.scrape_timeout", "value": "10", "value_type": "int", "category": "web", "description": "URL fetch timeout (seconds)", "min_value": "3", "max_value": "30"},
        {"key": "web.scrape_max_bytes", "value": "2097152", "value_type": "int", "category": "web", "description": "Max response body (2MB)", "min_value": "102400", "max_value": "10485760"},
        # ── prompt (3 rows) ──
        {"key": "prompt.custom_addendum", "value": "", "value_type": "str", "category": "prompt", "description": "Custom instructions appended to system prompt", "min_value": None, "max_value": None},
        {"key": "prompt.agent_name", "value": "Blair", "value_type": "str", "category": "prompt", "description": "AI agent display name", "min_value": None, "max_value": None},
        {"key": "prompt.communication_style", "value": "concise", "value_type": "str", "category": "prompt", "description": "Style: concise, detailed, friendly", "min_value": None, "max_value": None},
        # ── export (1 row) ──
        {"key": "export.excel_ttl_seconds", "value": "3600", "value_type": "int", "category": "export", "description": "Excel download TTL (1 hour)", "min_value": "300", "max_value": "86400"},
        # ── content (2 rows) ──
        {"key": "content.max_recursion_depth", "value": "100", "value_type": "int", "category": "content", "description": "Max recursion for content tree", "min_value": "10", "max_value": "500"},
        {"key": "content.max_node_count", "value": "50000", "value_type": "int", "category": "content", "description": "Max nodes in document tree", "min_value": "1000", "max_value": "200000"},
    ])

    # Copy existing AiSystemPrompt.prompt value into prompt.custom_addendum
    op.execute(
        """
        UPDATE "AgentConfigurations"
        SET value = COALESCE(
            (SELECT prompt FROM ai_system_prompts LIMIT 1),
            ''
        )
        WHERE key = 'prompt.custom_addendum'
        AND EXISTS (SELECT 1 FROM ai_system_prompts WHERE prompt IS NOT NULL AND prompt != '')
        """
    )


def downgrade() -> None:
    op.drop_table("AgentConfigurations")
