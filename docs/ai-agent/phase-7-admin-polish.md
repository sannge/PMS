# Phase 7: Admin Dashboard + Observability + Polish

**Goal**: Admin UI for AI configuration, monitoring, rate limiting, WebSocket events for AI status updates.

**Depends on**: Phase 5 (frontend patterns), Phase 4 (agent backend)
**Final phase**: No downstream dependencies

---

## Task 7.1: AI Settings Panel

### New File: `electron-app/src/renderer/components/ai/ai-settings-panel.tsx`

Accessible to Application Owners from the application settings area.

```tsx
/**
 * AI Settings Panel — Admin UI for configuring AI providers, models, and indexing.
 *
 * Access: Application Owners only (check role before rendering)
 *
 * Layout — Tabs:
 *
 * ┌─────────────────────────────────────────────────────┐
 * │ AI Settings                                        │
 * ├──────────┬──────────┬──────────┬──────────────────┤
 * │ Providers│  Models  │ Indexing │ System Prompt     │
 * ├──────────┴──────────┴──────────┴──────────────────┤
 * │                                                    │
 * │  (Tab content here)                                │
 * │                                                    │
 * └────────────────────────────────────────────────────┘
 */
```

### Tab 1: Providers

```
┌─────────────────────────────────────────────────────┐
│ LLM Providers                        [+ Add Provider]│
├─────────────────────────────────────────────────────┤
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ OpenAI                              🟢 Connected │ │
│ │ Scope: Global                                    │ │
│ │ API Key: ••••••••••sk-1234                       │ │
│ │ [Test] [Edit] [Delete]                           │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ Anthropic                           🔴 No key   │ │
│ │ Scope: Global                                    │ │
│ │ API Key: Not configured                          │ │
│ │ [Test] [Edit] [Delete]                           │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ Ollama (Local)                      🟡 Checking  │ │
│ │ Scope: Application (Engineering)                 │ │
│ │ URL: http://localhost:11434                      │ │
│ │ [Test] [Edit] [Delete]                           │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

- Status indicators: 🟢 Connected, 🔴 Error/No key, 🟡 Checking
- "Test" button calls `POST /api/ai/config/providers/{id}/test`
- "Add Provider" opens form dialog (name, type, URL, API key, scope)
- "Edit" opens same form pre-filled
- "Delete" shows confirmation dialog (cascade warning for models)

### Tab 2: Models

```
┌─────────────────────────────────────────────────────────┐
│ Configured Models                          [+ Add Model]│
├────────────┬───────────┬────────────┬──────────┬───────┤
│ Model      │ Provider  │ Capability │ Default  │       │
├────────────┼───────────┼────────────┼──────────┼───────┤
│ GPT-4o     │ OpenAI    │ Chat       │ ✅ Yes   │ [Edit]│
│ GPT-4o     │ OpenAI    │ Vision     │ ✅ Yes   │ [Edit]│
│ text-embed │ OpenAI    │ Embedding  │ ✅ Yes   │ [Edit]│
│ Claude 4   │ Anthropic │ Chat       │ ❌ No    │ [Edit]│
│ llama3     │ Ollama    │ Chat       │ ❌ No    │ [Edit]│
└────────────┴───────────┴────────────┴──────────┴───────┘
```

- "Default" checkbox: Only one default per capability
- Click default toggles (with confirmation if changing)
- "Add Model" form: provider (dropdown), model_id, capability, dimensions (if embedding)

### Tab 3: Indexing

```
┌─────────────────────────────────────────────────────────┐
│ Document Indexing Status                                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Nightly Job: Last run 2026-02-20 02:00 AM (✅ Success)  │
│ Next run: 2026-02-21 02:00 AM                           │
│                                                         │
│ Summary: 150 documents, 142 indexed, 8 stale            │
│                                                         │
│ [Reindex All Stale Documents]                           │
│                                                         │
│ ┌───────────┬──────────────────┬──────────────┬───────┐ │
│ │ Document  │ Embedding Updated│ Graph Updated│ Stale │ │
│ ├───────────┼──────────────────┼──────────────┼───────┤ │
│ │ API Spec  │ 2h ago           │ 6h ago       │  ❌   │ │
│ │ Sprint 12 │ 1d ago           │ 1d ago       │  ✅   │ │
│ │ Design v2 │ Never            │ Never        │  ✅   │ │
│ └───────────┴──────────────────┴──────────────┴───────┤ │
│                                                         │
│ Per-document: Click row → [Reindex Now] button          │
└─────────────────────────────────────────────────────────┘
```

- Data from `GET /api/ai/index-status/application/{app_id}`
- "Reindex All Stale" calls `POST /api/ai/reindex/application/{app_id}`
- Individual reindex calls `POST /api/ai/reindex/{document_id}`
- Progress updates via WebSocket events

### Tab 4: Blair's Personality

```
┌─────────────────────────────────────────────────────────┐
│ Blair's Personality                                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Custom system prompt (optional):                        │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ You are Blair, a helpful AI assistant for our       │ │
│ │ engineering team. Focus on technical accuracy and   │ │
│ │ provide code examples when relevant.                │ │
│ │                                                     │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ This overrides Blair's default personality.              │
│ Leave empty to use the default friendly assistant.       │
│ Note: Blair's name is always "Blair" regardless of      │
│ custom prompt.                                          │
│                                                         │
│ [Reset to Default]  [Save]                              │
└─────────────────────────────────────────────────────────┘
```

- Textarea for custom system prompt
- Saved as application-level setting (new column or JSON config)
- "Reset to Default" clears custom prompt, reverts to Blair's default personality
- Preview of current effective prompt (custom or default)
- Blair's name always stays "Blair" even with custom prompt (prepended if not present)

### Acceptance Criteria
- [ ] All four tabs render correctly
- [ ] Provider CRUD with test connectivity
- [ ] Model CRUD with default management
- [ ] Indexing status table loads correctly
- [ ] Reindex buttons trigger backend operations
- [ ] System prompt customization saves and applies
- [ ] Only Application Owners can access panel
- [ ] Responsive layout

---

## Task 7.2: Document Index Status Indicator

### Modify: Document header/metadata area in the editor

Add a small index status badge to the document editor header:

```tsx
/**
 * Shows in the document editor header area, near title or metadata.
 *
 * States:
 * - "Indexed 2h ago" (green) — embedding_updated_at is recent
 * - "Indexing..." (yellow, animated) — embedding job in progress
 * - "Not indexed" (gray) — embedding_updated_at is null
 * - "Stale" (orange) — document updated after last embedding
 *
 * Clickable: Opens small popover with:
 * - Embedding updated: timestamp
 * - Graph updated: timestamp
 * - Chunk count: N
 * - [Reindex Now] button
 *
 * Data source: DocumentResponse.embedding_updated_at, graph_ingested_at
 */
