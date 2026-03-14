# Chat Sessions - Security Audit (Round 1)

## Summary
NEEDS WORK -- Overall security posture is solid: all endpoints require JWT authentication, IDOR is prevented by _get_owned_session, and check_chat_rate_limit (30 req/min) is applied on every route. However three issues warrant remediation: a UUID type confusion degrading the 404/500 boundary, an unbounded summarize endpoint enabling LLM cost abuse, and missing UUID validation on session_id in ChatRequest.

---

## Findings

### SA-001: session_id Path Parameter Accepts Arbitrary Strings - UUID Cast Leaks 500 Errors
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/chat_sessions.py:56-66
- **Issue**: _get_owned_session receives session_id: str and passes it to ChatSession.id == session_id. PostgreSQL raises DataError for non-UUID strings, propagating as an unhandled 500 instead of 422. Affects all five path-parameter routes (PATCH, DELETE, GET /messages, POST /messages, POST /summarize).
- **Impact**: Information leakage via 500 error bodies. No SQL injection risk (SQLAlchemy parameterises), but internal DB error messages are exposed.
- **Fix**: Declare path parameter as uuid.UUID in all five route signatures. FastAPI validates UUID format before the handler and returns 422 automatically.

---

### SA-002: session_id in ChatRequest Has No UUID Format Validation
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/schemas/ai_chat.py:70-74, fastapi-backend/app/routers/ai_chat.py:1204-1231
- **Issue**: ChatRequest.session_id is str | None with max_length=256 only. The auto-create flow at ai_chat.py:1207-1211 performs a raw DB lookup. A non-UUID value causes DataError swallowed at line 1231, silently auto-creating a new session.
- **Impact**: No data disclosure, but misleading UX and log noise. Malformed UUID probing is undetected at validation.
- **Fix**: Add UUID regex pattern validation and max_length=36 to ChatRequest.session_id.

---

### SA-003: POST /{session_id}/summarize Shares Chat Rate Limit - LLM Cost Abuse
- **Severity**: HIGH
- **File**: fastapi-backend/app/routers/chat_sessions.py:309-376
- **Issue**: The summarize endpoint calls llm.ainvoke() with up to 10,000 chars and shares check_chat_rate_limit (30 req/60s) with cheap CRUD ops. At ~4-5K tokens per call, a user can drive ~120-150K LLM output tokens per minute from this endpoint alone.
- **Impact**: Authenticated cost abuse vector. A single user drives disproportionate LLM API spend.
- **Fix**: Apply dedicated stricter rate limit (e.g. 5 calls/min per user). Add minimum message-count guard. Validate up_to_sequence does not exceed session message_count.

---

### SA-004: generate_session_title Worker Has No Ownership Re-Validation
- **Severity**: LOW
- **File**: fastapi-backend/app/worker.py:1626-1663
- **Issue**: ARQ job generate_session_title(ctx, session_id, first_message) updates session.title without verifying session.user_id. Compromised Redis queue access could allow title overwrite on any session.
- **Impact**: Requires out-of-band Redis compromise. Not exploitable from the HTTP API alone.
- **Fix**: Pass user_id to the job and verify session.user_id == user_id before writing.

---

### SA-005: PersistMessageEntry.sources Has No Size Limit - JSONB Storage Amplification
- **Severity**: LOW
- **File**: fastapi-backend/app/schemas/ai_chat.py:215-228, fastapi-backend/app/models/chat_message.py:28
- **Issue**: sources is dict | list | None with no size cap. The DB column is JSONB (unbounded). Max 10 messages per request limits call frequency but not individual payload size.
- **Impact**: Storage amplification per API call. An authenticated user can rapidly inflate DB storage.
- **Fix**: Add a field validator capping serialised sources JSON to 64KB per entry.

---

### SA-006: message_count Incremented Without DB Lock - Race Condition
- **Severity**: LOW
- **File**: fastapi-backend/app/routers/chat_sessions.py:263
- **Issue**: session.message_count += len(body.messages) is a read-modify-write in application memory. Concurrent persist requests from two browser tabs can race and undercount.
- **Impact**: Metadata inaccuracy only. message_count drives display and auto-title heuristics, not security decisions.
- **Fix**: Use update(ChatSession).values(message_count=ChatSession.message_count + N) for atomic DB-side increment.

