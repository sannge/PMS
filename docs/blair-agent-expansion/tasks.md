# Blair Agent Expansion — Task Breakdown

**Created**: 2026-03-07
**Plan**: [plan.md](plan.md)
**Status**: Not Started

---

## Phase -1: Runtime Configuration Table

### Task -1.1: Create AgentConfigurations Model
- **File**: `fastapi-backend/app/models/agent_config.py` — NEW
- **Action**: Create SQLAlchemy model:
  ```python
  class AgentConfiguration(Base):
      __tablename__ = "AgentConfigurations"
      key         = Column(String(100), primary_key=True)
      value       = Column(String(500), nullable=False)
      value_type  = Column(String(10), nullable=False)  # "int", "float", "str", "bool"
      category    = Column(String(50), nullable=False)   # "agent", "rate_limit", "embedding", "sql", "web"
      description = Column(String(500))
      min_value   = Column(String(50))
      max_value   = Column(String(50))
      updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
      updated_by  = Column(UUID, ForeignKey("Users.id"))
  ```
- **Also**: Register in `app/models/__init__.py`
- **Status**: [ ] Not Started

### Task -1.2: Create Alembic Migration with Seed Data
- **File**: `fastapi-backend/alembic/versions/20260307_add_agent_configurations.py` — NEW
- **Action**: Create table + INSERT seed data for ~75 config keys across 13 categories:
  - **agent** (14 keys): max_iterations, max_tool_calls, max_llm_calls, max_clarify_rounds, temperature, max_tokens, request_timeout, context_summarize_threshold, recent_window, summary_max_tokens, max_tool_output_chars, max_knowledge_output_chars, max_concurrent_agents, sql_max_retries
  - **agent_tool** (4 keys): list_tasks_limit, comments_limit, workload_limit, match_limit
  - **sql** (3 keys): statement_timeout_ms, app_query_timeout_s, max_limit
  - **embedding** (5 keys): min/max_chunk_tokens, canvas_proximity_threshold, max_cluster_elements, max_images_per_document
  - **rate_limit** (14 keys): all endpoint rate limits including web_search, web_scrape
  - **stream** (4 keys): overall_timeout_s, idle_timeout_s, max_chunks, thread_owner_ttl
  - **websocket** (7 keys): receive_timeout, ping_interval, token_revalidation, rate limits, presence_ttl, batch_size
  - **search** (5 keys): max_content_length, scope_cache_ttl, snippet_context_chars, circuit breaker settings
  - **file** (4 keys): max_upload_size, max_image_size, max_import_size, max_chat_images
  - **worker** (7 keys): archive_after_days, embed_timeout, retries, nightly batch config, concurrent imports
  - **cache** (6 keys): document_lock_ttl, user_cache_ttl/size, room_auth_ttl/size, rbac_context_ttl
  - **web** (2 keys): scrape_timeout, scrape_max_bytes
  - **prompt** (3 keys): custom_addendum, agent_name, communication_style
  - **export** (1 key): excel_ttl_seconds
  - **content** (2 keys): max_recursion_depth, max_node_count
  - Each row includes: key, value, value_type, category, description, min_value, max_value
  - **Migration note**: Copy existing `AiSystemPrompt.prompt` value into `prompt.custom_addendum` if non-empty
- **Status**: [ ] Not Started

### Task -1.3: Create AgentConfigService
- **File**: `fastapi-backend/app/ai/config_service.py` — NEW
- **Action**: Create cached config service:

  #### Core class: `AgentConfigService`
  - **`_cache: dict[str, str]`** — in-memory key→value store
  - **`_cache_loaded_at: float`** — timestamp of last load
  - **`_cache_ttl: float = 300`** — 5 minute TTL safety net
  - **`_lock: asyncio.Lock`** — prevent thundering herd on refresh

  #### Methods:
  - **`get_int(key, default) -> int`** — typed getter, returns default if key missing or DB down
  - **`get_float(key, default) -> float`** — same pattern
  - **`get_str(key, default) -> str`** — same pattern
  - **`get_rate_limit(key, default) -> tuple[int, int]`** — parses "limit,window" string
  - **`async load_all()`** — SELECT all from AgentConfigurations → populate _cache
  - **`async invalidate()`** — clear _cache + PUBLISH to Redis channel `agent_config_changed`
  - **`async subscribe_invalidation()`** — Redis SUBSCRIBE to `agent_config_changed`, clear cache on message
  - **`async set_value(key, value, user_id)`** — UPDATE row + invalidate (for admin endpoint)

  #### Module-level singleton:
  ```python
  _instance: AgentConfigService | None = None

  def get_agent_config() -> AgentConfigService:
      global _instance
      if _instance is None:
          _instance = AgentConfigService()
      return _instance
  ```

  #### Fallback behavior:
  - If DB is unreachable during `load_all()`, log warning and use stale cache
  - If cache is empty AND DB is unreachable, getters return their `default` arg (= hardcoded Python values)
  - This means the system degrades gracefully — behaves exactly like today if DB/Redis is down

