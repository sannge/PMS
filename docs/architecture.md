# Architecture Overview

PM Desktop follows a layered architecture with clear separation between frontend, backend, AI agent, and real-time communication. The system includes a full AI copilot (Blair) built on LangGraph, collaborative document editing, hybrid search, and background job processing.

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
│  │  │  useAuth | useProjects | useTasks | useWebSocket | useAIChat │  │ │
│  │  └──────┬─────────────────┬─────────────────┬───────────────────┘  │ │
│  │         │                 │                 │                       │ │
│  │  ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐               │ │
│  │  │   Zustand   │  │ TanStack Query│  │  WebSocket  │               │ │
│  │  │   Stores    │  │    Client     │  │   Client    │               │ │
│  │  │(Client State)│ │(Server State) │  │ (Real-time) │               │ │
│  │  └──────┬──────┘  └───────┬───────┘  └──────┬──────┘               │ │
│  │         │                 │                 │                       │ │
│  │  ┌──────▼─────────────────▼─────────────────▼───────────────────┐  │ │
│  │  │                       IndexedDB                               │  │ │
│  │  │              (Persistent Cache with LZ-String)                │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│                    HTTP REST API   │   WebSocket / SSE                   │
└────────────────────────────────────┼─────────────────────────────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │        FastAPI Backend       │
                      │  ┌────────────────────────┐  │
                      │  │     API Routers (27)   │  │
                      │  │  (REST + WebSocket)    │  │
                      │  └───────────┬────────────┘  │
                      │              │               │
                      │  ┌───────────▼────────────┐  │
                      │  │   Services Layer (19)  │  │
                      │  │ (Business Logic + Auth)│  │
                      │  └───────────┬────────────┘  │
                      │              │               │
                      │  ┌───────────▼────────────┐  │
                      │  │    AI Module (57)      │  │
                      │  │ (Agent + Tools + LLM)  │  │
                      │  └───────────┬────────────┘  │
                      │              │               │
                      │  ┌───────────▼────────────┐  │
                      │  │  SQLAlchemy Models (29)│  │
                      │  │     (ORM Layer)        │  │
                      │  └───────────┬────────────┘  │
                      └──────────────┼───────────────┘
                                     │
         ┌───────────────┬───────────┼───────────┬───────────────┐
         │               │           │           │               │
   ┌─────▼─────┐  ┌──────▼──────┐ ┌──▼──┐ ┌──────▼──────┐ ┌─────▼─────┐
   │PostgreSQL │  │    Redis    │ │MinIO│ │ Meilisearch │ │    ARQ    │
   │ + pgvector│  │(Cache/PubSub│ │(S3) │ │(Full-text)  │ │ (Workers) │
   │ + pg_trgm │  │ + Locks)   │ │     │ │             │ │           │
   └───────────┘  └─────────────┘ └─────┘ └─────────────┘ └───────────┘
```

## Data Flow Patterns

### 1. Read Request Flow

```
User Action (View Project)
    │
    ▼
React Component
    │
    ├── Check TanStack Query Cache (in-memory)
    │       │
    │       ├── Cache Hit (fresh) -> Return data immediately
    │       │
    │       ├── Cache Hit (stale) -> Return data + refetch in background
    │       │
    │       └── Cache Miss -> Check IndexedDB
    │                           │
    │                           ├── IndexedDB Hit -> Decompress + return + refetch
    │                           │
    │                           └── IndexedDB Miss -> Fetch from API
    │
    ▼
API Request (GET /projects/{id})
    │
    ▼
FastAPI Router
    │
    ├── Validate JWT Token
    │
    ├── Check User Permissions
    │
    └── Query Database (SQLAlchemy)
            │
            ▼
        Return JSON Response
            │
            ▼
TanStack Query
    │
    ├── Store in memory cache
    │
    └── Persist to IndexedDB (compressed)
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
    ├── Optimistic Update (immediate UI feedback)
    │
    └── POST /tasks
            │
            ▼
        FastAPI Router
            │
            ├── Validate Request (Pydantic)
            │
            ├── Check Permissions
            │
            ├── Create in Database
            │
            ├── Update Aggregations
            │
            └── Broadcast via WebSocket
                    │
                    ▼
                WebSocket Manager
                    │
                    ├── Send to project:{id} room
                    │
                    └── Send to target users
                            │
                            ▼
                        All Connected Clients
                            │
                            └── Invalidate Query Cache
                                    │
                                    └── Refetch + Re-render
```

### 3. Real-Time Update Flow

```
WebSocket Connection Established
    │
    ▼
Client Joins Rooms
    │
    ├── project:{project_id}  (Kanban board viewers)
    ├── task:{task_id}        (Task detail viewers)
    ├── document:{doc_id}     (Document editors)
    └── application:{app_id}  (App-level events)
            │
            ▼
Server Event Occurs (e.g., task updated)
    │
    ▼
WebSocket Handler
    │
    ├── Create Message Payload
    │
    ├── Determine Target Rooms
    │
    ├── Publish to Redis (for cross-worker delivery)
    │
    └── Broadcast to Rooms
            │
            ▼
All Clients in Room Receive Event
    │
    ▼
Client-side Handler
    │
    ├── Check Message Deduplication
    │
    ├── Invalidate Related Queries
    │
    └── TanStack Query Refetches
            │
            └── UI Updates Automatically
```

### 4. AI Agent Request Flow

```
User Message (Chat Input)
    │
    ▼
