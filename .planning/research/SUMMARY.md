# Project Research Summary

**Project:** Document/Knowledge Base System for PM Desktop
**Domain:** Document management, collaborative editing, knowledge systems in project management
**Researched:** 2026-01-31
**Confidence:** HIGH

## Executive Summary

This project adds a comprehensive document/knowledge base system to an existing PM Desktop application (FastAPI + React/Electron). Research analyzed how competitors (Confluence, Notion, ClickUp, GitBook) build document systems, revealing that successful products combine rich editing with smart content storage, scope-based organization, and pragmatic concurrency control.

The recommended approach uses TipTap v2 (stay on current version, migrate to v3 separately), lock-based concurrent editing with Redis TTL, and a three-format content storage pattern (TipTap JSON + Markdown + plaintext). This balances feature completeness with implementation complexity. The architecture follows the existing codebase patterns (scope columns with FKs, materialized path for folders, WebSocket for real-time updates, MinIO for images), minimizing new infrastructure (only Meilisearch for full-text search).

The primary risks are auto-save data loss during navigation/crashes, orphaned document locks blocking users, TipTap schema evolution destroying content, and permission leaks across document scopes. All are preventable with Redis-based locks with TTL/heartbeat, schema versioning from day one, local draft persistence, and scope-aware permission checks. The research flags 6 critical pitfalls with concrete prevention strategies mapped to implementation phases.

## Key Findings

### Recommended Stack

Research found that the existing stack (FastAPI, SQLAlchemy, React 18, Electron 30, TipTap 2.6, Redis, MinIO) handles 90% of requirements. The critical decision is to **stay on TipTap v2 for this milestone** rather than migrating to v3 simultaneously, reducing risk. Only 3 frontend packages and 4 backend packages are needed, plus Meilisearch infrastructure.

**Core technologies:**
- **TipTap v2.6 (stay on current)** — avoid migration complexity; v3 can be a separate milestone after knowledge base ships
- **tiptap-markdown (0.8.x)** — community standard for bidirectional markdown conversion in v2
- **use-debounce (10.1.0)** — React-hook-native debounced auto-save (2-3s delay)
- **Meilisearch (v1.12+)** — typo-tolerant full-text search with sub-50ms response times
- **meilisearch-python-sdk (5.5.2+)** — async Python client for FastAPI patterns
- **markdownify (0.14.1)** — server-side HTML-to-markdown conversion for AI/search indexing
- **bleach (6.2.0)** — server-side HTML sanitization to prevent XSS

**Architecture patterns from existing codebase:**
- Redis locks with TTL (reuse existing RedisService) — simpler and more reliable than database-based locks
- Document templates as data pattern (flag column, not separate infrastructure)
- MinIO for image storage (reuse existing MinIOService and Attachment model)
- WebSocket via existing ConnectionManager for lock status and save notifications

**What NOT to use:**
- Yjs/CRDT (@tiptap/extension-collaboration + hocuspocus) — massive complexity for lock-based editing; defer unless lock contention becomes a real problem
- TipTap v3 — breaking changes justify a separate migration milestone, not bundled with feature work

### Expected Features

Research analyzed 7 competitors (Confluence, Notion, ClickUp, Coda, GitBook, Slite, Monday.com) to identify table stakes vs. differentiators.

**Must have (table stakes):**
- Rich text editing (bold, italic, headings, lists, tables, code blocks, images, checklists)
- Auto-save with visible status indicator ("Saving..." / "Saved Xs ago" / "Error")
- Folder/hierarchy organization with document scoping to teams/projects
- Full-text search across document content
- Permissions inheriting from project/application RBAC
- Soft delete with 30-day trash and restore capability
- Images via paste/upload/drag-drop
- Concurrent access handling (lock-based is acceptable; CRDT is not required for v1)
- Document templates (5-8 built-in types like Meeting Notes, Design Doc, Sprint Retrospective)
- @ mentions (research shows user mentions are more expected than entity mentions)
- Basic export (Markdown is sufficient; PDF can wait)

