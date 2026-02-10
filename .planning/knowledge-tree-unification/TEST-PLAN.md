# Knowledge Base - Comprehensive Test Plan

**Scope**: All knowledge base features excluding permissions, files, and attachments.
**Backend**: pytest (async) following existing test patterns
**Frontend E2E**: agent-browser with 2 concurrent clients for real-time/WebSocket validation

---

## Part 1: Backend Python Tests (pytest)

### 1.1 Test File Structure

```
fastapi-backend/tests/
├── conftest.py                    # Add document fixtures
├── test_documents.py              # Document CRUD + content + trash
├── test_document_folders.py       # Folder hierarchy + tree + move
├── test_document_locks.py         # Redis locking + heartbeat + force-take
├── test_document_tags.py          # Tag CRUD + assignment + scope validation
├── test_document_websocket.py     # WS broadcast for document/folder/lock events
```

### 1.2 New Fixtures (conftest.py additions)

```python
# Document fixtures needed:
test_document_folder       # Root folder in application scope
test_child_folder          # Nested folder (depth 1)
test_document              # Document in test_document_folder
test_personal_document     # Personal-scope document (user_id scope)
test_project_document      # Project-scope document
test_unfiled_document      # Document with folder_id=None
test_document_tag          # Tag in application scope
test_personal_tag          # Tag in personal scope
```

---

### 1.3 test_documents.py

#### TestListDocuments
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_list_documents_empty` | 200, empty items[], no next_cursor |
| 2 | `test_list_documents_with_data` | Returns documents in scope with correct fields |
| 3 | `test_list_documents_cursor_pagination` | next_cursor present when limit < total, second page correct |
| 4 | `test_list_documents_by_folder` | `folder_id` filter returns only folder's documents |
| 5 | `test_list_documents_include_unfiled` | `include_unfiled=true` returns docs with folder_id=None |
| 6 | `test_list_documents_excludes_deleted` | Soft-deleted documents not in list |
| 7 | `test_list_documents_scope_isolation` | App-scope docs not visible with project-scope params |
| 8 | `test_list_documents_unauthorized` | 401 without auth headers |

#### TestCreateDocument
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_create_document_application_scope` | 201, correct application_id set, title, row_version=1 |
| 2 | `test_create_document_project_scope` | 201, correct project_id set |
| 3 | `test_create_document_personal_scope` | 201, correct user_id set |
| 4 | `test_create_document_with_folder` | folder_id correctly assigned |
| 5 | `test_create_document_with_content` | content_json stored, markdown + plain text derived |
| 6 | `test_create_document_unfiled` | folder_id=None accepted |
| 7 | `test_create_document_empty_title` | 422 validation error |
| 8 | `test_create_document_invalid_scope` | 400 bad request |
| 9 | `test_create_document_nonexistent_folder` | 404 folder not found |
| 10 | `test_create_document_broadcasts_ws_event` | DOCUMENT_CREATED sent to scope room |

#### TestGetDocument
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_get_document_success` | 200, includes content_json, content_markdown, content_plain |
| 2 | `test_get_document_not_found` | 404 |
| 3 | `test_get_document_soft_deleted` | 404 (deleted docs not fetchable via normal get) |
| 4 | `test_get_document_includes_tags` | Response includes assigned tags |

#### TestUpdateDocument
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_update_document_title` | Title changed, row_version incremented |
| 2 | `test_update_document_move_to_folder` | folder_id updated |
| 3 | `test_update_document_content` | content_json updated, markdown + plain derived |
| 4 | `test_update_document_optimistic_concurrency_pass` | Correct row_version → 200 |
| 5 | `test_update_document_optimistic_concurrency_fail` | Stale row_version → 409 Conflict |
| 6 | `test_update_document_not_found` | 404 |
| 7 | `test_update_document_broadcasts_ws_event` | DOCUMENT_UPDATED sent |

