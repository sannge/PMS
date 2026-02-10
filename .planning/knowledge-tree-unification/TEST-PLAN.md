# Knowledge Base E2E Test Plan (Playwright + Electron)

**Last Updated**: 2026-02-09
**Tool**: Playwright (Electron mode, 2-client fixtures)
**Scope**: All knowledge base features across 4 contexts, excluding permissions, files, and attachments.

---

## Prerequisites

Before running E2E tests, ensure the following are running and configured:

### Backend Services
- **FastAPI** backend running on port 8001: `cd fastapi-backend && uvicorn app.main:app --reload --port 8001`
- **PostgreSQL** database accessible with test schema migrated (`alembic upgrade head`)
- **Redis** 7+ running (used for WebSocket pub/sub and document locks)
- **Meilisearch** running (used for full-text search)

### Frontend Build
- Electron app must be built before running E2E tests:
  ```bash
  cd electron-app
  npm install
  npm run build
  ```

### Test User Setup
Two test users must be seeded in the database:

| User | Email | Password |
|------|-------|----------|
| User 1 | `e2e-user1@test.com` | `TestPassword123!` |
| User 2 | `e2e-user2@test.com` | `TestPassword123!` |

### Test Data Requirements
- Both users must be members of the **"E2E Test App"** application
- The **"E2E Test Project"** must exist under "E2E Test App"
- Both users must have at least Editor role on the application
- At least one tag should exist in personal scope and one in app scope (for tag tests)

---

## Test Scope & Exclusions

### Included in E2E Tests
- All knowledge base features across 4 contexts (Notes-Personal, Notes-App, App-KB, Project-KB)
- Document and folder CRUD operations
- Drag-and-drop functionality
- Rich-text editing with TipTap
- WebSocket real-time sync between clients
- Document locking and lock contention
- Search and filtering
- Optimistic updates and cache behavior
- Loading states and skeletons
- Inactivity and quit protection dialogs
- Tags and trash (soft delete) flows
- Content conversion (TipTap → Markdown → Plain text)

### Explicitly Excluded
- **Permissions**: Role-based access control (Owner/Editor/Viewer) is not tested in E2E
  - Reason: Permission scenarios are covered in backend unit tests
  - Future: May add permission E2E tests in separate suite
- **File attachments**: Uploading files to documents
  - Reason: File upload UI not yet implemented
- **Document versioning**: Snapshot and version history features
  - Reason: Not yet implemented in UI
- **Collaborative editing**: Real-time co-editing with CRDT (Yjs)
  - Reason: Requires more complex 2-client coordination, planned for future
- **Performance testing**: Load testing for 5000 concurrent users
  - Reason: Requires separate performance test infrastructure

---

## Architecture Overview

### The 4 Contexts

| Context | Route | Tree Component | Scope | WS Room |
|---------|-------|---------------|-------|---------|
| **Notes - Personal** | Sidebar > Notes > "My Notes" tab | KnowledgeTree (no appId) | personal | `user:{userId}` |
| **Notes - App** | Sidebar > Notes > App tab | KnowledgeTree (appId) | application | `application:{appId}` |
| **App Knowledge Tab** | App Detail > Knowledge tab | KnowledgePanel > ApplicationTree | application | `application:{appId}` |
| **Project Knowledge Tab** | Project Detail > Knowledge tab | KnowledgePanel > FolderTree | project | `project:{projectId}` |

### Fixture Types

| Fixture | File | Provides | Used For |
|---------|------|----------|----------|
| **Single Client** | `fixtures/electron-app.ts` | `electronApp`, `window` | CRUD, DnD, caching, search, navigation, single-user flows |
| **Two Clients** | `fixtures/two-clients.ts` | `app1`, `app2`, `window1`, `window2` | WebSocket real-time sync, lock contention, concurrent operations, cross-room validation |

### Helper Files

| File | Purpose |
|------|---------|
| `helpers/auth.ts` | Login, navigation to all 4 contexts, test user constants |
| `helpers/knowledge-ops.ts` | Document/folder CRUD, edit mode, DnD, search, tree inspection |
| `helpers/wait.ts` | WebSocket update waits, removal waits, network idle, brief pauses |

---

## Test File Organization

