# Phase 6: Document Import (Docling) + Image Understanding

**Goal**: Import PDF/DOCX/PPTX into knowledge base. Process embedded images for RAG.

**Depends on**: Phase 1 (LLM providers for vision), Phase 2 (embedding pipeline)
**Parallel with**: Phase 3.1 (independent work)
**Blocks**: Phase 4 (agent uses image understanding tool)

---

## Task 6.1: Import Job Table Migration

### New File: `fastapi-backend/alembic/versions/YYYYMMDD_add_import_jobs.py`

### `ImportJobs` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | `default=uuid4` |
| user_id | UUID FK -> Users.id | Who initiated the import |
| file_name | VARCHAR(500) | Original filename |
| file_type | VARCHAR(50) | "pdf", "docx", "pptx" |
| file_size | BIGINT | Bytes |
| status | VARCHAR(50) | "pending", "processing", "completed", "failed" |
| progress_pct | INT DEFAULT 0 | 0-100 |
| document_id | UUID FK -> Documents.id NULL | Set on successful completion |
| scope | VARCHAR(20) | "application", "project", "personal" |
| scope_id | UUID | Application/project/user UUID |
| folder_id | UUID NULL | Target folder UUID |
| error_message | TEXT NULL | Set on failure |
| created_at | TIMESTAMP | |
| completed_at | TIMESTAMP NULL | |

### Indexes

```sql
CREATE INDEX idx_import_jobs_user ON "ImportJobs" (user_id);
CREATE INDEX idx_import_jobs_status ON "ImportJobs" (status);
```

### Acceptance Criteria
- [ ] Migration creates `ImportJobs` table
- [ ] FKs to Users and Documents tables
- [ ] Downgrade drops the table
- [ ] Indexes created for user and status

---

## Task 6.2: Docling Service

### New File: `fastapi-backend/app/ai/docling_service.py`

```python
from docling.document_converter import DocumentConverter

@dataclass
class ExtractedImage:
    image_bytes: bytes
    image_format: str        # "png", "jpg"
    page_number: int | None  # Source page
    caption: str | None      # If available from document
    position: int            # Order in document

@dataclass
class ProcessResult:
    markdown: str                      # Full document as clean markdown
    images: list[ExtractedImage]       # Extracted embedded images
    metadata: dict                     # {page_count, word_count, title_from_doc}
    warnings: list[str]                # Non-fatal issues

class DoclingService:
    """
    Document conversion service using Docling library.
    Converts PDF, DOCX, PPTX to clean markdown with image extraction.
    """

    def __init__(self):
        self.converter = DocumentConverter()

    async def convert_to_markdown(
        self,
        file_path: str
    ) -> str:
        """
        Convert a document file to clean Markdown.

        Handles:
        - PDF: OCR if needed, preserves tables, headings, lists
        - DOCX: Preserves formatting, tables, headings, lists
        - PPTX: Each slide becomes a section with slide title as heading

        Returns clean markdown string.
        """

    async def extract_images(
        self,
        file_path: str
    ) -> list[ExtractedImage]:
        """
        Extract embedded images from the document.

        Returns list of images with:
        - Raw bytes (for upload to MinIO)
        - Format (png/jpg)
        - Source page number
        - Caption (if present in document)
        - Position index for ordering
        """

    async def process_file(
        self,
        file_path: str,
        file_type: str
    ) -> ProcessResult:
        """
        Full processing pipeline:
        1. Validate file type (pdf, docx, pptx)
        2. Convert to markdown
        3. Extract images
        4. Extract metadata (page count, word count, etc.)
        5. Return ProcessResult with all outputs

        Error handling:
        - Corrupted files → raise ImportError with details
        - Password-protected PDFs → raise ImportError("Password-protected")
        - Large files (>50MB) → process with progress callback
        """
```

### Acceptance Criteria
- [ ] PDF → markdown conversion preserves headings, tables, lists
- [ ] DOCX → markdown conversion preserves formatting
- [ ] PPTX → markdown with slides as sections
- [ ] Images extracted with correct format and ordering
- [ ] Corrupted files raise clear errors
- [ ] Password-protected PDFs detected and rejected
- [ ] Large files don't cause memory issues (streaming where possible)

---

## Task 6.3: Image Understanding Service

### New File: `fastapi-backend/app/ai/image_understanding_service.py`

