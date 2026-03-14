# Blair Agent Expansion — Implementation Plan

**Created**: 2026-03-07
**Branch**: `feature/knowledge-base`
**Status**: Planning

## Overview

Expand Blair AI copilot from 27 tools (22 read + 5 write) to ~50 tools covering full CRUD operations, web research, PDF export, capabilities listing, document-type-aware writing, and auto-context summarization.

### Goals

- Full CRUD: applications, projects, tasks, members, documents, checklists
- Web search + scraping (free, unlimited, no API keys)
- PDF export for knowledge base documents
- "What can you do?" capabilities listing
- Document-type-aware writing (training, research, docs, notes)
- Auto-context summarization (replace silent message trimming)
- All write tools with RBAC enforcement + HITL confirmation

### Design Decisions

1. **All tools bound always** — like Claude Code. ~15K token overhead on 128K = 12%, leaving 88% for conversation.
2. **Auto-summarization at 90%** — replaces silent message dropping. Most infrastructure already exists (frontend UI, backend endpoint, DB fields).
3. **Explicit `doc_type` param** — writing guidelines in tool docstring (zero system prompt overhead).
4. **HITL pattern** — all writes use existing `interrupt()` + pre/post-interrupt RBAC checks.
5. **Runtime-configurable constants** — all tunable values (safety limits, thresholds, rate limits, timeouts) stored in a PostgreSQL `AgentConfigurations` table with in-memory caching + Redis pub/sub invalidation. Update values via SQL without redeploying.

---

## Existing Infrastructure (Already Built)

| Component | File | What It Does |
|-----------|------|-------------|
| HITL pattern | `tools/write_tools.py` | interrupt() + RBAC pre/post checks — template for all new write tools |
| Entity resolution | `tools/helpers.py` | `_resolve_project()`, `_resolve_task()`, etc. — fuzzy UUID/name matching |
| Tool context | `tools/context.py` | Per-request contextvars: user_id, accessible IDs, RBAC helpers |
| Rate limiter | `rate_limiter.py` | Redis sliding window + in-memory fallback |
| Output helpers | `tools/helpers.py` | `_truncate()`, `_format_date()`, `_wrap_user_content()` |
| Summarize endpoint | `chat_sessions.py:328-417` | LLM-based conversation summarization with prompt injection protection |
| Summary UI | `context-summary-divider.tsx` | Expandable "Context summarized" horizontal divider |
| Summary state | `use-ai-sidebar.ts:33` | `contextSummary` + `summarizedAtSequence` in sidebar store |
| Summary prepend | `use-ai-chat.ts:722-728` | Prepends context summary to messages when sending |
| Infinite scroll | `ai-sidebar.tsx:200-245` | IntersectionObserver + fetchNextPage + scroll position preservation |
| Token usage SSE | `types.ts:178-181` | `TokenUsageEvent` already streams token counts to frontend |

---

## Phase -1: Runtime Configuration Table

Move all hardcoded agent constants to a PostgreSQL key-value table so they can be updated at runtime without code changes.

### Problem

Currently, ~30 tunable values are scattered across 6+ files as Python constants:

| File | Constants |
|------|-----------|
| `agent/constants.py` | MAX_ITERATIONS=25, MAX_TOOL_CALLS=50, MAX_LLM_CALLS=25, MAX_CLARIFY_ROUNDS=3, AGENT_TEMPERATURE=0.1, AGENT_MAX_TOKENS=4096, AGENT_REQUEST_TIMEOUT=30 |
| `agent/constants.py` (new) | CONTEXT_SUMMARIZE_THRESHOLD=0.90, RECENT_WINDOW=12, SUMMARY_MAX_TOKENS=1000 |
| `agent_tools.py` | MAX_TOOL_OUTPUT_CHARS=8000, MAX_KNOWLEDGE_OUTPUT_CHARS=16000 |
| `sql_executor.py` | STATEMENT_TIMEOUT_MS=5000, MAX_ROWS=200 |
| `sql_validator.py` | MAX_LIMIT=100 |
| `rate_limiter.py` | 12+ rate limit entries (ai_chat, ai_query, web_search, etc.) |
| `chunking_service.py` | MIN_TOKENS=500, MAX_TOKENS=800, CANVAS_PROXIMITY_THRESHOLD=300 |

Changing any of these requires a code change + deployment.

### Solution: `AgentConfigurations` Table

#### Table Design

```sql
CREATE TABLE "AgentConfigurations" (
    key         VARCHAR(100) PRIMARY KEY,    -- e.g. "agent.max_tool_calls"
    value       VARCHAR(500) NOT NULL,       -- stored as string, parsed by type
    value_type  VARCHAR(10)  NOT NULL        -- "int", "float", "str", "bool"
                CHECK (value_type IN ('int', 'float', 'str', 'bool')),
    category    VARCHAR(50)  NOT NULL,       -- grouping: "agent", "rate_limit", "embedding", "sql", "web"
    description VARCHAR(500),                -- human-readable explanation
    min_value   VARCHAR(50),                 -- optional validation bound (parsed per value_type)
    max_value   VARCHAR(50),                 -- optional validation bound
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by  UUID         REFERENCES "Users"(id)
);
```

#### Seed Data (~75 rows across 10 categories)