SSE Endpoint (POST /ai/chat)
    │
    ├── Rate limit check (Redis sliding window)
    │
    ├── Acquire agent semaphore (max 50 concurrent)
    │
    └── LangGraph Invocation
            │
            ▼
        intake (reset state, load context)
            │
            ▼
        understand (classify intent + confidence)
            │
            ├── High confidence, simple -> respond (fast-path)
            │
            ├── Low confidence -> clarify (ask user, HITL interrupt)
            │
            └── Needs research -> explore
                    │
                    ▼
                explore <-> explore_tools (ReAct loop)
                    │       │
                    │       └── Tool calls (51 tools: 25 read + 26 write)
                    │           │
                    │           └── Write tools -> interrupt() for HITL confirmation
                    │
                    ▼
                synthesize (merge findings for complex queries)
                    │
                    ▼
                respond (format final answer with citations)
                    │
                    ▼
                SSE Stream -> Frontend (phase indicators + content)
```

## AI Agent Architecture (Blair Copilot)

Blair is an AI copilot built on LangGraph with a 7-node cognitive pipeline, 51 tools, and Human-In-The-Loop (HITL) confirmation for write operations.

### Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Blair Cognitive Pipeline                            │
│                                                                       │
│  START -> intake -> understand -> [clarify] -> explore <-> explore_tools
│                                                    │                  │
│                                              [synthesize]             │
│                                                    │                  │
│                                                 respond -> END        │
│                                                                       │
│  Conditional routing:                                                 │
│    understand -> respond     (fast-path: greetings, simple follow-ups)│
│    understand -> clarify     (low confidence, needs_clarification)    │
│    understand -> explore     (info queries, action requests)          │
│    explore    -> synthesize  (complex multi-source results)           │
│    explore    -> respond     (simple results, safety limit reached)   │
│    synthesize -> respond     (after merging findings)                 │
└──────────────────────────────────────────────────────────────────────┘
```

### Node Responsibilities

| Node | Purpose |
|------|---------|
| `intake` | Reset safety counters, load RBAC context, drain accumulated sources |
| `understand` | Classify intent (info_query, action_request, needs_clarification, multi_step, greeting, follow_up), assess confidence, identify entities and data sources |
| `clarify` | Ask clarification questions when confidence is below threshold; uses LangGraph `interrupt()` for HITL |
| `explore` | ReAct tool-calling loop; selects and invokes tools based on classification |
| `explore_tools` | LangGraph `ToolNode` that executes tool calls; write tools trigger `interrupt()` for HITL confirmation |
| `synthesize` | Merge multi-source research findings into coherent analysis |
| `respond` | Format final answer with source citations, stream to frontend via SSE |

### Tool Organization (51 tools across 16 files)

| File | Tools | Type |
|------|-------|------|
| `identity_tools.py` | get_current_user_info | Read |
| `application_tools.py` | list_applications, get_application_details, list_application_members | Read |
| `project_tools.py` | list_projects, get_project_details, list_project_members, get_project_statuses | Read |
| `task_tools.py` | list_tasks, get_task_details, search_tasks, get_task_comments, get_task_checklists | Read |
| `knowledge_tools.py` | search_knowledge, get_document, list_folders, list_documents | Read |
| `utility_tools.py` | query_database (scoped SQL), list_capabilities | Read |
| `web_tools.py` | web_search (DuckDuckGo), scrape_url (with SSRF protection) | Read |
| `application_write_tools.py` | create_application, update_application, delete_application | Write (HITL) |
| `member_write_tools.py` | invite_member, update_member_role, remove_member | Write (HITL) |
| `project_write_tools.py` | create_project, update_project, delete_project | Write (HITL) |
| `project_member_write_tools.py` | add_project_member, update_project_member_role, remove_project_member | Write (HITL) |
| `write_tools.py` | create_task, update_task, delete_task, add_task_comment | Write (HITL) |
| `checklist_write_tools.py` | add_checklist, add_checklist_item, toggle_checklist_item | Write (HITL) |
| `context.py` | Tool context injection (DB session, user, RBAC scope) | Infrastructure |
| `helpers.py` | Shared tool utilities | Infrastructure |

### Runtime Configuration

All agent constants are managed via the `AgentConfigurations` database table with an in-memory cache + Redis pub/sub invalidation pattern:

```
Admin API (PUT /admin/config)
    │
    ├── Update AgentConfigurations table
    │
    └── Publish to Redis channel "agent_config_changed"
            │
            ▼
        All workers receive invalidation
            │
            ▼
        In-memory cache refreshed on next read
```

Constants are read via getter functions at call time (e.g., `get_max_tool_calls()`) rather than module-level frozen values. This allows admin changes to take effect without worker restarts.

### Safety Limits

| Limit | Default | Description |
|-------|---------|-------------|
| `agent.max_iterations` | 25 | Per-request maximum iterations |
| `agent.max_tool_calls` | 50 | Per-request maximum tool calls |
| `agent.max_llm_calls` | 25 | Per-request maximum LLM calls |
| `agent.max_explore_iterations` | 10 | Maximum explore loop iterations |
| `agent.max_clarify_rounds` | 3 | Maximum clarification rounds per turn |
| `agent.max_concurrent_agents` | 50 | Concurrent agent invocations per worker |
| `agent.context_summarize_threshold` | 0.90 | Token threshold for auto-summarization |
| `agent.context_window` | 128,000 | Context window size in tokens |

### Context Management

