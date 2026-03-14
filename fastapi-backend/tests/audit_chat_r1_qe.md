# Chat Sessions - Quality Engineering Audit (Round 1)

## Summary
NEEDS WORK -- The feature has solid architecture: correct cursor pagination index, clean optimistic
cache mutations, proper SSE buffer guards, and good React selector patterns. Three HIGH severity
bugs must be fixed before ship, plus several MEDIUM issues.

---

## Findings

### QE-001: total_input_tokens / total_output_tokens Always Zero in DB
- **Severity**: HIGH
- **File**: fastapi-backend/app/routers/ai_chat.py:711-718
- **Issue**: _stream_agent extracts token counts from graph state and emits a token_usage SSE event
  but never persists them to ChatSession. persist_messages does not accept token fields.
  total_input_tokens and total_output_tokens are always 0 in the database.
- **Impact**: Token stats in session list always zero. TokenUsageBar shows zero for historical
  sessions on reload. Any analytics or billing on these columns is broken.
- **Fix**: In persist_messages accept input_tokens/output_tokens and apply atomic SQL increment.
  Pass token counts from onRunFinished alongside messages.

### QE-002: Auto-Summarize Sends Wrong up_to_sequence
- **Severity**: HIGH
- **File**: electron-app/src/renderer/components/ai/use-ai-chat.ts:286
- **Issue**: Auto-summarize sends up_to_sequence equal to sidebarState.messages.length.
  messages.length equals rendered message count. ChatMessages.sequence is a 1-based DB integer
  incremented per persist call; after a page reload it can be much higher.
  Endpoint filters WHERE sequence <= up_to_sequence, may return 0 messages and 400.
- **Impact**: Auto-summarize silently fails at the worst moment (near-full context).
- **Fix**: Store next_sequence from the persist response in the sidebar store and use that integer.

### QE-003: Auto-Created Session Never Added to React Query Cache
- **Severity**: HIGH
- **File**: electron-app/src/renderer/components/ai/use-ai-chat.ts:624-627
- **Issue**: Server auto-creates a session (ai_chat.py:1216-1230). Frontend receives session_id
  via run_started SSE and calls setActiveSession. However queryKeys.chatSessions has staleTime:
  Infinity and refetchOnWindowFocus: false so no automatic re-fetch occurs. The new session is
  invisible in the history list until ChatSessionList remounts.
- **Impact**: User sends first message, Blair responds, user clicks Back to sessions -- newest
  conversation is missing. Appears as though the conversation was lost.
- **Fix**: When activeSessionId was null before the stream, call queryClient.invalidateQueries
  chatSessions after run_finished.

### QE-004: IntersectionObserver Recreated on Every Render During Streaming
- **Severity**: MEDIUM
- **File**: electron-app/src/renderer/components/ai/ai-sidebar.tsx:189-213
- **Issue**: The infinite-scroll useEffect includes messagesQuery in its dep array. useInfiniteQuery
  returns a new object reference on every text_delta SSE event. This causes observer.disconnect +
  new IntersectionObserver + observe dozens of times per second during streaming.
- **Impact**: GC pressure and DOM churn during streaming. Visible jank on low-end hardware.
- **Fix**: Extract fetchNextPage and isFetchingNextPage as individual stable deps instead of the
  whole messagesQuery object. React Query stabilizes these references.

### QE-005: Double DB Round-Trip on Every Stream Start
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/ai_chat.py:1192-1202
- **Issue**: Every POST /api/ai/chat/stream executes SELECT max_tokens FROM AiModel WHERE
  is_default AND capability=chat before session handling. Model context limit almost never changes.
- **Impact**: Extra 2-5ms latency and DB connection on every message. At 5000 concurrent users
  this doubles connection pool pressure at stream initiation.
- **Fix**: Cache _context_limit in module-level variable with asyncio.Lock, refreshed every 60s.

### QE-006: Session List Uses Offset Pagination - Archived Path Unindexed
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/chat_sessions.py:87-101
- **Issue**: GET /api/ai/sessions uses OFFSET + LIMIT. Partial index ix_chatsessions_user_updated
  has WHERE NOT is_archived. With include_archived=True Postgres cannot use this index.
  The count subquery adds another full scan.