- **Status**: [ ] Not Started

### Task -1.4: Create Admin Config Router
- **File**: `fastapi-backend/app/routers/admin_config.py` — NEW
- **Action**: Create 3 endpoints:

  #### `GET /api/v1/admin/agent-config`
  - Returns all config rows grouped by category
  - RBAC: Global admin only (superuser check)

  #### `PUT /api/v1/admin/agent-config/{key}`
  - Body: `{ "value": "100" }`
  - Validates: key exists, value_type matches, min/max bounds respected
  - Updates row + calls `config.invalidate()` (clears cache + Redis pub/sub)
  - RBAC: Global admin only

  #### `POST /api/v1/admin/agent-config/reset`
  - Resets all values to seed defaults (re-runs seed INSERT/UPDATE)
  - RBAC: Global admin only

- **Also**: Register router in `app/routers/__init__.py` and `app/main.py`
- **Status**: [ ] Not Started

### Task -1.5: Wire Config Service into System Prompt
- **File**: `fastapi-backend/app/ai/agent/prompts.py` — EDIT
- **Action**: Update `load_system_prompt()` to read prompt configs from the config service:

  #### Configurable values:
  | Config Key | Default | What It Controls |
  |-----------|---------|-----------------|
  | `prompt.agent_name` | `"Blair"` | Agent identity — replaces "You are Blair" in base prompt |
  | `prompt.communication_style` | `"concise"` | Tone directive — maps to predefined style paragraphs |
  | `prompt.custom_addendum` | `""` (empty) | Free-text appended as `## Custom Instructions` section |

  #### Style mapping:
  ```python
  style_directives = {
      "concise": "Be concise and direct. No filler, no preamble.",
      "detailed": "Provide thorough, detailed explanations. Include context and reasoning.",
      "friendly": "Be warm and conversational. Use a friendly, approachable tone.",
  }
  ```

  #### What stays hardcoded (security-critical):
  - Tool documentation (must match actual tool signatures)
  - Security rules (`[USER CONTENT]` tag handling, RBAC instructions)
  - Clarification protocol (use `request_clarification` tool, never text questions)
  - SQL scoped views documentation

  #### Replaces:
  - The existing `AiSystemPrompt` single-row table lookup in `load_system_prompt()`
  - The addendum is now `prompt.custom_addendum` from the config table

- **Status**: [ ] Not Started

### Task -1.6: Wire Config Service into All Consuming Code
- **Priority order**: Wire high-value files first, then lower-frequency ones
- **Pattern**: Each file replaces `CONSTANT = value` with `config.get_type("key", default_value)`.
  For module-level constants used in hot paths, read once at import. For values tuned frequently (temperature, timeouts), read at call site.
