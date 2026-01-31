# PM Desktop Developer Documentation

Welcome to PM Desktop, a project management application with Jira-like features and OneNote-style note-taking.

## Quick Links

### User Documentation

| Document | Description |
|----------|-------------|
| [User Manual](./user-manual/index.md) | Complete end-user guide for PM Desktop |

### Developer Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](./getting-started.md) | Setup guide, requirements, and first run |
| [Architecture Overview](./architecture.md) | System design and component interactions |
| [Backend Guide](./backend.md) | FastAPI, SQLAlchemy, services, and APIs |
| [Frontend Guide](./frontend.md) | React, Electron, state management, and components |
| [Real-Time Communication](./websocket.md) | WebSocket implementation and patterns |
| [Database Guide](./database.md) | Models, migrations, and query patterns |
| [Deployment Guide](./deployment.md) | Production deployment and configuration |

## Technology Stack

### Backend
- **Python 3.12** - Core runtime
- **FastAPI** - Async web framework with automatic OpenAPI docs
- **SQLAlchemy 2.0** - ORM with async support
- **Alembic** - Database migrations
- **Microsoft SQL Server** - Primary database (via pyodbc)
- **Redis 7+** - Caching and pub/sub
- **MinIO** - S3-compatible file storage
- **Meilisearch** - Full-text search engine

### Frontend
- **Electron 30** - Desktop application framework
- **React 18** - UI library with concurrent features
- **TypeScript 5.5** - Type-safe JavaScript
- **TanStack Query** - Server state management with caching
- **Zustand** - Client state management
- **Radix UI + shadcn/ui** - Component library
- **TailwindCSS** - Utility-first styling
- **TipTap** - Rich text editor with collaborative editing
- **@dnd-kit** - Drag-and-drop for Kanban boards

### Real-Time
- **WebSocket** - Bidirectional communication
- **Yjs (pycrdt)** - CRDT for collaborative editing
- **y-websocket** - Yjs WebSocket provider

## Project Structure

```
pm-project/
├── fastapi-backend/           # Python backend
│   ├── app/
│   │   ├── main.py            # FastAPI application entry
│   │   ├── config.py          # Environment configuration
│   │   ├── database.py        # SQLAlchemy setup
│   │   ├── models/            # Database models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── routers/           # API endpoints
│   │   ├── services/          # Business logic layer
│   │   └── websocket/         # WebSocket handlers
│   ├── alembic/               # Database migrations
│   ├── tests/                 # pytest test suite
│   └── requirements.txt       # Python dependencies
│
├── electron-app/              # Electron + React frontend
│   ├── src/
│   │   ├── main/              # Electron main process
│   │   ├── preload/           # Secure bridge scripts
│   │   └── renderer/          # React application
│   │       ├── components/    # UI components
│   │       ├── pages/         # Page components
│   │       ├── stores/        # Zustand stores
│   │       ├── hooks/         # Custom React hooks
│   │       ├── contexts/      # React contexts
│   │       └── lib/           # Utilities and clients
│   ├── tests/                 # Frontend tests
│   └── package.json           # Node dependencies
│
├── specs/                     # Feature specifications
│   └── 019-knowledge-base/    # Current feature docs
│
└── docs/                      # This documentation
```

## Scale Target

PM Desktop is designed to support **5,000 concurrent users** per server instance with:
- Sub-100ms UI interactions
- Sub-200ms API read operations
- Real-time updates across all connected clients
- Offline-first caching with sync on reconnect

## Core Features

1. **Application Management** - Top-level containers for organizing projects
2. **Project Boards** - Kanban-style task management with drag-and-drop
3. **Task Management** - Issues with types (story, bug, epic), priorities, and statuses
4. **Comments & @Mentions** - Rich text comments with user tagging
5. **Checklists** - Task checklists with progress tracking
6. **File Attachments** - Upload and preview files on tasks
7. **Member Management** - Role-based access (owner, editor, viewer)
8. **Invitations** - Invite users to applications
9. **Notifications** - Real-time notifications for mentions and assignments
10. **Presence Indicators** - See who's viewing tasks in real-time
11. **Knowledge Base** - Collaborative notes with real-time editing

## Getting Started

See [Getting Started](./getting-started.md) for:
- System requirements
- Development environment setup
- Running the application locally
- Common development commands