##### Category: `agent` — AI Agent Safety & LLM Config (14 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `agent.max_iterations` | 25 | int | `agent/constants.py:8` | Max ReAct loop iterations per request |
| `agent.max_tool_calls` | 50 | int | `agent/constants.py:9` | Max total tool invocations per request |
| `agent.max_llm_calls` | 25 | int | `agent/constants.py:10` | Max LLM invocations per request |
| `agent.max_clarify_rounds` | 3 | int | `agent/constants.py:11` | Max clarification rounds |
| `agent.temperature` | 0.1 | float | `agent/constants.py:14` | LLM temperature |
| `agent.max_tokens` | 4096 | int | `agent/constants.py:15` | LLM max output tokens |
| `agent.request_timeout` | 30 | int | `agent/constants.py:16` | LLM request timeout (seconds) |
| `agent.context_summarize_threshold` | 0.90 | float | *(new — Phase 1)* | Trigger summarization at this % of context |
| `agent.recent_window` | 12 | int | *(new — Phase 1)* | Messages to keep unsummarized |
| `agent.summary_max_tokens` | 1000 | int | *(new — Phase 1)* | Max summary output tokens |
| `agent.max_tool_output_chars` | 8000 | int | `agent_tools.py:25` | Max chars per tool output |
| `agent.max_knowledge_output_chars` | 16000 | int | `agent_tools.py:27` | Max chars for knowledge search output |
| `agent.max_concurrent_agents` | 50 | int | `routers/ai_chat.py:58` | Max simultaneous agent graph executions |
| `agent.sql_max_retries` | 2 | int | `sql_generator.py:26` | Max SQL generation retries |

##### Category: `agent_tool` — Tool Query Limits (4 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `agent_tool.list_tasks_limit` | 200 | int | `tools/task_tools.py:131` | Max tasks returned by list_tasks |
| `agent_tool.comments_limit` | 200 | int | `tools/task_tools.py:319` | Max comments returned |
| `agent_tool.workload_limit` | 200 | int | `tools/identity_tools.py:139` | Max workload items returned |
| `agent_tool.match_limit` | 20 | int | `tools/helpers.py:199` | Max entity name matches |

##### Category: `sql` — SQL Execution Safety (3 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `sql.statement_timeout_ms` | 5000 | int | `sql_executor.py:27` | PostgreSQL statement timeout (ms) |
| `sql.app_query_timeout_s` | 6.0 | float | `sql_executor.py:28` | App-level query timeout (seconds) |
| `sql.max_limit` | 100 | int | `sql_validator.py:22` | Max LIMIT in generated queries |

##### Category: `embedding` — Chunking & Embedding (5 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `embedding.min_chunk_tokens` | 500 | int | `chunking_service.py:96` | Min tokens per chunk |
| `embedding.max_chunk_tokens` | 800 | int | `chunking_service.py:97` | Max tokens per chunk |
| `embedding.canvas_proximity_threshold` | 300.0 | float | `chunking_service.py:100` | Canvas proximity grouping (pixels) |
| `embedding.max_cluster_elements` | 500 | int | `chunking_service.py:944` | Max elements per canvas cluster |
| `embedding.max_images_per_document` | 10 | int | `image_understanding_service.py:50` | Max images to process per document |

##### Category: `rate_limit` — Rate Limiting (14 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `rate_limit.ai_chat` | 30,60 | str | `rate_limiter.py:155` | limit,window_seconds |
| `rate_limit.ai_query` | 30,60 | str | `rate_limiter.py:156` | limit,window_seconds |
| `rate_limit.ai_embed` | 100,60 | str | `rate_limiter.py:157` | limit,window_seconds |
| `rate_limit.ai_import` | 10,3600 | str | `rate_limiter.py:158` | limit,window_seconds |
| `rate_limit.ai_reindex` | 20,3600 | str | `rate_limiter.py:159` | limit,window_seconds |
| `rate_limit.ai_test` | 10,60 | str | `rate_limiter.py:160` | limit,window_seconds |
| `rate_limit.session_crud` | 120,60 | str | `rate_limiter.py:161` | limit,window_seconds |
| `rate_limit.session_summarize` | 5,60 | str | `rate_limiter.py:162` | limit,window_seconds |
| `rate_limit.auth_login` | 10,60 | str | `rate_limiter.py:163` | limit,window_seconds |
| `rate_limit.auth_register` | 5,60 | str | `rate_limiter.py:164` | limit,window_seconds |
| `rate_limit.auth_verify` | 10,60 | str | `rate_limiter.py:165` | limit,window_seconds |
| `rate_limit.auth_reset` | 5,60 | str | `rate_limiter.py:166` | limit,window_seconds |
| `rate_limit.web_search` | 20,60 | str | *(new — Phase 2)* | limit,window_seconds |
| `rate_limit.web_scrape` | 10,60 | str | *(new — Phase 2)* | limit,window_seconds |

##### Category: `stream` — SSE Streaming Limits (4 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `stream.overall_timeout_s` | 300 | int | `routers/ai_chat.py:53` | Max total stream duration (5 min) |
| `stream.idle_timeout_s` | 60 | int | `routers/ai_chat.py:54` | Max gap between stream chunks |
| `stream.max_chunks` | 2000 | int | `routers/ai_chat.py:55` | Max chunks per streamed response |
| `stream.thread_owner_ttl` | 86400 | int | `routers/ai_chat.py:88` | Thread ownership TTL (24h) |

