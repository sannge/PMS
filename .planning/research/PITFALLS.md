# Pitfalls Research

**Domain:** Document/Knowledge Base System (added to existing PM app)
**Researched:** 2026-01-31
**Confidence:** HIGH (combination of codebase analysis, official documentation, and community reports)

## Critical Pitfalls

### Pitfall 1: Auto-Save Race Condition Causing Data Loss on Navigation

**What goes wrong:**
User edits a document, then navigates away (clicks another document, switches pages, or closes the Electron window) before the 10-second inactivity debounce fires. The pending save is lost. Worse: if the frontend fires a save on `beforeunload` but the network request does not complete before the page transitions, the save silently fails. In Electron, `window.onbeforeunload` behavior differs from browsers -- the app may close before the `fetch` completes.

**Why it happens:**
The 10-second inactivity timer means there is always a window where unsaved content exists only in memory. Developers test with fast local servers and never experience the gap. In production with network latency, the window is larger.

**How to avoid:**
- Fire an immediate save (not debounced) on document switch, page navigation, and Electron `before-quit` / `will-quit` events. Use `navigator.sendBeacon()` or `fetch` with `keepalive: true` for unload saves.
- Track a `isDirty` boolean in the editor store. Show a confirmation dialog if the user navigates away while dirty.
- On the backend, return a `version` or `updated_at` timestamp in the save response. The frontend must verify the response arrived -- if not, mark the document as "save failed" and prompt retry.
- Store a local draft in IndexedDB or `localStorage` as a crash recovery mechanism. On next document open, compare local draft timestamp with server `updated_at`.

**Warning signs:**
- QA reports that "sometimes my edits disappear" but it cannot be reproduced reliably.
- No `beforeunload` or Electron lifecycle handlers in the editor component.
- Save endpoint returns 200 but frontend does not verify or acknowledge it.
- No dirty-state indicator in the UI.

**Phase to address:**
Phase 1 (Core CRUD + Auto-save). This must be correct from the start -- retrofitting crash recovery is much harder.

---

### Pitfall 2: Orphaned Document Locks Blocking All Editing

**What goes wrong:**
User A opens a document, acquiring an exclusive lock. User A's machine crashes, network disconnects, or they simply close the Electron app without the unlock request firing. The lock remains in the database (or Redis). No other user can edit the document until an admin manually clears the lock. At scale (5K users), orphaned locks accumulate and cause support tickets.

**Why it happens:**
Lock-based editing relies on the client sending an explicit "unlock" request. Any interruption -- crash, network failure, force-quit, sleep/hibernate -- prevents the unlock from firing. The existing Redis presence system (sorted sets with timestamps) shows the team is aware of heartbeat patterns, but document locks need their own TTL/heartbeat mechanism.

**How to avoid:**
- Use Redis keys with TTL for locks, not database rows. A lock key like `doc:lock:{document_id}` with a 60-second TTL auto-expires if the client stops refreshing.
- The client sends a heartbeat every 30 seconds to refresh the lock TTL. If the heartbeat stops (crash, disconnect), the lock expires within 60 seconds.
- Provide a "force unlock" capability for document owners (not just system admins). When force-unlocking, warn that the previous editor's unsaved changes will be lost.
- Implement a "lock takeover" flow: User B requests takeover, User A gets a WebSocket notification with a 30-second countdown to save and release. If User A does not respond (crashed), the lock transfers automatically.
- Never use database-level locks (row locks) for this -- use application-level locks in Redis.

**Warning signs:**
- Lock records in the database with no corresponding active WebSocket connection.
- Support tickets about "document stuck in locked state."
- No TTL or expiration on lock records.
- Lock release logic only in `componentWillUnmount` or `useEffect` cleanup (which does not fire on crashes).

**Phase to address:**
Phase 2 (Lock Management). Must be implemented before any multi-user testing.

---

### Pitfall 3: TipTap JSON Schema Evolution Silently Destroys Content

