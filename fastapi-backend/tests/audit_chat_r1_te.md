# Chat Sessions - Test Engineering Audit (Round 1)

## Summary

NEEDS WORK -- The feature introduces a new CRUD router (chat_sessions.py), a new ARQ background job (generate_session_title), session auto-create in ai_chat.py, and a token-usage SSE event, but zero dedicated test files exist for any of these. Existing tests (test_agent_chat.py, test_ai_chat_helpers.py) do not exercise the new router. Frontend hook tests are absent for use-chat-sessions.ts. Coverage for this feature is effectively 0%.

---

## Existing Test Coverage

### Backend

- tests/test_agent_chat.py -- Tests ChatRequest/ChatResponse schemas, image validation, thread ownership IDOR guards. No session CRUD, no token_usage emission, no session auto-create.
- tests/test_ai_chat_helpers.py -- Tests _build_chat_response, _register_cancel_event, _thread_owners_fallback, get_tool_db. No session lifecycle, no summarize endpoint.
- tests/test_arq_worker.py -- Tests archive and presence cleanup jobs only. generate_session_title is not tested at all.

### Frontend

- use-ai-chat.test.ts -- Tests SSE streaming, parseSSEChunk, sendMessage, cancelStream. token_usage event handling not explicitly tested; session_id plumbing not verified.
- use-websocket-cache.test.ts -- WebSocket cache; not related.
- No tests for use-chat-sessions.ts, chat-session-list.tsx, or token-usage-bar.tsx.

---

## Missing Test Cases

### TE-001: Session CRUD - Happy path for all five endpoints
- **Priority**: CRITICAL
- **Scope**: backend
- **What to test**: POST /api/ai/sessions/ creates a session (201, returns ChatSessionSummary); GET /api/ai/sessions/ lists it; PATCH renames and/or archives it; DELETE returns 204 and removes from DB; GET /{session_id}/messages returns empty page for fresh session.
- **Why**: Zero integration coverage for the primary router. Any wiring error (missing router registration, wrong prefix, schema mismatch) would ship undetected.

### TE-002: Session CRUD - IDOR prevention on all endpoints
- **Priority**: CRITICAL
- **Scope**: backend
- **What to test**: User A creates session; User B sends PATCH, DELETE, GET messages, POST messages, POST summarize to that session ID -- all must return 403 (not 404, not 200).
- **Why**: _get_owned_session is the only guard. A logic regression would allow full cross-user access to chat history. This is the highest-security risk in the feature.

### TE-003: 100-session cap - auto-archive oldest on overflow
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: Create 100 active sessions for a user, then POST a 101st. Verify (a) oldest session is_archived=True, (b) active count stays at 100, (c) new session returned successfully.
- **Why**: The active_count - 99 batch-archive logic (chat_sessions.py:128) is non-trivial. Off-by-one errors could archive wrong sessions or fail to enforce the limit.

### TE-004: Message persistence - sequence ordering and cursor pagination
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: POST 25 messages in two batches; GET with limit=20 returns the 20 most recent in chronological order with has_more=True; GET with before=<first_sequence> returns the remaining 5 with has_more=False.
- **Why**: The before cursor pagination reversal (chat_sessions.py:211 rows.reverse()) is subtle. A bug delivers messages out of order or loses history.

### TE-005: Message persistence - message_count and last_message_preview updates
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: After persisting a batch with user + assistant messages, verify session.message_count equals the batch size, last_message_preview equals the first 150 chars of the last non-error assistant message, and updated_at advances.
- **Why**: Both fields drive the session list UI. A silent bug results in stale previews or wrong counts.

### TE-006: Auto-title heuristic - first persist triggers title and ARQ enqueue
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: POST messages to a fresh session (max_seq=0); verify (a) session.title set to truncated first user message with ellipsis when content > 60 chars; (b) arq_redis.enqueue_job called with generate_session_title and _job_id; (c) second POST does NOT re-enqueue.
- **Why**: Truncation logic at chat_sessions.py:282-285 uses rsplit that can produce unexpected titles. The idempotency guard is only verified if the enqueue path is exercised.