##### Category: `websocket` — WebSocket & Presence (7 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `websocket.receive_timeout` | 45 | int | `main.py:537` | Message receive timeout (seconds) |
| `websocket.ping_interval` | 30 | int | `main.py:538` | Server ping interval (seconds) |
| `websocket.token_revalidation_interval` | 1800 | int | `main.py:539` | Token re-validation (30 min) |
| `websocket.rate_limit_messages` | 100 | int | `main.py:540` | Max messages per rate window |
| `websocket.rate_limit_window` | 10 | int | `main.py:541` | Rate limit window (seconds) |
| `websocket.presence_ttl` | 45 | int | `websocket/presence.py:23` | Presence TTL in Redis |
| `websocket.batch_size` | 50 | int | `websocket/manager.py:268` | Messages per broadcast batch |

##### Category: `search` — Meilisearch & Full-Text (5 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `search.max_content_length` | 300000 | int | `services/search_service.py:41` | Max content for indexing |
| `search.scope_cache_ttl` | 30 | int | `services/search_service.py:44` | RBAC scope filter cache TTL |
| `search.snippet_context_chars` | 60 | int | `services/search_service.py:47` | Context chars for snippets |
| `search.circuit_failure_threshold` | 3 | int | `services/search_service.py:101` | Failures before circuit opens |
| `search.circuit_open_seconds` | 30 | int | `services/search_service.py:102` | Circuit breaker open duration |

##### Category: `file` — File Upload & Processing (4 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `file.max_upload_size` | 104857600 | int | `routers/files.py:42` | Max file upload (100MB) |
| `file.max_image_size` | 10485760 | int | `routers/files.py:44` | Max image upload (10MB) |
| `file.max_import_size` | 52428800 | int | `routers/ai_import.py:38` | Max import file (50MB) |
| `file.max_chat_images` | 5 | int | `routers/ai_chat.py:48` | Max images per chat request |

##### Category: `worker` — Background Jobs (7 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `worker.archive_after_days` | 7 | int | `worker.py:53` | Archive Done tasks after N days |
| `worker.embed_timeout_s` | 30 | int | `worker.py:339` | Per-document embedding timeout |
| `worker.max_embed_retries` | 3 | int | `worker.py:340` | Embedding retry attempts |
| `worker.nightly_embed_batch_size` | 10 | int | `worker.py:569` | Nightly embedding batch size |
| `worker.nightly_embed_batch_delay_s` | 5 | int | `worker.py:570` | Delay between batches |
| `worker.max_nightly_embed` | 500 | int | `worker.py:571` | Max docs per nightly embed |
| `worker.max_concurrent_imports` | 5 | int | `worker.py:653` | Max concurrent import jobs |

##### Category: `cache` — Cache TTLs & Sizes (6 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `cache.document_lock_ttl` | 300 | int | `services/document_lock_service.py:24` | Document lock TTL (5 min) |
| `cache.user_cache_ttl` | 300 | int | `services/user_cache_service.py:24` | User/role cache TTL (5 min) |
| `cache.user_cache_max_size` | 10000 | int | `services/user_cache_service.py:25` | Max cache entries |
| `cache.room_auth_ttl` | 300 | int | `websocket/room_auth.py:37` | Room auth cache TTL |
| `cache.room_auth_max_size` | 50000 | int | `websocket/room_auth.py:38` | Room auth max entries |
| `cache.rbac_context_ttl` | 30 | int | `agent/rbac_context.py:30` | Agent RBAC context cache TTL |

##### Category: `web` — Web Scraping (2 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `web.scrape_timeout` | 10 | int | *(new — Phase 2)* | URL fetch timeout (seconds) |
| `web.scrape_max_bytes` | 2097152 | int | *(new — Phase 2)* | Max response body (2MB) |

##### Category: `prompt` — System Prompt (3 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `prompt.custom_addendum` | *(empty)* | str | `agent/prompts.py:191` | Custom instructions appended to system prompt |
| `prompt.agent_name` | Blair | str | `agent/prompts.py:13` | AI agent display name |
| `prompt.communication_style` | concise | str | `agent/prompts.py:71` | Style: "concise", "detailed", "friendly" |

##### Category: `export` — Data Export (1 row)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `export.excel_ttl_seconds` | 3600 | int | `excel_export.py:24` | Excel download TTL (1 hour) |

##### Category: `content` — Content Processing Safety (2 rows)

| Key | Value | Type | Source File | Description |
|-----|-------|------|-------------|-------------|
| `content.max_recursion_depth` | 100 | int | `services/content_converter.py:39` | Max recursion for content tree |
| `content.max_node_count` | 50000 | int | `services/content_converter.py:40` | Max nodes in document tree |

**Total: ~75 seed rows across 13 categories**

#### Excluded from DB config (stay hardcoded or in env vars)

| Constant | File | Reason |
|----------|------|--------|
| JWT algorithm (`HS256`) | `config.py:39` | Cryptographic — changing at runtime could break all sessions |
| JWT expiration times | `config.py:40-42` | Already env-configurable, security-sensitive |
| DB pool sizes | `config.py:27-28` | Requires connection pool rebuild — restart needed |
| Redis URL/pool | `config.py:54-56` | Infrastructure — needs restart to reconnect |
| SMTP settings | `config.py:109-115` | Already env-configurable |
| Meilisearch URL/key | `config.py:103-104` | Infrastructure — needs restart |
| Default status names (`Todo`, `In Progress`...) | `write_tools.py:56-62` | Schema convention — not tunable |
| `_INMEMORY_*` fallback limits | `rate_limiter.py` | Internal safety nets — not user-facing |
| `MIN_COL_WIDTH`/`MAX_COL_WIDTH` | `excel_export.py` | UI cosmetic — not worth configuring |
| `_MAX_ERROR_LENGTH` | `telemetry.py:65` | Debug detail — not user-facing |