- **Files to edit** (~20 files across 13 categories):

  #### HIGH PRIORITY (agent core — most frequently tuned)

  **`app/ai/agent/constants.py`** — agent category (14 keys)
  ```python
  from ..config_service import get_agent_config
  _cfg = get_agent_config()
  MAX_ITERATIONS = _cfg.get_int("agent.max_iterations", 25)
  MAX_TOOL_CALLS = _cfg.get_int("agent.max_tool_calls", 50)
  # ... etc for all 14 agent keys
  ```

  **`app/ai/agent_tools.py`** — tool output limits (2 keys)
  - `MAX_TOOL_OUTPUT_CHARS` → `config.get_int("agent.max_tool_output_chars", 8000)`
  - `MAX_KNOWLEDGE_OUTPUT_CHARS` → `config.get_int("agent.max_knowledge_output_chars", 16000)`

  **`app/ai/rate_limiter.py`** — rate limits (14 keys)
  - `RATE_LIMITS` dict → populated from config service
  - Priority chain: env var > DB config > hardcoded default

  **`app/routers/ai_chat.py`** — streaming + concurrency (7 keys)
  - `MAX_IMAGES`, `MAX_IMAGE_SIZE`, `STREAM_OVERALL_TIMEOUT_S`, `STREAM_IDLE_TIMEOUT_S`
  - `MAX_CHUNKS_PER_RESPONSE`, `_MAX_CONCURRENT_AGENTS`, `_THREAD_OWNER_TTL`

  #### MEDIUM PRIORITY (supporting services)

  **`app/ai/sql_executor.py`** — sql category (2 keys)
  - `STATEMENT_TIMEOUT_MS`, `APP_QUERY_TIMEOUT_S`

  **`app/ai/sql_validator.py`** — sql category (1 key)
  - `MAX_LIMIT`

  **`app/ai/sql_generator.py`** — agent category (1 key)
  - `MAX_RETRIES`

  **`app/ai/chunking_service.py`** — embedding category (4 keys)
  - `MIN_TOKENS`, `MAX_TOKENS`, `CANVAS_PROXIMITY_THRESHOLD`, `_MAX_CLUSTER_ELEMENTS`

  **`app/ai/image_understanding_service.py`** — embedding category (1 key)
  - `_MAX_IMAGES_PER_DOCUMENT`

  **`app/ai/agent/tools/task_tools.py`** — agent_tool category (2 keys)
  - `_LIST_TASKS_LIMIT`, `_COMMENTS_LIMIT`

  **`app/ai/agent/tools/identity_tools.py`** — agent_tool category (1 key)
  - `_WORKLOAD_LIMIT`

  **`app/ai/agent/tools/helpers.py`** — agent_tool category (1 key)
  - `_MATCH_LIMIT`

  #### LOWER PRIORITY (infrastructure, less frequently tuned)

  **`app/services/search_service.py`** — search category (5 keys)
  - `MAX_CONTENT_LENGTH`, `SCOPE_CACHE_TTL`, `SNIPPET_CONTEXT_CHARS`, circuit breaker settings

  **`app/services/document_lock_service.py`** — cache category (1 key)
  - `LOCK_TTL_SECONDS`

  **`app/services/user_cache_service.py`** — cache category (2 keys)
  - `_CACHE_TTL`, `_MAX_SIZE`

  **`app/websocket/presence.py`** — websocket category (1 key)
  - `PRESENCE_TTL`

  **`app/websocket/manager.py`** — websocket category (1 key)
  - `_BATCH_SIZE`

  **`app/websocket/room_auth.py`** — cache category (2 keys)
  - `_AUTH_CACHE_TTL`, `_AUTH_CACHE_MAX_SIZE`

  **`app/main.py`** — websocket + startup (6 keys)
  - WebSocket constants: `RECEIVE_TIMEOUT`, `SERVER_PING_INTERVAL`, `TOKEN_REVALIDATION_INTERVAL`, rate limits
  - Startup: `await get_agent_config().load_all()` in `lifespan()`
  - Background: `asyncio.create_task(get_agent_config().subscribe_invalidation())`

  **`app/routers/files.py`** — file category (2 keys)
  - `MAX_FILE_SIZE`, `MAX_IMAGE_SIZE`

  **`app/routers/ai_import.py`** — file category (1 key)
  - `MAX_FILE_SIZE`

  **`app/worker.py`** — worker category (7 keys)
  - `ARCHIVE_AFTER_DAYS`, `EMBED_TIMEOUT_S`, `MAX_EMBED_RETRIES`
  - `NIGHTLY_EMBED_BATCH_SIZE`, `NIGHTLY_EMBED_BATCH_DELAY_S`, `MAX_NIGHTLY_EMBED`
  - `MAX_CONCURRENT_IMPORTS`

  **`app/ai/excel_export.py`** — export category (1 key)
  - `EXPORT_TTL_SECONDS`

  **`app/services/content_converter.py`** — content category (2 keys)
  - `_MAX_RECURSION_DEPTH`, `_MAX_NODE_COUNT`

- **Status**: [ ] Not Started

### Task -1.7: Tests
- **File**: `fastapi-backend/tests/test_agent_config_service.py` — NEW
- **Tests** (~12):
  | # | Test | What It Verifies |
  |---|------|-----------------|
  | 1 | `test_get_int_returns_db_value` | Config loaded from DB |
  | 2 | `test_get_int_returns_default_on_miss` | Missing key returns default |
  | 3 | `test_get_float_parses_correctly` | Float parsing from string |
  | 4 | `test_get_rate_limit_parses_tuple` | "30,60" → (30, 60) |
  | 5 | `test_cache_ttl_refresh` | Stale cache triggers reload |
  | 6 | `test_invalidate_clears_cache` | After invalidate(), next get triggers reload |
  | 7 | `test_set_value_validates_bounds` | Rejects value outside min/max |
  | 8 | `test_set_value_validates_type` | Rejects "abc" for int field |
  | 9 | `test_fallback_on_db_error` | Returns default when DB unreachable |
  | 10 | `test_admin_endpoint_rbac` | Non-admin gets 403 |
  | 11 | `test_prompt_agent_name_injection` | Agent name appears in loaded system prompt |
  | 12 | `test_prompt_custom_addendum_appended` | Custom addendum appears at end of prompt |
- **Status**: [ ] Not Started

---

## Phase 0: Fix Chat Session List Bug