```

### Acceptance Criteria
- [ ] Badge visible in document editor header
- [ ] Correct state displayed based on timestamps
- [ ] Clickable popover with details
- [ ] "Reindex Now" triggers `POST /api/ai/reindex/{document_id}`
- [ ] Updates when WebSocket EMBEDDING_UPDATED event received
- [ ] Non-intrusive (small badge, doesn't disrupt editor UX)

---

## Task 7.3: WebSocket Events for AI

### Modify: `fastapi-backend/app/websocket/handlers.py`

Add new event types:

| Event | Trigger | Broadcast To | Payload |
|-------|---------|-------------|---------|
| `EMBEDDING_UPDATED` | Document embedding completed | Document room subscribers | `{document_id, chunk_count, timestamp}` |
| `ENTITIES_EXTRACTED` | Document entity extraction completed | Document room subscribers | `{document_id, entities_count, relationships_count, timestamp}` |
| `IMPORT_COMPLETED` | Document import finished | User DM (specific user) | `{job_id, document_id, title, scope}` |
| `IMPORT_FAILED` | Document import failed | User DM (specific user) | `{job_id, error_message, file_name}` |
| `REINDEX_PROGRESS` | Batch reindex progress | Application room | `{application_id, total, processed, failed}` |

### Broadcasting Patterns

Use existing `broadcast_to_target_users()` for user-specific events (IMPORT_*).
Use existing document room broadcasting for document-specific events (EMBEDDING_*, ENTITIES_*).
Use application room for application-wide events (REINDEX_*).

### Frontend Integration

**Modify**: `electron-app/src/renderer/hooks/use-websocket-cache.ts`

Add handlers for new event types:

```typescript
case "EMBEDDING_UPDATED":
  // Invalidate document index status query
  queryClient.invalidateQueries({
    queryKey: queryKeys.documentIndexStatus(payload.document_id)
  })
  break

case "ENTITIES_EXTRACTED":
  // Invalidate document index status + entity list
  queryClient.invalidateQueries({
    queryKey: queryKeys.documentIndexStatus(payload.document_id)
  })
  break