---

### SA-007: Auto-Summarize Sends UI Message Count as up_to_sequence - Always Wrong
- **Severity**: LOW
- **File**: electron-app/src/renderer/components/ai/use-ai-chat.ts:285-294
- **Issue**: Auto-summarize fires with up_to_sequence: sidebarState.messages.length (UI in-memory list count, not persisted DB sequence numbers). Backend returns 400 No messages to summarize and the error is silently swallowed.
- **Impact**: Auto-summarization never succeeds in practice, wasting rate limit quota and leaving context unmanaged.
- **Fix**: Store next_sequence from POST /messages response in sidebar state and use it for up_to_sequence.

---

### SA-008: All Session CRUD Shares ai_chat Rate Limit Bucket - Self-DoS Risk
- **Severity**: LOW
- **File**: fastapi-backend/app/routers/chat_sessions.py:80,108,157,178,193,237,314
- **Issue**: All 7 session management endpoints share check_chat_rate_limit (30 req/60s). Cheap CRUD ops (list, rename, archive) consume the same quota as LLM chat calls.
- **Impact**: Users can inadvertently block themselves from AI chat through normal UI activity.
- **Fix**: Use a separate higher-limit rate limiter for non-LLM CRUD (e.g. 120 req/60s).

---

### SA-009: LLM Prompt Injection via Session Title Generation
- **Severity**: LOW
- **File**: fastapi-backend/app/worker.py:1650-1655
- **Issue**: first_message[:500] is passed directly as HumanMessage content to the LLM. A crafted message can manipulate the generated title stored in session.title (String(200)).
- **Impact**: Stored LLM prompt injection scoped only to the owning user. Output capped at 200 chars. No escalation path or cross-user exposure.
- **Fix**: Add output sanitisation. Strengthen system prompt to prohibit following embedded user instructions.

---

### SA-010: No Unique Constraint on (session_id, sequence) - Duplicate Sequences Possible
- **Severity**: LOW
- **File**: fastapi-backend/alembic/versions/20260306_add_chat_sessions.py:60-64
- **Issue**: ix_chatmessages_session_seq index is not UNIQUE. Application-level max_seq + i + 1 computation without a DB row lock can produce duplicates under concurrent persist requests.
- **Impact**: Data integrity gap -- duplicate sequences distort summarize window and pagination.
- **Fix**: Add UniqueConstraint on (session_id, sequence) to the migration.

---

## Security Controls Confirmed Working

| Control | Status | Notes |
|---|---|---|
| JWT auth on all endpoints | PASS | get_current_user on every route |
| IDOR prevention via ownership check | PASS | _get_owned_session verifies session.user_id == current_user.id |
| IDOR on stream session_id auto-create | PASS | sess.user_id == current_user.id at ai_chat.py:1210 |
| Rate limiting | PASS | check_chat_rate_limit (30/min) on all 7 routes |
| 100 active session cap with auto-archive | PASS | Overflow auto-archives oldest sessions |
| Message batch limit | PASS | max_length=10 on PersistMessagesRequest.messages |
| Role validation in messages | PASS | DB CHECK constraint + schema pattern enforcement |
| Content length limit | PASS | max_length=32_000 on PersistMessageEntry.content |
| Conversation history size cap | PASS | 50 entries + 500K chars total in ChatRequest |
| LLM input capped at 10K chars | PASS | conversation[:10_000] in summarize endpoint |
| Session title output capped | PASS | [:200] on LLM title response in worker |
| Data isolation | PASS | All queries filter by user_id; no cross-user data exposure found |
| Delete cascade | PASS | ondelete=CASCADE on ChatMessages.session_id FK |
| DB check constraint on role | PASS | CHECK (role IN user,assistant) in migration |
| SQL injection | PASS | SQLAlchemy ORM with parameterised queries throughout |
| XSS via message content | PASS | Backend stores raw text; Electron app handles rendering |
