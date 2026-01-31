# Phase 1: Migration & Data Foundation - Context

**Gathered:** 2026-01-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove the old notes system entirely (code, routes, models, database tables), migrate the notes-store from Zustand to React Context + TanStack Query, and build the new document data model with scopes (personal/application/project), hierarchical folders, tags, and soft delete. This phase delivers the backend foundation and state management layer — no UI screens yet (those are Phase 2+).

</domain>

<decisions>
## Implementation Decisions

### Old Notes Removal
- Delete everything — no data migration, no backward compatibility. App is in development with no production data.
- Delete all old routes, links, sidebar references, and navigation entries that pointed to the old notes system. Dead code must go.
- Remove any unused packages/dependencies that were only needed by the old notes system (Claude identifies which ones).
- Single Alembic migration: drop old notes tables and create new document tables in the same migration. Atomic.

### Zustand Migration
- Migrate notes-store first. Auth-store and notification-ui-store can be migrated later (they're not blocking the knowledge base).
- After notes-store migration, if auth-store and notification-ui-store are straightforward to migrate, include them. Otherwise defer.
- Zustand package removal: Claude decides based on whether anything else still depends on it after migration.

### Document Schema Design
- Folder nesting limited to 5 levels maximum. Enforce server-side.
- Tags scoped per application. Projects inherit their application's tags. Personal notes have their own tag namespace.
- Default document sort within folders: by created date (newest first), with manual reordering support (sort_order column for drag-drop).
- Scope pattern: direct FK columns (application_id, project_id, user_id) with CHECK constraint ensuring exactly one is non-null. Follows existing Attachment model pattern.
- Materialized path column on folders for efficient tree queries.
- Schema includes snapshot table (empty, for future version history) — DATA-06.

### API Design
- Cursor-based pagination for document lists and search results.
- Folder tree: single API call returns full tree for a scope (GET /document-folders/tree?scope=...). Not lazy-loaded.
- Document content handling and endpoint structure: Claude decides based on codebase conventions and performance.
- URL pattern: Claude decides (flat vs nested) based on existing conventions.

### Claude's Discretion
- State management architecture for knowledge base (React Context for UI state + TanStack Query for server data, or TanStack Query only)
- Whether to follow auth-context.tsx pattern for the knowledge base context provider
- Trash location (global vs per-scope) — pick based on permission implications
- API URL structure (flat vs nested vs hybrid)
- Whether document content is a separate endpoint or included in single-document GET
- Which dependencies to remove after old notes cleanup
- Whether Zustand package is fully removable after migration

</decisions>

<specifics>
## Specific Ideas

- Research identified the existing Attachment model uses direct FK columns (not polymorphic) — documents should follow the same pattern for consistency.
- Research recommends Redis-based locks (Phase 5), so the schema should NOT include a `locked_by` column. Lock state lives in Redis.
- The `content_json` column should use NVARCHAR(MAX) / TEXT for large documents. Research estimates 50-100KB typical, but no hard limit.
- Include `row_version` INT column on documents for optimistic concurrency (useful for auto-save in Phase 4).
- Include `schema_version` INT column on documents for future TipTap schema evolution (pitfall prevention from research).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-migration-and-data-foundation*
*Context gathered: 2026-01-31*