#### TestUpdateDocumentContent (auto-save endpoint)
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_autosave_content_success` | content_json saved, row_version incremented |
| 2 | `test_autosave_content_version_conflict` | Stale row_version → 409 |
| 3 | `test_autosave_content_tiptap_to_markdown` | Markdown correctly derived from TipTap JSON |
| 4 | `test_autosave_content_tiptap_to_plain_text` | Plain text correctly derived |

#### TestDeleteDocument (soft delete)
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_delete_document_soft` | 204, deleted_at set, still in DB |
| 2 | `test_delete_document_not_found` | 404 |
| 3 | `test_delete_document_broadcasts_ws_event` | DOCUMENT_DELETED sent |
| 4 | `test_delete_document_idempotent` | Already-deleted doc → 404 |

#### TestTrashDocuments
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_list_trash_empty` | 200, empty list |
| 2 | `test_list_trash_with_deleted_docs` | Returns only soft-deleted documents |
| 3 | `test_restore_document_success` | deleted_at cleared, document accessible again |
| 4 | `test_restore_document_not_in_trash` | 404 or 400 if not deleted |
| 5 | `test_permanent_delete_success` | 204, row removed from DB |
| 6 | `test_permanent_delete_not_in_trash` | 404 if not soft-deleted first |

#### TestDocumentScopesSummary
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_scopes_summary_empty` | has_personal_docs=false, empty applications |
| 2 | `test_scopes_summary_with_personal` | has_personal_docs=true |
| 3 | `test_scopes_summary_with_applications` | applications[] populated with names |

#### TestProjectsWithContent
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_projects_with_content_empty` | Empty project_ids[] |
| 2 | `test_projects_with_content_has_documents` | project_id included |
| 3 | `test_projects_with_content_has_folders` | project_id included (folders only, no docs) |
| 4 | `test_projects_with_content_excludes_empty_projects` | Projects without docs/folders excluded |

---

### 1.4 test_document_folders.py

#### TestGetFolderTree
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_folder_tree_empty` | 200, empty list |
| 2 | `test_folder_tree_flat` | Root folders returned with children=[] |
| 3 | `test_folder_tree_nested` | Parent → child → grandchild hierarchy correct |
| 4 | `test_folder_tree_document_counts` | document_count per folder accurate |
| 5 | `test_folder_tree_scope_isolation` | App-scope folders not in project-scope tree |
| 6 | `test_folder_tree_sorted_by_name` | Alphabetical sort within each level |

#### TestCreateFolder
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_create_folder_root` | 201, parent_id=None, depth=0, materialized_path="/{id}/" |
| 2 | `test_create_folder_nested` | parent_id set, depth=parent+1, path includes parent |
| 3 | `test_create_folder_max_depth` | depth=5 → 400 exceeds max depth |
| 4 | `test_create_folder_duplicate_name_same_parent` | 409 name conflict |
| 5 | `test_create_folder_same_name_different_parent` | 201 allowed |
| 6 | `test_create_folder_application_scope` | application_id set correctly |
| 7 | `test_create_folder_project_scope` | project_id set correctly |
| 8 | `test_create_folder_personal_scope` | user_id set correctly |
| 9 | `test_create_folder_invalid_parent` | 404 parent not found |
| 10 | `test_create_folder_broadcasts_ws_event` | FOLDER_CREATED sent |

#### TestUpdateFolder
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_rename_folder` | name updated |
| 2 | `test_move_folder_to_new_parent` | parent_id, materialized_path, depth all updated |
| 3 | `test_move_folder_updates_descendants` | All descendant materialized_paths and depths updated |
| 4 | `test_move_folder_to_root` | parent_id=None, depth=0 |
| 5 | `test_move_folder_circular_prevention` | Move under own descendant → 400 |
| 6 | `test_move_folder_exceeds_max_depth` | Move causes descendant depth > 5 → 400 |
| 7 | `test_update_folder_not_found` | 404 |
| 8 | `test_update_folder_broadcasts_ws_event` | FOLDER_UPDATED sent |