When conversation history approaches the context window limit (90% threshold), a two-stage summarization occurs:
1. **Strip completed tool messages**: Remove tool call/result pairs that have been fully processed
2. **Auto-summarize**: LLM generates a concise summary of the conversation so far, preserving the most recent 12 messages

### Checkpointing

LangGraph state is persisted via `AsyncPostgresSaver` backed by a dedicated PostgreSQL connection pool (pool_size=10). This enables:
- Conversation resumption across worker restarts
- HITL interrupt/resume for write tool confirmations
- Time-travel debugging for agent state inspection

### LLM Provider Support

Blair supports multiple LLM providers via a provider registry pattern:

| Provider | Adapter | Use Cases |
|----------|---------|-----------|
| OpenAI | `openai_provider.py` | Chat, embeddings |
| Anthropic | `anthropic_provider.py` | Chat |
| Ollama | `ollama_provider.py` | Self-hosted chat, embeddings |
| Codex | `codex_provider.py` | Chat |

Provider API keys are stored encrypted in the `AiProvider` table. The active provider is resolved per-request from `AiProvider` + `AiModel` configuration.

## State Management Architecture

PM Desktop uses a three-layer state management approach with 28 custom hooks.

### Layer 1: Server State (TanStack Query)

**Purpose**: Manage data that comes from the server (tasks, projects, documents, AI chat, etc.)

**Features**:
- Automatic caching with stale-while-revalidate (global staleTime: 30s, gcTime: 24h)
- Request deduplication
- Background refetching
- Optimistic updates
- Persistent cache via IndexedDB with LZ-String compression
- `refetchOnMount: 'always'` for queries where WebSocket subscriptions are lost on unmount
- `refetchOnWindowFocus: false` for queries with WebSocket real-time sync

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

### Layer 2: Client State (Zustand)

**Purpose**: Manage UI state that doesn't need server persistence

**Stores**:
- `auth-store.ts` - User session, JWT token
- `notes-store.ts` - Active note, open tabs
- `notification-ui-store.ts` - Toast queue, banner state

**Example**:
```typescript
// Zustand store definition
const useAuthStore = create((set) => ({
  user: null,
  token: null,
  setUser: (user) => set({ user }),
  setToken: (token) => set({ token }),
  logout: () => set({ user: null, token: null }),
}));

// Usage in component
const { user, logout } = useAuthStore();
```

### Layer 3: React Context (Cross-cutting Concerns)

**Purpose**: Provide app-wide access to authentication, theme, AI, and UI utilities

**Contexts**:
- `AuthContext` - Login/logout, user fetching
- `NotificationUIContext` - Toast notifications
- `KnowledgeBaseContext` - Knowledge sidebar/tree state
- `AiContext` - AI chat session, copilot configuration
- `CopilotProvider` - CopilotKit runtime integration

**Example**:
```typescript
// Context provider
<AuthProvider>
  <CopilotProvider>
    <App />
  </CopilotProvider>
</AuthProvider>

// Usage in component
const { user, login, logout } = useAuth();
```

### Custom Hooks (28 hooks)

| Hook | Purpose |
|------|---------|
| `useAuth` | Authentication state and actions |
| `useProjects` | Project CRUD + membership |
| `useTasks` | Task CRUD + status management |
| `useWebSocket` | WebSocket connection and messaging |
| `useWebSocketCache` | Cache invalidation from WebSocket events |
| `useDocuments` | Document CRUD operations |
| `useDocumentFolders` | Folder tree operations |
| `useDocumentLock` | Document locking/unlocking |
| `useDocumentSearch` | Full-text search |
| `useDocumentTags` | Tag management |
| `useDocumentImport` | File import pipeline state |
| `useFolderFiles` | Files attached to folders |
| `useKnowledgePermissions` | Document/folder permission checks |
| `useChatSessions` | AI chat session management |
| `useAiConfig` | AI provider/model configuration |
| `useOAuthConnect` | OAuth connection for AI providers |
| `useChecklists` | Checklist CRUD |
| `useComments` | Comment CRUD + threading |
| `useAttachments` | File attachment management |
| `usePresence` | User presence indicators |
| `useTaskViewers` | Real-time task viewer tracking |
| `useDashboardWebSocket` | Dashboard-level WebSocket events |
| `useDragAndDrop` | @dnd-kit integration for Kanban |
| `useNotifications` | Notification feed |
| `useInvitations` | Application invitation management |
| `useMembers` | Member listing and management |
| `useDraft` | Draft auto-save |
| `useEditMode` | Inline editing state |

## Component Architecture

### Component Hierarchy

