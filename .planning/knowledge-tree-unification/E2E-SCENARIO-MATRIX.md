# E2E Scenario Matrix — Playwright Electron (2 Clients)

Every testable flow across all 3 knowledge base surfaces.
Excludes: permissions, files, attachments.

---

## Contexts

| Context | Route | Tree Component | Scope | DnD Prefix | Project Sections | Editor Key | Tab Bar | WS Room |
|---------|-------|---------------|-------|------------|-----------------|------------|---------|---------|
| **Notes - Personal** | Sidebar → Notes → Personal tab | KnowledgeTree (no appId) | personal | `personal` | No | `key={docId}` (remount) | Yes | `user:{userId}` |
| **Notes - App** | Sidebar → Notes → App tab | KnowledgeTree (appId) | application | `app` | Yes (lazy) | `key={docId}` (remount) | Yes | `application:{appId}` |
| **App Knowledge Tab** | App Detail → Knowledge tab | KnowledgePanel → ApplicationTree | application | `app` | Yes (lazy) | No key (reuse) | No | `application:{appId}` |
| **Project Knowledge Tab** | Project Detail → Knowledge tab | KnowledgePanel → FolderTree | project | `project` | No | No key (reuse) | No | `project:{projectId}` |

---

## 1. Tree Rendering & Empty States

### Per context: Notes-Personal, Notes-App, App-KB, Project-KB

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 1.1 | **Empty state — no documents** | Navigate to context with no docs/folders | "No documents yet" message + "Create your first document" button visible |
| 1.2 | **Empty state — create first doc** | Click "Create your first document" | Create dialog opens, submit creates doc, tree shows it, editor opens |
| 1.3 | **Tree renders folders + unfiled docs** | Have folders + unfiled docs in scope | Folders rendered as expandable, unfiled docs at root level, alphabetical order |
| 1.4 | **Nested folders render correctly** | Have 3-level folder hierarchy | Parent > Child > Grandchild nesting visible with correct indentation |
| 1.5 | **Folder expand/collapse** | Click folder chevron | Children toggle visibility, chevron rotates |
| 1.6 | **Folder document count** | Folder has 5 docs | Document count badge shows "5" |
| 1.7 | **Initial load skeleton** | First visit (no cache) | TreeSkeleton (6 rows) shown briefly, then replaced by real tree |
| 1.8 | **No skeleton on cached revisit** | Switch away and back | Tree renders instantly from cache, no skeleton |

### Notes-App & App-KB only:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 1.9 | **Project sections visible** | App has projects with documents | "Projects" heading shown, project rows listed below app-level tree |
| 1.10 | **Project section expand** | Click project name | Chevron rotates, project folders + docs lazy-load (skeleton while loading) |
| 1.11 | **Project section collapse** | Click expanded project | Content collapses |
| 1.12 | **Empty project hidden (hideIfEmpty)** | Project has no docs/folders | Project section not rendered after data loads |
| 1.13 | **Project with only folders visible** | Project has folders but no unfiled docs | Project section visible |
| 1.14 | **Project lazy-load skeleton** | Expand project first time | ProjectContentSkeleton (3 rows) shown while fetching |
| 1.15 | **Project cached on re-expand** | Collapse and re-expand | No skeleton, data appears instantly |

---

## 2. Document CRUD

### Per context (repeat each in all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 2.1 | **Create document at root** | Right-click tree → New Document (or create button) | Dialog opens, enter name, submit → doc appears in tree at root, editor opens |
| 2.2 | **Create document inside folder** | Right-click folder → New Document | Dialog opens, submit → doc appears inside that folder, parent folder auto-expands |
| 2.3 | **Create document — cancel dialog** | Open create dialog, click cancel/ESC | Dialog closes, no doc created |
| 2.4 | **Create document — empty name rejected** | Submit with blank name | Validation error shown, dialog stays open |
| 2.5 | **View document** | Click document in tree | Editor panel shows document content in read-only mode |
| 2.6 | **Rename document** | Right-click → Rename → type new name → Enter | Name updates inline, tree shows new name |
| 2.7 | **Rename document — cancel** | Press ESC during inline rename | Original name restored |
| 2.8 | **Rename document — empty name** | Clear name and press Enter | Reverts to original name |
| 2.9 | **Delete document** | Right-click → Delete → Confirm | Document removed from tree, selection clears if it was selected |
| 2.10 | **Delete document — cancel** | Right-click → Delete → Cancel | Document still in tree |
| 2.11 | **Delete selected document** | Select doc, then delete it | Editor shows "Select a document" empty state after deletion |