**What goes wrong:**
A TipTap extension is added, modified, or removed (e.g., adding a `taskList` extension, changing how `image` nodes store attributes). Documents saved under the old schema are loaded into the new editor. TipTap silently strips any nodes/marks it does not recognize. The user sees their content is missing, saves the document, and the stripped content is now permanently lost in the database. This is especially dangerous because the content loss is invisible until the user notices something is missing.

**Why it happens:**
TipTap enforces strict schema adherence by default. `enableContentCheck` is `false` by default for backward compatibility. Teams add extensions during development without considering that production documents were created without those extensions -- or vice versa, they remove an extension that existing documents use.

**How to avoid:**
- Enable `enableContentCheck: true` on the editor instance and handle `onContentError` events. Log these events and prevent auto-save when content errors are detected.
- Treat TipTap extension changes as database migrations. When adding/removing/modifying extensions, write a migration script that transforms existing documents' JSON to match the new schema.
- Store the schema version alongside each document (e.g., `schema_version` column). When loading a document with an older schema version, run the migration pipeline before rendering.
- Never remove a TipTap extension without first migrating all documents that use nodes from that extension.
- Keep a `RawDocumentViewer` component that can display the raw JSON for debugging when content errors are detected.

**Warning signs:**
- No `schema_version` field on the document model.
- Extensions being added/removed without a corresponding data migration.
- No `enableContentCheck` in the editor configuration.
- User reports of "my content disappeared" after a frontend deployment.

**Phase to address:**
Phase 1 (Core Editor Setup). Schema versioning must be in the data model from the start.

---

### Pitfall 4: Orphaned Images in MinIO After Document Deletion