```
electron-app/e2e/
├── playwright.config.ts              # Playwright configuration
├── tsconfig.json                     # TypeScript configuration
├── fixtures/
│   ├── electron-app.ts               # Single Electron app fixture
│   └── two-clients.ts                # Two Electron app fixture
├── helpers/
│   ├── auth.ts                       # Login + navigation helpers
│   ├── knowledge-ops.ts              # Tree operation helpers
│   └── wait.ts                       # Wait/polling helpers
└── tests/
    ├── smoke.spec.ts                        # App launch + login smoke test
    ├── two-client-smoke.spec.ts             # 2-client infrastructure smoke test
    │
    ├── notes-personal/                      # Personal (My Notes) context
    │   ├── tree-rendering.spec.ts           # #1.1-1.8
    │   ├── document-crud.spec.ts            # #2.1-2.11
    │   ├── folder-crud.spec.ts              # #3.1-3.10
    │   ├── dnd.spec.ts                      # #4.1-4.13, 4.18
    │   ├── editing.spec.ts                  # #5.1-5.13
    │   ├── search.spec.ts                   # #9.1-9.6
    │   └── context-menu.spec.ts             # #10.1-10.6
    │
    ├── notes-app/                           # App tab context (Notes page)
    │   ├── tree-rendering.spec.ts           # #1.1-1.15
    │   ├── document-crud.spec.ts            # #2.1-2.14
    │   ├── folder-crud.spec.ts              # #3.1-3.12
    │   ├── dnd.spec.ts                      # #4.1-4.17
    │   ├── editing.spec.ts                  # #5.1-5.13
    │   ├── search.spec.ts                   # #9.1-9.8
    │   ├── tabs.spec.ts                     # #13.1-13.6
    │   └── project-sections.spec.ts         # #1.9-1.15
    │
    ├── app-knowledge/                       # App Detail > Knowledge tab
    │   ├── tree-rendering.spec.ts           # #1.1-1.15
    │   ├── document-crud.spec.ts            # #2.1-2.14
    │   ├── folder-crud.spec.ts              # #3.1-3.12
    │   ├── dnd.spec.ts                      # #4.1-4.17
    │   ├── editing.spec.ts                  # #5.1-5.15
    │   ├── search.spec.ts                   # #9.1-9.8
    │   └── resize.spec.ts                   # #20.1-20.3
    │
    ├── project-knowledge/                   # Project Detail > Knowledge tab
    │   ├── tree-rendering.spec.ts           # #1.1-1.8
    │   ├── document-crud.spec.ts            # #2.1-2.11
    │   ├── folder-crud.spec.ts              # #3.1-3.10
    │   ├── dnd.spec.ts                      # #4.1-4.13
    │   ├── editing.spec.ts                  # #5.1-5.11, 5.14-5.15
    │   ├── search.spec.ts                   # #9.1-9.6
    │   └── resize.spec.ts                   # #20.1-20.3
    │
    ├── collaborative/                       # 2-client WebSocket tests
    │   ├── ws-document-sync.spec.ts         # #12.1-12.3, 12.7-12.8, 12.12-12.13
    │   ├── ws-folder-sync.spec.ts           # #12.4-12.6
    │   ├── ws-lock-sync.spec.ts             # #6.1-6.7, 12.9-12.11
    │   ├── ws-cross-context.spec.ts         # #12.14-12.17
    │   └── lock-contention.spec.ts          # #6.1-6.11
    │
    └── shared/                              # Cross-context tests (work across all 4 contexts)
        ├── tags.spec.ts                     # #15.1-15.7
        ├── trash.spec.ts                    # #16.1-16.4
        ├── optimistic-cache.spec.ts         # #11.1-11.7
        ├── loading-skeletons.spec.ts        # #14.1-14.8
        ├── inactivity.spec.ts               # #7.1-7.5 (uses test.slow())
        ├── quit-protection.spec.ts          # #8.1-8.5
        ├── content-conversion.spec.ts       # #17.1-17.3
        ├── ws-rooms.spec.ts                 # #19.1-19.6 (mixed: single + two-client)
        └── edge-cases.spec.ts               # #18.1-18.8 (mixed: single + two-client)
```

---

## Running Tests

### Run All E2E Tests

```bash
cd electron-app/e2e
npx playwright test
```

### Run by Context

```bash
# Notes - Personal context only
npx playwright test tests/notes-personal/

# Notes - App context only
npx playwright test tests/notes-app/

# App Knowledge tab context only
npx playwright test tests/app-knowledge/

# Project Knowledge tab context only
npx playwright test tests/project-knowledge/
```

### Run by Category

```bash
# Collaborative (2-client) tests
npx playwright test tests/collaborative/

# Shared (cross-context) tests
npx playwright test tests/shared/
```

### Run Individual File

```bash
# Single test file
npx playwright test tests/notes-personal/editing.spec.ts

# Single test file in shared
npx playwright test tests/shared/tags.spec.ts
npx playwright test tests/shared/optimistic-cache.spec.ts
```

### Run Specific Test by Name

```bash
# Run tests matching a keyword
npx playwright test -g "optimistic create"
npx playwright test -g "inactivity"
npx playwright test -g "quit"
```

---

## Debugging Failures

### Interactive Debug Mode

```bash
# Opens Playwright Inspector for step-through debugging
npx playwright test --debug

# Debug a specific file
npx playwright test tests/shared/edge-cases.spec.ts --debug
```