### TE-007: Auto-title heuristic - no user message in batch
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: POST messages containing only role=assistant entries to a fresh session. Verify title remains New Chat and no ARQ job is enqueued.
- **Why**: first_user_content stays None. If the guard changed, a title-generation job would fire for assistant-only batches.

### TE-008: generate_session_title ARQ job - success and skip paths
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: (a) Valid session_id + mock LLM returning a title => title updated in DB, returns {status: success}; (b) Non-existent session_id => {status: skipped}; (c) LLM raises exception => {status: error}, session title unchanged.
- **Why**: test_arq_worker.py has zero coverage of this job. LLM failure silently swallows errors.

### TE-009: generate_session_title ARQ job - no chat model configured
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: Mock ProviderRegistry.get_chat_model() to return None; verify job returns {status: skipped} without touching session title.
- **Why**: New installations without a configured model should not corrupt session titles or throw unhandled exceptions.

### TE-010: Summarize endpoint - happy path
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: Create session, persist 10 messages (user/assistant/error mix), call POST summarize with up_to_sequence=8; verify only non-error messages included, context_summary set, summary_up_to_msg_seq==8.
- **Why**: The error-message filter at chat_sessions.py:329 has no test. Wrong filtering would summarize error messages as facts.

### TE-011: Summarize endpoint - no messages found returns 400
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: Call summarize with up_to_sequence=999 on a session with no messages (or all errors). Verify 400 with No messages to summarize.
- **Why**: Missing guard results in an empty conversation string sent to LLM, wasting tokens.

### TE-012: Summarize endpoint - LLM unavailable returns 503
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: Mock ProviderRegistry.get_chat_model() to return None; verify 503 with No chat model configured.
- **Why**: Distinguishes model not configured (503) from summarization failed (500) for frontend error handling.

### TE-013: Session auto-create in /api/ai/chat/stream
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: POST to /api/ai/chat/stream without session_id; verify (a) new ChatSession row created linked to current_user.id, (b) SSE run_started event contains non-empty session_id, (c) session thread_id populated.
- **Why**: ai_chat.py:1216-1230 is the auto-create path. Failure means frontend never gets a session_id and cannot persist history.

### TE-014: Session auto-create - provided session_id with wrong owner silently ignored
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: POST to /api/ai/chat/stream with session_id belonging to another user; verify endpoint does NOT raise 403 but continues with session_id empty so stream still works.
- **Why**: The ownership check at ai_chat.py:1210 is intentionally fail-open but untested. A regression could block valid requests or allow IDOR.

### TE-015: Token usage SSE event emission
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: In a mocked stream run, verify SSE stream emits an event with event=token_usage containing input_tokens, output_tokens, total_tokens, and context_limit fields.
- **Why**: token_usage event emission (ai_chat.py:721-726) drives TokenUsageBar. No test exercises this code path.

### TE-016: Context limit sourced from AiModel.max_tokens
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: Insert AiModel with is_default=True, capability=chat, max_tokens=32000; verify SSE token_usage event contains context_limit=32000 rather than hardcoded default 128000.
- **Why**: DB lookup at ai_chat.py:1194-1202 overrides the default. If broken, users always see wrong context limit.

### TE-017: List sessions - include_archived filter
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: Create 2 active + 1 archived session; GET /api/ai/sessions/ returns 2; GET with include_archived=true returns 3.
- **Why**: The is_archived filter at chat_sessions.py:86 is untested. A regression leaks archived sessions into the default list.

### TE-018: List sessions - pagination
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: Create 15 sessions; GET with limit=10&offset=0 returns 10 and total=15; GET with limit=10&offset=10 returns 5.
- **Why**: Total count is computed from a subquery (chat_sessions.py:90-91). If total is wrong, UI pagination controls break.

### TE-019: PersistMessagesRequest - max 10 messages enforced
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: POST messages with 11 entries; verify 422 validation error.
- **Why**: PersistMessagesRequest.messages has max_length=10 (schemas/ai_chat.py:228). This Pydantic constraint should be confirmed at the API boundary.

### TE-020: ChatSessionUpdate - partial updates do not clobber other fields
- **Priority**: MEDIUM
- **Scope**: backend
- **What to test**: PATCH with only title field should not change is_archived; PATCH with only is_archived should not change title.
- **Why**: Conditional assignment at chat_sessions.py:163-166 using if body.title is not None could regress if changed.