**What goes wrong:**
A user uploads images into a document (stored in MinIO's `pm-images` bucket under a path like `document/{document_id}/{uuid}_{filename}`). The document is later deleted (or the images are removed from the document content by editing). The MinIO objects remain. Over months, storage grows unbounded. The existing `Attachment` model tracks files with `minio_bucket` and `minio_key`, but images embedded inline in TipTap JSON (via the `Image` extension) are typically not tracked as `Attachment` records -- they are just URLs inside the JSON content.

**Why it happens:**
The MinIO service has `delete_file()` but it requires knowing the exact bucket and key. When a document is deleted via cascade, the `Attachment` records are cleaned up (via `ondelete="CASCADE"`), but inline images referenced only in TipTap JSON content are not tracked in the `Attachments` table at all. There is no process to parse the JSON, extract image URLs, and delete the corresponding MinIO objects.

**How to avoid:**
- Track every uploaded image in the `Attachments` table, even inline images. When an image is uploaded for a document, create an `Attachment` record with `entity_type='document'` and the document's ID. Use `ondelete="CASCADE"` on the foreign key.
- On document deletion, query all attachments for that document and delete the MinIO objects before (or alongside) the database cascade.
- Implement a periodic garbage collection job: scan MinIO `pm-images` bucket, cross-reference against `Attachments` table, and delete objects with no matching record. Run weekly during off-peak hours.
- For images removed from content by editing (not document deletion): compare the image URLs in the old vs. new TipTap JSON on save. Delete MinIO objects for images that were removed from the content.
- Set MinIO lifecycle rules as a safety net: auto-delete objects older than 90 days that have no corresponding database record (via a scheduled job, not MinIO's built-in lifecycle rules which cannot query your database).

**Warning signs:**
- MinIO storage growing faster than document count.
- No `Attachment` records being created for inline editor images.
- `delete_note` endpoint (existing code) does not call `minio_service.delete_file()` for associated images.
- No garbage collection job in the task scheduler.

**Phase to address:**
Phase 1 (Image Upload) for tracking, Phase 4 (Maintenance) for garbage collection.

---

### Pitfall 5: Permission Leaks Across Document Scopes

**What goes wrong:**
A personal document (scope: personal) is accidentally visible to other users. Or: a project-scoped document remains accessible after a user is removed from the project. Or: when a document's scope changes from `project` to `personal`, other project members still have cached access. The existing permission model (`PermissionService`) checks application/project membership but does not have document-level permission checks. The current `verify_note_access` in `notes.py` only checks application ownership -- there is no concept of per-note/document RBAC.

**Why it happens:**
The existing Notes system uses a simple ownership model (application owner sees all notes). The new knowledge base has three scopes (personal, application, project) with different visibility rules. Teams often bolt the new permission model onto the old ownership check, leaving gaps. Cache invalidation on permission changes (user removed from project, scope changed) is frequently missed.

**How to avoid:**
- Design the permission check as a single function that takes `(user_id, document_id, action)` and returns `allow/deny`. Do not scatter permission logic across routers.
- For each scope, define the rules explicitly:
  - `personal`: only `created_by` user can read/write
  - `project`: project members with appropriate application role can read; project members with Editor+ role can write
  - `application`: all application members can read; Editors+ can write
- Cache permissions in Redis with a key like `doc:perm:{document_id}:{user_id}` with a short TTL (60s). Invalidate on: scope change, project membership change, application role change.
- Write integration tests that verify: personal docs are invisible to other users, project docs become invisible after user removal, scope changes immediately update access.
- The document list/tree API must filter by permission -- never return documents the user cannot access and rely on frontend filtering.

**Warning signs:**
- Document list endpoint returns all documents and filters by scope on the frontend.
- No integration tests for cross-scope visibility.
- Permission cache not invalidated when project membership changes.
- `verify_note_access` pattern copied without adding scope-awareness.

**Phase to address:**
Phase 2 (Permissions). Must be complete before any multi-user testing or beta release.

---

### Pitfall 6: Search Index Diverges from Database (Stale Search Results)

**What goes wrong:**
A document is updated or deleted in the database, but Meilisearch still has the old content (or still lists a deleted document). Users search for content, find a result, click it, and get a 404 or see outdated content. At scale with frequent auto-saves (every 10s of inactivity across 5K users), the indexing pipeline becomes a bottleneck -- Meilisearch tasks queue up and lag further behind reality.

**Why it happens:**
Meilisearch indexing is asynchronous -- `addDocuments` returns a task ID, not a confirmation. If the task fails silently (e.g., schema mismatch, Meilisearch instance down), the index diverges. Additionally, indexing every auto-save (every 10 seconds per active document) creates massive write amplification in the search index.

**How to avoid:**
- Do not index on every auto-save. Index on "meaningful save" events: document close, explicit save button, or a longer debounce (e.g., 60 seconds after last edit). This reduces write amplification by 6x or more.
- Check Meilisearch task status after enqueuing. Log failed tasks and implement a retry queue. Meilisearch returns task IDs -- poll for completion or use webhooks.
- Implement a periodic full reconciliation job: compare all document IDs in the database with all document IDs in the Meilisearch index. Delete stale entries, re-index missing entries. Run daily.
- On document deletion, send a delete to Meilisearch in the same API handler (not via an async event that might be lost).
- Define searchable attributes upfront before adding documents. Changing searchable attributes later triggers a full re-index.
- Do not index large binary content or raw TipTap JSON. Extract plain text and index that.

**Warning signs:**
- Search returns documents that have been deleted.
- Meilisearch task queue length growing over time (check `/tasks` endpoint).
- No monitoring on Meilisearch task success/failure rates.
- Indexing triggered on every auto-save event.

**Phase to address:**
Phase 3 (Search Integration). Index reconciliation job in Phase 4 (Maintenance).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store TipTap HTML instead of JSON | Simpler rendering (just `dangerouslySetInnerHTML`) | Cannot migrate schema, cannot diff content, XSS risk | Never -- always store JSON as primary format |
| Skip schema versioning on documents | Faster initial development | Content silently destroyed on extension changes, no migration path | Never |
| Full document re-index on every auto-save | Search always current | Write amplification kills Meilisearch at scale, 5K users * 6 saves/min = 30K index ops/min | Only in Phase 1 prototype, must fix before multi-user |
| No image tracking in Attachments table | Simpler image upload flow | Orphaned images grow forever, no cleanup possible | Only if lifecycle rules can handle it (they cannot for this use case) |
| Lock state in database instead of Redis | No Redis dependency for locks | Lock checks add latency to every edit operation, no TTL, orphaned locks require manual cleanup | Never for lock-based editing at scale |
| Recursive tree queries in Python | Simple code (existing `build_note_tree` pattern) | O(n^2) for deep trees, N+1 queries for lazy loading | Acceptable for < 500 documents per scope, must optimize beyond that |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| TipTap + MinIO image upload | Uploading directly from TipTap to MinIO via presigned URL, but not creating an Attachment record | Route uploads through backend API that creates Attachment record AND returns presigned URL |
| Meilisearch + Auto-save | Indexing raw TipTap JSON (includes formatting marks, node types) | Extract plain text via TipTap's `getText()` or a server-side JSON-to-text converter, index only that |
| Meilisearch + Document deletion | Deleting from DB but forgetting to delete from search index | Delete from Meilisearch in the same request handler, before or after DB deletion |
| Redis locks + Electron | Relying on `window.onbeforeunload` to release locks | Use heartbeat pattern -- lock auto-expires if heartbeat stops |
| TipTap + Content Security Policy | TipTap uses inline styles and `data:` URIs for images | CSP must allow `style-src 'unsafe-inline'` and `img-src data: blob:` or images/formatting break |
| Existing Notes migration | Deleting old Notes table/API before new system is proven | Keep old system read-only, migrate data to new system, validate, then deprecate |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full folder tree with all documents on page load | Initial page load > 2s, grows with document count | Lazy-load tree: fetch root folders first, expand on click. Cache tree structure in Redis. | > 500 documents per application |
| N+1 queries for folder tree with children counts | Each folder expansion triggers a separate query | Use the existing `children_count_subquery` pattern from `notes.py` but apply it to folders. Use `selectinload` for batch loading. | > 100 folders |
| Auto-save write amplification (DB + Meilisearch + MinIO) | Every 10s save hits DB, search index, and potentially image storage | Separate concerns: DB save on 10s debounce, search index on 60s debounce, image cleanup on document close | > 100 concurrent editors |
| TipTap `getHTML()` on every save for comparison | UI freezes during save, especially with browser Find (Cmd+F) open | Use `getJSON()` for comparison and persistence. Only generate HTML on demand (export, preview). | Documents > 50KB |
| Full document content in list/tree API responses | API response size explodes, tree loading is slow | Never include `content` field in list endpoints. Only return content in single-document GET. | > 200 documents in a listing |
| Circular parent reference in folder tree | Infinite loop in tree rendering, stack overflow | Validate parent changes: check that new parent is not a descendant (existing `is_descendant` check in `notes.py` -- reuse this pattern). Add DB constraint or trigger. | Any time folder reparenting is allowed |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Rendering TipTap HTML output without sanitization | Stored XSS -- attacker crafts a document with `<img src=x onerror=alert(1)>` or `javascript:` link href, other users viewing the document execute the script | Sanitize with DOMPurify before rendering HTML. Better: render from JSON using TipTap's `generateHTML()` which only produces schema-valid output. Never use `dangerouslySetInnerHTML` with raw stored HTML. |
| Paste from external sources (Word, web pages) injecting malicious HTML | XSS via clipboard -- user pastes content from a malicious webpage into the editor | TipTap's schema strips unknown nodes, but `<img>` event handlers and `javascript:` URIs can survive. Add a `transformPastedHTML` hook that runs DOMPurify on pasted content before TipTap processes it. |
| Document API returning content without permission check | Information disclosure -- personal documents or project documents visible to unauthorized users | Centralized permission check function (not scattered across routers). Every document endpoint must call it. |
| Presigned MinIO URLs leaked or cached | Anyone with the URL can access the image for the URL's lifetime (default 1 hour in existing code) | Keep presigned URL expiry short (15 minutes). Generate fresh URLs on each document load. Do not cache presigned URLs in frontend state that persists across sessions. |
| Lock bypass via direct API call | User bypasses frontend lock check and saves via direct API call, overwriting locked content | Backend must enforce lock ownership on every save endpoint -- not just frontend UI state. Check `doc:lock:{id}` in Redis and verify the lock holder matches the requesting user. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Save indicator shows "saved" before server confirms | User trusts the indicator, closes the app, loses data | Show "saving..." until server responds with 200. Show "saved" with timestamp. Show "save failed" with retry button on error. Never show "saved" optimistically. |
| No visual indicator of who holds the lock | User sees "document is locked" but does not know by whom or when the lock will expire | Show "Locked by [username] since [time]. You can request edit access." with a "Request Access" button. |
| Folder tree does not update after another user creates a document | User does not see new documents until page refresh | Use WebSocket or polling to push tree updates. At minimum, refresh tree on folder expand. |
| Rich text paste from Word/Google Docs produces broken formatting | Tables, images, and custom styles from external sources render poorly | Add a "Paste as plain text" option. Show a toast warning when rich paste is detected from an external source. Implement `transformPastedHTML` to normalize common patterns (Word's `mso-*` styles, Google Docs' `<b style="font-weight:normal">` nonsense). |
| Search results show stale content snippets | User clicks a search result expecting content X, sees content Y (updated since last index) | Show `last_indexed` timestamp on search results. Re-fetch content on click, not from the search index. |
| Document version history not available | User accidentally deletes content via auto-save, no way to recover | Implement periodic snapshots (every N saves or every hour). Show a "Version History" panel. This is table stakes for any document system. |

## "Looks Done But Isn't" Checklist

- [ ] **Auto-save:** Often missing `beforeunload` handler for Electron -- verify save fires on app quit, not just tab close
- [ ] **Auto-save:** Often missing offline/network-failure handling -- verify save retries on reconnect, verify local draft persistence
- [ ] **Lock management:** Often missing heartbeat mechanism -- verify locks auto-expire when client crashes
- [ ] **Lock management:** Often missing "who has the lock" UI -- verify locked-by username is displayed
- [ ] **Image upload:** Often missing Attachment record creation for inline images -- verify MinIO objects are tracked in the database
- [ ] **Image upload:** Often missing cleanup on document deletion -- verify MinIO objects are deleted when document is deleted
- [ ] **Search:** Often missing task status verification after Meilisearch enqueue -- verify failed indexing tasks are logged and retried
- [ ] **Search:** Often missing reconciliation job -- verify stale/orphaned search entries are cleaned up periodically
- [ ] **Permissions:** Often missing scope-change cache invalidation -- verify changing a document from project to personal immediately revokes access
- [ ] **Permissions:** Often missing backend enforcement of lock ownership -- verify direct API save is rejected for non-lock-holders
- [ ] **Folder tree:** Often missing circular reference prevention -- verify reparenting a folder to its own descendant is rejected
- [ ] **Content conversion:** Often missing DOMPurify sanitization on HTML render -- verify XSS payloads in document content do not execute
- [ ] **Schema versioning:** Often missing `schema_version` on document model -- verify schema changes include data migration scripts

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Data loss from auto-save race condition | HIGH | If local drafts exist, recover from IndexedDB. If not, data is permanently lost. Post-incident: add `beforeunload` handlers and local draft persistence. |
| Orphaned locks blocking editing | LOW | Admin endpoint to force-release locks. Post-incident: add TTL-based locks in Redis with heartbeat. |
| TipTap schema change strips content | HIGH | If document snapshots exist, restore from last good snapshot. If not, raw JSON may still be in database backups -- restore and migrate. Post-incident: add schema versioning and content error detection. |
| Orphaned images consuming MinIO storage | LOW | Run a reconciliation script: list all MinIO objects, cross-reference with Attachments table, delete orphans. Post-incident: add image tracking and GC job. |
| Permission leak exposing private documents | HIGH | Audit access logs to determine exposure scope. Immediate: add backend permission checks. Post-incident: add integration tests for cross-scope visibility. |
| Stale Meilisearch index | MEDIUM | Run full re-index from database. Post-incident: add reconciliation job and task status monitoring. |
| Circular parent reference in folder tree | MEDIUM | Direct database fix to set the offending `parent_id` to NULL. Post-incident: add cycle detection in the reparenting endpoint and a DB-level constraint. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Auto-save data loss | Phase 1: Core CRUD + Auto-save | Integration test: edit, navigate away, verify content persisted. Electron-specific test: edit, force-quit, reopen, verify local draft recovery. |
| Orphaned locks | Phase 2: Lock Management | Test: acquire lock, kill client process, verify lock expires within 60s. Test: another user can edit after expiry. |
| TipTap schema content loss | Phase 1: Core Editor + Phase 3: Schema Migration tooling | Test: save document with extension A, remove extension A, load document, verify content error is caught (not silently stripped). |
| Orphaned MinIO images | Phase 1: Image Upload (tracking) + Phase 4: Maintenance (GC job) | Verify: upload image, delete document, check MinIO object is deleted. Monthly: run GC job, verify no orphan growth trend. |
| Permission leaks | Phase 2: Permissions | Integration tests per scope: personal invisible to others, project invisible after removal, scope change revokes access immediately. |
| Stale search index | Phase 3: Search Integration + Phase 4: Reconciliation job | Test: delete document, search for it, verify no results. Monitor: Meilisearch task queue length, failed task count. |
| Folder tree performance | Phase 1: Tree Structure | Load test: 1000 documents, measure tree load time. Verify lazy loading works. Profile N+1 queries. |
| XSS via editor content | Phase 1: Core Editor (sanitization) | Security test: save document with XSS payload, render in another user's browser, verify script does not execute. |
| Lock bypass via API | Phase 2: Lock Management (backend enforcement) | Test: acquire lock as User A, attempt API save as User B without lock, verify 409 Conflict response. |
| Circular folder references | Phase 1: Tree Structure | Test: attempt to set folder parent to its own child, verify 400 Bad Request. |

## Sources

- [TipTap Persistence Documentation](https://tiptap.dev/docs/editor/core-concepts/persistence)
- [TipTap Invalid Schema Handling](https://tiptap.dev/docs/guides/invalid-schema)
- [TipTap Content Error Detection (enableContentCheck)](https://tiptap.dev/docs/guides/invalid-schema)
- [TipTap Discussion: Efficient Saving](https://github.com/ueberdosis/tiptap/discussions/5677)
- [TipTap Discussion: Save with Delay](https://github.com/ueberdosis/tiptap/discussions/2871)
- [TipTap Issue: Data Loss on Reload with Schema Enforcement](https://github.com/ueberdosis/tiptap/issues/5032)
- [TipTap Issue: XSS via Link Extension](https://github.com/ueberdosis/tiptap/issues/3673)
- [TipTap Issue: XSS via getHTML()](https://github.com/scrumpy/tiptap/issues/724)
- [Snyk: TipTap XSS Vulnerability](https://security.snyk.io/vuln/SNYK-JS-TIPTAP-575143)
- [Meilisearch Indexing Best Practices](https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices)
- [Meilisearch Issue: Silent Indexing Failure](https://github.com/meilisearch/meilisearch/issues/4438)
- [Meilisearch Indexing Performance](https://www.meilisearch.com/docs/learn/advanced/indexing)
- [Budibase Issue: Orphaned Files in MinIO](https://github.com/Budibase/budibase/issues/5564)
- [MinIO Object Lifecycle Management](https://min.io/docs/minio/linux/administration/object-management/object-lifecycle-management.html)
- [SharePoint File Locking Troubleshooting](https://wolfesystems.com.au/troubleshooting-sharepoint-file-locking/)
- [Payload CMS Document Locking](https://payloadcms.com/docs/admin/locked-documents)
- [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- Codebase analysis: `fastapi-backend/app/models/note.py`, `fastapi-backend/app/routers/notes.py`, `fastapi-backend/app/services/minio_service.py`, `fastapi-backend/app/services/permission_service.py`, `fastapi-backend/app/services/redis_service.py`

---
*Pitfalls research for: Document/Knowledge Base System in PM Desktop*
*Researched: 2026-01-31*
