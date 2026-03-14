# Chat Sessions -- Devils Advocate Audit (Round 1)

## Summary
NEEDS WORK -- DA-001 (concurrent session auto-create race) and DA-002 (silent persist data loss) are HIGH. DA-003 through DA-008 are MEDIUM covering auto-summarize timing, inflated token counts, stale session list cache, and session-switch state corruption. None are individually blockers but the aggregate risk is significant for a persistence-critical feature.

---

## Findings

### DA-001: Concurrent session auto-create race condition
- **Severity**: HIGH
- **Category**: Race Condition
- **Scenario**:
  1. User starts a new chat with no active session.
  2. Two POST /api/ai/chat/stream requests arrive within milliseconds (two browser tabs, React StrictMode double-invoke, or network retry).
  3. Both reach the else branch at ai_chat.py:1216 and open separate async_session_maker() contexts.
  4. Both INSERT a new ChatSession and commit. Two rows created.
  5. Frontend receives two session_id values from two SSE run_finished events. The second overwrites activeSessionId. The first session is orphaned with no messages.
- **Impact**: Session duplication. The orphan gets a heuristic title forever. The _job_id dedup prevents one session getting two title jobs but not two sessions each getting one. The real session may never get an LLM title.
- **Fix**: Add a unique partial index on (user_id, thread_id) WHERE thread_id IS NOT NULL, or use INSERT ... ON CONFLICT DO NOTHING. Alternatively generate session_id client-side and pass it with the first request.

---

### DA-002: Silent persist failure causes invisible data loss
- **Severity**: HIGH
- **Category**: Failure Mode
- **Scenario**:
  1. Stream finishes. onRunFinished calls authPost to /api/ai/sessions/SESSION_ID/messages.
  2. The persist call fails (network error, 5xx, expired token).
  3. use-ai-chat.ts:645 swallows the error silently.
  4. UI shows the conversation in memory. User switches sessions or refreshes. Messages are gone from the DB.
- **Impact**: Silent data loss. No retry, no toast, no indicator. User believes the conversation is saved but it is not.
- **Fix**: Surface persist errors with a toast. Retry 1-2 times with exponential backoff. The .catch(() => {}) on line 645 is the primary culprit.

---

### DA-003: Auto-summarize fires mid-stream against stale in-memory state
- **Severity**: MEDIUM
- **Category**: Race Condition
- **Scenario**:
  1. token_usage SSE event is emitted BEFORE run_finished (ai_chat.py lines 720-728 vs 730-738).
  2. Frontend at use-ai-chat.ts:280 checks usage.totalTokens > usage.contextLimit * 0.9 and immediately POSTs to /summarize with up_to_sequence: sidebarState.messages.length.
  3. sidebarState.messages.length is the in-memory count with no DB sequences yet (persist runs in onRunFinished, after stream ends).
  4. If up_to_sequence=3 but only 1 message is persisted, the summary covers an incomplete conversation.
  5. If no messages are persisted (first-ever turn near context limit), endpoint returns HTTP 400. The .catch(() => {}) on line 294 swallows it. contextSummary stays null and the 90% check fires on every subsequent token_usage event, creating a thundering herd.
- **Impact**: Incorrect or empty context summary. Multiple concurrent summarize calls per stream. summary_up_to_msg_seq written to sequences that do not exist in the DB.
- **Fix**: Defer auto-summarize to onRunFinished (after persist), using persisted next_sequence - 1 as up_to_sequence. Add a summarizePending flag to prevent concurrent calls.

---

### DA-004: Token usage sums ALL graph history turns, not the current context window
- **Severity**: MEDIUM
- **Category**: Assumption
- **Scenario**:
  1. ai_chat.py:714-718 iterates over ALL messages in graph_state.values[messages] and sums usage_metadata.
  2. LangGraph stores the full conversation history in the thread checkpoint. After turn 3, the checkpoint contains all 3 turns each with its own usage_metadata.
  3. token_usage reports CUMULATIVE total across all historical turns, not the context window for the current LLM call.
  4. The frontend comparison usage.totalTokens > usage.contextLimit * 0.9 fires prematurely on long conversations.
- **Impact**: False-positive context warnings and premature auto-summarize.
- **Fix**: Read usage_metadata only from the LAST assistant message in graph_state, which reflects actual tokens in the most recent LLM call.

---

### DA-005: Auto-created session never appears in session list cache
- **Severity**: MEDIUM
- **Category**: Edge Case
- **Scenario**:
  1. Auto-created session (ai_chat.py:1219-1230) is created directly in the backend, bypassing POST /api/ai/sessions/.
  2. useChatSessions (use-chat-sessions.ts:54-61) has staleTime: Infinity and refetchOnWindowFocus: false. It never re-fetches unless explicitly invalidated.
  3. onRunFinished sets activeSessionId but does NOT invalidate queryKeys.chatSessions.
  4. When user navigates back to the sessions list, the new session is absent. Invisible until app restart (gcTime: 24h).
- **Impact**: User cannot rename, archive, or delete the auto-created session from the list view.
- **Fix**: After setting activeSessionId in onRunFinished, call queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions }). Import queryClient from query-client.ts into use-ai-chat.ts.

---