### Task 0.1: Move Session List Invalidation to onRunFinished
- **File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts`
- **Action**: EDIT
- **Details**:
  - Remove session list invalidation from `run_started` handler (~line 624)
  - Add invalidation in `onRunFinished` callback, after `persistWithRetry()` succeeds
  - Add delayed re-invalidation (~3s) to pick up LLM-generated title from worker
  ```typescript
  // In onRunFinished callback, after persistWithRetry():
  queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions })
  setTimeout(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions })
  }, 3000)
  ```
- **Tests**: Manual — verify sessions appear immediately and titles update within 3s
- **Status**: [ ] Not Started

### Task 0.2 (Optional): WebSocket Broadcast on Title Update
- **File**: `fastapi-backend/app/routers/chat_sessions.py`
- **Action**: EDIT
- **Details**: Have `generate_session_title` worker broadcast a WS event on title update; frontend invalidates on receipt
- **Status**: [ ] Not Started

---

## Phase 1: Context Summarization

### Task 1.1: Add Summarization Constants
- **File**: `fastapi-backend/app/ai/agent/constants.py`
- **Action**: EDIT
- **Details**: Add constants that read from the config service (Phase -1):
  ```python
  _cfg = get_agent_config()
  CONTEXT_SUMMARIZE_THRESHOLD = _cfg.get_float("agent.context_summarize_threshold", 0.90)
  RECENT_WINDOW = _cfg.get_int("agent.recent_window", 12)
  SUMMARY_MAX_TOKENS = _cfg.get_int("agent.summary_max_tokens", 1000)
  ```
  - The hardcoded defaults (0.90, 12, 1000) serve as fallback if DB is unavailable
  - Seed data for these keys is already created in Phase -1 migration
- **Depends on**: Phase -1 (config service must exist)
- **Status**: [ ] Not Started

### Task 1.2: Replace Silent Trim with Two-Stage Context Management
- **File**: `fastapi-backend/app/ai/agent/graph.py`
- **Action**: EDIT — replace lines 202-252
- **Details**:
  - **Stage A**: Strip completed tool messages on every LLM call
    - Identify completed turns: `AIMessage(tool_calls)` + `ToolMessage(s)` + `AIMessage(content, no tool_calls)`
    - For completed turns: drop tool_calls AIMessage + ToolMessages, keep only HumanMessage + final AIMessage
    - Keep current (in-progress) turn intact
  - **Stage B**: Auto-summarize at configurable threshold (`CONTEXT_SUMMARIZE_THRESHOLD` from config service, default 0.90)
    - Estimate tokens: `sum(len(str(m.content)) / 4)` + 15,200 fixed overhead
    - If over threshold: split at `messages[:-RECENT_WINDOW]`, ensure no broken tool pairs
    - Call bound model with summarization prompt (reuse from `chat_sessions.py:389-396`)
    - Replace old messages with `SystemMessage("[CONVERSATION SUMMARY]\n{summary}")`
    - Store summary in state for SSE emission
    - Edge case: recent window alone > 90% → truncation fallback + warning
  - **Preserve**: Orphaned tool_call sanitization logic (lines 230-252)
- **Status**: [ ] Not Started

### Task 1.3: Emit context_summary SSE Event
- **File**: `fastapi-backend/app/routers/ai_chat.py`
- **Action**: EDIT
- **Details**:
  - After agent graph returns response with summary in state:
    - Emit `event: context_summary` with `data: { summary, up_to_sequence }`
    - Persist to `ChatSession.context_summary` and `summary_up_to_msg_seq`
- **Status**: [ ] Not Started

### Task 1.4: Handle SSE Event in Frontend
- **File**: `electron-app/src/renderer/components/ai/types.ts`
- **Action**: EDIT — add `ContextSummaryEvent` to `ChatStreamEvent` union
- **File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts`
- **Action**: EDIT — add `case 'context_summary'` handler calling `sidebar.setContextSummary()`
- **Status**: [ ] Not Started

### Task 1.5: Tests
- **File**: `fastapi-backend/tests/test_context_summarization.py` — NEW
- **Tests** (8):
  | # | Test | What It Verifies |
  |---|------|-----------------|
  | 1 | `test_strip_completed_tool_messages` | Completed turns stripped, current turn preserved |
  | 2 | `test_no_trim_under_threshold` | Messages under configurable threshold are not modified |
  | 3 | `test_summarize_at_threshold` | Messages at threshold trigger summarization |
  | 4 | `test_summary_preserves_recent_window` | Last 12 messages are kept verbatim |
  | 5 | `test_summary_does_not_split_tool_pairs` | tool_call + ToolMessage pairs stay together |
  | 6 | `test_cumulative_resummarization` | Existing summary + new messages → updated summary |
  | 7 | `test_edge_case_huge_single_message` | Falls back to truncation if recent alone > 90% |
  | 8 | `test_orphaned_tool_calls_sanitized` | Orphaned tool_calls still cleaned after summarization |
