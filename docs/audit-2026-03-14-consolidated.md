# Consolidated Audit Report — 2026-03-14

**Target:** Production readiness at 5,000 concurrent users / 1 server instance
**Auditors:** Code Reviewer (Backend Perf), Code Reviewer (Blair AI Quality), Security Analyst, Quality Engineer, Test Engineer, Devil's Advocate
**Mode:** Read-only — no code modified

---

## Executive Summary

6 parallel audits identified **93 findings** across backend performance, AI agent quality, security, frontend quality, test coverage, and failure modes. After deduplication (many findings overlap across auditors), the consolidated list is **~70 unique issues**.

### Critical / Must-Fix Before Production

| # | Area | Issue | Auditors |
|---|------|-------|----------|
| 1 | **Blair AI** | RRF deduplicates by document_id, collapsing all chunks to 1 per doc — root cause of wrong context + shallow answers | Reviewer2 |
| 2 | **Blair AI** | Chunk overlap bleeds across heading boundaries (education into experience) | Reviewer2 |
| 3 | **Scale** | Per-process `_agent_semaphore` allows 200 concurrent agents (4 workers × 50) vs intended 50 — exhausts DB pool | Reviewer1, QE, DA |
| 4 | **Scale** | DB pool `50 + 100 overflow` × N workers exceeds PostgreSQL `max_connections` | Reviewer1, DA |
| 5 | **Security** | `BackgroundTasks = Depends()` crash on startup — **already fixed this session** | — |
| 6 | **Security** | Comment attachment upload has no permission check (`files.py:358`) | Security |
| 7 | **Security** | Token blacklist fail-open when Redis down (`REDIS_REQUIRED=false` default) | Security |
| 8 | **Scale** | `max_jobs=10` hard-coded in ARQ worker — embedding queue stalls under load | Reviewer1 |

### Top 20 Prioritized Findings (deduplicated)

#### CRITICAL (fix before go-live)

**C1 — RRF chunk dedup drops all but 1 chunk per document**
- Files: `retrieval_service.py:563-599`
- Impact: Wrong answers (education vs experience) + shallow answers (pgvector)
- Fix: Key RRF on `(source_type, document_id, chunk_index)` not `(source_type, document_id)`

**C2 — Chunk overlap bleeds across heading boundaries**
- File: `chunking_service.py:792-820`
- Impact: "Experience" content leaks into "Education" chunk, corrupting embeddings
- Fix: Skip overlap when `chunks[i-1].heading_context != chunks[i].heading_context`

**C3 — Per-process agent semaphore (not distributed)**
- File: `ai_chat.py:74-75`
- Impact: 4 workers × 50 = 200 concurrent agents; DB pool (150) exhaustion
- Fix: Redis-backed distributed semaphore (`INCR`/`DECR` with atomic ceiling check)

**C4 — DB connection pool sizing**
- Files: `config.py:55-56`, `database.py:16-24`
- Impact: 9 workers × 150 pool = 1,350 PG connections vs default `max_connections=200`
- Fix: PgBouncer in transaction mode; reduce per-worker pool to 5-10

#### HIGH (fix in first sprint)

**H1 — No `read_document` tool for Blair agent**
- File: `knowledge_tools.py` (entire file)
- Impact: Agent can't read full document content — only gets search chunks
- Fix: Add `read_document(doc_id)` tool returning `content_plain` (capped at 12K chars)

**H2 — System prompt forbids re-searching same query**
- File: `prompts.py:213-217`
- Impact: Agent gets 1 chance to find content; can't drill deeper
- Fix: Allow re-search with different/more specific query phrasing

**H3 — Tool results truncated to 500 chars in research accumulator**
- Files: `explore.py:354-357`, `synthesize.py:62-64`
- Impact: 16K search results reduced to 500 chars before synthesis
- Fix: Raise to 3-4K chars per entry; reduce window from 15 to 5-8 entries

**H4 — Double truncation: 16K then 8K**
- Files: `agent_tools.py:29-31`, `knowledge_tools.py:210`
- Impact: `search_knowledge` re-truncates at 8K after RAG tool already curated 16K
- Fix: Pass `max_len=MAX_KNOWLEDGE_OUTPUT_CHARS` to `_truncate` in search_knowledge