- **Impact**: Slow for users with many archived sessions using include_archived=True and offset > 0.
  Current frontend hardcodes limit=100 with no offset so only affects direct API consumers.
- **Fix**: For default non-archived view the partial index is acceptable. For include_archived=True
  add cursor pagination via before_updated_at parameter.

### QE-007: message_count Denormalization Can Drift Under Concurrent Writes
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/chat_sessions.py:263
- **Issue**: persist_messages does session.message_count += N -- a read-modify-write without a
  row-level lock. Two concurrent persist calls both read the same value and both write original + N.
- **Impact**: Cosmetic drift in message_count display. Not used in queries.
- **Fix**: Use atomic SQL: UPDATE ChatSessions SET message_count = message_count + :n.

### QE-008: Auto-Summarize Is Fully Silent on Failure
- **Severity**: LOW
- **File**: electron-app/src/renderer/components/ai/use-ai-chat.ts:285-294
- **Issue**: Auto-summarize uses .catch(() => {}) with no logging or notification.
  Fails silently on 400 (wrong sequence from QE-002) or 503 (no model configured).
- **Impact**: User eventually hits hard model context limit and receives a raw LLM error.
- **Fix**: After fixing QE-002, surface a toast on failure and add console.warn.

### QE-009: Token Extraction Iterates All Graph State Messages Per Response
- **Severity**: LOW
- **File**: fastapi-backend/app/routers/ai_chat.py:713-718
- **Issue**: After each run the code iterates graph_state messages to sum usage_metadata.
  LangGraph accumulates all messages in thread state. For a 200-message session scans 200 entries.
- **Impact**: Negligible at current counts. Grows at 500+ messages per thread.
- **Fix**: Sum token counts from on_chat_model_end stream events incrementally during streaming.

### QE-010: No React Error Boundary Around AI Sidebar or Session List
- **Severity**: LOW
- **File**: electron-app/src/renderer/components/ai/ai-sidebar.tsx
- **Issue**: Neither AiSidebar nor ChatSessionList is wrapped in an Error Boundary. Runtime errors
  from malformed SSE data, corrupted sources JSON, or NaN dates propagate and blank the sidebar.
- **Impact**: In production, any unexpected data shape permanently crashes the sidebar until reload.
- **Fix**: Wrap AiSidebar and ChatSessionList in ErrorBoundary with a retry fallback button.

### QE-011: window.confirm Used for Delete Confirmation
- **Severity**: NIT
- **File**: electron-app/src/renderer/components/ai/chat-session-list.tsx:160
- **Issue**: window.confirm uses a native browser dialog that does not match the design system.
- **Fix**: Replace with Radix UI AlertDialog or Sonner toast with undo action.

### QE-012: Date Computations Recreated Per Session in getDateGroup
- **Severity**: NIT
- **File**: electron-app/src/renderer/components/ai/chat-session-list.tsx:29-38
- **Issue**: getDateGroup creates new Date(), today, yesterday, weekAgo for every session on every
  call. 400 Date constructions per useMemo recomputation with 100 sessions.
- **Fix**: Hoist date constants to the top of the grouped useMemo callback.

---

## Positive Observations

- Cursor pagination for messages is correct: WHERE sequence < before ORDER BY sequence DESC LIMIT
  n+1 with ix_chatmessages_session_seq composite index efficiently serves infinite scroll.
- Partial index design is sound: ix_chatsessions_user_updated on (user_id, updated_at DESC)
  WHERE NOT is_archived precisely matches the default session list query shape.
- Chat data excluded from IndexedDB: chat-sessions and chat-messages correctly listed in
  NON_PERSISTENT_KEYS, preventing stale history from IndexedDB hydration on startup.
- TokenUsageBar is properly selective: useAiSidebar selector for tokenUsage only re-renders
  when tokenUsage changes, not on every message append.
- IntersectionObserver cleanup: observer.disconnect() in effect cleanup prevents accumulation.
- SSE buffer guard: 1MB MAX_BUFFER_SIZE and lastIndexOf newline prevent unbounded buffer growth.
- Optimistic cache updates: Create/Update/Delete mutations update React Query cache without
  network re-fetches -- correct given staleTime: Infinity.
- Message array capped at 200: addMessage trims to 200 messages, bounding in-memory growth.
- Rate limiting: All session endpoints use check_chat_rate_limit.
