# File Uploads to Document Folders — Task Breakdown

**Created**: 2026-03-10
**Plan**: [plan.md](plan.md)
**Research**: [research.md](research.md)
**Status**: In Progress

---

## Phase 0: Wire Up Existing ImportDialog (Quick Win)

No backend changes needed. Ships independently of Phases 1–8.

### Task 0.1: Add Upload Button to KnowledgeSidebar

- **File**: `electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx` — MODIFY
- **Action**: Add an `Upload` icon button in the quick creation button bar (line 179–194), next to the existing `FilePlus` and `FolderPlus` buttons:
  - Import `Upload` from `lucide-react`
  - Add a third button with `title="Import document"` that sets import dialog state
  - Guard behind same `canEdit` check as existing buttons
  - Add state: `const [importDialogOpen, setImportDialogOpen] = useState(false)`
  - Render `<ImportDialog>` below the `<CreateDialog>`, passing:
    - `defaultScope`: resolved from `activeTab` (same as `resolveScope()`)
    - `defaultScopeId`: resolved from `activeTab`
    - `defaultFolderId`: `selectedFolderId`
    - `onImportComplete`: close dialog (optionally navigate to new document)
  - The dialog manages its own open state via the `open` prop pattern — set `open={importDialogOpen}` and `onOpenChange={setImportDialogOpen}`
  - **Note**: ImportDialog currently uses `<DialogTrigger>` internally. Two integration options:
    1. Pass a custom `trigger` prop to let the sidebar button be the trigger
    2. Control open state externally via props (may require minor ImportDialog refactor to accept `open`/`onOpenChange`)
- **Status**: [ ] Not Started

### Task 0.2: Add Import Support to KnowledgeTree

- **File**: `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx` — MODIFY
- **Action**: Enable import from within the tree (folder-level import):
  - Add `onImport` callback to the tree's context menu handler
  - When a folder's "Import Document" is clicked:
    - Set import state with `targetFolderId` + scope info from the folder
    - Render `<ImportDialog>` at tree level with the folder's scope/folderId pre-filled
  - Import `ImportDialog` from `@/components/ai/import-dialog`
  - Add state:
    ```ts
    const [importTarget, setImportTarget] = useState<{
      folderId: string
      scope: 'application' | 'project' | 'personal'
      scopeId: string
    } | null>(null)
    ```
  - Render:
    ```tsx
    {importTarget && (
      <ImportDialog
        defaultScope={importTarget.scope}
        defaultScopeId={importTarget.scopeId}
        defaultFolderId={importTarget.folderId}
        onImportComplete={() => setImportTarget(null)}
      />
    )}
    ```
  - Pass `onImport={(folderId) => setImportTarget({ folderId, ...resolvedScope })}` to `<FolderContextMenu>`
- **Status**: [ ] Not Started

### Task 0.3: Add "Import Document" to Folder Context Menu

- **File**: `electron-app/src/renderer/components/knowledge/folder-context-menu.tsx` — MODIFY
- **Action**: Add an "Import Document" menu item for folder targets:
  - Add `onImport` prop to `FolderContextMenuProps`:
    ```ts
    onImport?: (folderId: string) => void
    ```
  - In the folder menu items array (line 76–82), add after "New Document":
    ```ts
    { label: 'Import Document', icon: Upload, action: () => onImport?.(target.id) },
    ```
  - Import `Upload` from `lucide-react`
  - Only show when `onImport` is provided (backward compatible)
  - Updated folder menu order:
    1. New Folder
    2. New Document
    3. Import Document ← NEW
    4. (separator)
    5. Rename
    6. (separator)
    7. Delete
- **Status**: [ ] Not Started

### Task 0.4: Verification

- **Action**: Manual testing checklist:
  - [ ] Upload icon button appears in sidebar next to FilePlus/FolderPlus
  - [ ] Clicking Upload button opens ImportDialog
  - [ ] ImportDialog scope is pre-filled from active tab (application/personal)
  - [ ] ImportDialog folder is pre-filled from selected folder (if any)
  - [ ] Right-click folder → "Import Document" menu item appears
  - [ ] Clicking "Import Document" from context menu opens ImportDialog with that folder pre-filled
  - [ ] Upload a PDF → progress tracking works → document created → appears in tree
  - [ ] Read-only users do NOT see the Upload button or Import menu item
- **Status**: [ ] Not Started

---

## Phase 1: Data Model & Migration

### Task 1.1: Create Alembic Migration

- **File**: `fastapi-backend/alembic/versions/20260311_add_folder_files.py` — NEW
- **Depends on**: `20260309_add_session_token_auth` (latest migration)
- **Action**: Create migration with the following DDL:

  #### Create FolderFiles table:
  ```sql
  CREATE TABLE "FolderFiles" (
      id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      folder_id           UUID NOT NULL REFERENCES "DocumentFolders"(id) ON DELETE CASCADE,
      application_id      UUID REFERENCES "Applications"(id) ON DELETE CASCADE,
      project_id          UUID REFERENCES "Projects"(id) ON DELETE CASCADE,
      user_id             UUID REFERENCES "Users"(id) ON DELETE CASCADE,
      original_name       VARCHAR(255) NOT NULL,
      display_name        VARCHAR(255) NOT NULL,
      mime_type           VARCHAR(255) NOT NULL DEFAULT 'application/octet-stream',
      file_size           BIGINT NOT NULL,
      file_extension      VARCHAR(20) NOT NULL,
      storage_bucket      VARCHAR(100) NOT NULL,
      storage_key         VARCHAR(500) NOT NULL,
      thumbnail_key       VARCHAR(500),
      extraction_status   VARCHAR(12) NOT NULL DEFAULT 'pending',
      extraction_error    TEXT,
      content_plain       TEXT,
      extracted_metadata  JSONB DEFAULT '{}',
      embedding_status    VARCHAR(8) NOT NULL DEFAULT 'none',
      embedding_updated_at TIMESTAMPTZ,
      sha256_hash         VARCHAR(64),
      sort_order          INTEGER NOT NULL DEFAULT 0,
      created_by          UUID REFERENCES "Users"(id) ON DELETE SET NULL,
      row_version         INTEGER NOT NULL DEFAULT 1,
      deleted_at          TIMESTAMPTZ,
      created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  ```

  #### Constraints on FolderFiles:
  - `ck_folder_files_exactly_one_scope`: Same pattern as DocumentFolders — exactly one of application_id/project_id/user_id must be NOT NULL
  - `ck_folder_files_extraction_status`: CHECK `extraction_status IN ('pending', 'processing', 'completed', 'failed', 'unsupported')`
  - `ck_folder_files_embedding_status`: CHECK `embedding_status IN ('none', 'stale', 'syncing', 'synced', 'failed')`

  #### Indexes on FolderFiles:
  - `uq_folder_files_name`: UNIQUE on `(folder_id, LOWER(display_name)) WHERE deleted_at IS NULL`
  - `ix_folder_files_folder_id` on `folder_id`
  - `ix_folder_files_application_id` on `application_id`
  - `ix_folder_files_project_id` on `project_id`
  - `ix_folder_files_user_id` on `user_id`
  - `ix_folder_files_extraction_status` on `extraction_status`
  - `ix_folder_files_deleted_at` on `deleted_at`

  #### Extend DocumentChunks:
  - ADD COLUMN `source_type VARCHAR(10) NOT NULL DEFAULT 'document'`
  - ADD COLUMN `file_id UUID REFERENCES "FolderFiles"(id) ON DELETE CASCADE`
  - ALTER `document_id` to NULLABLE
  - ADD CHECK `ck_chunks_exactly_one_source`: `(document_id IS NOT NULL AND file_id IS NULL) OR (document_id IS NULL AND file_id IS NOT NULL)`
  - ADD UNIQUE INDEX `idx_document_chunks_file_idx ON "DocumentChunks" (file_id, chunk_index) WHERE file_id IS NOT NULL`
  - BACKFILL: `UPDATE "DocumentChunks" SET source_type = 'document' WHERE source_type IS NULL`

  #### Downgrade:
  - Drop CHECK constraint, drop columns (source_type, file_id), restore document_id NOT NULL
  - Drop FolderFiles table