#### System Prompt Configurability

The system prompt has three layers:

```
┌─────────────────────────────────────────────────┐
│  1. BASE PROMPT (hardcoded in prompts.py)        │  ← NOT editable at runtime
│     - Security rules (never trust user content)  │     (tied to code/tool definitions)
│     - Tool documentation (names, args, usage)    │
│     - Message protocol (parallel calls, etc.)    │
├─────────────────────────────────────────────────┤
│  2. CONFIGURABLE SECTIONS (from config table)    │  ← Editable at runtime
│     - prompt.agent_name: "Blair" → "Atlas"       │
│     - prompt.communication_style: tone/verbosity │
├─────────────────────────────────────────────────┤
│  3. CUSTOM ADDENDUM (from config table)          │  ← Editable at runtime
│     - prompt.custom_addendum: free-text appended │
│       after base prompt (replaces AiSystemPrompt │
│       single-row table)                          │
└─────────────────────────────────────────────────┘
```

**Why not make the entire prompt editable?**
- The base prompt contains **security boundaries** (`[USER CONTENT]` tag handling, RBAC enforcement instructions) — making these editable risks accidental or malicious removal
- Tool documentation in the prompt **must match the actual tool signatures** — editing it without updating code creates mismatches that break the agent
- The base prompt is ~4K tokens of carefully audited text across 9 review rounds

**What IS editable at runtime:**

| Config Key | Example Update | Effect |
|-----------|---------------|--------|
| `prompt.agent_name` | `SET value = 'Atlas'` | Changes "You are Blair" → "You are Atlas" everywhere in the prompt |
| `prompt.communication_style` | `SET value = 'detailed'` | Switches from "Be concise and direct" to "Provide thorough explanations" |
| `prompt.custom_addendum` | `SET value = 'Always greet users by name. Prefer tables over bullet lists.'` | Appended as `## Custom Instructions` section at end of system prompt |

**Implementation in `prompts.py`:**
```python
async def load_system_prompt(db: Any) -> str:
    config = get_agent_config()

    # Inject configurable values into base prompt
    agent_name = config.get_str("prompt.agent_name", "Blair")
    style = config.get_str("prompt.communication_style", "concise")
    prompt = SYSTEM_PROMPT.replace("You are Blair", f"You are {agent_name}")

    # Apply communication style
    style_directives = {
        "concise": "Be concise and direct. No filler, no preamble.",
        "detailed": "Provide thorough, detailed explanations. Include context and reasoning.",
        "friendly": "Be warm and conversational. Use a friendly, approachable tone.",
    }
    directive = style_directives.get(style, style_directives["concise"])
    prompt = prompt.replace(
        "Be concise and direct. No filler, no preamble.",
        directive,
    )

    # Append custom addendum (replaces old AiSystemPrompt table)
    addendum = config.get_str("prompt.custom_addendum", "")
    if addendum.strip():
        prompt += f"\n\n## Custom Instructions\n\n{addendum}"

    return prompt
```

**Migration note:** The existing `ai_system_prompts` table (single-row `AiSystemPrompt` model) is superseded by `prompt.custom_addendum` in the config table. The migration should:
1. Copy any existing `AiSystemPrompt.prompt` value into `prompt.custom_addendum`
2. Keep the old table for backward compatibility (mark as deprecated)

#### Caching Architecture

```
┌──────────────┐    cache miss     ┌────────────┐
│  Python      │ ───────────────→  │  PostgreSQL │
│  dict cache  │ ←───────────────  │  table      │
│  (in-memory) │    query result   │             │
└──────┬───────┘                   └────────────┘
       │                                  │
       │  Redis pub/sub                   │  UPDATE trigger
       │  "agent_config_changed"          │  (optional)
       ▼                                  ▼
  invalidate cache              Redis PUBLISH "agent_config_changed"
  on next access                  (via SQL or service)
```

- **In-memory dict** — loaded once at startup, refreshed on cache miss or invalidation
- **TTL**: 5 minutes (safety net — even without Redis pub/sub, configs refresh within 5 min)
- **Redis pub/sub** channel `agent_config_changed` — instant invalidation across all workers
- **Fallback**: hardcoded defaults in Python if DB is unreachable (same values as seed data)
- **Thread-safe**: `asyncio.Lock` guards cache refresh to prevent thundering herd

#### Service API

```python
# fastapi-backend/app/ai/config_service.py

class AgentConfigService:
    """Runtime configuration with in-memory cache + Redis invalidation."""

    # Typed getters with hardcoded fallback defaults
    def get_int(self, key: str, default: int) -> int: ...
    def get_float(self, key: str, default: float) -> float: ...
    def get_str(self, key: str, default: str) -> str: ...
    def get_rate_limit(self, key: str, default: tuple[int, int]) -> tuple[int, int]: ...

    # Bulk load + cache management
    async def load_all(self) -> None: ...          # DB → cache
    async def invalidate(self) -> None: ...        # Clear cache, publish Redis
    async def subscribe_invalidation(self) -> None: ...  # Listen for Redis pub/sub

    # Update (for admin endpoint)
    async def set_value(self, key: str, value: str, user_id: UUID) -> None: ...
```

#### Usage Pattern (in consuming code)

