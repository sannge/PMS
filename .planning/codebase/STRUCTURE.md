# Codebase Structure

**Analysis Date:** 2026-01-31

## Directory Layout

```
pm-project/
├── fastapi-backend/              # Python FastAPI backend
│   ├── app/                      # Main application code
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── routers/              # FastAPI endpoint routers
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── services/             # Business logic services
│   │   ├── websocket/            # WebSocket management and handlers
│   │   ├── utils/                # Utility functions
│   │   ├── main.py               # FastAPI app initialization
│   │   ├── database.py           # Database connection and session management
│   │   └── config.py             # Configuration from environment variables
│   ├── alembic/                  # Database migrations
│   ├── tests/                    # pytest unit and integration tests
│   ├── scripts/                  # Utility scripts
│   └── requirements.txt           # Python dependencies
│
├── electron-app/                 # Electron + React frontend
│   ├── src/
│   │   ├── main/                 # Electron main process
│   │   ├── preload/              # Preload scripts for IPC security
│   │   └── renderer/             # React renderer process
│   │       ├── components/       # React components by domain
│   │       ├── pages/            # Page-level components (layout + routing)
│   │       ├── hooks/            # Custom React hooks (data queries, WebSocket)
│   │       ├── stores/           # Legacy Zustand stores (migrating to Context)
│   │       ├── contexts/         # React Context providers
│   │       ├── lib/              # Utility libraries (query client, WebSocket, etc)
│   │       ├── App.tsx           # Root component with providers
│   │       └── main.tsx          # React entry point
│   ├── out/                      # Compiled TypeScript output
│   ├── tests/                    # E2E tests
│   ├── package.json              # npm dependencies and scripts
│   └── tsconfig.json             # TypeScript configuration
│
├── .planning/
│   └── codebase/                 # Codebase analysis documents
│       ├── ARCHITECTURE.md       # Architecture patterns and layers
│       ├── STRUCTURE.md          # This file - directory structure guidance
│       ├── CONVENTIONS.md        # Code style and naming conventions
│       ├── TESTING.md            # Testing patterns and frameworks
│       ├── STACK.md              # Technology stack overview
│       ├── INTEGRATIONS.md       # External services and APIs
│       └── CONCERNS.md           # Technical debt and issues
│
├── docs/                         # User documentation
│   └── user-manual/
│
├── tests/                        # Root-level E2E tests
│   └── e2e/                      # End-to-end test files
│
└── CLAUDE.md                     # Project instructions and context
```

## Directory Purposes

**fastapi-backend/app/models/:**
- Purpose: SQLAlchemy ORM entity definitions with relationships and constraints
- Contains: 18 model files (User, Application, Project, Task, Comment, Checklist, etc.)
- Key files: `task.py` (core task entity), `application.py` (app root), `project.py` (project), `user.py` (user)

**fastapi-backend/app/routers/:**
- Purpose: FastAPI endpoint definitions organized by domain
- Contains: 14 router files handling CRUD for all entities
- Key files: `tasks.py` (91KB, task CRUD with status logic), `projects.py` (60KB, project CRUD), `applications.py` (41KB, app management)

**fastapi-backend/app/schemas/:**
- Purpose: Pydantic models for request validation and response serialization
- Contains: 13 schema files mirroring models with separate Create/Update/Response types
- Key files: `task.py` (complex task schemas with nested types), `project.py` (project schemas)

**fastapi-backend/app/services/:**
- Purpose: Business logic services used by routers
- Contains: 10 service files handling auth, permissions, notifications, caching, etc.
- Key files:
  - `permission_service.py` (18KB, role-based access control)
  - `auth_service.py` (JWT token creation/validation)
  - `user_cache_service.py` (in-memory role caching)
  - `notification_service.py` (event/notification creation)
  - `status_derivation_service.py` (task status aggregation)
  - `archive_service.py` (scheduled cleanup of archived items)

**fastapi-backend/app/websocket/:**
- Purpose: WebSocket connection management and real-time event broadcasting
- Contains: 4 files
- Key files:
  - `manager.py` (22KB, connection pooling and room management)
  - `handlers.py` (68KB, message routing and business logic)
  - `presence.py` (16KB, ephemeral user activity tracking)
  - `room_auth.py` (8KB, permission checks for room access)