```python
@dataclass
class ImageDescription:
    attachment_id: UUID | None   # If from existing attachment
    image_index: int             # Position in document
    description: str             # Vision LLM output
    token_count: int             # For embedding

class ImageUnderstandingService:
    """
    Processes images through vision LLM to generate text descriptions.
    Descriptions are stored as supplementary DocumentChunks for RAG.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        embedding_service: EmbeddingService,
        minio_service: MinioService,
        db: AsyncSession
    ):
        ...

    async def process_document_images(
        self,
        document_id: UUID,
        content_json: dict
    ) -> list[ImageDescription]:
        """
        Process images already embedded in a TipTap document.

        1. Walk TipTap JSON content tree
        2. Find nodes with type='resizableImage' and attachmentId attribute
           (see editor-extensions.tsx for the image node schema)
        3. For each image:
           a. Download from MinIO using attachment_id
           b. Send to VisionProvider.describe_image() with prompt:
              "Describe this image in detail. If it contains a diagram,
               flowchart, chart, or technical illustration, describe its
               structure, data, and key information."
           c. Create an ImageDescription
        4. Store descriptions as supplementary DocumentChunks:
           - chunk_text = f"[Image: {caption}] {description}"
           - heading_context = nearest heading in document
           - Generate embedding for the description
        5. Optionally feed descriptions to Graphiti as supplementary episodes
        6. Return list of ImageDescription

        Rate limiting: Process max 10 images per document.
        Skip images < 10KB (likely icons/bullets, not meaningful).
        """

    async def process_imported_images(
        self,
        images: list[ExtractedImage],
        document_id: UUID,
        scope_ids: dict
    ) -> list[ImageDescription]:
        """
        Process images extracted by Docling from imported documents.

        1. Upload each image to MinIO as Attachment
        2. Send to VisionProvider for description
        3. Create DocumentChunks with descriptions
        4. Return ImageDescription list
        """
```

### TipTap Image Node Structure

Reference from existing `editor-extensions.tsx`:
```json
{
  "type": "resizableImage",
  "attrs": {
    "src": "...",
    "attachmentId": "uuid-here",
    "alt": "...",
    "title": "...",
    "width": 500
  }
}
```

### Acceptance Criteria
- [ ] Extracts image attachments from TipTap JSON correctly
- [ ] Downloads images from MinIO
- [ ] Sends to vision LLM with appropriate prompt
- [ ] Creates supplementary DocumentChunks with descriptions
- [ ] Descriptions are embedded (have vector embeddings)
- [ ] Small images (<10KB) skipped
- [ ] Max 10 images per document (rate limiting)
- [ ] Imported images uploaded to MinIO as attachments
- [ ] Error in one image doesn't fail entire batch

---

## Task 6.4: Import Router

### New File: `fastapi-backend/app/routers/ai_import.py`

**Prefix**: `/api/ai/import`

### Endpoints

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/` | POST | Upload file, create import job | Authenticated user with write access to target scope |
| `/{job_id}` | GET | Get import job status | Job owner |
| `/jobs` | GET | List user's import jobs | Authenticated user |

### `POST /` — Upload and Import

**Request**: `multipart/form-data`
- `file`: The uploaded file (PDF/DOCX/PPTX)
- `scope`: "application", "project", or "personal"
- `scope_id`: UUID of target scope
- `folder_id`: Optional target folder UUID
- `title`: Optional override title (defaults to filename)

**Validation**:
- File type: Only `.pdf`, `.docx`, `.pptx` (check both extension and MIME type)
- File size: Max 50MB
- RBAC: User must have write access to target scope

**Flow**:
1. Validate file type and size
2. Validate user's write access to target scope
3. Save file to temp location (not MinIO — temp processing only)
4. Create `ImportJob` record with status="pending"
5. Enqueue ARQ job: `process_document_import`
6. Return immediately:
   ```json
   {
     "job_id": "uuid",
     "status": "pending",
     "file_name": "report.pdf"
   }
   ```

### `GET /{job_id}` — Job Status

```json
{
  "job_id": "uuid",
  "file_name": "report.pdf",
  "file_type": "pdf",
  "status": "processing",
  "progress_pct": 45,
  "document_id": null,
  "error_message": null,
  "created_at": "2026-02-20T10:00:00Z",
  "completed_at": null
}
```

### `GET /jobs` — List Jobs

Query params: `status` (optional filter), `limit` (default 20), `offset` (default 0)

Returns paginated list of user's import jobs, most recent first.

### Modify: `fastapi-backend/app/main.py`

Mount the router:
```python
from app.routers import ai_import
app.include_router(ai_import.router)
```

### Acceptance Criteria
- [ ] File upload accepts PDF/DOCX/PPTX only
- [ ] File size limited to 50MB
- [ ] MIME type validated (not just extension)
- [ ] Import job created and returned immediately (async processing)
- [ ] Job status endpoint returns current progress
- [ ] Jobs list filtered by authenticated user
- [ ] RBAC checked for target scope
- [ ] Router mounted in main.py

---

## Task 6.5: Import Background Worker

### Modify: `fastapi-backend/app/worker.py`

Add import processing job:

```python
async def process_document_import(ctx: dict, job_id: str) -> dict:
    """
    Background job to process a document import.

    1. Load ImportJob from DB, set status="processing"
    2. Read file from temp location
    3. Convert via DoclingService.process_file():
       a. Update progress: 10% (conversion started)
       b. Get markdown content and extracted images
       c. Update progress: 40% (conversion complete)
    4. Create Document:
       a. Convert markdown to TipTap JSON (for editor compatibility)
       b. Set scope, scope_id, folder_id from job
       c. Update progress: 50% (document created)
    5. Upload extracted images to MinIO as Attachments:
       a. Insert image references into TipTap JSON content
       b. Update progress: 60% (images uploaded)
    6. Process images through vision LLM:
       a. Get descriptions for each image
       b. Update progress: 80% (images processed)
    7. Trigger embedding pipeline:
       a. Enqueue embed_document_job with _defer_by=0 (immediate)
       b. Update progress: 90% (embedding queued)
    8. Finalize:
       a. Set status="completed", document_id=new_doc.id
       b. Set progress_pct=100, completed_at=now()
       c. Clean up temp file
       d. Update progress: 100% (complete)
    9. WebSocket broadcast IMPORT_COMPLETED to user:
       {type: "IMPORT_COMPLETED", job_id, document_id, title}

    Error handling:
    - Any step failure → set status="failed", error_message=str(error)
    - Clean up temp file on failure
    - WebSocket broadcast IMPORT_FAILED to user
    - Return {status: "failed", error: str}
    """
