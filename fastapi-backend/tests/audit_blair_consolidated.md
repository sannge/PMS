# Blair AI Agent System - Consolidated Audit Report

**Date**: 2026-03-06
**Auditors**: Code Reviewer, Security Analyst, Quality Engineer, Devil's Advocate, Test Engineer
**Scope**: Full Blair AI agent system (backend + frontend)

---

## How to Read This Report

Findings are deduplicated across all 5 auditors. When multiple auditors flagged the same issue, the most severe rating is used and all auditor tags are listed. Findings are grouped by severity, then by subsystem.

**Auditor tags**: `[SA]` Security Analyst, `[CR]` Code Reviewer, `[QE]` Quality Engineer, `[DA]` Devil's Advocate, `[TE]` Test Engineer

---

## CRITICAL (7 findings)

### CRIT-1: System Prompt DB Override Enables Full Agent Jailbreak [SA]
**File**: `app/ai/agent/nodes/intake.py:71-78`

The intake node loads a custom system prompt from `AiSystemPrompt` with `LIMIT 1` and uses it **verbatim as a replacement** for the hardcoded `SYSTEM_PROMPT`. Any admin (or attacker with DB write access) can completely erase all security instructions — SQL RBAC rules, `[USER CONTENT]` trust boundaries, tool restrictions — with a single row.

**Fix**: Treat the DB-loaded prompt as a suffix/addendum appended **after** the hardcoded base `SYSTEM_PROMPT`, never a replacement. Apply length and content policy validation.

---

### CRIT-2: Shared Mutable Caches Enable Cross-Request State Pollution [QE][DA]
**File**: `app/ai/agent/graph.py:332-336`

`chat_model_cache`, `system_prompt_cache`, `bound_model_cache` are plain Python lists captured by `functools.partial` closures. The comment says `build_agent_graph() MUST be called per-request` but there is **no enforcement**. If the compiled graph is ever cached/reused (a natural optimization), `intake_node` skips re-initialization (`if not chat_model_cache:`) and the second request inherits the first user's model and system prompt.

**Fix**: Move cache state into `AgentState` (per-invocation by design), or add a runtime guard that the compiled graph cannot be reused.

---

### CRIT-3: `_ContextVarSyncDict` — Dangerous Dual-Write Pattern [CR][DA][QE]
**File**: `app/ai/agent/tools/context.py:24-88`

Three separate mutation paths (`update`, `__setitem__`, `clear`) each call `ContextVar.set()`. The module-level `_tool_context` dict is a single global object — any code that reads it directly (tests, debugging) gets the wrong context. `clear()` sets the ContextVar to `{}`, which bypasses the `RuntimeError` guard in `_get_ctx()` (empty dict is falsy). Production code must actively work around its own abstraction (comments at lines 83-88).

**Fix**: Remove `_ContextVarSyncDict` entirely. Have `set_tool_context`/`clear_tool_context` exclusively own the ContextVar. Update tests to use those functions.

---

### CRIT-4: Thread IDOR When Redis Down (Fail-Open Fallback) [SA][DA]
**File**: `app/routers/ai_chat.py:113-169`

The in-memory `_thread_owners_fallback` dict holds only 10,000 entries with FIFO eviction. After eviction, an attacker can guess/enumerate another user's `thread_id` and access their conversation via `/resume`, `/replay`, or `/history`. The MEMORY.md flags this as "LOW" but the practical exploitability against `/history` warrants CRITICAL.

**Fix**: Return 503 for sensitive endpoints (`/resume`, `/replay`, `/history`) when Redis is unavailable, rather than falling back to the in-memory dict.

---

### CRIT-5: Post-Interrupt RBAC Re-Check Uses Stale In-Memory List [DA]
**File**: `app/ai/agent/tools/write_tools.py:182, 343, 508`

All three write tools call `_check_project_access(project_id)` after interrupt resume. This reads from `_tool_context_var`, populated at request start from a point-in-time DB snapshot. If user membership was revoked during the HITL pause (could be hours), the stale list still passes. The comments claim TOCTOU protection but never re-query the database.

