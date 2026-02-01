# Requirements: PM Desktop -- Knowledge Base & Documents

**Defined:** 2026-01-31
**Core Value:** Teams can create, organize, and find internal documentation without leaving their project management tool.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Migration

- [x] **MIGR-01**: Existing notes system completely removed (old code, old database tables, old API endpoints)
- [x] **MIGR-02**: Clean slate -- no backward compatibility with old notes system
- [x] **MIGR-03**: All Zustand stores used by knowledge base replaced with React Context + TanStack Query (no new Zustand stores introduced; existing stores auth-store, notes-store, notification-ui-store migrated to Context)

### Data Model

- [x] **DATA-01**: Documents support three scopes: personal (user-only), application-wide, and project-specific
- [x] **DATA-02**: Hierarchical folder structure with nested folders within each scope
- [x] **DATA-03**: Documents not in a folder appear in an "Unfiled" section
- [x] **DATA-04**: Tag system -- documents can have multiple tags, tags filterable in sidebar
- [x] **DATA-05**: Documents stored in three formats: TipTap JSON (editor), Markdown (AI), plain text (search)
- [x] **DATA-06**: Schema supports future version history (snapshot table in schema, not populated yet)
- [x] **DATA-07**: Soft delete -- deleted documents move to trash, recoverable for 30 days, auto-purged after

### Rich Text Editor

- [x] **EDIT-01**: TipTap WYSIWYG editor with toolbar: bold, italic, underline, strikethrough
- [x] **EDIT-02**: Headings (H1-H6), paragraph styles
- [x] **EDIT-03**: Bullet lists, numbered lists, indentation controls
- [x] **EDIT-04**: Interactive checklists (toggleable checkboxes)
- [x] **EDIT-05**: Tables with resizable columns (add/remove rows and columns)
- [x] **EDIT-06**: Code blocks with syntax highlighting
- [x] **EDIT-07**: Links/URLs (insertable and clickable)
- [x] **EDIT-08**: Font family selection and font size controls
- [x] **EDIT-09**: Text coloring (foreground color)
- [ ] **EDIT-10**: Images: paste from clipboard, upload button (inserts at cursor position), drag-and-drop
- [ ] **EDIT-11**: Image resizing within the editor (drag handles)
- [ ] **EDIT-12**: Image skeleton/placeholder animation while images load
- [ ] **EDIT-13**: Images stored in MinIO, referenced by URL in document content
- [x] **EDIT-14**: Word count displayed at bottom of editor

### Auto-Save

- [x] **SAVE-01**: Auto-save after 10 seconds of typing inactivity
- [x] **SAVE-02**: Save on navigate away or app close
- [x] **SAVE-03**: Status bar shows "Saving..." / "Saved Xs ago" / "Save failed" indicator
- [x] **SAVE-04**: Client-side dirty check -- skip save if content hasn't changed since last save
- [x] **SAVE-05**: Server generates Markdown and plain text from TipTap JSON on each save

### Local Caching (IndexedDB)

- [x] **CACHE-01**: Local draft persistence -- unsaved editor content auto-saved to IndexedDB so content survives crashes, navigation, and app restarts
- [x] **CACHE-02**: Document content caching -- recently opened documents load instantly from IndexedDB via TanStack Query persistence layer (per-query-persister)
- [x] **CACHE-03**: Folder tree caching -- sidebar folder tree renders immediately from IndexedDB cache, then refreshes from server in background

### Document Locking