**Should have (competitive advantage):**
- **Docs embedded in Application/Project detail pages** — strongest differentiator; view/edit docs in context of work without switching to separate Notes screen (Confluence/Notion require navigation)
- **Three-format content storage (JSON + Markdown + plaintext)** — enables AI agent consumption and fast search without runtime conversion
- **User-created templates** — "Save as template" on any document provides high value, low effort
- **Tag system for cross-cutting organization** — folders impose single hierarchy; tags allow multi-faceted navigation
- **@ mentions for Applications and Projects** — semantic linking stronger than generic page linking
- **Scope-aware Notes screen** — unified view of all documents filterable by scope (All / My Notes / by Application / by Project)
- **Owner lock override** — Application owners can force-take editing locks (saving previous editor's work first), preventing stuck locks

**Defer (v2+):**
- Real-time collaborative editing (CRDT/Yjs) — lock-based handles 95%+ of scenarios; add only if lock contention emerges
- Document-level comments — task comments already exist; separate comment system creates confusion
- PDF/HTML export — Markdown covers most use cases for technical teams
- Offline editing — requires conflict resolution, queue management; defer until connectivity proves unreliable
- Version history UI — schema supports it from day one, but UI can wait for user demand
- Public/external sharing links — internal-only access in v1; external sharing has security implications

### Architecture Approach

The architecture extends the existing PM Desktop patterns rather than introducing new paradigms. Documents use explicit nullable scope columns (`application_id`, `project_id`, `user_id`) with a CHECK constraint ensuring exactly one is non-null, matching the existing Attachment model pattern. Folders use materialized path for efficient subtree queries. Redis-based locking with TTL auto-expiry handles concurrent editing. WebSocket integration reuses the existing ConnectionManager with new message types for document events.

**Major components:**
1. **Backend Services** — `document_service` (CRUD + content pipeline + permissions), `document_lock_service` (Redis locks with heartbeat), `document_search_service` (Meilisearch indexing)
2. **Frontend Components** — `KnowledgeTree` (folder/doc navigation), `DocumentEditor` (TipTap + auto-save), `DocumentSearch` (full-text search UI)
3. **Data Model** — `Documents` (with `content_json`, `markdown_content`, scope FKs), `DocumentFolders` (with materialized `path`), `DocumentTags`, `DocumentTagAssignments`
4. **Content Pipeline** — Auto-save debounce (2s) -> store TipTap JSON -> background task generates Markdown + plaintext -> update Meilisearch index
5. **Locking Flow** — Client acquires Redis lock with TTL, sends heartbeat every 30s, lock auto-expires if heartbeat stops (crash/disconnect), WebSocket broadcasts lock status to all viewers

**Key patterns:**
- **Scope columns (not polymorphic FK)** — type-safe FKs, efficient indexed queries, consistent with existing Attachment pattern
- **Redis-based document locking** — O(1) atomic acquire with automatic expiry; no database write contention
- **Debounced auto-save with versioned content** — 2-3s debounce, full TipTap JSON sent per save, `row_version` for optimistic concurrency
- **Folder tree with materialized path** — single query fetches subtrees (`WHERE path LIKE '/root%'`), depth calculation is trivial
- **Lazy-load tree nodes** — fetch root-level first, expand children on demand; avoid loading entire tree

### Critical Pitfalls

Research identified 6 critical pitfalls with high impact if not addressed:

1. **Auto-save race condition causing data loss on navigation** — user navigates away before debounce fires; save silently fails during page transition. **Prevention:** Fire immediate save (not debounced) on navigation/close, use `navigator.sendBeacon()` or `fetch` with `keepalive: true`, track `isDirty` state, store local draft in IndexedDB as crash recovery, show confirmation dialog on dirty navigation.

2. **Orphaned document locks blocking all editing** — user crashes/disconnects without releasing lock; no other user can edit until admin intervention. **Prevention:** Redis locks with 60s TTL, client heartbeat every 30s refreshes TTL, lock auto-expires if heartbeat stops, provide "force unlock" for document owners, never use database-level locks.

3. **TipTap JSON schema evolution silently destroying content** — extension added/removed, documents saved under old schema load in new editor, TipTap strips unrecognized nodes, user saves and content is permanently lost. **Prevention:** Enable `enableContentCheck: true` on editor, handle `onContentError` events, store `schema_version` with each document, write migration scripts when changing extensions, never remove extensions without migrating existing documents.

4. **Orphaned images in MinIO after document deletion** — images uploaded inline via TipTap are not tracked in Attachments table, remain in MinIO after document deletion, storage grows unbounded. **Prevention:** Create Attachment record for every uploaded image (even inline), use `ondelete="CASCADE"` FKs, delete MinIO objects on document deletion, implement periodic GC job to reconcile MinIO vs. database.

5. **Permission leaks across document scopes** — personal docs visible to other users, project docs remain accessible after user removed from project, scope changes don't invalidate cached access. **Prevention:** Single centralized permission check function, explicit rules per scope, cache permissions in Redis with short TTL (60s), invalidate on scope/membership changes, backend must filter document lists (never rely on frontend filtering).

6. **Search index diverges from database (stale results)** — document updated/deleted in DB but Meilisearch still has old content, users find and click stale results. **Prevention:** Index on "meaningful save" events (close/explicit save/60s debounce) not every auto-save, check Meilisearch task status and log failures, implement periodic full reconciliation job (compare DB vs. index, delete stale entries, re-index missing), delete from Meilisearch in same request handler as DB deletion.

## Implications for Roadmap

Based on research, the dependency analysis suggests a 7-phase structure that builds foundation first, then layers on complexity:

### Phase 1: Data Model + Basic CRUD (Foundation)
**Rationale:** Database schema and core CRUD endpoints are the foundation everything else depends on. No external dependencies beyond existing stack.
**Delivers:** Alembic migration for Documents/DocumentFolders/DocumentTags tables, SQLAlchemy models, Pydantic schemas, basic REST endpoints for document/folder CRUD.
**Addresses:** Core data model for all features.
**Avoids:** Pitfall #3 (schema evolution) by including `schema_version` from day one, Pitfall #5 (permission leaks) by designing scope columns with proper constraints from start.

### Phase 2: Frontend Tree + Editor Shell
**Rationale:** Needs Phase 1 APIs. Gets the UI navigable and validates the folder tree UX before adding editing complexity.
**Delivers:** `useDocumentStore` (Zustand), TanStack Query hooks, `KnowledgeTree` component, `DocumentEditor` component (read-only rendering first).
**Addresses:** Folder navigation, document viewing.
**Uses:** TipTap v2.6 (existing), TanStack Query (existing).

### Phase 3: Auto-Save + Content Pipeline
**Rationale:** Needs Phase 2 editor component. This is the core editing experience and must be rock-solid before adding locking.
**Delivers:** Auto-save endpoint, debounced auto-save hook, TipTap JSON -> Markdown converter, background task for markdown generation, edit mode in DocumentEditor, save status indicator.
**Addresses:** Rich text editing (table stakes), auto-save (table stakes), three-format content storage (differentiator).
**Avoids:** Pitfall #1 (auto-save data loss) with `beforeunload` handlers, local draft persistence, dirty state tracking.

### Phase 4: Locking
**Rationale:** Needs Phase 3 auto-save working. Locking controls write access; save must be stable first.
**Delivers:** `document_lock_service.py`, lock REST endpoints (acquire/release/heartbeat), `use-document-lock.ts` hook, WebSocket message types for lock events, `DocumentLockBanner` component.
**Addresses:** Concurrent access handling (table stakes).
**Avoids:** Pitfall #2 (orphaned locks) with Redis TTL + heartbeat pattern.
**Uses:** Redis (existing), WebSocket ConnectionManager (existing).

### Phase 5: Images + Templates
**Rationale:** Needs Phase 3 content pipeline. Image upload reuses existing MinIO service; templates build on document CRUD.
**Delivers:** Image upload endpoint, TipTap image paste/drop handler, template CRUD, `TemplateSelector` component, built-in template seed data.
**Addresses:** Images in documents (table stakes), document templates (table stakes), user-created templates (differentiator).
**Avoids:** Pitfall #4 (orphaned MinIO images) by creating Attachment records for inline images.
**Uses:** MinIO (existing), Attachment model pattern (existing).

### Phase 6: Search
**Rationale:** Needs Phase 3 markdown generation for indexing. Can be deferred if Meilisearch infrastructure not ready.
**Delivers:** Meilisearch integration service, index sync after saves (background task), search REST endpoint, `DocumentSearch` component, DB-based fallback search (PostgreSQL FTS).
**Addresses:** Full-text search (table stakes).
**Avoids:** Pitfall #6 (stale search index) with task status verification, reconciliation job, meaningful-save-only indexing.
**Uses:** Meilisearch v1.12+, meilisearch-python-sdk.

### Phase 7: Tags + Polish
**Rationale:** Nice-to-have features that enhance UX but are not core functionality. Can be built incrementally.
**Delivers:** Tag CRUD endpoints, tag assignment, tag UI in editor/tree, drag-drop reordering, keyboard shortcuts, unified Notes screen with scope filter.
**Addresses:** Tag system (differentiator), scope-aware Notes screen (differentiator), embedded Docs tab (differentiator).

### Phase Ordering Rationale

- **Foundation first:** Phase 1 (data model) has zero external dependencies and establishes schema versioning, scope patterns from day one.
- **UI shell before editing logic:** Phase 2 (tree + read-only editor) validates navigation UX before adding complex auto-save.
- **Auto-save before locking:** Phase 3 must work perfectly before Phase 4 adds locking on top. Lock release triggers auto-save, so save must be reliable first.
- **Images/templates deferred until editing stable:** Phase 5 builds on proven auto-save pipeline.
- **Search decoupled:** Phase 6 can be skipped if Meilisearch infrastructure not ready; DB-based fallback works initially.
- **Polish last:** Phase 7 features are high-value but not blockers; can ship without them.

**Dependency chain:** Phase 1 (data) -> Phase 2 (UI shell) -> Phase 3 (editing) -> Phase 4 (locking) -> Phase 5 (images/templates) -> Phase 6 (search) -> Phase 7 (polish).

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Auto-Save + Content Pipeline):** TipTap JSON-to-Markdown conversion is custom code; may need research on edge cases (nested lists, tables, code blocks with language variants).
- **Phase 4 (Locking):** Lock takeover flow and owner override UX need design research; behavior on network reconnection after disconnect needs protocol design.
- **Phase 6 (Search):** Meilisearch index schema design (searchable vs. filterable vs. sortable attributes) and reconciliation job patterns need research.

