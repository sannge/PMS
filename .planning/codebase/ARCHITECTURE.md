# Architecture

**Analysis Date:** 2026-01-31

## Pattern Overview

**Overall:** Multi-tier application with client-server separation. Backend serves as a REST/WebSocket API; frontend is an Electron app with React UI. The architecture uses layered separation of concerns: API layer, business logic layer, data access layer on the backend, and component-driven UI with state management on the frontend.

**Key Characteristics:**
- **REST + WebSocket Hybrid**: REST for CRUD operations, WebSocket for real-time collaboration and event broadcasting
- **Role-based Access Control (RBAC)**: Users, Applications, Projects with hierarchical permission inheritance
- **Room-based Broadcasting**: WebSocket connections organized into rooms (tasks, projects, applications) for targeted event distribution
- **Async Throughout**: Fully async backend using FastAPI and async SQLAlchemy; async frontend with React hooks and TanStack Query
- **Entity Hierarchy**: Application > Project > Task with ownership cascading through membership tables

## Layers

**API/Router Layer:**
- Purpose: HTTP/WebSocket endpoint definitions and request validation
- Location: `fastapi-backend/app/routers/` (REST endpoints), `fastapi-backend/app/websocket/handlers.py` (WebSocket message routing)
- Contains: FastAPI Router instances, request validation using Pydantic schemas, HTTP status handling
- Depends on: Service layer, database session, authentication tokens
- Used by: External clients (Electron frontend), direct API consumers

**Business Logic/Service Layer:**
- Purpose: Core application logic independent of protocol/storage
- Location: `fastapi-backend/app/services/`
- Contains: `auth_service.py` (user auth, tokens), `permission_service.py` (RBAC checks), `notification_service.py` (event creation), `archive_service.py` (scheduled cleanup), `status_derivation_service.py` (task aggregation), `user_cache_service.py` (in-memory role caching)
- Depends on: Data access (models/database), external services (Redis, MinIO)
- Used by: API routers, WebSocket handlers

**Data Access/Model Layer:**
- Purpose: SQLAlchemy ORM models and database queries
- Location: `fastapi-backend/app/models/` (ORM definitions), database session via `fastapi-backend/app/database.py`
- Contains: Entity definitions (User, Application, Project, Task, Comment, Checklist, etc.), relationships, foreign keys
- Depends on: PostgreSQL database, Alembic migrations
- Used by: Services for data persistence

**WebSocket Management Layer:**
- Purpose: Connection state, room management, cross-worker broadcasting
- Location: `fastapi-backend/app/websocket/`
- Contains: `manager.py` (connection pooling, room subscriptions), `handlers.py` (message routing and business logic), `presence.py` (ephemeral user activity tracking), `room_auth.py` (permission checks for joining rooms)
- Depends on: Redis for pub/sub across workers
- Used by: FastAPI WebSocket endpoint

**Frontend Component Layer:**
- Purpose: React components for UI rendering
- Location: `electron-app/src/renderer/components/`
- Contains: Domain-specific components (tasks, projects, applications, notes) and UI primitives (shadcn/ui)
- Depends on: Hooks for data fetching and mutations, stores for state
- Used by: Page components, other components

**Frontend State Management Layer:**
- Purpose: Data fetching, caching, and local state
- Location: `electron-app/src/renderer/hooks/` (data queries via TanStack Query), `electron-app/src/renderer/contexts/` (auth, notifications, notes), `electron-app/src/renderer/stores/` (legacy Zustand stores being migrated to Context)
- Contains: `use-queries.ts` (all data fetching queries), `use-websocket.ts` (WebSocket subscription and cache invalidation), `auth-context.tsx` (authentication state), `notification-ui-context.tsx` (toast notifications)
- Depends on: TanStack Query client, WebSocket client, backend API
- Used by: Components for data and state access