**electron-app/src/renderer/components/:**
- Purpose: Reusable React components organized by domain
- Contains: 17 subdirectories
- Key directories:
  - `ui/` - shadcn/ui primitive components (button, dialog, input, etc.)
  - `tasks/` - task-specific components (task list, task card, task form)
  - `projects/` - project components (project list, kanban board)
  - `applications/` - app management components
  - `notes/` - collaborative note editor components
  - `layout/` - sidebar, header, notification panel
  - `kanban/` - drag-and-drop board implementation
  - `comments/` - comment thread components
  - `checklists/` - checklist components

**electron-app/src/renderer/pages/:**
- Purpose: Full-page components that handle routing and orchestrate sub-components
- Contains: 4 page files + 2 subdirectories for detail pages
- Key files:
  - `dashboard.tsx` (30KB, main dashboard with navigation)
  - `applications/index.tsx` (applications list page)
  - `applications/[id].tsx` (application detail page)
  - `projects/index.tsx` (projects list page)
  - `projects/[id].tsx` (project detail page with kanban)
  - `notes/index.tsx` (collaborative notes interface)

**electron-app/src/renderer/hooks/:**
- Purpose: Custom React hooks for data fetching, mutations, WebSocket subscriptions
- Contains: 15 hook files
- Key files:
  - `use-queries.ts` (50KB, all TanStack Query query definitions and cache keys)
  - `use-websocket.ts` (27KB, WebSocket subscription management and cache invalidation)
  - `use-websocket-cache.ts` (22KB, specific cache invalidation patterns)
  - `use-notifications.ts` (21KB, notification handling)
  - `use-invitations.ts` (14KB, invitation mutations)

**electron-app/src/renderer/contexts/:**
- Purpose: React Context providers for global state
- Contains: 3 context files
- Key files:
  - `auth-context.tsx` (authentication state, token management)
  - `notification-ui-context.tsx` (toast notification queue)
  - `notes-context.tsx` (collaborative editing state)

**electron-app/src/renderer/lib/:**
- Purpose: Utility libraries and helpers
- Contains: 14 utility files
- Key files:
  - `query-client.ts` (TanStack Query setup with IndexedDB persistence)
  - `websocket.ts` (WebSocket client with auto-reconnection)
  - `per-query-persister.ts` (IndexedDB persistence strategy)
  - `query-cache-db.ts` (IndexedDB schema definition)

**fastapi-backend/alembic/:**
- Purpose: Database schema migrations
- Contains: Migration scripts generated by Alembic
- Key: Always run migrations before deploying new code with schema changes

**fastapi-backend/tests/:**
- Purpose: pytest unit and integration tests
- Contains: Test files parallel to src structure

## Key File Locations

**Entry Points:**

- `fastapi-backend/app/main.py` - Backend API server startup
- `electron-app/src/renderer/main.tsx` - Frontend React entry point
- `electron-app/src/renderer/App.tsx` - Root React component with providers
- `electron-app/src/renderer/pages/dashboard.tsx` - Main authenticated UI

**Configuration:**

- `fastapi-backend/app/config.py` - Backend settings from environment
- `electron-app/tsconfig.json` - TypeScript compiler configuration
- `electron-app/package.json` - Frontend dependencies and scripts
- `fastapi-backend/requirements.txt` - Backend Python dependencies
- `.env.example` (if exists) - Environment variable template

**Core Logic:**

- `fastapi-backend/app/services/permission_service.py` - Role-based access control
- `fastapi-backend/app/services/auth_service.py` - JWT authentication
- `fastapi-backend/app/websocket/handlers.py` - Real-time event routing
- `electron-app/src/renderer/hooks/use-queries.ts` - All data fetching queries
- `electron-app/src/renderer/lib/query-client.ts` - TanStack Query configuration

**Testing:**

- `fastapi-backend/tests/` - Backend unit/integration tests
- `tests/e2e/` - End-to-end tests
- `electron-app/tests/` - Electron-specific tests (if any)

## Naming Conventions

**Files:**

