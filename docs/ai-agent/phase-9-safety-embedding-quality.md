# Phase 9: Safety, Cost Controls & Embedding Quality

**Goal**: Harden AI pipelines against cost explosions, resource exhaustion, and embedding quality issues discovered during audit. Fix chunking for tables, slides, and canvas containers to improve RAG retrieval accuracy.

**Depends on**: Phase 7 (admin polish — rate limiter, telemetry, embedding service already exist)
**No downstream dependencies**

---

## Category A: Cost & Safety

### Task 9.1: Agent Tool Call Counting

**Problem**: `_count_tool_iterations()` in `agent/graph.py` counts `AIMessage` objects, not individual tool calls. If the LLM batches 20 tool calls in one message, it counts as 1 iteration. With `MAX_ITERATIONS = 10`, that allows up to 200 tool executions per chat.

**Fix**: Count total tool calls across all messages. Introduce `MAX_TOOL_CALLS = 50` as the hard limit.

#### Modify: `fastapi-backend/app/ai/agent/graph.py`

Change `_count_tool_iterations()` to count `len(msg.tool_calls)` per AIMessage instead of counting AIMessages. Replace iteration-based check with total-tool-call-based check:

```python
def _count_total_tool_calls(messages: list[BaseMessage]) -> int:
    """Count total tool calls across all messages."""
    count = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            count += len(msg.tool_calls)
    return count
```

Update the should-continue condition to check `_count_total_tool_calls(state["messages"]) >= MAX_TOOL_CALLS`.

---

### Task 9.2: Streaming Timeout

**Problem**: SSE stream in `ai_chat.py` wraps `astream()` with no timeout. If the LLM provider hangs mid-stream, the connection + DB session are held open indefinitely.

**Fix**: Add 120s overall timeout + 30s idle-between-chunks timeout.

#### Modify: `fastapi-backend/app/routers/ai_chat.py`

Wrap the streaming generator in `asyncio.timeout(120)` for the overall stream. Track time since last chunk; if >30s between chunks, raise `asyncio.TimeoutError` to kill the hung stream. Ensure timeout triggers proper cleanup of DB session and Redis locks.

```python
STREAM_OVERALL_TIMEOUT_S = 120
STREAM_IDLE_TIMEOUT_S = 30
```

---

### Task 9.3: Streaming Chunk Limit

**Problem**: No cap on total chunks or bytes streamed per response. A runaway response could consume unbounded memory across thousands of concurrent users.

**Fix**: Add `MAX_CHUNKS_PER_RESPONSE` counter.

#### Modify: `fastapi-backend/app/routers/ai_chat.py`

Add counter inside the streaming generator. If chunk count exceeds limit, log a warning and terminate the stream gracefully with an error event.

```python
MAX_CHUNKS_PER_RESPONSE = 2000  # ~32KB if avg 16 bytes/chunk
```

---

### Task 9.4: Vision API Timeout

**Problem**: Each `describe_image()` call in `image_understanding_service.py` has no timeout. 10 images × a hung vision API = worker blocked for hours.

**Fix**: Wrap each vision call in `asyncio.wait_for(..., timeout=30)`.

#### Modify: `fastapi-backend/app/ai/image_understanding_service.py`

Wrap `self._describe_image()` calls in both `process_document_images()` and `process_imported_images()`:

```python
try:
    description_text = await asyncio.wait_for(
        self._describe_image(vision_provider, vision_model, image_bytes),
        timeout=30.0,
    )
except asyncio.TimeoutError:
    logger.warning("Vision LLM timeout for image %d in document %s", idx, document_id)
    failed += 1
    continue
```

---

### Task 9.5: Global Import Concurrency Limit

**Problem**: Rate limit is per-user (10 files/hr), but there is no global cap. 100 users × 10 imports = 1,000 concurrent import jobs all calling Docling + vision + embedding APIs simultaneously.

**Fix**: Redis-based concurrency counter with cap at ~5 concurrent imports.

#### Modify: `fastapi-backend/app/worker.py`

At the start of `process_document_import()`:
1. `INCR` a Redis key `import:concurrency:count` (with TTL as safety net).
2. If value > `MAX_CONCURRENT_IMPORTS` (5), re-queue the job with `_defer_by=timedelta(seconds=15)` and `DECR` the counter.
3. Wrap the entire import body in `try/finally` to always `DECR` on completion.

