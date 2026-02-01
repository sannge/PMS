# Roadmap: PM Desktop -- Knowledge Base & Documents

## Overview

This roadmap delivers a complete document and notes system inside PM Desktop, replacing the existing notes system with a rich-text knowledge base organized by personal, application, and project scopes. The journey starts with migration (including Zustand removal) and data foundation, builds the editor and auto-save pipeline with IndexedDB draft persistence, layers on locking and permissions, then finishes with search, templates, embedded docs, and entity linking. Ten phases deliver 61 requirements with each phase completing a coherent, verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Migration & Data Foundation** - Remove old notes system, migrate Zustand stores to React Context + TanStack Query, and build new document schema with folders, tags, scopes, and soft delete (completed 2026-01-31)
- [x] **Phase 2: Notes Screen Shell & Folder Navigation** - Sidebar with folder tree (cached via IndexedDB), search bar, tag list, scope filtering, and document content caching (completed 2026-01-31)
- [ ] **Phase 3: Rich Text Editor Core** - Full-featured TipTap editor with text formatting, headings, lists, tables, code blocks, and links
- [ ] **Phase 4: Auto-Save & Content Pipeline** - Debounced auto-save with three-format storage (JSON, Markdown, plain text) and IndexedDB draft persistence for crash recovery
- [ ] **Phase 5: Document Locking** - Lock-based concurrent editing with heartbeat, auto-expiry, and owner override
- [ ] **Phase 6: Document Tabs & Editor UI Integration** - Browser-style document tabs, metadata bar, title editing, and editor layout
- [ ] **Phase 7: Images in Editor** - Image paste, upload, drag-and-drop, resizing, loading placeholders, and MinIO storage
- [ ] **Phase 8: Permissions** - Role-based access control for documents across all three scopes
- [ ] **Phase 9: Search, Templates & Export** - Full-text search, built-in and custom templates, and Markdown export
- [ ] **Phase 10: Embedded Docs & @ Mentions** - Docs tabs in Application/Project detail pages and entity linking via @ mentions

## Phase Details

### Phase 1: Migration & Data Foundation
**Goal**: Old notes system is gone, all Zustand stores are replaced with React Context + TanStack Query, and the new document data model is live with full schema support for scopes, folders, tags, and soft delete
**Depends on**: Nothing (first phase)
**Requirements**: MIGR-01, MIGR-02, MIGR-03, DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07
**Success Criteria** (what must be TRUE):
  1. Old notes code, API endpoints, and database tables are completely removed from the codebase
  2. All three Zustand stores (auth-store, notes-store, notification-ui-store) are replaced with React Context providers and no Zustand import exists anywhere in the codebase
  3. Documents can be created in all three scopes (personal, application, project) via API
  4. Folders can be created and nested within any scope, and documents not in a folder appear in an Unfiled section
  5. Tags can be created, assigned to documents, and queried via API
  6. Deleted documents move to trash and are recoverable; schema includes snapshot table for future version history
**Plans**: 4 plans

Plans:
- [ ] 01-01-PLAN.md — Remove old notes system (backend models/routes/schemas, frontend contexts/pages/components, all references)
- [ ] 01-02-PLAN.md — Remove Zustand store shims and update all imports to point directly at React Context providers
- [ ] 01-03-PLAN.md — Create Document, DocumentFolder, DocumentSnapshot models, Alembic migration, and CRUD endpoints
- [ ] 01-04-PLAN.md — Add tag system (DocumentTag + assignments), trash/restore/permanent-delete endpoints

### Phase 2: Notes Screen Shell & Folder Navigation
**Goal**: Users can navigate the Notes screen with a working sidebar showing folders, search bar, tag filters, and scope selection, with the folder tree and document content loading instantly from IndexedDB cache
**Depends on**: Phase 1
**Requirements**: UI-01, UI-02, UI-03, UI-10, CACHE-02, CACHE-03
**Success Criteria** (what must be TRUE):
  1. Notes screen renders with a left sidebar containing a search bar at the top
  2. Folder tree displays in sidebar with expand/collapse and right-click context menu (new folder, new document, rename, move, delete)
  3. Tag list appears in sidebar and clicking a tag filters the document list
  4. Scope filter works: user can switch between All docs, My Notes, by Application, and by Project
  5. Folder tree renders immediately from IndexedDB cache on screen open, then refreshes from server in background (no loading spinner on repeat visits)
  6. Recently opened documents load instantly from IndexedDB cache via TanStack Query persistence (per-query-persister integration for document queries)
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — Notes screen layout, KnowledgeBaseContext for UI state, TanStack Query hooks with IndexedDB persistence for documents/folders/tags
- [ ] 02-02-PLAN.md — Folder tree component with expand/collapse, right-click context menu, CRUD actions, and IndexedDB cache integration
- [ ] 02-03-PLAN.md — Scope filter dropdown and tag filter list sidebar sections

