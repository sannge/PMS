# Architecture Overview

PM Desktop follows a layered architecture with clear separation between frontend, backend, and real-time communication.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Electron Application                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        React Renderer Process                       │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │ │
│  │  │  Components  │  │    Pages     │  │        UI Library        │  │ │
│  │  │  (Radix UI)  │  │ (Dashboard)  │  │  (shadcn/ui + Tailwind)  │  │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────────────────────┘  │ │
│  │         │                 │                                         │ │
│  │  ┌──────▼─────────────────▼─────────────────────────────────────┐  │ │
│  │  │                     Custom Hooks Layer                        │  │ │
│  │  │  useAuth │ useProjects │ useTasks │ useWebSocket │ useCache  │  │ │
│  │  └──────┬─────────────────┬─────────────────┬───────────────────┘  │ │
│  │         │                 │                 │                       │ │
│  │  ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐               │ │
│  │  │React Context│  │ TanStack Query│  │  WebSocket  │               │ │
│  │  │  Providers  │  │    Client     │  │   Client    │               │ │
│  │  │(Client State)│ │(Server State) │  │ (Real-time) │               │ │
│  │  └──────┬──────┘  └───────┬───────┘  └──────┬──────┘               │ │
│  │         │                 │                 │                       │ │
│  │  ┌──────▼─────────────────▼─────────────────▼───────────────────┐  │ │
│  │  │                       IndexedDB                               │  │ │
│  │  │              (Persistent Cache with LZ-String)                │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│                    HTTP REST API   │   WebSocket                        │
└────────────────────────────────────┼─────────────────────────────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │        FastAPI Backend       │
                      │  ┌────────────────────────┐  │
                      │  │     API Routers        │  │
                      │  │  (REST + WebSocket)    │  │
                      │  └───────────┬────────────┘  │
                      │              │               │
                      │  ┌───────────▼────────────┐  │
                      │  │    Services Layer      │  │
                      │  │ (Business Logic + Auth)│  │
                      │  └───────────┬────────────┘  │
                      │              │               │
                      │  ┌───────────▼────────────┐  │
                      │  │  SQLAlchemy Models     │  │
                      │  │     (ORM Layer)        │  │
                      │  └───────────┬────────────┘  │
                      └──────────────┼───────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
   ┌─────▼─────┐         ┌──────▼──────┐       ┌──────▼──────┐    ┌─────────────┐
   │PostgreSQL │         │    Redis    │       │   MinIO     │    │ Meilisearch │
   │(Database) │         │  (Cache)    │       │  (Files)    │    │  (Search)   │
   └───────────┘         └─────────────┘       └─────────────┘    └─────────────┘
```

## Data Flow Patterns

### 1. Read Request Flow

```
User Action (View Project)
    │
    ▼
React Component
    │
    ├─► Check TanStack Query Cache (in-memory)
    │       │
    │       ├─► Cache Hit (fresh) → Return data immediately
    │       │
    │       ├─► Cache Hit (stale) → Return data + refetch in background
    │       │
    │       └─► Cache Miss → Check IndexedDB
    │                           │
    │                           ├─► IndexedDB Hit → Decompress + return + refetch
    │                           │
    │                           └─► IndexedDB Miss → Fetch from API
    │
    ▼
API Request (GET /projects/{id})
    │
    ▼
FastAPI Router
    │
    ├─► Validate JWT Token
    │
    ├─► Check User Permissions
    │
    └─► Query Database (SQLAlchemy)
            │
            ▼
        Return JSON Response
            │
            ▼
TanStack Query
    │
    ├─► Store in memory cache
    │
    └─► Persist to IndexedDB (compressed)
            │
            ▼
        Render UI
```

### 2. Write Request Flow

```
User Action (Create Task)
    │
    ▼
React Component (onSubmit)
    │
    ▼