- **Status**: [ ] Not Started

### Task 1.2: Create FolderFile SQLAlchemy Model

- **File**: `fastapi-backend/app/models/folder_file.py` — NEW
- **Action**: Create model following the pattern from `document.py`:
  ```python
  class FolderFile(Base):
      __tablename__ = "FolderFiles"
      __allow_unmapped__ = True

      id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      folder_id = Column(UUID(as_uuid=True), ForeignKey("DocumentFolders.id", ondelete="CASCADE"), nullable=False)
      application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True, index=True)
      project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id", ondelete="CASCADE"), nullable=True, index=True)
      user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="CASCADE"), nullable=True, index=True)
      original_name = Column(String(255), nullable=False)
      display_name = Column(String(255), nullable=False)
      mime_type = Column(String(255), nullable=False, default="application/octet-stream")
      file_size = Column(BigInteger, nullable=False)
      file_extension = Column(String(20), nullable=False)
      storage_bucket = Column(String(100), nullable=False)
      storage_key = Column(String(500), nullable=False)
      thumbnail_key = Column(String(500), nullable=True)
      extraction_status = Column(String(12), nullable=False, default="pending")
      extraction_error = Column(Text, nullable=True)
      content_plain = Column(Text, nullable=True)
      extracted_metadata = Column(JSONB, default={})
      embedding_status = Column(String(8), nullable=False, default="none")
      embedding_updated_at = Column(DateTime(timezone=True), nullable=True)
      sha256_hash = Column(String(64), nullable=True)
      sort_order = Column(Integer, nullable=False, default=0)
      created_by = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="SET NULL"), nullable=True)
      row_version = Column(Integer, nullable=False, default=1)
      deleted_at = Column(DateTime(timezone=True), nullable=True)
      created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
      updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
  ```
  - Relationships: `folder` (DocumentFolder), `creator` (User), `chunks` (DocumentChunk)
  - `__table_args__`: scope CHECK constraint (same as DocumentFolders line 146-153)
- **Status**: [ ] Not Started

### Task 1.3: Extend DocumentChunk Model

- **File**: `fastapi-backend/app/models/document_chunk.py` — MODIFY
- **Action**:
  - Change `document_id` from `nullable=False` to `nullable=True`
  - Add `source_type = Column(String(10), nullable=False, default="document")`
  - Add `file_id = Column(UUID(as_uuid=True), ForeignKey("FolderFiles.id", ondelete="CASCADE"), nullable=True)`
  - Add `file = relationship("FolderFile", back_populates="chunks")`
  - Add CHECK constraint to `__table_args__`: `ck_chunks_exactly_one_source`
  - Add partial unique index for file chunks to `__table_args__`
- **Status**: [ ] Not Started

### Task 1.4: Update DocumentFolder Model

- **File**: `fastapi-backend/app/models/document_folder.py` — MODIFY
- **Action**: Add `files` relationship:
  ```python
  files: List["FolderFile"] = relationship(
      "FolderFile",
      back_populates="folder",
      lazy="dynamic",
      passive_deletes=True,
  )
  ```
- **Status**: [ ] Not Started

### Task 1.5: Register Model in __init__

- **File**: `fastapi-backend/app/models/__init__.py` — MODIFY
- **Action**: Add `from .folder_file import FolderFile` and include in `__all__`
- **Status**: [ ] Not Started

### Task 1.6: Create Pydantic Schemas

- **File**: `fastapi-backend/app/schemas/folder_file.py` — NEW
- **Action**: Create schemas:
  - `FolderFileResponse` — Full response with all fields, `model_config = ConfigDict(from_attributes=True)`
  - `FolderFileListItem` — Lightweight for tree: id, display_name, file_extension, mime_type, file_size, extraction_status, embedding_status, sort_order, folder_id, created_by, created_at, updated_at
  - `FolderFileUpdate` — Optional fields: display_name, folder_id, sort_order, row_version (required for optimistic concurrency)
  - `FolderFileReplaceResponse` — id, display_name, extraction_status, message
- **Status**: [ ] Not Started

### Task 1.7: Write Phase 1 Tests

- **File**: `fastapi-backend/tests/test_folder_file_model.py` — NEW
- **Tests**:
  - Create FolderFile with valid scope (application_id only) — should succeed
  - Create FolderFile with zero scope FKs — should fail CHECK constraint
  - Create FolderFile with two scope FKs — should fail CHECK constraint
  - Create DocumentChunk with file_id (no document_id) — should succeed
  - Create DocumentChunk with both document_id and file_id — should fail CHECK constraint
  - Create DocumentChunk with neither — should fail CHECK constraint
  - Duplicate display_name in same folder — should fail unique constraint
  - Duplicate display_name in different folder — should succeed
  - Duplicate display_name with one soft-deleted — should succeed (partial index)
  - Cascade delete: delete FolderFile → chunks deleted
- **Status**: [ ] Not Started

---

## Phase 2: Upload API & MinIO Storage

### Task 2.1: Create Folder Files Router

- **File**: `fastapi-backend/app/routers/folder_files.py` — NEW
- **Action**: Create router with prefix `/api/folder-files`, tags `["FolderFiles"]`
- **Pattern**: Follow `fastapi-backend/app/routers/files.py` for auth/upload patterns
- **Status**: [ ] Not Started

### Task 2.2: Implement Upload Endpoint

- **File**: `fastapi-backend/app/routers/folder_files.py`
- **Endpoint**: `POST /api/folder-files/upload`
- **Parameters**: multipart `file` (UploadFile), query `folder_id` (UUID), optional query `display_name` (str)
- **Logic**:
  1. Validate file present, has filename
  2. Read content, check size <= MAX_FILE_SIZE (100MB from config)
  3. RBAC: Load folder → resolve scope FKs → `PermissionService.check_can_edit_knowledge(user_id, scope_type, scope_id)`
  4. Extract file_extension from filename (lowercase, strip dot)
  5. Determine display_name: use param or default to `file.filename`
  6. Check for duplicate: `SELECT ... WHERE folder_id = :fid AND LOWER(display_name) = LOWER(:name) AND deleted_at IS NULL`
     - If exists: return `409 Conflict` with body `{"detail": "File with this name already exists", "existing_file_id": str(existing.id)}`
  7. Compute SHA-256: `hashlib.sha256(content).hexdigest()`
  8. Determine MIME type: `file.content_type` or `magic.from_buffer(content[:8192], mime=True)` via python-magic
  9. Upload to MinIO:
     - Bucket: `pm-attachments`
     - Key: `folder-files/{folder_id}/{uuid8}_{sanitized_filename}`
     - Use `minio_service.upload_bytes(bucket, key, content, content_type)`
  10. Determine extraction_status:
      ```python
      EXTRACTABLE_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".tsv", ".vsdx"}
      status = "pending" if f".{file_extension}" in EXTRACTABLE_EXTENSIONS else "unsupported"
      ```
  11. Create FolderFile record with scope FKs copied from folder
  12. Commit + refresh
  13. If status == "pending": enqueue ARQ job
      ```python
      arq_redis = await get_arq_redis()
      await arq_redis.enqueue_job(
          "extract_and_embed_file_job",
          str(file_record.id),
          _job_id=f"extract_file:{file_record.id}",
      )
      ```
  14. WebSocket broadcast `FILE_UPLOADED` to scope room
  15. Return `FolderFileResponse`