#### TestDeleteFolder
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_delete_folder_empty` | 204, folder removed |
| 2 | `test_delete_folder_cascades_documents` | Documents in folder get deleted_at set |
| 3 | `test_delete_folder_cascades_subfolders` | Child folders also deleted |
| 4 | `test_delete_folder_not_found` | 404 |
| 5 | `test_delete_folder_broadcasts_ws_event` | FOLDER_DELETED sent |

---

### 1.5 test_document_locks.py

#### TestAcquireLock
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_acquire_lock_success` | locked=true, lock_holder has user_id, user_name, acquired_at |
| 2 | `test_acquire_lock_already_held_by_other` | 409 Conflict, response includes current holder info |
| 3 | `test_acquire_lock_reacquire_same_user` | 200, TTL extended (no conflict) |
| 4 | `test_acquire_lock_broadcasts_ws_event` | DOCUMENT_LOCKED sent to scope room |

#### TestReleaseLock
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_release_lock_success` | locked=false, lock_holder=None |
| 2 | `test_release_lock_not_held` | 200 or 404 (idempotent release) |
| 3 | `test_release_lock_held_by_other` | 403/409 cannot release another user's lock |
| 4 | `test_release_lock_broadcasts_ws_event` | DOCUMENT_UNLOCKED sent |

#### TestGetLockStatus
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_get_lock_unlocked` | locked=false |
| 2 | `test_get_lock_locked` | locked=true with holder info |

#### TestHeartbeat
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_heartbeat_extends_ttl` | extended=true, Redis TTL reset |
| 2 | `test_heartbeat_not_holder` | extended=false (different user) |
| 3 | `test_heartbeat_no_lock` | extended=false (no lock exists) |

#### TestForceTakeLock
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_force_take_success` | Lock transferred, previous holder info returned |
| 2 | `test_force_take_no_existing_lock` | Creates new lock (force-take on unlocked doc) |
| 3 | `test_force_take_broadcasts_ws_event` | DOCUMENT_FORCE_TAKEN sent with previous_holder |

#### TestActiveLocks (batch endpoint)
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_active_locks_empty` | locks=[] when no docs locked |
| 2 | `test_active_locks_returns_scope_filtered` | Only locks for specified scope returned |
| 3 | `test_active_locks_multiple` | Multiple locked docs in response |
| 4 | `test_active_locks_excludes_other_scope` | Locks from different scope not included |

#### TestLockTTL
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_lock_expires_after_ttl` | Lock auto-released after 5 min (mock time or short TTL) |
| 2 | `test_lock_ttl_atomic_lua_script` | Concurrent acquire attempts → only one wins |

---

### 1.6 test_document_tags.py

#### TestListTags
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_list_tags_empty` | 200, empty list |
| 2 | `test_list_tags_with_data` | Returns tags with id, name, color |
| 3 | `test_list_tags_scope_isolation` | App tags not in personal list |

#### TestCreateTag
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_create_tag_application_scope` | 201, application_id set |
| 2 | `test_create_tag_personal_scope` | 201, user_id set |
| 3 | `test_create_tag_with_color` | Hex color stored correctly |
| 4 | `test_create_tag_duplicate_name` | 409 case-insensitive conflict |
| 5 | `test_create_tag_invalid_color` | 422 validation error |

#### TestUpdateTag
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_update_tag_name` | Name changed |
| 2 | `test_update_tag_color` | Color changed |
| 3 | `test_update_tag_not_found` | 404 |

#### TestDeleteTag
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_delete_tag_success` | 204 |
| 2 | `test_delete_tag_cascades_assignments` | Assignments removed |
| 3 | `test_delete_tag_not_found` | 404 |