### TE-021: Delete session - cascades to messages
- **Priority**: HIGH
- **Scope**: backend
- **What to test**: Create session, persist 5 messages, DELETE session, verify all 5 ChatMessage rows are removed from DB.
- **Why**: Cascade is declared in the ORM relationship. If db.delete() is replaced with a bulk DELETE statement, cascade breaks and orphaned messages accumulate.

### TE-022: Frontend - useChatSessions hook cache mutation on create
- **Priority**: HIGH
- **Scope**: frontend
- **What to test**: Render a component using useCreateSession; call the mutation; verify queryKeys.chatSessions cache updated with new session at head and total increments by 1 without a refetch.
- **Why**: The onSuccess cache mutation in use-chat-sessions.ts:122-137 is complex object patching. If cache shape changes, the update silently no-ops.

### TE-023: Frontend - useUpdateSession archive removes session from cache
- **Priority**: HIGH
- **Scope**: frontend
- **What to test**: Pre-populate cache with 3 sessions; call useUpdateSession with is_archived: true for one; verify it is removed from cached list and total decrements.
- **Why**: Archive branch at use-chat-sessions.ts:159 filters by id. A typo leaves the archived session visible in the list.

### TE-024: Frontend - useDeleteSession removes messages cache for deleted session
- **Priority**: MEDIUM
- **Scope**: frontend
- **What to test**: Pre-populate queryKeys.chatMessages(id) cache; call useDeleteSession; verify queryClient.removeQueries called for that message cache key.
- **Why**: use-chat-sessions.ts:195 calls removeQueries. If removed during refactoring, stale messages appear when switching back to a deleted session.

### TE-025: Frontend - TokenUsageBar color thresholds
- **Priority**: LOW
- **Scope**: frontend
- **What to test**: Render TokenUsageBar with tokenUsage at 49%, 74%, 89%, and 95% utilization; verify bar receives bg-emerald-500, bg-amber-500, bg-orange-500, and bg-red-500 respectively.
- **Why**: Color-coding is the primary UX signal for context pressure. Threshold boundary errors give users misleading feedback.

### TE-026: Frontend - TokenUsageBar renders null when no token usage
- **Priority**: LOW
- **Scope**: frontend
- **What to test**: Render TokenUsageBar with tokenUsage=null; verify component renders nothing.
- **Why**: token-usage-bar.tsx:18 early-returns null. A regression renders an empty/broken bar on every fresh session.

### TE-027: Frontend - useChatMessages infinite query next page param
- **Priority**: HIGH
- **Scope**: frontend
- **What to test**: Mock API to return has_more=true with 20 messages where first sequence=5; verify getNextPageParam returns 5; mock second page with has_more=false; verify getNextPageParam returns undefined.
- **Why**: getNextPageParam at use-chat-sessions.ts:83 uses lastPage.messages[0]?.sequence. If backend changes sort order, infinite scroll loops or stops.

### TE-028: Frontend - ChatSessionList date grouping
- **Priority**: LOW
- **Scope**: frontend
- **What to test**: Render ChatSessionList with sessions spanning today, yesterday, 4 days ago, and 14 days ago; verify four groups render with correct session membership.
- **Why**: getDateGroup uses new Date() comparisons. A midnight boundary bug misplaces sessions.

### TE-029: Frontend - ChatSessionList filter by title and preview
- **Priority**: MEDIUM
- **Scope**: frontend
- **What to test**: Render list with 3 sessions; type into filter input; verify only sessions whose title or lastMessagePreview match are shown case-insensitively.
- **Why**: Filter at chat-session-list.tsx:192-198 uses two includes() checks. If field names change, filter silently returns no results.

### TE-030: Backend - SummarizeRequest.up_to_sequence minimum validation
- **Priority**: LOW
- **Scope**: backend
- **What to test**: POST summarize with up_to_sequence=0; verify 422 validation error.
- **Why**: SummarizeRequest.up_to_sequence has ge=1. Confirm Pydantic enforces this at the API boundary.