### Phase 3: Rich Text Editor Core
**Goal**: Users can create and edit documents with a full-featured rich text editor covering all standard formatting
**Depends on**: Phase 2
**Requirements**: EDIT-01, EDIT-02, EDIT-03, EDIT-04, EDIT-05, EDIT-06, EDIT-07, EDIT-08, EDIT-09, EDIT-14
**Success Criteria** (what must be TRUE):
  1. Editor toolbar provides bold, italic, underline, strikethrough, font family, font size, and text color controls
  2. User can insert headings (H1-H6), bullet lists, numbered lists, and interactive checklists
  3. User can insert and edit tables with resizable columns and add/remove rows and columns
  4. User can insert code blocks with syntax highlighting and clickable links
  5. Word count displays at the bottom of the editor
**Plans**: 4 plans

Plans:
- [ ] 03-01-PLAN.md — Install packages, create extension factory, types, CSS, and DocumentEditor with basic text formatting toolbar
- [ ] 03-02-PLAN.md — Add heading dropdown (H1-H6), lists, checklists, code block button, and indent controls to toolbar
- [ ] 03-03-PLAN.md — Add table insert button and contextual table controls to toolbar
- [ ] 03-04-PLAN.md — Add link dialog, font family/size dropdowns, and word count status bar

### Phase 4: Auto-Save & Content Pipeline
**Goal**: Documents auto-save reliably, content is stored in three formats for editor, AI, and search consumption, and unsaved drafts persist locally in IndexedDB to survive crashes and navigation
**Depends on**: Phase 3
**Requirements**: SAVE-01, SAVE-02, SAVE-03, SAVE-04, SAVE-05, CACHE-01
**Success Criteria** (what must be TRUE):
  1. Document auto-saves after 10 seconds of typing inactivity without user intervention
  2. Document saves immediately when user navigates away or closes the app (no data loss)
  3. Status bar shows real-time save state: "Saving...", "Saved Xs ago", or "Save failed"
  4. Redundant saves are skipped when content has not changed (client-side dirty check)
  5. Server generates Markdown and plain text from TipTap JSON on each save (verifiable via API)
  6. If the app crashes or the user force-quits mid-edit, reopening the document recovers the unsaved draft from IndexedDB with a prompt to restore or discard
**Plans**: 4 plans

Plans:
- [ ] 04-01-PLAN.md — Auto-save PUT endpoint with optimistic concurrency and useAutoSave hook with 10s debounce and dirty tracking
- [ ] 04-02-PLAN.md — IndexedDB draft persistence (draft-db store, useDraft hook with 2s auto-buffer, restore prompt on reopen)
- [ ] 04-03-PLAN.md — Save on navigate away, Electron before-quit IPC coordination, and SaveStatus indicator component
- [ ] 04-04-PLAN.md — TDD: Custom Python TipTap JSON to Markdown and plain text converter