- **Models**: PascalCase (`user.py`, `application.py`, `project_member.py`)
- **Routers**: lowercase with underscores, plural (`tasks.py`, `project_members.py`, `applications.py`)
- **Schemas**: PascalCase inside files, but file is plural lowercase (`task.py` contains `TaskCreate`, `TaskResponse`)
- **Services**: lowercase with `_service` suffix (`auth_service.py`, `permission_service.py`)
- **Components**: PascalCase with .tsx extension (`TaskCard.tsx`, `ProjectList.tsx`)
- **Hooks**: camelCase with `use-` prefix (`use-queries.ts`, `use-websocket.ts`)
- **Utils/Lib**: camelCase (`query-client.ts`, `websocket.ts`)
- **Types**: PascalCase or interfaces with I prefix if needed

**Directories:**

- **Backend**: lowercase with underscores (`app`, `models`, `routers`, `websocket`)
- **Frontend**: lowercase with hyphens for multi-word (`renderer`, `auth-context`, `use-queries`)
- **Domain grouping**: lowercase, plural for many items (`components`, `routers`, `models`)

**Functions/Variables:**

- **Backend**: snake_case (`get_current_user()`, `verify_project_access()`)
- **Frontend**: camelCase (`useCreateTask()`, `handleTaskUpdate()`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_STALE_TIME`, `MAX_OVERFLOW`)

**Types/Interfaces:**

- **Backend**: PascalCase classes/enums (`TaskCreate`, `MessageType`)
- **Frontend**: PascalCase (`TaskResponse`, `DashboardProps`)

## Where to Add New Code

**New Feature (Full Stack):**

1. **Backend Model**: Add SQLAlchemy class to `fastapi-backend/app/models/{domain}.py`
   - Include relationships, foreign keys, indexes
   - Add migration: `alembic revision --autogenerate -m "Add feature"`

2. **Backend Schema**: Add Pydantic classes to `fastapi-backend/app/schemas/{domain}.py`
   - Separate Create, Update, Response schemas
   - Use validators for business rules

3. **Backend Router**: Add endpoints to `fastapi-backend/app/routers/{domain}.py`
   - Include `get_current_user` dependency for auth
   - Call `permission_service.check_*()` for RBAC
   - Publish WebSocket events via `handle_*()` functions

4. **Backend Service**: Add functions to `fastapi-backend/app/services/{domain}_service.py` if complex logic
   - Keep routers thin, move logic to services
   - Services handle DB transactions and external calls

5. **Frontend Hook**: Add query/mutation to `electron-app/src/renderer/hooks/use-queries.ts`
   - Define query key in `queryKeys` object
   - Use `useQuery` for reads, `useMutation` for writes

6. **Frontend Component**: Create in `electron-app/src/renderer/components/{domain}/`
   - Use the hook from use-queries.ts
   - Render error and loading states
   - Use Radix UI components from `components/ui/`

7. **Frontend WebSocket Sync**: Add listener in `electron-app/src/renderer/hooks/use-websocket.ts`
   - Invalidate query cache on server events
   - Subscribe to relevant rooms

**New Component/Module:**

- **Shared Component**: Place in `electron-app/src/renderer/components/{feature}/` with descriptive name
- **Feature Hook**: Add to `electron-app/src/renderer/hooks/` if reusable across components
- **Utility Function**: Add to `electron-app/src/renderer/lib/{util-name}.ts` if not domain-specific

**Utilities:**

- **Backend Helpers**: Add to `fastapi-backend/app/utils/` for non-service logic
- **Frontend Helpers**: Add to `electron-app/src/renderer/lib/` with clear naming

## Special Directories

**fastapi-backend/alembic/:**
- Purpose: Database schema migration scripts
- Generated: Yes (use `alembic revision --autogenerate`)
- Committed: Yes, all migrations committed to git

**electron-app/out/:**
- Purpose: Compiled TypeScript output (ES modules)
- Generated: Yes (via `tsc` during build)
- Committed: No, generated during build

**electron-app/node_modules/:**
- Purpose: npm installed dependencies
- Generated: Yes (via `npm install`)
- Committed: No

**fastapi-backend/.venv/:**
- Purpose: Python virtual environment
- Generated: Yes (via `python -m venv .venv`)
- Committed: No

**.planning/codebase/:**
- Purpose: Codebase analysis documents (this structure, architecture, conventions, etc.)
- Generated: No, manually written by code analyzer
- Committed: Yes, guides future development

**tests/ and fastapi-backend/tests/:**
- Purpose: Test files
- Location: Mirror source structure for unit tests, separate for E2E
- Convention: File names match source with `.test.ts` or `test_*.py` suffix

---

*Structure analysis: 2026-01-31*