**H5 — `follow_up` fast-path skips exploration**
- File: `routing.py:44-51`
- Impact: Follow-up questions about documents answered from LLM parametric knowledge, not KB
- Fix: Restrict fast-path to `intent="greeting"` only

**H6 — Comment attachment upload — no authorization**
- File: `files.py:358-370`
- Impact: Any authenticated user can upload to any comment
- Fix: Add `verify_task_attachment_access(comment.task_id, ...)` before accepting upload

**H7 — `GET /api/files/entity/task/{id}` — no project membership check**
- File: `files.py:945-1007`
- Impact: Any authenticated user can enumerate attachments on any task
- Fix: Add `verify_task_attachment_access` for task/comment entity types

**H8 — Token blacklist fail-open (default)**
- Files: `auth_service.py:210-270`, `config.py:58`
- Impact: Revoked JWTs accepted during Redis outage (up to 15 min)
- Fix: Set `REDIS_REQUIRED=true` in production; add startup check

**H9 — WebSocket per-user connection limit check outside lock (TOCTOU)**
- File: `manager.py:336-343`
- Impact: Burst of concurrent upgrades bypasses the limit (10× cap)
- Fix: Move limit check inside `self._lock` before `websocket.accept()`

**H10 — `LOCK_TTL_SECONDS` frozen at import time**
- File: `document_lock_service.py:24-28`
- Impact: Admin can't change lock TTL at runtime; locked docs stay locked
- Fix: Replace with getter function `_get_lock_ttl()` called at each Lua invocation

**H11 — Cross-worker cancel is silently dropped**
- File: `ai_chat.py:80-92`
- Impact: Cancel request routes to different worker → "not found" → stream runs 5 min
- Fix: Publish cancel via Redis pub/sub channel; workers subscribe and set local event

**H12 — `_active_stream_cancels` never pruned for completed streams**
- File: `ai_chat.py:80-92`
- Impact: Stale cancel events can accidentally cancel future streams reusing thread_id
- Fix: Pop `thread_id` from dict in `_guarded_sse_stream` finally block

**H13 — Redis pool too small (50) for 5K-user broadcast storm**
- File: `redis_service.py:47-53`
- Impact: WebSocket publishes block waiting for pool connections
- Fix: Increase `redis_max_connections` to 200-500

**H14 — INCR/EXPIRE race in `rate_limit_check`**
- File: `redis_service.py:444-447`
- Impact: Redis crash between INCR and EXPIRE → key persists forever, user permanently rate-limited
- Fix: Use Lua-atomized version from `AIRateLimiter` or `SET NX EX`

**H15 — Client disconnect during HITL → interrupt bypass**
- File: `ai_chat.py:859-1040`
- Impact: Unresolved interrupt in checkpoint; next message bypasses HITL confirmation
- Fix: Store "awaiting resume" flag in Redis; reject non-resume requests to interrupted threads

**H16 — `refetchOnWindowFocus: true` globally in Electron**
- File: `query-client.ts:207`
- Impact: Alt-tab back to app → thundering herd of stale query refetches
- Fix: Set global default to `false`; selectively enable for notifications

#### MEDIUM (fix in next 2 sprints)