```
App.tsx
├── Providers (Theme, Auth, Query, Notifications, CopilotKit)
│   └── Router (state-based, NOT react-router)
│       ├── LoginPage
│       ├── RegisterPage
│       ├── ForgotPasswordPage
│       ├── ResetPasswordPage
│       ├── VerifyEmailPage
│       └── DashboardPage
│           ├── Sidebar
│           │   ├── ApplicationList
│           │   └── Navigation
│           ├── Header
│           │   ├── SearchBar
│           │   ├── NotificationBell
│           │   └── UserMenu
│           ├── AISidebar (Blair Copilot)
│           │   ├── ChatSessionList
│           │   ├── ChatInput
│           │   ├── AIMessageRenderer
│           │   ├── ToolConfirmation (HITL)
│           │   ├── ToolExecutionCard
│           │   ├── ClarificationCard
│           │   ├── SourceCitation
│           │   ├── InterruptHandler
│           │   ├── ContextSummaryDivider
│           │   └── TokenUsageBar
│           └── MainContent
│               ├── ApplicationPage
│               │   ├── ProjectList
│               │   └── MemberList
│               ├── ProjectPage
│               │   ├── KanbanBoard
│               │   │   ├── StatusColumn
│               │   │   └── TaskCard
│               │   └── PresenceIndicators
│               ├── TaskDetailModal
│               │   ├── TaskHeader
│               │   ├── TaskDescription
│               │   ├── CommentThread
│               │   ├── ChecklistPanel
│               │   └── AttachmentList
│               └── NotesPage
│                   ├── KnowledgeSidebar
│                   │   ├── KnowledgeTree
│                   │   ├── SearchBar
│                   │   ├── TagFilterList
│                   │   └── FileUploadZone
│                   ├── KnowledgeTabBar
│                   ├── DocumentEditor
│                   │   ├── DocumentHeader
│                   │   ├── EditorToolbar
│                   │   ├── TipTap (rich text editing)
│                   │   ├── CanvasEditor (draw.io diagrams)
│                   │   └── DocumentStatusBadge
│                   ├── FileViewerPanel
│                   ├── SearchResultsPanel
│                   └── AISettingsPanel
│                       ├── ProvidersModelsTab
│                       ├── PersonalityTab
│                       └── IndexingTab
```

### Component Categories

| Category | Location | Purpose |
|----------|----------|---------|
| UI Primitives | `components/ui/` | Radix UI wrappers, shadcn/ui components |
| Feature Components | `components/{feature}/` | Business logic components |
| Layout Components | `components/layout/` | Header, sidebar, panels |
| Page Components | `pages/` | Route-level components |
| AI Components | `components/ai/` | Blair copilot UI (chat, tools, citations) |
| Knowledge Components | `components/knowledge/` | Document editor, tree, search |
| Kanban Components | `components/kanban/` | Drag-and-drop board |

## Backend Architecture

### Layer Structure

```
Request
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                     API Router Layer (27 routers)            │
│  (Request validation, routing)                               │
│  routers/tasks.py, routers/auth.py, routers/ai_chat.py ...  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer (19 services)              │
│  (Business logic, authorization)                             │
│  services/permission_service.py, services/search_service.py  │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼                               ▼
┌────────────────────────┐  ┌─────────────────────────────────┐
│    AI Module (57 files) │  │        Model Layer (29 models)   │
│  app/ai/                │  │  (Database access via ORM)       │
│  ├── agent/             │  │  models/task.py, models/user.py  │
│  │   ├── nodes/ (6)     │  └──────────────┬──────────────────┘
│  │   ├── tools/ (15)    │                  │
│  │   ├── graph.py       │                  ▼
│  │   ├── state.py       │  ┌─────────────────────────────────┐
│  │   ├── routing.py     │  │        Database Layer            │
│  │   └── constants.py   │  │  (PostgreSQL via SQLAlchemy)     │
│  ├── providers (4)      │  │  database.py, alembic migrations │
│  ├── embeddings (3)     │  └─────────────────────────────────┘
│  ├── search (3)         │
│  ├── file processing (5)│
│  └── config/export (6)  │
└─────────────────────────┘
```

### AI Module Directory (`app/ai/`)

| Subdirectory / File | Count | Purpose |
|---------------------|-------|---------|
| `agent/nodes/` | 6 | Pipeline node implementations (intake, understand, clarify, explore, synthesize, respond) |
| `agent/tools/` | 15 | Tool definitions (read + write tools, context, helpers) |
| `agent/` (core) | 8 | Graph definition, state, routing, constants, prompts, RBAC context, source references |
| Provider adapters | 4 | openai_provider, anthropic_provider, ollama_provider, codex_provider |
| Embeddings | 3 | embedding_service, embedding_normalizer, chunking_service |
| Search/retrieval | 3 | retrieval_service, sql_executor, sql_validator |
| File processing | 5 | file_extraction_service, docling_service, spreadsheet_extractor, visio_extractor, image_understanding_service |
| Config/export | 6 | config_service, encryption, rate_limiter, pdf_export, excel_export, schema_context |
| Other | 5 | agent_tools (registration), provider_interface, provider_registry, oauth_service, telemetry, exceptions |

### Request Processing

1. **Request Received**: FastAPI receives HTTP request
2. **Validation**: Pydantic schema validates request body/params
3. **Authentication**: JWT token verified via `get_current_user` dependency
4. **Rate Limiting**: Redis sliding window counter for AI endpoints (auth, chat, SQL query)
5. **Authorization**: Permission service checks user access (RBAC hierarchy: application > project)
6. **Business Logic**: Service layer processes request
7. **Database**: SQLAlchemy executes queries
8. **Response**: Pydantic schema serializes response
9. **WebSocket**: Real-time broadcast to relevant clients via Redis pub/sub

### Background Jobs (ARQ)

Background processing is handled by ARQ workers backed by Redis:

| Job | Trigger | Purpose |
|-----|---------|---------|
| `embed_document_job` | Document save/update | Generate vector embeddings for semantic search |
| `check_search_index_consistency` | Cron | Verify Meilisearch index matches database |
| `recalculate_aggregation_from_tasks` | Cron | Recompute project status aggregation tables |

Embedding jobs use ARQ `_job_id` for deduplication and `_defer_by=120s` to batch rapid edits.