case "IMPORT_COMPLETED":
  // Invalidate import jobs list + show toast notification
  queryClient.invalidateQueries({ queryKey: queryKeys.importJobs })
  // Toast: "Import complete: {title}"
  break

case "IMPORT_FAILED":
  // Invalidate import jobs list + show error toast
  queryClient.invalidateQueries({ queryKey: queryKeys.importJobs })
  // Toast: "Import failed: {file_name} - {error}"
  break

case "REINDEX_PROGRESS":
  // Update application index status
  queryClient.invalidateQueries({
    queryKey: queryKeys.applicationIndexStatus(payload.application_id)
  })
  break
```

### Acceptance Criteria
- [ ] All 5 event types broadcast correctly (EMBEDDING_UPDATED, ENTITIES_EXTRACTED, IMPORT_COMPLETED, IMPORT_FAILED, REINDEX_PROGRESS)
- [ ] Events reach correct subscribers (document room, user DM, app room)
- [ ] Frontend handles all event types
- [ ] Cache invalidation triggers correct query refetches
- [ ] Toast notifications for import completion/failure
- [ ] Document index badge updates in real-time

---

## Task 7.4: Rate Limiting

### New File: `fastapi-backend/app/ai/rate_limiter.py`

```python
class AIRateLimiter:
    """
    Redis-based rate limiting for AI endpoints.
    Uses existing Redis rate limiting patterns from redis_service.py.

    Uses sliding window counter pattern:
    Key format: ratelimit:{endpoint}:{scope_id}:{window}
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        endpoint: str,
        scope_id: str,
        limit: int,
        window_seconds: int
    ) -> RateLimitResult:
        """
        Check if request is within rate limits.

        Returns:
        RateLimitResult(
            allowed: bool,
            remaining: int,
            reset_at: datetime,
            limit: int
        )
        """

    async def increment(
        self,
        endpoint: str,
        scope_id: str,
        window_seconds: int
    ) -> int:
        """Increment counter. Returns current count."""
```

### Rate Limits

| Endpoint | Limit | Window | Scope | Header |
|----------|-------|--------|-------|--------|
| AI Chat | 30 requests | 1 minute | Per user | X-RateLimit-AI-Chat |
| Embedding jobs | 100 documents | 1 minute | Per application | X-RateLimit-AI-Embed |
| Document import | 10 files | 1 hour | Per user | X-RateLimit-AI-Import |
| Manual reindex | 20 requests | 1 hour | Per user | X-RateLimit-AI-Reindex |

### Integration with Routers

Add rate limiting middleware/dependency to each AI endpoint:

```python
async def check_chat_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter)
):
    result = await rate_limiter.check_rate_limit(
        endpoint="ai_chat",
        scope_id=str(current_user.id),
        limit=30,
        window_seconds=60
    )
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_at.timestamp()))
            }
        )
```

### Acceptance Criteria
- [ ] Rate limits enforced per endpoint
- [ ] Sliding window counter (not fixed window)
- [ ] Rate limit headers in response
- [ ] 429 response with clear error message
- [ ] Rate limit info available for frontend display
- [ ] Reuses existing Redis patterns
- [ ] Limits configurable (not hardcoded)

---

## Task 7.5: Telemetry & Logging

### New File: `fastapi-backend/app/ai/telemetry.py`

```python
class AITelemetry:
    """
    Structured logging for all AI operations.
    Uses Python's logging module with structured JSON output.

    All log entries include:
    - timestamp
    - operation (chat, embedding, graph_ingest, import, etc.)
    - user_id (for audit)
    - duration_ms
    - success: bool
    """

    @staticmethod
    async def log_chat_request(
        user_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        tool_calls: int,
        duration_ms: int,
        cost_estimate: float | None = None
    ) -> None:
        """Log a chat completion request."""

    @staticmethod
    async def log_embedding_batch(
        document_count: int,
        chunk_count: int,
        total_tokens: int,
        provider: str,
        model: str,
        duration_ms: int,
        cost_estimate: float | None = None
    ) -> None:
        """Log an embedding batch operation."""

    @staticmethod
    async def log_graph_ingest(
        document_count: int,
        entities_extracted: int,
        relations_created: int,
        duration_ms: int
    ) -> None:
        """Log a graph ingestion operation."""

    @staticmethod
    async def log_tool_call(
        tool_name: str,
        user_id: UUID,
        duration_ms: int,
        success: bool,
        error: str | None = None
    ) -> None:
        """Log an agent tool call."""

    @staticmethod
    async def log_import(
        user_id: UUID,
        file_type: str,
        file_size: int,
        duration_ms: int,
        success: bool,
        error: str | None = None
    ) -> None:
        """Log a document import operation."""

    @staticmethod
    def estimate_cost(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Estimate cost based on known pricing.
        Rough estimates — not for billing, just for monitoring.

        Known rates (per 1M tokens):
        - GPT-4o: $2.50 input, $10.00 output
        - GPT-4o-mini: $0.15 input, $0.60 output
        - Claude Sonnet: $3.00 input, $15.00 output
        - text-embedding-3-small: $0.02 input
        - Ollama: $0.00 (local)
        """
