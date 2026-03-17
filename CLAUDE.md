# PM Desktop

**Last updated**: 2026-03-15

PM Desktop is a project management app (Jira-like + OneNote-style notes), built with Electron (React/TypeScript frontend) and FastAPI (Python backend).

## Commands

```bash
# Backend (APP_ENV selects .env.dev or .env.prod; defaults to "prod")
cd fastapi-backend && APP_ENV=dev uv run uvicorn app.main:app --reload --port 8001
cd fastapi-backend && APP_ENV=dev uv run arq app.worker.WorkerSettings
cd fastapi-backend && uv run pytest tests/ -v
cd fastapi-backend && uv run ruff check .

# Frontend
cd electron-app && npm run dev
cd electron-app && npm run typecheck
cd electron-app && npm run lint
```

## Environment Separation

Dev and prod share the same VMs but use separate namespaces. `APP_ENV` controls which `.env.*` file is loaded:

- `APP_ENV=dev` → `.env.dev` (pmsdb_test, Redis DB 1, `*-dev` buckets/indexes)
- `APP_ENV=prod` (default) → `.env.prod` (pmsdb, Redis DB 0, standard buckets/indexes)

Both env files are gitignored. See `fastapi-backend/.env.prod.example` for the template.

## Architecture Decisions

- **IMPORTANT**: State-based routing, NOT react-router — navigation via callbacks and state in DashboardPage. Components fully unmount on screen switch.
- WebSocket-driven cache invalidation at app level (`use-websocket-cache.ts`)
- IndexedDB persistence with progressive hydration (`cache-config.ts`)
- Document locking + WebSocket sync for collaborative editing (TipTap rich text)
- Blair AI Copilot: LangGraph agent with 51 tools (25 read + 26 write), runtime-configurable via `config_service.py`
- Runtime constants via getter functions (`get_max_tool_calls()` etc.), NOT module-level frozen values

## Coding Standards

File-scoped rules are in `.claude/rules/`:
- @.claude/rules/backend.md — Python/FastAPI conventions
- @.claude/rules/frontend.md — TypeScript/React conventions

## External API Documentation (Context Hub)

**IMPORTANT**: When writing code that uses any external API, SDK, or third-party library, use `chub` to fetch current documentation BEFORE writing code. Do NOT rely on training data for API shapes — APIs change frequently.

### When to use Context Hub

- Integrating or modifying code that calls a third-party API or SDK
- Unsure about current method signatures, parameters, or return types
- Adding a new dependency to the project
- Debugging API errors that might stem from version mismatches

### Quick reference

```bash
chub search "<library>"             # Find available docs
chub get <id> --lang py             # Fetch Python-specific docs
chub get <id> --lang js             # Fetch JS/TS-specific docs
chub annotate <id> "<note>"         # Save a gotcha for future sessions
chub feedback <id> up               # Rate docs quality (ask user first)
```

### Key APIs in this project

Look these up with `chub` when modifying their integrations:
- **Backend**: `fastapi`, `sqlalchemy`, `pydantic`, `alembic`, `meilisearch`, `redis`
- **Frontend**: `electron`, `react`, `tiptap`, `zustand`, `radix-ui`, `tailwindcss`
- **AI/Agent**: `langchain`, `langgraph`, `openai` (LLM provider APIs)
- **Infrastructure**: `arq` (task queue), `fpdf2` (PDF export)

## Performance Targets

- UI interactions: <100ms
- API reads: <200ms
- Scale: 5,000 concurrent users per server instance

## Testing

- Backend: pytest with 80% coverage target — prefer single test files over full suite
- Frontend: ESLint zero warnings, `npm run typecheck` must pass
- Run relevant tests after making changes

## Specs & Plans

Feature specs and implementation plans: `specs/<number>-<name>/`