useMutation Hook
    │
    ├─► Optimistic Update (immediate UI feedback)
    │
    └─► POST /tasks
            │
            ▼
        FastAPI Router
            │
            ├─► Validate Request (Pydantic)
            │
            ├─► Check Permissions
            │
            ├─► Create in Database
            │
            ├─► Update Aggregations
            │
            └─► Broadcast via WebSocket
                    │
                    ▼
                WebSocket Manager
                    │
                    ├─► Send to project:{id} room
                    │
                    └─► Send to target users
                            │
                            ▼
                        All Connected Clients
                            │
                            └─► Invalidate Query Cache
                                    │
                                    └─► Refetch + Re-render
```

### 3. Real-Time Update Flow

```
WebSocket Connection Established
    │
    ▼
Client Joins Rooms
    │
    ├─► project:{project_id}  (Kanban board viewers)
    ├─► task:{task_id}        (Task detail viewers)
    └─► application:{app_id}  (App-level events)
            │
            ▼
Server Event Occurs (e.g., task updated)
    │
    ▼
WebSocket Handler
    │
    ├─► Create Message Payload
    │
    ├─► Determine Target Rooms
    │
    └─► Broadcast to Rooms
            │
            ▼
All Clients in Room Receive Event
    │
    ▼
Client-side Handler
    │
    ├─► Check Message Deduplication
    │
    ├─► Invalidate Related Queries
    │
    └─► TanStack Query Refetches
            │
            └─► UI Updates Automatically
```

## State Management Architecture

PM Desktop uses a three-layer state management approach:

### Layer 1: Server State (TanStack Query)

**Purpose**: Manage data that comes from the server (tasks, projects, comments, etc.)

**Features**:
- Automatic caching with stale-while-revalidate
- Request deduplication
- Background refetching
- Optimistic updates
- Persistent cache via IndexedDB

**Example**:
```typescript
// Query hook for fetching tasks
const { data: tasks, isLoading } = useQuery({
  queryKey: ['tasks', projectId],
  queryFn: () => api.getTasks(projectId),
  staleTime: 5 * 60 * 1000, // 5 minutes
});

// Mutation for creating task
const createTask = useMutation({
  mutationFn: api.createTask,
  onSuccess: () => {
    queryClient.invalidateQueries(['tasks', projectId]);
  },
});
```

### Layer 2: Client State (React Context)

**Purpose**: Manage UI state that doesn't need server persistence

**Contexts**:
- `auth-context.tsx` - User session, JWT token, login/logout
- `knowledge-base-context.tsx` - Active document, tree state, search, tabs
- `notification-ui-context.tsx` - Toast queue, notification display

**Example**:
```typescript
// Context-based auth state
const { user, login, logout } = useAuth();

// Knowledge base UI state
const { selectedDocumentId, searchQuery, expandedFolders } = useKnowledgeBase();
```

### Layer 3: React Context (Cross-cutting Concerns)

**Purpose**: Provide app-wide access to authentication, theme, and UI utilities

**Contexts**:
- `AuthContext` - Login/logout, user fetching, token management
- `NotificationUIContext` - Toast notifications
- `KnowledgeBaseContext` - Knowledge base UI state (selection, tree, search)
- `ThemeContext` - Dark/light mode

**Example**:
```typescript
// Provider hierarchy in App.tsx
<QueryClientProvider client={queryClient}>
  <AuthProvider>
    <NotificationUIProvider>
      <ThemeProvider>
        <ErrorBoundary>
          {/* App content */}
        </ErrorBoundary>
      </ThemeProvider>
    </NotificationUIProvider>
  </AuthProvider>