- **Status**: [ ] Not Started

### Task 2.3: Implement List Files Endpoint

- **File**: `fastapi-backend/app/routers/folder_files.py`
- **Endpoint**: `GET /api/folder-files`
- **Query params**: `folder_id` (UUID, required), `limit` (int, default 100), `cursor` (UUID, optional)
- **Logic**:
  1. RBAC: Load folder → resolve scope → `check_can_view_knowledge`
  2. Query: `SELECT FROM FolderFiles WHERE folder_id = :fid AND deleted_at IS NULL ORDER BY sort_order, display_name LIMIT :limit`
  3. Keyset pagination via cursor (WHERE id > cursor)
  4. Return list of `FolderFileListItem`
- **Status**: [ ] Not Started

### Task 2.4: Implement Get File / Download URL Endpoints

- **File**: `fastapi-backend/app/routers/folder_files.py`
- **Endpoints**:
  - `GET /api/folder-files/{file_id}` — Full details + presigned download URL
  - `GET /api/folder-files/{file_id}/download` — Just `{ download_url, file_name }`
- **Logic**: Load FolderFile → RBAC check via scope FKs → `minio_service.get_presigned_download_url(bucket, key)` → return
- **Status**: [ ] Not Started

### Task 2.5: Implement Rename/Move Endpoint

- **File**: `fastapi-backend/app/routers/folder_files.py`
- **Endpoint**: `PUT /api/folder-files/{file_id}`
- **Body**: `FolderFileUpdate` (display_name, folder_id, sort_order, row_version)
- **Logic**:
  1. Load FolderFile, verify not deleted
  2. RBAC: `check_can_edit_knowledge` on current scope
  3. Optimistic concurrency: `if file.row_version != body.row_version: raise 409`
  4. If display_name changed: check duplicate in target folder
  5. If folder_id changed (move):
     - RBAC: `check_can_edit_knowledge` on target folder's scope too
     - Update scope FKs from new folder
     - Update chunk scope FKs (denormalized)
  6. Increment `row_version`, update fields
  7. WebSocket broadcast `FILE_UPDATED`
- **Status**: [ ] Not Started

### Task 2.6: Implement Delete Endpoint

- **File**: `fastapi-backend/app/routers/folder_files.py`
- **Endpoint**: `DELETE /api/folder-files/{file_id}`
- **Logic**:
  1. Load FolderFile, verify not already deleted
  2. RBAC: `check_can_edit_knowledge`
  3. Soft delete: set `deleted_at = utc_now()`
  4. Delete all DocumentChunks where `file_id = :fid`
  5. Remove from Meilisearch: `remove_file_from_index(file_id)`
  6. Do NOT delete MinIO object (soft delete — recoverable)
  7. WebSocket broadcast `FILE_DELETED`
- **Status**: [ ] Not Started

### Task 2.7: Implement Replace Endpoint

- **File**: `fastapi-backend/app/routers/folder_files.py`
- **Endpoint**: `POST /api/folder-files/{file_id}/replace`
- **Parameters**: multipart `file` (UploadFile)
- **Logic**:
  1. Load existing FolderFile, verify not deleted
  2. RBAC: `check_can_edit_knowledge`
  3. Read new file content, validate size
  4. Delete old MinIO object: `minio_service.delete_file(old_bucket, old_key)`
  5. Upload new file to MinIO (new key with new UUID prefix)
  6. Update FolderFile: new storage_key, file_size, mime_type, sha256_hash
  7. Reset: `extraction_status = 'pending'`, `extraction_error = None`, `content_plain = None`, `embedding_status = 'none'`
  8. Delete existing chunks: `DELETE FROM DocumentChunks WHERE file_id = :fid`
  9. Remove old Meilisearch entry
  10. Enqueue `extract_and_embed_file_job`
  11. WebSocket broadcast `FILE_UPDATED`
- **Status**: [ ] Not Started

### Task 2.8: Add WebSocket Message Types

- **File**: `fastapi-backend/app/websocket/manager.py` — MODIFY
- **Action**: Add to MessageType:
  ```python
  FILE_UPLOADED = "file_uploaded"
  FILE_UPDATED = "file_updated"
  FILE_DELETED = "file_deleted"
  FILE_EXTRACTION_COMPLETED = "file_extraction_completed"
  FILE_EXTRACTION_FAILED = "file_extraction_failed"
  ```
- **Status**: [ ] Not Started

### Task 2.9: Register Router

- **File**: `fastapi-backend/app/main.py` — MODIFY
- **Action**: `app.include_router(folder_files.router)` (import from `app.routers.folder_files`)
- **Status**: [ ] Not Started

### Task 2.10: Write Phase 2 Tests

- **File**: `fastapi-backend/tests/test_folder_files_api.py` — NEW
- **Tests**:
  - Upload file to folder → 201, verify MinIO storage, FolderFile record, scope FK denormalization
  - Upload duplicate name → 409 with existing_file_id
  - Upload with explicit display_name → stored correctly
  - RBAC: viewer cannot upload → 403
  - RBAC: editor can upload → 201
  - File size > MAX_FILE_SIZE → 413
  - List files in folder → correct items, sort order
  - Get file → presigned URL returned
  - Rename file → display_name updated, row_version incremented
  - Rename to duplicate name → 409
  - Move file to different folder → scope FKs updated
  - Delete file → soft deleted, chunks removed
  - Replace file → new content, extraction re-enqueued
  - Upload to non-existent folder → 404
- **Status**: [ ] Not Started

---

## Phase 3: Content Extraction Services

### Task 3.1: Add Dependencies to requirements.txt

- **File**: `fastapi-backend/requirements.txt` — MODIFY
- **Action**: Add:
  ```
  python-calamine>=0.6.0,<1.0.0
  chardet>=7.0.0,<8.0.0
  vsdx>=0.5.0,<1.0.0
  ```
- **Status**: [ ] Not Started

### Task 3.2: Create ExtractionResult Dataclass

- **File**: `fastapi-backend/app/ai/file_extraction_service.py` — NEW
- **Action**: Define shared result type:
  ```python
  @dataclass
  class ExtractionResult:
      content_plain: str          # Full extracted text (for Meilisearch + content_plain column)
      content_markdown: str       # Markdown-formatted (for chunking)
      metadata: dict[str, Any]    # Format-specific: {page_count, sheet_names, shape_count, ...}
      warnings: list[str]         # Non-fatal issues
  ```
- **Status**: [ ] Not Started