**Fix**: After resuming from interrupt, re-query `ProjectMember`/`ApplicationMember` from the database.

---

### CRIT-6: Stale `project_key` After HITL Produces Wrong Task Keys [CR]
**File**: `app/ai/agent/tools/write_tools.py:102-243`

`project_key` is captured before `interrupt()` (line 117), but the task key is assembled using it after user confirmation (line 212). If the project key changed during the HITL pause, tasks get silently wrong keys.

**Fix**: Re-fetch the project inside the post-interrupt DB session and use the freshly loaded `proj.key`.

---

### CRIT-7: SQL Executor Timed-Out Tasks Hold Stale Tool Context [QE]
**File**: `app/ai/sql_executor.py:143`, `app/ai/agent/tools/context.py:86`

`asyncio.wait_for` wraps the SQL execution in a child Task. On timeout, the parent proceeds to the next request, but the abandoned child task still holds the previous user's `_tool_context_var`. If the timed-out query's PG-side execution continues (until PG's own `statement_timeout`), the connection slot is held and the leaked task can read stale context.

**Fix**: Explicitly cancel the abandoned task and `await session.close()` on timeout paths.

---

## HIGH (18 findings)

### HIGH-1: SQL Injection via LLM-Generated SQL [SA]
**File**: `app/ai/sql_executor.py`

`SET TRANSACTION READ ONLY` is the real last line of defense, not the regex/sqlglot validator. A `WITH ... DELETE/UPDATE RETURNING *` CTE is valid Postgres syntax that produces read results with write side-effects. If the DB user has `SET SESSION AUTHORIZATION` privileges, `SET TRANSACTION READ ONLY` can be escaped.

**Fix**: Enforce `REVOKE INSERT, UPDATE, DELETE, TRUNCATE, DROP, CREATE` at the PostgreSQL role level. Confirm `WITH ... DELETE/UPDATE RETURNING` is blocked.

---

### HIGH-2: SSRF via Ollama `base_url` Not Re-Validated at Request Time [SA]
**File**: `app/ai/agent/graph.py:87-97`

SSRF prevention (metadata IP blocking) only applies at config-save time. Once a malicious `base_url` is stored, every chat request makes HTTP requests to that URL. Internal cloud metadata endpoints would be reachable.

**Fix**: Re-validate `base_url` at resolution time in `_get_langchain_chat_model`.

---

### HIGH-3: Rate Limit In-Memory Fallback Multiplied by Worker Count [SA][DA][QE]
**File**: `app/ai/rate_limiter.py:90-94`

When Redis is down: `limit * 2 * N_workers`. For `ai_chat` (limit=30, 4 workers): 240 req/min instead of 30. For `auth_login` (limit=10, 4 workers): 80 attempts/min, meaningfully weakening brute-force protection.

**Fix**: Use 1x limit in fallback. Log `CRITICAL` alarm when fallback activates. Consider shared memory or stricter deny policy.

---

### HIGH-4: Embedding Rate Limit `application_id` Not Authenticated [SA]
**File**: `app/ai/rate_limiter.py:443-463`

The docstring says "the calling router MUST validate" but enforcement is caller discipline. An attacker can lock out another application's embedding quota by flooding under a victim's `application_id`.

**Fix**: Perform access check inside `check_embedding_rate_limit` or scope to `user_id`.

---

### HIGH-5: `export_to_excel` Application Scope Skips Post-Interrupt RBAC [SA][DA]
**File**: `app/ai/agent/tools/write_tools.py:818-820`

Only `project`-scoped exports re-check RBAC post-interrupt. `application`-scoped exports skip entirely.

**Fix**: Add `_check_app_access(resolved_scope_id)` for application scope.

---

### HIGH-6: Client-Injected `conversation_history` Bypasses Prompt Defenses [SA][DA]
**File**: `app/routers/ai_chat.py:912-914`, `app/schemas/ai_chat.py:30-31`

A client can inject 49 fake `role=assistant` messages claiming the AI previously agreed to ignore its system prompt. The LLM treats these as genuine prior exchanges. The `[USER CONTENT]` wrapping is not applied to injected history.

**Fix**: Discard client-supplied history and reconstruct from the checkpointer, or apply content policy scanning.

---

### HIGH-7: `resume_chat` Non-Streaming Has No Execution Timeout [DA]
**File**: `app/routers/ai_chat.py:1159-1199`

The streaming resume goes through `_guarded_sse_stream` (which has `STREAM_OVERALL_TIMEOUT_S`). The non-streaming `resume_chat` has no `asyncio.timeout()` wrapper. A stuck LLM call holds a semaphore slot indefinitely.

**Fix**: Add `asyncio.timeout(STREAM_OVERALL_TIMEOUT_S)` around `graph.ainvoke` in `resume_chat`.

---

### HIGH-8: `_resolve_application`/`_resolve_project` ~250 Lines of Duplicated Logic [CR]
**File**: `app/ai/agent/tools/helpers.py:127-306`

Identical pattern: validate, UUID fast path, ILIKE search, list available, format ambiguity error. Only the model class, IDs key, and noun differ.

**Fix**: Extract `_resolve_entity(model, accessible_ids_key, noun, identifier, db)`.

---

### HIGH-9: Three Nearly Identical SSE-Fetch-and-Stream Functions [CR]
**File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts:489-755`

`sendMessage`, `resumeInterrupt`, `sendReplayMessage` are ~200 lines with ~80% duplication.

**Fix**: Extract `_runStream(url, body, opts)`.

---

### HIGH-10: System Prompt Loading Duplicated Between `ai_chat.py` and `intake.py` [CR]
**File**: `app/routers/ai_chat.py:376-384` vs `app/ai/agent/nodes/intake.py:67-81`

Identical logic in two files. Changes must be synchronized.

**Fix**: Extract `load_system_prompt(db) -> str` to a shared module.

---

### HIGH-11: Circular Import Deferred in Hot Path [CR]
**File**: `app/ai/agent/nodes/intake.py:52-53`, `app/ai/agent/graph.py:202`

`intake_node` defers importing `_get_langchain_chat_model` from `graph.py` on every execution. `graph.py:202` defers `ToolMessage` import inside a while-True loop.

**Fix**: Move `_get_langchain_chat_model` to `intake.py` or `model_factory.py`. Move `ToolMessage` import to module top.

---

### HIGH-12: `_STATUS_NAME_MAP` Duplicated in Two Files [CR]
**File**: `app/ai/agent/tools/task_tools.py:61-67`, `app/ai/agent/tools/write_tools.py:53-59`

Identical status mapping. A new status must be updated in two places.

**Fix**: Move to `helpers.py` or `constants.py` as `TASK_STATUS_MAP`.

---

### HIGH-13: `export_to_excel` Contains 120 Lines of Inline Business Logic [CR]
**File**: `app/ai/agent/tools/write_tools.py:822-946`

Data-gathering SQL, column mapping, and row building all inline in the tool. Untestable without full tool context. Also imports `selectinload` inside the function body.

**Fix**: Extract to a service function. The tool should only handle HITL and call the service.

---

### HIGH-14: Unbounded `selectinload(Task.comments)` [QE]
**File**: `app/ai/agent/tools/task_tools.py:205`

Fetches ALL comments for a task (no SQL LIMIT), then takes only last 5 in Python (line 284).

**Fix**: Use a subquery or separate limited query instead of full selectinload.

---

### HIGH-15: Full Message List Re-Render on Every Streaming Token [QE]
**File**: `electron-app/src/renderer/components/ai/ai-sidebar.tsx:329`

`messages` selector returns a new array reference on every `text_delta` (~10-50/sec). All consumers re-render.

**Fix**: Use `useShallow` from Zustand, or split `streamingMessage` into a separate state slice.

---

### HIGH-16: Array Spread on Every SSE Event Creates GC Pressure [QE]
**File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts:231,245,258`

Every `tool_call_start`/`tool_call_end` does `[...activityItems, newItem]`. With 50 tool calls = 100+ array copies.

**Fix**: Use Immer `produce`, or keep a mutable Map and spread once at `flushBatch`.

---

### HIGH-17: Double Concurrent `aget_state` During Idle Timeout + Stream End [QE]
**File**: `app/routers/ai_chat.py:756-805`

Idle timeout and stream loop both call `graph.aget_state(config)` simultaneously. May cause lock contention or inconsistent state.

**Fix**: Store graph state in a shared reference consumed by either path.

---

### HIGH-18: Rate Limiter Endpoint Functions Are Near-Identical Boilerplate [CR]
**File**: `app/ai/rate_limiter.py:427-592`

Eight functions with identical structure, differing only in key name, scope, and detail string. ~165 lines of pure boilerplate.

**Fix**: Create `_make_rate_limit_dep(key, scope, prefix)` factory. Reduces to ~30 lines.

---

## MEDIUM (24 findings)

### MED-1: Markdown Export Link Injection — Authenticated Fetch [SA]
**File**: `electron-app/src/renderer/components/ai/markdown-renderer.tsx:382-393`

Any AI response link starting with `/api/ai/export/` triggers an authenticated `fetch()` with `Authorization: Bearer`. A prompt-injected link like `/api/ai/export/../../api/users/me` could hit any backend endpoint with the user's credentials.

**Fix**: Validate export links match strict pattern `/api/ai/export/[uuid]/[filename].xlsx`. Reject path traversal.

---

### MED-2: `_wrap_user_content` Delimiter Bypass [SA]
**File**: `app/ai/agent/tools/helpers.py:637-644`

Only removes exact case-sensitive `[USER CONTENT START]` matches. Lowercase or extra-space variants bypass.

**Fix**: Use regex for all bracket variations, or use a per-request cryptographic nonce as delimiter.

---

### MED-3: Image `media_type` Not Verified Against Decoded Bytes [SA]
**File**: `app/routers/ai_chat.py:213-237`

User-supplied `media_type` string is trusted without checking actual bytes. File polyglot attack surface.

**Fix**: Use `python-magic` to verify decoded bytes match declared MIME type.

---

### MED-4: `thread_id` Has No Character Allowlist [SA]
**File**: `app/schemas/ai_chat.py:64-68`

Used as Redis key prefix and LangGraph checkpoint key with no format validation. Characters like `*`, `?`, `[` could cause key collisions.

**Fix**: Validate against `^[a-zA-Z0-9_-]{1,256}$`.

---

### MED-5: JWT Refresh Secret Fallback Silently Accepted [SA]
**File**: `app/config.py:172-181`

Empty `JWT_REFRESH_SECRET` in non-Redis mode means access and refresh tokens share signing secret.

**Fix**: Make empty `JWT_REFRESH_SECRET` a fatal startup error unconditionally.

---

### MED-6: Creator/Member Email Exposed in Tool Output [SA]
**Files**: `app/ai/agent/tools/knowledge_tools.py:374-376`, `app/ai/agent/tools/application_tools.py:209-218`

Full email addresses exposed in tool results sent to LLM, which includes them in responses. PII disclosure.

**Fix**: Expose only `display_name`. Mask email as fallback: `u***@domain.com`.

---

### MED-7: Message Trimming Can Orphan ToolMessage from Parent AIMessage [DA]
**File**: `app/ai/agent/graph.py:197-209`

Walk-back hits `idx < 2` and breaks, leaving ToolMessage without its parent. Some LLM providers raise validation errors.

**Fix**: Ensure walk-back always includes the AIMessage that triggered the ToolMessages.

---

### MED-8: `?` in Code/URLs Falsely Triggers Clarification Auto-Conversion [DA]
**File**: `app/ai/agent/graph.py:123-147`

Any `?` in the last 5 lines triggers `request_clarification`. Rhetorical questions, SQL `WHERE status = ?`, URLs with query params all false-positive.

**Fix**: Use a more sophisticated heuristic (e.g., check if line ends with `?` and doesn't start with code markers).

---

### MED-9: `embed_document` Never Commits — Silent Success Without Durable Writes [DA][QE]
**File**: `app/ai/embedding_service.py:157-158`

Calls `flush()` but not `commit()`. Works in batch context but if called directly, chunks are never committed.

**Fix**: Document the commit contract explicitly. Add a guard or commit in the function.

---

### MED-10: UUID Fast Path in Resolver Skips DB Existence/Soft-Delete Check [DA]
**File**: `app/ai/agent/tools/helpers.py:153-160`

If identifier is a valid UUID in `accessible_app_ids`, it's returned without checking DB existence or soft-delete status.

**Fix**: Add a lightweight DB existence check on the UUID fast path.

---

### MED-11: SSE Buffer Overflow Drops Complete Events [DA]
**File**: `electron-app/src/renderer/components/ai/use-ai-chat.ts:338-342`

When buffer exceeds 1 MB, entire buffer is dropped including complete `\n\n`-terminated events. `run_finished` may be lost, leaving UI in streaming state until 60s timeout.

**Fix**: Process complete events before discarding remainder.

---

### MED-12: Redis GET on Every Request for Thread Owner Validation [QE]
**File**: `app/routers/ai_chat.py:113-169`

Hot path Redis round-trip (~0.5-2ms) that could be avoided by checking in-memory fallback first.

**Fix**: Check local fallback first, skip Redis if found and not expired.

---

### MED-13: Extra DB Session in `intake_node` When Already Opened in Setup [QE]
**File**: `app/ai/agent/nodes/intake.py:57-82`

`_setup_agent_context` opens a DB session for RBAC. `intake_node` opens another for model/prompt. Two pool connections consumed sequentially.

**Fix**: Pass resolved config from `_setup_agent_context` directly into the graph via pre-warmed slots.

---

### MED-14: `AIRateLimiter` Instance Created Per-Request with 3 Script Registrations [QE]
**File**: `app/ai/rate_limiter.py:393-403`

`get_rate_limiter()` creates a new instance per request, registering 3 Lua scripts each time.

**Fix**: Cache as singleton per Redis client reference.

---

### MED-15: 5 Serial DB Round-Trips in `browse_folders` [QE]
**File**: `app/ai/agent/tools/knowledge_tools.py:229-286`

Five sequential queries. Queries 2+3 and 4+5 can be parallelized with `asyncio.gather`.

---

### MED-16: Double Commit in Write Tools [QE]
**File**: `app/ai/agent/tools/write_tools.py:232,370,523,709`

Explicit `await db.commit()` + `get_tool_db` auto-commit = two commits per operation.

**Fix**: Remove explicit commits; rely on `get_tool_db` auto-commit.

---

### MED-17: Global `asyncio.Lock` Serializes All Rate Limit Fallback Checks [QE]
**File**: `app/ai/rate_limiter.py:90`

Single lock for all users when Redis is down. At 5,000 concurrent users, every request blocks.

**Fix**: Use per-key locks or sharded counters.

---

### MED-18: 10 Separate Zustand Subscriptions in AiSidebar [QE][CR]
**File**: `electron-app/src/renderer/components/ai/ai-sidebar.tsx:78-88`

10 individual `useAiSidebar(s => s.xxx)` calls = 10 subscriptions, all evaluated on every state change.

**Fix**: Consolidate with `useShallow` or single selector returning a plain object.

---

### MED-19: `_get_tool_session` Inconsistent Commit Behavior [CR]
**File**: `app/ai/agent/tools/helpers.py:83-117`

Injected factory path commits via `get_tool_db`; fallback path does not. Contract is implicit and depends on which path is active.

**Fix**: Standardize: either context manager always commits on clean exit, or callers always commit explicitly.

---

### MED-20: `_history_to_langchain_messages` Uses `hasattr`/`.get()` Duck Typing on Known Type [CR]
**File**: `app/routers/ai_chat.py:246-263`

Caller always passes `list[ChatHistoryEntry]` but function signature says `list[Any]`.

**Fix**: Type parameter properly as `list[ChatHistoryEntry]` and use direct attribute access.

---

### MED-21: Multiple Deferred Imports Inside Function Bodies [CR]
**Files**: `write_tools.py:825` (`selectinload`), `write_tools.py:625` (`DocumentFolder`), `project_tools.py:406` (`timedelta`), `knowledge_tools.py:359` (`aliased`)

All should be module-level imports.

---

### MED-22: `AgentState` Uses `str` for `user_id` Instead of UUID [CR]
**File**: `app/ai/agent/state.py:27-29`

Throughout tools, strings are converted to `UUID` on every access. Badly formed IDs fail only at DB query time.

**Fix**: Use `UUID` type in state or validate at construction.

---

### MED-23: `ChatRequest` Validator Named `validate_history_length` Silently Truncates [CR]
**File**: `app/schemas/ai_chat.py:55`

A `validate_*` method that mutates data is surprising in Pydantic.

**Fix**: Rename to `truncate_history` or convert to a `@model_validator`.

---

### MED-24: Non-TimeoutError Exceptions May Escape Guarded SSE Wrapper [DA]
**File**: `app/routers/ai_chat.py:613-615`

`_guarded_sse_stream` only catches `TimeoutError` explicitly. Other exceptions bubble to `EventSourceResponse` which may send raw exception text.

**Fix**: Add `except Exception` before the `TimeoutError` handler, or add `except GraphBubbleUp: raise` before generic handler.

---

## LOW (20 findings)

### LOW-1: Rate Limit Headers Expose Internal Limits [SA]
`app/ai/rate_limiter.py:417-423` — `X-RateLimit-Limit` discloses configured limits.

### LOW-2: Application Name Enumeration via Error Messages [SA]
`app/ai/agent/tools/helpers.py:188-201` — Failed lookups list up to 10 available app names.

### LOW-3: `_active_stream_cancels` Not Per-User [SA][QE]
`app/routers/ai_chat.py:63-75` — Keyed by `thread_id`; user-chosen ID collision enables cross-user cancel.

### LOW-4: `application_id` Scope Hint Not Validated Against RBAC [SA]
`app/schemas/ai_chat.py:59-63` — Advisory filter passed to tools without membership check (tools self-filter).

### LOW-5: `AI_ENCRYPTION_KEY` Guard Bypassed in Test Mode [SA]
`app/config.py:162-169` — `TESTING=1` env var silently bypasses encryption key check.

### LOW-6: Cancel Endpoint Counts Against Chat Rate Limit [DA]
`app/routers/ai_chat.py:1139-1151` — Rapid cancel-retry cycles lock user out.

### LOW-7: `MAX_CLARIFY_ROUNDS` Defined But Never Enforced [DA]
`app/ai/agent/constants.py:10` — LLM can call `request_clarification` up to 50 times.

### LOW-8: Orphaned `tool_call_end` Leaves Activity Item Permanently "Running" [DA]
`use-ai-chat.ts:252-269` — Unmatched ID from buffer reset silently ignored.

### LOW-9: Empty-Content Documents Stuck in "syncing" Status [DA]
`app/ai/embedding_service.py:230-233` — Counted as succeeded but never updated.

### LOW-10: Pipe Characters in Cell Values Break Markdown Tables [DA]
`app/ai/sql_executor.py:83-88` — No escaping of `|` in `str(val)`.

### LOW-11: `understand_image` Downloads Without Size Limit [DA]
`app/ai/agent/tools/utility_tools.py:158` — 500 MB TIFF downloaded into memory.

### LOW-12: Serial Batch Embedding — No Parallelism [QE]
`app/ai/embedding_service.py:213-256` — Sequential DB+API per document in batch.

### LOW-13: LLM Config Constants in `graph.py` Instead of `constants.py` [CR]
`app/ai/agent/graph.py:32-34` — `AGENT_TEMPERATURE`, `AGENT_MAX_TOKENS`, `AGENT_REQUEST_TIMEOUT`.

### LOW-14: `_extract_clarification` Returns `None` vs `[]` for No Options [CR]
`app/ai/agent/graph.py:150-166` — Inconsistent; callers must `if options:` guard.

### LOW-15: RBAC Check After Full ORM Eager Load [CR]
`app/ai/agent/tools/task_tools.py:193-214` — Full relationship load before access check.

### LOW-16: Magic `200` Row Limit Repeated Without Constant [CR]
`task_tools.py:131,434`, `project_tools.py:529` — Should be `MAX_TASK_LIST_ROWS` in constants.

### LOW-17: `_serialize` Duplicated Between `helpers.py` and `sql_executor.py` [CR]
`helpers.py:605-613`, `sql_executor.py:31-52` — Same UUID/datetime/None serialization.

### LOW-18: `createThumbnailDataUrl`/`createLightboxDataUrl` Share Identical Logic [CR]
`use-ai-chat.ts:36-108` — ~50 lines of duplication. Extract `_resizeImageToDataUrl()`.

### LOW-19: `useDocumentIndexStatus` Missing `refetchOnMount: 'always'` [QE]
`electron-app/src/renderer/hooks/use-ai-config.ts:508` — Stale data for 60s after remount.

### LOW-20: `cancelStream` Silently Swallows Server Response [CR]
`use-ai-chat.ts:765-770` — At minimum log a debug message on error.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| CRITICAL | 7 | Prompt jailbreak, shared mutable state, context leaks, IDOR, stale RBAC, stale task keys |
| HIGH | 18 | SQL injection depth, SSRF, rate limit bypass, DRY violations, re-render storms, missing timeouts |
| MEDIUM | 24 | Input validation, markdown injection, N+1 queries, commit inconsistency, email PII exposure |
| LOW | 20 | Minor cleanup, constants, serialization duplication, edge-case UX issues |
| **TOTAL** | **69** | |

---

## Priority Remediation Order

### Immediate (Security-Critical)
1. **CRIT-1** — Append DB prompt after hardcoded base; never replace
2. **CRIT-4** — Return 503 on Redis unavailability for `/resume`, `/replay`, `/history`
3. **HIGH-1** — Verify AI DB role has `REVOKE INSERT/UPDATE/DELETE/TRUNCATE/DROP/CREATE`
4. **HIGH-6** — Discard or scan client-supplied `conversation_history`
5. **HIGH-2** — Re-validate `base_url` for SSRF at request time

### This Sprint (Data Integrity + Safety)
6. **CRIT-5** — Re-query RBAC from DB after interrupt resume
7. **CRIT-6** — Re-fetch `project_key` in post-interrupt session
8. **HIGH-5** — Add application-scope post-interrupt RBAC check
9. **HIGH-7** — Add timeout to non-streaming `resume_chat`
10. **MED-1** — Validate export link format before authenticated fetch

### Next Sprint (Architecture + Performance)
11. **CRIT-2** — Move caches into `AgentState`
12. **CRIT-3** — Remove `_ContextVarSyncDict`, use functions only
13. **CRIT-7** — Cancel abandoned tasks, close sessions on timeout
14. **HIGH-3** — Fix rate limit fallback to 1x, add CRITICAL alarm
15. **HIGH-15** — Fix Zustand re-render storm with `useShallow`

### Backlog (Code Quality)
16. **HIGH-8** — Extract `_resolve_entity` (DRY)
17. **HIGH-9** — Extract `_runStream` (DRY)
18. **HIGH-11** — Fix circular import
19. **HIGH-18** — Rate limiter factory pattern
20. Remaining MEDIUM and LOW findings