```

Add to `WorkerSettings.functions`:
```python
functions = [
    ...,  # existing functions
    embed_document_job,           # From Phase 2
    process_document_import,      # New
]
```

### Acceptance Criteria
- [ ] Import job processes file end-to-end
- [ ] Progress updates visible via status endpoint
- [ ] Document created with correct scope and folder
- [ ] Images uploaded to MinIO and embedded in document
- [ ] Vision LLM descriptions generated for images
- [ ] Embedding pipeline triggered for new document
- [ ] WebSocket notification sent on completion/failure
- [ ] Temp file cleaned up in all cases (success and failure)
- [ ] Failed jobs have error_message set

---

## Task 6.6: Import UI

### New File: `electron-app/src/renderer/components/ai/import-dialog.tsx`

```tsx
/**
 * Document import dialog.
 * Allows users to upload PDF/DOCX/PPTX files for import into knowledge base.
 *
 * Uses Radix Dialog component.
 *
 * Layout:
 * ┌─────────────────────────────────────────────┐
 * │ Import Document                          [X] │
 * ├─────────────────────────────────────────────┤
 * │                                             │
 * │  ┌─────────────────────────────────────┐    │
 * │  │                                     │    │
 * │  │   📄 Drop file here or click to     │    │  ← Drop zone
 * │  │      browse                         │    │
 * │  │                                     │    │
 * │  │   Supports: PDF, DOCX, PPTX        │    │
 * │  │   Max size: 50MB                    │    │
 * │  │                                     │    │
 * │  └─────────────────────────────────────┘    │
 * │                                             │
 * │  Title: [Auto-filled from filename    ]     │  ← Editable title
 * │                                             │
 * │  Scope: [Application ▼]                     │  ← Scope selector
 * │  Application: [Engineering ▼]               │  ← Conditional on scope
 * │  Folder: [/ API Docs ▼]                     │  ← Folder picker
 * │                                             │
 * │              [Cancel]  [Import]             │
 * └─────────────────────────────────────────────┘
 *
 * After upload:
 * ┌─────────────────────────────────────────────┐
 * │ Importing: report.pdf                       │
 * ├─────────────────────────────────────────────┤
 * │                                             │
 * │  Converting document...                     │
 * │  ████████████░░░░░░░░░  45%                 │  ← Progress bar
 * │                                             │
 * │  Steps:                                     │
 * │  ✅ File uploaded                           │
 * │  ✅ Converting to markdown                  │
 * │  🔄 Processing images...                    │
 * │  ⬜ Creating document                       │
 * │  ⬜ Generating embeddings                   │
 * │                                             │
 * └─────────────────────────────────────────────┘
 *
 * On completion:
 * - Shows success message with link to new document
 * - "Open Document" button navigates to it
 * - Dialog auto-closes after 3 seconds (or on click)
 */