### Task 3.3: Create SpreadsheetExtractor

- **File**: `fastapi-backend/app/ai/spreadsheet_extractor.py` — NEW
- **Action**: Create class with two extraction paths:

  #### `async extract(file_path: str, extension: str) -> ExtractionResult`
  - Route: `.csv`/`.tsv` → `_extract_csv()`, everything else → `_extract_calamine()`
  - Wrap sync methods with `asyncio.to_thread()`

  #### `_extract_calamine(file_path: str) -> ExtractionResult` (sync)
  - Open: `CalamineWorkbook.from_path(file_path)`
  - Guard: max 50 sheets (`MAX_SHEETS` from config)
  - Per sheet:
    - `rows = wb.get_sheet_by_name(name).to_python()`
    - Guard: max 500,000 rows per sheet, max 10,000 chars per cell
    - Detect headers: first row where all cells are non-None strings
    - If no clear header: generate `Column_1, Column_2, ...`
    - Format cell values:
      - `datetime` → `YYYY-MM-DD HH:MM:SS`
      - `date` → `YYYY-MM-DD`
      - `bool` → `"Yes"` / `"No"`
      - `float` where `== int(float)` → int string (no `.0`)
      - `None` → empty string
    - Build markdown:
      - If columns <= 10: pipe table `| Col1 | Col2 |\n|---|---|\n| val1 | val2 |`
      - If columns > 10: KV format `### Row N\n- **Col1**: val1\n- **Col2**: val2`
    - Prepend heading: `## Sheet: {name}\n\n`
    - If sheet is empty (all rows empty after header): skip with warning
  - Join all sheets with `\n\n`
  - Metadata: `{ "sheet_count": N, "sheet_names": [...], "total_rows": M, "column_counts": {sheet: N} }`
  - Content_plain: strip markdown formatting (just the text, for Meilisearch)

  #### `_extract_csv(file_path: str, extension: str) -> ExtractionResult` (sync)
  - Encoding detection:
    1. Read first 32KB as bytes
    2. Try `bytes.decode('utf-8')` — if succeeds, use UTF-8
    3. If UnicodeDecodeError: `chardet.detect(bytes)` → use detected encoding
    4. If confidence < 0.5: fall back to `latin-1` (never fails)
  - Delimiter detection:
    1. Read first 8KB as text
    2. `csv.Sniffer().sniff(sample, delimiters=',;\t|')`
    3. If csv.Error: default to `,` for .csv, `\t` for .tsv
  - Parse with `csv.reader(file, dialect)`
  - Header detection: same as calamine (first all-string row or generated)
  - Format: same markdown as calamine
  - Guard: max 500,000 rows
  - Metadata: `{ "encoding": detected, "delimiter": char, "row_count": N, "column_count": M }`

  #### Error handling:
  - `CalamineError` / `BadZipFile` → raise `ImportError("Corrupted or invalid spreadsheet file")`
  - Password detection: catch specific calamine/openpyxl errors → `ImportError("Password-protected files are not supported")`
  - openpyxl fallback: if calamine fails with unexpected error, try `openpyxl.load_workbook(path, read_only=True, data_only=True)` with same extraction logic

- **Status**: [ ] Not Started

### Task 3.4: Create VisioExtractor

- **File**: `fastapi-backend/app/ai/visio_extractor.py` — NEW
- **Action**: Create class:

  #### `async extract(file_path: str) -> ExtractionResult`
  - Wrap `_extract_sync()` with `asyncio.to_thread()`

  #### `_extract_sync(file_path: str) -> ExtractionResult` (sync)
  - Open: `vsdx.VisioFile(file_path)` (context manager: `with vsdx.VisioFile(file_path) as vis:`)
  - Per page in `vis.pages`:
    - Heading: `## Page: {page.name}`
    - Collect shapes: iterate `page.all_shapes` (recursive — handles groups)
    - For each shape with `shape.text.strip()`: add to shapes list
    - Build shapes section: `### Shapes\n- shape1_text\n- shape2_text`
    - Build connections section:
      ```python
      connections = []
      processed = set()
      for shape in page.all_shapes:
          for connected in (shape.connected_shapes or []):
              pair = tuple(sorted([shape.ID, connected.ID]))
              if pair not in processed:
                  processed.add(pair)
                  from_text = (shape.text or "").strip() or f"Shape {shape.ID}"
                  to_text = (connected.text or "").strip() or f"Shape {connected.ID}"
                  # Try to get connector label
                  connectors = page.get_connectors_between(shape, connected)
                  label = ""
                  if connectors:
                      label = (connectors[0].text or "").strip()
                  arrow = f"- {from_text} -> {to_text}"
                  if label:
                      arrow += f" [{label}]"
                  connections.append(arrow)
      ```
    - Output: `### Connections\n{connection_lines}` (or skip section if no connections)
  - Join pages with `\n\n`
  - Metadata: `{ "page_count": N, "shape_count": M, "connection_count": K, "page_names": [...] }`
  - Content_plain: same as markdown (VSDX output is already plain-text-like)

  #### Error handling:
  - `zipfile.BadZipFile` → `ImportError("Invalid or corrupted Visio file")`
  - `KeyError` / `XMLSyntaxError` → `ImportError("Malformed Visio file structure")`
  - Empty file (no pages or no shapes with text) → return empty ExtractionResult with warning

- **Status**: [ ] Not Started

### Task 3.5: Create FileExtractionService (Router/Orchestrator)

- **File**: `fastapi-backend/app/ai/file_extraction_service.py` — MODIFY (add to file from Task 3.2)
- **Action**: Create orchestrator class:

  ```python
  class FileExtractionService:
      SUPPORTED_EXTENSIONS: dict[str, str] = {
          ".pdf": "docling", ".docx": "docling", ".pptx": "docling",
          ".xlsx": "spreadsheet", ".xls": "spreadsheet",
          ".xlsm": "spreadsheet", ".xlsb": "spreadsheet",
          ".csv": "spreadsheet", ".tsv": "spreadsheet",
          ".vsdx": "visio",
      }

      MAX_FILE_SIZES: dict[str, int] = {
          "docling": 100 * 1024 * 1024,      # 100MB for PDF
          "spreadsheet": 50 * 1024 * 1024,    # 50MB for XLSX/CSV
          "visio": 50 * 1024 * 1024,          # 50MB for VSDX
      }

      def __init__(self):
          self._docling = DoclingService()     # reuse existing
          self._spreadsheet = SpreadsheetExtractor()
          self._visio = VisioExtractor()

      def is_supported(self, extension: str) -> bool:
          return extension.lower() in self.SUPPORTED_EXTENSIONS

      async def extract(self, file_path: str, extension: str) -> ExtractionResult:
          ext = extension.lower()
          if ext not in self.SUPPORTED_EXTENSIONS:
              raise ValueError(f"Unsupported format: {ext}")

          category = self.SUPPORTED_EXTENSIONS[ext]

          # Size guard
          file_size = os.path.getsize(file_path)
          max_size = self.MAX_FILE_SIZES.get(category, 50 * 1024 * 1024)
          if file_size > max_size:
              raise ImportError(f"File too large: {file_size} bytes (max {max_size})")

          if category == "docling":
              result = await self._docling.process_file(file_path, ext.lstrip("."))
              return ExtractionResult(
                  content_plain=result.markdown,  # strip formatting for search
                  content_markdown=result.markdown,
                  metadata=result.metadata,
                  warnings=result.warnings,
              )
          elif category == "spreadsheet":
              return await self._spreadsheet.extract(file_path, ext)
          elif category == "visio":
              return await self._visio.extract(file_path)
          else:
              raise ValueError(f"Unknown extraction category: {category}")
  ```