</QueryClientProvider>
```

## Component Architecture

### Component Hierarchy

```
App.tsx
├── Providers (Query, Auth, Notifications, Theme)
│   └── AuthGate (state-based routing)
│       ├── LoginPage / RegisterPage (unauthenticated)
│       └── DashboardPage (authenticated)
│           ├── Sidebar
│           │   ├── ApplicationList
│           │   └── Navigation
│           ├── Header
│           │   ├── SearchBar
│           │   ├── NotificationBell
│           │   └── UserMenu
│           └── MainContent
│               ├── ApplicationPage
│               │   ├── ProjectList
│               │   └── MemberList
│               ├── ProjectPage
│               │   ├── KanbanBoard
│               │   │   ├── StatusColumn
│               │   │   └── TaskCard
│               │   └── PresenceIndicators
│               └── TaskDetailModal
│                   ├── TaskHeader
│                   ├── TaskDescription
│                   ├── CommentThread
│                   ├── ChecklistPanel
│                   └── AttachmentList
│               └── NotesPage
│                   ├── KnowledgeSidebar
│                   │   └── KnowledgeTree
│                   └── DocumentEditor
│                       ├── EditorToolbar
│                       └── TipTap (with document locking)
```

### Component Categories

| Category | Location | Purpose |
|----------|----------|---------|
| UI Primitives | `components/ui/` | Radix UI wrappers, shadcn/ui components |
| Feature Components | `components/{feature}/` | Business logic components |
| Layout Components | `components/layout/` | Header, sidebar, panels |
| Page Components | `pages/` | Route-level components |

## Backend Architecture

### Layer Structure

```
Request
    │
    ▼
┌─────────────────────────────────────┐
│          API Router Layer           │
│  (Request validation, routing)      │
│  routers/tasks.py, routers/auth.py  │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│          Service Layer              │
│  (Business logic, authorization)    │
│  services/permission_service.py     │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│          Model Layer                │
│  (Database access via ORM)          │
│  models/task.py, models/user.py     │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│          Database Layer             │
│  (PostgreSQL via SQLAlchemy)        │
│  database.py, alembic migrations    │
└─────────────────────────────────────┘
```

### Request Processing

1. **Request Received**: FastAPI receives HTTP request
2. **Validation**: Pydantic schema validates request body/params
3. **Authentication**: JWT token verified via `get_current_user` dependency
4. **Authorization**: Permission service checks user access
5. **Business Logic**: Service layer processes request
6. **Database**: SQLAlchemy executes queries
7. **Response**: Pydantic schema serializes response
8. **WebSocket**: Real-time broadcast to relevant clients

## Database Architecture

### Entity Relationships

```
User
 │
 ├──► owns ──► Application
 │               │
 │               ├──► contains ──► Project
 │               │                   │
 │               │                   ├──► contains ──► Task
 │               │                   │                   │
 │               │                   │                   ├──► has ──► Comments
 │               │                   │                   ├──► has ──► Checklists
 │               │                   │                   └──► has ──► Attachments
 │               │                   │
 │               │                   ├──► has ──► TaskStatuses
 │               │                   └──► has ──► ProjectMembers
 │               │
 │               ├──► has ──► DocumentFolders
 │               │                   │
 │               │                   └──► contains ──► Documents
 │               │
 │               ├──► has ──► ApplicationMembers
 │               └──► has ──► Invitations
 │
 ├──► assigned to ──► Task
 ├──► mentioned in ──► Comment
 └──► receives ──► Notification
```

### Key Design Decisions

1. **Denormalization for Performance**
   - `Task.checklist_total`, `Task.checklist_done` - Avoid counting on every read
   - `ProjectTaskStatusAgg` - Pre-computed status counts for project status derivation

2. **Lexorank for Ordering**
   - `Task.task_rank` - String-based ordering for efficient reordering in Kanban

3. **Soft Relationships**
   - `Task.parent_id` - Self-referential for subtasks
   - `Comment.task_id` + `Comment.parent_id` - Threaded comments

## Caching Strategy

### Multi-Level Cache

```
┌─────────────────────────────────────┐
│     Level 1: In-Memory (React)      │
│  TanStack Query cache (30s stale)   │
│  Fastest access, limited size       │
└─────────────────┬───────────────────┘
                  │ Cache Miss
                  ▼
┌─────────────────────────────────────┐
│     Level 2: IndexedDB (Browser)    │
│  Persistent, LZ-String compressed   │
│  50MB limit, LRU eviction           │
└─────────────────┬───────────────────┘
                  │ Cache Miss
                  ▼
┌─────────────────────────────────────┐
│     Level 3: Redis (Server)         │
│  User objects, session data         │
│  Shared across instances            │
└─────────────────┬───────────────────┘
                  │ Cache Miss
                  ▼