```

### Implementation Details

- **Drop zone**: Uses HTML5 drag-and-drop API
- **File validation**: Client-side size and type check before upload
- **Scope selector**: Reuses existing scope/folder selection patterns from knowledge tree
- **Progress polling**: Uses React Query to poll `GET /api/ai/import/{job_id}` every 2 seconds
- **WebSocket**: Also listens for `IMPORT_COMPLETED` event for instant notification
- **Navigation**: On completion, navigates to new document using state-based routing

### Acceptance Criteria
- [ ] Drop zone accepts PDF/DOCX/PPTX files
- [ ] Drag-and-drop visual feedback
- [ ] File type and size validated client-side
- [ ] Title auto-filled from filename (editable)
- [ ] Scope/folder selectors work
- [ ] Upload progress shown
- [ ] Processing progress updates in real-time
- [ ] Success navigates to new document
- [ ] Failure shows error message
- [ ] Dialog closeable at any stage

---

### New File: `electron-app/src/renderer/hooks/use-document-import.ts`

```typescript
/**
 * React Query hooks for document import.
 *
 * useImportDocument():
 *   - Mutation: POST /api/ai/import (multipart/form-data)
 *   - Returns: { job_id, status }
 *
 * useImportJobStatus(jobId):
 *   - Query: GET /api/ai/import/{jobId}
 *   - Polls every 2s while status is "pending" or "processing"
 *   - Stops polling on "completed" or "failed"
 *   - refetchInterval: (data) => data?.status in ["pending", "processing"] ? 2000 : false
 *
 * useImportJobs():
 *   - Query: GET /api/ai/import/jobs
 *   - Lists user's recent imports
 */
```

### Acceptance Criteria
- [ ] Upload mutation handles multipart/form-data correctly
- [ ] Polling stops automatically on completion/failure
- [ ] Job list refreshes when new import starts
- [ ] Error states handled (network errors, validation errors)

---

## Task 6.7: Dependencies

### Modify: `fastapi-backend/requirements.txt`

Add:
```
docling>=2.0.0
```

### Acceptance Criteria
- [ ] `pip install -r requirements.txt` succeeds
- [ ] Docling installs with all required sub-dependencies
- [ ] No version conflicts with existing dependencies

---

## Task 6.8: Tests

### New File: `fastapi-backend/tests/test_docling_service.py`

```
test_convert_pdf_to_markdown
test_convert_docx_to_markdown
test_convert_pptx_to_markdown
test_extract_images_from_pdf
test_extract_images_from_docx
test_process_file_returns_complete_result
test_corrupted_file_raises_error
test_unsupported_type_raises_error
test_large_file_processes_without_oom
test_password_protected_pdf_raises_error
```

### New File: `fastapi-backend/tests/test_image_understanding.py`

```
test_extract_image_nodes_from_tiptap
test_process_document_images_creates_chunks
test_process_document_images_skips_small_images
test_process_document_images_limits_count
test_process_imported_images_uploads_to_minio
test_vision_provider_error_continues_batch
test_image_descriptions_are_embedded
```

### New File: `fastapi-backend/tests/test_import_router.py`

```
test_upload_pdf_creates_job
test_upload_docx_creates_job
test_upload_pptx_creates_job
test_upload_invalid_type_rejected
test_upload_too_large_rejected
test_upload_requires_scope_access
test_get_job_status_returns_progress
test_get_job_status_unauthorized
test_list_jobs_returns_user_jobs_only
test_import_job_creates_document
test_import_job_sets_error_on_failure
test_import_job_cleans_temp_file
```

### Acceptance Criteria
- [ ] All tests pass
- [ ] Docling tests use small fixture files (included in tests/ or generated)
- [ ] Vision provider mocked (no real API calls)
- [ ] Import router tests use test database
- [ ] Temp file cleanup verified in tests

---

## Verification Checklist

```
1. Upload a PDF via import dialog
   → Job created, progress polling starts

2. Watch processing status update (10% → 40% → 60% → 80% → 100%)
   → Each step visible in progress UI

3. On completion:
   → Document appears in knowledge tree at specified folder
   → Document content is clean markdown converted from PDF
   → Success notification shows

4. Check document content in editor
   → Formatting preserved (headings, tables, lists)
   → Images from PDF stored as attachments and visible

5. Verify image understanding
   → DocumentChunks include image description chunks
   → Descriptions are meaningful (not generic)

6. Ask AI: "Summarize the document I just imported"
   → Returns accurate summary based on embedded chunks

7. Upload a DOCX with tables and images
   → Tables preserved in markdown
   → Images extracted and described

8. Upload a PPTX with multiple slides
   → Each slide becomes a section
   → Slide images processed

9. Try uploading unsupported file (e.g., .txt)
   → Rejected with clear error message

10. Try uploading >50MB file
    → Rejected with size limit error
```
