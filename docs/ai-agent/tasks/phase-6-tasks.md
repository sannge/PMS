# Phase 6: Document Import (Docling) + Image Understanding — Task Tracker

**Created**: 2026-02-24
**Last updated**: 2026-02-24
**Status**: NOT STARTED
**Spec**: [phase-6-document-import.md](../phase-6-document-import.md)

> **Depends on**: Phase 1 (LLM providers for vision), Phase 2 (embedding pipeline)
> **Parallel with**: Phase 3.1 (independent work)
> **Blocks**: Phase 4 (agent uses image understanding tool)

## Task Count Summary

| Section | Description | Tasks |
|---------|-------------|-------|
| 6.1 | Database — ImportJobs Migration | 12 |
| 6.2 | Database — SQLAlchemy Model | 9 |
| 6.3 | Docling Service — PDF Conversion | 8 |
| 6.4 | Docling Service — DOCX Conversion | 7 |
| 6.5 | Docling Service — PPTX Conversion | 7 |
| 6.6 | Docling Service — Image Extraction | 8 |
| 6.7 | Docling Service — Error Handling | 7 |
| 6.8 | Image Understanding Service — TipTap Image Processing | 10 |
| 6.9 | Image Understanding Service — Imported Image Processing | 8 |
| 6.10 | Image Understanding Service — Rate Limiting & Chunking | 6 |
| 6.11 | Import Router — File Upload Endpoint | 12 |
| 6.12 | Import Router — Status & Listing Endpoints | 9 |
| 6.13 | Import Background Worker — Pipeline | 12 |
| 6.14 | Import Background Worker — Progress & WebSocket | 10 |
| 6.15 | Import Dialog (Frontend) — Drop Zone & File Selection | 10 |
| 6.16 | Import Dialog (Frontend) — Form Fields & Progress | 12 |
| 6.17 | useDocumentImport Hook | 9 |
| 6.18 | Dependencies | 5 |
| 6.19 | Code Reviews & Security Analysis | 12 |
| 6.20 | Unit Tests — Docling Service | 11 |
| 6.21 | Unit Tests — Image Understanding | 8 |
| 6.22 | Integration Tests — Import Router | 13 |
| 6.23 | Manual Verification Scenarios | 10 |
| 6.24 | Phase 6 Sign-Off | 6 |
| **TOTAL** | | **221** |

## Team

| Role | Abbreviation |
|------|-------------|
| Frontend Engineer | **FE** |
| Backend Engineer | **BE** |
| Database Engineer | **DBE** |
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

## 6.1 Database — ImportJobs Migration

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.1.1 | Create Alembic migration file `alembic/versions/YYYYMMDD_add_import_jobs.py` with upgrade and downgrade functions | DBE | [ ] | |
| 6.1.2 | Add `id` column — UUID primary key with `default=uuid4` | DBE | [ ] | |
| 6.1.3 | Add `user_id` column — UUID, NOT NULL, FK referencing `Users.id` with ON DELETE CASCADE | DBE | [ ] | |
| 6.1.4 | Add `file_name` column — VARCHAR(500), NOT NULL | DBE | [ ] | |
| 6.1.5 | Add `file_type` column — VARCHAR(50), NOT NULL, CHECK constraint for values ("pdf", "docx", "pptx") | DBE | [ ] | |
| 6.1.6 | Add `file_size` column — BIGINT, NOT NULL; `status` column — VARCHAR(50), NOT NULL, DEFAULT "pending", CHECK constraint ("pending", "processing", "completed", "failed"); `progress_pct` column — INT, DEFAULT 0, CHECK 0-100 | DBE | [ ] | |
| 6.1.7 | Add `document_id` column — UUID, NULLABLE, FK referencing `Documents.id` with ON DELETE SET NULL; `scope` column — VARCHAR(20), NOT NULL; `scope_id` column — UUID, NOT NULL; `folder_id` column — UUID, NULLABLE | DBE | [ ] | |
| 6.1.8 | Add `error_message` column — TEXT, NULLABLE; `created_at` column — TIMESTAMPTZ, NOT NULL, server_default=now(); `completed_at` column — TIMESTAMPTZ, NULLABLE | DBE | [ ] | |
| 6.1.9 | Create index `idx_import_jobs_user` on `(user_id)` | DBE | [ ] | |
| 6.1.10 | Create index `idx_import_jobs_status` on `(status)` | DBE | [ ] | |
| 6.1.11 | Implement downgrade function — DROP TABLE `ImportJobs` with CASCADE, drop indexes | DBE | [ ] | |
| 6.1.12 | Run migration on dev DB — verify table exists, all columns correct, FK constraints enforced, indexes created; run downgrade and re-upgrade to confirm reversibility | DBE | [ ] | |

---