- **Status**: [ ] Not Started

---

## Phase 2: Web Tools

### Task 2.1: Add Dependencies
- **File**: `fastapi-backend/requirements.txt`
- **Action**: EDIT — add `duckduckgo-search>=7.0.0,<8.0.0` and `trafilatura>=2.0.0,<3.0.0`
- **Status**: [ ] Not Started

### Task 2.2: Add Rate Limit Keys
- **File**: `fastapi-backend/app/ai/rate_limiter.py`
- **Action**: EDIT — add to `RATE_LIMITS` dict:
  ```python
  "web_search": (20, 60),   # 20 searches per 60s per user
  "web_scrape": (10, 60),   # 10 scrapes per 60s per user
  ```
- **Status**: [ ] Not Started

### Task 2.3: Create web_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/web_tools.py` — NEW
- **Action**: Create file with 4 components:

  #### 2.3.1: SSRF Validator — `_validate_url_safe(url: str) -> None`
  - Parse with `urllib.parse.urlparse()`, reject non-http/https
  - DNS resolve via `asyncio.to_thread(socket.getaddrinfo, hostname, None)`
  - Check ALL resolved IPs against blocklist:
    - `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
    - `169.254.0.0/16` (cloud metadata)
    - `::1/128`, `fe80::/10`, `fc00::/7`
  - If ANY IP blocked → `ValueError("URL resolves to a blocked address")`

  #### 2.3.2: Rate Limit Helper — `_check_web_rate_limit(endpoint, limit, window) -> str | None`
  - Uses `_get_user_id()` + `get_rate_limiter().check_and_increment()`

  #### 2.3.3: Tool — `web_search(query: str, max_results: int = 5) -> str`
  - Validate: query 1-500 chars, max_results 1-8
  - Rate limit: 20/min
  - Execute: `await asyncio.to_thread(DDGS().text, query, max_results=N)`
  - Format as numbered list with bold title + URL + snippet
  - Error handling: catch all → "Web search temporarily unavailable"

  #### 2.3.4: Tool — `scrape_url(url: str) -> str`
  - SSRF check → rate limit → httpx.AsyncClient fetch (10s timeout, 2MB limit)
  - Extract text: `await asyncio.to_thread(trafilatura.extract, html)`
  - Fallback: basic regex tag stripping
  - Wrap output with `_wrap_user_content()` (prompt injection defense)
  - Apply `_truncate()` to final output

- **Status**: [ ] Not Started

### Task 2.4: Tests
- **File**: `fastapi-backend/tests/test_web_tools.py` — NEW
- **Tests** (15):
  | # | Test | Category |
  |---|------|----------|
  | 1 | `test_ssrf_blocks_metadata_ip` | SSRF |
  | 2 | `test_ssrf_blocks_localhost` | SSRF |
  | 3 | `test_ssrf_blocks_private_10` | SSRF |
  | 4 | `test_ssrf_blocks_private_172` | SSRF |
  | 5 | `test_ssrf_blocks_private_192` | SSRF |
  | 6 | `test_ssrf_blocks_non_http` | SSRF |
  | 7 | `test_ssrf_blocks_dns_rebind` | SSRF |
  | 8 | `test_ssrf_allows_public_ip` | SSRF |
  | 9 | `test_search_rate_limited` | Rate Limit |
  | 10 | `test_scrape_rate_limited` | Rate Limit |
  | 11 | `test_search_returns_formatted` | Functional |
  | 12 | `test_search_empty_query` | Functional |
  | 13 | `test_search_truncates_output` | Functional |
  | 14 | `test_scrape_extracts_text` | Functional |
  | 15 | `test_scrape_timeout_handled` | Functional |
- **Status**: [ ] Not Started

---

## Phase 3: Application & Member Write Tools

### Task 3.1: Create application_write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/application_write_tools.py` — NEW
- **Action**: Create 3 tools following HITL pattern from `write_tools.py:70-261`:

  #### `create_application(name: str, description: str = "") -> str`
  - RBAC: Any authenticated user
  - DB: Create Application + ApplicationMember(role="owner", user_id=current_user)
  - Confirmation: "Create application 'My App'"

  #### `update_application(app: str, name: str = "", description: str = "") -> str`
  - RBAC: Owner or Editor (check via ApplicationMember.role)
  - Resolution: `_resolve_application(app, db)`
  - Partial update: only provided fields
  - Confirmation: "Update application 'My App': name → 'New Name'"

  #### `delete_application(app: str) -> str`
  - RBAC: Owner only
  - Extra warning: "This will permanently delete all projects, tasks, documents, and members"
  - DB: Delete Application (cascade)
  - Confirmation: "DELETE application 'My App' and all its contents (irreversible)"