```

### Integration Points

Add telemetry calls to:
- `ai_chat.py` router (after each chat request)
- `embedding_service.py` (after each embedding batch)
- `entity_extraction_service.py` (after each extraction)
- Agent tool execution (each tool call)
- Import worker (after each import)

### Acceptance Criteria
- [ ] All AI operations logged with structured data
- [ ] Token counts tracked per request
- [ ] Cost estimates calculated (rough, for monitoring)
- [ ] Duration tracked for all operations
- [ ] User ID included for audit trail
- [ ] Logs parseable as JSON for log aggregation tools
- [ ] No PII logged (no message content, no API keys)

---

## Task 7.6: Health Check Extension

### Modify: `fastapi-backend/app/main.py`

Extend the existing `/health` endpoint with AI service status:

```python
@app.get("/health")
async def health():
    # ... existing health checks ...

    # AI Services
    ai_health = {
        "knowledge_graph": {
            "entity_count": int,         # Total entities in DocumentEntities
            "relationship_count": int,   # Total relationships
        },
        "embedding_provider": {
            "name": str | None,      # e.g., "openai"
            "model": str | None,     # e.g., "text-embedding-3-small"
            "connected": bool
        },
        "chat_provider": {
            "name": str | None,
            "model": str | None,
            "connected": bool
        },
        "document_chunks_count": int,   # Total chunks in DB
        "pending_embedding_jobs": int,  # ARQ queue depth
    }

    return {
        **existing_health,
        "ai": ai_health
    }
```

### Acceptance Criteria
- [ ] Health endpoint includes AI service status
- [ ] Knowledge graph counts reported (entities, relationships)
- [ ] Provider connectivity status shown
- [ ] Chunk count for system overview
- [ ] Health endpoint doesn't slow down (timeouts on checks)
- [ ] Degraded state reported (not crash) when AI services are down

---

## Task 7.7: AI Hooks & React Query

### New File: `electron-app/src/renderer/hooks/use-ai-config.ts`

```typescript
/**
 * React Query hooks for AI configuration management.
 * Used by the AI Settings Panel (Task 7.1).
 */

// --- Providers ---

export function useAiProviders() {
  /**
   * Query: GET /api/ai/config/providers
   * Returns list of all configured providers.
   * Stale time: 30s (follows global pattern)
   */
}

export function useCreateAiProvider() {
  /**
   * Mutation: POST /api/ai/config/providers
   * Invalidates: aiProviders query
   * Optimistic update: Add provider to list immediately
   */
}

export function useUpdateAiProvider() {
  /**
   * Mutation: PUT /api/ai/config/providers/{id}
   * Invalidates: aiProviders query
   */
}

export function useDeleteAiProvider() {
  /**
   * Mutation: DELETE /api/ai/config/providers/{id}
   * Invalidates: aiProviders query
   * Confirmation: Should be handled by caller (cascade warning)
   */
}

export function useTestAiProvider() {
  /**
   * Mutation: POST /api/ai/config/providers/{id}/test
   * No cache invalidation needed
   * Returns: { success: bool, message: string }
   */
}

// --- Models ---

export function useAiModels() {
  /**
   * Query: GET /api/ai/config/models
   * Returns list of all configured models.
   */
}

export function useCreateAiModel() {
  /**
   * Mutation: POST /api/ai/config/models
   * Invalidates: aiModels query
   */
}

export function useUpdateAiModel() {
  /**
   * Mutation: PUT /api/ai/config/models/{id}
   * Invalidates: aiModels query
   */
}

export function useDeleteAiModel() {
  /**
   * Mutation: DELETE /api/ai/config/models/{id}
   * Invalidates: aiModels query
   */
}

// --- Indexing ---

export function useDocumentIndexStatus(documentId: string) {
  /**
   * Query: GET /api/ai/index-status/{documentId}
   * Stale time: 60s (updated via WebSocket EMBEDDING_UPDATED events)
   * refetchOnWindowFocus: false (WebSocket keeps it fresh)
   */
}