## 6.2 Database — SQLAlchemy Model

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.2.1 | Create `app/models/import_job.py` with `ImportJob` SQLAlchemy model class | DBE | [ ] | |
| 6.2.2 | Define all columns matching migration: id (UUID PK), user_id, file_name, file_type, file_size, status, progress_pct, document_id, scope, scope_id, folder_id, error_message, created_at, completed_at | DBE | [ ] | |
| 6.2.3 | Define `relationship("User")` back_populates on user_id FK | DBE | [ ] | |
| 6.2.4 | Define `relationship("Document")` on document_id FK (nullable) | DBE | [ ] | |
| 6.2.5 | Add column-level server defaults: `status="pending"`, `progress_pct=0`, `created_at=func.now()` | DBE | [ ] | |
| 6.2.6 | Register `ImportJob` in `app/models/__init__.py` | DBE | [ ] | |
| 6.2.7 | Create Pydantic schemas (`app/schemas/import_job.py`) — ImportJobCreate, ImportJobResponse, ImportJobListResponse with pagination | BE | [ ] | |
| 6.2.8 | **CR1 Review**: Model design — FK relationships, nullable fields, default values, relationship loading strategy (selectinload vs lazy) | CR1 | [ ] | |
| 6.2.9 | **DA Challenge**: Why a dedicated `ImportJobs` table instead of a generic `BackgroundJobs` table? What if we add CSV import later — another table or extend this one? | DA | [ ] | |

---

## 6.3 Docling Service — PDF Conversion

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.3.1 | Create `app/ai/docling_service.py` with `DoclingService` class, `__init__` instantiating `DocumentConverter` | BE | [ ] | |
| 6.3.2 | Define `ExtractedImage` and `ProcessResult` dataclasses with all fields (image_bytes, image_format, page_number, caption, position; markdown, images, metadata, warnings) | BE | [ ] | |
| 6.3.3 | Implement `convert_to_markdown()` for PDF — preserve headings (H1-H6 hierarchy from font sizes) | BE | [ ] | |
| 6.3.4 | Implement PDF table preservation — tables rendered as Markdown pipe tables with header rows | BE | [ ] | |
| 6.3.5 | Implement PDF list preservation — ordered and unordered lists converted to Markdown list syntax | BE | [ ] | |
| 6.3.6 | Implement PDF OCR path — detect scanned/image-based PDFs and apply OCR via Docling's built-in OCR pipeline | BE | [ ] | |
| 6.3.7 | Extract metadata from PDF — page_count, word_count, title_from_doc (from PDF metadata or first heading) | BE | [ ] | |
| 6.3.8 | **CR2 Review**: PDF conversion quality — do headings, tables, lists, OCR output match source fidelity? Edge cases (multi-column PDFs, rotated pages, scanned handwriting)? | CR2 | [ ] | |

---

## 6.4 Docling Service — DOCX Conversion

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.4.1 | Implement `convert_to_markdown()` for DOCX — preserve heading styles (Heading 1-6 mapped to Markdown `#`-`######`) | BE | [ ] | |
| 6.4.2 | Implement DOCX table preservation — tables with merged cells handled gracefully (unmerge or flatten) | BE | [ ] | |
| 6.4.3 | Implement DOCX list preservation — bullet lists, numbered lists, nested lists (indentation levels) | BE | [ ] | |
| 6.4.4 | Implement DOCX inline formatting — bold, italic, strikethrough, code spans mapped to Markdown syntax | BE | [ ] | |
| 6.4.5 | Implement DOCX hyperlink preservation — links converted to Markdown `[text](url)` syntax | BE | [ ] | |
| 6.4.6 | Extract metadata from DOCX — page_count (approximate from word count), word_count, title_from_doc (from document properties or first heading) | BE | [ ] | |
| 6.4.7 | **CR2 Review**: DOCX conversion — are Word-specific features (tracked changes, comments, headers/footers) handled or explicitly ignored? Are warnings generated for unsupported features? | CR2 | [ ] | |

---

## 6.5 Docling Service — PPTX Conversion

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.5.1 | Implement `convert_to_markdown()` for PPTX — each slide becomes a Markdown section with `## Slide N: {title}` heading | BE | [ ] | |
| 6.5.2 | Extract slide titles from PPTX title placeholders; fallback to "Slide N" if no title placeholder | BE | [ ] | |
| 6.5.3 | Convert slide body text (text frames, bullet points) to Markdown paragraphs and lists | BE | [ ] | |
| 6.5.4 | Convert PPTX tables to Markdown pipe tables | BE | [ ] | |
| 6.5.5 | Handle speaker notes — append as blockquote `> Note: ...` under each slide section | BE | [ ] | |
| 6.5.6 | Extract metadata from PPTX — slide_count (as page_count), word_count, title_from_doc (from first slide title or presentation properties) | BE | [ ] | |
| 6.5.7 | **CR2 Review**: PPTX conversion — are animations, transitions, SmartArt, embedded charts handled or warned? Does slide ordering match source? | CR2 | [ ] | |

---

