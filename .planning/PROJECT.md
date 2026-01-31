# PM Desktop — Knowledge Base & Documents

## What This Is

A document and notes system inside the PM Desktop project management app. It's the team's internal documentation hub — meeting notes, design docs, decision records, personal scratch notes — all organized alongside existing applications and projects. Documents live in three scopes (personal, application, project), use a rich text editor with auto-save, and store content in multiple formats to power a future AI knowledge agent.

## Core Value

Teams can create, organize, and find internal documentation without leaving their project management tool. Documentation lives alongside the work it describes.

## Requirements

### Validated

<!-- Existing capabilities inferred from codebase -->

- ✓ User authentication with JWT (login, register, session persistence) — existing
- ✓ Application/Project/Task hierarchy with RBAC (Owner/Editor/Viewer) — existing
- ✓ Real-time WebSocket infrastructure (rooms, presence, pub/sub via Redis) — existing
- ✓ File uploads to MinIO (S3-compatible object storage) — existing
- ✓ TipTap rich text editor integration — existing
- ✓ Notification system (in-app + desktop) — existing
- ✓ Kanban board with drag-and-drop — existing
- ✓ Comments and checklists on tasks — existing
- ✓ TanStack Query with IndexedDB persistence — existing

### Active

<!-- Current scope: Knowledge Base / Documents system -->

**Document Organization**

- [ ] Three document scopes: Personal notes, Application docs, Project docs
- [ ] Hierarchical folder structure (nested folders within each scope)
- [ ] Unfiled section for documents not in any folder
- [ ] Tag system for cross-cutting organization (assign multiple tags, filter by tag)
- [ ] Scope filter on Notes screen: All / My Notes / by Application / by Project

**Notes Screen UI**

- [ ] Left sidebar: search bar, folder tree (expand/collapse, right-click context menu), tag list
- [ ] Top bar: browser-style tabs for open documents (unsaved indicator dot, switch between docs)
- [ ] Main area: document title (click to rename), metadata bar (tags, scope, last edited by/when), full editor, word count + last saved status

**Embedded Docs Tab**

- [ ] Application detail page: new "Docs" tab with full embedded editor experience (folder tree + editor)
- [ ] Project detail page: new "Docs" tab with full embedded editor experience

**Rich Text Editor**

- [ ] TipTap WYSIWYG editor with toolbar: bold, italic, headings, bullet lists, numbered lists, checklists, tables, images, code blocks, links
- [ ] Tables with resizable columns
- [ ] Images: paste from clipboard, upload button (inserts at cursor), drag-and-drop into editor
- [ ] Image resizing in editor
- [ ] Image skeleton/placeholder animation while loading
- [ ] Images stored in MinIO, referenced by URL in document

**Auto-Save & Locking**