**Frontend Utility Layer:**
- Purpose: Cross-cutting concerns and helpers
- Location: `electron-app/src/renderer/lib/`
- Contains: `query-client.ts` (TanStack Query setup with IndexedDB persistence), `websocket.ts` (WebSocket client with reconnection), `query-cache-db.ts` (IndexedDB schema), `notifications.ts` (browser notifications API)
- Depends on: Browser APIs, external libraries
- Used by: State management and components

## Data Flow

**Create/Update Task Flow:**

1. User submits form in TaskForm component
2. Component calls `useMutation` from `use-queries.ts` (e.g., `useCreateTask`)
3. Mutation sends POST/PATCH to `fastapi-backend/app/routers/tasks.py` endpoint
4. Router validates token via `get_current_user()`, deserializes request to TaskCreate schema
5. Router calls `verify_project_access()` to check RBAC via PermissionService
6. Router calls service function (e.g., `task_service.update_task()`) to execute business logic
7. Service updates database via SQLAlchemy ORM
8. Service calls `handle_task_update()` in websocket handlers to broadcast event
9. WebSocket handler publishes message to Redis pub/sub channel for room (e.g., `project:{project_id}`)
10. WebSocket manager broadcasts MessageType.TASK_UPDATED to all connections in that room
11. Frontend `use-websocket.ts` listens for event and invalidates TanStack Query cache for task queries
12. Components re-render with fresh data from cache or new API call
13. Optimistic update shown to user immediately; actual update merged after server confirmation

**Real-time Collaboration (Presence & Awareness):**

1. User opens project detail view
2. Component mounts `usePresenceManager` hook which subscribes to `project:{project_id}:presence` room
3. Backend presence_manager broadcasts user's cursor position, viewing status periodically
4. Other users receive USER_VIEWING and USER_PRESENCE events via WebSocket
5. Components render presence indicators (avatars, typing cursors) near task/note being viewed

**WebSocket Room Subscription Flow:**

1. On component mount (e.g., opening task detail), component calls `useJoinRoom('task', taskId)`
2. `use-websocket.ts` sends `join_room` message to backend
3. Backend `route_incoming_message()` calls `check_room_access()` to verify user permission
4. Manager adds connection to room
5. Backend publishes ROOM_JOINED confirmation to user
6. Future events in room are broadcast to all subscribed connections
7. On unmount, component calls `useLeaveRoom()` to unsubscribe

**State Management:**

- **Authentication**: Stored in React Context (`auth-context.tsx`), persisted in localStorage
- **Query Data**: Cached in TanStack Query with IndexedDB persistence (`query-client.ts`), invalidated on WebSocket updates
- **Notifications**: Toast notifications in React Context (`notification-ui-context.tsx`)
- **Notes/Documents**: Specialized context for collaborative editing state (`notes-context.tsx`)
- **Ephemeral State** (presence, viewing): Managed in WebSocket manager, not persisted

## Key Abstractions

**Application/Project/Task Hierarchy:**
- Purpose: Multi-level organizational structure mimicking Jira
- Examples: `fastapi-backend/app/models/application.py`, `project.py`, `task.py`
- Pattern: Owner-based root access; ApplicationMember/ProjectMember RBAC; foreign key cascade relationships

**Room-Based Broadcasting:**
- Purpose: Target updates to specific users (only those viewing that entity)
- Examples: Rooms named `task:{id}`, `project:{id}`, `application:{id}`
- Pattern: WebSocket manager maintains in-memory Map<roomName, Set<Connection>>; Redis pub/sub syncs across workers

**Permission Service:**
- Purpose: Centralized RBAC logic
- Examples: `fastapi-backend/app/services/permission_service.py`
- Pattern: Hierarchical permission inheritance (App Owner > Project Editor > Task Assignee); cached role lookups

**Status Aggregation:**
- Purpose: Derive project/task status from child entities
- Examples: `fastapi-backend/app/services/status_derivation_service.py`, `ProjectTaskStatusAgg` model
- Pattern: Materialized views (ProjectTaskStatusAgg table) updated on task changes; computed on-demand for efficiency