- **Status**: [ ] Not Started

### Task 3.2: Create member_write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/member_write_tools.py` — NEW
- **Action**: Create 3 tools:

  #### `add_application_member(app: str, email: str, role: str) -> str`
  - RBAC: Owner → any role; Editor → editor/viewer; Viewer → denied
  - Resolve user by email: `select(User).where(User.email == email)`
  - Validation: User must exist. If not: "Use the invitation system to invite external users."
  - Confirmation: "Add user@example.com as Editor to 'My App'"

  #### `update_application_member_role(app: str, user: str, new_role: str) -> str`
  - RBAC: Owner → any; Editor → viewer→editor only
  - Validation: Cannot downgrade the last owner
  - Resolution: `_resolve_user(user, db)` — UUID, email, or name
  - Confirmation: "Change Alice's role from Viewer to Editor in 'My App'"

  #### `remove_application_member(app: str, user: str) -> str`
  - RBAC: Owner only (except self-removal for any member)
  - Validation: Cannot remove last owner; block if member has active tasks
  - Confirmation: "Remove Alice from 'My App'"

- **Status**: [ ] Not Started

### Task 3.3: Tests
- **File**: `fastapi-backend/tests/test_application_write_tools.py` — NEW (~10 tests)
- **File**: `fastapi-backend/tests/test_member_write_tools.py` — NEW (~10 tests)
- **Coverage**: RBAC enforcement, HITL confirmation flow, TOCTOU re-check, input validation, last-owner protection
- **Status**: [ ] Not Started

---

## Phase 4: Project & Project Member Write Tools

### Task 4.1: Create project_write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/project_write_tools.py` — NEW
- **Action**: Create 3 tools:

  #### `create_project(app: str, name: str, key: str, description: str = "", due_date: str = "") -> str`
  - RBAC: App Owner or Editor
  - Validation: `key` must be uppercase, unique within app
  - DB: Create Project + 5 default TaskStatus records + ProjectMember(admin)
  - Confirmation: "Create project 'Sprint 1' (SP) in 'My App'"

  #### `update_project(project: str, name: str = "", description: str = "", due_date: str = "") -> str`
  - RBAC: App Owner or Editor
  - Partial update, `due_date` ISO format validation
  - Confirmation: "Update project 'Sprint 1': due_date → 2026-04-01"

  #### `delete_project(project: str) -> str`
  - RBAC: App Owner or Project Admin
  - Extra warning: cascade deletes tasks/checklists/comments/documents
  - Confirmation: "DELETE project 'Sprint 1' and all its contents (irreversible)"

- **Status**: [ ] Not Started

### Task 4.2: Create project_member_write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/project_member_write_tools.py` — NEW
- **Action**: Create 3 tools:

  #### `add_project_member(project: str, user: str, role: str = "member") -> str`
  - RBAC: App Owner or Project Admin
  - Validation: User must be app member with Owner/Editor role
  - Roles: "admin" or "member"

  #### `update_project_member_role(project: str, user: str, new_role: str) -> str`
  - RBAC: App Owner or Project Admin

  #### `remove_project_member(project: str, user: str) -> str`
  - RBAC: App Owner or Project Admin
  - Validation: Block if user has active tasks

- **Status**: [ ] Not Started

### Task 4.3: Tests
- **File**: `fastapi-backend/tests/test_project_write_tools.py` — NEW (~10 tests)
- **File**: `fastapi-backend/tests/test_project_member_write_tools.py` — NEW (~8 tests)
- **Status**: [ ] Not Started

---

## Phase 5: Task Write Tool Expansion

### Task 5.1: Add Tools to write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/write_tools.py` — EDIT
- **Action**: Add 3 tools before the WRITE_TOOLS list:

  #### `update_task(task: str, title: str = "", description: str = "", priority: str = "", due_date: str = "", task_type: str = "") -> str`
  - RBAC: Owner/Editor + ProjectMember (same as create_task)
  - Resolution: `_resolve_task(task, db)` — UUID, task key, or title
  - Partial update: only non-empty fields
  - `due_date`: ISO format, validate with `datetime.fromisoformat()`
  - `priority`: lowest/low/medium/high/highest
  - `task_type`: story/bug/epic/subtask/task
  - Confirmation: "Update SP-1 'Fix login': priority → high, due_date → 2026-04-01"

  #### `add_task_comment(task: str, content: str, mentions: str = "") -> str`
  - RBAC: Any application member can comment
  - `content`: Max 5,000 characters
  - `mentions`: Comma-separated emails/names → resolved to user IDs
    - For each: `_resolve_user(mention.strip(), db, scope_project_id=...)`
    - Create MENTION_NOTIFICATION for each resolved user
  - Confirmation: "Add comment to SP-1 (mentioning Alice, Bob)"

  #### `delete_task(task: str) -> str`
  - RBAC: Owner/Editor + ProjectMember
  - Extra warning: cascade deletes comments/checklists/attachments
  - Update ProjectTaskStatusAgg counters
  - Confirmation: "DELETE task SP-1 'Fix login' (irreversible)"