Phases with standard patterns (skip `/gsd:research-phase`):
- **Phase 1 (Data Model + Basic CRUD):** Standard SQLAlchemy models, Alembic migration, REST CRUD — well-documented, existing patterns in codebase.
- **Phase 2 (Frontend Tree + Editor Shell):** Zustand stores, TanStack Query hooks, TipTap rendering — existing patterns in codebase (Notes, Tasks).
- **Phase 5 (Images + Templates):** MinIO upload reuses existing service, templates are data pattern (flag column) — no new concepts.
- **Phase 7 (Tags + Polish):** Many-to-many tag assignment, drag-drop reordering — standard patterns, well-documented in libraries (@dnd-kit existing).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | TipTap v2 stay-put decision verified with official upgrade guide. Meilisearch, use-debounce, markdownify all have official docs and active communities. Custom markdown converter is straightforward given TipTap JSON schema stability. |
| Features | HIGH | 7 competitor products analyzed (Confluence, Notion, ClickUp, Coda, GitBook, Slite, Monday.com). Table stakes vs. differentiators based on convergent evidence across multiple sources. MVP definition aligns with existing PM Desktop patterns. |
| Architecture | HIGH | Direct codebase analysis of existing patterns (Attachment model, Note hierarchy, ConnectionManager, RedisService, MinIOService, PermissionService). All proposed patterns match existing conventions. |
| Pitfalls | HIGH | Combination of official documentation (TipTap invalid schema handling, Meilisearch indexing best practices), community issue reports (GitHub issues on data loss, lock contention, orphaned files), and codebase analysis of existing edge case handling. |

