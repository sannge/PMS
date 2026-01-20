# PM Desktop - Claude Code Context

**Last updated**: 2026-01-19

## Project Overview

PM Desktop is a project management application with Jira-like features and OneNote-style note-taking, built with Electron (React/TypeScript frontend) and FastAPI (Python backend).

## Active Technologies

- Python 3.11 + FastAPI, SQLAlchemy, Pydantic, Alembic (017-project-task-management-and-permissions)
- TypeScript 5.5 + React 18, Electron 30, Zustand, Radix UI, TailwindCSS, TipTap (017-project-task-management-and-permissions)
- Microsoft SQL Server (via pyodbc)
- Redis 7+ (WebSocket pub/sub and caching)
- @dnd-kit (drag-and-drop)

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
uvicorn app.main:app --reload --port 8000
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
- Radix UI + TailwindCSS for components
- Zustand for state management
- TipTap for rich text editing
- ESLint with zero warnings policy

## Current Feature: 017-project-task-management-and-permissions

### Scope
Complete project task management with:
- Drag-and-drop Kanban board
- Comments with @mentions
- Checklists
- Project member management
- Status override
- Real-time presence indicators

### Scale Target
5,000 concurrent users per server instance

### Key Files
- Spec: `specs/auto-claude/017-project-task-management-and-permissions/spec.md`
- Plan: `specs/auto-claude/017-project-task-management-and-permissions/plan.md`
- Research: `specs/auto-claude/017-project-task-management-and-permissions/research.md`
- Data Model: `specs/auto-claude/017-project-task-management-and-permissions/data-model.md`

### Skills to Use
- **frontend-design**: For UI component implementation
- **agent-browser**: For E2E testing after each feature

## Recent Changes

- 017-project-task-management-and-permissions: Added Comments, Checklists, DnD, Presence features
- Backend: TaskStatus, ProjectMember, ProjectTaskStatusAgg models
- Frontend: Basic Kanban structure, WebSocket connection

## Constitution Principles

1. **Code Quality**: Type safety, linting compliance, code review
2. **Testing Standards**: pytest backend (80%), agent-browser E2E frontend
3. **UX Consistency**: Radix UI design system, WCAG 2.1 AA
4. **Performance**: <100ms UI, <200ms API reads, 5000 concurrent users