| ID | Area | File | Issue |
|----|------|------|-------|
| M1 | AI | `prompts.py:316-338` | Classifier may route "experience" to projects/tasks, not knowledge |
| M2 | AI | `chunking_service.py:792-820` | Overlap crosses table boundaries → malformed chunk text |
| M3 | AI | `chunking_service.py:96-106` | Chunker config frozen at class definition time |
| M4 | Scale | `worker.py:1538-1547` | Fresh Redis pool opened on every import deferral |
| M5 | Scale | `worker.py:1086-1092` | Bulk "syncing" pre-update → 24h document limbo on crash |
| M6 | Scale | `worker.py:1510-1548` | Fixed 15s retry delay → thundering herd under sustained load |
| M7 | Scale | `room_auth.py:158-177` | 4 sequential DB queries per WebSocket room join |
| M8 | Scale | `retrieval_service.py:130-141` | RBAC scope resolution (2 queries) per AI retrieval, uncached |
| M9 | Scale | `ai_chat.py:910-914` | `wait_for` per SSE event creates 2K Task objects per stream |
| M10 | Scale | `ai_chat.py:784-798` | Token/summary DB writes block SSE before `run_finished` |
| M11 | Security | `rate_limiter.py:580` | IP spoofing via `X-Forwarded-For` (no trusted proxy config) |
| M12 | Security | `auth_service.py:98-100` | JWT access/refresh share same secret when `JWT_REFRESH_SECRET` unset |
| M13 | Security | `sql_executor.py:30-32` | SQL safety constants frozen at import time |
| M14 | Security | `.env.example` | Insecure defaults (`minioadmin`, empty keys, `REDIS_REQUIRED=false`) |
| M15 | Frontend | `ai-sidebar.tsx:91-97` | Full store subscription → AiSidebar re-renders at 60fps during streaming |
| M16 | Frontend | `markdown-renderer.tsx:614` | O(N lines) parse on every SSE chunk during streaming |
| M17 | Data | `ai_chat.py:1344-1382` | Session creation races past 100-session cap |
| M18 | Data | `ai_chat.py:1371-1384` | Ghost session ID emitted to frontend on commit failure |
| M19 | Data | `ai_chat.py:835` | Context summary overwrite not monotonic — last writer wins |
| M20 | WS | `manager.py:192-196` | `initialize_redis` double-subscribe race → duplicate message delivery |

#### LOW (backlog)

| ID | Area | Issue |
|----|------|-------|
| L1 | AI | Explore-specific iteration limits defined but never wired |
| L2 | Scale | Presence cleanup pipelines thousands of Redis commands at once |
| L3 | Scale | No global WebSocket connection cap |
| L4 | Scale | Pub/sub reconnect tight-loops on Redis outage, no backoff |
| L5 | Scale | In-memory aggregation in archive job loads all tasks |
| L6 | Frontend | `SessionRow` not memoized; mutation ref churn |
| L7 | Frontend | IndexedDB LRU eviction check hits DB on every write flush |
| L8 | Frontend | Phase 2 hydration hard-coded 2s setTimeout |
| L9 | Security | `verify_email_code` is idempotent on verified accounts → returns tokens without code check |
| L10 | Security | WebSocket room auth cache TTL: 5-min unauthorized access window after revocation |
| L11 | Data | `_pending_search_tasks` set in documents.py grows unboundedly |

---

## Test Coverage Gaps (from Test Engineer)

### Missing Coverage
- **WebSocket handlers**: No tests for `manager.py` connect/disconnect/broadcast flows
- **SSE streaming E2E**: No integration test for full chat streaming pipeline
- **Concurrent access**: No tests for race conditions (session cap, lock TOCTOU, thread ownership)
- **Redis failure**: No tests verifying behavior when Redis goes down mid-operation
- **Frontend AI components**: No component tests for AiSidebar, ChatInput, message renderer
- **Frontend hooks**: No tests for `useAiChat`, `useChatSessions` hooks

### Recommended Test Additions (priority order)
1. Integration test: Full chat stream with tool calls → persist → reload
2. Concurrency test: 10 parallel session creations → verify cap enforcement
3. Redis failure test: Disable Redis mid-request → verify fail-closed behavior
4. WebSocket reconnection storm test: 100 concurrent reconnects → verify no duplicate delivery
5. Frontend: Vitest component test for AiSidebar view switching + message hydration

---

## Quick Win Summary (high impact, low effort)

| Fix | Effort | Impact |
|-----|--------|--------|
| RRF dedup key: add `chunk_index` | 1 line | Fixes both reported Blair bugs |
| Skip overlap at heading boundaries | 5 lines | Fixes cross-section contamination |
| `refetchOnWindowFocus: false` global | 1 line | Eliminates Electron thundering herd |
| Pop `_active_stream_cancels` in finally | 1 line | Prevents stale cancel events |
| `LOCK_TTL_SECONDS` → getter function | 3 lines | Enables runtime lock TTL tuning |
| Cancel via Redis pub/sub | ~30 lines | Cross-worker cancel works |
| WS limit check inside lock | Move 5 lines | Prevents connection limit bypass |
| Ghost session ID: reset on commit fail | 1 line | Prevents 404 on frontend |