#### TestTagAssignment
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_assign_tag_to_document` | 201, assignment created |
| 2 | `test_assign_tag_duplicate` | 409 already assigned |
| 3 | `test_assign_tag_scope_mismatch` | 400/409 app tag on personal doc |
| 4 | `test_remove_tag_from_document` | 204, assignment deleted |
| 5 | `test_remove_tag_not_assigned` | 404 |

---

### 1.7 test_document_websocket.py

#### TestDocumentBroadcast
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_document_created_broadcast_to_scope_room` | Message sent to application/project room |
| 2 | `test_document_updated_broadcast_includes_actor` | actor_id in payload for skip-own logic |
| 3 | `test_document_deleted_broadcast_to_scope_room` | DOCUMENT_DELETED with scope info |
| 4 | `test_project_doc_broadcasts_to_both_rooms` | Project-scoped events broadcast to project AND application rooms |

#### TestFolderBroadcast
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_folder_created_broadcast` | FOLDER_CREATED to scope room |
| 2 | `test_folder_updated_broadcast` | FOLDER_UPDATED to scope room |
| 3 | `test_folder_deleted_broadcast_before_commit` | Data captured before delete, broadcast after commit |

#### TestLockBroadcast
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_lock_broadcast_to_document_and_scope_rooms` | Parallel broadcast to document + scope rooms |
| 2 | `test_force_take_broadcast_includes_previous_holder` | previous_holder in FORCE_TAKEN payload |
| 3 | `test_unlock_broadcast_removes_holder` | DOCUMENT_UNLOCKED has no lock_holder |

#### TestConnectionManager
| # | Test Case | Validates |
|---|-----------|-----------|
| 1 | `test_join_room` | Connection added to room, room created if new |
| 2 | `test_leave_room` | Connection removed, room cleaned up if empty |
| 3 | `test_broadcast_to_room_excludes_sender` | exclude parameter works |
| 4 | `test_broadcast_to_user_multiple_connections` | Message sent to all user's connections |
| 5 | `test_disconnect_cleanup` | All rooms and user tracking cleaned up |

---

## Part 2: E2E Tests (agent-browser, 2 Clients)

### 2.1 Test Architecture

```
agent-browser setup:
├── Client A (User 1) - Primary actor
├── Client B (User 2) - Observer / concurrent actor
├── Both logged in, both on Notes page or Knowledge panel
└── Tests verify real-time sync between the two browsers
```

### 2.2 Document CRUD Operations

#### E2E-DOC-01: Create Document
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Navigate to Notes page, application tab | Navigate to Notes page, same application tab | Both see same tree |
| 2 | Click "New Document" button | - | Create dialog opens |
| 3 | Enter title "Test Document", select folder, submit | - | Dialog closes |
| 4 | - | - | **Client A**: Document appears in tree, editor opens |
| 5 | - | - | **Client B**: Document appears in tree via WS (no manual refresh) |

#### E2E-DOC-02: Rename Document
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Right-click document → Rename | - | Inline rename input appears |
| 2 | Type "Renamed Doc", press Enter | - | Name updates in tree |
| 3 | - | - | **Client B**: Name updates in tree via WS |

#### E2E-DOC-03: Delete Document
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Right-click document → Delete | - | Confirmation dialog appears |
| 2 | Confirm deletion | - | Document removed from tree |
| 3 | - | - | **Client B**: Document disappears from tree via WS |
| 4 | - | - | If Client B had this doc selected, selection clears |

#### E2E-DOC-04: Move Document (DnD)
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Drag document from root to a folder | - | Drop target highlights |
| 2 | Drop on folder | - | Document moves into folder |
| 3 | - | - | **Client B**: Document appears in new folder via WS |

---

### 2.3 Folder CRUD Operations

#### E2E-FOLD-01: Create Folder
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Click "New Folder" button | - | Create dialog opens |
| 2 | Enter name "Test Folder", submit | - | Folder appears in tree |
| 3 | - | - | **Client B**: Folder appears in tree via WS |

#### E2E-FOLD-02: Create Nested Folder
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Right-click existing folder → New Subfolder | - | Dialog opens |
| 2 | Enter name, submit | - | Subfolder appears nested under parent |
| 3 | - | - | **Client B**: Nested folder appears via WS |