┌─────────────────────────────────────┐
│     Level 4: PostgreSQL             │
│  Source of truth                    │
│  Connection pooling (50+100)        │
└─────────────────────────────────────┘
```

### Cache Invalidation

Caches are invalidated via:
1. **Time-based**: Stale time expiration (30 seconds default)
2. **Event-based**: WebSocket events trigger cache invalidation
3. **Manual**: User actions (create, update, delete) invalidate related queries
4. **Auth-based**: Logout clears all caches

## Security Architecture

### Authentication Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     Authentication Flow                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. User Login                                                    │
│     ┌─────────┐  POST /auth/login   ┌─────────────┐              │
│     │ Client  │ ──────────────────► │   Server    │              │
│     │         │  {email, password}  │             │              │
│     └─────────┘                     └──────┬──────┘              │
│                                            │                      │
│  2. Token Generation                       │ Verify password      │
│                                            │ Create JWT           │
│     ┌─────────┐  {access_token}     ┌──────▼──────┐              │
│     │ Client  │ ◄────────────────── │   Server    │              │
│     │         │                     │             │              │
│     └────┬────┘                     └─────────────┘              │
│          │                                                        │
│  3. Token Storage                                                 │
│          │ Store in:                                              │
│          ├─► AuthContext (memory)                                  │
│          └─► localStorage (persistence)                           │
│                                                                   │
│  4. Authenticated Requests                                        │
│     ┌─────────┐  Authorization: Bearer {token}  ┌───────────┐    │
│     │ Client  │ ───────────────────────────────►│  Server   │    │
│     └─────────┘                                 └─────┬─────┘    │
│                                                       │           │
│  5. Token Validation                                  │ Decode JWT│
│                                                       │ Check exp │
│     ┌─────────┐  Protected Resource             ┌─────▼─────┐    │
│     │ Client  │ ◄───────────────────────────────│  Server   │    │
│     └─────────┘                                 └───────────┘    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Authorization Levels

| Level | Check | Implementation |
|-------|-------|----------------|
| Route | JWT valid | `get_current_user` dependency |
| Application | User is member | `check_app_member` service |
| Project | User is member | `check_project_member` service |
| Task | User has project access | Via project membership |
| Role | User role sufficient | Role comparison (owner > editor > viewer) |

## Performance Optimizations

### Frontend

| Optimization | Technique | Impact |
|--------------|-----------|--------|
| Code Splitting | Dynamic imports | Faster initial load |
| Compression | LZ-String for cache | 80% storage reduction |
| Deduplication | Request & message | Reduced network/renders |
| Virtual Scrolling | react-virtuoso | Handle large lists |
| Memoization | React.memo, useMemo | Prevent re-renders |
| SWR | Stale-while-revalidate | Instant perceived loads |

### Backend

| Optimization | Technique | Impact |
|--------------|-----------|--------|
| Connection Pool | 50 base + 100 overflow | Handle concurrent requests |
| Eager Loading | selectinload | Prevent N+1 queries |
| Indexes | Composite indexes | Faster query execution |
| Denormalization | Aggregation tables | Avoid expensive counts |
| Room Broadcast | O(1) to room members | Scale to 5000+ users |
| Rate Limiting | 100 msg/10s per user | Prevent overload |

## Scalability Considerations

### Horizontal Scaling

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │  (Sticky WS)    │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │ Server 1│          │ Server 2│          │ Server 3│
   │ FastAPI │          │ FastAPI │          │ FastAPI │
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌──────────────┼──────────────┼──────────────┐
        │              │              │              │
   ┌────▼────┐    ┌────▼────┐   ┌────▼────┐   ┌────▼──────┐
   │PostgreSQL│   │  Redis  │   │  MinIO  │   │Meilisearch│
   │(Primary) │   │(Shared) │   │(Shared) │   │ (Search)  │
   └──────────┘   └─────────┘   └─────────┘   └───────────┘
```

### Scale Considerations

1. **WebSocket Affinity**: Use sticky sessions for WebSocket connections
2. **Redis Pub/Sub**: Cross-server event distribution (when needed)
3. **Database Replica**: Read replicas for query distribution
4. **File Storage**: MinIO clusters for high availability