### Notes-App & App-KB only (project-scoped docs):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 2.12 | **Create doc inside project section** | Expand project, right-click project folder → New Document | Doc created with scope=project, appears under project section |
| 2.13 | **Rename doc in project section** | Rename a project-scoped doc | Name updates in project section |
| 2.14 | **Delete doc from project section** | Delete project-scoped doc | Disappears from project section |

---

## 3. Folder CRUD

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 3.1 | **Create root folder** | Create button / right-click tree → New Folder | Folder appears at root level, alphabetically sorted |
| 3.2 | **Create nested subfolder** | Right-click folder → New Subfolder | Subfolder appears inside parent, parent auto-expands |
| 3.3 | **Create at max depth (5)** | Create folder at depth 5 | Success — folder created |
| 3.4 | **Create beyond max depth (6)** | Try to create folder inside depth-5 folder | Error: max depth exceeded |
| 3.5 | **Rename folder** | Right-click → Rename → type → Enter | Name updates inline |
| 3.6 | **Rename folder — duplicate name** | Rename to existing sibling folder name | Error toast: name already exists (409) |
| 3.7 | **Delete empty folder** | Right-click → Delete → Confirm | Folder removed from tree |
| 3.8 | **Delete folder with documents** | Folder has 3 docs, delete it | Folder + all 3 docs disappear (cascade soft-delete) |
| 3.9 | **Delete folder with nested subfolders** | Folder has subfolders with docs | Entire subtree removed |
| 3.10 | **Delete folder — selected doc inside** | Select doc inside folder, then delete folder | Doc disappears, editor shows empty state |

### Notes-App & App-KB only:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 3.11 | **Create folder inside project section** | Right-click in project → New Folder | Folder created with project scope |
| 3.12 | **Delete project folder** | Delete folder in project section | Cascades within project scope only |

---