- **Status**: [ ] Not Started

### Task 5.2: Tests
- **File**: `fastapi-backend/tests/test_task_write_tools_expanded.py` — NEW
- **Tests** (10):
  | # | Test |
  |---|------|
  | 1 | `test_update_task_partial_fields` |
  | 2 | `test_update_task_invalid_priority` |
  | 3 | `test_update_task_invalid_due_date` |
  | 4 | `test_update_task_rbac_denied` |
  | 5 | `test_add_comment_with_mentions` |
  | 6 | `test_add_comment_too_long` |
  | 7 | `test_add_comment_any_app_member` |
  | 8 | `test_delete_task_cascade` |
  | 9 | `test_delete_task_rbac_denied` |
  | 10 | `test_delete_task_hitl_rejection` |
- **Status**: [ ] Not Started

---

## Phase 6: Checklist Write Tools

### Task 6.1: Create checklist_write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/checklist_write_tools.py` — NEW
- **Action**: Create 3 tools:

  #### `add_checklist(task: str, title: str) -> str`
  - RBAC: Owner/Editor + ProjectMember
  - Validation: Cannot add checklist to Done tasks
  - DB: Create Checklist record, update Task.checklist_total

  #### `add_checklist_item(task: str, checklist_title: str, item_title: str) -> str`
  - Resolution: Resolve checklist by title within task (case-insensitive ILIKE)
  - DB: Create ChecklistItem, update Task.checklist_total

  #### `toggle_checklist_item(task: str, checklist_title: str, item_title: str) -> str`
  - Resolution: Resolve item by title within checklist (case-insensitive ILIKE)
  - DB: Toggle ChecklistItem.completed, update Task.checklist_done count

- **Status**: [ ] Not Started

### Task 6.2: Tests
- **File**: `fastapi-backend/tests/test_checklist_write_tools.py` — NEW (~8 tests)
- **Status**: [ ] Not Started

---

## Phase 7: Document Write Tools + PDF Export

### Task 7.1: Add Document Update/Delete to write_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/write_tools.py` — EDIT
- **Action**: Add 2 tools:

  #### `update_document(doc: str, title: str = "", content: str = "") -> str`
  - RBAC: App Owner/Editor, ProjectMember, or Self (scope-based)
  - Resolution: `_resolve_document(doc, db)` — UUID or title
  - DB: Update Document fields + trigger re-embedding job
  - Confirmation: "Update document 'Design Spec': title → 'Design Spec v2'"

  #### `delete_document(doc: str) -> str`
  - RBAC: Document creator only (`Document.created_by == current_user`)
  - Soft delete: sets `Document.deleted_at` (restorable)
  - Side effect: remove from Meilisearch index
  - Confirmation: "Delete document 'Old Notes' (can be restored from trash)"

- **Status**: [ ] Not Started

### Task 7.2: Update create_document with doc_type Parameter
- **File**: `fastapi-backend/app/ai/agent/tools/write_tools.py` — EDIT
- **Action**: Add `doc_type: str = "general"` parameter to existing `create_document`
- **Details**: Writing guidelines in docstring (training, research, documentation, notes, general)
- **Status**: [ ] Not Started

### Task 7.3: Add PDF Export Dependency
- **File**: `fastapi-backend/requirements.txt` — EDIT
- **Action**: Add `weasyprint>=63.0,<64.0`
- **Note**: Requires system libs (cairo, pango). Fallback: `fpdf2` (pure Python)
- **Status**: [ ] Not Started

### Task 7.4: Create export_tools.py
- **File**: `fastapi-backend/app/ai/agent/tools/export_tools.py` — NEW
- **Action**: Create 1 tool:

  #### `export_document_pdf(doc: str) -> str`
  - RBAC: Must have view access to document's scope
  - Process: Load content → markdown→HTML → HTML→PDF (weasyprint) → save via file service → return URL
  - HITL: Yes (resource-intensive)
  - Confirmation: "Export 'Design Spec' as PDF for download"

- **Status**: [ ] Not Started

### Task 7.5: Tests
- **File**: `fastapi-backend/tests/test_document_write_tools.py` — NEW (~8 tests)
- **Status**: [ ] Not Started

---