## Database Architecture

### Entity Relationships

```
User
 │
 ├── owns --> Application
 │               │
 │               ├── contains --> Project
 │               │                   │
 │               │                   ├── contains --> Task
 │               │                   │                   │
 │               │                   │                   ├── has --> Comments
 │               │                   │                   ├── has --> Checklists --> ChecklistItems
 │               │                   │                   └── has --> Attachments
 │               │                   │
 │               │                   ├── has --> TaskStatuses
 │               │                   ├── has --> ProjectMembers
 │               │                   └── has --> ProjectAssignments
 │               │
 │               ├── has --> DocumentFolders
 │               │               │
 │               │               ├── contains --> Documents
 │               │               │                   │
 │               │               │                   ├── has --> DocumentSnapshots
 │               │               │                   ├── has --> DocumentChunks (embeddings)
 │               │               │                   └── has --> DocumentTagAssignments
 │               │               │
 │               │               └── contains --> FolderFiles
 │               │
 │               ├── has --> ApplicationMembers
 │               └── has --> Invitations
 │
 ├── has --> ChatSessions
 │               │
 │               └── contains --> ChatMessages
 │
 ├── assigned to --> Task
 ├── mentioned in --> Comment
 └── receives --> Notification

AI Configuration (global)
 ├── AiProvider (encrypted API keys)
 │       └── has --> AiModel (model_id, capabilities)
 ├── AiSystemPrompt (versioned prompts)
 ├── AgentConfiguration (runtime constants, 81+ rows)
 └── ImportJob (document import tracking)

Tagging
 └── DocumentTag --> DocumentTagAssignment --> Document
```

### Models (29 model files)

| Model | Table | Purpose |
|-------|-------|---------|
| User | users | Authentication and identity |
| Application | applications | Top-level workspace container |
| ApplicationMember | application_members | App membership + roles |
| Project | projects | Project within an application |
| ProjectMember | project_members | Project membership + roles |
| ProjectAssignment | project_assignments | User-project assignments |
| ProjectTaskStatusAgg | project_task_status_agg | Pre-computed status counts |
| Task | tasks | Work items with Kanban ordering |
| TaskStatus | task_statuses | Custom status definitions |
| Comment | comments | Threaded comments on tasks |
| Checklist | checklists | Task checklists |
| ChecklistItem | checklist_items | Individual checklist items |
| Attachment | attachments | File attachment metadata |
| Notification | notifications | User notifications |
| Mention | mentions | @mention references |
| Invitation | invitations | Application invitations |
| Document | documents | Knowledge base documents |
| DocumentFolder | document_folders | Hierarchical folder structure |
| DocumentSnapshot | document_snapshots | Document version snapshots |
| DocumentChunk | document_chunks | Vector embedding chunks (pgvector) |
| DocumentTag | document_tags | Tag definitions |
| FolderFile | folder_files | Files uploaded to folders |
| ImportJob | import_jobs | Document import pipeline tracking |
| ChatSession | chat_sessions | AI chat conversation sessions |
| ChatMessage | chat_messages | Individual chat messages |
| AiProvider | ai_providers | LLM provider configuration |
| AiModel | ai_models | Model definitions per provider |
| AiSystemPrompt | ai_system_prompts | Versioned system prompts |
| AgentConfiguration | agent_configurations | Runtime agent constants (81+ rows) |

### PostgreSQL Extensions

| Extension | Purpose |
|-----------|---------|
| `pgvector` | Vector similarity search for document embeddings (HNSW indexes) |
| `pg_trgm` | Trigram-based fuzzy matching for typo-tolerant search (GIN indexes) |

### Key Design Decisions

1. **Denormalization for Performance**
   - `Task.checklist_total`, `Task.checklist_done` - Avoid counting on every read
   - `ProjectTaskStatusAgg` - Pre-computed status counts for project status derivation

2. **Lexorank for Ordering**
   - `Task.task_rank` - String-based ordering for efficient reordering in Kanban

3. **Soft Relationships**
   - `Task.parent_id` - Self-referential for subtasks
   - `Comment.task_id` + `Comment.parent_id` - Threaded comments

4. **Scoped Views for AI SQL Access**
   - Personal, application, and project security boundary views
   - AI-generated SQL executes against scoped views, not raw tables
   - `SET TRANSACTION READ ONLY` + `statement_timeout=5s` + sqlglot validation

5. **Embedding Storage**
   - `DocumentChunk` stores chunked text with vector embeddings
   - `embedding_updated_at` column on Documents tracks freshness
   - Chunks include heading context and positional metadata for retrieval

## Search Architecture

PM Desktop implements a three-layer hybrid search system for knowledge base retrieval.

### Search Layers

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hybrid Retrieval Service                    │
│                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│  │   Meilisearch   │  │    pgvector     │  │   pg_trgm    │  │
│  │  (Full-text)    │  │  (Semantic)     │  │  (Fuzzy)     │  │
│  │                 │  │                 │  │              │  │
│  │ Keyword matching│  │ Cosine similarity│ │ Trigram match│  │
│  │ Ranked results  │  │ on embeddings   │  │ on titles    │  │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘  │
│           │                    │                   │           │
│           └────────────────────┼───────────────────┘           │
│                                │                               │
│                    Reciprocal Rank Fusion (RRF)                │
│                                │                               │
│                    Deduplicate by document_id                  │
│                                │                               │
│                    Return merged results                       │
└────────────────────────────────┼──────────────────────────────┘
                                 │
                                 ▼
                          Ranked Results
