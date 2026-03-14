# Chat Sessions - Code Review Audit (Round 1)

## Summary
**NEEDS WORK** - Largely solid foundation with clean models, correct migration, well-structured React components using the custom external store pattern, and correct IndexedDB exclusion. However there are HIGH-severity correctness bugs causing real runtime failures that must be fixed before shipping.

---

## Findings

### CR-001: All endpoint path params use str instead of UUID
- **Severity**: HIGH
- **File**: fastapi-backend/app/routers/chat_sessions.py:55-66
- **Issue**: All path parameters are session_id: str. Passing a non-UUID string causes a DB-level DataError from asyncpg instead of a clean FastAPI 422. Inside _get_owned_session, ChatSession.id == session_id compares a UUID column to a Python string. All other routers (documents.py, projects.py, tasks.py) use UUID typed path params for proper validation.
- **Fix**: Change all path parameter types to UUID (import from uuid). FastAPI automatically validates and returns 422 on malformed UUIDs.

### CR-002: create_session count query missing select_from
- **Severity**: HIGH
- **File**: fastapi-backend/app/routers/chat_sessions.py:113-117
- **Issue**: select(func.count()).where(ChatSession.user_id == ...) has no .select_from(ChatSession). Without it SQLAlchemy may emit SELECT count(*) WHERE ... with no FROM clause, causing a DB error. Compare list_sessions (line 90) which correctly uses select(func.count()).select_from(query.subquery()).
- **Fix**: select(func.count()).select_from(ChatSession).where(ChatSession.user_id == current_user.id, ChatSession.is_archived.is_(False))

### CR-003: persist_messages has a race condition on sequence numbers
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/chat_sessions.py:244-258
- **Issue**: Max sequence is fetched with a plain SELECT then messages are inserted separately. Two concurrent persist_messages calls read the same max_seq and produce duplicate sequence numbers, corrupting cursor-based pagination. No UNIQUE constraint on (session_id, sequence) exists at the DB level.
- **Fix**: Lock the session row with SELECT ... FOR UPDATE before reading max_seq. Add UniqueConstraint on (session_id, sequence) to both the migration and ChatMessage model.

### CR-004: Inline LLM calls duplicated between summarize_session and generate_session_title
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/chat_sessions.py:342-363 and fastapi-backend/app/worker.py:1641-1655
- **Issue**: Both contain near-identical boilerplate: instantiate ProviderRegistry, load_from_db, get_chat_model, ainvoke with SystemMessage + HumanMessage. DRY violation; any provider change requires updates in two places.
- **Fix**: Extract a shared async helper such as app/ai/chat_helpers.py::invoke_chat_llm(db, messages) -> str. Both callers import and use it.

### CR-005: ChatSessionSummary uses str for timestamps instead of datetime
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/schemas/ai_chat.py:180-193
- **Issue**: created_at: str and updated_at: str require manual .isoformat() calls in _session_to_summary and bypass Pydantic timezone-aware serialization. Every other schema in the codebase uses datetime for timestamps.
- **Fix**: Change to datetime fields, add model_config = ConfigDict(from_attributes=True) for ORM mode, remove manual isoformat calls. The _session_to_summary helper can then be replaced by ChatSessionSummary.model_validate(session).

### CR-006: Frontend ChatSessionSummary type is camelCase but API returns snake_case
- **Severity**: HIGH
- **File**: electron-app/src/renderer/components/ai/types.ts:210-221
- **Issue**: TypeScript defines createdAt, updatedAt, messageCount, lastMessagePreview, applicationId, threadId, totalInputTokens, totalOutputTokens. The API returns snake_case equivalents. There is no transformation in use-chat-sessions.ts. At runtime session.updatedAt is always undefined, breaking date grouping in chat-session-list.tsx:134 and the search filter at line 196 (accesses session.lastMessagePreview). This is a confirmed runtime bug.
- **Fix**: Add a toSessionSummary(raw) mapper in use-chat-sessions.ts that converts API snake_case to the camelCase TS interface, called inside the queryFn before returning. Alternatively switch the TS interface to snake_case to match the API directly.

### CR-007: useChatSessions queryFn does not check API response status
- **Severity**: MEDIUM
- **File**: electron-app/src/renderer/hooks/use-chat-sessions.ts:54-61
- **Issue**: authGet returns ApiResponse with a status field. useChatSessions ignores the status and silently returns undefined data on 4xx/5xx. By contrast useChatMessages (line 76) throws on non-200 status. Inconsistent error handling within the same file.
- **Fix**: Throw inside the queryFn when response.status >= 400, matching the pattern in useChatMessages.

