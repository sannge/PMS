# Phase 9: Safety, Cost Controls & Embedding Quality — Task Breakdown

**Created**: 2026-02-28
**Last updated**: 2026-02-28
**Status**: COMPLETE
**Spec**: [phase-9-safety-embedding-quality.md](../phase-9-safety-embedding-quality.md)

> **Depends on**: Phase 7 (admin polish — rate limiter, telemetry, embedding service already exist)
> **No downstream dependencies**

---

## Task Summary

| Section | Description | Task Count |
|---------|-------------|------------|
| 9.1 | Agent Tool Call Counting | 8 |
| 9.2 | Streaming Timeout | 10 |
| 9.3 | Streaming Chunk Limit | 6 |
| 9.4 | Vision API Timeout | 6 |
| 9.5 | Global Import Concurrency Limit | 10 |
| 9.6 | Embedding — Manual Sync Only | 18 |
| 9.7 | SQL Execution Backup Timeout | 5 |
| 9.8 | RAG Query Embedding Cache | 8 |
| 9.9 | Import File Streaming | 7 |
| 9.10 | Table Boundary Awareness | 14 |
| 9.11 | Canvas Container TipTap Parsing | 10 |
| 9.12 | Slide Boundary Enforcement | 8 |
| 9.13 | Canvas Oversized Element Fallback | 6 |
| 9.14 | Imported Image Slide Context | 7 |
| 9.15 | Generate AI Encryption Key | 2 |
| 9.16 | Replace JWT Secret Placeholder | 2 |
| 9.17 | Fix is_developer Bug | 4 |
| 9.18 | Add Filtering to GET /models | 5 |
| 9.19 | Add GET /capability/{capability} Endpoint | 6 |
| 9.20 | Fix User Override Model Access | 4 |
| 9.21 | Wire AI Settings into App | 4 |
| 9.22 | Providers & Models Management Tab | 10 |
| 9.23 | Code Reviews & Security Analysis | 12 |
| 9.24 | Unit Tests | 17 |
| 9.25 | Manual E2E Verification | 12 |
| 9.26 | Phase 9 Sign-Off | 5 |
| **GRAND TOTAL** | | **206** |

---

## Team

| Role | Abbreviation |
|------|-------------|
| Frontend Engineer | **FE** |
| Backend Engineer | **BE** |
| Code Reviewer 1 | **CR1** |
| Code Reviewer 2 | **CR2** |
| Security Analyst | **SA** |
| Quality Engineer | **QE** |
| Test Engineer | **TE** |
| Devil's Advocate | **DA** |

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked
- `[-]` Skipped / N/A

---

## 9.1 Agent Tool Call Counting

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.1.1 | Add `MAX_TOOL_CALLS = 50` constant to `agent/graph.py` alongside existing `MAX_ITERATIONS` | BE | [ ] | Total tool calls across all iterations, not per-iteration |
| 9.1.2 | Rename `_count_tool_iterations()` to `_count_total_tool_calls()` — iterate all `AIMessage` objects, sum `len(msg.tool_calls)` for each | BE | [ ] | Counts individual tool calls, not messages |
| 9.1.3 | Update the should-continue conditional node — check `_count_total_tool_calls(state["messages"]) >= MAX_TOOL_CALLS` instead of iteration count | BE | [ ] | Keep `MAX_ITERATIONS` as secondary safety net |
| 9.1.4 | When tool call limit is reached, return a user-facing message: `"I've reached the maximum number of operations for this request. Here's what I found so far..."` | BE | [ ] | Don't just silently stop |
| 9.1.5 | Add structured log via telemetry when tool call limit is hit — log user_id, total_tool_calls, last_tool_name | BE | [ ] | Helps identify patterns |
| 9.1.6 | Write unit test: mock LLM that returns 20 tool_calls per AIMessage — verify agent stops at 50 total, not 50 iterations | TE | [ ] | Critical correctness test |
| 9.1.7 | Write unit test: normal agent with 3 tool calls per iteration — verify still works up to ~16 iterations | TE | [ ] | Regression test |
| 9.1.8 | **CR1 Review**: Is `MAX_TOOL_CALLS = 50` the right number? Too low blocks legitimate complex queries, too high allows cost explosion. Check typical tool call counts from telemetry logs. | CR1 | [ ] | |

---