**Overall confidence:** HIGH

### Gaps to Address

Despite high overall confidence, several areas need attention during planning/execution:

- **TipTap v2 community support timeline:** TipTap v2 is in maintenance mode with no formal EOL date. If v2 critical bugs emerge during development, migration to v3 may become urgent. **Mitigation:** Monitor TipTap GitHub for security issues; plan v3 migration as next milestone after knowledge base ships.

- **Meilisearch operational patterns at 5K users:** Research covered Meilisearch features and indexing best practices, but scaling patterns for 5K concurrent users with frequent auto-saves are less documented. **Mitigation:** Phase 6 includes reconciliation job from start; monitor task queue length and indexing lag in production; meaningful-save-only indexing (not every auto-save) prevents write amplification.

- **Lock contention frequency in real usage:** Research assumes lock-based editing is sufficient (95%+ of scenarios are single-editor-at-a-time), but actual contention rate unknown until user testing. **Mitigation:** Log lock acquisition failures and timeouts; if contention >5% of edit attempts, re-evaluate CRDT in post-v1 roadmap.

- **Electron-specific auto-save edge cases:** Auto-save race conditions on `window.onbeforeunload` differ between browsers and Electron. Research covers general patterns but not all Electron lifecycle events. **Mitigation:** Phase 3 must include Electron-specific testing for force-quit, sleep/wake, network disconnect scenarios; local draft recovery in IndexedDB as safety net.