## 6.6 Docling Service — Image Extraction

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.6.1 | Implement `extract_images()` for PDF — extract embedded raster images with page number and position index | BE | [ ] | |
| 6.6.2 | Implement `extract_images()` for DOCX — extract inline and floating images with position index | BE | [ ] | |
| 6.6.3 | Implement `extract_images()` for PPTX — extract slide images, background images, and shape images with slide number as page_number | BE | [ ] | |
| 6.6.4 | Normalize extracted image format — convert BMP/TIFF/WMF/EMF to PNG; preserve existing PNG/JPEG | BE | [ ] | |
| 6.6.5 | Extract image captions where available (alt text from DOCX/PPTX, figure captions from PDF) | BE | [ ] | |
| 6.6.6 | Maintain correct position ordering across all formats — images ordered by appearance in document | BE | [ ] | |
| 6.6.7 | Handle documents with zero images — return empty list, no errors | BE | [ ] | |
| 6.6.8 | **CR1 Review**: Image extraction — are all common image formats handled? What about SVG, vector graphics in PDFs? Memory usage for documents with many large images? | CR1 | [ ] | |

---

## 6.7 Docling Service — Error Handling

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.7.1 | Implement `process_file()` entry point — validate file_type is in ("pdf", "docx", "pptx"), raise `ImportError` with descriptive message for unsupported types | BE | [ ] | |
| 6.7.2 | Detect and reject password-protected PDFs — raise `ImportError("Password-protected PDF files are not supported")` | BE | [ ] | |
| 6.7.3 | Detect and handle corrupted files — catch Docling conversion exceptions, wrap in `ImportError` with original error details | BE | [ ] | |
| 6.7.4 | Implement large file handling (>50MB) — process with streaming/chunked reads where possible, accept optional progress callback for UI updates | BE | [ ] | |
| 6.7.5 | Populate `warnings` list in `ProcessResult` for non-fatal issues (e.g., "3 images could not be extracted", "OCR quality low on page 5") | BE | [ ] | |
| 6.7.6 | Ensure no file handles are leaked — wrap all file operations in context managers / try-finally | BE | [ ] | |
| 6.7.7 | **SA Review**: File processing security — can a crafted PDF cause arbitrary code execution via Docling? Are temp files written with restrictive permissions? Is path traversal possible via embedded filenames? | SA | [ ] | |

---

## 6.8 Image Understanding Service — TipTap Image Processing

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.8.1 | Create `app/ai/image_understanding_service.py` with `ImageUnderstandingService` class and `ImageDescription` dataclass | BE | [ ] | |
| 6.8.2 | Implement `__init__` accepting `ProviderRegistry`, `EmbeddingService`, `MinioService`, `AsyncSession` dependencies | BE | [ ] | |
| 6.8.3 | Implement TipTap JSON tree walker — recursively traverse `content` arrays, find nodes with `type="resizableImage"` and `attrs.attachmentId` | BE | [ ] | |
| 6.8.4 | For each found image node, extract `attachmentId`, `alt`, `title`, and `src` from `attrs` | BE | [ ] | |
| 6.8.5 | Download image bytes from MinIO using `attachment_id` — handle missing attachments gracefully (log warning, skip) | BE | [ ] | |
| 6.8.6 | Send image to `VisionProvider.describe_image()` with prompt: "Describe this image in detail. If it contains a diagram, flowchart, chart, or technical illustration, describe its structure, data, and key information." | BE | [ ] | |
| 6.8.7 | Create `ImageDescription` result with attachment_id, image_index, description text, and token_count | BE | [ ] | |
| 6.8.8 | Store descriptions as supplementary `DocumentChunk` records — `chunk_text = f"[Image: {caption}] {description}"`, `heading_context` = nearest heading ancestor in document tree | BE | [ ] | |
| 6.8.9 | Generate embedding vector for each image description chunk via `EmbeddingService` | BE | [ ] | |
| 6.8.10 | **CR1 Review**: TipTap JSON walking logic — does it handle deeply nested content (e.g., images inside table cells, blockquotes, list items)? What about canvas documents with different node structures? | CR1 | [ ] | |

---

## 6.9 Image Understanding Service — Imported Image Processing

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.9.1 | Implement `process_imported_images()` accepting `list[ExtractedImage]`, `document_id`, and `scope_ids` dict | BE | [ ] | |
| 6.9.2 | Upload each `ExtractedImage` to MinIO — generate unique object key, set content-type from image_format | BE | [ ] | |
| 6.9.3 | Create `Attachment` DB record for each uploaded image — link to document scope, store file_size, mime_type, original caption | BE | [ ] | |
| 6.9.4 | Send each uploaded image to `VisionProvider.describe_image()` with the same prompt as 6.8.6 | BE | [ ] | |
| 6.9.5 | Create `DocumentChunk` records for each image description — same format as 6.8.8 | BE | [ ] | |
| 6.9.6 | Generate embeddings for all image description chunks in a single batch call where possible | BE | [ ] | |
| 6.9.7 | Return list of `ImageDescription` with `attachment_id` populated from newly created attachments | BE | [ ] | |
| 6.9.8 | **CR2 Review**: Imported image pipeline — are MinIO uploads transactional with DB records? What happens if MinIO upload succeeds but DB insert fails (orphaned objects)? Cleanup strategy? | CR2 | [ ] | |

