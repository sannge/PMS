# PM Desktop Developer Documentation

Welcome to PM Desktop, a project management application with Jira-like features, OneNote-style knowledge base, and an AI copilot agent (Blair).

## Quick Links

### User Documentation

| Document | Description |
|----------|-------------|
| [User Manual](./user-manual/index.md) | Complete end-user guide for PM Desktop |

### Developer Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](./getting-started.md) | Setup guide, requirements, and first run |
| [Architecture Overview](./architecture.md) | System design, component interactions, data flow |
| [Backend Guide](./backend.md) | FastAPI, SQLAlchemy, services, APIs, and migrations |
| [Frontend Guide](./frontend.md) | React, Electron, state management, and components |
| [Desktop Releases & OTA Updates](./desktop-releases.md) | Building, publishing, and auto-updating the Electron app |

## Technology Stack

### Backend
- **Python 3.12** - Core runtime
- **FastAPI** - Async web framework with automatic OpenAPI docs
- **SQLAlchemy 2.0** - ORM with async support
- **Pydantic** - Request/response validation and serialization
- **Alembic** - Database migrations (20+ migration files)
- **PostgreSQL** - Primary database with **pgvector** (semantic search) and **pg_trgm** (typo-tolerant search) extensions
- **Redis 7+** - Caching, WebSocket pub/sub, and config invalidation
- **MinIO** - S3-compatible file storage for attachments and imports
- **Meilisearch** - Full-text search engine
- **ARQ** - Background job processing (embeddings, document import)

### AI
- **LangGraph** - Agent orchestration framework (7-node cognitive pipeline)
- **OpenAI / Anthropic / Ollama** - Multi-provider LLM support
- **pgvector** - Vector embeddings for semantic search
- **fpdf2** - PDF export from agent
- **docling, python-calamine, vsdx** - Document processing (PDF, DOCX, PPTX, XLSX, VSDX)

### Frontend
- **Electron 30** - Desktop application framework (with OTA auto-updates via `electron-updater`)
- **React 18** - UI library with concurrent features
- **TypeScript 5.5** - Type-safe JavaScript
- **TanStack Query** - Server state management with caching and IndexedDB persistence
- **Zustand** - Client state management
- **Radix UI + shadcn/ui** - Component library
- **TailwindCSS** - Utility-first styling
- **TipTap** - Rich text editor with collaborative editing
- **@dnd-kit** - Drag-and-drop for Kanban boards

### Real-Time
- **WebSocket** - Bidirectional communication (presence, notifications, document sync, cache invalidation)

## Project Structure

```
pm-project/
├── fastapi-backend/              # Python backend
│   ├── app/
│   │   ├── main.py               # FastAPI application entry
│   │   ├── config.py             # Environment configuration
│   │   ├── database.py           # SQLAlchemy setup
│   │   ├── models/               # 32 SQLAlchemy models
│   │   ├── schemas/              # 24 Pydantic schema files
│   │   ├── routers/              # 28 FastAPI endpoint files
│   │   ├── services/             # 20 service files (business logic)
│   │   ├── ai/                   # AI module (29 files)
│   │   │   ├── agent/            # LangGraph agent (10 files)
│   │   │   │   ├── nodes/        # 6 pipeline nodes
│   │   │   │   └── tools/        # 16 tool files (51 tools total)
│   │   │   └── ...               # Providers, embeddings, export
│   │   ├── websocket/            # WebSocket handlers
│   │   ├── dependencies/         # Dependency injection and Redis gate
│   │   └── utils/                # Shared utilities
│   ├── alembic/                  # 20+ database migrations
│   ├── tests/                    # pytest test suite
│   └── pyproject.toml            # Python dependencies and tool config
│
├── electron-app/                 # Electron + React frontend
│   ├── src/
│   │   ├── main/                 # Electron main process
│   │   ├── preload/              # Secure bridge scripts
│   │   └── renderer/             # React application
│   │       ├── components/       # 133+ React components (20 categories)
│   │       ├── pages/            # 11 pages
│   │       ├── stores/           # Zustand stores
│   │       ├── hooks/            # 30 custom hooks
│   │       ├── contexts/         # Auth, Knowledge, Notification contexts
│   │       └── lib/              # Query client, API, WebSocket, utils
│   ├── tests/                    # Frontend tests
│   └── package.json              # Node dependencies
│
├── specs/                        # Feature specifications
│
└── docs/                         # This documentation
```

## Features

### Core Project Management
- **Application management** - Top-level containers for organizing projects
- **Project boards** - Custom workflows with configurable statuses
- **Task management** - Kanban drag-and-drop with types (story, bug, epic), priorities, and assignments
- **Dashboard** - Charts for task distribution, completion trends, and project health
- **Threaded comments** - Rich text comments with @-mentions
- **Checklists** - Task checklists with completion tracking and progress indicators
- **File attachments** - Upload and preview via MinIO (images, documents)
- **Notifications** - Real-time notifications for mentions, assignments, and updates
- **Presence indicators** - See who is viewing tasks in real-time

### Knowledge Base
- **Rich-text documents** - TipTap editor with formatting, tables, code blocks
- **Hierarchical folders** - Scoped to personal, application, or project level
- **Real-time collaborative editing** - Document locking with WebSocket-based sync
- **Document snapshots** - Version history with restore capability
- **Document tags and filtering** - Organize and find documents quickly
- **Full-text search** - Meilisearch combined with semantic (pgvector) and typo-tolerant (pg_trgm) search
- **Document locking** - Lock/unlock with presence indicators and force-take support
- **Canvas/Draw.io diagrams** - Embedded diagram editing within documents
- **Batch document import** - PDF, DOCX, PPTX, XLSX, VSDX via docling and other processors

### AI Agent (Blair Copilot)
- **7-node cognitive pipeline** - Intake, understand, clarify, explore, synthesize, respond, and HITL nodes
- **51 tools** - 25 read tools and 26 write tools with human-in-the-loop confirmation for writes
- **Intent classification** - Automatic routing and multi-step reasoning
- **SQL generation** - Real-time queries via scoped PostgreSQL views with sqlglot validation
- **Document embeddings** - Hybrid search combining semantic (pgvector), BM25 (Meilisearch), and trigram (pg_trgm)
- **Context summarization** - Automatic summarization at 90% token threshold to maintain long conversations
- **Web search and scraping** - DuckDuckGo search and URL scraping with SSRF protection
- **PDF and Excel export** - Generate reports and exports from agent conversations
- **Runtime configuration** - 81 configurable settings via admin API with Redis pub/sub invalidation
- **Multi-provider LLM** - OpenAI, Anthropic, and Ollama with per-model configuration
- **Chat sessions** - Persistent history with time-travel and replay

### User and Permissions
- **JWT authentication** - Access and refresh tokens
- **Email verification** - Account verification and password reset flows
- **Role-based access control** - Owner, Manager, Member, Viewer at application and project levels
- **User invitations** - Invite users with role assignment

### Admin and Configuration
- **AI provider management** - Configure API keys, models, and endpoints per provider
- **Runtime agent configuration** - 81 settings across cost controls, safety limits, and behavioral tuning
- **Document import monitoring** - Track batch import jobs and status

## Scale Targets

PM Desktop is designed to support **5,000 concurrent users** per server instance with:
- Sub-100ms UI interactions
- Sub-200ms API read operations
- Real-time updates across all connected clients
- Offline-first caching with IndexedDB persistence and sync on reconnect

## Getting Started

See [Getting Started](./getting-started.md) for:
- System requirements
- Development environment setup
- Running the application locally
- Common development commands