### Traces and Artifacts

Traces are captured on first retry (configured in `playwright.config.ts`):

- **Traces**: `test-results/artifacts/` (Playwright trace files)
- **Screenshots**: Captured on failure automatically
- **Videos**: Captured on first retry

### HTML Report

```bash
# Generate and open the HTML report
npx playwright show-report test-results/html
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Tests timeout on launch | Increase `timeout` in fixture (currently 60s) |
| Login fails | Verify test users are seeded in the database |
| WS events not arriving | Check Redis is running, backend WS handler is active |
| Tree not loading | Verify backend API is responding on port 8001 |
| "App not found" | Ensure "E2E Test App" exists and users are members |
| Slow tests timing out | Use `test.slow()` to triple timeout (120s → 360s) |
| Electron launch failure | Run `npm run build` before E2E tests |
| Route interception not working | Verify API URL patterns match actual endpoints |

---

## Shared Test Files — Scenario Coverage

### `tags.spec.ts` (Scenarios #15.1-15.7)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 15.1 | Assign tag to document | Single | Tag chip appears after assignment |
| 15.2 | Remove tag from document | Single | Tag chip disappears after X click |
| 15.3 | Duplicate tag assignment rejected | Single | 409 error toast or prevented at UI level |
| 15.4 | App tag on app doc | Single | Assignment succeeds, no scope error |
| 15.5 | App tag on project doc (same app) | Single | Assignment succeeds (parent app matches) |
| 15.6 | Personal tag on personal doc | Single | Assignment succeeds |
| 15.7 | App tag on personal doc | Single | Rejected as scope mismatch (or filtered from picker) |

### `trash.spec.ts` (Scenarios #16.1-16.4)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 16.1 | Deleted doc goes to trash | Single | Doc disappears from tree, appears in trash view |
| 16.2 | Restore from trash | Single | Restored doc reappears in tree |
| 16.3 | Permanent delete | Single | Doc gone from both tree and trash |
| 16.4 | Trash filters by scope | Single | Personal trash shows only personal docs |

### `optimistic-cache.spec.ts` (Scenarios #11.1-11.7)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 11.1 | Optimistic create doc | Single | Doc visible in < 1s despite 2s API delay |
| 11.2 | Temp ID replaced | Single | No TEMP prefix, exactly 1 tree item after server response |
| 11.3 | Optimistic create folder | Single | Folder visible in < 1s despite 2s API delay |
| 11.4 | Optimistic rename | Single | New name appears in < 1s, no flicker to old name |
| 11.5 | Optimistic delete | Single | Item removed in < 1s despite 2s API delay |
| 11.6 | Optimistic move (DnD) | Single | Item in new folder immediately despite 2s delay |
| 11.7 | Rollback on error | Single | Item returns to original position, error toast shown |

### `loading-skeletons.spec.ts` (Scenarios #14.1-14.8)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 14.1 | Tree skeleton on first load | Single | Skeleton visible (or tree loads) with API delay |
| 14.2 | No skeleton when cached | Single | Tree renders in < 3s from cache on revisit |
| 14.3 | Folder docs lazy-load skeleton | Single | Inline skeleton on first expand, docs load |
| 14.4 | Folder docs cached on re-expand | Single | No skeleton on re-expand, docs visible in < 1s |
| 14.5 | Editor skeleton | Single | Editor skeleton or editor loads with API delay |
| 14.6 | Editor "not found" | Single | "Document not found" message on 404 |
| 14.7 | Project section skeleton | Single | ProjectContentSkeleton on first project expand |
| 14.8 | Background refresh indicator | Single | No full skeleton, subtle spinner on background refetch |

### `inactivity.spec.ts` (Scenarios #7.1-7.5)

| # | Scenario | Fixture | Timeout | Key Assertions |
|---|----------|---------|---------|----------------|
| 7.1 | Inactivity dialog appears | Single | `test.slow()` | Dialog appears after 5 min idle |
| 7.2 | Keep editing | Single | `test.slow()` | Dialog closes, stays in edit mode |
| 7.3 | Save | Single | `test.slow()` | Content saved, returns to view mode |
| 7.4 | Discard | Single | `test.slow()` | Changes lost, returns to view mode |
| 7.5 | Auto-save (60s countdown) | Single | `test.slow()` | Auto-saves after countdown, edit mode exits |

### `quit-protection.spec.ts` (Scenarios #8.1-8.5)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 8.1 | Quit with unsaved changes | Single | Unsaved changes dialog with 3 options |
| 8.2 | Save and close | Single | Content saved (API call), app closes |
| 8.3 | Discard and close | Single | No save API call, app closes |
| 8.4 | Keep editing | Single | Dialog closes, still in edit mode, content preserved |
| 8.5 | Quit without changes | Single | No dialog, immediate close |

### `content-conversion.spec.ts` (Scenarios #17.1-17.3)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 17.1 | TipTap content round-trip | Single | Headings, bold, lists, code preserved after save+reload |
| 17.2 | Content saved as markdown | Single | API response includes correct content_markdown |
| 17.3 | Content saved as plain text | Single | API response includes content_plain without formatting |

### `ws-rooms.spec.ts` (Scenarios #19.1-19.6)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 19.1 | Join personal room | Single | Tree loads, CRUD works in personal scope |
| 19.2 | Join app room | Single | Tab switch loads app tree, CRUD works |
| 19.3 | Room switch on tab change | Single | App docs not in personal, cached on return |
| 19.4 | Project room | Single | Project tree loads, CRUD works |
| 19.5 | Room cleanup on unmount | Single | Navigate away + back successfully re-joins |
| 19.6 | Events scoped to room | Two-Client | Doc in App X not seen by Client B in Personal tab |

### `edge-cases.spec.ts` (Scenarios #18.1-18.8)

| # | Scenario | Fixture | Key Assertions |
|---|----------|---------|----------------|
| 18.1 | Rapid create (5 docs) | Single | All 5 appear, each exactly once |
| 18.2 | Long title (255 chars) | Single | Truncated in tree, visible in editor |
| 18.3 | Special characters / XSS | Single | Rendered as text, no script execution |
| 18.4 | Concurrent rename | Two-Client | Last writer wins, one name visible |
| 18.5 | Delete while editing | Two-Client | Editor exits edit mode, shows empty state |
| 18.6 | Duplicate doc names | Single | Both docs coexist (count = 2) |
| 18.7 | Folder name conflict (case) | Single | 409 conflict error shown |
| 18.8 | Large tree performance | Single | 20+ items render, scroll works, DnD responsive |

---

## Test Count Summary

| Category | File | Scenarios | Fixture |
|----------|------|-----------|---------|
| Tags | `shared/tags.spec.ts` | 7 | Single |
| Trash | `shared/trash.spec.ts` | 4 | Single |
| Optimistic Updates | `shared/optimistic-cache.spec.ts` | 7 | Single |
| Loading States | `shared/loading-skeletons.spec.ts` | 8 | Single |
| Inactivity | `shared/inactivity.spec.ts` | 5 | Single (slow) |
| Quit Protection | `shared/quit-protection.spec.ts` | 5 | Single |
| Content Conversion | `shared/content-conversion.spec.ts` | 3 | Single |
| WS Rooms | `shared/ws-rooms.spec.ts` | 6 | Single + Two-Client |
| Edge Cases | `shared/edge-cases.spec.ts` | 8 | Single + Two-Client |
| **TOTAL (shared)** | **9 files** | **53** | |

### Full Suite Summary

| Directory | Files | Scenarios |
|-----------|-------|-----------|
| `notes-personal/` | 7 | ~50 |
| `notes-app/` | 8 | ~65 |
| `app-knowledge/` | 7 | ~60 |
| `project-knowledge/` | 7 | ~45 |
| `collaborative/` | 5 | ~35 |
| `shared/` | 9 | 53 |
| Smoke tests | 2 | 2 |
| **TOTAL** | **45** | **~310** |

---

## Test Design Patterns

### Unique Names
All test-created entities use `Date.now()` suffixes to avoid collisions between test runs:
```typescript
const docName = `TestDoc-${Date.now()}`
```

### Test Independence
Every test is fully independent. Tests create their own data and do not depend on data from other tests. The `beforeEach` hook handles login and navigation.

### Optimistic Testing with Route Interception
To prove optimistic updates, tests intercept API routes and add delays:
```typescript
await window.route('**/documents', async (route) => {
  if (route.request().method() === 'POST') {
    await new Promise(r => setTimeout(r, 2000))
    await route.continue()
  } else {
    await route.continue()
  }
})
```
Then assert the UI updated within 1 second (before the 2-second delay completes).

### Slow Tests
Inactivity tests use `test.slow()` to triple the default 120-second timeout to 360 seconds.

### Two-Client Tests in Shared Files
Some shared files (`ws-rooms.spec.ts`, `edge-cases.spec.ts`) import from both fixtures and have separate `test.describe` blocks:
```typescript
import { test, expect } from '../../fixtures/electron-app'
import { test as twoClientTest, expect as expect2 } from '../../fixtures/two-clients'

test.describe('Single client tests', () => { ... })
twoClientTest.describe('Two client tests', () => { ... })
```

### Graceful Assertions
Tests use `.catch()` chains for assertions that may vary based on UI implementation details (e.g., different empty state messages, skeleton timing). The primary assertion always has a fallback that verifies the core behavior.