## 9.2 Streaming Timeout

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.2.1 | Add constants `STREAM_OVERALL_TIMEOUT_S = 120` and `STREAM_IDLE_TIMEOUT_S = 30` to `ai_chat.py` | BE | [ ] | |
| 9.2.2 | Wrap the outer streaming generator (`_guarded_stream()` or equivalent) in `asyncio.timeout(STREAM_OVERALL_TIMEOUT_S)` | BE | [ ] | Catches total-time runaways |
| 9.2.3 | Inside the streaming loop, track `last_chunk_time = time.monotonic()`. Before each `yield`, check if `time.monotonic() - last_chunk_time > STREAM_IDLE_TIMEOUT_S` — if so, raise `asyncio.TimeoutError` | BE | [ ] | Catches mid-stream hangs |
| 9.2.4 | On timeout, send a final SSE error event `{"type": "error", "message": "Stream timeout — response took too long"}` before closing | BE | [ ] | Client sees clean error, not silent disconnect |
| 9.2.5 | Ensure timeout cleanup releases: DB session, Redis locks, any open provider connections | BE | [ ] | Use `try/finally` block |
| 9.2.6 | Write unit test: mock provider that yields 2 chunks then hangs — verify idle timeout fires at 30s | TE | [ ] | |
| 9.2.7 | Write unit test: mock provider that yields 1 chunk per second for 200s — verify overall timeout fires at 120s | TE | [ ] | |
| 9.2.8 | Write unit test: normal fast stream (10 chunks in 2s) — verify no timeout interference | TE | [ ] | Regression test |
| 9.2.9 | Add telemetry log on stream timeout — log user_id, chunks_sent_before_timeout, timeout_type (overall vs idle), elapsed_ms | BE | [ ] | |
| 9.2.10 | **CR1 Review**: Are 120s/30s the right thresholds? Review agent tool chain timing — complex multi-tool queries may legitimately have 20s+ gaps between chunks during tool execution. | CR1 | [ ] | |

---

## 9.3 Streaming Chunk Limit

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.3.1 | Add constant `MAX_CHUNKS_PER_RESPONSE = 2000` to `ai_chat.py` | BE | [ ] | ~32KB at avg 16 bytes/chunk |
| 9.3.2 | Add `chunk_count` counter inside the streaming generator — increment on each yielded event | BE | [ ] | |
| 9.3.3 | When `chunk_count > MAX_CHUNKS_PER_RESPONSE`, send final error SSE event and terminate stream | BE | [ ] | `{"type": "error", "message": "Response exceeded maximum size"}` |
| 9.3.4 | Add telemetry log when chunk limit is hit — log user_id, chunk_count, estimated_bytes | BE | [ ] | |
| 9.3.5 | Write unit test: mock provider that produces 5000 chunks — verify stream stops at 2000 | TE | [ ] | |
| 9.3.6 | **DA Challenge**: Is 2000 chunks the right limit? What's the largest legitimate agent response? Check if multi-tool responses with SQL results + RAG context could legitimately exceed this. | DA | [ ] | |

---

## 9.4 Vision API Timeout

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.4.1 | Add constant `VISION_TIMEOUT_S = 30` to `image_understanding_service.py` | BE | [ ] | |
| 9.4.2 | Wrap `self._describe_image()` call in `process_document_images()` (TipTap path) with `asyncio.wait_for(..., timeout=VISION_TIMEOUT_S)` — on timeout, increment `failed` counter and `continue` | BE | [ ] | |
| 9.4.3 | Wrap `self._describe_image()` call in `process_imported_images()` (import path) with same timeout logic | BE | [ ] | Both paths need the fix |
| 9.4.4 | Log warning on vision timeout — include document_id, image_index, elapsed time | BE | [ ] | |
| 9.4.5 | Write unit test: mock vision provider that hangs for 60s — verify timeout fires at 30s, processing continues to next image | TE | [ ] | |
| 9.4.6 | Write unit test: 10 images, 3 timeout — verify 7 descriptions stored, 3 logged as failed | TE | [ ] | |

---

## 9.5 Global Import Concurrency Limit

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.5.1 | Add constants `MAX_CONCURRENT_IMPORTS = 5`, `IMPORT_CONCURRENCY_KEY = "import:concurrency:count"`, `IMPORT_CONCURRENCY_TTL = 3600` to `worker.py` | BE | [ ] | |
| 9.5.2 | At the start of `process_document_import()`, `INCR` the Redis concurrency key and set TTL if new | BE | [ ] | TTL is safety net against leaked counters |
| 9.5.3 | If `INCR` result > `MAX_CONCURRENT_IMPORTS`, `DECR` immediately and re-queue the job with `_defer_by=timedelta(seconds=15)` — return early with status `"deferred"` | BE | [ ] | Job retries after 15s |
| 9.5.4 | Wrap the entire import processing body in `try/finally` — always `DECR` on completion (success, failure, or exception) | BE | [ ] | Critical: leaked counters would block all future imports |
| 9.5.5 | Add safety: if `DECR` returns a negative value, `SET` the key to 0 — prevents counter drift from race conditions or crashes | BE | [ ] | |
| 9.5.6 | Handle Redis unavailability — if Redis is down, allow the import (fail-open for concurrency check, not for rate limit) | BE | [ ] | Imports are more important than concurrency control |
| 9.5.7 | Log concurrency status on each import — `"Import concurrency: %d/%d active"` | BE | [ ] | |
| 9.5.8 | Write unit test: simulate 10 concurrent imports — verify only 5 proceed, 5 are deferred | TE | [ ] | Mock Redis INCR/DECR |
| 9.5.9 | Write unit test: import fails mid-processing — verify DECR still fires (counter cleanup) | TE | [ ] | |
| 9.5.10 | **CR1 Review**: Is `MAX_CONCURRENT_IMPORTS = 5` correct for the target hardware? Could CPU-bound Docling processing + vision API calls + embedding calls handle 5 simultaneously without starving other workers? | CR1 | [ ] | |

