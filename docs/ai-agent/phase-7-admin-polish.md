# Phase 7: Admin Dashboard + Observability + Polish

**Goal**: Admin UI for AI configuration, monitoring, rate limiting, WebSocket events for AI status updates.

**Depends on**: Phase 5 (frontend patterns), Phase 4 (agent backend)
**Final phase**: No downstream dependencies

---

## Task 7.0: Database Migration — `is_developer` Column

### Modify: `fastapi-backend/app/models/user.py`

Add `is_developer` boolean column:

```python
is_developer = Column(
    Boolean,
    nullable=False,
    default=False,
    server_default="false",
)
```

### New Migration: `alembic/versions/YYYYMMDD_add_user_is_developer.py`

```sql
ALTER TABLE "Users" ADD COLUMN is_developer BOOLEAN NOT NULL DEFAULT false;
```

No UI for managing this — set manually via database for trusted developers.

### Modify: `fastapi-backend/app/routers/ai_config.py`

Replace `require_ai_admin()` with `require_developer()`:

```python
async def require_developer(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the current user to be a developer."""
    if not current_user.is_developer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer access required for AI configuration",
        )
    return current_user
```

Apply `require_developer` to all global admin endpoints (provider CRUD, model CRUD, system prompt).
User override endpoints (`/me/*`) remain accessible to any authenticated user via `get_current_user`.

### Modify: `fastapi-backend/app/schemas/ai_config.py`

Add `provider_type` column to `AiModels` table for seed data filtering:

```python
class AiModelCreate(BaseModel):
    # ... existing fields ...
    provider_type: str  # NEW: "openai", "anthropic", "ollama"
```

### New: Model Seed Data

All known models pre-populated in `AiModels` table. New models added manually via DB INSERT.
Frontend dropdowns read from this table, filtered by `provider_type` and `capability`.

**OpenAI Chat Models:**
| model_id | display_name | capability | provider_type |
|----------|-------------|------------|---------------|
| `gpt-5.2` | GPT-5.2 | chat | openai |
| `gpt-5.1` | GPT-5.1 | chat | openai |
| `gpt-5` | GPT-5 | chat | openai |
| `gpt-5-mini` | GPT-5 Mini | chat | openai |
| `gpt-5-nano` | GPT-5 Nano | chat | openai |
| `gpt-4.1` | GPT-4.1 | chat | openai |
| `gpt-4.1-mini` | GPT-4.1 Mini | chat | openai |

**Anthropic Chat Models:**
| model_id | display_name | capability | provider_type |
|----------|-------------|------------|---------------|
| `claude-opus-4-6` | Claude Opus 4.6 | chat | anthropic |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | chat | anthropic |
| `claude-opus-4-5` | Claude Opus 4.5 | chat | anthropic |
| `claude-sonnet-4-5` | Claude Sonnet 4.5 | chat | anthropic |
| `claude-haiku-4-5` | Claude Haiku 4.5 | chat | anthropic |

**Ollama Chat Models:**
| model_id | display_name | capability | provider_type |
|----------|-------------|------------|---------------|
| `llama3.1` | Llama 3.1 | chat | ollama |
| `llama3.2` | Llama 3.2 | chat | ollama |
| `mistral` | Mistral | chat | ollama |
| `qwen3` | Qwen 3 | chat | ollama |

**Embedding Models (OpenAI + Ollama only — Anthropic has no embedding API):**
| model_id | display_name | capability | provider_type | embedding_dimensions |
|----------|-------------|------------|---------------|---------------------|
| `text-embedding-3-small` | Embedding 3 Small | embedding | openai | 1536 |
| `text-embedding-3-large` | Embedding 3 Large | embedding | openai | 3072 |
| `nomic-embed-text` | Nomic Embed Text | embedding | ollama | 768 |
| `mxbai-embed-large` | MxBai Embed Large | embedding | ollama | 1024 |
| `all-minilm` | All-MiniLM | embedding | ollama | 384 |
| `snowflake-arctic-embed` | Snowflake Arctic | embedding | ollama | 1024 |

**Vision Models:**
| model_id | display_name | capability | provider_type |
|----------|-------------|------------|---------------|
| `gpt-5.2` | GPT-5.2 Vision | vision | openai |
| `gpt-5.1` | GPT-5.1 Vision | vision | openai |
| `gpt-5` | GPT-5 Vision | vision | openai |
| `gpt-4.1` | GPT-4.1 Vision | vision | openai |
| `claude-opus-4-6` | Claude Opus 4.6 Vision | vision | anthropic |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 Vision | vision | anthropic |
| `claude-sonnet-4-5` | Claude Sonnet 4.5 Vision | vision | anthropic |
| `llava` | LLaVA 1.6 | vision | ollama |
| `llava-llama3` | LLaVA-Llama3 | vision | ollama |
| `qwen2.5-vl` | Qwen 2.5 VL | vision | ollama |

