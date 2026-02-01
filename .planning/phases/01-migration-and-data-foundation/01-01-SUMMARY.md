---
phase: 01-migration-and-data-foundation
plan: 01
subsystem: notes-removal
tags: [migration, cleanup, notes, backend, frontend]
dependency-graph:
  requires: []
  provides: [clean-codebase-no-notes]
  affects: [01-02, 01-03, 01-04]
tech-stack:
  added: []
  removed: [notes-system]
  patterns: []
key-files:
  created: []
  modified:
    - fastapi-backend/app/models/__init__.py
    - fastapi-backend/app/models/application.py
    - fastapi-backend/app/models/user.py
    - fastapi-backend/app/models/attachment.py
    - fastapi-backend/app/routers/__init__.py
    - fastapi-backend/app/routers/files.py
    - fastapi-backend/app/main.py
    - fastapi-backend/alembic/env.py
    - fastapi-backend/app/schemas/file.py
    - fastapi-backend/app/websocket/__init__.py
    - fastapi-backend/app/websocket/handlers.py
    - fastapi-backend/app/websocket/manager.py
    - fastapi-backend/app/websocket/room_auth.py
    - electron-app/src/renderer/App.tsx
    - electron-app/src/renderer/contexts/index.ts
    - electron-app/src/renderer/stores/index.ts
    - electron-app/src/renderer/pages/dashboard.tsx
    - electron-app/src/renderer/components/layout/sidebar.tsx
  deleted:
    - fastapi-backend/app/models/note.py
    - fastapi-backend/app/schemas/note.py
    - fastapi-backend/app/routers/notes.py
    - fastapi-backend/tests/test_notes.py
    - electron-app/src/renderer/contexts/notes-context.tsx
    - electron-app/src/renderer/__tests__/notes-context.test.tsx
    - electron-app/src/renderer/stores/notes-store.ts
    - electron-app/src/renderer/pages/notes/index.tsx
    - electron-app/src/renderer/components/notes/note-editor.tsx
    - electron-app/src/renderer/components/notes/notes-sidebar.tsx
    - electron-app/src/renderer/components/notes/notes-tab-bar.tsx
decisions: []
metrics:
  duration: ~12 minutes
  completed: 2026-01-31
---

# Phase 1 Plan 1: Remove Old Notes System Summary

**One-liner:** Complete removal of old notes system (model, schema, router, context, store, pages, components) from both backend and frontend with all cross-references cleaned up.

## What Was Done

### Task 1: Remove old notes backend code and clean up references (7480473)

Deleted all backend notes files and cleaned every reference across the codebase:

- **Deleted files:** `note.py` model, `note.py` schema, `notes.py` router, `test_notes.py`
- **Model cleanup:** Removed `notes` relationship from Application, `created_notes` from User, `note_id` FK and `note` relationship from Attachment
- **Router/main cleanup:** Removed `notes_router` import and include
- **Files router cleanup:** Removed `note_id` query parameter, Note existence checks, note attachment logic from upload/list/delete endpoints
- **WebSocket cleanup:** Removed `handle_note_update`, `get_note_room`, `_check_note_access`, `NOTE_*` message types, `note_update_request` handler
- **Schema cleanup:** Removed `NOTE` from `EntityType` enum, removed `note_id` fields from `AttachmentCreate`/`AttachmentResponse`

### Task 2: Remove old notes frontend code and clean up references (962f477)

Deleted all frontend notes files and cleaned every reference:

- **Deleted files:** `notes-context.tsx` (700+ lines), `notes-context.test.tsx`, `notes-store.ts`, `pages/notes/index.tsx` (900+ lines), `note-editor.tsx`, `notes-sidebar.tsx`, `notes-tab-bar.tsx`
- **Deleted directories:** `pages/notes/`, `components/notes/`
- **App.tsx:** Removed `NotesProvider` wrapper from component tree
- **contexts/index.ts:** Removed all notes exports (NotesProvider, useNotesStore, selectors, types)
- **stores/index.ts:** Removed all notes re-exports and comment reference
- **dashboard.tsx:** Removed NotesPage import, 'notes' case in renderContent, 'New Note' quick action, onNavigateToNotes prop
- **sidebar.tsx:** Removed 'notes' from NavItem type, removed Notes nav item entry

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Cleaned up files.py note references**
- **Found during:** Task 1
- **Issue:** `files.py` imported `Note` model and had `note_id` query params, Note existence checks, and note attachment delete logic
- **Fix:** Removed all note-related code from files router (import, params, queries, delete logic)
- **Files modified:** `fastapi-backend/app/routers/files.py`

**2. [Rule 3 - Blocking] Cleaned up WebSocket handlers note references**
- **Found during:** Task 1
- **Issue:** `handlers.py` had `get_note_room()`, `handle_note_update()`, `note_update_request` message handler; `room_auth.py` imported Note and had `_check_note_access()`; `manager.py` had `NOTE_*` message types; `__init__.py` exported note functions
- **Fix:** Removed all note-related functions, message types, imports, and exports from websocket module
- **Files modified:** `handlers.py`, `room_auth.py`, `manager.py`, `__init__.py`

**3. [Rule 3 - Blocking] Cleaned up schemas/file.py note references**
- **Found during:** Task 1
- **Issue:** `EntityType` enum had `NOTE = "note"` value; `AttachmentCreate` and `AttachmentResponse` had `note_id` fields
- **Fix:** Removed NOTE enum value and note_id fields from attachment schemas
- **Files modified:** `fastapi-backend/app/schemas/file.py`

## Verification Results

- Backend `from app.main import app` loads successfully
- Backend `from app.models import *` loads successfully
- No Python files import Note model or notes_router
- No note_id column in attachment model
- Frontend has zero references to notes-context, notes-store, NotesProvider, useNotesStore, or NotesPage
- Notes directories (pages/notes/, components/notes/) fully removed
- Frontend typecheck passes with no notes-related errors (pre-existing unrelated errors remain)

## Lines Removed

- Backend: ~1,823 lines deleted
- Frontend: ~4,217 lines deleted
- **Total: ~6,040 lines of old notes system removed**

## Next Phase Readiness

Plan 01-01 is complete. The codebase has zero references to the old notes system. Ready for:
- **Plan 01-02:** Zustand store removal (auth-store, notification-ui-store migration)
- **Plan 01-03:** New knowledge base data model and migration
- **Plan 01-04:** Backend API for knowledge base CRUD