### DA-006: Session switch while streaming -- cancellation not awaited, state can corrupt
- **Severity**: MEDIUM
- **Category**: Race Condition
- **Scenario**:
  1. User is receiving a stream for session A.
  2. User clicks back-to-sessions and immediately selects session B.
  3. handleBackToSessions calls cancelStream() without awaiting it (ai-sidebar.tsx:158-160).
  4. cancelStream sends a cancel POST and aborts the reader concurrently.
  5. setActiveSession(sessionB_id, ...) immediately clears messages and sets new session context.
  6. If buffered SSE bytes from session A arrive after the switch (reader.read() loop has no activeSessionId guard), onRunFinished fires for session A and overwrites the session B context.
  7. User sees session B messages but the store believes they are in session A. Messages are persisted under session A.
- **Impact**: State corruption -- wrong session_id in the store, messages persisted to the wrong session.
- **Fix**: Await cancelStream() before changing session state, or guard setActiveSessionId in onRunFinished to verify the incoming session_id matches the current activeSessionId.

---

### DA-007: Only last two messages persisted -- gaps compound on failure and resume paths
- **Severity**: MEDIUM
- **Category**: Assumption
- **Scenario**:
  1. onRunFinished (use-ai-chat.ts:629-647) persists only msgs[msgs.length - 2] (last user) and msgs[msgs.length - 1] (last assistant).
  2. If persist fails silently for turn N (see DA-002), turn N+1 saves only itself. Turn N is permanently lost. DB sequences skip N-1 to N+1.
  3. For resumeInterrupt or replay paths where the graph generates multiple new assistant messages, only the final message is saved.
- **Impact**: Incomplete conversation history. Pagination appears valid but the conversation is logically gapped.
- **Fix**: Track last_persisted_sequence in the frontend store. On each onRunFinished, persist all messages since last_persisted_sequence rather than just the final two.

---

### DA-008: summarize up_to_sequence uses in-memory count, not DB sequence
- **Severity**: MEDIUM
- **Category**: Assumption
- **Scenario**:
  1. Auto-summarize posts up_to_sequence: sidebarState.messages.length (use-ai-chat.ts:286).
  2. sidebarState.messages includes DB-loaded messages (real sequences 1-N) plus new in-memory messages (no DB sequence yet).
  3. If there are 4 DB messages (sequences 1-4) and 1 new in-memory one, up_to_sequence=5. DB only has 1-4. Endpoint writes summary_up_to_msg_seq=5 but message 5 was not included in the summary.
  4. Next turn, contextSummary is set but the model receives a misleading summary boundary and may re-receive supposedly summarized context.
- **Impact**: Context summary covers the wrong range. Prompt size may increase rather than decrease.
- **Fix**: Use the next_sequence returned by the persist endpoint as up_to_sequence, not the in-memory count.

---

### DA-009: Infinite scroll sentinel fires immediately on session open
- **Severity**: LOW
- **Category**: Edge Case
- **Scenario**:
  1. A session with has_more: true is loaded. The sentinel div renders at the top of the message list.
  2. IntersectionObserver fires immediately on mount if the sentinel is in the initial viewport.
  3. fetchNextPage is called before the user has scrolled.
  4. The requestAnimationFrame scroll correction races with scrollContainer initialization. If scrollContainer is null when fetchNextPage resolves, the user ends up at the top of the list.
- **Impact**: User opens a session and sees oldest messages instead of most recent ones.
- **Fix**: Only start observing the sentinel after the initial scroll-to-bottom has settled. Use an initialScrollSettled ref flag.

---

### DA-010: Title generation ARQ job silently fails with no retry
- **Severity**: LOW
- **Category**: Failure Mode
- **Scenario**:
  1. generate_session_title (worker.py:1626) catches all exceptions and returns status error without re-raising.
  2. ARQ treats a non-exception return as success. No retry is scheduled.
  3. The _job_id dedup means only one title job is ever enqueued per session.
  4. If the LLM is down when the job runs, the session title is permanently stuck as the heuristic truncated string.
- **Impact**: Sessions display truncated user messages as titles with no recovery.
- **Fix**: Re-raise the exception so ARQ retries, or re-enqueue with _defer_by on failure. Add max_tries=3 to enqueue_job.

---

### DA-011: session_id type mismatch causes 500 instead of 400
- **Severity**: LOW
- **Category**: Edge Case
- **Scenario**:
  1. _get_owned_session accepts session_id: str and passes it directly to SQLAlchemy WHERE ChatSession.id == session_id.
  2. A malformed UUID string causes asyncpg to raise DataError rather than returning None.
  3. DataError propagates as HTTP 500 Internal Server Error.
- **Impact**: Confusing error response; unnecessary stack traces in logs.
- **Fix**: Declare the path parameter as UUID type in FastAPI, or catch ValueError and DataError and raise HTTP 400.

---

### DA-012: conversation_history strips assistant messages -- multi-turn context broken for new threads
- **Severity**: LOW
- **Category**: Assumption
- **Scenario**:
  1. ai_chat.py:1150-1154 filters conversation_history to role==user only for injection safety.
  2. Frontend sends both user and assistant messages in conversationHistory (use-ai-chat.ts:676-684).
  3. All assistant messages are silently discarded. For a new thread_id with no LangGraph checkpoint, the model sees only user messages -- no assistant context.
  4. Blair appears to have amnesia about its own prior answers.
- **Impact**: Multi-turn conversational continuity is broken for new sessions. Users find Blair ignoring prior context.
- **Fix**: Either rely exclusively on LangGraph checkpoints for history and omit conversation_history for existing thread_ids; or sign the history payload with HMAC; or document this as an intentional security tradeoff.
