# External Integrations

**Analysis Date:** 2026-01-31

## APIs & External Services

**File Storage (Object Storage):**
- MinIO (S3-compatible API) - Self-hosted or cloud object storage
  - SDK: `minio>=7.2.0` (Python)
  - Usage: File uploads/downloads via `app/services/minio_service.py`
  - Auth: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` (env vars)
  - Frontend config: `VITE_MINIO_URL` in `electron-app/.env`

**Full-Text Search (Optional):**
- Meilisearch - Modern search engine
  - Configuration: `MEILISEARCH_URL`, `MEILISEARCH_MASTER_KEY` (env vars)
  - Implementation: Referenced in CLAUDE.md for knowledge-base feature (not yet wired in requirements.txt)

**Real-time Pub/Sub & Caching:**
- Redis 7+ - In-memory data store
  - SDK: `redis[hiredis]>=5.0.0` (Python async)
  - Usage: WebSocket pub/sub (multi-worker scaling), presence tracking, caching
  - Auth: `REDIS_URL` connection string (env var, e.g., `redis://:password@host:port/db`)
  - Config: `REDIS_MAX_CONNECTIONS`, `REDIS_SOCKET_TIMEOUT`, `REDIS_RETRY_ON_TIMEOUT`
  - Requirement: `REDIS_REQUIRED=true` for multi-worker deployment
  - Fallback: Single-worker mode if Redis unavailable (when `REDIS_REQUIRED=false`)

**Message Serialization:**
- msgpack 1.0+ - Binary message encoding for WebSocket efficiency
  - Usage: Compact serialization of WebSocket frames and Redis messages

## Data Storage

**Primary Database:**
- PostgreSQL 13+ (async connection via asyncpg)
  - Client: `sqlalchemy>=2.0.0` (ORM), `asyncpg>=0.29.0` (async driver)
  - Connection: `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` (env vars)
  - Pooling: `DB_POOL_SIZE=50`, `DB_MAX_OVERFLOW=100` (tuned for 5000 concurrent users)
  - Async connection URL: `postgresql+asyncpg://user:pass@host:port/db`
  - Sync URL (Alembic): `postgresql+psycopg2://user:pass@host:port/db`
  - Alembic migrations: `fastapi-backend/alembic/` directory
  - Warmup: Connection pool pre-warmed at startup (`app/database.py`)

**Secondary Database (Alternate):**
- MSSQL Server (mentioned in CLAUDE.md for production)
  - Environment vars: `MSSQL_SERVER`, `MSSQL_DB`, `MSSQL_USER`, `MSSQL_PASSWORD`, `MSSQL_PORT`
  - Current code uses PostgreSQL; MSSQL support appears to be legacy or future integration

**Client Storage:**
- IndexedDB (browser/Electron local storage)
  - Libraries: `idb>=8.0.1`, `idb-keyval>=6.2.2` (JavaScript)
  - Purpose: Offline data, cache, local state persistence
  - TanStack React Query integrates with IndexedDB via `@tanstack/react-query-persist-client`

**File Storage:**
- MinIO (S3-compatible, see APIs section above)

## Authentication & Identity

**Auth Provider:**
- Custom JWT-based implementation
  - Library: `python-jose[cryptography]>=3.3.0`, `passlib[bcrypt]>=1.7.4` (Python backend)
  - Token: JWT (JSON Web Tokens)
  - Algorithm: `JWT_ALGORITHM` (HS256 or similar, env var)
  - Expiration: `JWT_EXPIRATION_MINUTES=1440` (24 hours, env var)
  - Secret: `JWT_SECRET` (env var, must change in production)
  - Password hashing: bcrypt via passlib
  - Implementation: `app/services/auth_service.py` (backend), `src/renderer/contexts/auth-context.ts` (frontend)

**Authorization:**
- Role-based access control (RBAC)
  - Roles: Owner, Editor, Viewer (document/project-level)
  - Implementation: `app/services/permission_service.py`
  - WebSocket access: Validated in `app/websocket/room_auth.py` before subscriptions