> **Adding new models**: When new models are released (e.g., GPT-5.3, Claude Opus 4.7),
> INSERT a new row into `AiModels` with the correct `provider_type` and `capability`.
> The row appears in frontend dropdowns automatically. No code change required.

### Acceptance Criteria
- [ ] `is_developer` column added to Users table via Alembic migration
- [ ] `require_developer()` replaces `require_ai_admin()` on all global admin endpoints
- [ ] User override endpoints still use `get_current_user` (any authenticated user)
- [ ] `provider_type` column added to `AiModels` table
- [ ] All seed models inserted via migration or seed script
- [ ] Model dropdowns populate from DB, filtered by `provider_type` + `capability`

---

## Task 7.1: Developer AI Settings Panel

### New File: `electron-app/src/renderer/components/ai/ai-settings-panel.tsx`

Accessible to **Developers only** (`is_developer=true`). Three separate sections — one per capability — each with its own provider, API key, and model.

```tsx
/**
 * Developer AI Settings Panel — Configure AI providers per capability.
 *
 * Access: Developers only (is_developer=true, check before rendering)
 *
 * Layout — 3 independent sections (Chat, Embedding, Vision):
 *
 * ┌──────────────────────────────────────────────────────────┐
 * │ AI Configuration (Developer Only)                        │
 * ├──────────────────────────────────────────────────────────┤
 * │                                                          │
 * │ ━━ CHAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
 * │ Provider:  [Anthropic        ▼]                          │
 * │ API Key:   [sk-ant-•••••••••••••]                        │
 * │ Model:     [claude-sonnet-4-6   ▼]                       │
 * │            [Test Chat] 🟢 "Hello! I'm Blair" (201ms)    │
 * │                                                          │
 * │ ━━ EMBEDDING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
 * │ Provider:  [OpenAI           ▼]                          │
 * │ API Key:   [sk-•••••••••••••••]                          │
 * │ Model:     [text-embedding-3-small ▼]                    │
 * │            [Test Embedding] 🟢 1536 dims (89ms)         │
 * │                                                          │
 * │ ━━ VISION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
 * │ Provider:  [OpenAI           ▼]                          │
 * │ API Key:   [sk-•••••••••••••••]                          │
 * │ Model:     [gpt-5.2             ▼]                       │
 * │            [Test Vision] 🟢 "White image" (412ms)       │
 * │                                                          │
 * └──────────────────────────────────────────────────────────┘
 *
 * Additional tabs: Indexing, Blair's Personality (unchanged)
 */
```

### Section: Chat Configuration

- **Provider dropdown**: OpenAI, Anthropic, Ollama (all 3 supported)
- **API Key**: Password input, masked display (`••••••sk-1234`). Required for OpenAI/Anthropic, optional for Ollama.
- **Model dropdown**: Populated from `AiModels` table filtered by `provider_type` + `capability='chat'`
- **Base URL**: Text input, visible only when Ollama selected (default: `http://localhost:11434`)
- **[Test Chat]**: Sends `"Say hello in 5 words"` to the selected provider+model, displays response text + latency
- Status indicators: 🟢 Connected (shows response), 🔴 Error (shows error message), 🟡 Testing (spinner)
- **This is the global default** — affects all users who don't set their own override

### Section: Embedding Configuration

- **Provider dropdown**: OpenAI, Ollama only (Anthropic has no embedding API — grayed out / not shown)
- **API Key**: Same pattern as chat
- **Model dropdown**: Filtered by `provider_type` + `capability='embedding'`
- **[Test Embedding]**: Embeds the word `"test"`, displays dimension count + latency
- **Warning banner**: "Changing the embedding model requires re-embedding all documents. This can take significant time and API cost depending on corpus size."

### Section: Vision Configuration

- **Provider dropdown**: OpenAI, Anthropic, Ollama (all 3 supported)
- **API Key**: Same pattern
- **Model dropdown**: Filtered by `provider_type` + `capability='vision'`
- **[Test Vision]**: Sends a 1x1 white PNG pixel, displays model's description + latency

### General UX Notes