#### E2E-FOLD-03: Rename Folder
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Right-click folder → Rename | - | Inline rename |
| 2 | Type new name, Enter | - | Name updates |
| 3 | - | - | **Client B**: Name updates via WS |

#### E2E-FOLD-04: Delete Folder with Contents
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Create folder with 2 documents inside | Client B sees folder + docs | Setup |
| 2 | Right-click folder → Delete, confirm | - | Folder + all documents removed |
| 3 | - | - | **Client B**: Folder + contents disappear via WS |

#### E2E-FOLD-05: Move Folder (DnD)
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Drag folder into another folder | - | Drop target highlights |
| 2 | Drop | - | Folder moves (becomes child) |
| 3 | - | - | **Client B**: Tree structure updates via WS |

#### E2E-FOLD-06: Move Folder to Root (DnD)
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Drag nested folder to root drop zone | - | Root zone highlights |
| 2 | Drop | - | Folder becomes root-level |
| 3 | - | - | **Client B**: Tree updates via WS |

---

### 2.4 Document Editing & Lock System

#### E2E-LOCK-01: Basic Edit Flow (Lock → Edit → Save → Release)
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Select document | Select same document | Both see read-only view |
| 2 | Click "Edit" button | - | Editor becomes editable |
| 3 | - | - | **Client A**: Lock acquired, edit mode active |
| 4 | - | - | **Client B**: Lock icon appears on document, "Edit" disabled or shows lock holder name |
| 5 | Type content changes | - | Editor shows changes |
| 6 | Click "Save" | - | Content saved |
| 7 | - | - | **Client A**: Returns to view mode, lock released |
| 8 | - | - | **Client B**: Lock icon disappears, content updates to saved version |

#### E2E-LOCK-02: Lock Contention (Two Users Try to Edit)
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Click "Edit" on document | - | Lock acquired by A |
| 2 | - | Click "Edit" on same document | **Client B**: Sees error/toast "Document locked by User A" |
| 3 | - | - | **Client B**: Cannot enter edit mode |

#### E2E-LOCK-03: Force-Take Lock
| Step | Client A | Client B (App Owner) | Verify |
|------|----------|----------|--------|
| 1 | Edit document (lock held) | - | A is editing |
| 2 | - | Force-take lock (owner action) | Lock transferred to B |
| 3 | - | - | **Client A**: Receives FORCE_TAKEN event, exits edit mode, shows warning toast |
| 4 | - | - | **Client B**: Enters edit mode successfully |

#### E2E-LOCK-04: Lock Release on Cancel
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Click "Edit" | - | Lock acquired |
| 2 | Make changes, click "Cancel" | - | Discard dialog appears |
| 3 | Confirm discard | - | Changes discarded, lock released |
| 4 | - | - | **Client B**: Lock icon disappears, "Edit" becomes available |

#### E2E-LOCK-05: Lock Release on Navigation
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Edit document (lock held) | - | A is editing |
| 2 | Navigate to different document | - | Navigation guard dialog appears |
| 3 | Confirm leave without saving | - | Lock released on previous document |
| 4 | - | - | **Client B**: Lock released via WS |

---

### 2.5 Optimistic Concurrency (row_version)

#### E2E-OCC-01: Concurrent Edits Version Conflict
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Both clients view same document (row_version=1) | - | Both see v1 |
| 2 | A acquires lock, edits, saves | - | row_version → 2 |
| 3 | A releases lock | B acquires lock | B enters edit mode |
| 4 | - | B edits and saves | Should succeed with current row_version from cache |
| 5 | - | - | **Verify**: No 409 conflict because B fetched latest version after A's save |

---

### 2.6 Optimistic Cache Updates

#### E2E-CACHE-01: Optimistic Create (Instant UI Feedback)
| Step | Client A | Verify |
|------|----------|--------|
| 1 | Create document | Document appears in tree IMMEDIATELY (before server response) |
| 2 | - | Temp ID replaced with real ID after server response |
| 3 | - | No flicker or duplicate entry |