- [ ] **LOCK-01**: When user starts editing, document is locked to them
- [ ] **LOCK-02**: Other users opening a locked document see "Being edited by [name]" and can only read
- [ ] **LOCK-03**: Lock auto-releases after 30 seconds of inactivity (saves first)
- [ ] **LOCK-04**: User can manually stop editing to release lock
- [ ] **LOCK-05**: Server-side lock expiry (Redis TTL) for crashed/disconnected clients
- [ ] **LOCK-06**: Application owners can force-take lock (saves previous editor's work first)
- [ ] **LOCK-07**: Lock heartbeat -- client sends periodic heartbeat to extend lock TTL while actively editing

### Notes Screen UI

- [x] **UI-01**: Left sidebar: search bar at top
- [x] **UI-02**: Left sidebar: folder tree below search (expand/collapse, right-click context menu for new folder, new document, rename, move, delete)
- [x] **UI-03**: Left sidebar: tag list at bottom (click to filter documents by tag)
- [ ] **UI-04**: Top bar: browser-style tabs for open documents (unsaved changes dot indicator)
- [ ] **UI-05**: Top bar: multiple documents open simultaneously, switch between tabs
- [ ] **UI-06**: Main area: document title at top (click to rename)
- [ ] **UI-07**: Main area: metadata bar (tags add/remove, scope, last edited by and when)
- [ ] **UI-08**: Main area: full rich text editor with toolbar
- [ ] **UI-09**: Bottom: word count and last saved timestamp
- [x] **UI-10**: Scope filter: show All docs / My Notes / filter by Application / filter by Project

### Embedded Docs

- [ ] **EMBED-01**: Application detail page gets a new "Docs" tab with full embedded editor experience (folder tree + editor)
- [ ] **EMBED-02**: Project detail page gets a new "Docs" tab with full embedded editor experience (folder tree + editor)

### Permissions

- [ ] **PERM-01**: Application owners can create, edit, and delete any document in their application
- [ ] **PERM-02**: Application owners can force-unlock documents
- [ ] **PERM-03**: Editors in an application/project can create new documents and edit documents in their scope
- [ ] **PERM-04**: Viewers can read documents but cannot edit
- [ ] **PERM-05**: Personal notes visible and editable only by their creator
- [ ] **PERM-06**: Document list API filters by permission (never returns documents the user cannot access)

### Search

- [ ] **SRCH-01**: Search bar searches document titles and content
- [ ] **SRCH-02**: PostgreSQL full-text search (tsvector/tsquery) for relevance-ranked results
- [ ] **SRCH-03**: Search results show document title, snippet, scope, and last edited date

### Templates

- [ ] **TMPL-01**: Built-in document templates (Meeting Notes, Design Doc, Decision Record, Project Brief, Sprint Retrospective)
- [ ] **TMPL-02**: Users can save any document as a custom template
- [ ] **TMPL-03**: "New from template" option when creating documents

### @ Mentions (Entities)

- [ ] **MENT-01**: @ mentions for Applications that create navigable links in documents
- [ ] **MENT-02**: @ mentions for Projects that create navigable links in documents
- [ ] **MENT-03**: Suggestion popup (search-as-you-type) when user types @ in editor

### Export

- [ ] **EXPR-01**: Export document as Markdown (.md file download)

## v1.x Requirements

Planned additions after core v1 ships. Not in initial roadmap.

### @ Mentions (People)

- **MENTP-01**: @ mentions for users (team members) with navigable links
- **MENTP-02**: Notification triggered when a user is @mentioned in a document

### Enhanced Search

- **SRCH-04**: Meilisearch integration for typo-tolerant full-text search
- **SRCH-05**: Search result highlighting (matching text highlighted in snippets)
- **SRCH-06**: Faceted search filtering (by tag, scope, date range)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Version History

- **HIST-01**: View document version history (list of snapshots with timestamps and authors)
- **HIST-02**: Revert document to a previous version
- **HIST-03**: Side-by-side diff view between versions

### Additional Export

- **EXPR-02**: Export document as PDF

### Comments

- **CMNT-01**: Document-level comments (not inline)

### Real-Time Collaboration

- **COLLAB-01**: Real-time collaborative editing with CRDT (Yjs) -- multiple simultaneous editors

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time CRDT collaborative editing | Lock-based editing sufficient for team sizes; massive complexity increase for edge case |
| Offline editing | Requires server connection; simplifies data consistency significantly |
| Notion-style databases in documents | PM app already has structured data (projects/tasks); documents are for prose |
| Unlimited nested page hierarchy (pages-within-pages) | Leads to lost content; folders + documents + tags provide better navigation |
| Public/external sharing links | Security implications for enterprise PM tool; export to Markdown covers sharing |
| Wiki-style graph visualization | Rarely used in practice; @ mentions + simple backlinks sufficient |
| Mobile app support | Desktop-first via Electron |
| Inline document comments/annotations | Task comments cover discussion needs; defer unless strong demand |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MIGR-01 | Phase 1 | Pending |
| MIGR-02 | Phase 1 | Pending |
| MIGR-03 | Phase 1 | Pending |
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Pending |
| DATA-04 | Phase 1 | Pending |
| DATA-05 | Phase 1 | Pending |
| DATA-06 | Phase 1 | Pending |
| DATA-07 | Phase 1 | Pending |
| EDIT-01 | Phase 3 | Complete |
| EDIT-02 | Phase 3 | Complete |
| EDIT-03 | Phase 3 | Complete |
| EDIT-04 | Phase 3 | Complete |
| EDIT-05 | Phase 3 | Complete |
| EDIT-06 | Phase 3 | Complete |
| EDIT-07 | Phase 3 | Complete |
| EDIT-08 | Phase 3 | Complete |
| EDIT-09 | Phase 3 | Complete |
| EDIT-10 | Phase 7 | Pending |
| EDIT-11 | Phase 7 | Pending |
| EDIT-12 | Phase 7 | Pending |
| EDIT-13 | Phase 7 | Pending |
| EDIT-14 | Phase 3 | Complete |
| SAVE-01 | Phase 4 | Complete |
| SAVE-02 | Phase 4 | Complete |
| SAVE-03 | Phase 4 | Complete |
| SAVE-04 | Phase 4 | Complete |
| SAVE-05 | Phase 4 | Complete |
| CACHE-01 | Phase 4 | Complete |
| CACHE-02 | Phase 2 | Pending |
| CACHE-03 | Phase 2 | Pending |
| LOCK-01 | Phase 5 | Pending |
| LOCK-02 | Phase 5 | Pending |
| LOCK-03 | Phase 5 | Pending |
| LOCK-04 | Phase 5 | Pending |
| LOCK-05 | Phase 5 | Pending |
| LOCK-06 | Phase 5 | Pending |
| LOCK-07 | Phase 5 | Pending |
| UI-01 | Phase 2 | Pending |
| UI-02 | Phase 2 | Pending |
| UI-03 | Phase 2 | Pending |
| UI-04 | Phase 6 | Pending |
| UI-05 | Phase 6 | Pending |
| UI-06 | Phase 6 | Pending |
| UI-07 | Phase 6 | Pending |
| UI-08 | Phase 6 | Pending |
| UI-09 | Phase 6 | Pending |
| UI-10 | Phase 2 | Pending |
| EMBED-01 | Phase 10 | Pending |
| EMBED-02 | Phase 10 | Pending |
| PERM-01 | Phase 8 | Pending |
| PERM-02 | Phase 8 | Pending |
| PERM-03 | Phase 8 | Pending |
| PERM-04 | Phase 8 | Pending |
| PERM-05 | Phase 8 | Pending |
| PERM-06 | Phase 8 | Pending |
| SRCH-01 | Phase 9 | Pending |
| SRCH-02 | Phase 9 | Pending |
| SRCH-03 | Phase 9 | Pending |
| TMPL-01 | Phase 9 | Pending |
| TMPL-02 | Phase 9 | Pending |
| TMPL-03 | Phase 9 | Pending |
| MENT-01 | Phase 10 | Pending |
| MENT-02 | Phase 10 | Pending |
| MENT-03 | Phase 10 | Pending |
| EXPR-01 | Phase 9 | Pending |

**Coverage:**
- v1 requirements: 61 total
- Mapped to phases: 61
- Unmapped: 0

---
*Requirements defined: 2026-01-31*
*Last updated: 2026-01-31 after roadmap revision*