## Monitoring & Observability

**Error Tracking:**
- Not detected / Standard logging only
- Logging: Built-in Python `logging` module, console output
  - Backend: Configured in `app/main.py` (INFO level)
  - Frontend: Console logging in development

**Logs:**
- Standard output (stdout)
  - Backend: FastAPI/Uvicorn logs to console
  - Frontend: Browser/Electron console
  - No centralized log aggregation detected

**Performance Metrics:**
- Not implemented (infrastructure-level monitoring not in codebase)

## CI/CD & Deployment

**Hosting:**
- Self-hosted or on-premises only (no cloud provider integration detected)
- Backend: Uvicorn ASGI server (Python, can run on Windows, Linux, macOS)
- Frontend: Electron desktop app (Windows NSIS installer target)
  - Build target: `win` with `nsis` installer
  - Packager: `electron-builder>=24.13.3`

**CI Pipeline:**
- Not detected in codebase (no GitHub Actions, GitLab CI, or similar found)

**Deployment Configuration:**
- Backend: Uvicorn startup with env vars (no Docker detected)
- Frontend: Electron packager config in `electron-app/package.json`
  - Windows NSIS installer (one-click not forced, directory selection allowed)
  - Output: `electron-app/dist/`

## Environment Configuration

**Required env vars (Backend):**
- **Database:** DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT
- **MinIO:** MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE
- **Auth:** JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES
- **Server:** HOST, PORT
- **WebSocket:** WS_MAX_CONNECTIONS_PER_USER, WS_MAX_CONNECTIONS, WS_HEARTBEAT_INTERVAL
- **Redis:** REDIS_URL, REDIS_MAX_CONNECTIONS, REDIS_SOCKET_TIMEOUT, REDIS_RETRY_ON_TIMEOUT, REDIS_REQUIRED
- **Pooling:** DB_POOL_SIZE, DB_MAX_OVERFLOW
- **Search:** MEILISEARCH_URL, MEILISEARCH_MASTER_KEY (optional)
- **Testing:** TEST_DB_USER, TEST_DB_PASSWORD

**Required env vars (Frontend):**
- VITE_API_URL - Backend API endpoint (e.g., http://localhost:8001)
- VITE_MINIO_URL - MinIO endpoint for file operations

**Secrets location:**
- `.env` files in `fastapi-backend/` and `electron-app/`
- **WARNING:** These contain secrets; always use `.env.example` as template
- Example: `fastapi-backend/.env.example`, `fastapi-backend/.env` (production secrets, gitignored)

## Webhooks & Callbacks

**Incoming Webhooks:**
- Not detected in codebase

**Outgoing Webhooks:**
- Not detected in codebase

**Real-time Callbacks:**
- WebSocket messages (bidirectional)
  - Server → Client: Presence updates, document changes, notifications
  - Client → Server: User actions, edits, room subscriptions
  - Handler: `app/websocket/handlers.py` (message routing and processing)

## Data Sync & Collaboration Features

**Real-time Collaboration Layers:**
- WebSocket transport: Electron ↔ FastAPI WebSocket endpoint
- Message format: JSON + msgpack (binary optimization)
- State synchronization:
  - **Presence:** Active user cursors/selections (via `app/websocket/presence.py`)
  - **Documents:** Hierarchical folder/document structure (SQLAlchemy ORM)
  - **Notifications:** Real-time alerts (Redis pub/sub broadcast)
  - **Activity:** Comments, checklists, task updates (via WebSocket room subscriptions)

**Collaborative Editing (In Development):**
- TipTap editor with Yjs support planned (CLAUDE.md mentions Yjs CRDT)
- pycrdt mentioned for Yjs compatibility (not yet in requirements.txt)
- @tiptap/extension-collaboration not in package.json yet (feature 019-knowledge-base in progress)

---

*Integration audit: 2026-01-31*