## 4. Drag and Drop

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 4.1 | **Drag document into folder** | Drag doc, hover folder (highlights), drop | Doc moves into folder, folder auto-expands, toast confirms |
| 4.2 | **Drag document to root** | Drag doc from folder to root drop zone | Doc becomes unfiled (root level), toast confirms |
| 4.3 | **Drag document — already in folder** | Drag doc onto its own folder | No-op (skip if same folder_id) |
| 4.4 | **Drag folder into folder** | Drag folder A onto folder B | A becomes child of B |
| 4.5 | **Drag folder to root** | Drag nested folder to root drop zone | Folder becomes root-level |
| 4.6 | **Drag folder onto itself** | Drag folder and drop on itself | No-op |
| 4.7 | **Prevent circular move** | Drag parent onto its own child | Drop target NOT highlighted, no-op, error toast |
| 4.8 | **Drag folder exceeds max depth** | Drag folder (with 3 nested levels) into depth-3 folder | Backend returns 400, toast error |
| 4.9 | **Drag overlay shows item name** | Start drag | Floating overlay shows icon + item name |
| 4.10 | **Root drop zone appears during drag** | Start any drag | Root drop zone area appears at bottom of tree |
| 4.11 | **Root drop zone hidden when not dragging** | Not dragging | Root drop zone not visible |
| 4.12 | **Drop on document resolves to parent folder** | Drag doc A, drop onto doc B (which is inside folder X) | Doc A moves into folder X (drop target = B's parent) |
| 4.13 | **Drop on root-level document = move to root** | Drag nested doc, drop on unfiled doc at root | Dragged doc moves to root (unfiled) |

### Notes-App & App-KB (cross-scope):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 4.14 | **Prevent cross-scope drag: app → project** | Drag app-level doc, hover project section folder | Drop target NOT highlighted, no-op |
| 4.15 | **Prevent cross-scope drag: project → app** | Drag project doc, hover app-level folder | No-op |
| 4.16 | **DnD within project section** | Drag project doc to project folder (same project) | Move succeeds |
| 4.17 | **DnD between projects blocked** | Drag doc from project A, hover project B folder | No-op (different prefix `project:{idA}` vs `project:{idB}`) |

### Notes-Personal:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 4.18 | **Personal DnD uses personal prefix** | Drag personal doc | Sortable IDs use `personal-doc-{id}`, mutations use scope='personal' |

---

## 5. Document Editing & Save Flow

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 5.1 | **View mode (default)** | Select document | Editor shows content, read-only, "Edit" button visible |
| 5.2 | **Enter edit mode** | Click "Edit" | Lock acquired, editor becomes editable, "Save" and "Cancel" buttons appear |
| 5.3 | **Type content** | In edit mode, type text | Content appears, editor accepts input |
| 5.4 | **Save changes** | Type content → click "Save" | Content persisted, row_version incremented, returns to view mode, lock released |
| 5.5 | **Cancel — no changes** | Enter edit mode, click "Cancel" (no edits made) | Returns to view mode immediately, lock released |
| 5.6 | **Cancel — with changes (discard dialog)** | Type content → click "Cancel" | "Discard changes?" dialog appears |
| 5.7 | **Discard dialog — Keep editing** | Cancel with changes → dialog → "Keep editing" | Dialog closes, still in edit mode, content preserved |
| 5.8 | **Discard dialog — Discard** | Cancel with changes → dialog → "Discard" | Changes reverted, returns to view mode, lock released |
| 5.9 | **Save while locked by other (row_version conflict)** | Client A saves (v1→v2), Client B tries save with stale v1 | 409 Conflict error, toast shown |
| 5.10 | **Rich text editing** | Bold, italic, headings, lists, code blocks, tables | All TipTap extensions render and save correctly |
| 5.11 | **Content heading auto-prepend** | View doc with title "My Doc" | H1 heading "My Doc" + horizontal rule prepended to content |

### Notes page only (editor key behavior):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 5.12 | **Editor remounts on doc switch** | Select doc A (editing), select doc B | Editor fully remounts (key={docId}), TipTap state clean for doc B |
| 5.13 | **Switch doc while dirty → discard dialog** | Edit doc A with changes, click doc B in tree | Discard dialog appears before switching |

### KnowledgePanel (App-KB, Project-KB):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 5.14 | **Editor reuses instance (no key)** | Select doc A, then doc B | Editor content updates without full remount |
| 5.15 | **Quick create "Untitled"** | Click FilePlus button in panel | Document named "Untitled" created, auto-selected, editor opens |

---

## 6. Lock System (2 clients)

### Per context (all 4):

| # | Scenario | Client A | Client B | Verify |
|---|----------|----------|----------|--------|
| 6.1 | **Lock indicator visible** | Acquire lock on doc | View same doc | B sees lock icon / "Locked by A" in action bar |
| 6.2 | **Lock release visible** | Release lock (save/cancel) | View same doc | B sees lock icon disappear, "Edit" enabled |
| 6.3 | **Lock contention** | Hold lock | Click "Edit" on same doc | B gets error toast / disabled Edit button |
| 6.4 | **Force-take lock** | Hold lock | Force-take (owner action) | A gets kicked out of edit mode, toast warning. B enters edit. |
| 6.5 | **Lock reacquire (same user)** | Acquire lock, release, re-acquire | - | No conflict, lock extended |
| 6.6 | **Lock across tree items** | Lock doc A | Lock doc B | Both show locked independently |
| 6.7 | **Lock in batch endpoint** | Lock 3 docs | View scope lock summary | Active-locks batch shows all 3 |

### Lock lifecycle edge cases:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 6.8 | **Heartbeat keeps lock alive** | Enter edit mode, wait 2 minutes (within 5 min TTL) | Lock still held (heartbeat every 30s extends TTL) |
| 6.9 | **Lock released on navigation** | Edit doc in Notes → navigate to Tasks | Lock released (fire-and-forget on unmount) |
| 6.10 | **Lock released on tab switch** | Edit doc in Personal tab → switch to App tab | Lock released (component unmounts) |
| 6.11 | **Lock released on doc switch** | Edit doc A → click doc B in tree | Discard/save dialog → lock on A released after resolution |

---

## 7. Inactivity & Timeout

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 7.1 | **Inactivity dialog appears** | Enter edit mode, wait 5 min (no interaction) | "Are you still editing?" dialog appears |
| 7.2 | **Inactivity — Keep editing** | Dialog → "Keep Editing" | Dialog closes, stays in edit mode, timer resets |
| 7.3 | **Inactivity — Save** | Dialog → "Save" | Content saved, returns to view mode, lock released |
| 7.4 | **Inactivity — Discard** | Dialog → "Discard" | Changes discarded, returns to view mode, lock released |
| 7.5 | **Inactivity auto-save (60s countdown)** | Dialog shows → wait 60s without action | Auto-saves, returns to view mode |

---

## 8. Quit/Close Protection

### Notes page and KnowledgePanel:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 8.1 | **Quit with unsaved changes** | Edit doc with changes → close window (X button) | "Unsaved changes" dialog appears (Save and close / Discard and close / Keep editing) |
| 8.2 | **Quit — Save and close** | Dialog → "Save and close" | Content saved, app closes |
| 8.3 | **Quit — Discard and close** | Dialog → "Discard and close" | Changes discarded, app closes |
| 8.4 | **Quit — Keep editing** | Dialog → "Keep editing" | Dialog closes, stays in edit mode |
| 8.5 | **Quit without changes** | View mode or clean edit → close window | App closes immediately (no dialog) |

---

## 9. Search & Filtering

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 9.1 | **Search filters tree** | Type query in search bar | Only matching folders/docs shown |
| 9.2 | **Search auto-expands folders** | Search term matches doc inside collapsed folder | Parent folder auto-expands to show match |
| 9.3 | **Search — no results** | Search for nonexistent term | "No results found" message |
| 9.4 | **Clear search** | Clear search input | Full tree restored |
| 9.5 | **Search is case-insensitive** | Create "My Document", search "my document" | Match found |
| 9.6 | **Search partial match** | Create "Architecture Notes", search "Arch" | Match found |

### Notes-App & App-KB:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 9.7 | **Search filters project sections** | Search query matches project name | Project section visible, non-matching hidden |
| 9.8 | **Search inside project sections** | Search matches doc inside project | Project section + matching content shown |

---

## 10. Context Menu

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 10.1 | **Folder context menu** | Right-click folder | Shows: New Subfolder, New Document, Rename, Delete |
| 10.2 | **Document context menu** | Right-click document | Shows: Rename, Delete; also selects doc in editor |
| 10.3 | **Context menu closes on click outside** | Open context menu, click elsewhere | Menu closes |
| 10.4 | **Context menu folder highlight** | Right-click folder | Folder gets transient highlight (isSelected=true via contextMenuFolderId) |
| 10.5 | **New Subfolder from context menu** | Right-click folder → New Subfolder → enter name → submit | Subfolder created inside that folder |
| 10.6 | **New Document from context menu** | Right-click folder → New Document → enter name → submit | Doc created inside that folder |

---

## 11. Optimistic Updates & Cache

### Per context (all 4), single client:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 11.1 | **Optimistic create doc** | Create document | Appears in tree IMMEDIATELY (before server 201) |
| 11.2 | **Temp ID replaced** | After create | Tree item ID changes from TEMP_xxx to real UUID (no duplicate) |
| 11.3 | **Optimistic create folder** | Create folder | Appears in tree immediately |
| 11.4 | **Optimistic rename** | Rename doc/folder | Name changes instantly, no flicker back |
| 11.5 | **Optimistic delete** | Delete doc/folder | Removed from tree instantly |
| 11.6 | **Optimistic move (DnD)** | Move doc to folder | Appears in new folder instantly, removed from old |
| 11.7 | **Rollback on error** | Move to invalid target (server 400) | Item returns to original position, error toast |

---

## 12. WebSocket Real-Time Sync (2 clients)

### Per context (all 4):

| # | Scenario | Client A | Client B | Verify |
|---|----------|----------|----------|--------|
| 12.1 | **Doc created → appears on B** | Create doc | Observe tree | B: doc appears (WS DOCUMENT_CREATED) |
| 12.2 | **Doc renamed → updates on B** | Rename doc | Observe tree | B: name changes |
| 12.3 | **Doc deleted → disappears on B** | Delete doc | Observe tree | B: doc removed |
| 12.4 | **Folder created → appears on B** | Create folder | Observe tree | B: folder appears |
| 12.5 | **Folder renamed → updates on B** | Rename folder | Observe tree | B: name changes |
| 12.6 | **Folder deleted → disappears on B** | Delete folder (with docs) | Observe tree | B: folder + docs removed |
| 12.7 | **Doc moved → B sees new location** | Move doc to folder via DnD | Observe tree | B: doc appears in new folder |
| 12.8 | **Skip-own events** | Create doc | Observe own tree | A: doc appears ONCE (optimistic), not duplicated by own WS event |
| 12.9 | **Lock event → B sees indicator** | Acquire lock | Observe doc in tree | B: lock icon appears |
| 12.10 | **Unlock event → B sees removal** | Release lock | Observe tree | B: lock icon disappears |
| 12.11 | **Force-take → A notified** | Hold lock | Force-take | A: exits edit mode, sees toast |
| 12.12 | **B's selected doc deleted by A** | Select doc | Delete same doc | B: selection clears, editor shows empty state |
| 12.13 | **Content update → B refreshes** | Save content | View same doc | B: sees updated content (cache invalidated by WS) |

### Cross-context WS (2 different screens):

| # | Scenario | Client A (on...) | Client B (on...) | Verify |
|---|----------|------------------|------------------|--------|
| 12.14 | **Notes ↔ App-KB** | Notes App tab | App Detail KB tab (same app) | CRUD operations sync between both |
| 12.15 | **Notes ↔ Project-KB** | Notes App tab (project section) | Project Detail KB tab (same project) | Project-scoped CRUD syncs |
| 12.16 | **App-KB → Project-KB** | App Detail KB | Project Detail KB (project under same app) | Project-scoped doc created in App-KB shows in Project-KB |
| 12.17 | **Project-KB → Notes App tab** | Project Detail KB | Notes App tab (same app) | Doc created in project appears under project section in Notes |

---

## 13. Navigation & Tab Switching

### Notes page only:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 13.1 | **Personal → App tab** | Click app tab | Personal tree unmounts, app tree loads |
| 13.2 | **App → Personal tab** | Click personal tab | App tree unmounts, personal tree loads from cache |
| 13.3 | **Tab switch preserves selection per tab** | Select doc A (personal), switch to app, select doc B, switch back | Personal tab shows doc A selected again |
| 13.4 | **Tab switch — dirty guard** | Edit doc in personal tab, switch to app tab | Discard dialog appears (dirty state blocks navigation) |
| 13.5 | **Multiple app tabs** | Have 2 apps with docs | Tab bar shows both app names, switch between them |
| 13.6 | **App tab shows only apps with docs** | App X has docs, App Y has none | Tab bar shows X but not Y (ScopesSummary) |

### All contexts:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 13.7 | **Folder expand state persisted** | Expand folders → switch away → come back | Same folders still expanded (localStorage) |
| 13.8 | **Selected doc persisted** | Select doc → switch away → come back | Same doc still selected (localStorage) |
| 13.9 | **Navigate away from Notes** | Click "Tasks" in sidebar | Notes page unmounts, locks released |
| 13.10 | **Navigate back to Notes** | Click "Notes" in sidebar | Notes page remounts, state restored from localStorage + cache |

### App/Project Knowledge Panel:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 13.11 | **Panel state isolated** | Open App A KB, expand folders. Open App B KB. | App B starts with collapsed folders (separate storagePrefix) |
| 13.12 | **Panel resizable** | Drag resize handle | Tree panel width changes (200-500px range) |

---

## 14. Loading States & Skeletons

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 14.1 | **Tree skeleton on first load** | First visit (no cache) | 6-row TreeSkeleton shown |
| 14.2 | **No skeleton when cached** | Revisit after data loaded | Tree appears instantly |
| 14.3 | **Folder docs lazy-load skeleton** | Expand folder with docs (first time) | 2-row skeleton inside folder while loading |
| 14.4 | **Folder docs cached on re-expand** | Collapse and re-expand | No skeleton |
| 14.5 | **Editor skeleton** | Select doc (first load) | EditorSkeleton (title bar + content lines) |
| 14.6 | **Editor "not found"** | Select doc that was deleted by other user | "Document not found" message |

### Notes-App & App-KB:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 14.7 | **Project section skeleton** | Expand project section (first time) | ProjectContentSkeleton (3 rows) while fetching |
| 14.8 | **Background refresh indicator** | Data loaded, background refetch happening | Subtle loading indicator (Loader2 spinner) without skeleton |

---

## 15. Tags

### Per context (all 4):

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 15.1 | **Assign tag to document** | Open doc → assign tag from tag picker | Tag chip appears on document |
| 15.2 | **Remove tag from document** | Click X on tag chip | Tag removed |
| 15.3 | **Duplicate tag assignment rejected** | Assign same tag twice | Error toast (409) |

### Scope validation:

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 15.4 | **App tag on app doc** | Assign app-scoped tag to app-scoped doc | Success |
| 15.5 | **App tag on project doc (same app)** | Assign app-scoped tag to project doc | Success (project's parent app matches) |
| 15.6 | **Personal tag on personal doc** | Assign personal tag to personal doc | Success |
| 15.7 | **App tag on personal doc** | Try to assign | Rejected (scope mismatch) |

---

## 16. Trash (Soft Delete) Flows

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 16.1 | **Deleted doc goes to trash** | Delete doc | Doc disappears from tree, visible in trash view |
| 16.2 | **Restore from trash** | Navigate to trash → Restore doc | Doc reappears in tree |
| 16.3 | **Permanent delete** | Trash → Permanent delete | Doc gone permanently, not in tree or trash |
| 16.4 | **Trash list filters by scope** | Delete docs in personal + app scope | Trash shows only scope-relevant docs |

---

## 17. Content Conversion

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 17.1 | **TipTap content round-trip** | Edit: headings, bold, lists, code, table → Save → Reload | All formatting preserved exactly |
| 17.2 | **Content saved as markdown** | Save rich content via API | API response includes content_markdown correctly derived |
| 17.3 | **Content saved as plain text** | Save rich content via API | API response includes content_plain correctly derived |

---

## 18. Edge Cases & Boundary Conditions

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 18.1 | **Rapid create** | Create 5 docs in quick succession | All 5 appear, no duplicates, no race conditions |
| 18.2 | **Long document title** | Create doc with 255-char title | Title truncated with ellipsis in tree, full title in editor |
| 18.3 | **Special characters in name** | Create doc with `<script>`, `é`, `日本語` | Rendered correctly, no XSS |
| 18.4 | **Concurrent rename** | A renames doc, B renames same doc | Last writer wins (no row_version on folders), doc-rename checks version |
| 18.5 | **Delete while editing** | A editing doc → B deletes same doc | A receives WS event, exits edit mode, shows empty state |
| 18.6 | **Create doc with same name** | Two docs named "Notes" in same folder | Both created successfully (docs allow duplicate names) |
| 18.7 | **Folder name conflict** | Create folder "Docs", try creating "docs" (case) | 409 case-insensitive conflict |
| 18.8 | **Large tree performance** | 100+ folders and documents | Tree renders without lag, scroll works, DnD responsive |

---

## 19. WebSocket Room Management

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 19.1 | **Join personal room** | Navigate to Notes → Personal tab | WS joins `user:{userId}`, receives personal events |
| 19.2 | **Join app room** | Switch to App tab | WS leaves personal room, joins `application:{appId}` |
| 19.3 | **Room switch on tab change** | Switch from App A tab to App B tab | Leaves `application:{appA}`, joins `application:{appB}` |
| 19.4 | **Project room (Project-KB)** | Open project Knowledge tab | WS joins `project:{projectId}` |
| 19.5 | **Room cleanup on unmount** | Navigate away from Notes | All WS rooms left (cleanup effect) |
| 19.6 | **Events scoped to room** | Client A creates doc in App X | Client B in App Y does NOT see it (different room) |

---

## 20. Resizable Panel (App-KB & Project-KB)

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 20.1 | **Resize tree panel wider** | Drag handle right | Tree panel gets wider (up to 500px max) |
| 20.2 | **Resize tree panel narrower** | Drag handle left | Tree panel gets narrower (down to 200px min) |
| 20.3 | **Resize doesn't exceed bounds** | Drag beyond min/max | Clamped at 200px min, 500px max |

---

## Summary Count

| Category | Scenarios |
|----------|-----------|
| Tree Rendering & Empty States | 15 |
| Document CRUD | 14 |
| Folder CRUD | 12 |
| Drag and Drop | 18 |
| Document Editing & Save | 15 |
| Lock System (2-client) | 11 |
| Inactivity & Timeout | 5 |
| Quit/Close Protection | 5 |
| Search & Filtering | 8 |
| Context Menu | 6 |
| Optimistic Updates & Cache | 7 |
| WebSocket Real-Time Sync | 17 |
| Navigation & Tab Switching | 12 |
| Loading States & Skeletons | 8 |
| Tags | 7 |
| Trash (Soft Delete) | 4 |
| Content Conversion | 3 |
| Edge Cases | 8 |
| WebSocket Room Management | 6 |
| Resizable Panel | 3 |
| **TOTAL** | **184** |

---

## Test File Organization (Playwright)

```
electron-app/e2e/tests/
├── smoke.spec.ts                          # App launch, login, navigation
├── two-client-smoke.spec.ts               # 2-client infrastructure
│
├── notes-personal/
│   ├── tree-rendering.spec.ts             # 1.1-1.8
│   ├── document-crud.spec.ts              # 2.1-2.11
│   ├── folder-crud.spec.ts                # 3.1-3.10
│   ├── dnd.spec.ts                        # 4.1-4.13, 4.18
│   ├── editing.spec.ts                    # 5.1-5.13
│   ├── search.spec.ts                     # 9.1-9.6
│   └── context-menu.spec.ts              # 10.1-10.6
│
├── notes-app/
│   ├── tree-rendering.spec.ts             # 1.1-1.15
│   ├── document-crud.spec.ts              # 2.1-2.14
│   ├── folder-crud.spec.ts                # 3.1-3.12
│   ├── dnd.spec.ts                        # 4.1-4.17
│   ├── editing.spec.ts                    # 5.1-5.13
│   ├── search.spec.ts                     # 9.1-9.8
│   ├── tabs.spec.ts                       # 13.1-13.6
│   └── project-sections.spec.ts          # 1.9-1.15
│
├── app-knowledge/
│   ├── tree-rendering.spec.ts             # 1.1-1.15
│   ├── document-crud.spec.ts              # 2.1-2.14
│   ├── folder-crud.spec.ts                # 3.1-3.12
│   ├── dnd.spec.ts                        # 4.1-4.17
│   ├── editing.spec.ts                    # 5.1-5.15
│   ├── search.spec.ts                     # 9.1-9.8
│   └── resize.spec.ts                    # 20.1-20.3
│
├── project-knowledge/
│   ├── tree-rendering.spec.ts             # 1.1-1.8
│   ├── document-crud.spec.ts              # 2.1-2.11
│   ├── folder-crud.spec.ts                # 3.1-3.10
│   ├── dnd.spec.ts                        # 4.1-4.13
│   ├── editing.spec.ts                    # 5.1-5.11, 5.14-5.15
│   ├── search.spec.ts                     # 9.1-9.6
│   └── resize.spec.ts                    # 20.1-20.3
│
├── collaborative/ (2-client tests)
│   ├── ws-document-sync.spec.ts           # 12.1-12.8
│   ├── ws-folder-sync.spec.ts             # 12.4-12.8
│   ├── ws-lock-sync.spec.ts               # 6.1-6.7, 12.9-12.13
│   ├── ws-cross-context.spec.ts           # 12.14-12.17
│   └── lock-contention.spec.ts           # 6.1-6.11
│
├── shared/
│   ├── tags.spec.ts                       # 15.1-15.7
│   ├── trash.spec.ts                      # 16.1-16.4
│   ├── optimistic-cache.spec.ts           # 11.1-11.7
│   ├── loading-skeletons.spec.ts          # 14.1-14.8
│   ├── inactivity.spec.ts                # 7.1-7.5
│   ├── quit-protection.spec.ts           # 8.1-8.5
│   ├── content-conversion.spec.ts        # 17.1-17.3
│   ├── ws-rooms.spec.ts                  # 19.1-19.6
│   └── edge-cases.spec.ts               # 18.1-18.8
```