export function useApplicationIndexStatus(applicationId: string) {
  /**
   * Query: GET /api/ai/index-status/application/{applicationId}
   * Used by indexing tab in settings panel.
   */
}

export function useReindexDocument() {
  /**
   * Mutation: POST /api/ai/reindex/{documentId}
   * Invalidates: documentIndexStatus query for that doc
   */
}

export function useReindexApplication() {
  /**
   * Mutation: POST /api/ai/reindex/application/{applicationId}
   * Invalidates: applicationIndexStatus query
   */
}

export function useIndexProgress() {
  /**
   * Query: GET /api/ai/index-progress
   * Polls every 5s while status is "running"
   * refetchInterval: (data) => data?.status === "running" ? 5000 : false
   */
}

// --- Import (from Phase 6, but hooks defined here for organization) ---

export function useImportJobs() {
  /**
   * Query: GET /api/ai/import/jobs
   * Lists user's recent import jobs.
   */
}

// --- Config Summary ---

export function useAiConfigSummary() {
  /**
   * Query: GET /api/ai/config/summary
   * Returns full config with defaults.
   */
}
```

### Acceptance Criteria
- [ ] All queries follow existing React Query patterns
- [ ] Mutations invalidate correct cache keys
- [ ] Polling configured for progress-tracking queries
- [ ] WebSocket-synced queries have `refetchOnWindowFocus: false`
- [ ] Error states handled (toast notifications)
- [ ] TypeScript types for all query responses
- [ ] Hooks are composable (used by settings panel components)

---

## Verification Checklist — Full E2E

```
1. Configure AI Provider:
   → Open application settings → AI Settings tab
   → Add OpenAI provider with API key
   → Click "Test" → Shows "Connected"
   → Add GPT-4o model for chat + vision
   → Add text-embedding-3-small model for embedding
   → Set both as defaults

2. Create a Document:
   → Create a document with text content + embedded images
   → Wait ~30s
   → Document header shows "Indexed X seconds ago"
   → Click badge → popover shows chunk count

3. Trigger Entity Extraction:
   → In AI Settings → Indexing tab
   → Click "Reindex Now" on the document
   → graph_ingested_at populates, entities appear
   → WebSocket event updates UI

4. Chat with Blair:
   → Open Blair sidebar (click Sparkles icon or Ctrl+Shift+A)
   → Type: "What did the document I just created say?"
   → Streaming response with document citations
   → Source reference links at bottom of Blair's response
   → Click a source link → navigates to document, scrolls to section, highlights cited text

5. Project Queries:
   → Type: "What tasks are overdue?"
   → Shows overdue tasks from accessible projects
   → Task keys clickable → navigates to task

6. Write Actions (Human-in-the-Loop):
   → Type: "Create a task to review this document"
   → Inline confirmation card appears IN the chat stream (not a modal)
   → Card shows: action type, title, project, priority
   → Click "Approve" → task created, Blair confirms in chat
   → Card updates to show "Approved ✅" with buttons disabled

7. Import Document:
   → Click import button → Import dialog opens
   → Drop a PDF file
   → Select scope and folder
   → Watch progress: 10% → 40% → 60% → 80% → 100%
   → Document appears in knowledge tree
   → Content is clean markdown from PDF

8. Blair on Imported Document:
   → Type: "Summarize the PDF I just imported"
   → Accurate summary returned with source references
   → Click source link → navigates to imported document with highlight

9. Rate Limiting:
   → Send 31 messages in 1 minute
   → 31st message: 429 error with retry-after info

10. Context Awareness:
    → Navigate to project board
    → Ask: "What's the status of this project?"
    → Blair uses context injection (knows which project)
    → Navigate to a canvas document
    → Ask: "What's on this canvas?"
    → Blair summarizes canvas elements

11. Source Reference Navigation:
    → Ask Blair about a topic covered in multiple documents
    → Blair responds with source references from different retrieval methods
    → Each source shows: document title, section heading, relevance score, source type (semantic/keyword/fuzzy/graph)
    → Click source from regular document → opens document, scrolls to heading, highlights text
    → Click source from canvas → opens canvas, pans to element, highlights it
    → Click entity source → opens document mentioning that entity

11. Health Check:
    → GET /health
    → AI section shows provider status, chunk count, entity count

12. Settings Admin:
    → Non-owner tries to access AI settings → hidden/403
    → Owner can CRUD providers and models
    → Indexing tab shows all documents with status
```