```python
# Before (hardcoded):
MAX_TOOL_CALLS = 50

# After (runtime):
from app.ai.config_service import get_agent_config
config = get_agent_config()  # module-level singleton
max_calls = config.get_int("agent.max_tool_calls", default=50)
```

#### Admin Endpoint

```
GET  /api/v1/admin/agent-config          — list all configs (grouped by category)
PUT  /api/v1/admin/agent-config/{key}    — update a single config value
POST /api/v1/admin/agent-config/reset    — reset all to seed defaults
```

- **RBAC**: Global admin only (checked via User.is_superuser or similar)
- **Validation**: Enforce min_value/max_value bounds, reject invalid types
- **Audit**: `updated_at` + `updated_by` columns track who changed what

#### Why Not Environment Variables?

Env vars require process restart. The DB approach lets you:
1. Change a value via SQL: `UPDATE "AgentConfigurations" SET value = '100' WHERE key = 'agent.max_tool_calls';`
2. It takes effect within 5 minutes (TTL) or instantly (Redis pub/sub)
3. No restart, no deployment, no downtime

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/models/agent_config.py` | **NEW** — SQLAlchemy model |
| `fastapi-backend/app/ai/config_service.py` | **NEW** — Cached config service |
| `fastapi-backend/app/routers/admin_config.py` | **NEW** — Admin REST endpoints |
| `fastapi-backend/alembic/versions/20260307_add_agent_configurations.py` | **NEW** — Migration + ~75 seed rows |
| `fastapi-backend/app/ai/agent/constants.py` | EDIT — 14 agent keys |
| `fastapi-backend/app/ai/agent/prompts.py` | EDIT — 3 prompt keys |
| `fastapi-backend/app/ai/agent_tools.py` | EDIT — 2 output limit keys |
| `fastapi-backend/app/ai/sql_executor.py` | EDIT — 2 sql keys |
| `fastapi-backend/app/ai/sql_validator.py` | EDIT — 1 sql key |
| `fastapi-backend/app/ai/sql_generator.py` | EDIT — 1 retry key |
| `fastapi-backend/app/ai/rate_limiter.py` | EDIT — 14 rate limit keys |
| `fastapi-backend/app/ai/chunking_service.py` | EDIT — 4 embedding keys |
| `fastapi-backend/app/ai/image_understanding_service.py` | EDIT — 1 embedding key |
| `fastapi-backend/app/ai/excel_export.py` | EDIT — 1 export key |
| `fastapi-backend/app/ai/agent/tools/task_tools.py` | EDIT — 2 tool limit keys |
| `fastapi-backend/app/ai/agent/tools/identity_tools.py` | EDIT — 1 tool limit key |
| `fastapi-backend/app/ai/agent/tools/helpers.py` | EDIT — 1 tool limit key |
| `fastapi-backend/app/routers/ai_chat.py` | EDIT — 7 stream/concurrency keys |
| `fastapi-backend/app/routers/files.py` | EDIT — 2 file limit keys |
| `fastapi-backend/app/routers/ai_import.py` | EDIT — 1 file limit key |
| `fastapi-backend/app/services/search_service.py` | EDIT — 5 search keys |
| `fastapi-backend/app/services/document_lock_service.py` | EDIT — 1 cache key |
| `fastapi-backend/app/services/user_cache_service.py` | EDIT — 2 cache keys |
| `fastapi-backend/app/services/content_converter.py` | EDIT — 2 content keys |
| `fastapi-backend/app/websocket/presence.py` | EDIT — 1 websocket key |
| `fastapi-backend/app/websocket/manager.py` | EDIT — 1 websocket key |
| `fastapi-backend/app/websocket/room_auth.py` | EDIT — 2 cache keys |
| `fastapi-backend/app/worker.py` | EDIT — 7 worker keys |
| `fastapi-backend/app/main.py` | EDIT — 6 websocket keys + startup init |
| `fastapi-backend/tests/test_agent_config_service.py` | **NEW** — ~12 tests |

**Phase -1 total: 4 new files + ~26 edited files + ~75 seed rows**

---

## Phase 0: Fix Chat Session List Bug (Prerequisite)

**Problem**: Sessions don't appear in the session list panel, and titles stay as "New Chat" even after the LLM generates a better title.

**Root cause**: Two issues:
1. Session list query invalidation at `run_started` (use-ai-chat.ts:624) races with session creation — the query may refetch before the DB commit finishes.
2. After `generate_session_title` ARQ worker completes, there's no mechanism to notify the frontend to refetch the session list. The LLM-generated title never appears until the user navigates away and back.

**Files to fix**:
- `electron-app/src/renderer/components/ai/use-ai-chat.ts` — EDIT
- `fastapi-backend/app/routers/chat_sessions.py` — EDIT (optional: add WS broadcast on title update)

**Fix**:
1. Move session list invalidation to `onRunFinished` (after persist succeeds).
2. Add a delayed re-invalidation (~3s after first message) to pick up LLM-generated title from the worker job.

---

## Phase 1: Context Summarization

Replace silent message trimming with two-stage context management.

The agent graph (graph.py:202-252) currently silently drops messages when count > 20. Replace with:

### Stage A — Strip Completed Tool Messages (every LLM call)

For completed turns where the AI already synthesized an answer, the raw tool data is redundant.

- Walk through messages and identify "completed turns" — a sequence of `AIMessage(tool_calls)` + `ToolMessage(s)` + `AIMessage(content)` where the final AIMessage has no tool_calls.
- For completed turns: drop the `AIMessage(tool_calls)` + all `ToolMessage` results. Keep only `HumanMessage` + final `AIMessage(content)`.
- For the current turn (last tool chain still in progress): keep everything.

**Token impact per historical turn**: ~12x reduction (4,450 → 350 tokens).

### Stage B — Auto-Summarize at Configurable Threshold (when needed)

After Stage A stripping, if total tokens still approach `CONTEXT_SUMMARIZE_THRESHOLD` (default 90%, configurable via DB) of context window:

1. Estimate total message tokens using char/4 heuristic + ~15,200 token fixed overhead
2. If under threshold: proceed with stripped messages
3. If over threshold:
   - Split: `old = messages[:-RECENT_WINDOW]`, `recent = messages[-RECENT_WINDOW:]`
   - Ensure split doesn't break tool_call/ToolMessage pairs
   - Call bound model with summarization prompt (reuse from `chat_sessions.py:389-396`)
   - Replace old messages with `SystemMessage("[CONVERSATION SUMMARY]\n{summary}")`
   - Store summary in state for SSE emission
4. Edge case: if recent window alone > 90%, fall back to truncation + log warning

### SSE + Frontend Integration

- Backend emits `event: context_summary` with `data: { summary, up_to_sequence }`
- Frontend handles event via `sidebar.setContextSummary()` — the `ContextSummaryDivider` already renders

### Constants (via config service from Phase -1)

```python
# constants.py — reads from AgentConfigurations table, falls back to hardcoded defaults
_cfg = get_agent_config()
CONTEXT_SUMMARIZE_THRESHOLD = _cfg.get_float("agent.context_summarize_threshold", 0.90)
RECENT_WINDOW = _cfg.get_int("agent.recent_window", 12)          # ~2 full turns preserved
SUMMARY_MAX_TOKENS = _cfg.get_int("agent.summary_max_tokens", 1000)
```

These are seeded in the Phase -1 migration. To tune at runtime:
```sql
UPDATE "AgentConfigurations" SET value = '0.85' WHERE key = 'agent.context_summarize_threshold';
UPDATE "AgentConfigurations" SET value = '16' WHERE key = 'agent.recent_window';
```

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/constants.py` | EDIT — add summarization constants (read from config service) |
| `fastapi-backend/app/ai/agent/graph.py` | EDIT — replace lines 202-252 with two-stage context management |
| `fastapi-backend/app/routers/ai_chat.py` | EDIT — emit `context_summary` SSE event |
| `electron-app/src/renderer/components/ai/types.ts` | EDIT — add ContextSummaryEvent |
| `electron-app/src/renderer/components/ai/use-ai-chat.ts` | EDIT — handle context_summary SSE |
| `fastapi-backend/tests/test_context_summarization.py` | NEW — 8 tests |