```

### Search Layer Details

| Layer | Engine | Strengths | Index Type |
|-------|--------|-----------|------------|
| Full-text | Meilisearch | Keyword relevance, fast indexing | Meilisearch internal |
| Semantic | pgvector | Synonym understanding, conceptual similarity | HNSW (approximate nearest neighbor) |
| Fuzzy | pg_trgm | Typo tolerance, partial matches | GIN trigram index |

### Retrieval Flow

1. User query is sent to all three search layers in parallel
2. Each layer returns ranked results filtered by the user's RBAC scope
3. Results are merged using Reciprocal Rank Fusion (RRF) with configurable weights
4. Duplicates are removed by `document_id` (a document may appear in multiple layers)
5. Final ranked list is returned with source attribution (semantic, keyword, fuzzy, or combined)

### Embedding Pipeline

```
Document Save/Update
    │
    ▼
ARQ Job Enqueue (embed_document_job, deferred 120s)
    │
    ▼
Chunking Service
    │
    ├── Split by headings and semantic boundaries
    ├── Respect table boundaries and canvas containers
    ├── Handle slide boundaries and oversized elements
    └── Attach heading context to each chunk
            │
            ▼
Embedding Service
    │
    ├── Generate vectors via configured provider (OpenAI, Ollama)
    ├── Normalize embeddings for consistent cosine similarity
    └── Store in document_chunks table (pgvector)
            │
            ▼
Update document.embedding_updated_at
```

## File Processing Pipeline

PM Desktop supports importing and exporting documents in multiple formats.

### Import Pipeline

```
File Upload (PDF, DOCX, PPTX, XLSX, VSDX)
    │
    ▼
File Extraction Service
    │
    ├── PDF/DOCX/PPTX --> docling (document conversion)
    ├── XLSX           --> python-calamine (spreadsheet extraction)
    └── VSDX           --> vsdx (Visio diagram parsing)
            │
            ▼
Content Converter (to TipTap JSON)
    │
    ▼
Document Creation + Meilisearch Indexing
    │
    ▼
Background Embedding Job (ARQ)
```

### Export Pipeline

| Format | Library | Endpoint |
|--------|---------|----------|
| PDF | fpdf2 | `export_document_pdf` |
| Excel | openpyxl | `excel_export` |

## Real-Time Communication

### WebSocket Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Client 1   │    │   Client 2   │    │   Client 3   │
│  (Worker A)  │    │  (Worker A)  │    │  (Worker B)  │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       └─────────┬─────────┘                   │
                 │                             │
       ┌─────────▼─────────┐         ┌─────────▼─────────┐
       │   Worker A        │         │   Worker B        │
       │   ConnectionMgr   │         │   ConnectionMgr   │
       └─────────┬─────────┘         └─────────┬─────────┘
                 │                             │
                 └──────────┬──────────────────┘
                            │
                   ┌────────▼────────┐
                   │  Redis Pub/Sub  │
                   │  (Cross-worker  │
                   │   relay)        │
                   └─────────────────┘
```

### WebSocket Message Types

| Category | Message Types |
|----------|--------------|
| Connection | CONNECTED, DISCONNECTED, ERROR, PING, PONG |
| Room | JOIN_ROOM, LEAVE_ROOM, ROOM_JOINED, ROOM_LEFT |
| Task | TASK_CREATED, TASK_UPDATED, TASK_DELETED, TASK_STATUS_CHANGED, TASK_MOVED |
| Comment | COMMENT_ADDED, COMMENT_UPDATED, COMMENT_DELETED |
| Checklist | CHECKLIST_CREATED, CHECKLIST_UPDATED, CHECKLIST_DELETED, CHECKLISTS_REORDERED, CHECKLIST_ITEM_TOGGLED, CHECKLIST_ITEM_ADDED, CHECKLIST_ITEM_UPDATED, CHECKLIST_ITEM_DELETED, CHECKLIST_ITEMS_REORDERED |
| Attachment | ATTACHMENT_UPLOADED, ATTACHMENT_DELETED |
| Presence | PRESENCE_UPDATE, TASK_VIEWERS, USER_PRESENCE, USER_TYPING, USER_VIEWING |
| Project | PROJECT_CREATED, PROJECT_UPDATED, PROJECT_DELETED, PROJECT_STATUS_CHANGED |
| Application | APPLICATION_CREATED, APPLICATION_UPDATED, APPLICATION_DELETED |
| Member | INVITATION_RECEIVED, INVITATION_RESPONSE, MEMBER_ADDED, MEMBER_REMOVED, ROLE_UPDATED |
| Project Member | PROJECT_MEMBER_ADDED, PROJECT_MEMBER_REMOVED, PROJECT_ROLE_CHANGED |
| Document | DOCUMENT_CREATED, DOCUMENT_UPDATED, DOCUMENT_DELETED, DOCUMENT_LOCKED, DOCUMENT_UNLOCKED, DOCUMENT_FORCE_TAKEN, DOCUMENT_EMBEDDING_SYNCED |
| Folder | FOLDER_CREATED, FOLDER_UPDATED, FOLDER_DELETED |
| File | FILE_UPLOADED, FILE_UPDATED, FILE_DELETED, FILE_EXTRACTION_COMPLETED, FILE_EXTRACTION_FAILED |
| AI | EMBEDDING_UPDATED, ENTITIES_EXTRACTED, IMPORT_COMPLETED, IMPORT_FAILED, REINDEX_PROGRESS |
| Infrastructure | REDIS_STATUS_CHANGED |
| Notification | NOTIFICATION, NOTIFICATION_READ |