---

## 9.6 Embedding — Manual Sync Only

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.6.1 | Remove `embed_document_job` enqueue from document save/update paths in `worker.py` and `routers/documents.py` — search for all places that enqueue embedding on document content change | BE | [ ] | Audit all enqueue points |
| 9.6.2 | Keep `embed_document_job` callable from manual sync endpoint and import pipeline — do NOT delete the job function itself | BE | [ ] | Only remove auto-trigger |
| 9.6.3 | Create `POST /api/documents/{document_id}/sync-embeddings` endpoint in `routers/documents.py` — queues `embed_document_job` for the specified document | BE | [ ] | Returns 202 Accepted with job ID |
| 9.6.4 | Add permission check on sync endpoint — require Editor or Owner role on the document | BE | [ ] | Viewers can't trigger embedding |
| 9.6.5 | Add rate limit to sync endpoint — reuse `ai_reindex` rate limit (20 req/hr per user) | BE | [ ] | Prevent manual spam |
| 9.6.6 | Add `is_embedding_stale` computed property to `Document` SQLAlchemy model — returns `True` when `embedding_updated_at IS NULL` or `embedding_updated_at < updated_at` | BE | [ ] | Column `embedding_updated_at` already exists from Phase 2 |
| 9.6.7 | Add `is_embedding_stale: bool` field to `DocumentResponse` Pydantic schema — computed from the model property | BE | [ ] | Frontend uses this for badge display |
| 9.6.8 | Create nightly cron job `batch_embed_stale_documents` in `worker.py` — query all documents where `is_embedding_stale`, enqueue embed jobs in batches of 10 with 5s spacing between batches | BE | [ ] | Use ARQ cron pattern |
| 9.6.9 | Add ARQ cron schedule for `batch_embed_stale_documents` — run at 2:00 AM server timezone daily | BE | [ ] | Off-peak hours |
| 9.6.10 | Add batch size and spacing constants: `NIGHTLY_EMBED_BATCH_SIZE = 10`, `NIGHTLY_EMBED_BATCH_DELAY_S = 5` | BE | [ ] | Configurable via env vars |
| 9.6.11 | Create `document-sync-badge.tsx` component — show yellow "Unsynced" badge with sync button when `is_embedding_stale = true`, green "Synced" when false | FE | [ ] | Reuse existing badge patterns |
| 9.6.12 | Add sync button click handler — call `POST /api/documents/{id}/sync-embeddings`, show toast on success/error, optimistically update badge | FE | [ ] | |
| 9.6.13 | Integrate `document-sync-badge.tsx` into `document-header.tsx` — show next to document title | FE | [ ] | |
| 9.6.14 | Integrate `document-sync-badge.tsx` into document list views (KnowledgeTree, search results) — show small indicator icon | FE | [ ] | Subtle, not distracting |
| 9.6.15 | Add WebSocket event `DOCUMENT_EMBEDDING_SYNCED` — broadcast when embed job completes, frontend invalidates document query to update badge | BE | [ ] | Real-time badge update |
| 9.6.16 | Handle WebSocket event in frontend — on `DOCUMENT_EMBEDDING_SYNCED`, invalidate the document's React Query cache entry | FE | [ ] | Badge turns green without page refresh |
| 9.6.17 | Write unit test: save document via API — verify no `embed_document_job` enqueued | TE | [ ] | Regression test for auto-trigger removal |
| 9.6.18 | Write unit test: call sync endpoint — verify `embed_document_job` enqueued. Call again immediately — verify rate limited. | TE | [ ] | |

---

## 9.7 SQL Execution Backup Timeout

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.7.1 | Add constant `APP_QUERY_TIMEOUT_S = 6.0` to `sql_executor.py` — slightly above PG's 5s to let PG timeout fire first | BE | [ ] | |
| 9.7.2 | Wrap the DB execute call in `asyncio.wait_for(..., timeout=APP_QUERY_TIMEOUT_S)` | BE | [ ] | |
| 9.7.3 | On `asyncio.TimeoutError`, raise `ValueError("Query execution timeout exceeded (application-level)")` with structured log | BE | [ ] | |
| 9.7.4 | Write unit test: mock DB session that hangs on execute — verify asyncio timeout fires at 6s | TE | [ ] | |
| 9.7.5 | **CR1 Review**: Confirm the 6s app timeout doesn't race with the 5s PG timeout in a way that causes double-error handling. | CR1 | [ ] | |

---

