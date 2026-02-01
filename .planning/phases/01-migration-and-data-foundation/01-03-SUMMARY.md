---
phase: 01-migration-and-data-foundation
plan: 03
subsystem: knowledge-base-data-model
tags: [models, schemas, api, crud, documents, folders, migration, alembic]
dependency-graph:
  requires: [01-01]
  provides: [document-crud-api, folder-tree-api, document-data-model]
  affects: [01-04, 02-01, 02-02, 04-01]
tech-stack:
  added: []
  removed: [notes-table]
  patterns: [materialized-path, optimistic-concurrency, cursor-pagination, soft-delete, three-format-content]
key-files:
  created:
    - fastapi-backend/app/models/document.py
    - fastapi-backend/app/models/document_folder.py
    - fastapi-backend/app/models/document_snapshot.py
    - fastapi-backend/app/schemas/document.py
    - fastapi-backend/app/schemas/document_folder.py
    - fastapi-backend/app/services/document_service.py
    - fastapi-backend/app/routers/documents.py
    - fastapi-backend/app/routers/document_folders.py
    - fastapi-backend/alembic/versions/20260131_drop_notes_create_documents.py
  modified:
    - fastapi-backend/app/models/__init__.py
    - fastapi-backend/app/schemas/__init__.py
    - fastapi-backend/app/routers/__init__.py
    - fastapi-backend/app/main.py
    - fastapi-backend/alembic/env.py
decisions:
  - "Materialized path pattern for folder tree queries (no recursive CTEs needed)"
  - "Three-format content storage: JSON (editor), Markdown (AI), plain text (search)"
  - "Cursor pagination with base64-encoded JSON cursor (created_at + id)"
  - "DocumentSnapshot table created as empty placeholder for Phase 4+ version history"
metrics:
  duration: ~7 minutes
  completed: 2026-01-31
---

# Phase 1 Plan 3: Knowledge Base Data Model and CRUD API Summary

**One-liner:** Document/folder data model with 3-scope CHECK constraints, materialized path folders (depth <= 5), cursor-paginated CRUD API, optimistic concurrency, and content conversion stubs for Phase 4.

## What Was Done

### Task 1: Create Models and Alembic Migration (900c1ff)

Created three SQLAlchemy models following existing codebase patterns:

- **Document model** (`document.py`): UUID PK, three scope FKs (application/project/user) with CHECK constraint enforcing exactly one non-null, folder_id FK (SET NULL on delete), title, three content columns (JSON/Markdown/plain), sort_order, created_by, row_version (optimistic concurrency), schema_version (TipTap evolution), deleted_at (soft delete), timestamps. Composite indexes for app+folder and project+folder queries.

- **DocumentFolder model** (`document_folder.py`): UUID PK, self-referential parent_id (CASCADE delete), materialized_path (String(4000)), depth, name, sort_order, three scope FKs with CHECK constraint, created_by, timestamps. Relationships: parent, children (dynamic), documents (dynamic), creator.

- **DocumentSnapshot model** (`document_snapshot.py`): UUID PK, document_id FK (CASCADE), content_json, snapshot_type (auto/manual/restore), created_by, created_at. Empty placeholder for Phase 4+ version history.

- **Alembic migration** (`20260131_drop_notes_create_documents.py`): Atomically drops note_id column and FK from Attachments, drops Notes table and indexes, creates DocumentFolders/Documents/DocumentSnapshots with all constraints, indexes, and server defaults. Fully reversible downgrade recreates Notes table stub.

### Task 2: Schemas, Service, and CRUD Endpoints (7ffdc09)

Created complete API layer:

- **Document schemas** (`schemas/document.py`): DocumentCreate (scope + scope_id pattern), DocumentUpdate (optimistic concurrency via row_version), DocumentResponse (full content), DocumentListItem (no content), DocumentListResponse (cursor pagination).

- **Folder schemas** (`schemas/document_folder.py`): FolderCreate, FolderUpdate, FolderResponse, FolderTreeNode (self-referential with children list and document_count).

- **Document service** (`services/document_service.py`): validate_scope, set_scope_fks, get_scope_filter, encode_cursor/decode_cursor (base64 JSON), validate_folder_depth (max 5), compute_materialized_path, update_descendant_paths (bulk SQL update), convert_tiptap_to_markdown (stub), convert_tiptap_to_plain_text (stub).

- **Document router** (`routers/documents.py`): GET /api/documents (cursor pagination, scope+folder filter), POST /api/documents (scope validation), GET /api/documents/{id} (full content), PUT /api/documents/{id} (optimistic concurrency 409), DELETE /api/documents/{id} (soft delete).

- **Folder router** (`routers/document_folders.py`): GET /api/document-folders/tree (full tree with doc counts), POST /api/document-folders (depth validation), PUT /api/document-folders/{id} (path recompute on move), DELETE /api/document-folders/{id} (cascade).

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- Models import successfully: `from app.models import Document, DocumentFolder, DocumentSnapshot`
- CHECK constraints verified: `ck_documents_exactly_one_scope`, `ck_document_folders_exactly_one_scope`
- Composite indexes verified: `ix_documents_app_folder`, `ix_documents_project_folder`
- Migration file parses correctly with proper revision chain
- All 9 document/folder API routes registered in FastAPI app
- Schemas import correctly from `app.schemas`
- Conversion stubs return empty strings as expected
- Server boots without errors

## Next Phase Readiness

Plan 01-03 is complete. The data foundation for the knowledge base is established. Ready for:
- **Plan 01-04:** Frontend knowledge base components (tree view, document editor)
- **Phase 2:** TipTap editor integration, folder tree UI
- **Phase 4:** Auto-save pipeline will implement the conversion stubs