#### E2E-CACHE-02: Optimistic Delete (Instant Removal)
| Step | Client A | Verify |
|------|----------|--------|
| 1 | Delete document | Document removed from tree IMMEDIATELY |
| 2 | - | No reappearance after server confirms |

#### E2E-CACHE-03: Optimistic Rename (Instant Update)
| Step | Client A | Verify |
|------|----------|--------|
| 1 | Rename folder | Name updates IMMEDIATELY in tree |
| 2 | - | No flicker back to old name |

#### E2E-CACHE-04: Optimistic Move (Instant Reparent)
| Step | Client A | Verify |
|------|----------|--------|
| 1 | Move document to folder via DnD | Document appears in new folder IMMEDIATELY |
| 2 | - | Document removed from old location |
| 3 | - | No ghost entries in either location |

---

### 2.7 WebSocket Real-Time Sync

#### E2E-WS-01: Cross-Client Document Sync
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Create 3 documents in rapid succession | Observe tree | **Client B**: All 3 appear (order may batch) |
| 2 | Delete 1 document | Observe tree | **Client B**: Deleted doc disappears |
| 3 | Rename 1 document | Observe tree | **Client B**: Name updates |

#### E2E-WS-02: Cross-Client Folder Sync
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Create folder, create doc inside it | Observe tree | **Client B**: Folder + doc appear |
| 2 | Move doc out of folder to root | Observe tree | **Client B**: Doc moves to root |
| 3 | Delete empty folder | Observe tree | **Client B**: Folder disappears |

#### E2E-WS-03: Lock Status Real-Time Update
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Acquire lock on doc | Observe lock indicator | **Client B**: Lock icon appears on doc in tree |
| 2 | Release lock | Observe lock indicator | **Client B**: Lock icon disappears |
| 3 | Re-acquire lock | Observe lock indicator | **Client B**: Lock icon reappears |

#### E2E-WS-04: Skip-Own-Events (No Double Processing)
| Step | Client A | Verify |
|------|----------|--------|
| 1 | Create document | Document appears once (optimistic), NOT duplicated by own WS event |
| 2 | Delete document | Document removed once, no flicker |
| 3 | Rename document | Name updates once, no revert-then-reapply |

#### E2E-WS-05: Project-Scoped Dual-Room Broadcast
| Step | Client A (on project page) | Client B (on application page) | Verify |
|------|----------|----------|--------|
| 1 | Create document in project scope | Observe application tree | **Client B**: Document visible under project section |
| 2 | Delete document | Observe application tree | **Client B**: Document removed from project section |

---

### 2.8 DnD Operations & Constraints

#### E2E-DND-01: Document to Folder
| Step | Action | Verify |
|------|--------|--------|
| 1 | Drag doc, hover over folder | Folder highlights as drop target |
| 2 | Drop | Doc moves into folder |

#### E2E-DND-02: Document to Root
| Step | Action | Verify |
|------|--------|--------|
| 1 | Drag doc from folder to root drop zone | Root zone highlights |
| 2 | Drop | Doc becomes unfiled (root level) |

#### E2E-DND-03: Folder Into Folder
| Step | Action | Verify |
|------|--------|--------|
| 1 | Drag folder A, hover over folder B | Folder B highlights |
| 2 | Drop | Folder A becomes child of B |

#### E2E-DND-04: Prevent Circular Move
| Step | Action | Verify |
|------|--------|--------|
| 1 | Drag parent folder, hover over its child | Drop target NOT highlighted |
| 2 | Drop attempt | No operation occurs (drag cancelled) |

#### E2E-DND-05: Prevent Cross-Scope Drag
| Step | Action | Verify |
|------|--------|--------|
| 1 | Drag personal doc, hover over application folder | Drop target NOT highlighted |
| 2 | Drop attempt | No operation occurs |