- [ ] Auto-save after 10 seconds of typing inactivity
- [ ] Save on navigate away / app close
- [ ] Status bar: "Saved 2s ago" indicator
- [ ] Lock-based concurrent access: editing user holds lock, others see "Being edited by [name]" (read-only)
- [ ] Auto-release lock after 30 seconds of inactivity (saves first)
- [ ] Manual "stop editing" to release lock
- [ ] Server-side lock expiry (30s) for crashed clients
- [ ] Owner override: application owners can force-take lock (saves previous editor's work first)

**Content Storage**

- [ ] Editor format: TipTap JSON stored in database (primary, what auto-save writes)
- [ ] Markdown: generated server-side from TipTap JSON on save (for future AI agent)
- [ ] Plain text: generated server-side on save (for search indexing)
- [ ] Client-side dirty check to skip redundant saves

**Permissions**

- [ ] Application owners: CRUD any document in their application, force-unlock
- [ ] Editors (application/project): create and edit documents in their scope
- [ ] Viewers: read-only access to documents in their scope
- [ ] Personal notes: only creator can see or edit

**Search**

- [ ] Search bar searches document titles and content
- [ ] Results ranked by relevance
- [ ] Basic search in v1 (database-level), Meilisearch upgrade in later phase

**Templates**

- [ ] Built-in document templates (Meeting Notes, Design Doc, Decision Record, etc.)
- [ ] Users can save any document as a custom template
- [ ] "New from template" option when creating documents

**Document Linking**

- [ ] @ mentions for Applications and Projects that create navigable links within documents

**Trash / Soft Delete**

- [ ] Deleted documents move to trash (recoverable for 30 days)
- [ ] Auto-purge after 30 days

**Export**

- [ ] Export document as Markdown (.md file download)

**Migration**

- [ ] Remove existing notes system entirely (old code, old database tables)
- [ ] Fresh start — no backward compatibility needed

### Out of Scope

- Real-time collaborative editing (CRDT/Yjs) — lock-based editing is sufficient for team size; revisit if needed
- Offline editing — requires server connection; simplifies data consistency
- Version history UI — design schema to support it later, but no UI in v1
- PDF/HTML export — markdown export covers the need for now
- Document comments/annotations — documents are the content, use task comments for discussion
- @ mentions for Tasks — only Application and Project linking in v1
- Mobile app support — desktop-first via Electron

## Context

**Existing codebase:** Full-stack Electron (React/TypeScript) + FastAPI (Python) project management app with Jira-like task management, kanban boards, real-time WebSocket infrastructure, and MinIO file storage. TipTap editor is already a dependency.

**Scale target:** 5,000 concurrent users, tens of thousands of documents. Database queries need pagination and indexing. Auto-save writes ~1MB(no limit?) TipTap JSON per save (images stored separately in MinIO).

**Future AI agent:** Documents will feed a knowledge agent that answers questions and creates tasks from project documentation. Markdown format is stored specifically for this. Schema and content format decisions should keep AI consumption in mind (clean markdown, section-based splitting by headings).

**Storage architecture:**

- TipTap JSON (editor format) → PostgreSQL (primary store, what auto-save writes)
- Images → MinIO (uploaded on insert, referenced by URL in document JSON)
- Markdown → generated server-side on save, stored alongside JSON (for AI)
- Plain text → generated server-side on save (for search indexing)
- Auto-save only writes document JSON (~1MB(no limit?)), not image binaries
- Schema should support version history addition later (snapshot table pattern)
- How to handle very large documents?

## Constraints

- **Tech stack**: Must use existing stack — FastAPI, SQLAlchemy, React, TipTap, MinIO, Redis, PostgreSQL
- **Performance**: <200ms API reads, auto-save must not block UI, document locking must be reliable under 5K concurrent users
- **Permissions**: Must integrate with existing RBAC system (Application/Project membership + Owner/Editor/Viewer roles)
- **Database**: PostgreSQL with async SQLAlchemy; Alembic migrations required
- **Editor**: TipTap 2.6+ with existing extensions as base; new extensions for tables, images, templates

## Key Decisions

| Decision                                      | Rationale                                                                                          | Outcome   |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------- |
| TipTap rich text over markdown editor         | Resizable images/tables require WYSIWYG; TipTap already in stack; generate markdown on save for AI | — Pending |
| Lock-based editing over CRDT                  | Simpler architecture, sufficient for team sizes; CRDT adds significant complexity                  | — Pending |
| Images in MinIO, JSON in PostgreSQL           | Auto-save only writes lightweight JSON; images uploaded once on insert                             | — Pending |
| Three content formats (JSON + MD + plaintext) | JSON for editor, MD for future AI agent, plaintext for search                                      | — Pending |
| Soft delete with 30-day auto-purge            | Safety net for accidental deletion without permanent trash accumulation                            | — Pending |
| Embedded editor in App/Project detail pages   | Users can work with docs in context without switching to Notes screen                              | — Pending |

---

_Last updated: 2026-01-31 after initialization_