- **Status**: [ ] Not Started

### Task 3.6: Write Phase 3 Tests

- **File**: `fastapi-backend/tests/test_file_extraction.py` — NEW
- **Test fixtures**: Create small test files in `tests/fixtures/`:
  - `test_simple.xlsx` — 2 sheets, 5 rows each, mixed types (string, int, date, bool)
  - `test_wide.xlsx` — 1 sheet, 15 columns (to test KV format)
  - `test_simple.csv` — UTF-8, comma-delimited, 10 rows
  - `test_latin1.csv` — Latin-1 encoded, semicolon-delimited
  - `test_diagram.vsdx` — 3 shapes, 2 connections (create manually in Visio or programmatically)
- **Tests**:
  - SpreadsheetExtractor: XLSX multi-sheet → verify both sheet headings in output
  - SpreadsheetExtractor: XLSX wide table → verify KV format used
  - SpreadsheetExtractor: XLSX date/bool formatting → verify human-readable output
  - SpreadsheetExtractor: CSV UTF-8 → verify correct parsing
  - SpreadsheetExtractor: CSV Latin-1 → verify chardet detects encoding
  - SpreadsheetExtractor: CSV semicolon delimiter → verify Sniffer detection
  - SpreadsheetExtractor: TSV → verify tab delimiter
  - SpreadsheetExtractor: empty sheet → verify warning, no crash
  - SpreadsheetExtractor: too many rows (>500K) → verify truncation + warning
  - VisioExtractor: shapes + connections → verify both sections in output
  - VisioExtractor: empty VSDX → verify warning
  - FileExtractionService: route .xlsx → spreadsheet extractor
  - FileExtractionService: route .pdf → docling
  - FileExtractionService: route .vsdx → visio extractor
  - FileExtractionService: unsupported .zip → ValueError
  - FileExtractionService: oversized file → ImportError
- **Status**: [ ] Not Started

---

## Phase 4: Chunking Extension for Extracted Content

### Task 4.1: Add chunk_markdown Method to SemanticChunker