- **Permission cache invalidation latency:** Permission checks cached in Redis with 60s TTL may have 60s lag when user removed from project or scope changed. Acceptable for most scenarios but may surprise users. **Mitigation:** Document the TTL in UX ("changes may take up to 60 seconds"); consider pushing cache invalidation events via WebSocket for immediate revocation.

## Sources

### Primary (HIGH confidence)
- [TipTap v2 to v3 Upgrade Guide](https://tiptap.dev/docs/guides/upgrade-tiptap-v2) — verified v3 breaking changes, confirmed v2 maintenance status
- [TipTap Image Extension](https://tiptap.dev/docs/editor/extensions/nodes/image), [FileHandler](https://tiptap.dev/docs/editor/extensions/functionality/filehandler), [Mention](https://tiptap.dev/docs/editor/extensions/nodes/mention) — official extension docs
- [TipTap Persistence](https://tiptap.dev/docs/editor/core-concepts/persistence), [Invalid Schema Handling](https://tiptap.dev/docs/guides/invalid-schema) — schema evolution and content error detection
- [tiptap-markdown npm](https://www.npmjs.com/package/tiptap-markdown) — v0.8.x for TipTap v2, v0.9+ for v3
- [Meilisearch Releases](https://github.com/meilisearch/meilisearch/releases), [Indexing Best Practices](https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices), [Indexing Performance](https://www.meilisearch.com/docs/learn/advanced/indexing)
- [meilisearch-python-sdk PyPI](https://pypi.org/project/meilisearch-python-sdk/), [GitHub](https://github.com/sanders41/meilisearch-python-sdk) — AsyncClient docs
- [use-debounce npm](https://www.npmjs.com/package/use-debounce), [markdownify PyPI](https://pypi.org/project/markdownify/), [bleach PyPI](https://pypi.org/project/bleach/)
- Direct codebase analysis: `fastapi-backend/app/` (models, routers, services, websocket), `electron-app/src/renderer/` (stores, hooks, components)

### Secondary (MEDIUM confidence)
- [Confluence vs Notion Comparison (The Digital Project Manager)](https://thedigitalprojectmanager.com/tools/confluence-vs-notion/), [Atlassian Official Comparison](https://www.atlassian.com/software/confluence/comparison/confluence-vs-notion)
- [Notion Auto-Save Guide](https://www.notion.com/help/guides/working-offline-in-notion-everything-you-need-to-know), [Delete & Restore](https://www.notion.com/help/duplicate-delete-and-restore-content), [Template Guide](https://www.notion.com/help/guides/the-ultimate-guide-to-notion-templates), [Links & Backlinks](https://www.notion.com/help/create-links-and-backlinks)
- [Confluence Concurrent Editing](https://confluence.atlassian.com/doc/concurrent-editing-and-merging-changes-144719.html), [Delete/Restore](https://confluence.atlassian.com/doc/delete-or-restore-a-page-139429.html), [Retention Rules](https://confluence.atlassian.com/doc/set-retention-rules-to-delete-unwanted-data-1108681072.html), [Templates](https://www.atlassian.com/software/confluence/templates), [Page Permissions](https://support.atlassian.com/confluence-cloud/docs/manage-permissions-on-the-page-level/), [RBAC (StiltSoft)](https://stiltsoft.com/blog/role-based-access-control-rbac-in-confluence-cloud/)
- [Edit Lock for Confluence (Seibert Media)](https://seibert.group/blog/en/edit-lock-for-confluence-better-protection-against-simultaneous-editing-of-confluence-pages/)
- [GitBook Official](https://www.gitbook.com/), [GitBook Review (Research.com)](https://research.com/software/reviews/gitbook)
- [ClickUp Features](https://clickup.com/features), [Meilisearch Knowledge Base Blog](https://www.meilisearch.com/blog/searchable-knowledge-base)
- [GitHub Primer Save Patterns](https://primer.style/ui-patterns/saving/), [Outline Knowledge Base GitHub](https://github.com/outline/outline), [Notion Page History (ONES Blog)](https://ones.com/blog/notion-page-history-version-control/)

### Tertiary (LOW confidence, community reports)
- [TipTap GitHub Discussion: Efficient Saving](https://github.com/ueberdosis/tiptap/discussions/5677), [Save with Delay](https://github.com/ueberdosis/tiptap/discussions/2871)
- [TipTap GitHub Issues: Data Loss on Reload #5032](https://github.com/ueberdosis/tiptap/issues/5032), [XSS via Link #3673](https://github.com/ueberdosis/tiptap/issues/3673), [XSS via getHTML() #724](https://github.com/scrumpy/tiptap/issues/724)
- [Snyk: TipTap XSS Vulnerability](https://security.snyk.io/vuln/SNYK-JS-TIPTAP-575143), [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [Meilisearch GitHub Issue: Silent Indexing Failure #4438](https://github.com/meilisearch/meilisearch/issues/4438)
- [Budibase GitHub Issue: Orphaned Files in MinIO #5564](https://github.com/Budibase/budibase/issues/5564), [MinIO Lifecycle Management](https://min.io/docs/minio/linux/administration/object-management/object-lifecycle-management.html)
- [SharePoint File Locking Troubleshooting](https://wolfesystems.com.au/troubleshooting-sharepoint-file-locking/), [Payload CMS Document Locking](https://payloadcms.com/docs/admin/locked-documents)

---
*Research completed: 2026-01-31*
*Ready for roadmap: yes*
