# File Uploads to Document Folders — Research

**Created**: 2026-03-10
**Plan**: [plan.md](plan.md)
**Tasks**: [tasks.md](tasks.md)

---

## 1. Spreadsheet Extraction (XLSX/XLS/XLSM/XLSB/CSV/TSV)

### Why NOT Docling for XLSX

Docling has critical XLSX bugs discovered during research:

| Issue | Description | Impact |
|-------|-------------|--------|
| [#2390](https://github.com/DS4SD/docling/issues/2390) | `IndexError` on `ExcelFormatOption` | Crashes on valid .xlsx files |
| [#1235](https://github.com/DS4SD/docling/issues/1235) | Formula cells return formula string, not computed value | Wrong data extracted |
| [#2269](https://github.com/DS4SD/docling/issues/2269) | No sheet selection — dumps all sheets concatenated | No control over output |

### python-calamine (Recommended Primary)

- **Package**: `python-calamine>=0.6.0`
- **Engine**: Rust calamine crate via PyO3 bindings
- **Formats**: .xlsx, .xls, .xlsm, .xlsb, .ods (all from one library)
- **Performance**: 7x faster than openpyxl, 22x less memory on large files
- **API**: `CalamineWorkbook(path)` → iterate sheets → iterate rows as `list[CalamineCell]`
- **Limitations**: Read-only (fine for extraction), no formula evaluation (returns cached computed values — better than Docling which returns formula strings)
- **Fallback**: openpyxl (already in requirements.txt) for edge cases where calamine fails

### Text Representation Format for Spreadsheets

Research benchmarked 11 serialization formats for LLM comprehension of tabular data:

| Format | LLM Accuracy | Token Efficiency | Notes |
|--------|-------------|-----------------|-------|
| Markdown-KV | 60.7% | Low (verbose) | Best accuracy but 2x tokens |
| Markdown-Table | 51.9% | High (compact) | Good balance for ≤10 cols |
| JSON-Array | 48.2% | Medium | Familiar to LLMs |
| CSV-raw | 44.1% | Highest | Loses structure for LLMs |
| HTML-Table | 43.8% | Low | Too many tokens |

**Decision**: Hybrid approach
- **≤10 columns**: Markdown pipe table (compact, good accuracy)
- **>10 columns**: Markdown-KV format (higher accuracy worth token cost)

### Row-Range Chunking for Large Spreadsheets

Large spreadsheets need chunking to fit within embedding token limits (500-800 target):

```
Algorithm:
1. Estimate tokens_per_row = avg(len(cell_values)) / 4
2. rows_per_chunk = MAX_TOKENS / tokens_per_row (clamped to 10-200)
3. For each chunk: prepend header row + row range
4. Chunk metadata: { sheet_name, row_start, row_end, total_rows }
```

Header repetition in each chunk ensures embedding context is self-contained. This reuses `SemanticChunker._split_table_by_rows()` which already implements this pattern.

### CSV Encoding Detection

- **Package**: `chardet>=7.0.0`
- **Accuracy**: 98.2% on diverse encodings (UTF-8, Latin-1, Shift-JIS, GB2312, etc.)
- **Performance**: mypyc compiled in v7.x (significant speedup over pure Python v5.x)
- **Alternative considered**: `charset-normalizer` (already a transitive dependency via requests)
  - Only 89.1% accuracy on non-UTF-8 encodings
  - chardet's 9% accuracy gap matters for real-world CSVs exported from legacy systems
- **Usage**: `chardet.detect(raw_bytes)` → decode with detected encoding → `csv.Sniffer()` for delimiter

### CSV Delimiter Detection

Standard library `csv.Sniffer().sniff(sample)` handles:
- Comma (,), Tab (\t), Semicolon (;), Pipe (|)
- Auto-detects quoting style
- Falls back to comma if detection fails
- Sample first 8KB for sniffing (sufficient for reliable detection)

---

## 2. VSDX (Visio Diagram) Extraction

### Why VSDX Needs Dedicated Support

- **Docling**: Does NOT support .vsdx format at all
- **Image rendering**: Would require a Visio renderer (not available on Linux servers) and only produces pixels — no searchable/embeddable text
- **Blair use case**: Users upload process flow diagrams, architecture diagrams, org charts. Blair needs to understand and explain the flows, not just see labels.

### vsdx Library

- **Package**: `vsdx>=0.5.0`
- **Size**: ~100KB (pure Python, minimal dependencies)
- **Capabilities**:
  - `vsdx.Document(path)` → iterate pages → iterate shapes
  - `shape.text` — shape label text
  - `shape.connected_shapes` — list of shapes connected by connectors
  - `page.get_connectors_between(shape_a, shape_b)` — connector details
  - Access to shape properties (position, size, master shape name)

### Extraction Strategy: Text + Topology

Shape labels alone have low search/embedding value ("Start", "Process", "Decision" are generic). The connection topology is what gives Blair understanding:

```
Output format (Markdown):
## Page: Main Flow

### Shapes
- [1] Start Process (FlowChart.Start)
- [2] Validate Input (FlowChart.Process)
- [3] Input Valid? (FlowChart.Decision)
- [4] Process Data (FlowChart.Process)
- [5] Return Error (FlowChart.Process)

### Connections
- [1] → [2]: (unlabeled)
- [2] → [3]: (unlabeled)
- [3] → [4]: "Yes"
- [3] → [5]: "No"
```

This gives Blair enough context to explain: "The flow starts at 'Start Process', validates input, then branches — if valid, processes data; if not, returns an error."

### Multi-Page Handling

VSDX files often have multiple pages (e.g., "Overview", "Detail", "Subprocess"). Each page is extracted separately with its own shapes and connections, then concatenated with page headers.

---

## 3. PDF/DOCX/PPTX Extraction (Existing)

### DoclingService (Already Implemented)

- **File**: `fastapi-backend/app/ai/docling_service.py`
- **Formats**: PDF, DOCX, PPTX via `_SUPPORTED_TYPES` dict
- **Output**: Markdown via `convert_to_markdown()`
- **Images**: `extract_images()` saves embedded images
- **Threading**: `asyncio.to_thread()` for CPU-bound Docling conversion
- **No changes needed**: FileExtractionService will route .pdf/.docx/.pptx to DoclingService as-is

---

## 4. Existing Infrastructure Analysis

### MinIO Storage (files.py router)

- **Current**: `fastapi-backend/app/routers/files.py` handles upload with:
  - 100MB max file size
  - RBAC permission checks
  - MinIO bucket creation and object storage
  - SHA256 hashing during upload
- **Reuse**: Same MinIO client and upload pattern for folder files
- **New bucket**: `folder-files` (separate from task attachments bucket)

### DocumentChunks Table

- **Current**: `document_id UUID NOT NULL` — FK to Documents
- **Extension needed**:
  - Make `document_id` nullable
  - Add `source_type VARCHAR(10) DEFAULT 'document'`
  - Add `file_id UUID` nullable FK to FolderFiles
  - CHECK constraint: exactly one of document_id/file_id must be set
  - Same HNSW vector index covers both document and file chunks

### Meilisearch Index

- **Current index**: `documents` with searchableAttributes=[title, content_plain]
- **Extension needed**:
  - Add `file_name` to searchableAttributes
  - Add `content_type` and `mime_type` to filterableAttributes
  - Files indexed with `id="file:{uuid}"` to avoid collision with document UUIDs
  - Same index, unified search results

### HybridRetrievalService

- **Current**: 3-source RRF (pgvector, Meilisearch, pg_trgm)
- **JOINs**: DocumentChunks → Documents (INNER JOIN)
- **Extension needed**:
  - LEFT JOIN to both Documents and FolderFiles
  - `RetrievalResult` gains `source_type` and `file_id` fields
  - RBAC filter updated to include folder file scope checks

### ARQ Worker Pattern

- **Current**: `embed_document_job` in `worker.py` (lines 323-542):
  - Redis retry guard with 30s timeout
  - ARQ dedup via `_job_id`
  - WebSocket broadcast on completion
  - Lua script for import concurrency control
- **New job**: `extract_and_embed_file_job` follows identical pattern:
  - Download from MinIO → extract → chunk → embed → index → broadcast

### SemanticChunker

- **Current**: `chunk_document()` routes to `_chunk_tiptap()` or `_chunk_canvas()`
- **Target**: 500-800 tokens (MIN_TOKENS=500, MAX_TOKENS=800), 100 token overlap
- **Has**: `_split_table_by_rows()` with header repetition — reusable for spreadsheet chunks
- **Extension needed**: New `chunk_markdown()` method for file-extracted content (plain markdown → sentence-based splitting with overlap)

---

## 5. Dependency Decisions

### Added (3 packages)

| Package | Version | Justification |
|---------|---------|---------------|
| `python-calamine` | >=0.6.0 | Rust-based XLSX/XLS reader, 7x faster than openpyxl, avoids Docling XLSX bugs |
| `chardet` | >=7.0.0 | CSV encoding detection with 98.2% accuracy (vs charset-normalizer 89.1%) |
| `vsdx` | >=0.5.0 | Visio diagram text + topology extraction (Docling doesn't support VSDX) |

### Rejected

| Package | Reason |
|---------|--------|
| `tree-sitter` | Code file extraction removed from scope |
| `charset-normalizer` | 9% lower accuracy than chardet on non-UTF-8 encodings |
| `tabulate` | stdlib csv + manual markdown formatting is sufficient |
| `python-pptx` | DoclingService already handles PPTX well |
| `PyMuPDF/fitz` | DoclingService already handles PDF well |
| Additional Docling plugins | XLSX plugin is buggy, no VSDX support |

---

## 6. Format Scope Decision

### In Scope (extraction + embedding)
PDF, DOCX, PPTX, XLSX/XLS/XLSM/XLSB, CSV/TSV, VSDX

### Out of Scope (download-only)
All other formats: images (.png, .jpg, .gif, .svg), code files, text files (.txt, .md, .log), HTML, JSON, XML, YAML, RTF, EML, EPUB, ODT, audio, video, archives, etc.

**Rationale**: The 6 supported formats cover 95%+ of business document types uploaded in PM tools. Adding more extractors increases maintenance burden with diminishing returns. Users can still upload any file type — they just won't get content search for unsupported formats.

### Future Extension Path
If needed later, add extractors incrementally without schema changes:
- Add a new extractor class implementing the same interface
- Register it in FileExtractionService's format router
- No migration needed — FolderFiles table already supports any format

---

## 7. Existing ImportDialog Infrastructure Analysis (Phase 0)

### What Already Exists

A fully-built document import pipeline exists but is **dead code** — never rendered anywhere in the app.

#### Frontend: `import-dialog.tsx` (617 lines)
- **Location**: `electron-app/src/renderer/components/ai/import-dialog.tsx`
- **Exported from**: `@/components/ai/index.ts` (registered but never imported elsewhere)
- **Features**:
  - Drag-and-drop file upload zone with click-to-browse fallback
  - File validation: accepts `.pdf`, `.docx`, `.pptx` only, 50MB max
  - Auto-generates document title from filename (strips extension, replaces `-_` with spaces)
  - Scope selector (Application / Project / Personal)
  - Folder ID pre-fill via `defaultFolderId` prop
  - Progress tracking with 5-step indicators:
    1. File uploaded (10%)
    2. Converting to markdown (40%)
    3. Processing images (60%)
    4. Creating document (80%)
    5. Generating embeddings (100%)
  - Polls job status via `useImportJobStatus(jobId)` hook
  - Auto-closes 3s after completion
  - Retry button on failure
  - "Open Document" button on success

- **Props interface**:
  ```ts
  interface ImportDialogProps {
    defaultScope?: 'application' | 'project' | 'personal'
    defaultScopeId?: string
    defaultFolderId?: string
    trigger?: React.ReactNode
    onImportComplete?: (documentId: string) => void
  }
  ```

- **Integration pattern**: Uses Radix `<Dialog>` with optional `<DialogTrigger>`. Can be controlled externally by passing a custom `trigger` prop, or rendered with the built-in "Import" button trigger.

#### Frontend Hook: `use-document-import.ts`
- **Location**: `electron-app/src/renderer/hooks/use-document-import.ts`
- **Exports**:
  - `useImportDocument()` — mutation that POSTs multipart form to `/api/ai/import`
  - `useImportJobStatus(jobId)` — query that polls `/api/ai/import/{jobId}` every 2s while processing
  - `ImportJobResponse` type

#### Backend: `ai_import.py` router
- **Location**: `fastapi-backend/app/routers/ai_import.py`
- **Endpoints**:
  - `POST /api/ai/import` — Validates file (extension, MIME, magic bytes, 50MB), streams to temp file, creates ImportJob, enqueues ARQ job, returns 202
  - `GET /api/ai/import/{job_id}` — Returns ImportJob status for polling
- **Model**: `ImportJob` in `models/import_job.py` — tracks status (pending/processing/completed/failed), progress_pct, document_id (FK to result), temp_file_path
- **Worker job**: `import_document_job` in `worker.py` — downloads temp file, calls DoclingService for PDF/DOCX/PPTX conversion, creates Document with extracted content, generates embeddings

### Why It's Dead Code

The `ImportDialog` component is exported from `@/components/ai/index.ts` but **no component in the app imports or renders it**. Specifically:
- `knowledge-sidebar.tsx` (line 179-194) has `FilePlus` and `FolderPlus` buttons but no Upload/Import button
- `knowledge-tree.tsx` renders the folder/document tree but never references ImportDialog
- `folder-context-menu.tsx` (line 76-82) has "New Folder", "New Document", "Rename", "Delete" but no "Import Document" option
- No other component in the `knowledge/` directory imports from `@/components/ai/import-dialog`

### Wiring Strategy (Phase 0)

Three touchpoints to wire up:
1. **Sidebar button** (`knowledge-sidebar.tsx`): Add Upload icon button → opens `<ImportDialog>` with scope pre-filled from `activeTab`
2. **Tree-level import** (`knowledge-tree.tsx`): When folder context menu triggers import → render `<ImportDialog>` with that folder's scope + folderId
3. **Context menu** (`folder-context-menu.tsx`): Add "Import Document" item → calls new `onImport` callback

No backend changes, no new dependencies, no migration. Pure frontend wiring of existing infrastructure.

### Scope Limitations

The existing ImportDialog only supports **PDF, DOCX, PPTX** (via DoclingService). The full file upload system (Phases 1–8) extends this to:
- XLSX/XLS/XLSM/XLSB (spreadsheets via python-calamine)
- CSV/TSV (via csv + chardet)
- VSDX (Visio via vsdx library)
- Any file type (download-only for unsupported formats)

Phase 0 delivers immediate value by unblocking the most common document import use case while the broader system is built.