#### E2E-DND-06: Folder to Root
| Step | Action | Verify |
|------|--------|--------|
| 1 | Drag nested folder to root drop zone | Root zone highlights |
| 2 | Drop | Folder becomes root-level |

---

### 2.9 Navigation & Tab Switching

#### E2E-NAV-01: Personal ↔ Application Tab Switch
| Step | Action | Verify |
|------|--------|--------|
| 1 | Open Notes page on Personal tab | Personal documents visible |
| 2 | Switch to Application tab | Application tree loads (may show skeleton briefly) |
| 3 | Switch back to Personal | Personal tree restored from cache (no skeleton) |
| 4 | - | Selected document preserved per tab |

#### E2E-NAV-02: Document Selection Persistence
| Step | Action | Verify |
|------|--------|--------|
| 1 | Select document, view content | Editor shows content |
| 2 | Navigate away (e.g., to Tasks page) | - |
| 3 | Navigate back to Notes | Same document selected, content visible |

#### E2E-NAV-03: Folder Expand/Collapse Persistence
| Step | Action | Verify |
|------|--------|--------|
| 1 | Expand 3 folders, collapse 1 | Tree state reflects expansions |
| 2 | Switch tabs and back | Same folders expanded/collapsed |

---

### 2.10 Loading States & Skeletons

#### E2E-SKEL-01: Initial Load Skeleton
| Step | Action | Verify |
|------|--------|--------|
| 1 | Hard refresh Notes page | TreeSkeleton visible briefly |
| 2 | Data loads | Skeleton replaced by real tree |

#### E2E-SKEL-02: No Skeleton on Cached Tab Switch
| Step | Action | Verify |
|------|--------|--------|
| 1 | Load Application tab (data cached) | - |
| 2 | Switch to Personal, switch back | NO skeleton shown (cache hit) |

#### E2E-SKEL-03: Folder Lazy-Load Skeleton
| Step | Action | Verify |
|------|--------|--------|
| 1 | Expand folder with documents | Brief skeleton in folder while docs load |
| 2 | Collapse and re-expand | No skeleton (cached) |

---

### 2.11 Search & Filtering

#### E2E-SEARCH-01: Document Search
| Step | Action | Verify |
|------|--------|--------|
| 1 | Type search query in search bar | Tree filters to matching items |
| 2 | Matching folders auto-expand | Documents within matching folders visible |
| 3 | Clear search | Full tree restored |

#### E2E-SEARCH-02: Search Across Folders
| Step | Action | Verify |
|------|--------|--------|
| 1 | Create docs in different folders with distinct names | Setup |
| 2 | Search for specific name | Only matching doc visible, its parent folder expanded |
| 3 | Search for different name | Different doc visible, different folder expanded |

---

### 2.12 Tag Operations

#### E2E-TAG-01: Assign Tag to Document
| Step | Action | Verify |
|------|--------|--------|
| 1 | Open document editor/header | Tag section visible |
| 2 | Assign tag | Tag chip appears on document |

#### E2E-TAG-02: Remove Tag from Document
| Step | Action | Verify |
|------|--------|--------|
| 1 | Click remove on assigned tag | Tag removed |
| 2 | - | Document no longer shows tag |

---

### 2.13 Inactivity Timeout

#### E2E-TIMEOUT-01: Edit Mode Inactivity
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | Enter edit mode | - | Lock acquired |
| 2 | Wait 5 minutes (no interaction) | - | Inactivity dialog appears |
| 3 | Dialog auto-saves after 60s | - | Content saved, lock released |
| 4 | - | - | **Client B**: Lock released via WS |