---

## Phase 2: Web Tools

### Dependencies

```
duckduckgo-search>=7.0.0,<8.0.0
trafilatura>=2.0.0,<3.0.0
```

### SSRF Validator — `_validate_url_safe(url)`

- Parse URL, reject non-http/https schemes
- Resolve hostname via `asyncio.to_thread(socket.getaddrinfo, ...)`
- Check ALL resolved IPs against blocklist: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, ::1/128, fe80::/10, fc00::/7
- Any blocked IP → `ValueError("URL resolves to a blocked address")`

### Tools

| Tool | Args | Rate Limit | Description |
|------|------|-----------|-------------|
| `web_search` | `query`, `max_results=5` | 20/min | DuckDuckGo search, returns numbered list |
| `scrape_url` | `url` | 10/min | Fetch + extract text via trafilatura, SSRF-safe |

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/requirements.txt` | EDIT — add deps |
| `fastapi-backend/app/ai/rate_limiter.py` | EDIT — add web_search, web_scrape rate limit entries |
| `fastapi-backend/app/ai/agent/tools/web_tools.py` | NEW |
| `fastapi-backend/tests/test_web_tools.py` | NEW — ~15 tests (SSRF, rate limits, functional) |

---

## Phase 3: Application & Member Write Tools

All follow HITL pattern from `write_tools.py:70-261`:
1. Validate inputs
2. Resolve entities via helpers.py
3. Check RBAC BEFORE `interrupt()` (never confirm then deny)
4. Build confirmation dict → `interrupt(confirmation)`
5. Re-check RBAC AFTER interrupt (TOCTOU mitigation)
6. Execute DB write
7. Return human-readable result

### Application Tools

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `create_application` | Any authenticated user | Creates App + ApplicationMember(owner) |
| `update_application` | Owner or Editor | Partial update (name, description) |
| `delete_application` | Owner only | Cascade deletes everything, extra warning |

### Member Tools

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `add_application_member` | Owner: any role; Editor: editor/viewer; Viewer: denied | User must exist in DB |
| `update_application_member_role` | Owner: any; Editor: viewer→editor only | Cannot downgrade last owner |
| `remove_application_member` | Owner only (except self-removal) | Block if member has active tasks |

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/tools/application_write_tools.py` | NEW |
| `fastapi-backend/app/ai/agent/tools/member_write_tools.py` | NEW |
| `fastapi-backend/tests/test_application_write_tools.py` | NEW — ~10 tests |
| `fastapi-backend/tests/test_member_write_tools.py` | NEW — ~10 tests |

---

## Phase 4: Project & Project Member Write Tools

