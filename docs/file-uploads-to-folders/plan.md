# File Uploads to Document Folders — Implementation Plan

**Created**: 2026-03-10
**Tasks**: [tasks.md](tasks.md)
**Research**: [research.md](research.md)
**Status**: In Progress

## Status Tracking

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Wire Up Existing ImportDialog | [ ] Not Started |
| 1 | Data Model & Migration | [ ] Not Started |
| 2 | Upload API & MinIO Storage | [ ] Not Started |
| 3 | Content Extraction Services | [ ] Not Started |
| 4 | Chunking Extension | [ ] Not Started |
| 5 | Background Worker Job | [ ] Not Started |
| 6 | Search Integration | [ ] Not Started |
| 7 | Frontend — Upload UI & Tree Integration | [ ] Not Started |
| 8 | E2E Polish | [ ] Not Started |

---

## Overview

Allow users to upload files (PDF, DOCX, PPTX, XLSX, CSV, VSDX, images, and any other type) into knowledge base folders. Supported formats get content extracted, chunked, and embedded for full search integration. Unsupported formats are stored as download-only.

## Supported Formats for Extraction + Embedding

| Format | Extensions | Extractor | Notes |
|--------|-----------|-----------|-------|
| PDF | .pdf | DoclingService (existing) | Already works |
| DOCX | .docx | DoclingService (existing) | Already works |
| PPTX | .pptx | DoclingService (existing) | Already works |
| XLSX/XLS | .xlsx, .xls, .xlsm, .xlsb | python-calamine + openpyxl fallback | Docling XLSX is buggy |
| CSV/TSV | .csv, .tsv | stdlib csv + chardet encoding detection | Sniffer for delimiters |
| VSDX | .vsdx | vsdx library (shapes + connections) | For Blair diagram understanding |

Everything else = download-only (stored in MinIO, name indexed in Meilisearch, no content extraction).

## New Dependencies (3 only)

| Package | Purpose | Size |
|---------|---------|------|
| `python-calamine>=0.6.0` | Fast XLSX/XLS/XLSB extraction (Rust, 7x faster than openpyxl) | ~1MB |
| `chardet>=7.0` | CSV encoding detection (98.2% accuracy, mypyc compiled) | ~2MB |
| `vsdx>=0.5` | Visio .vsdx shape text + connection extraction | ~100KB |

## Phase 0: Wire Up Existing ImportDialog (Quick Win)

**Why**: A fully-built import dialog (`import-dialog.tsx`) and backend (`ai_import.py`) already exist for PDF/DOCX/PPTX import, but the dialog is never rendered anywhere in the app. No button or menu triggers it. Wiring it up unblocks document import immediately while the full file upload system is built.

**Files to modify** (3 frontend files):
- `knowledge-sidebar.tsx` — Add Upload icon button next to FilePlus/FolderPlus buttons
- `knowledge-tree.tsx` — Add import state + render `<ImportDialog>` with scope/folder pre-filled
- `folder-context-menu.tsx` — Add "Import Document" menu item for folders, add `onImport` prop

**Can ship independently** — no backend changes needed, no dependency on other phases.

See [tasks.md](tasks.md) Phase 0 for detailed task breakdown and [research.md](research.md) §7 for ImportDialog infrastructure analysis.

---

## Architecture

```
File Upload (frontend drag-and-drop / file picker)
    |
    +-> Upload to MinIO -> create FolderFile record (status: pending)
    |
    +-> ARQ Job: extract_and_embed_file_job
         |
         +-> Download from MinIO to temp dir
         |
         +-> Format Detection (extension-based, validated by python-magic)
         |
         +-> Format Router:
         |     .pdf/.docx/.pptx --> DoclingService (existing)
         |     .xlsx/.xls/.xlsm --> SpreadsheetExtractor (calamine)
         |     .csv/.tsv --------> CsvExtractor (csv + chardet)
         |     .vsdx ------------> VisioExtractor (vsdx library)
         |     everything else --> metadata only (no extraction)
         |
         +-> Store content_plain on FolderFile
         |
         +-> Chunk extracted text (SemanticChunker.chunk_markdown)
         |
         +-> Generate embeddings -> store in DocumentChunks
         |     (source_type='file', file_id=UUID)
         |
         +-> Index in Meilisearch (same index, id="file:{uuid}")
         |
         +-> Update FolderFile status -> broadcast via WebSocket
```

## Data Model

### New Table: FolderFiles

Separate from Documents (files are not editable rich text) and Attachments (attachments are entity-scoped to tasks/comments, files are folder-scoped with full extraction pipeline).

Key columns: id, folder_id, scope FKs (exactly-one constraint), original_name, display_name, mime_type, file_size, file_extension, storage_bucket, storage_key, extraction_status, extraction_error, content_plain, extracted_metadata (JSONB), embedding_status, sha256_hash, sort_order, created_by, row_version, deleted_at.

### DocumentChunks Extension

- Add `source_type` (default 'document') and `file_id` (nullable FK)
- Make `document_id` nullable
- CHECK: exactly one of document_id/file_id must be set
- File chunks share the same HNSW vector index

## Phase Dependency Graph

```
Phase 0 (Wire ImportDialog) ← Can ship independently, no deps
    |
Phase 1 (Data Model + Migration)
  |
  +-- Phase 2 (Upload API + MinIO Storage)
  |     |
  |     +-- Phase 3 (Extraction Services)
  |     |     |
  |     |     +-- Phase 4 (Chunking Extension)
  |     |           |
  |     |           +-- Phase 5 (Worker Job)
  |     |                 |
  |     |                 +-- Phase 6 (Search Integration)
  |     |
  |     +-- Phase 7 (Frontend) ← Can start after Phase 2
  |
  +-- Phase 8 (E2E Polish) ← After all above
```

## Key Design Decisions

1. **Separate FolderFiles table** (not reusing Attachments or Documents) — Files have a distinct lifecycle: extraction, embedding, version replacement. Documents are editable rich text. Attachments are scoped to tasks/comments.

2. **Docling NOT used for XLSX/CSV** — Research found Docling XLSX has bugs: IndexError on ExcelFormatOption (Issue #2390), formula values returned as strings not computed values (Issue #1235), no sheet selection (Issue #2269). python-calamine is 7x faster, 22x less memory.

3. **Same Meilisearch index** with `content_type` filter — Avoids managing two indexes. Files use `"file:{uuid}"` as document ID to prevent collisions.

4. **Same DocumentChunks table** with `source_type` discriminator — Keeps vector search unified. One HNSW index, one retrieval query (with LEFT JOIN).

5. **Markdown-Table for spreadsheet text** (≤10 columns), Markdown-KV for wider — Research benchmarked 11 formats: Markdown-KV had 60.7% LLM accuracy, Markdown-Table 51.9% but 2x fewer tokens. Best balance.

6. **VSDX includes topology** (not just shape labels) — Blair needs connection data to explain flows. `shape.connected_shapes` + `page.get_connectors_between()` provides this.

7. **Conflict resolution at API level** — 409 Conflict response when duplicate name exists. Frontend decides Replace/Keep Both/Cancel. Keeps backend stateless.