```python
MAX_CONCURRENT_IMPORTS = 5
IMPORT_CONCURRENCY_KEY = "import:concurrency:count"
IMPORT_CONCURRENCY_TTL = 3600  # 1hr safety TTL
```

---

### Task 9.6: Embedding — Manual Sync Only

**Problem**: Every document save queues an embedding job. ARQ dedup helps but after the 120s defer window, a new edit queues a fresh one. Power users editing all day trigger hundreds of re-embeddings per document.

**Fix**: Remove auto-embed on save entirely. Embeddings triggered only by:
1. Manual "Sync to Knowledge" button click per document.
2. Nightly batch worker job for all stale documents.
3. Document import (initial embed on import is fine).

Display a badge on documents where `updated_at > embedding_updated_at` OR `embedding_updated_at IS NULL` to indicate the document has unsynced changes.

#### Modify: `fastapi-backend/app/worker.py`

Remove the `embed_document_job` enqueue call from document save/update paths. Keep it callable from the manual sync endpoint and the nightly batch job.

#### Modify: `fastapi-backend/app/routers/documents.py`

Add `POST /api/documents/{document_id}/sync-embeddings` endpoint — queues `embed_document_job` for a single document. Requires Editor or Owner permission.

#### Modify: `fastapi-backend/app/worker.py`

Add nightly cron job `batch_embed_stale_documents` — queries all documents where `updated_at > embedding_updated_at` or `embedding_updated_at IS NULL`, queues embed jobs in batches of 10 with 5s spacing.

#### Modify: `fastapi-backend/app/schemas/document.py`

Add `is_embedding_stale: bool` computed field to `DocumentResponse` — `True` when `embedding_updated_at IS NULL` or `embedding_updated_at < updated_at`.

#### New: `electron-app/src/renderer/components/knowledge/document-sync-badge.tsx`

Badge component showing sync status. Yellow "Unsynced" badge + sync button when stale. Green "Synced" when up to date.

---

### Task 9.7: SQL Execution Backup Timeout

**Problem**: `sql_executor.py` has `SET LOCAL statement_timeout = 5000ms` but no `asyncio.wait_for()` backup. If the PostgreSQL timeout fails to fire, the app has no safety net.

**Fix**: Wrap the DB execute call in `asyncio.wait_for(..., timeout=6)`.

#### Modify: `fastapi-backend/app/ai/sql_executor.py`

```python
try:
    result = await asyncio.wait_for(
        _execute_query(sql, db),
        timeout=6.0,  # Slightly above PG's 5s to let PG timeout first
    )
except asyncio.TimeoutError:
    raise ValueError("Query execution timeout exceeded (application-level)")
```

---

### Task 9.8: RAG Query Embedding Cache

**Problem**: Each RAG tool invocation in a single chat session generates a fresh query embedding. 10 RAG calls in one chat = 10 embedding API calls for the same or similar query.

**Fix**: Cache query embeddings for the chat session. Pass cached embedding from agent state to the RAG tool.

#### Modify: `fastapi-backend/app/ai/agent_tools.py`

Add `_query_embedding_cache: dict[str, list[float]]` to agent state. Before calling `retrieval_service.retrieve()`, check if the query (or a sufficiently similar query) has a cached embedding. Pass the pre-computed embedding to `retrieve()` to skip re-generation.

#### Modify: `fastapi-backend/app/ai/retrieval_service.py`

Add optional `query_embedding: list[float] | None = None` parameter to `retrieve()`. If provided, skip the embedding generation step and use the provided vector directly.

---

### Task 9.9: Import File Streaming

**Problem**: `await file.read()` in the import router loads up to 50MB entirely into memory. 100 concurrent imports = 5GB memory spike.

**Fix**: Stream the uploaded file directly to a temp file on disk.

#### Modify: `fastapi-backend/app/routers/ai_import.py`

Replace:
```python
contents = await file.read()
```

With streaming write:
```python
import aiofiles
import tempfile

with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp:
    temp_path = tmp.name

async with aiofiles.open(temp_path, "wb") as f:
    while chunk := await file.read(64 * 1024):  # 64KB chunks
        await f.write(chunk)
```