### CR-008: Auto-session creation in chat_stream bypasses the 100-session cap
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/routers/ai_chat.py:1219-1230
- **Issue**: chat_stream auto-creates a ChatSession inline without enforcing the 100-active-session cap that create_session in chat_sessions.py enforces. Users relying on the auto-create path can accumulate unlimited sessions.
- **Fix**: Extract session creation into app/services/session_service.py::get_or_create_session(db, user_id, session_id, thread_id) that enforces the cap. Both chat_stream and create_session call this shared function.

### CR-009: Auto-summarize fires during active stream with incorrect sequence number
- **Severity**: MEDIUM
- **File**: electron-app/src/renderer/components/ai/use-ai-chat.ts:279-295
- **Issue**: The token_usage SSE event handler fires authPost summarize fire-and-forget using sidebarState.messages.length as up_to_sequence. DB sequences are 1-based and independent of the in-memory array length, especially after loading an old session. This may summarize the wrong range and races with the onRunFinished persistence call.
- **Fix**: Track the last persisted message sequence in sidebar state. Move the summarization trigger to post-stream inside onRunFinished callback to avoid the race.

### CR-010: ChatMessage.sources ORM type is dict | None but actual stored structure is a list
- **Severity**: MEDIUM
- **File**: fastapi-backend/app/models/chat_message.py:28
- **Issue**: Mapped[dict | None] is wrong: sources stores a JSON array of SourceCitation objects. The schema correctly declares dict | list | None. The ORM annotation causes mypy/pyright type errors.
- **Fix**: Change to sources: Mapped[list | dict | None] or Mapped[Any] with a comment explaining the polymorphic JSONB structure.

### CR-011: staleTime: Infinity means generate_session_title ARQ job updates are never seen
- **Severity**: LOW
- **File**: electron-app/src/renderer/hooks/use-chat-sessions.ts:58
- **Issue**: The generate_session_title ARQ worker updates session title in DB asynchronously, but with staleTime: Infinity the session list never refetches. Users see the placeholder New Chat title permanently.
- **Fix**: Emit a WebSocket event (SESSION_TITLE_UPDATED) from the worker job and invalidate queryKeys.chatSessions in use-websocket-cache.ts, matching the existing WS-driven cache invalidation pattern.

### CR-012: window.confirm used for delete confirmation, inconsistent with app pattern
- **Severity**: LOW
- **File**: electron-app/src/renderer/components/ai/chat-session-list.tsx:160
- **Issue**: window.confirm is a blocking native dialog inconsistent with the rest of the app which uses Radix UI AlertDialog for confirmations (see document-editor.tsx).
- **Fix**: Replace with a Radix AlertDialog.

### CR-013: ContextSummaryDivider missing aria-expanded on toggle button
- **Severity**: LOW
- **File**: electron-app/src/renderer/components/ai/context-summary-divider.tsx:22
- **Issue**: The expand/collapse button has no aria-expanded attribute. Screen readers cannot announce state. Project constitution requires WCAG 2.1 AA.
- **Fix**: Add aria-expanded={expanded} to the button element.

### CR-014: ChatSessionSummary missing context_summary field
- **Severity**: LOW
- **File**: fastapi-backend/app/schemas/ai_chat.py:180-193
- **Issue**: The session list response does not include context_summary or summary_up_to_msg_seq. When the user reopens a previously summarized session the frontend cannot show the ContextSummaryDivider at session open.
- **Fix**: Add context_summary: str | None = None and summary_up_to_msg_seq: int | None = None to ChatSessionSummary.

### CR-015: main.py router import line exceeds ruff line length
- **Severity**: NIT
- **File**: fastapi-backend/app/main.py:31
- **Issue**: The from .routers import ... line is approximately 300 characters, failing ruff check with E501.
- **Fix**: Split across multiple lines with parentheses.

### CR-016: Stray blank line in models/__init__.py
- **Severity**: NIT
- **File**: fastapi-backend/app/models/__init__.py:23
- **Issue**: Extra blank line between Mention and Notification imports breaks the alphabetical block and may be flagged by ruff.
- **Fix**: Remove the extra blank line.