**Pydantic Schemas:**
- Purpose: Request/response validation and serialization
- Examples: `fastapi-backend/app/schemas/task.py`
- Pattern: Separate create/update/response schemas; nested schemas for relationships; discriminated unions for polymorphic types

**Query Client with Persistence:**
- Purpose: Smart caching with offline-first architecture
- Examples: `electron-app/src/renderer/lib/query-client.ts`, `per-query-persister.ts`
- Pattern: TanStack Query + IndexedDB for per-query persistence; automatic hydration on app load; LRU eviction

## Entry Points

**Backend:**
- Location: `fastapi-backend/app/main.py`
- Triggers: `uvicorn app.main:app` command
- Responsibilities:
  - FastAPI app creation and configuration
  - CORS middleware setup
  - Router registration (all 14 domain routers)
  - WebSocket endpoint (`/ws`) with token validation and rate limiting
  - Lifespan events (startup: warmup DB, connect Redis, start services; shutdown: cleanup)
  - Global exception handlers

**Frontend:**
- Location: `electron-app/src/renderer/main.tsx`
- Triggers: Electron renderer process startup
- Responsibilities:
  - React 18 root creation with StrictMode
  - Global error handlers for unhandled promise rejections and errors

**Frontend App Root:**
- Location: `electron-app/src/renderer/App.tsx`
- Triggers: Rendered by main.tsx
- Responsibilities:
  - Provider nesting (QueryClientProvider, AuthProvider, ThemeProvider, ErrorBoundary)
  - State-based routing (login/register vs dashboard based on auth state)
  - Theme persistence and dark/light mode management
  - Error boundary for graceful error UI

**Frontend Dashboard:**
- Location: `electron-app/src/renderer/pages/dashboard.tsx`
- Triggers: Rendered when user is authenticated
- Responsibilities:
  - Sidebar navigation with auth state
  - Page routing via state (applications, projects, tasks, notes)
  - WebSocket connection lifecycle management
  - Cache invalidation on disconnections (e.g., project member removal)

## Error Handling

**Strategy:** Multi-layer error handling with user-facing fallbacks

**Patterns:**

- **HTTP Errors**: FastAPI HTTPException with status codes; global exception handler logs to console and returns 500 JSON
- **WebSocket Errors**: Connection closes with code and reason; client auto-reconnects with exponential backoff
- **Database Errors**: SQLAlchemy TimeoutError caught and returned as 503 Service Unavailable; pool exhaustion triggers client retry
- **Validation Errors**: Pydantic models raise ValidationError, FastAPI returns 422 Unprocessable Entity with field-level errors
- **Permission Errors**: `PermissionService.check_*()` methods raise HTTPException 403 Forbidden
- **React Error Boundary**: Catches component render errors and displays error UI with reload button
- **Query Errors**: TanStack Query catches fetch errors, stored in query state; components render error UI conditionally

## Cross-Cutting Concerns

**Logging:**
- Backend: Python logging module configured at startup; logs to stdout with INFO level
- Frontend: Browser console in development; can be integrated with error tracking (e.g., Sentry)

**Validation:**
- Backend: Pydantic models for request validation; FastAPI auto-validates query/path/body parameters
- Frontend: React Hook Form or manual validation in components before submission

**Authentication:**
- Backend: JWT tokens (HS256) issued by `create_access_token()`; validated in `get_current_user()` dependency
- Frontend: Token stored in localStorage, sent in Authorization header for REST calls and as query parameter for WebSocket
- Token re-validation: Backend re-validates every 30 minutes on WebSocket connection

**Authorization:**
- Backend: `PermissionService.check_*()` methods enforce RBAC at endpoint/action level
- WebSocket: `check_room_access()` validates user has permission before joining room
- Frontend: Components check `user.role` before rendering edit buttons, but server is source of truth

**Caching:**
- Query-level: TanStack Query + IndexedDB (frontend)
- Role-level: In-memory caches in `user_cache_service.py` (backend)
- Redis: Pub/sub for multi-worker broadcasting, optional single-worker mode fallback

---

*Architecture analysis: 2026-01-31*
