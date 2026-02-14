# PM Desktop - Claude Code Context

**Last updated**: 2026-01-24

## Project Overview

PM Desktop is a project management application with Jira-like features and OneNote-style note-taking, built with Electron (React/TypeScript frontend) and FastAPI (Python backend).

## Active Technologies

- Python 3.12 + FastAPI, SQLAlchemy, Pydantic, Alembic
- TypeScript 5.5 + React 18, Electron 30, Zustand, Radix UI, TailwindCSS, TipTap
- Postgres SQL
- Redis 7+ (WebSocket pub/sub and caching)
- @dnd-kit (drag-and-drop)
- pycrdt (Python CRDT for Yjs compatibility)
- Meilisearch (full-text search engine)
- @tiptap/extension-collaboration + y-websocket (real-time collaborative editing)

## Project Structure

```
fastapi-backend/
├── app/
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   ├── routers/      # FastAPI endpoints
│   ├── services/     # Business logic
│   └── websocket/    # WebSocket handlers
├── alembic/          # Database migrations
└── tests/            # pytest unit/integration tests

electron-app/
├── src/
│   └── renderer/
│       ├── components/  # React components
│       ├── pages/       # Page components
│       ├── stores/      # Zustand stores
│       └── hooks/       # Custom hooks
└── tests/               # E2E tests
```

## Common Commands

```bash
# Backend
cd fastapi-backend
uvicorn app.main:app --reload --port 8001
pytest tests/ -v
ruff check .

# Frontend
cd electron-app
npm run dev
npm run typecheck
npm run lint
```

## Coding Conventions

### Python (Backend)

- Type hints required for all functions
- Pydantic models for request/response schemas
- SQLAlchemy async patterns with selectinload
- pytest for testing (80% coverage target)
- Ruff for linting

### TypeScript (Frontend)

- Strict mode enabled
- Radix UI + TailwindCSS for components (shadcn/ui pattern)
- Zustand for state management
- TipTap for rich text editing
- State-based routing (NOT react-router) - navigation via callbacks and state in DashboardPage
- ESLint with zero warnings policy

## Current Feature: 019-knowledge-base

### Scope

Real-time collaborative knowledge system with:

- Google Docs-like collaborative rich-text editing
- Hierarchical folder/document structure for Applications, Projects, Tasks
- Real-time cursor sharing and co-editing using Yjs CRDT
- Full-text search via Meilisearch
- Unified "Notes" screen showing all knowledge organized by Application → Projects
- Role-based permissions (Owner/Editor can edit, Viewers read-only)

### Scale Target

5,000 concurrent users per server instance

### Key Files

- Spec: `specs/019-knowledge-base/spec.md`
- Plan: `specs/019-knowledge-base/plan.md`
- Research: `specs/019-knowledge-base/research.md`
- Data Model: `specs/019-knowledge-base/data-model.md`
- API Contracts: `specs/019-knowledge-base/contracts/`

### Skills to Use

- **frontend-design**: For UI component implementation
- **agent-browser**: For E2E testing after each feature

## Recent Changes

- 019-knowledge-base (in progress):
  - Backend: Document, DocumentFolder, DocumentSnapshot models with Alembic migration
  - Backend: Document/folder CRUD routers, Yjs WebSocket handler, search service (Meilisearch)
  - Frontend: Knowledge tree components (FolderNode, DocumentNode, KnowledgeTree)
  - Frontend: Collaborative editor with TipTap + Yjs integration
  - Frontend: Full-text search UI (KnowledgeSearch component)
  - Frontend: shadcn/ui components (dialog, input, label, popover, dropdown-menu, scroll-area)
- 017-project-task-management-and-permissions: Comments, Checklists, DnD, Presence features
- Backend: TaskStatus, ProjectMember, ProjectTaskStatusAgg models

## Constitution Principles

1. **Code Quality**: Type safety, linting compliance, code review
2. **Testing Standards**: pytest backend (80%), agent-browser E2E frontend
3. **UX Consistency**: Radix UI design system, WCAG 2.1 AA
4. **Performance**: <100ms UI, <200ms API reads, 5000 concurrent users