---

## 6.10 Image Understanding Service — Rate Limiting & Chunking

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.10.1 | Implement per-document image limit — process max 10 images per `process_document_images()` call; log warning if more exist, process first 10 by position order | BE | [ ] | |
| 6.10.2 | Implement small image filter — skip images < 10KB (likely icons, bullets, decorative elements); add to warnings list | BE | [ ] | |
| 6.10.3 | Implement per-image error isolation — if vision LLM fails on one image, log error, continue processing remaining images, include partial results | BE | [ ] | |
| 6.10.4 | Implement concurrency control — process images sequentially (not parallel) to avoid overwhelming vision API rate limits; make concurrency configurable for future tuning | BE | [ ] | |
| 6.10.5 | Add metrics logging — total images found, skipped (too small), processed, failed, total vision API latency | BE | [ ] | |
| 6.10.6 | **DA Challenge**: Is 10 images per document the right limit? What about a 200-page PDF with 50 figures? Should the limit scale with document size? What about image deduplication (same image referenced twice)? | DA | [ ] | |

---

## 6.11 Import Router — File Upload Endpoint

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.11.1 | Create `app/routers/ai_import.py` with FastAPI router, prefix `/api/ai/import` | BE | [ ] | |
| 6.11.2 | Implement `POST /` endpoint — accept `multipart/form-data` with fields: `file` (UploadFile), `scope` (str), `scope_id` (UUID), `folder_id` (Optional[UUID]), `title` (Optional[str]) | BE | [ ] | |
| 6.11.3 | Validate file extension — only `.pdf`, `.docx`, `.pptx` allowed; return 400 with specific error message for other types | BE | [ ] | |
| 6.11.4 | Validate MIME type — check `Content-Type` header matches expected: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.openxmlformats-officedocument.presentationml.presentation`; reject mismatches | BE | [ ] | |
| 6.11.5 | Validate file size — reject files > 50MB with 413 status and clear error message including the limit | BE | [ ] | |
| 6.11.6 | Validate `scope` value — must be one of "application", "project", "personal"; return 422 for invalid values | BE | [ ] | |
| 6.11.7 | Implement RBAC check — verify authenticated user has write access to target `scope_id` using existing `PermissionService`; return 403 if denied | BE | [ ] | |
| 6.11.8 | Save uploaded file to temp directory — use `tempfile.NamedTemporaryFile(delete=False)` with appropriate suffix matching file_type | BE | [ ] | |
| 6.11.9 | Create `ImportJob` DB record with status="pending", populate all fields from request, default title from filename (strip extension) if not provided | BE | [ ] | |
| 6.11.10 | Enqueue ARQ job `process_document_import` with `job_id` parameter; return 202 with `{job_id, status, file_name}` | BE | [ ] | |
| 6.11.11 | Mount `ai_import` router in `app/main.py` via `app.include_router(ai_import.router)` | BE | [ ] | |
| 6.11.12 | **SA Review**: File upload endpoint — path traversal via crafted filenames, zip bomb detection (malicious compressed content inside DOCX/PPTX which are ZIP archives), MIME type spoofing, temp file permissions, file descriptor exhaustion under high concurrency | SA | [ ] | |

---

## 6.12 Import Router — Status & Listing Endpoints

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.12.1 | Implement `GET /{job_id}` endpoint — return full `ImportJobResponse` with all fields (job_id, file_name, file_type, status, progress_pct, document_id, error_message, created_at, completed_at) | BE | [ ] | |
| 6.12.2 | Add authorization check on `GET /{job_id}` — only job owner can view; return 404 (not 403) for non-owners to avoid information leakage | BE | [ ] | |
| 6.12.3 | Handle non-existent job_id — return 404 with message "Import job not found" | BE | [ ] | |
| 6.12.4 | Implement `GET /jobs` endpoint — list authenticated user's import jobs, ordered by `created_at DESC` | BE | [ ] | |
| 6.12.5 | Add query params to `GET /jobs`: `status` (optional filter), `limit` (default 20, max 100), `offset` (default 0) | BE | [ ] | |
| 6.12.6 | Return paginated response with `total` count, `items` list, `limit`, `offset` | BE | [ ] | |
| 6.12.7 | Ensure `GET /jobs` only returns current user's jobs — filter by `user_id` from auth token, never expose other users' imports | BE | [ ] | |
| 6.12.8 | **CR1 Review**: Endpoint design — RESTful conventions, response shapes consistent with existing API patterns, appropriate HTTP status codes (200 for GET, 202 for POST, 404 for missing) | CR1 | [ ] | |
| 6.12.9 | **SA Review**: Authorization on status endpoints — can users enumerate job IDs? Is the 404-instead-of-403 pattern applied consistently? Are query params sanitized against SQL injection? | SA | [ ] | |

---

## 6.13 Import Background Worker — Pipeline

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.13.1 | Add `process_document_import` async function to `app/worker.py` accepting `ctx: dict` and `job_id: str` | BE | [ ] | |
| 6.13.2 | Load `ImportJob` from DB by `job_id`, set `status="processing"`, commit | BE | [ ] | |
| 6.13.3 | Read uploaded file from temp path stored in job record; verify file still exists, handle missing file gracefully | BE | [ ] | |
| 6.13.4 | Call `DoclingService.process_file()` — get `ProcessResult` with markdown, images, metadata, warnings | BE | [ ] | |
| 6.13.5 | Convert markdown to TipTap JSON format — implement `markdown_to_tiptap_json()` helper using appropriate library or manual conversion (headings, paragraphs, lists, tables, code blocks, blockquotes) | BE | [ ] | |
| 6.13.6 | Create `Document` record — set title (from job or metadata), content (TipTap JSON), scope, scope_id, folder_id, created_by=job.user_id | BE | [ ] | |
| 6.13.7 | Upload extracted images to MinIO via `ImageUnderstandingService.process_imported_images()` — get back attachment IDs | BE | [ ] | |
| 6.13.8 | Insert `resizableImage` nodes into TipTap JSON content at correct positions — map `ExtractedImage.position` to document position, set `attachmentId` in node attrs | BE | [ ] | |
| 6.13.9 | Update Document content with image-augmented TipTap JSON | BE | [ ] | |
| 6.13.10 | Trigger embedding pipeline — enqueue `embed_document_job` with `_defer_by=0` for immediate processing | BE | [ ] | |
| 6.13.11 | Finalize job — set `status="completed"`, `document_id=new_doc.id`, `progress_pct=100`, `completed_at=now()`, commit | BE | [ ] | |
| 6.13.12 | Register `process_document_import` in `WorkerSettings.functions` list alongside existing functions | BE | [ ] | |

---

## 6.14 Import Background Worker — Progress & WebSocket

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.14.1 | Implement progress update helper — `_update_progress(session, job_id, pct)` that updates `progress_pct` and commits | BE | [ ] | |
| 6.14.2 | Set progress 10% after status="processing" set (conversion started) | BE | [ ] | |
| 6.14.3 | Set progress 40% after `DoclingService.process_file()` returns (conversion complete) | BE | [ ] | |
| 6.14.4 | Set progress 50% after `Document` created in DB (document created) | BE | [ ] | |
| 6.14.5 | Set progress 60% after images uploaded to MinIO and inserted into TipTap JSON (images uploaded) | BE | [ ] | |
| 6.14.6 | Set progress 80% after vision LLM descriptions generated (images processed) | BE | [ ] | |
| 6.14.7 | Set progress 90% after `embed_document_job` enqueued (embedding queued) | BE | [ ] | |
| 6.14.8 | Broadcast `IMPORT_COMPLETED` WebSocket event to user on success — payload: `{type: "IMPORT_COMPLETED", job_id, document_id, title}` | BE | [ ] | |
| 6.14.9 | Implement error handling wrapper — any exception sets `status="failed"`, `error_message=str(error)`, cleans up temp file, broadcasts `IMPORT_FAILED` WebSocket event to user with `{type: "IMPORT_FAILED", job_id, error_message}` | BE | [ ] | |
| 6.14.10 | Ensure temp file cleanup in all code paths — success, failure, and unexpected exceptions (use try/finally) | BE | [ ] | |

---

## 6.15 Import Dialog (Frontend) — Drop Zone & File Selection

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.15.1 | Create `electron-app/src/renderer/components/ai/import-dialog.tsx` with Radix Dialog wrapper, trigger button, and dialog content layout | FE | [ ] | |
| 6.15.2 | Implement drop zone using HTML5 drag-and-drop API — `onDragEnter`, `onDragOver`, `onDragLeave`, `onDrop` handlers on a styled div | FE | [ ] | |
| 6.15.3 | Implement drag-over visual feedback — border color change, background highlight, icon animation when file is dragged over drop zone | FE | [ ] | |
| 6.15.4 | Implement file picker fallback — hidden `<input type="file" accept=".pdf,.docx,.pptx">` triggered by click on drop zone | FE | [ ] | |
| 6.15.5 | Client-side file type validation — check file extension is .pdf, .docx, or .pptx; show inline error "Unsupported file type. Please upload PDF, DOCX, or PPTX." for invalid files | FE | [ ] | |
| 6.15.6 | Client-side file size validation — check `file.size <= 50 * 1024 * 1024`; show inline error "File is too large. Maximum size is 50MB." for oversized files | FE | [ ] | |
| 6.15.7 | Display selected file info after drop/selection — file name, file size (human-readable: KB/MB), file type icon | FE | [ ] | |
| 6.15.8 | Implement "remove file" action — clear selected file, return to drop zone state | FE | [ ] | |
| 6.15.9 | Prevent default browser behavior for drag events — `e.preventDefault()` on dragover/drop to stop browser from opening the file | FE | [ ] | |
| 6.15.10 | **CR1 Review**: Drop zone UX — does it work on all platforms (Windows/Mac/Linux)? Accessible via keyboard? Screen reader announcements for file selection state? | CR1 | [ ] | |

---

## 6.16 Import Dialog (Frontend) — Form Fields & Progress

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.16.1 | Implement title input field — auto-fill from filename (strip extension, replace hyphens/underscores with spaces), editable by user | FE | [ ] | |
| 6.16.2 | Implement scope selector — dropdown with options "Application", "Project", "Personal"; reuse existing scope selection patterns from knowledge tree | FE | [ ] | |
| 6.16.3 | Implement conditional scope-ID selector — show Application picker when scope="application", Project picker when scope="project"; hide for "personal" | FE | [ ] | |
| 6.16.4 | Implement folder selector — show folder tree/dropdown for selected scope; allow "Root" (no folder) option | FE | [ ] | |
| 6.16.5 | Implement Import button — disabled until file selected, scope chosen, and scope_id set (if applicable); calls `useImportDocument` mutation | FE | [ ] | |
| 6.16.6 | Implement Cancel button — closes dialog, clears form state; if upload in progress, show confirmation "Import is in progress. Close anyway?" | FE | [ ] | |
| 6.16.7 | Transition to progress view after upload — replace form with progress display showing file name in header | FE | [ ] | |
| 6.16.8 | Implement progress bar — animated bar reflecting `progress_pct` from polling; TailwindCSS styled with transition animation | FE | [ ] | |
| 6.16.9 | Implement step indicators — list of steps (File uploaded, Converting to markdown, Processing images, Creating document, Generating embeddings) with checkmark for completed, spinner for current, empty circle for pending | FE | [ ] | Map progress_pct ranges to steps: 0-10%=upload, 10-40%=converting, 40-60%=images, 60-80%=creating, 80-100%=embedding |
| 6.16.10 | Implement success state — show success message with document title, "Open Document" button that navigates to new document via state-based routing, auto-close dialog after 3 seconds | FE | [ ] | |
| 6.16.11 | Implement failure state — show error message from `error_message` field, "Try Again" button that resets to form view, "Close" button | FE | [ ] | |
| 6.16.12 | **CR2 Review**: Form UX — field validation messages clear? Loading states prevent double submission? Dialog closeable at every stage? Focus management correct (focus trap inside dialog)? | CR2 | [ ] | |

---

## 6.17 useDocumentImport Hook

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.17.1 | Create `electron-app/src/renderer/hooks/use-document-import.ts` | FE | [ ] | |
| 6.17.2 | Implement `useImportDocument()` mutation — `POST /api/ai/import` with `multipart/form-data` body; construct `FormData` with file, scope, scope_id, folder_id, title fields | FE | [ ] | |
| 6.17.3 | Handle mutation success — extract `job_id` from response, trigger `useImportJobStatus` polling | FE | [ ] | |
| 6.17.4 | Handle mutation error — network errors, 400 (validation), 403 (permission), 413 (file too large); map to user-friendly error messages | FE | [ ] | |
| 6.17.5 | Implement `useImportJobStatus(jobId)` query — `GET /api/ai/import/{jobId}`; `refetchInterval: (data) => data?.status in ["pending", "processing"] ? 2000 : false` for conditional polling | FE | [ ] | |
| 6.17.6 | Stop polling when status is "completed" or "failed" — return final state to component | FE | [ ] | |
| 6.17.7 | Implement `useImportJobs()` query — `GET /api/ai/import/jobs` with optional `status` filter; invalidate on new import start | FE | [ ] | |
| 6.17.8 | Listen for `IMPORT_COMPLETED` and `IMPORT_FAILED` WebSocket events in `use-websocket-cache.ts` — invalidate import job queries, provide instant completion notification alongside polling | FE | [ ] | |
| 6.17.9 | **CR1 Review**: Hook design — are query keys properly scoped? Does polling cleanup on component unmount? Are there race conditions between polling and WebSocket events? Memory leak potential from abandoned polls? | CR1 | [ ] | |

---

## 6.18 Dependencies

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.18.1 | Add `docling>=2.0.0` to `fastapi-backend/requirements.txt` | BE | [ ] | |
| 6.18.2 | Run `pip install -r requirements.txt` — verify Docling installs with all sub-dependencies (including OCR components) | BE | [ ] | |
| 6.18.3 | Verify no version conflicts between Docling and existing dependencies (especially numpy, Pillow, pydantic) | BE | [ ] | |
| 6.18.4 | Test Docling import in Python REPL — `from docling.document_converter import DocumentConverter` succeeds without error | BE | [ ] | |
| 6.18.5 | **DA Challenge**: Docling is a relatively new library — what is its maintenance status? Are there alternatives (pymupdf, python-docx, python-pptx) that are more mature? What is the fallback plan if Docling has a critical bug? | DA | [ ] | |

---

## 6.19 Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.19.1 | **CR1 Review**: Full code review of `docling_service.py` — code quality, error handling, type hints, docstrings | CR1 | [ ] | |
| 6.19.2 | **CR2 Review**: Full code review of `image_understanding_service.py` — code quality, error handling, type hints, docstrings | CR2 | [ ] | |
| 6.19.3 | **CR1 Review**: Full code review of `ai_import.py` router — endpoint design, validation, error responses, auth patterns | CR1 | [ ] | |
| 6.19.4 | **CR2 Review**: Full code review of `worker.py` changes — pipeline logic, error handling, cleanup, progress tracking | CR2 | [ ] | |
| 6.19.5 | **CR1 Review**: Full code review of `import-dialog.tsx` — component structure, accessibility, state management | CR1 | [ ] | |
| 6.19.6 | **CR2 Review**: Full code review of `use-document-import.ts` — hook patterns, query configuration, error handling | CR2 | [ ] | |
| 6.19.7 | **SA Review**: File upload security — validate that crafted filenames cannot cause path traversal (`../../etc/passwd`), sanitize filename before writing to temp | SA | [ ] | |
| 6.19.8 | **SA Review**: Zip bomb protection — DOCX and PPTX are ZIP archives; verify Docling or pre-processing detects decompression bombs (ratio > 100:1 or expanded size > 1GB) | SA | [ ] | |
| 6.19.9 | **SA Review**: Malicious macro detection — verify DOCX/PPTX macros are not executed during conversion; Docling should parse content only, not execute embedded code | SA | [ ] | |
| 6.19.10 | **SA Review**: MIME type validation — verify both `Content-Type` header and file magic bytes are checked; reject files where extension and magic bytes disagree | SA | [ ] | |
| 6.19.11 | **SA Review**: SSRF via image URLs — if TipTap content contains image nodes with external `src` URLs, verify the service does not fetch arbitrary URLs (only MinIO attachments via `attachmentId`) | SA | [ ] | |
| 6.19.12 | **SA Review**: Temp file security — verify temp files are created with restrictive permissions (0600), stored in OS temp directory (not web-accessible), and cleaned up within bounded time even if worker crashes | SA | [ ] | |

---

## 6.20 Unit Tests — Docling Service

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.20.1 | Create `fastapi-backend/tests/test_docling_service.py` with test fixtures — small sample PDF, DOCX, PPTX files (< 100KB each, committed to `tests/fixtures/`) | TE | [ ] | |
| 6.20.2 | `test_convert_pdf_to_markdown` — verify headings, paragraphs, lists preserved in output markdown | TE | [ ] | |
| 6.20.3 | `test_convert_pdf_tables_to_markdown` — verify PDF tables rendered as Markdown pipe tables with correct columns/rows | TE | [ ] | |
| 6.20.4 | `test_convert_docx_to_markdown` — verify DOCX headings, bold/italic, lists, hyperlinks in output markdown | TE | [ ] | |
| 6.20.5 | `test_convert_docx_tables_to_markdown` — verify DOCX tables with merged cells handled gracefully | TE | [ ] | |
| 6.20.6 | `test_convert_pptx_to_markdown` — verify each slide is a section, titles extracted, body text preserved | TE | [ ] | |
| 6.20.7 | `test_extract_images_from_pdf` — verify images extracted with correct format, page_number, position ordering | TE | [ ] | |
| 6.20.8 | `test_extract_images_from_docx` — verify inline images extracted with position ordering | TE | [ ] | |
| 6.20.9 | `test_process_file_returns_complete_result` — verify `ProcessResult` has all fields populated (markdown, images, metadata, warnings) | TE | [ ] | |
| 6.20.10 | `test_corrupted_file_raises_import_error` — pass a truncated/invalid file, verify `ImportError` raised with descriptive message | TE | [ ] | |
| 6.20.11 | `test_password_protected_pdf_raises_import_error` — pass a password-protected PDF, verify `ImportError("Password-protected")` raised | TE | [ ] | |

---

## 6.21 Unit Tests — Image Understanding

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.21.1 | Create `fastapi-backend/tests/test_image_understanding.py` with mocked `ProviderRegistry`, `EmbeddingService`, `MinioService`, `AsyncSession` | TE | [ ] | |
| 6.21.2 | `test_extract_image_nodes_from_tiptap` — pass TipTap JSON with 3 `resizableImage` nodes, verify all 3 detected with correct `attachmentId` and position | TE | [ ] | |
| 6.21.3 | `test_process_document_images_creates_chunks` — verify `DocumentChunk` records created with `chunk_text` format `[Image: {caption}] {description}` and embeddings generated | TE | [ ] | |
| 6.21.4 | `test_process_document_images_skips_small_images` — include a < 10KB image, verify it is skipped and a warning logged | TE | [ ] | |
| 6.21.5 | `test_process_document_images_limits_to_10` — pass TipTap JSON with 15 images, verify only first 10 processed | TE | [ ] | |
| 6.21.6 | `test_process_imported_images_uploads_to_minio` — verify each `ExtractedImage` results in a MinIO upload and `Attachment` record | TE | [ ] | |
| 6.21.7 | `test_vision_provider_error_continues_batch` — mock vision provider to fail on image #2 of 5, verify images #1, #3, #4, #5 still processed successfully | TE | [ ] | |
| 6.21.8 | `test_image_descriptions_are_embedded` — verify `EmbeddingService` called for each image description chunk, embedding vectors stored in `DocumentChunk` | TE | [ ] | |

---

## 6.22 Integration Tests — Import Router

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.22.1 | Create `fastapi-backend/tests/test_import_router.py` with test fixtures, authenticated test client, test database | TE | [ ] | |
| 6.22.2 | `test_upload_pdf_creates_job` — POST multipart with valid PDF, verify 202 response with `job_id`, `status="pending"`, `file_name` | TE | [ ] | |
| 6.22.3 | `test_upload_docx_creates_job` — POST multipart with valid DOCX, verify 202 response | TE | [ ] | |
| 6.22.4 | `test_upload_pptx_creates_job` — POST multipart with valid PPTX, verify 202 response | TE | [ ] | |
| 6.22.5 | `test_upload_invalid_type_rejected` — POST with .txt file, verify 400 response with error message about supported types | TE | [ ] | |
| 6.22.6 | `test_upload_mime_type_mismatch_rejected` — POST with .pdf extension but wrong MIME type (e.g., text/plain), verify 400 response | TE | [ ] | |
| 6.22.7 | `test_upload_too_large_rejected` — POST with file > 50MB (mock or generate), verify 413 response with size limit message | TE | [ ] | |
| 6.22.8 | `test_upload_requires_scope_access` — POST with scope_id user has no write access to, verify 403 response | TE | [ ] | |
| 6.22.9 | `test_get_job_status_returns_progress` — create job, update progress to 45%, GET status, verify response contains `progress_pct=45` | TE | [ ] | |
| 6.22.10 | `test_get_job_status_unauthorized` — GET status for job owned by different user, verify 404 response (not 403) | TE | [ ] | |
| 6.22.11 | `test_list_jobs_returns_user_jobs_only` — create jobs for 2 users, GET /jobs for user A, verify only user A's jobs returned | TE | [ ] | |
| 6.22.12 | `test_import_job_creates_document` — run full pipeline (mock Docling), verify Document created with correct scope, folder, title, content | TE | [ ] | |
| 6.22.13 | `test_import_job_cleans_temp_file` — run pipeline, verify temp file deleted on both success and failure paths | TE | [ ] | |

---

## 6.23 Manual Verification Scenarios

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.23.1 | **MV-1**: Upload a PDF via import dialog — verify job created, progress polling starts, progress bar animates | QE | [ ] | |
| 6.23.2 | **MV-2**: Watch processing status update (10% -> 40% -> 60% -> 80% -> 100%) — verify each step visible in progress UI with correct step indicators | QE | [ ] | |
| 6.23.3 | **MV-3**: On completion — verify document appears in knowledge tree at specified folder, content is clean markdown, success notification shows, "Open Document" navigates correctly | QE | [ ] | |
| 6.23.4 | **MV-4**: Check document content in editor — verify formatting preserved (headings, tables, lists), images from PDF stored as attachments and visible inline | QE | [ ] | |
| 6.23.5 | **MV-5**: Verify image understanding — check DocumentChunks include image description chunks, descriptions are meaningful (not generic placeholder text) | QE | [ ] | |
| 6.23.6 | **MV-6**: Ask AI: "Summarize the document I just imported" — verify returns accurate summary based on embedded chunks (requires Phase 4 agent) | QE | [ ] | Blocked until Phase 4 |
| 6.23.7 | **MV-7**: Upload a DOCX with tables and images — verify tables preserved in markdown, images extracted and described | QE | [ ] | |
| 6.23.8 | **MV-8**: Upload a PPTX with multiple slides — verify each slide becomes a section, slide images processed | QE | [ ] | |
| 6.23.9 | **MV-9**: Try uploading unsupported file (.txt, .csv, .zip) — verify rejected with clear error message before upload starts | QE | [ ] | |
| 6.23.10 | **MV-10**: Try uploading > 50MB file — verify rejected with size limit error before upload starts (client-side validation) | QE | [ ] | |

---

## 6.24 Phase 6 Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 6.24.1 | All unit tests pass: `pytest tests/test_docling_service.py tests/test_image_understanding.py -v` | QE | [ ] | |
| 6.24.2 | All integration tests pass: `pytest tests/test_import_router.py -v` | QE | [ ] | |
| 6.24.3 | Ruff lint clean: `ruff check app/ai/docling_service.py app/ai/image_understanding_service.py app/routers/ai_import.py app/models/import_job.py` | QE | [ ] | |
| 6.24.4 | Frontend lint clean: `npm run lint` and `npm run typecheck` pass with zero warnings for new files | QE | [ ] | |
| 6.24.5 | **DA Final Challenge**: What happens if Docling library is abandoned? What is the cost of vision API calls at scale (1000 imports/day, 10 images each)? Is the 50MB limit too generous or too restrictive? What about import of encrypted/DRM-protected documents? | DA | [ ] | |
| 6.24.6 | Phase 6 APPROVED — all reviewers (CR1, CR2, SA, QE, DA) sign off | ALL | [ ] | |