---

## Category B: Embedding Quality

### Task 9.10: Table Boundary Awareness

**Problem**: The chunker treats table nodes as regular text. Tables get merged with surrounding paragraphs. When tables are large, they get split at sentence boundaries which can break mid-row and lose column headers. Tables should be exempt from MAX_TOKENS — they are always kept as a single chunk.

**Fix**: When the chunker encounters a `table` node:
1. Flush whatever is in the current text buffer as its own chunk.
2. Extract the table as its own chunk with a natural language preamble.
3. **Bypass MAX_TOKENS** — tables are never split, never "oversized".
4. Continue walking — next content starts a fresh buffer.

Applies to: **Editor documents** (TipTap), **Imported documents** (Docling → TipTap), and **Canvas containers** (after fix 9.11).

#### Modify: `fastapi-backend/app/ai/chunking_service.py`

In `_extract_blocks()`, when `node_type == "table"`:
- Mark the block with `is_table = True` (add field to `_TextBlock` dataclass).
- Extract header row cells for the preamble.

In `_merge_and_split()`:
- When encountering a block with `is_table = True`:
  - Flush the current buffer as a chunk.
  - Build preamble: `"Table: {heading_context} — columns: {col1}, {col2}, ..."`
  - Create the table as its own chunk (preamble + pipe-delimited rows).
  - Do NOT check MAX_TOKENS — table chunks are exempt.
  - Continue with a fresh buffer.

In `_extract_table_text()`:
- Return both the full table text AND the header row cells separately (for preamble generation).

---

### Task 9.11: Canvas Container TipTap Parsing

**Problem**: Canvas containers store full TipTap JSON in `container.content`, but the canvas chunker only reads `elem.get("text")` which flattens everything to plain text. Tables in canvas containers lose all structure.

**Fix**: Parse each canvas container's `content` as a TipTap document and run `_chunk_tiptap()` on it. This gives canvas containers all the same chunking quality as editor documents — tables become own chunks (via fix 9.10), headings create context, etc.

#### Modify: `fastapi-backend/app/ai/chunking_service.py`

In `_chunk_canvas()`:
- Detect `containers` array in canvas JSON.
- For each container with `content.type == "doc"`:
  - Run `_chunk_tiptap(container["content"], title)` on the container's content.
  - Use container position for heading context: `"{container_label} — {quadrant}"`.
  - Collect resulting chunks.
- For non-container elements (plain text sticky notes, etc.):
  - Keep existing clustering + `_build_cluster_text()` logic.

---

### Task 9.12: Slide Boundary Enforcement

**Problem**: When PPTX is imported via Docling, each slide becomes `## Slide N: Title`. But the chunker merges adjacent small slides into one chunk and splits large slides with overlap that bleeds across slide boundaries.

**Fix**: Enforce chunk boundaries at `## Slide N` headings. Each slide = its own chunk (or set of chunks if the slide itself exceeds MAX_TOKENS). Never merge content across slide boundaries.

#### Modify: `fastapi-backend/app/ai/chunking_service.py`

