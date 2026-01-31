# Technology Stack

**Analysis Date:** 2026-01-31

## Languages

**Primary:**
- Python 3.12 - Backend API, data processing, WebSocket handlers
- TypeScript 5.5 - Frontend React components, Electron main/preload, build configuration
- JavaScript/JSX - React component implementations, some utility functions

**Secondary:**
- HTML/CSS - DOM markup and styling (Tailwind CSS utility-based)
- SQL - Database migrations and queries via SQLAlchemy ORM

## Runtime

**Backend Environment:**
- Python 3.12 (via venv at `fastapi-backend/.venv/`)
- Uvicorn ASGI server (async HTTP + WebSocket support)

**Frontend Environment:**
- Node.js (npm-based package management)
- Electron 30.1.2 (Chromium + Node.js for desktop app)
- Vite 5.3.4 (module bundler and dev server)

**Package Managers:**
- **Backend:** pip (Python) - see `fastapi-backend/requirements.txt`
- **Frontend:** npm 10+ (npm-lock.json at `electron-app/package-lock.json`)
- **E2E Tests:** npm (separate `tests/package.json`)

## Frameworks

**Core Backend:**
- FastAPI 0.115+ - REST API framework with async/await, type hints, auto-docs
- Uvicorn 0.32+ - ASGI server with WebSocket support

**Core Frontend:**
- React 18.3.1 - UI component framework
- Electron 30.1.2 - Cross-platform desktop application
- TailwindCSS 3.4.6 - Utility-first CSS framework
- Radix UI - Unstyled, accessible component library (buttons, dialogs, menus, tabs, etc.)
  - Uses 15+ packages: `@radix-ui/react-*` for dialog, dropdown-menu, popover, tabs, tooltip, accordion, etc.
  - Located in `electron-app/src/renderer/components/` (shadcn/ui pattern)

**Real-time & Collaboration:**
- Electron 30.1.2 with WebSocket support for bidirectional communication
- Server-Sent Events via FastAPI WebSocket endpoints (`app/websocket/handlers.py`)

**State Management:**
- React Context (authentication) - migrated from Zustand, see `src/renderer/contexts/auth-context.ts`
- TanStack React Query 5.90+ - Server state + caching (async data synchronization)
  - Devtools enabled (`@tanstack/react-query-devtools`)
  - Persistence client (`@tanstack/react-query-persist-client`)

**Rich Text Editing:**
- TipTap 2.6.0 - Collaborative-ready WYSIWYG editor
  - Extensions: StarterKit, Underline, TextAlign, Highlight, Image, Link, Table (with Row/Header/Cell), Color, FontFamily, Placeholder, TaskList
  - Custom extensions available at `src/renderer/components/editor/RichTextEditor.tsx`

**Drag & Drop:**
- @dnd-kit 6.1.0 + sortable 8.0.0 - Headless drag-and-drop primitives
  - Used for task/project organization

**Testing:**
- **Backend:** pytest 8.3+, pytest-asyncio 0.24+ for async tests
  - Config: None found (uses defaults)
  - Tests at `fastapi-backend/tests/`
- **Frontend:** Vitest 1.3.1 - Fast unit/component testing (Vite-native)
  - Config: `electron-app/vitest.config.ts`
  - jsdom environment for DOM testing
  - Tests co-located or in `src/renderer/__tests__/`
- **E2E:** Playwright (likely, see `tests/playwright.config.ts`)

**Build & Dev Tools:**
- Electron Vite 2.3.0 - Electron-optimized bundler (Vite + ESM for main/preload)
  - Config: `electron-app/electron.vite.config.ts`
- Electron Builder 24.13.3 - Desktop app packaging (NSIS installer for Windows)
- TypeScript 5.5.3 - Type checking compiler
- ESLint - JavaScript/TypeScript linter (config not found, likely uses eslint.config.js or defaults)
- PostCSS 8.4.39 - CSS transformation (with TailwindCSS plugin)
- Vite 5.3.4 - Frontend build tool

**UI & Styling:**
- TailwindCSS 3.4.6 - Utility CSS with `tailwind.config.js`
- TailwindCSS Animate 1.0.7 - Animation utility classes
- Class Variance Authority 0.7.0 - Type-safe component variant library (shadcn/ui patterns)
- clsx 2.1.1 - Conditional class name utility
- Tailwind Merge 2.4.0 - Smart class merging (resolve Tailwind conflicts)
- Lucide React 0.400.0 - Icon library

**Client Storage:**
- IndexedDB via idb 8.0.1 - Structured client-side database
- idb-keyval 6.2.2 - Simple key-value wrapper over IndexedDB
- lz-string 1.5.0 - String compression for storage efficiency

**Utilities:**
- dotenv 17.2.3 - Environment variable loading
- react-dom 18.3.1 - React DOM rendering
- react-virtuoso 4.10.0 - Virtual scrolling for large lists
- msgpack 1.0+ (Python) - Binary serialization for WebSocket messages

## Configuration

**Backend Environment (.env pattern):**
- `fastapi-backend/.env` - Production/dev secrets (DO NOT commit)
- `fastapi-backend/.env.example` - Template for environment variables
- Key env vars:
  - `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` - PostgreSQL connection
  - `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_SECURE` - S3-compatible storage
  - `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES` - Authentication
  - `HOST`, `PORT` - Server binding
  - `REDIS_URL`, `REDIS_MAX_CONNECTIONS` - Redis pub/sub (5000 concurrent users)
  - `WS_MAX_CONNECTIONS_PER_USER`, `WS_MAX_CONNECTIONS` - DDoS protection
  - `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` - Connection pooling tuning
  - `MEILISEARCH_URL`, `MEILISEARCH_MASTER_KEY` - Full-text search (optional)

**Frontend Environment (.env pattern):**
- `electron-app/.env` - Development/build vars
  - `VITE_API_URL=http://localhost:8001` - Backend API endpoint
  - `VITE_MINIO_URL=http://10.18.137.108:9000` - MinIO endpoint for file upload/download

**Build Configuration:**
- `electron-app/package.json` - Scripts: dev, dev:client2, dev:client3 (multi-user testing), build, preview, typecheck, lint, package
- `electron-app/electron.vite.config.ts` - Vite bundler config for Electron
- `electron-app/tsconfig.json` - TypeScript strict mode, path aliases (`@/*`, `@/components/*`, etc.)
- `electron-app/postcss.config.js` - PostCSS with TailwindCSS plugin
- `electron-app/tailwind.config.js` - TailwindCSS configuration
- `fastapi-backend/alembic.ini` - Database migration tool config

**Type Safety:**
- TypeScript: `strict: true` mode enabled
- Python: Type hints required (enforced via Pydantic schemas and FastAPI type hints)

## Platform Requirements

**Development:**
- Python 3.12 with pip (Windows/macOS/Linux)
- Node.js 18+ with npm
- PostgreSQL 13+ or compatible (for development; production uses MSSQL)
- Redis 7+ (optional for single-worker, required for 5000 concurrent users)
- MinIO (S3-compatible storage, local or remote)
- Meilisearch (full-text search engine, optional)

**Production Deployment:**
- Windows server (NSIS installer target for desktop, or Uvicorn on Windows Server)
- Electron packaged as Windows NSIS installer (see `electron-app/package.json` build config)
- PostgreSQL or compatible database backend
- Redis (for multi-worker WebSocket scaling)
- MinIO or S3-compatible object storage
- Meilisearch (for full-text search features)

---

*Stack analysis: 2026-01-31*