### Project Tools

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `create_project` | App Owner or Editor | Creates Project + 5 default TaskStatuses + ProjectMember(admin) |
| `update_project` | App Owner or Editor | Partial update (name, description, due_date) |
| `delete_project` | App Owner or Project Admin | Cascade deletes tasks/checklists/comments/docs |

### Project Member Tools

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `add_project_member` | App Owner or Project Admin | User must be app member with Owner/Editor role |
| `update_project_member_role` | App Owner or Project Admin | admin or member |
| `remove_project_member` | App Owner or Project Admin | Block if user has active tasks |

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/tools/project_write_tools.py` | NEW |
| `fastapi-backend/app/ai/agent/tools/project_member_write_tools.py` | NEW |
| `fastapi-backend/tests/test_project_write_tools.py` | NEW — ~10 tests |
| `fastapi-backend/tests/test_project_member_write_tools.py` | NEW — ~8 tests |

---

## Phase 5: Task Write Tool Expansion

Add 3 tools to existing `write_tools.py`:

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `update_task` | Owner/Editor + ProjectMember | Partial update: title, description, priority, due_date, task_type |
| `add_task_comment` | Any app member | Max 5,000 chars, @mention resolution → notifications |
| `delete_task` | Owner/Editor + ProjectMember | Cascade deletes, updates ProjectTaskStatusAgg |

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/tools/write_tools.py` | EDIT — add 3 tools |
| `fastapi-backend/tests/test_task_write_tools_expanded.py` | NEW — ~10 tests |

---

## Phase 6: Checklist Write Tools

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `add_checklist` | Owner/Editor + ProjectMember | Cannot add to Done tasks, updates checklist_total |
| `add_checklist_item` | Same | Resolves checklist by title (case-insensitive ILIKE) |
| `toggle_checklist_item` | Same | Toggle completed, updates checklist_done count |

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/tools/checklist_write_tools.py` | NEW |
| `fastapi-backend/tests/test_checklist_write_tools.py` | NEW — ~8 tests |

---

## Phase 7: Document Write Tools + PDF Export

### Document Tools (added to `write_tools.py`)

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `update_document` | Scope-based (App Owner/Editor, ProjectMember, or Self) | Triggers re-embedding job |
| `delete_document` | Document creator only | Soft delete (sets deleted_at), removes from Meilisearch |

### `create_document` Enhancement

Add `doc_type: str = "general"` parameter with writing guidelines in the docstring:
- **training** — Teach skills step by step (Objective → Prerequisites → Steps → Summary → Assessment)
- **research** — Present evidence and analysis (Executive Summary → Findings → Recommendations)
- **documentation** — Reference material for lookup (Overview → Quick Start → Detailed → Troubleshooting)
- **notes** — Meeting notes (Summary → Attendees → Discussion → Decisions → Action Items)
- **general** — Default clear professional writing

### PDF Export

**Dependency**: `weasyprint>=63.0,<64.0` (fallback: `fpdf2` if system libs problematic)

| Tool | RBAC | Key Behavior |
|------|------|-------------|
| `export_document_pdf` | Must have view access to document's scope | Convert markdown→HTML→PDF, save via file service |

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/requirements.txt` | EDIT — add weasyprint |
| `fastapi-backend/app/ai/agent/tools/write_tools.py` | EDIT — add update_document, delete_document, doc_type param |
| `fastapi-backend/app/ai/agent/tools/export_tools.py` | NEW |
| `fastapi-backend/tests/test_document_write_tools.py` | NEW — ~8 tests |

---

## Phase 8: Capabilities Listing