- Each section saves independently (`[Save]` button per section)
- Changing provider clears the API key and model fields
- Model dropdown is disabled until provider is selected
- If the same provider+key is used across sections (e.g., OpenAI for chat + vision), the key is stored once and shared
- **Backend endpoint**: `PUT /api/ai/config/capability/{capability}` — saves provider + key + model for one capability

### Acceptance Criteria
- [ ] Three separate sections render (Chat, Embedding, Vision)
- [ ] Provider dropdown filters model options correctly per capability
- [ ] Embedding section excludes Anthropic from provider dropdown
- [ ] API key input masked, never shown in full
- [ ] Each section has independent Test button with result display
- [ ] Test Chat shows response text + latency
- [ ] Test Embedding shows dimension count + latency
- [ ] Test Vision shows image description + latency
- [ ] Save per section works independently
- [ ] Embedding model change shows re-embed warning
- [ ] Only `is_developer=true` users can access panel (hidden + 403 for others)
- [ ] Responsive layout

---

## Task 7.1b: User Chat Override UI

### New File: `electron-app/src/renderer/components/ai/user-chat-override.tsx`

Accessible to **any authenticated user** from the chat sidebar gear icon. Allows users to bring their own API key for chat only.

```tsx
/**
 * User Chat Override — personal API key for Blair chat.
 *
 * Access: Any authenticated user (including viewers)
 * Location: Chat sidebar → gear icon (⚙) → settings popover/panel
 *
 * ┌─────────────────────────────────────────────┐
 * │ ⚙ AI Settings                              │
 * ├─────────────────────────────────────────────┤
 * │                                             │
 * │ Use your own AI subscription to power       │
 * │ Blair. Otherwise, the company default       │
 * │ will be used.                               │
 * │                                             │
 * │ Provider:  ○ OpenAI    ○ Anthropic          │
 * │                                             │
 * │ API Key:   [•••••••••••••••••••••]          │
 * │                                             │
 * │ Model:     [Claude Sonnet 4.6       ▼]      │
 * │                                             │
 * │         [Test] 🟢 Connected (189ms)         │
 * │                                             │
 * │         [Save]  [Remove My Override]        │
 * │                                             │
 * │ i Your key is encrypted and never shared.   │
 * │   Remove anytime to use company default.    │
 * │                                             │
 * │ Currently using: Your Anthropic key         │
 * └─────────────────────────────────────────────┘
 */
```

### UX Details

- **Provider**: Radio buttons — **OpenAI** and **Anthropic** only. No Ollama (server-side, not relevant for personal keys).
- **API Key**: Password input, masked. Required.
- **Model dropdown**: Populated from `AiModels` table filtered by selected `provider_type` + `capability='chat'`.
  - OpenAI selected → shows GPT-5.2, GPT-5.1, GPT-5, GPT-5 Mini, GPT-5 Nano, GPT-4.1, GPT-4.1 Mini
  - Anthropic selected → shows Claude Opus 4.6, Claude Sonnet 4.6, Claude Opus 4.5, Claude Sonnet 4.5, Claude Haiku 4.5
- **[Test]**: Calls `POST /api/ai/config/me/providers/{type}/test` after saving. Shows response latency + success/failure.
- **[Save]**: Calls `POST /api/ai/config/me/providers` — creates/updates user-scoped provider with `scope='user'` and auto-creates a chat `AiModel` under it.
- **[Remove My Override]**: Calls `DELETE /api/ai/config/me/providers/{type}` — removes user override, falls back to company default.
- **Status bar at bottom**: Shows current effective state:
  - `"Currently using: Your Anthropic key (Claude Sonnet 4.6)"` — override active
  - `"Currently using: Company default (GPT-5.2)"` — no override, using global
  - `"⚠ Your key failed. Using company default."` — override key invalid, fell back
  - `"⚠ AI not configured. Contact your admin."` — no global config and no override

### Backend Changes

- `POST /api/ai/config/me/providers` — restrict to chat-only overrides. Reject attempts to create embedding/vision overrides.
- Auto-create a chat `AiModel` under the user's provider from the `preferred_model` field (which becomes required).
- `ProviderRegistry.get_vision_provider()` — remove `user_id` parameter so vision always resolves globally (same as embedding).

### API Flow