In `_merge_and_split()`:
- When encountering a heading block that starts with `"Slide "` (from Docling's `## Slide N: Title` pattern):
  - Flush the current buffer as a chunk.
  - Start a new buffer with this slide's content.
  - Set `heading_context = "Slide N: {title}"` for all chunks from this slide.
- Within a single slide, normal chunking rules apply (split at MAX_TOKENS with sentence boundaries if the slide text is huge).

---

### Task 9.13: Canvas Oversized Element Fallback

**Problem**: In `_split_cluster()`, if a single canvas element exceeds MAX_TOKENS, it gets added as-is with no sub-split. This can produce chunks that exceed the embedding model's input limit (8,191 tokens for `text-embedding-3-small`).

**Fix**: After appending an element in `_split_cluster()`, check if the single element exceeds MAX_TOKENS. If so, fall back to `_split_large_text()` on that element's text. Tables are exempt from this (they bypass MAX_TOKENS per fix 9.10/9.11).

#### Modify: `fastapi-backend/app/ai/chunking_service.py`

In `_split_cluster()`:
```python
for elem in cluster:
    elem_tokens = self.count_tokens(elem_text)

    # Tables bypass MAX_TOKENS (handled by _chunk_tiptap via 9.11)
    # For plain text elements that exceed MAX_TOKENS, sub-split
    if elem_tokens > self.MAX_TOKENS:
        heading = self._canvas_heading_context(elem)
        sub_chunks = self._split_large_text(elem.text, heading)
        chunks.extend(sub_chunks)
        continue

    # Normal element accumulation logic...
```

---

### Task 9.14: Imported Image Slide Context

**Problem**: When Docling extracts images from PPTX slides, the image description chunks have `heading_context = "Imported Image (page N)"`. They lose the slide title context, reducing retrieval quality.

**Fix**: When building `image_nodes_for_chunks` in `process_imported_images()`, look up the slide title from the markdown and use it as heading context.

#### Modify: `fastapi-backend/app/ai/image_understanding_service.py`

Change heading from:
```python
heading = f"Imported Image (page {img.page_number})" if img.page_number else "Imported Image"
```

To:
```python
heading = f"Imported Image — Slide {img.page_number}: {slide_title}" if slide_title else f"Imported Image (page {img.page_number})"
```

#### Modify: `fastapi-backend/app/worker.py`

In `process_document_import()`, after Docling produces markdown, parse `## Slide N: Title` headings into a `dict[int, str]` mapping page_number → slide_title. Pass this mapping to `process_imported_images()` so it can resolve slide titles.

---

## Category C: Configuration

### Task 9.15: Generate AI Encryption Key

**Action**: Generate a Fernet key and set `AI_ENCRYPTION_KEY` in `.env`. Without this, AI provider API keys are stored unencrypted in the database.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

### Task 9.16: Replace JWT Secret Placeholder

**Action**: Replace `JWT_SECRET=your-super-secret-key-change-in-production` in `.env` with a real secret.

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## Category D: AI Config Panel

### Task 9.17: Fix is_developer Bug

**Problem**: `require_developer()` in `ai_config.py` has leftover debug logging from investigation. If `is_developer=None` on a `User` object (from stale cache predating the field), the check silently fails instead of explicitly denying access.

**Fix**: Remove debug logging. Add safety net for `is_developer=None` — log warning, invalidate cache, deny access.

#### Modify: `fastapi-backend/app/routers/ai_config.py`

Remove debug `import logging as _log` and `_log.getLogger(...).warning(...)` from `require_developer()`. Add safety net: if `is_developer is None`, log warning, call `invalidate_user(user_id)`, raise 403.

---

### Task 9.18: Add Filtering to GET /models

**Problem**: `GET /api/ai/config/models` returns ALL models regardless of provider or capability. The per-capability config tab's model dropdown shows irrelevant models.

**Fix**: Add optional `provider_type` and `capability` query parameters with conditional `.where()` clauses.

#### Modify: `fastapi-backend/app/routers/ai_config.py`

Add `provider_type: str | None = None` and `capability: str | None = None` query params to `list_models()`. Apply `.where(AiModel.provider_type == provider_type)` and `.where(AiModel.capability == capability)` when provided.

---

### Task 9.19: Add GET /capability/{capability} Endpoint

**Problem**: Frontend calls `GET /capability/{capability}` to load saved per-capability config, but only `PUT` exists. The AI Config panel can't display current settings on page load.

**Fix**: Add GET endpoint and `CapabilityConfigResponse` schema.

#### Modify: `fastapi-backend/app/schemas/ai_config.py`

Add `CapabilityConfigResponse` schema with fields: `capability`, `provider_id`, `provider_type`, `model_id`, `model_display_name`, `has_api_key`.

#### Modify: `fastapi-backend/app/routers/ai_config.py`

Add `GET /capability/{capability}` — query the default model for the capability (`is_default=True`, global scope), return provider info via `CapabilityConfigResponse`.

---

### Task 9.20: Fix User Override Model Access

**Problem**: `UserChatOverrideContent` calls `useAiModels()` which hits the developer-only `GET /models` endpoint. Regular users get 403 when trying to select a model in the chat override popover.

**Fix**: Use the existing public `GET /api/ai/config/models/available` endpoint instead.

#### Modify: `electron-app/src/renderer/hooks/use-ai-config.ts`

Add `useAvailableModels(params?)` hook calling `GET /api/ai/config/models/available` with optional `provider_type` and `capability` filter params.

#### Modify: `electron-app/src/renderer/components/ai/user-chat-override.tsx`

Replace `useAiModels(...)` with `useAvailableModels({ provider_type, capability: 'chat' })`.

---

### Task 9.21: Wire AI Settings into App

**Problem**: `AiSettingsPanel` is built but the Settings page in `dashboard.tsx` renders a "coming soon" placeholder. Developers cannot access the AI configuration UI.

**Fix**: Render `AiSettingsPanel` in the Settings page with fallback for non-developers.

#### Modify: `electron-app/src/renderer/pages/dashboard.tsx`

Replace "coming soon" placeholder in the settings case with `<AiSettingsPanel />`. Add `{!user?.is_developer && <p>No settings available</p>}` fallback.

---

### Task 9.22: Providers & Models Management Tab

**Problem**: No UI to manage (add, edit, delete) AI models under existing providers. Developers must use API calls directly.

**Fix**: New CRUD table component wired as 4th tab in AiSettingsPanel.

#### New: `electron-app/src/renderer/components/ai/providers-models-tab.tsx`

Table with columns: Model ID, Display Name, Provider, Capability, Embedding Dimensions, Default, Enabled, Actions (Edit/Delete). Provider + capability filter dropdowns. Add/Edit model dialogs. Delete confirmation AlertDialog.

Reuses hooks: `useAiModels()`, `useAiProviders()`, `useCreateAiModel()`, `useUpdateAiModel()`, `useDeleteAiModel()`.

#### Modify: `electron-app/src/renderer/components/ai/ai-settings-panel.tsx`

Add 4th tab "Providers & Models" rendering `<ProvidersModelsTab />`.

#### Modify: `electron-app/src/renderer/components/ai/index.ts`

Export `ProvidersModelsTab`.

---

## Testing Requirements

All fixes must include unit tests. Use existing test patterns:
- Create tables at session start, rollback at session end (no per-test create/drop).
- pytest fixtures for DB sessions, Redis mocks, provider mocks.
- 80% coverage target.

### Key Test Scenarios

| Fix | Test |
|-----|------|
| 9.1 | Agent with LLM that batches 20 tool calls — verify stops at MAX_TOOL_CALLS |
| 9.2 | Mock provider that hangs after 2 chunks — verify stream terminates at idle timeout |
| 9.3 | Mock provider that produces 5000 chunks — verify stream stops at MAX_CHUNKS |
| 9.4 | Mock vision provider that hangs — verify 30s timeout per image |
| 9.5 | Simulate 10 concurrent imports — verify only 5 run, rest deferred |
| 9.6 | Save document, verify no embed job queued. Click sync, verify job queued. Verify stale badge logic. |
| 9.7 | Mock DB that hangs on execute — verify asyncio timeout fires |
| 9.8 | Two RAG calls with same query — verify only 1 embedding API call |
| 9.9 | Upload 50MB file — verify memory stays flat (stream to disk) |
| 9.10 | Document with paragraph + table + paragraph — verify 3 chunks: text, table (with preamble), text. Table with 200 rows — verify 1 chunk (bypass MAX_TOKENS). |
| 9.11 | Canvas with container holding TipTap table — verify table chunked as own chunk with preamble |
| 9.12 | PPTX with 5 slides — verify 5+ chunks with slide boundaries enforced, no cross-slide merging |
| 9.13 | Canvas element with 5000 tokens plain text — verify sub-split into multiple chunks |
| 9.14 | PPTX with image on Slide 3: "Revenue" — verify chunk heading = "Imported Image — Slide 3: Revenue" |
| 9.17 | User with stale `is_developer=None` — verify cache invalidated and 403 returned |
| 9.18 | GET /models with `provider_type=openai` — verify only OpenAI models returned |
| 9.19 | GET /capability/chat with configured default — verify correct config returned |
| 9.20 | Non-developer calls `useAvailableModels` — verify no 403, models returned |
| 9.21 | Developer navigates to Settings — verify AI Settings panel renders |
| 9.22 | Add/edit/delete model via table UI — verify CRUD operations persist |