## Phase 8: Capabilities Listing

### Task 8.1: Add list_capabilities Tool
- **File**: `fastapi-backend/app/ai/agent/tools/utility_tools.py` — EDIT
- **Action**: Add `list_capabilities()` tool that returns structured markdown listing all Blair capabilities:
  - Applications (create/update/delete, members)
  - Projects (create/update/delete, members, timelines)
  - Tasks (full CRUD, comments, checklists, assign, status)
  - Knowledge Base (create/update/delete, search, browse, PDF export)
  - Web Research (search, scrape, chain for deep research)
  - Data Export (Excel, PDF)
  - Analytics (SQL queries, workload, timelines, image analysis)
  - Footer: "All write operations require your confirmation before executing."
- **Status**: [ ] Not Started

### Task 8.2: Tests
- **File**: `fastapi-backend/tests/test_capabilities_tool.py` — NEW (~2 tests)
- **Status**: [ ] Not Started

---

## Phase 9: Register Tools + Update System Prompt

### Task 9.1: Register All New Tools in __init__.py
- **File**: `fastapi-backend/app/ai/agent/tools/__init__.py` — EDIT
- **Action**:
  - Add imports for all new tool files
  - Add to `ALL_READ_TOOLS`: `web_search`, `scrape_url`, `list_capabilities`
  - Add to `ALL_WRITE_TOOLS`: all 21 new write tools
  - Update `__all__` with all new tool names
- **Depends on**: All of Phases 2-8
- **Status**: [ ] Not Started

### Task 9.2: Update System Prompt
- **File**: `fastapi-backend/app/ai/agent/prompts.py` — EDIT
- **Action**:
  - Add `### Web` section: `web_search`, `scrape_url` with deep research chain guidance
  - Add `### Capabilities` section: `list_capabilities` trigger
  - Expand `### Write operations` with all new tools grouped by entity
  - Add `<web_research>` behavior block (use web_search for external topics, cite URLs)
  - Add `<capabilities>` behavior block (trigger on "what can you do?", "help")
- **Depends on**: All of Phases 2-8
- **Status**: [ ] Not Started

---

## Verification Checklist

After all phases complete:

1. [ ] `pip install -r requirements.txt` — new deps install
2. [ ] `pytest tests/test_context_summarization.py tests/test_web_tools.py tests/test_application_write_tools.py tests/test_member_write_tools.py tests/test_project_write_tools.py tests/test_project_member_write_tools.py tests/test_task_write_tools_expanded.py tests/test_checklist_write_tools.py tests/test_document_write_tools.py tests/test_capabilities_tool.py -v` — all pass
3. [ ] `ruff check app/ai/agent/tools/` — no lint errors
4. [ ] Manual test: "What can you do?" → calls `list_capabilities`
5. [ ] Manual test: "Create an application called Test" → HITL → creates app
6. [ ] Manual test: "Add user@example.com as editor to Test" → HITL → adds member
7. [ ] Manual test: "Create project Sprint-1 in Test with key SP" → HITL → creates project
8. [ ] Manual test: "Create a task: Fix the login bug, high priority" → HITL → creates task
9. [ ] Manual test: "Update SP-1: set priority to highest" → HITL → updates
10. [ ] Manual test: "Add a comment to SP-1: @alice please review" → HITL → comment + notification
11. [ ] Manual test: "Add checklist 'QA Steps' to SP-1" → HITL → creates checklist
12. [ ] Manual test: "Search the web for sprint retrospective best practices" → web_search
13. [ ] Manual test: "Summarize this page: https://docs.python.org/3/whatsnew/3.13.html" → scrape_url
14. [ ] Manual test: "Write a training document about onboarding" → create_document(doc_type="training")
15. [ ] Manual test: "Export the design doc as PDF" → generates PDF
16. [ ] Manual test: Long conversation (20+ turns) → auto-summarization triggers

---

## Dependency Graph

```
Phase -1 (config table) ── FIRST — config service must exist before others consume it
    │
    ├── Phase 0 (session fix) ─── independent
    ├── Phase 1 (summarization) ── reads CONTEXT_SUMMARIZE_THRESHOLD etc. from config
    ├── Phase 2 (web tools) ────── reads web rate limits from config
    ├── Phase 3 (app/member) ───── independent
    ├── Phase 4 (project/member) ─ independent
    ├── Phase 5 (task expansion) ─ independent
    ├── Phase 6 (checklists) ───── independent
    ├── Phase 7 (doc/pdf) ──────── independent
    └── Phase 8 (capabilities) ─── independent
                                       │
                                Phase 9 (registration) ─── depends on ALL of 2-8
```

Phase -1 is the foundation. Once it's done, Phases 0-8 can all run in parallel. Phase 9 is the final integration step.