## 9.8 RAG Query Embedding Cache

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.8.1 | Add `query_embedding_cache: dict[str, list[float]]` to agent state dict in `agent/graph.py` — initialized empty at session start | BE | [ ] | Keyed by query text hash |
| 9.8.2 | Add optional `query_embedding: list[float] | None = None` parameter to `retrieval_service.retrieve()` | BE | [ ] | When provided, skip embedding generation |
| 9.8.3 | In `retrieval_service.retrieve()`, if `query_embedding` is provided, use it directly for pgvector search instead of calling `provider.generate_embedding()` | BE | [ ] | |
| 9.8.4 | In `rag_search_tool` (agent_tools.py), before calling `retrieve()`: check cache for the query text — if hit, pass cached embedding; if miss, call `retrieve()` without pre-computed embedding, then cache the generated embedding from the result | BE | [ ] | |
| 9.8.5 | Add `generated_embedding: list[float] | None` to the `RetrievalResult` return type so the caller can cache it | BE | [ ] | |
| 9.8.6 | Cache is session-scoped — cleared when chat session ends (no persistence needed) | BE | [ ] | |
| 9.8.7 | Write unit test: call `retrieve()` twice with same query — verify embedding provider called only once | TE | [ ] | |
| 9.8.8 | Write unit test: call `retrieve()` with two different queries — verify embedding provider called twice | TE | [ ] | |

---