```
1. User picks Anthropic, pastes key, picks claude-sonnet-4-6
2. Clicks [Save]
   → POST /api/ai/config/me/providers
     { provider_type: "anthropic", api_key: "sk-ant-...", preferred_model: "claude-sonnet-4-6" }
   → Backend encrypts key, creates AiProvider(scope='user') + AiModel(capability='chat')
3. Clicks [Test]
   → POST /api/ai/config/me/providers/anthropic/test
   → Backend decrypts key, sends minimal message, returns { success: true, latency_ms: 189 }
   → UI shows 🟢 or 🔴
4. Next time Blair is used:
   → ProviderRegistry.get_chat_provider(db, user_id=current_user.id)
   → Finds user's Anthropic override → uses it
   → Embedding/Vision still use company global config (unaffected)
5. User clicks [Remove My Override]
   → DELETE /api/ai/config/me/providers/anthropic
   → Falls back to company default
```

### Acceptance Criteria
- [ ] Accessible from chat sidebar gear icon
- [ ] Only shows OpenAI and Anthropic as provider options (no Ollama)
- [ ] Model dropdown filters by selected provider + capability='chat'
- [ ] API key encrypted on save, never returned in responses
- [ ] Test button verifies connectivity and shows latency
- [ ] Save creates user-scoped provider + auto-creates chat model
- [ ] Remove override deletes user-scoped provider, falls back to global
- [ ] Status bar shows current effective configuration
- [ ] Works for any authenticated user (including viewers)
- [ ] Embedding and vision are unaffected by user override

---

## Task 7.1c: Developer Indexing Tab

Part of the developer settings panel (separate tab alongside the capability sections).

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

### Developer Tab: Blair's Personality

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
│ Leave empty to use the default (concise, professional). │
│ Note: Blair's name is always "Blair" regardless of      │
│ custom prompt.                                          │
│                                                         │
│ [Reset to Default]  [Save]                              │
└─────────────────────────────────────────────────────────┘
```

- Textarea for custom system prompt
- Saved as application-level setting (new column or JSON config)
- "Reset to Default" clears custom prompt, reverts to Blair's default (concise, professional)
- Preview of current effective prompt (custom or default)
- Blair's name always stays "Blair" even with custom prompt (prepended if not present)

### Acceptance Criteria (Indexing + Personality)
- [ ] Indexing tab loads document status correctly
- [ ] Reindex buttons trigger backend operations
- [ ] System prompt customization saves and applies
- [ ] Only `is_developer=true` users can access developer settings
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
 * - (Graph timestamp removed — Phase 3 KG replaced by Phase 3.1)
 * - Chunk count: N
 * - [Reindex Now] button
 *
 * Data source: DocumentResponse.embedding_updated_at (graph_ingested_at removed by Phase 3.1)
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
- ~~`entity_extraction_service.py` (after each extraction)~~ *(Removed — Phase 3 KG replaced by Phase 3.1)*
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
        # knowledge_graph section REMOVED — Phase 3 KG replaced by Phase 3.1 (SQL access via scoped views)
        "sql_access": {
            "scoped_views_count": int,   # Number of v_* views available
            "last_query_at": str | None, # ISO timestamp of last AI SQL query
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
- [ ] ~~Knowledge graph counts reported~~ → SQL access status reported (scoped views count, last query timestamp)
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
1. Developer Configure AI (requires is_developer=true):
   → Open developer settings → AI Configuration
   → Chat section: pick Anthropic, paste API key, select claude-sonnet-4-6, click [Test Chat] → Shows response text + latency 🟢
   → Embedding section: pick OpenAI, paste API key, select text-embedding-3-small, click [Test Embedding] → Shows 1536 dims 🟢
   → Vision section: pick OpenAI (same key auto-shared), select gpt-5.2, click [Test Vision] → Shows description 🟢
   → Save each section independently

2. Create a Document:
   → Create a document with text content + embedded images
   → Wait ~30s
   → Document header shows "Indexed X seconds ago"
   → Click badge → popover shows chunk count

3. ~~Trigger Entity Extraction~~ → Test SQL Access *(Updated — Phase 3 KG replaced by Phase 3.1)*:
   → In Blair sidebar, ask "How many tasks are in this project?"
   → Verify SQL query executes against scoped views
   → Verify results are RBAC-scoped to user's accessible applications

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

12. Developer Settings Access:
    → Non-developer tries to access AI settings → hidden/403
    → Developer (is_developer=true) can configure chat/embedding/vision providers+models
    → Test buttons work for all 3 capabilities
    → Indexing tab shows all documents with status

13. User Chat Override:
    → Any authenticated user opens sidebar → gear icon → AI Settings
    → Picks Anthropic, pastes personal API key, selects Claude Sonnet 4.6
    → Clicks [Test] → 🟢 Connected
    → Clicks [Save] → status shows "Currently using: Your Anthropic key"
    → Blair now uses personal key for chat (embedding/vision unaffected)
    → Clicks [Remove My Override] → falls back to company default
```