### Document Locking

Document locks are managed via Redis with WebSocket push notifications:

- `DOCUMENT_LOCKED` - Broadcast when a user acquires a document lock
- `DOCUMENT_UNLOCKED` - Broadcast when a user releases a lock
- `DOCUMENT_FORCE_TAKEN` - Broadcast when an editor force-takes a locked document

Batch lock status is available via the active-locks endpoint to avoid N+1 queries.

## Caching Strategy

### Multi-Level Cache

```
┌─────────────────────────────────────────────────────┐
│     Level 1: In-Memory (React)                       │
│  TanStack Query cache (30s stale, 24h garbage collect│
│  Fastest access, limited size                        │
└──────────────────────┬──────────────────────────────┘
                       │ Cache Miss
                       ▼
┌─────────────────────────────────────────────────────┐
│     Level 2: IndexedDB (Browser)                     │
│  Per-query persister with LZ-String compression      │
│  80% storage reduction, LRU eviction                 │
│  Progressive hydration on app startup                │
└──────────────────────┬──────────────────────────────┘
                       │ Cache Miss
                       ▼
┌─────────────────────────────────────────────────────┐
│     Level 3: Redis (Server)                          │
│  User objects, session data, document locks          │
│  Config cache, rate limit counters                   │
│  Shared across instances via pub/sub                 │
└──────────────────────┬──────────────────────────────┘
                       │ Cache Miss
                       ▼
┌─────────────────────────────────────────────────────┐
│     Level 4: PostgreSQL                              │
│  Source of truth                                     │
│  Connection pooling (10 base + 20 overflow per pool) │
└─────────────────────────────────────────────────────┘
```

### Cache Invalidation

Caches are invalidated via:
1. **Time-based**: Stale time expiration (30 seconds default)
2. **Event-based**: WebSocket events trigger cache invalidation (use-websocket-cache.ts)
3. **Manual**: User actions (create, update, delete) invalidate related queries
4. **Auth-based**: Logout clears all caches
5. **Redis Pub/Sub**: Config service invalidation across workers (AgentConfigurations)

### Electron-Specific Cache Behavior

- Electron focus manager fires window focus events on app switch (triggers refetch for queries without `refetchOnWindowFocus: false`)
- IndexedDB persistence hydrates stale data on startup, causing initial revalidation
- React.StrictMode (enabled in dev) causes double effects -- WebSocket connections deduplicated

## Desktop Distribution & Auto-Updates

PM Desktop uses `electron-updater` with GitHub Releases for OTA updates.

### Update Flow

```
App Launch → auto-updater checks GitHub latest.yml (5s delay)
  → If newer version: sends 'available' status to renderer
  → User triggers download → sends progress events
  → Download complete → installs on next quit (or immediately)
```

### Key Files

| File | Purpose |
|------|---------|
| `src/main/auto-updater.ts` | Update check, download, install logic |
| `src/preload/index.ts` | Bridges `checkForUpdates`, `downloadUpdate`, `installUpdate`, `onUpdateStatus` to renderer |
| `package.json` `"build"` | electron-builder config with GitHub publish target |

### Publishing

```bash
npm version patch && npx electron-vite build && npx electron-builder --publish always
```

Requires `GH_TOKEN` environment variable. See [Desktop Releases & OTA Updates](./desktop-releases.md) for full details.

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
│                                            │ Create JWT pair      │
│     ┌─────────┐  {access, refresh}  ┌──────▼──────┐              │
│     │ Client  │ ◄────────────────── │   Server    │              │
│     │         │                     │             │              │
│     └────┬────┘                     └─────────────┘              │
│          │                                                        │
│  3. Token Storage                                                 │
│          │ Store in:                                              │
│          ├── Zustand (memory)                                     │
│          └── localStorage (persistence)                           │
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

### Authorization Levels (RBAC Hierarchy)

| Level | Check | Implementation |
|-------|-------|----------------|
| Route | JWT valid | `get_current_user` dependency |
| Application | User is member | `check_app_member` service |
| Project | User is member | `check_project_member` service |
| Task | User has project access | Via project membership |
| Role | User role sufficient | Role hierarchy: owner > editor > viewer |
| AI Tools | RBAC scope | Agent tools filter by `accessible_app_ids` + `accessible_project_ids` |

RBAC hierarchy: application membership grants implicit access to all projects within that application. Project membership is a narrower scope.

### AI-Specific Security

| Threat | Mitigation |
|--------|------------|
| SSRF via Ollama config | Block metadata IP ranges (169.254.x.x, 10.x.x.x, etc.) |
| SSRF via web tools | URL validation + IP blocking for `scrape_url` |
| SQL injection via AI | sqlglot AST validation + `SET TRANSACTION READ ONLY` + 5s statement timeout + scoped views |
| Excessive AI resource use | Rate limiting (Redis sliding window), agent semaphore (50 concurrent), safety limits (50 tool calls, 25 iterations) |
| API key exposure | AES encryption for provider API keys in database |
| Unauthorized AI writes | HITL `interrupt()` for all 26 write tools; RBAC validation before execution |
| Token-based session auth | Chat sessions bound to user; session validation on each message |

### Rate Limiting