## 9.9 Import File Streaming

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.9.1 | Add `aiofiles` to `requirements.txt` if not already present | BE | [ ] | Check existing deps first |
| 9.9.2 | Replace `contents = await file.read()` with streaming write loop: `while chunk := await file.read(64 * 1024): await f.write(chunk)` to a `NamedTemporaryFile` | BE | [ ] | 64KB read chunks |
| 9.9.3 | Ensure temp file is cleaned up in `finally` block — `os.unlink(temp_path)` | BE | [ ] | Even on import failure |
| 9.9.4 | Update file size validation — track bytes written during streaming, reject if exceeds 50MB limit mid-stream (don't read entire file first to check size) | BE | [ ] | Early abort saves memory |
| 9.9.5 | Remove the old in-memory `contents` variable and any `tmp.write(contents)` that wrote from memory | BE | [ ] | |
| 9.9.6 | Write unit test: upload 50MB mock file — verify peak memory stays under 5MB (stream, don't buffer) | TE | [ ] | May need memory profiling fixture |
| 9.9.7 | **CR1 Review**: Is `aiofiles` the right choice? Could use `anyio.open_file()` instead if anyio is already a dependency. Check for unnecessary dependency addition. | CR1 | [ ] | |

---

## 9.10 Table Boundary Awareness

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.10.1 | Add `is_table: bool = False` and `header_cells: list[str] | None = None` fields to `_TextBlock` dataclass | BE | [ ] | |
| 9.10.2 | In `_extract_blocks()`, when `node_type == "table"`: set `is_table = True` on the created `_TextBlock` | BE | [ ] | |
| 9.10.3 | Modify `_extract_table_text()` to return a tuple `(full_text, header_cells)` — `header_cells` is a list of text from the first `tableRow` | BE | [ ] | Used for preamble generation |
| 9.10.4 | Store `header_cells` on the `_TextBlock` when `is_table = True` | BE | [ ] | |
| 9.10.5 | In `_merge_and_split()`, when encountering a block with `is_table = True`: (a) flush current buffer as chunk, (b) build preamble `"Table: {heading_context} — columns: {col1}, {col2}, ..."`, (c) create table as own chunk with preamble + table text, (d) do NOT check MAX_TOKENS, (e) continue with fresh buffer | BE | [ ] | Core logic change |
| 9.10.6 | Handle edge case: table with no heading context — preamble is just `"Table — columns: {col1}, {col2}, ..."` | BE | [ ] | |
| 9.10.7 | Handle edge case: table with no recognizable header row (all `tableCell`, no `tableHeader`) — use first row as header anyway (best effort) | BE | [ ] | TipTap paste from Excel uses `tableCell` for all rows |
| 9.10.8 | Handle edge case: empty table (no rows) — skip, don't create empty chunk | BE | [ ] | |
| 9.10.9 | Write unit test: document with paragraph (400 tokens) + table (300 tokens) + paragraph (300 tokens) — verify 3 separate chunks, table is middle chunk with preamble | TE | [ ] | |
| 9.10.10 | Write unit test: table with 200 rows (2000+ tokens) — verify single chunk, no split, preamble present | TE | [ ] | Tables bypass MAX_TOKENS |
| 9.10.11 | Write unit test: two adjacent tables — verify 2 separate chunks, never merged | TE | [ ] | |
| 9.10.12 | Write unit test: table with heading context "Q4 Report" and columns ["Name", "Revenue"] — verify preamble = `"Table: Q4 Report — columns: Name, Revenue"` | TE | [ ] | |
| 9.10.13 | Write unit test: empty table — verify no chunk created | TE | [ ] | |
| 9.10.14 | **CR2 Review**: Does bypassing MAX_TOKENS for tables risk exceeding embedding model input limit (8,191 tokens)? Is that an acceptable trade-off? Should we at least log a warning for tables > 4000 tokens? | CR2 | [ ] | |

---

## 9.11 Canvas Container TipTap Parsing

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.11.1 | In `_chunk_canvas()`, detect `containers` array in canvas JSON (alongside existing `elements` array) | BE | [ ] | Canvas format has both |
| 9.11.2 | For each container with `content.type == "doc"`: extract container position (`x`, `y`) and compute quadrant label | BE | [ ] | Reuse `_canvas_heading_context` pattern |
| 9.11.3 | Run `_chunk_tiptap(container["content"], title)` on each container's TipTap content | BE | [ ] | Reuse existing TipTap chunking — tables get fix 9.10 automatically |
| 9.11.4 | Prefix each container's chunks with heading context including container position: `"Canvas Container — {quadrant}"` | BE | [ ] | |
| 9.11.5 | Merge container chunks into the main canvas chunk list, maintaining chunk_index ordering | BE | [ ] | Container chunks interleaved with element chunks by position |
| 9.11.6 | For non-container elements (sticky notes, text boxes without TipTap content): keep existing clustering + `_build_cluster_text()` logic unchanged | BE | [ ] | Backwards compatible |
| 9.11.7 | Write unit test: canvas with one container holding a TipTap table — verify table is own chunk with preamble | TE | [ ] | Verifies 9.10 + 9.11 integration |
| 9.11.8 | Write unit test: canvas with container (TipTap doc) + plain text sticky notes — verify container uses `_chunk_tiptap`, sticky notes use existing clustering | TE | [ ] | |
| 9.11.9 | Write unit test: canvas with empty container (no content) — verify no crash, no empty chunks | TE | [ ] | |
| 9.11.10 | **CR1 Review**: Does delegating to `_chunk_tiptap()` per container produce correct heading_context? Does the container's position context survive the TipTap chunking pipeline? | CR1 | [ ] | |

---

## 9.12 Slide Boundary Enforcement

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.12.1 | In `_merge_and_split()`, detect heading blocks that match the pattern `"Slide \d+:?"` (Docling's `## Slide N: Title` pattern) | BE | [ ] | Regex: `r"^Slide \d+"` |
| 9.12.2 | When a slide heading is detected: flush current buffer as chunk, start fresh buffer for this slide's content | BE | [ ] | Same pattern as table boundary |
| 9.12.3 | Set `heading_context = "Slide N: {title}"` for all chunks generated from that slide's content | BE | [ ] | Persists through sub-splits |
| 9.12.4 | Within a single slide, normal MAX_TOKENS splitting applies — if one slide has 2000 tokens of text, split at sentence boundaries | BE | [ ] | Tables within slides still get fix 9.10 |
| 9.12.5 | Handle speaker notes (blockquotes from Docling): prepend `"[Speaker Notes] "` prefix to blockquote text within a slide | BE | [ ] | Helps RAG distinguish notes from body |
| 9.12.6 | Write unit test: PPTX with 3 slides (200, 300, 400 tokens) — verify 3 chunks, no merging across slides | TE | [ ] | |
| 9.12.7 | Write unit test: PPTX with 1 huge slide (2000 tokens) — verify split within slide at sentence boundaries, both chunks have same heading_context | TE | [ ] | |
| 9.12.8 | Write unit test: PPTX with slide containing speaker notes — verify notes prefixed with `"[Speaker Notes] "` | TE | [ ] | |

---

## 9.13 Canvas Oversized Element Fallback

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.13.1 | In `_split_cluster()`, after computing `elem_tokens`: if `elem_tokens > MAX_TOKENS`, call `_split_large_text(elem.text, heading_context)` and extend `chunks` with results, then `continue` | BE | [ ] | Skip normal accumulation |
| 9.13.2 | Ensure table elements in canvas containers are NOT subject to this fallback — they go through `_chunk_tiptap()` via fix 9.11, which exempts them from MAX_TOKENS | BE | [ ] | Only applies to plain text elements |
| 9.13.3 | Log info when oversized element is sub-split — element type, original token count, number of sub-chunks produced | BE | [ ] | |
| 9.13.4 | Write unit test: canvas with one text element of 5000 tokens — verify split into multiple chunks, each ≤ MAX_TOKENS | TE | [ ] | |
| 9.13.5 | Write unit test: canvas with one text element of 500 tokens — verify no split (below threshold) | TE | [ ] | Regression test |
| 9.13.6 | **CR2 Review**: Confirm `_split_large_text()` correctly handles canvas text (may lack sentence-ending punctuation). Does it fall back to newline splitting? | CR2 | [ ] | |

---

## 9.14 Imported Image Slide Context

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.14.1 | In `worker.py` `process_document_import()`, after Docling produces markdown: parse all `## Slide N: Title` headings into a `dict[int, str]` mapping `page_number → slide_title` | BE | [ ] | Regex: `r"^## Slide (\d+):\s*(.+)$"` |
| 9.14.2 | Pass the `slide_titles` dict to `process_imported_images()` as new parameter | BE | [ ] | Only for PPTX imports |
| 9.14.3 | Add `slide_titles: dict[int, str] | None = None` parameter to `process_imported_images()` | BE | [ ] | None for PDF/DOCX |
| 9.14.4 | In heading construction, look up slide title: if `slide_titles` is provided and `img.page_number in slide_titles`, use `f"Imported Image — Slide {page}: {title}"` | BE | [ ] | Falls back to `"Imported Image (page N)"` |
| 9.14.5 | Write unit test: PPTX import with image on slide 3 titled "Revenue" — verify chunk heading = `"Imported Image — Slide 3: Revenue"` | TE | [ ] | |
| 9.14.6 | Write unit test: PDF import with image on page 5 — verify heading = `"Imported Image (page 5)"` (no slide title for PDFs) | TE | [ ] | |
| 9.14.7 | Write unit test: PPTX import with image on slide that has no title — verify fallback heading = `"Imported Image (page N)"` | TE | [ ] | |

---

## 9.15 Generate AI Encryption Key

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.15.1 | Generate Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | BE | [ ] | Run once, store securely |
| 9.15.2 | Set `AI_ENCRYPTION_KEY=<generated-key>` in `.env` on all environments (dev, staging, prod) | BE | [ ] | Different key per environment |

---

## 9.16 Replace JWT Secret Placeholder

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.16.1 | Generate secure secret: `python -c "import secrets; print(secrets.token_urlsafe(64))"` | BE | [ ] | Run once per environment |
| 9.16.2 | Replace `JWT_SECRET=your-super-secret-key-change-in-production` with generated secret in `.env` on all environments | BE | [ ] | Existing tokens will be invalidated — users must re-login |

---

## 9.17 Fix is_developer Bug

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.17.1 | Remove debug `import logging as _log` block and `_log.getLogger(__name__).warning(...)` call from `require_developer()` in `ai_config.py` | BE | [ ] | Leftover from investigation |
| 9.17.2 | Add safety net in `require_developer()`: if `is_developer is None`, log warning, call `invalidate_user(current_user.id)`, raise `HTTPException(403)` | BE | [ ] | Handles stale cache from before field was added |
| 9.17.3 | Write unit test: user with `is_developer=None` — verify cache invalidated and 403 returned | TE | [ ] | |
| 9.17.4 | Verify fix by restarting server to clear stale in-memory cache entries | QE | [ ] | Full restart, not hot-reload |

---

## 9.18 Add Filtering to GET /models

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.18.1 | Add `provider_type: str | None = None` query param to `list_models()` in `ai_config.py` | BE | [ ] | |
| 9.18.2 | Add `capability: str | None = None` query param to `list_models()` in `ai_config.py` | BE | [ ] | |
| 9.18.3 | Add conditional `.where(AiModel.provider_type == provider_type)` and `.where(AiModel.capability == capability)` clauses when params are provided | BE | [ ] | |
| 9.18.4 | Write unit test: `GET /models?provider_type=openai` returns only OpenAI models | TE | [ ] | |
| 9.18.5 | Write unit test: `GET /models` with no filters returns all models (regression) | TE | [ ] | |

---

## 9.19 Add GET /capability/{capability} Endpoint

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.19.1 | Add `CapabilityConfigResponse` schema to `schemas/ai_config.py` — fields: `capability`, `provider_id`, `provider_type`, `model_id`, `model_display_name`, `has_api_key` | BE | [ ] | |
| 9.19.2 | Add `GET /capability/{capability}` endpoint to `routers/ai_config.py` with `require_developer` dependency | BE | [ ] | |
| 9.19.3 | Implement endpoint: query default model for capability (`is_default=True`, global scope), join provider for `has_api_key` | BE | [ ] | |
| 9.19.4 | Handle no-default case: return `CapabilityConfigResponse` with `None` fields | BE | [ ] | |
| 9.19.5 | Write unit test: `GET /capability/chat` with configured default — verify correct provider_type, model_id, has_api_key | TE | [ ] | |
| 9.19.6 | Write unit test: `GET /capability/chat` with no default model — verify null fields returned | TE | [ ] | |

---

## 9.20 Fix User Override Model Access

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.20.1 | Add `useAvailableModels(params?)` hook to `use-ai-config.ts` calling `GET /api/ai/config/models/available` (public, no developer auth) | FE | [ ] | Endpoint already exists at line 646 of ai_config.py |
| 9.20.2 | Support optional `provider_type` and `capability` filter params in `useAvailableModels` | FE | [ ] | Pass as query string |
| 9.20.3 | Update `user-chat-override.tsx` line 131: replace `useAiModels(...)` with `useAvailableModels({ provider_type, capability: 'chat' })` | FE | [ ] | Fixes 403 for non-developer users |
| 9.20.4 | Verify: non-developer user opens chat override popover — model dropdown loads without 403 | QE | [ ] | |

---

## 9.21 Wire AI Settings into App

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.21.1 | Add `AiSettingsPanel` import to `dashboard.tsx` (from `@/components/ai`) | FE | [ ] | May already be partially imported |
| 9.21.2 | Replace "coming soon" placeholder in settings case with `<AiSettingsPanel />` | FE | [ ] | Lines 940-950 of dashboard.tsx |
| 9.21.3 | Add fallback for non-developer users: `{!user?.is_developer && <p className="text-muted-foreground">No settings available</p>}` | FE | [ ] | AiSettingsPanel returns null for non-devs |
| 9.21.4 | Verify: developer navigates to Settings → sees 4-tab AI Settings panel; non-developer sees "No settings available" | QE | [ ] | |

---

## 9.22 Providers & Models Management Tab

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.22.1 | Create `providers-models-tab.tsx` with models table component | FE | [ ] | New file in `components/ai/` |
| 9.22.2 | Implement table columns: Model ID, Display Name, Provider, Capability, Embedding Dimensions, Default, Enabled, Actions | FE | [ ] | Use shadcn Table component |
| 9.22.3 | Add provider filter dropdown (All, OpenAI, Anthropic, Ollama) and capability filter dropdown (All, Chat, Embedding, Vision) | FE | [ ] | Filter client-side from useAiModels results |
| 9.22.4 | Create Add Model dialog — fields: Provider (Select from useAiProviders), Model ID, Display Name, Capability (Select), Embedding Dimensions (shown only when capability=embedding), Max Tokens, Default (Switch), Enabled (Switch) | FE | [ ] | `provider_type` auto-derived from selected provider |
| 9.22.5 | Create Edit Model dialog — reuse Add form, pre-populated from selected row | FE | [ ] | Uses `useUpdateAiModel()` |
| 9.22.6 | Create Delete Model confirmation — AlertDialog: "Delete model {display_name}? This cannot be undone." | FE | [ ] | Uses `useDeleteAiModel()` |
| 9.22.7 | Handle `is_default` toggling — when setting a model as default, backend should unset previous default for that capability | FE | [ ] | Verify backend handles this |
| 9.22.8 | Add 4th tab "Providers & Models" to `ai-settings-panel.tsx` rendering `<ProvidersModelsTab />` | FE | [ ] | |
| 9.22.9 | Export `ProvidersModelsTab` from `components/ai/index.ts` | FE | [ ] | |
| 9.22.10 | Verify: CRUD operations work — add model, edit display name, toggle default, delete model | QE | [ ] | |

---

## 9.23 Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.23.1 | **CR1 Review**: Agent tool counting (9.1) — verify `MAX_TOOL_CALLS` correctly stops both batched and sequential tool calls | CR1 | [ ] | |
| 9.23.2 | **CR1 Review**: Streaming timeouts (9.2, 9.3) — verify cleanup path releases all resources. No DB session leaks on timeout? | CR1 | [ ] | |
| 9.23.3 | **CR2 Review**: Import concurrency (9.5) — Redis counter race conditions? What if two workers INCR simultaneously at the limit boundary? | CR2 | [ ] | |
| 9.23.4 | **SA Review**: Manual sync endpoint (9.6.3) — can a user trigger mass sync across all documents they have access to? Is rate limit sufficient? | SA | [ ] | |
| 9.23.5 | **SA Review**: File streaming (9.9) — temp file permissions. Is the temp directory accessible to other processes? Should files be created with restricted mode? | SA | [ ] | |
| 9.23.6 | **CR2 Review**: Table chunking (9.10) — unbounded table chunk size. Should we at least warn (not block) when a table exceeds 6000 tokens (approaching embedding model limit)? | CR2 | [ ] | |
| 9.23.7 | **CR1 Review**: Canvas container parsing (9.11) — verify heading_context propagation through `_chunk_tiptap()` when called from canvas context | CR1 | [ ] | |
| 9.23.8 | **SA Review**: RAG embedding cache (9.8) — is the cache scoped to the user's session? Could one user's cached embedding leak to another user's session? | SA | [ ] | |
| 9.23.9 | **CR2 Review**: Nightly batch job (9.6.8) — what if the batch job runs for 4+ hours on a large backlog? Does it block other ARQ jobs? | CR2 | [ ] | |
| 9.23.10 | **DA Challenge**: Overall — with auto-embed removed (9.6), users must manually sync or wait for nightly. Is this acceptable UX? What if users forget to sync and get stale search results? | DA | [ ] | |
| 9.23.11 | **CR1 Review**: is_developer safety net (9.17) — verify cache invalidation doesn't cause secondary side effects. Is the log message sufficient for debugging? | CR1 | [ ] | |
| 9.23.12 | **CR2 Review**: Models management tab (9.22) — verify CRUD operations handle concurrent edits and race conditions on `is_default` toggling | CR2 | [ ] | |

---

## 9.24 Unit Tests

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.24.1 | Create `tests/test_agent_tool_limit.py` — tests for 9.1 (tool call counting) | TE | [ ] | |
| 9.24.2 | Create `tests/test_stream_timeout.py` — tests for 9.2 and 9.3 (streaming timeout + chunk limit) | TE | [ ] | |
| 9.24.3 | Create `tests/test_vision_timeout.py` — tests for 9.4 (vision API timeout) | TE | [ ] | |
| 9.24.4 | Create `tests/test_import_concurrency.py` — tests for 9.5 (global concurrency limit) | TE | [ ] | |
| 9.24.5 | Create `tests/test_manual_sync.py` — tests for 9.6 (manual sync endpoint, stale badge, nightly job) | TE | [ ] | |
| 9.24.6 | Create `tests/test_sql_app_timeout.py` — tests for 9.7 (asyncio backup timeout) | TE | [ ] | |
| 9.24.7 | Create `tests/test_rag_embedding_cache.py` — tests for 9.8 (query embedding cache) | TE | [ ] | |
| 9.24.8 | Create `tests/test_import_streaming.py` — tests for 9.9 (file streaming to disk) | TE | [ ] | |
| 9.24.9 | Create `tests/test_table_chunking.py` — tests for 9.10 (table boundary awareness) | TE | [ ] | |
| 9.24.10 | Create `tests/test_canvas_container_chunking.py` — tests for 9.11 (canvas TipTap parsing) | TE | [ ] | |
| 9.24.11 | Create `tests/test_slide_chunking.py` — tests for 9.12 (slide boundary enforcement) | TE | [ ] | |
| 9.24.12 | Create `tests/test_canvas_oversized.py` — tests for 9.13 (oversized element fallback) | TE | [ ] | |
| 9.24.13 | Create `tests/test_image_slide_context.py` — tests for 9.14 (imported image slide context) | TE | [ ] | |
| 9.24.14 | Create `tests/test_ai_config_filtering.py` — tests for 9.17-9.19 (is_developer fix, model filtering, capability GET endpoint) | TE | [ ] | |
| 9.24.15 | Run full test suite — verify all existing tests still pass (no regressions) | TE | [ ] | `pytest tests/ -v` |
| 9.24.16 | Verify coverage ≥ 80% for all modified files | TE | [ ] | `pytest --cov=app/ai --cov-report=term-missing` |
| 9.24.17 | **QE Review**: Test coverage — are edge cases covered? Missing scenarios? | QE | [ ] | |

---

## 9.25 Manual E2E Verification

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.25.1 | Agent chat: ask a complex question requiring 5+ tool calls — verify agent completes normally, doesn't hit limits prematurely | QE | [ ] | |
| 9.25.2 | Agent chat: trigger a slow query — verify streaming timeout doesn't fire for legitimate 60s responses | QE | [ ] | |
| 9.25.3 | Document import: upload 5 PDFs simultaneously from 2 users — verify concurrency limit allows 5, defers extras | QE | [ ] | |
| 9.25.4 | Document edit + sync: edit a document, verify yellow "Unsynced" badge appears. Click sync, verify badge turns green. | QE | [ ] | |
| 9.25.5 | Table embedding: create document with paragraph + table + paragraph. Sync. Use Blair to ask about table content — verify RAG retrieves the table chunk specifically. | QE | [ ] | Critical: validates table preamble improves retrieval |
| 9.25.6 | Canvas with table: create canvas, add container with table. Sync. Ask Blair about table data — verify retrieval works. | QE | [ ] | |
| 9.25.7 | PPTX import: import a 10-slide PPTX with tables and images. Ask Blair about specific slide content — verify slide-level retrieval. | QE | [ ] | |
| 9.25.8 | Nightly job: manually trigger `batch_embed_stale_documents` — verify stale documents get re-embedded and badges update | QE | [ ] | |
| 9.25.9 | Vision timeout: (if testable) disconnect vision provider mid-import — verify import completes with partial results, doesn't hang | QE | [ ] | |
| 9.25.10 | JWT secret change: after rotating JWT_SECRET, verify all existing sessions are invalidated and users must re-login | QE | [ ] | |
| 9.25.11 | AI Settings panel: developer navigates to Settings → sees 4-tab panel. Select per-capability config, save, refresh — verify settings persist via `GET /capability/{capability}`. | QE | [ ] | |
| 9.25.12 | User chat override: non-developer opens chat override popover — model dropdown loads. Save override, verify chat uses personal key. | QE | [ ] | |

---

## 9.26 Phase 9 Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 9.26.1 | All unit tests pass (`pytest tests/ -v`) | TE | [ ] | |
| 9.26.2 | All E2E verification scenarios pass | QE | [ ] | |
| 9.26.3 | All code reviews completed and findings addressed | CR1/CR2 | [ ] | |
| 9.26.4 | Security review completed — no new vulnerabilities introduced | SA | [ ] | |
| 9.26.5 | Phase 9 marked COMPLETE in task index | BE | [ ] | Update `tasks/index.md` |