- **File**: `fastapi-backend/app/ai/chunking_service.py` — MODIFY
- **Action**: Add new public method:

  ```python
  def chunk_markdown(self, markdown: str, title: str) -> list[ChunkResult]:
      """Chunk extracted markdown content from file extraction.

      Unlike chunk_document() which expects TipTap JSON, this takes
      raw markdown and splits at heading boundaries.
      """
  ```

  #### Algorithm:
  1. If empty markdown: return `[]`
  2. Split at heading boundaries using regex: `re.split(r'(?=^#{1,3}\s)', markdown, flags=re.MULTILINE)`
  3. For each section:
     - Extract heading text from first line (if starts with `#`)
     - Set `heading_context` to heading text, or `title` if no heading
     - Count tokens with `self.count_tokens(section_text)`
  4. Create `_TextBlock` for each section (reuse existing dataclass)
  5. **Detect spreadsheet tables**: if section contains `|---|`, mark as `is_table=True` and extract column headers from first `| ... |` line into `table_columns`
  6. Pass blocks through existing `self._merge_and_split(blocks)`:
     - Sections < MIN_TOKENS (200): merge with next section (don't cross H1 `#` boundaries)
     - Sections > MAX_TOKENS (800): for tables → use `self._split_table_by_rows()` with dynamic rows_per_chunk; for text → split at `\n\n` paragraph boundaries, then at `. ` sentence boundaries
  7. Apply `self._add_overlap(merged)` for 100-token overlap
  8. Assign sequential `chunk_index`
  9. Return `list[ChunkResult]`

  #### Dynamic rows_per_chunk for spreadsheets:
  ```python
  # Sample first 5 data rows to estimate tokens per row
  sample_rows = data_lines[:5]
  avg_tokens_per_row = sum(self.count_tokens(r) for r in sample_rows) / max(len(sample_rows), 1)
  header_tokens = self.count_tokens(header_line) + self.count_tokens(preamble)
  available = self.MAX_TOKENS - header_tokens - 20  # safety margin
  rows_per_chunk = max(5, int(available / max(avg_tokens_per_row, 1)))
  ```

- **Status**: [ ] Not Started

### Task 4.2: Add embed_file Method to EmbeddingService

- **File**: `fastapi-backend/app/ai/embedding_service.py` — MODIFY
- **Action**: Add three new methods:

  #### `async embed_file(file_id, content_markdown, title, scope_ids) -> EmbedResult`
  Same pipeline as `embed_document()` (lines 73-190) but:
  - Step 1: `chunks = self.chunker.chunk_markdown(content_markdown, title)` (instead of `chunk_document`)
  - Step 4: `await self.delete_file_chunks(file_id)` (instead of `delete_document_chunks`)
  - Step 5: Create chunks with `file_id=file_id, document_id=None, source_type='file'`
  - Step 6: `await self._update_file_embedding_timestamp(file_id)`

  #### `async delete_file_chunks(file_id: UUID) -> int`
  ```python
  result = await self.db.execute(
      delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
  )
  return result.rowcount
  ```

  #### `async _update_file_embedding_timestamp(file_id: UUID) -> None`
  Same pattern as `_update_embedding_timestamp` but updates FolderFile:
  ```python
  await self.db.execute(
      update(FolderFile)
      .where(FolderFile.id == file_id)
      .where(FolderFile.embedding_status == "syncing")
      .values(
          embedding_updated_at=utc_now(),
          updated_at=FolderFile.updated_at,
          embedding_status="synced",
      )
  )
  ```

- **Status**: [ ] Not Started

### Task 4.3: Write Phase 4 Tests

- **File**: `fastapi-backend/tests/test_file_chunking.py` — NEW
- **Tests**:
  - chunk_markdown: heading-structured markdown → verify heading_context propagation
  - chunk_markdown: single large section (2000 tokens) → verify split into 3+ chunks with overlap
  - chunk_markdown: small sections (50 tokens each) → verify merged into fewer chunks
  - chunk_markdown: pipe table with 80 rows → verify header repeated in each chunk
  - chunk_markdown: wide KV format → verify split at row boundaries
  - chunk_markdown: mixed (text + table) → verify table gets own chunk
  - chunk_markdown: empty string → returns []
  - embed_file: mock provider → verify chunks stored with file_id and source_type='file'
  - embed_file: empty content → verify no chunks, status updated
  - delete_file_chunks: verify only file's chunks deleted, other file's chunks and document chunks intact
- **Status**: [ ] Not Started

---

## Phase 5: Background Worker Job

### Task 5.1: Create extract_and_embed_file_job

- **File**: `fastapi-backend/app/worker.py` — MODIFY
- **Action**: Add function (follow `embed_document_job` pattern at line 323-542):

  ```python
  async def extract_and_embed_file_job(ctx: dict[str, Any], file_id: str) -> dict[str, Any]:
  ```

  #### Pipeline:
  1. **Retry guard** (same pattern as embed_document_job lines 350-372):
     - Redis key: `extract_retry:{file_id}`
     - Max retries: `_cfg.get_int("worker.max_extract_retries", 3)`
     - On max retries: set `extraction_status = 'failed'`, return

  2. **Load FolderFile**:
     ```python
     async with async_session_maker() as db:
         result = await db.execute(
             select(FolderFile).where(
                 FolderFile.id == file_uuid,
                 FolderFile.deleted_at.is_(None),
             )
         )
         file_record = result.scalar_one_or_none()
     ```
     - If not found or deleted: return `{"status": "skipped", "reason": "not_found"}`
     - If `extraction_status` already `'completed'` or `'unsupported'`: return skipped

  3. **Set processing status**:
     ```python
     file_record.extraction_status = "processing"
     await db.flush()
     ```

  4. **Download from MinIO to temp file**:
     ```python
     import tempfile
     from .services.minio_service import minio_service

     with tempfile.NamedTemporaryFile(suffix=f".{file_record.file_extension}", delete=False) as tmp:
         tmp_path = tmp.name
         minio_service.download_file(
             bucket=file_record.storage_bucket,
             object_name=file_record.storage_key,
             file_path=tmp_path,
         )
     ```

  5. **Extract content** (wrapped in try/finally for temp file cleanup):
     ```python
     try:
         extraction_service = FileExtractionService()
         ext = f".{file_record.file_extension}"

         if not extraction_service.is_supported(ext):
             file_record.extraction_status = "unsupported"
             await db.commit()
             return {"status": "unsupported"}

         EXTRACT_TIMEOUT = _cfg.get_int("worker.file_extract_timeout_s", 60)
         result = await asyncio.wait_for(
             extraction_service.extract(tmp_path, ext),
             timeout=EXTRACT_TIMEOUT,
         )

         file_record.content_plain = result.content_plain
         file_record.extracted_metadata = result.metadata
         file_record.extraction_status = "completed"
         if result.warnings:
             file_record.extraction_error = "; ".join(result.warnings)
     finally:
         os.unlink(tmp_path)  # Always cleanup temp file
     ```

  6. **Index in Meilisearch**:
     ```python
     from .services.search_service import build_search_file_data, index_file_from_data
     search_data = build_search_file_data(file_record)
     await index_file_from_data(search_data)
     ```

  7. **Embed content** (if extraction succeeded and content non-empty):
     ```python
     if file_record.extraction_status == "completed" and file_record.content_plain:
         file_record.embedding_status = "syncing"
         await db.flush()

         from .ai.chunking_service import SemanticChunker
         from .ai.embedding_normalizer import EmbeddingNormalizer
         from .ai.embedding_service import EmbeddingService
         from .ai.provider_registry import ProviderRegistry

         registry = ProviderRegistry()
         chunker = SemanticChunker()
         normalizer = EmbeddingNormalizer()
         service = EmbeddingService(registry, chunker, normalizer, db)

         EMBED_TIMEOUT = _cfg.get_int("worker.embed_timeout_s", 30)
         embed_result = await asyncio.wait_for(
             service.embed_file(
                 file_id=file_uuid,
                 content_markdown=result.content_markdown,
                 title=file_record.display_name,
                 scope_ids={
                     "application_id": file_record.application_id,
                     "project_id": file_record.project_id,
                     "user_id": file_record.user_id,
                 },
             ),
             timeout=EMBED_TIMEOUT,
         )
     ```

  8. **Commit + WebSocket broadcast**:
     ```python
     await db.commit()

     ws_payload = {
         "type": "file_extraction_completed",
         "data": {
             "file_id": file_id,
             "extraction_status": file_record.extraction_status,
             "embedding_status": file_record.embedding_status,
             "chunk_count": embed_result.chunk_count if embed_result else 0,
         },
     }
     # Broadcast to scope room (same pattern as embed_document_job lines 484-506)
     ```

  9. **Clear retry counter on success**

  #### Error handling (except block):
  - Set `extraction_status = 'failed'`, `extraction_error = str(e)`
  - Set `embedding_status = 'failed'` if it was 'syncing'
  - Broadcast `FILE_EXTRACTION_FAILED`
  - Log with exc_info=True

- **Status**: [ ] Not Started

### Task 5.2: Register Job in WorkerSettings

- **File**: `fastapi-backend/app/worker.py` — MODIFY
- **Action**: Add `extract_and_embed_file_job` to `WorkerSettings.functions` list (around line 1697)
- **Status**: [ ] Not Started

### Task 5.3: Write Phase 5 Tests

- **File**: `fastapi-backend/tests/test_file_extraction_worker.py` — NEW
- **Tests**:
  - Happy path: mock MinIO download + extraction → verify status transitions: pending → processing → completed, embedding_status synced
  - Unsupported extension: verify extraction_status = 'unsupported', no chunks
  - Extraction failure: mock extraction to raise → verify extraction_status = 'failed', error stored
  - Embedding failure: mock embed to raise → verify extraction_status = 'completed' but embedding_status = 'failed'
  - Timeout: mock slow extraction → verify timeout error, status = 'failed'
  - Retry guard: simulate 3 failures → verify max retries, status = 'failed'
  - Dedup: enqueue same file_id twice → verify only one job runs
  - Deleted file: soft-delete file before job runs → verify skipped
  - Empty content: extraction returns empty string → verify embedding skipped, status = 'completed'
  - Temp file cleanup: verify temp file deleted on success and on failure
  - WebSocket: verify FILE_EXTRACTION_COMPLETED broadcast on success
  - Meilisearch: verify index_file_from_data called with correct data
- **Status**: [ ] Not Started

---

## Phase 6: Search Integration

### Task 6.1: Extend Meilisearch Index Settings

- **File**: `fastapi-backend/app/services/search_service.py` — MODIFY
- **Action**: Update `MEILISEARCH_INDEX_SETTINGS`:
  ```python
  "searchableAttributes": [
      "title",
      "file_name",       # NEW — file search by name
      "content_plain",
  ],
  "filterableAttributes": [
      "application_id",
      "project_id",
      "user_id",
      "folder_id",
      "content_type",    # NEW — "document" or "file"
      "mime_type",       # NEW — filter by file type
      "deleted_at",
  ],
  "displayedAttributes": [
      "id",
      "title",
      "file_name",       # NEW
      "content_type",    # NEW
      "mime_type",       # NEW
      "content_plain",
      "application_id",
      "project_id",
      "user_id",
      "folder_id",
      "updated_at",
      "created_by",
  ],
  ```
- **Status**: [ ] Not Started

### Task 6.2: Add File Indexing Functions

- **File**: `fastapi-backend/app/services/search_service.py` — MODIFY
- **Action**: Add functions:

  #### `build_search_file_data(file: FolderFile, project_application_id: UUID | None = None) -> dict`
  ```python
  def build_search_file_data(file, project_application_id=None):
      application_id = file.application_id
      if not application_id and file.project_id and project_application_id:
          application_id = project_application_id
      return {
          "id": f"file:{file.id}",  # Namespace to avoid collision
          "title": file.display_name,
          "file_name": file.original_name,
          "content_plain": (file.content_plain or "")[:MAX_CONTENT_LENGTH],
          "content_type": "file",
          "mime_type": file.mime_type,
          "application_id": str(application_id) if application_id else None,
          "project_id": str(file.project_id) if file.project_id else None,
          "user_id": str(file.user_id) if file.user_id else None,
          "folder_id": str(file.folder_id),
          "created_by": str(file.created_by) if file.created_by else None,
          "updated_at": int(file.updated_at.timestamp()),
          "deleted_at": None,
      }
  ```

  #### `async index_file_from_data(data: dict) -> None`
  Same pattern as `index_document_from_data` (circuit breaker, fire-and-forget)

  #### `async remove_file_from_index(file_id: UUID) -> None`
  Same pattern as `remove_document_from_index` but uses `f"file:{file_id}"` as doc ID

  #### Update `_expand_hits()`:
  - When hit ID starts with `"file:"`: strip prefix, set content_type in result

  #### Update `check_search_index_consistency`:
  - After processing Documents, also check FolderFiles:
    - Count active FolderFiles with extraction_status='completed'
    - Compare with Meilisearch count of content_type='file' entries
    - Re-index stale file entries

- **Status**: [ ] Not Started

### Task 6.3: Extend Retrieval Service

- **File**: `fastapi-backend/app/ai/retrieval_service.py` — MODIFY
- **Action**:

  #### Update `RetrievalResult` dataclass:
  - Add `source_type: str = "document"` field
  - Add `file_id: UUID | None = None` field

  #### Update `_semantic_search()`:
  - Change the SQL query to LEFT JOIN both Documents and FolderFiles:
    ```sql
    SELECT
        dc.document_id,
        dc.file_id,
        dc.source_type,
        dc.chunk_text,
        dc.heading_context,
        dc.chunk_index,
        dc.chunk_type,
        dc.application_id,
        dc.project_id,
        COALESCE(d.title, ff.display_name) AS document_title,
        1 - (dc.embedding <=> CAST(:query_embedding AS vector)) AS similarity
    FROM "DocumentChunks" dc
    LEFT JOIN "Documents" d ON d.id = dc.document_id
    LEFT JOIN "FolderFiles" ff ON ff.id = dc.file_id
    WHERE (d.deleted_at IS NULL OR d.id IS NULL)
      AND (ff.deleted_at IS NULL OR ff.id IS NULL)
      AND ({scope_filter})
    ORDER BY dc.embedding <=> CAST(:query_embedding AS vector)
    LIMIT :limit
    ```
  - Map `source_type` and `file_id` from result rows to `_RankedResult`

  #### Update `_keyword_search()`:
  - When Meilisearch returns hits with `id` starting with `"file:"`:
    - Strip prefix, set `source_type = "file"`, set `file_id`

  #### Update `_reciprocal_rank_fusion()`:
  - Change dedup key from `document_id` to `(source_type, document_id or file_id)`
  - Propagate `source_type` and `file_id` to final `RetrievalResult`

- **Status**: [ ] Not Started

### Task 6.4: Update Blair Agent Knowledge Tools

- **File**: `fastapi-backend/app/ai/agent/tools/read_tools.py` (or wherever search_knowledge tool is) — MODIFY
- **Action**: When formatting retrieval results for Blair:
  - For `source_type == "file"`: format as `**{display_name}** ({mime_type}) — {snippet}`
  - Include source_type in the tool output so Blair knows it's a file vs document
- **Status**: [ ] Not Started

### Task 6.5: Write Phase 6 Tests

- **File**: `fastapi-backend/tests/test_file_search.py` — NEW
- **Tests**:
  - build_search_file_data: verify "file:" prefix on ID, content_type="file"
  - Index file then search by file_name → file result returned
  - Index file then search by extracted content → file result with snippet
  - Hybrid retrieval: file + document results merge correctly in RRF
  - Dedup: same file from semantic + keyword → single result with merged source
  - Soft-deleted file: not returned in search results
  - Consistency checker: detect missing file entries and re-index
  - Blair search tool: file results formatted correctly
- **Status**: [ ] Not Started

---

## Phase 7: Frontend — Upload UX & Tree Integration

### Task 7.1: Create Folder Files Hook

- **File**: `electron-app/src/renderer/hooks/use-folder-files.ts` — NEW
- **Action**: Follow pattern from `use-documents.ts`:
  ```typescript
  export interface FolderFileListItem {
    id: string
    display_name: string
    original_name: string
    file_extension: string
    mime_type: string
    file_size: number
    extraction_status: 'pending' | 'processing' | 'completed' | 'failed' | 'unsupported'
    embedding_status: 'none' | 'stale' | 'syncing' | 'synced' | 'failed'
    sort_order: number
    folder_id: string
    created_by: string | null
    created_at: string
    updated_at: string
  }

  export function useFolderFiles(folderId: string | null)
  // GET /api/folder-files?folder_id={folderId}
  // queryKey: ['folderFiles', folderId]

  export function useUploadFile()
  // POST /api/folder-files/upload (multipart FormData)
  // onSuccess: invalidate folderFiles queries, toast success

  export function useRenameFile()
  // PUT /api/folder-files/{file_id}
  // Optimistic update on folderFiles query cache

  export function useDeleteFile()
  // DELETE /api/folder-files/{file_id}
  // Optimistic removal from cache

  export function useReplaceFile()
  // POST /api/folder-files/{file_id}/replace (multipart FormData)

  export function useFileDownloadUrl(fileId: string)
  // GET /api/folder-files/{file_id}/download
  ```
- **Status**: [ ] Not Started

### Task 7.2: Add Query Keys

- **File**: `electron-app/src/renderer/lib/query-client.ts` — MODIFY
- **Action**: Add to queryKeys object:
  ```typescript
  folderFiles: (folderId: string) => ['folderFiles', folderId] as const,
  folderFile: (fileId: string) => ['folderFile', fileId] as const,
  ```
- **Status**: [ ] Not Started

### Task 7.3: Add WebSocket Message Types (Frontend)

- **File**: `electron-app/src/renderer/lib/websocket.ts` — MODIFY
- **Action**: Add enum values matching backend:
  ```typescript
  FILE_UPLOADED = 'file_uploaded',
  FILE_UPDATED = 'file_updated',
  FILE_DELETED = 'file_deleted',
  FILE_EXTRACTION_COMPLETED = 'file_extraction_completed',
  FILE_EXTRACTION_FAILED = 'file_extraction_failed',
  ```
- **Status**: [ ] Not Started

### Task 7.4: Add WebSocket Cache Invalidation

- **File**: `electron-app/src/renderer/hooks/use-websocket-cache.ts` — MODIFY
- **Action**: Add handlers in the message switch:
  ```typescript
  case MessageType.FILE_UPLOADED:
  case MessageType.FILE_UPDATED:
  case MessageType.FILE_DELETED:
    // Invalidate folderFiles query for the affected folder
    queryClient.invalidateQueries({ queryKey: ['folderFiles', data.folder_id] })
    break

  case MessageType.FILE_EXTRACTION_COMPLETED:
  case MessageType.FILE_EXTRACTION_FAILED:
    // Update specific file in cache (extraction_status, embedding_status)
    queryClient.invalidateQueries({ queryKey: ['folderFiles', data.folder_id] })
    break
  ```
- **Status**: [ ] Not Started

### Task 7.5: Extend Folder Tree Item for File Nodes

- **File**: `electron-app/src/renderer/components/knowledge/folder-tree-item.tsx` — MODIFY
- **Action**:
  - Extend `type` prop: `'folder' | 'document' | 'file'`
  - Add file icon helper:
    ```typescript
    function getFileIcon(extension: string): LucideIcon {
      const iconMap: Record<string, LucideIcon> = {
        pdf: FileText,       // red tint
        xlsx: FileSpreadsheet, xls: FileSpreadsheet, csv: FileSpreadsheet,
        docx: FileText,       // blue tint
        pptx: Presentation,   // orange tint
        vsdx: GitBranch,      // diagram icon
      }
      return iconMap[extension] || File
    }
    ```
  - For `type === 'file'`: render file icon instead of Folder/FileText, no expand chevron
  - Show extraction status indicator:
    - `pending`/`processing` → small spinner (Loader2 animated)
    - `completed` → nothing (clean)
    - `failed` → red dot with tooltip showing error
    - `unsupported` → gray dash
  - Click handler: open download URL (not navigate to editor)
  - Context menu items: Rename, Download, Replace, Delete (no "Open in Editor")
- **Status**: [ ] Not Started

### Task 7.6: Update Parent Tree to Render File Nodes

- **File**: The component that renders the folder tree (likely `knowledge-tree.tsx` or equivalent) — MODIFY
- **Action**: When rendering an expanded folder's children:
  1. Render sub-folders first (existing)
  2. Render documents (existing)
  3. Render files from `useFolderFiles(folderId)` — NEW
  - Each file renders as `<FolderTreeItem type="file" node={file} ... />`
- **Status**: [ ] Not Started

### Task 7.7: Create File Upload Zone

- **File**: `electron-app/src/renderer/components/knowledge/file-upload-zone.tsx` — NEW
- **Action**: Drag-and-drop + button component:
  - Uses HTML5 drag events: `onDragEnter`, `onDragOver`, `onDragLeave`, `onDrop`
  - Visual: dashed border overlay with "Drop files to upload" text
  - On drop: iterate `event.dataTransfer.files`, call `uploadFile.mutateAsync()` for each
  - Also render a hidden `<input type="file" multiple>` triggered by "Upload Files" button
  - Show upload progress: files queued with individual status (uploading/done/error)
  - Sequential upload (not parallel) to avoid overwhelming the server
- **Status**: [ ] Not Started

### Task 7.8: Create File Conflict Dialog

- **File**: `electron-app/src/renderer/components/knowledge/file-conflict-dialog.tsx` — NEW
- **Action**: Dialog shown when upload returns 409:
  ```
  +--------------------------------------------+
  | File "report.xlsx" already exists           |
  |                                             |
  |  [Replace]  [Keep Both]  [Cancel]           |
  +--------------------------------------------+
  ```
  - **Replace**: call `useReplaceFile().mutateAsync(existingFileId, newFile)`
  - **Keep Both**: re-upload with `display_name = "report (1).xlsx"` (increment number until unique)
  - **Cancel**: skip this file, continue with others in batch
  - Uses Radix AlertDialog (existing shadcn/ui pattern)
- **Status**: [ ] Not Started

### Task 7.9: Add "Upload Files" to Folder Context Menu

- **File**: The component that renders folder context menu — MODIFY
- **Action**: Add menu item "Upload Files..." that triggers the hidden file input
- **Status**: [ ] Not Started

### Task 7.10: Write Phase 7 Tests

- **File**: `electron-app/tests/knowledge/file-upload.spec.ts` — NEW (E2E)
- **Tests**:
  - Upload single file → appears in tree with pending status
  - Upload multiple files → all appear
  - Extraction completes → status badge updates
  - Rename file → tree updates
  - Delete file → removed from tree
  - Download file → browser opens URL
  - Conflict dialog → Replace works
  - Conflict dialog → Keep Both appends number
  - Drag-and-drop → files upload
- **Status**: [ ] Not Started

---

## Phase 8: E2E Polish & Edge Cases

### Task 8.1: File Preview Panel

- **File**: `electron-app/src/renderer/components/knowledge/file-preview-panel.tsx` — NEW
- **Action**: When a file is selected in the tree, show preview in editor panel area:
  - Images (png, jpg, gif, webp): `<img>` with presigned URL
  - PDF: `<iframe>` with presigned URL
  - Everything else: metadata card (name, size, type, extraction status, download button)
- **Status**: [ ] Not Started

### Task 8.2: Scope Summary Endpoint Update

- **File**: `fastapi-backend/app/routers/documents.py` — MODIFY
- **Action**: Update `scopes-summary` and `projects-with-content` endpoints to also count FolderFiles per folder, so applications/projects with only files (no documents) still appear in navigation
- **Status**: [ ] Not Started

### Task 8.3: Folder Deletion Cascade Verification

- **File**: `fastapi-backend/tests/test_folder_file_cascade.py` — NEW
- **Action**: Test that deleting a folder cascades correctly:
  - FolderFile records get CASCADE deleted (DB FK)
  - DocumentChunks with file_id get CASCADE deleted (DB FK)
  - Meilisearch entries need manual cleanup (not handled by DB cascade)
  - MinIO objects NOT deleted (soft delete philosophy — admin cleanup later)
- **Logic fix if needed**: Hook into folder deletion code to also call `remove_file_from_index()` for each file in the folder
- **Status**: [ ] Not Started

### Task 8.4: Search Consistency Checker Extension

- **File**: `fastapi-backend/app/services/search_service.py` — MODIFY
- **Action**: In `check_search_index_consistency()`, add a section after the document check to also verify FolderFiles:
  - Count FolderFiles with extraction_status='completed' and deleted_at IS NULL
  - Compare with Meilisearch count filtered by content_type='file'
  - Re-index stale files (same keyset pagination pattern)
- **Status**: [ ] Not Started

### Task 8.5: Admin Re-extract Endpoint

- **File**: `fastapi-backend/app/routers/folder_files.py` — MODIFY
- **Endpoint**: `POST /api/folder-files/re-extract-all` (admin only)
- **Action**: Reset all files with extraction_status='completed' to 'pending', enqueue extraction jobs. Useful when extraction libraries are upgraded.
- **Status**: [ ] Not Started

### Task 8.6: Upload Progress Indicator

- **File**: `electron-app/src/renderer/components/knowledge/file-upload-zone.tsx` — MODIFY
- **Action**: Track upload progress via `XMLHttpRequest.upload.onprogress`:
  - Show per-file progress bar in a small floating panel
  - For batch uploads: "Uploading 3/5 files..."
  - Auto-dismiss 3s after all complete
- **Status**: [ ] Not Started

### Task 8.7: Full E2E Test Suite

- **File**: `fastapi-backend/tests/test_file_uploads_e2e.py` — NEW
- **Tests**:
  - Upload PDF → extract via Docling → chunk → embed → search by content → found
  - Upload XLSX (3 sheets) → extract → all sheets in content_plain → search by cell value → found
  - Upload CSV (Latin-1, semicolon) → chardet detects → extract → search → found
  - Upload VSDX → extract shapes + connections → Blair search finds by shape text
  - Upload unsupported .zip → metadata only → search by filename → found, content search → not found
  - Upload → delete → search → not found
  - Upload → replace with new file → old content gone, new content searchable
  - Two users upload same filename to same folder → 409 conflict handled
  - Blair asks "what's in the Q4 spreadsheet?" → retrieval returns XLSX chunks → Blair explains
- **Status**: [ ] Not Started