#### E2E-TIMEOUT-02: Lock TTL Expiry (No Heartbeat)
| Step | Client A | Client B | Verify |
|------|----------|----------|--------|
| 1 | A acquires lock | - | Lock held |
| 2 | Simulate heartbeat failure (e.g., network disconnect) | - | - |
| 3 | Wait for TTL (5 min) | Try to edit | **Client B**: Can acquire lock (A's expired) |

---

### 2.14 Content Conversion Validation

#### E2E-CONTENT-01: TipTap Content Persistence
| Step | Action | Verify |
|------|--------|--------|
| 1 | Enter edit mode | - |
| 2 | Type headings, lists, bold, italic, code blocks | Rich content in editor |
| 3 | Save | Content saved |
| 4 | Refresh page | Content restored exactly as typed |
| 5 | - | **API check**: content_markdown and content_plain derived correctly |

---

### 2.15 Multi-Scope End-to-End Flow

#### E2E-SCOPE-01: Full Workflow Across Scopes
| Step | Action | Verify |
|------|--------|--------|
| 1 | Create personal document | Appears in Personal tab |
| 2 | Switch to Application tab | Personal doc NOT visible |
| 3 | Create application-scoped document | Appears in Application tab |
| 4 | Open project's Knowledge panel | - |
| 5 | Create project-scoped document | Appears in project panel |
| 6 | Return to Notes page, Application tab | Project section shows project doc |
| 7 | Switch to Personal tab | Only personal doc visible |

---

## Part 3: Test Execution Strategy

### 3.1 Backend Test Execution

```bash
# Run all knowledge base tests
cd fastapi-backend
pytest tests/test_documents.py tests/test_document_folders.py tests/test_document_locks.py tests/test_document_tags.py tests/test_document_websocket.py -v

# Run with coverage
pytest tests/test_document*.py -v --cov=app/routers --cov=app/services --cov=app/websocket --cov-report=term-missing
```

**Prerequisites**:
- Test PostgreSQL database available
- Test Redis instance available (for lock tests)
- No mocked WS manager needed for broadcast tests (mock `broadcast_to_room`)

### 3.2 E2E Test Execution

```
agent-browser setup:
1. Launch app in dev mode (backend + frontend)
2. Open Client A → login as User 1
3. Open Client B → login as User 2
4. Both navigate to Notes page
5. Execute test scenarios sequentially
6. For timeout tests: use accelerated timers or wait actual duration
```

**Two-client tests** (require both browsers):
- E2E-DOC-01 through E2E-DOC-04 (CRUD sync)
- E2E-FOLD-01 through E2E-FOLD-06 (folder sync)
- E2E-LOCK-01 through E2E-LOCK-05 (lock contention & release)
- E2E-WS-01 through E2E-WS-05 (real-time sync)
- E2E-TIMEOUT-01, E2E-TIMEOUT-02 (lock expiry)

**Single-client tests** (Client A only):
- E2E-CACHE-01 through E2E-CACHE-04 (optimistic updates)
- E2E-DND-01 through E2E-DND-06 (drag-and-drop)
- E2E-NAV-01 through E2E-NAV-03 (navigation)
- E2E-SKEL-01 through E2E-SKEL-03 (loading states)
- E2E-SEARCH-01, E2E-SEARCH-02 (search)
- E2E-TAG-01, E2E-TAG-02 (tags)
- E2E-CONTENT-01 (content persistence)
- E2E-SCOPE-01 (multi-scope flow)
- E2E-OCC-01 (version conflict)

### 3.3 Test Count Summary

| Area | Backend Tests | E2E Scenarios |
|------|---------------|---------------|
| Document CRUD | 28 | 4 |
| Document Trash | 6 | - |
| Document Scopes/Summary | 7 | 1 |
| Folder CRUD + Tree | 19 | 6 |
| Document Locks | 14 | 5 |
| Document Tags | 13 | 2 |
| WebSocket Broadcasts | 12 | 5 |
| Optimistic Caching | - | 4 |
| DnD Operations | - | 6 |
| Navigation/Tabs | - | 3 |
| Loading States | - | 3 |
| Search | - | 2 |
| Timeouts | - | 2 |
| Content Conversion | 2 | 1 |
| Concurrency Control | 2 | 1 |
| **Total** | **103** | **45** |