Add `list_capabilities` tool to `utility_tools.py` — returns a structured markdown list of all Blair capabilities grouped by category (Applications, Projects, Tasks, Knowledge Base, Web Research, Data Export, Analytics).

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/tools/utility_tools.py` | EDIT — add list_capabilities |
| `fastapi-backend/tests/test_capabilities_tool.py` | NEW — ~2 tests |

---

## Phase 9: Registration + System Prompt

### Tool Registration (`tools/__init__.py`)

Register all new tools in `ALL_READ_TOOLS` and `ALL_WRITE_TOOLS`:

**New read tools** (3): `web_search`, `scrape_url`, `list_capabilities`

**New write tools** (21):
- Application (3): create/update/delete_application
- Members (3): add/update_role/remove_application_member
- Project (3): create/update/delete_project
- Project Members (3): add/update/remove_project_member
- Task (3): update_task, add_task_comment, delete_task
- Checklist (3): add_checklist, add_checklist_item, toggle_checklist_item
- Document (2): update_document, delete_document
- Export (1): export_document_pdf

### System Prompt (`prompts.py`)

Add tool documentation for:
- Web tools (search + scrape chain for deep research)
- Capabilities tool (trigger on "what can you do?")
- All new write tools grouped by entity
- Web research behavior guidance
- Capabilities trigger guidance

### Files Changed

| File | Action |
|------|--------|
| `fastapi-backend/app/ai/agent/tools/__init__.py` | EDIT — register all new tools |
| `fastapi-backend/app/ai/agent/prompts.py` | EDIT — document all new tools |

---

## Files Changed Summary

| File | Action |
|------|--------|
| `fastapi-backend/app/models/agent_config.py` | **NEW** — AgentConfigurations SQLAlchemy model |
| `fastapi-backend/app/ai/config_service.py` | **NEW** — Cached config service with Redis pub/sub |
| `fastapi-backend/app/routers/admin_config.py` | **NEW** — Admin REST endpoints for config CRUD |
| `fastapi-backend/alembic/versions/20260307_add_agent_configurations.py` | **NEW** — Migration + seed |
| `fastapi-backend/app/ai/agent/constants.py` | EDIT — read from config service |
| `fastapi-backend/app/ai/agent_tools.py` | EDIT — read MAX_TOOL_OUTPUT_CHARS from config |
| `fastapi-backend/app/ai/sql_executor.py` | EDIT — read timeout from config |
| `fastapi-backend/app/ai/rate_limiter.py` | EDIT — read limits from config |
| `fastapi-backend/app/main.py` | EDIT — init config service at startup |
| `fastapi-backend/tests/test_agent_config_service.py` | **NEW** — ~10 tests |
| `fastapi-backend/app/ai/agent/graph.py` | EDIT — replace silent trim with auto-summarization |
| `fastapi-backend/app/ai/agent/constants.py` | EDIT — add summarization threshold constants |
| `fastapi-backend/app/routers/ai_chat.py` | EDIT — emit `context_summary` SSE event |
| `electron-app/src/renderer/components/ai/types.ts` | EDIT — add ContextSummaryEvent |
| `electron-app/src/renderer/components/ai/use-ai-chat.ts` | EDIT — handle context_summary SSE + fix session list |
| `fastapi-backend/requirements.txt` | EDIT — add duckduckgo-search, trafilatura, weasyprint |
| `fastapi-backend/app/ai/rate_limiter.py` | EDIT — add web rate limit entries |
| `fastapi-backend/app/ai/agent/tools/web_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/application_write_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/member_write_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/project_write_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/project_member_write_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/checklist_write_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/export_tools.py` | **NEW** |
| `fastapi-backend/app/ai/agent/tools/write_tools.py` | EDIT — add 5 tools + doc_type |
| `fastapi-backend/app/ai/agent/tools/utility_tools.py` | EDIT — add list_capabilities |
| `fastapi-backend/app/ai/agent/tools/__init__.py` | EDIT — register all |
| `fastapi-backend/app/ai/agent/prompts.py` | EDIT — document all |
| `fastapi-backend/tests/test_context_summarization.py` | **NEW** — 8 tests |
| `fastapi-backend/tests/test_web_tools.py` | **NEW** — 15 tests |
| `fastapi-backend/tests/test_application_write_tools.py` | **NEW** — 10 tests |
| `fastapi-backend/tests/test_member_write_tools.py` | **NEW** — 10 tests |
| `fastapi-backend/tests/test_project_write_tools.py` | **NEW** — 10 tests |
| `fastapi-backend/tests/test_project_member_write_tools.py` | **NEW** — 8 tests |
| `fastapi-backend/tests/test_task_write_tools_expanded.py` | **NEW** — 10 tests |
| `fastapi-backend/tests/test_checklist_write_tools.py` | **NEW** — 8 tests |
| `fastapi-backend/tests/test_document_write_tools.py` | **NEW** — 8 tests |
| `fastapi-backend/tests/test_capabilities_tool.py` | **NEW** — 2 tests |

**Total**: ~28 files, ~89 tests

---

## Security Summary

| Threat | Mitigation |
|--------|-----------|
| SSRF via scrape_url | DNS resolve → IP blocklist (private, metadata, localhost) |
| Unauthorized writes | RBAC pre-interrupt + re-check post-interrupt (TOCTOU) |
| Prompt injection from scraped content | `_wrap_user_content()` tags |
| Prompt injection in summarization | Conversation text wrapped in code block (existing pattern) |
| Web abuse | Per-user rate limits: 20 search/min, 10 scrape/min |
| Cascade delete accidents | HITL confirmation with explicit warning text |
| Role escalation | RBAC enforced per existing role hierarchy |
| Last owner removal | Blocked at validation level |

---

## Patterns to Reuse

| Pattern | Source | Reference |
|---------|--------|-----------|
| HITL interrupt flow | `tools/write_tools.py:70-261` | create_task as full template |
| TOCTOU re-check | `tools/write_tools.py:184-195` | Fresh DB query after interrupt |
| Entity resolution | `tools/helpers.py` | `_resolve_*()` functions |
| Tool context | `tools/context.py` | `_get_user_id()`, `_check_*_access()` |
| DB session | `tools/helpers.py` | `_get_tool_session()` |
| Output helpers | `tools/helpers.py` | `_truncate()`, `_wrap_user_content()` |
| Rate limiter | `rate_limiter.py:446-463` | `get_rate_limiter().check_and_increment()` |
| Summarization prompt | `chat_sessions.py:389-396` | Existing LLM summarization pattern |

---

## Implementation Order

| Phase | Scope | Est. Tests |
|-------|-------|------------|
| -1 | Runtime Configuration Table | 10 |
| 0 | Fix chat session list bug | — |
| 1 | Context Summarization | 8 |
| 2 | Web Tools | 15 |
| 3 | App + Member Write Tools | 20 |
| 4 | Project + Project Member Write Tools | 18 |
| 5 | Task Write Expansion | 10 |
| 6 | Checklist Write Tools | 8 |
| 7 | Document Write + PDF Export | 8 |
| 8 | Capabilities Listing | 2 |
| 9 | Registration + System Prompt | — |

**Dependency order**:
- **Phase -1 first** — config service must exist before other phases can read from it
- **Phases 0-1 and 2-8** are independent and parallelizable
- **Phase 9** depends on all of 2-8