### Phase 5: Document Locking
**Goal**: Only one user can edit a document at a time, with reliable lock management that prevents stuck locks
**Depends on**: Phase 4
**Requirements**: LOCK-01, LOCK-02, LOCK-03, LOCK-04, LOCK-05, LOCK-06, LOCK-07
**Success Criteria** (what must be TRUE):
  1. When a user starts editing, the document is locked and other users see "Being edited by [name]" in read-only mode
  2. Lock auto-releases after 30 seconds of inactivity (saving the document first)
  3. User can manually click "stop editing" to release the lock
  4. If a client crashes or disconnects, the server-side Redis TTL expires the lock automatically
  5. Application owners can force-take the lock (previous editor's work is saved first)
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md — Backend lock service (Redis atomic ops + Lua scripts), Pydantic schemas, REST endpoints, WebSocket message types and broadcast handler
- [ ] 05-02-PLAN.md — Frontend useDocumentLock hook (heartbeat, inactivity timer, WebSocket listener), LockBanner component, editor integration

### Phase 6: Document Tabs & Editor UI Integration
**Goal**: Users can work with multiple documents simultaneously using browser-style tabs with full metadata visibility
**Depends on**: Phase 4
**Requirements**: UI-04, UI-05, UI-06, UI-07, UI-08, UI-09
**Success Criteria** (what must be TRUE):
  1. User can open multiple documents as tabs in the top bar and switch between them
  2. Tabs show an unsaved changes dot indicator when a document has pending changes
  3. Document title is displayed at the top and is editable by clicking on it
  4. Metadata bar shows tags (add/remove), scope, and "last edited by" with timestamp
  5. Bottom bar shows word count and last saved timestamp
**Plans**: 3 plans

Plans:
- [ ] 06-01-PLAN.md — Extend KnowledgeBaseContext with tab state + build DocumentTabBar and DocumentTabItem components
- [ ] 06-02-PLAN.md — Document title editing, metadata bar with tag management, and status bar with word count
- [ ] 06-03-PLAN.md — DocumentPanel integration, Notes page layout wiring, sidebar tab-opening behavior

### Phase 7: Images in Editor
**Goal**: Users can add and resize images in documents via paste, upload, or drag-and-drop with images stored in MinIO
**Depends on**: Phase 4
**Requirements**: EDIT-10, EDIT-11, EDIT-12, EDIT-13
**Success Criteria** (what must be TRUE):
  1. User can paste an image from clipboard and it appears at the cursor position in the document
  2. User can upload an image via button or drag-and-drop into the editor
  3. Images can be resized within the editor using drag handles
  4. Images show a skeleton/placeholder animation while loading and are stored in MinIO (referenced by URL)
**Plans**: TBD

Plans:
- [ ] 07-01: Image upload endpoint (MinIO) and TipTap image extension with paste/drop/upload
- [ ] 07-02: Image resizing handles and loading placeholder animation

### Phase 8: Permissions
**Goal**: Document access is enforced by role -- owners manage everything, editors create and edit, viewers read, personal notes are private
**Depends on**: Phase 1
**Requirements**: PERM-01, PERM-02, PERM-03, PERM-04, PERM-05, PERM-06
**Success Criteria** (what must be TRUE):
  1. Application owners can create, edit, delete any document in their application and force-unlock documents
  2. Editors can create and edit documents within their application/project scope
  3. Viewers can read documents in their scope but cannot edit or create
  4. Personal notes are visible and editable only by their creator -- no other user can see them
  5. Document list API never returns documents the requesting user cannot access
**Plans**: TBD

Plans:
- [ ] 08-01: Centralized permission check service for documents
- [ ] 08-02: Permission enforcement on all document and folder API endpoints
- [ ] 08-03: Frontend permission-aware UI (hide/disable edit controls based on role)

### Phase 9: Search, Templates & Export
**Goal**: Users can find documents by searching content, create documents from templates, and export to Markdown
**Depends on**: Phase 4
**Requirements**: SRCH-01, SRCH-02, SRCH-03, TMPL-01, TMPL-02, TMPL-03, EXPR-01
**Success Criteria** (what must be TRUE):
  1. Search bar returns relevant results across document titles and content using PostgreSQL full-text search
  2. Search results show document title, content snippet, scope, and last edited date
  3. User can create a new document from built-in templates (Meeting Notes, Design Doc, Decision Record, Project Brief, Sprint Retrospective)
  4. User can save any document as a custom template and create new documents from custom templates
  5. User can export any document as a Markdown .md file download
**Plans**: TBD

Plans:
- [ ] 09-01: PostgreSQL full-text search endpoint and search results UI
- [ ] 09-02: Built-in templates, custom template save, and "new from template" flow
- [ ] 09-03: Markdown export endpoint and download button

### Phase 10: Embedded Docs & @ Mentions
**Goal**: Users can access and edit documents directly within Application and Project detail pages, and link to entities with @ mentions
**Depends on**: Phase 6, Phase 8
**Requirements**: EMBED-01, EMBED-02, MENT-01, MENT-02, MENT-03
**Success Criteria** (what must be TRUE):
  1. Application detail page has a "Docs" tab with folder tree and full editor experience
  2. Project detail page has a "Docs" tab with folder tree and full editor experience
  3. User can type @ in the editor to get a search-as-you-type popup listing Applications and Projects
  4. Selecting an @ mention inserts a navigable link that takes the user to the referenced Application or Project
**Plans**: TBD

Plans:
- [ ] 10-01: Embedded docs tab component for Application and Project detail pages
- [ ] 10-02: @ mention TipTap extension with suggestion popup and navigable links

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10
Note: Phases 5, 6, 7, 9 all depend on Phase 4 and can potentially be parallelized after Phase 4 completes. Phase 8 depends only on Phase 1. Phase 10 depends on Phase 6 and Phase 8.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Migration & Data Foundation | 4/4 | Complete | 2026-01-31 |
| 2. Notes Screen Shell & Folder Navigation | 3/3 | Complete | 2026-01-31 |
| 3. Rich Text Editor Core | 0/4 | Planned | - |
| 4. Auto-Save & Content Pipeline | 0/4 | Planned | - |
| 5. Document Locking | 0/2 | Planned | - |
| 6. Document Tabs & Editor UI Integration | 0/3 | Not started | - |
| 7. Images in Editor | 0/2 | Not started | - |
| 8. Permissions | 0/3 | Not started | - |
| 9. Search, Templates & Export | 0/3 | Not started | - |
| 10. Embedded Docs & @ Mentions | 0/2 | Not started | - |