Redis-based sliding window counters with Lua script atomicity:

| Endpoint Category | Implementation |
|-------------------|----------------|
| Authentication | Per-IP rate limit on login attempts |
| AI Chat | Per-user rate limit on chat messages |
| SQL Query | Per-user rate limit on AI SQL execution |

Fallback: in-memory counter per worker when Redis is unavailable (with CRITICAL log).

## Performance Optimizations

### Frontend

| Optimization | Technique | Impact |
|--------------|-----------|--------|
| Code Splitting | Dynamic imports | Faster initial load |
| Compression | LZ-String for IndexedDB cache | 80% storage reduction |
| Deduplication | Request & message dedup | Reduced network/renders |
| Virtual Scrolling | react-virtuoso | Handle large lists |
| Memoization | React.memo, useMemo | Prevent re-renders |
| SWR | Stale-while-revalidate | Instant perceived loads |
| SSE Streaming | AI responses stream in real-time | Progressive rendering |
| Selective Refetch | `refetchOnWindowFocus: false` for WS-synced queries | Avoid unnecessary API calls |

### Backend

| Optimization | Technique | Impact |
|--------------|-----------|--------|
| Connection Pool | 10 base + 20 overflow (per pool) | Handle concurrent requests |
| Checkpointer Pool | Dedicated pool_size=10 for LangGraph | Isolated from main pool |
| Eager Loading | selectinload | Prevent N+1 queries |
| Composite Indexes | Dashboard queries, search | Faster query execution |
| GiST Indexes | Full-text search columns | Fast text search |
| HNSW Indexes | pgvector embedding columns | Approximate nearest neighbor |
| GIN Indexes | pg_trgm trigram columns | Fast fuzzy matching |
| Denormalization | Aggregation tables | Avoid expensive counts |
| Room Broadcast | O(1) to room members | Scale to 5000+ users |
| Rate Limiting | Redis sliding window per user | Prevent overload |
| Agent Semaphore | 50 concurrent agents per worker | Bounded resource usage |
| Embedding Dedup | ARQ `_job_id` + `_defer_by=120s` | Batch rapid edits |
| Context Summarization | Two-stage at 90% token threshold | Unbounded conversations |

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
   │ + ARQ   │          │ + ARQ   │          │ + ARQ   │
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
    ┌──────────┬─────────────┼─────────────┬──────────┐
    │          │             │             │          │
┌───▼────┐ ┌───▼───┐   ┌────▼────┐  ┌─────▼─────┐ ┌──▼──┐
│Postgres│ │ Redis │   │  MinIO  │  │Meilisearch│ │ ARQ │
│+pgvec  │ │(Shared│   │ (Shared)│  │ (Shared)  │ │Workers│
│+pg_trgm│ │ PubSub│   │         │  │           │ │     │
└────────┘ └───────┘   └─────────┘  └───────────┘ └─────┘
```

### Scale Considerations

1. **WebSocket Affinity**: Use sticky sessions for WebSocket connections
2. **Redis Pub/Sub**: Cross-server event distribution for WebSocket, config invalidation, and document locks
3. **Database Replica**: Read replicas for query distribution
4. **File Storage**: MinIO clusters for high availability
5. **Search Scaling**: Meilisearch can be clustered independently
6. **Agent Concurrency**: 50 concurrent agents per worker (bounded by semaphore)
7. **Connection Budget**: Each worker uses approximately 10+20 (main pool) + 10 (LangGraph checkpointer) PostgreSQL connections

## File Storage (MinIO)

MinIO provides S3-compatible object storage for all file uploads. Binary content is stored in MinIO; only metadata lives in PostgreSQL.

### Storage Layout

```
MinIO
├── pm-images/                          # Image files (PNG, JPEG, GIF, WebP)
│   ├── task/{task_id}/
│   │   └── {uuid8}_{filename}          # Task image attachments
│   ├── comment/{comment_id}/
│   │   └── {uuid8}_{filename}          # Comment image attachments
│   └── document/{document_id}/
│       ├── {uuid8}_{filename}          # Editor inline images
│       └── {uuid8}_diagram.png         # Draw.io diagram previews
│
└── pm-attachments/                     # Non-image files (PDF, DOCX, ZIP, etc.)
    ├── task/{task_id}/
    │   └── {uuid8}_{filename}          # Task file attachments
    ├── comment/{comment_id}/
    │   └── {uuid8}_{filename}          # Comment file attachments
    └── document/{document_id}/
        └── {uuid8}_{filename}          # Document file attachments
```

### Access Pattern

```
Upload Flow:
  Client --POST /api/files/upload--> FastAPI --put_object--> MinIO
                                        │
                                        └--> Attachment record --> PostgreSQL

Download Flow:
  Client --GET /api/files/{id}/download-url--> FastAPI --presigned_get--> MinIO
    │                                             │
    │<---- presigned URL (1hr expiry) ────────────┘
    │
    └──── GET presigned URL ──────────────────────────────────────────> MinIO
```

### Key Constraints

| Constraint | Value |
|-----------|-------|
| Max file size | 100 MB |
| Max image size | 10 MB |
| Allowed image types | PNG, JPEG, GIF, WebP |
| Download URL expiry | 1 hour |
| Upload URL expiry | 2 hours |
| Batch URL limit | 50 IDs per request |
| Orphan cleanup grace | 5 minutes |

For full implementation details, see the [Backend Guide -- MinIO File Storage](./backend.md#minio-file-storage) section.
