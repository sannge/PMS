# Getting Started

This guide covers setting up your development environment and running PM Desktop locally.

## System Requirements

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.12+ | Backend runtime |
| Node.js | 20 LTS+ | Frontend tooling |
| npm | 10+ | Package management |
| Git | 2.40+ | Version control |
| LLM Provider | Any one of: OpenAI, Anthropic, or Ollama | AI agent features |

All infrastructure services (PostgreSQL, Redis, MinIO, MeiliSearch) run on shared VMs with separate dev/prod namespaces. See [Environment Separation](#environment-separation) for details.

### Recommended Development Tools

- **VS Code** or **PyCharm** - IDE with Python/TypeScript support
- **pgAdmin** or **DBeaver** - Database management
- **Redis Insight** - Redis GUI
- **Postman** or **Insomnia** - API testing

## Environment Separation

Dev and prod share the same VM infrastructure but use separate databases, buckets, indexes, and Redis keyspaces:

| Service | Dev (`APP_ENV=dev`) | Prod (default) |
|---------|---------------------|-----------------|
| PostgreSQL | `pmsdb_test` | `pmsdb` |
| Redis | DB 1 (`/1`) | DB 0 (`/0`) |
| MinIO buckets | `pm-attachments-dev`, `pm-images-dev` | `pm-attachments`, `pm-images` |
| MeiliSearch index | `documents_dev` | `documents` |
| Environment | `development` | `production` |

### How it works

The `APP_ENV` environment variable selects which config file to load:

```
APP_ENV=dev  --> loads .env.dev
APP_ENV=prod --> loads .env.prod  (this is the default)
```

Both `.env.dev` and `.env.prod` are **gitignored** (they contain real credentials). A committed template `.env.prod.example` shows the expected structure.

### Config files

| File | Gitignored | Purpose |
|------|------------|---------|
| `fastapi-backend/.env.dev` | Yes | Dev config (pmsdb_test, Redis DB 1, dev buckets) |
| `fastapi-backend/.env.prod` | Yes | Prod config (pmsdb, Redis DB 0, prod buckets) |
| `fastapi-backend/.env.prod.example` | No | Committed template with placeholder secrets |

## Backend Setup

### 1. Install uv

[uv](https://docs.astral.sh/uv/) is the package manager for the backend.

```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install Python Dependencies

```bash
cd fastapi-backend

# Install all dependencies (creates .venv automatically, generates uv.lock)
uv sync
```

This reads `pyproject.toml` and installs all production and dev dependencies. Key packages include:
- `fastapi` / `uvicorn` - Web framework and ASGI server
- `sqlalchemy` / `asyncpg` / `alembic` - Database ORM, async driver, migrations
- `redis` / `minio` / `meilisearch-python-sdk` - Caching, file storage, search
- `langgraph` / `langchain-*` - AI agent framework
- `pgvector` / `tiktoken` - Vector embeddings and tokenization
- `arq` - Background job worker (document embedding)
- `docling` / `fpdf2` / `python-calamine` - Document import and export
- `ruff` - Linting and formatting (dev dependency)
- `vsdx` - Visio file extraction
- `openpyxl` - Excel export
- `duckduckgo-search`, `trafilatura` - Web search and scraping tools
- `sqlglot` - SQL validation for agent database queries
- `defusedxml` - XXE prevention for XML parsing

### 3. Configure Environment Variables

Copy the prod template and fill in real credentials:

```bash
cp fastapi-backend/.env.prod.example fastapi-backend/.env.prod
# Edit .env.prod with real passwords and API keys
```

For the dev environment, create `fastapi-backend/.env.dev` with the same structure but using dev-specific values (see [Environment Separation](#environment-separation) for which values differ).

> **Note**: You only need one LLM provider. Alternatively, you can skip the AI keys and configure a provider later through the admin Settings panel in the UI.

### 4. Run Database Migrations

```bash
cd fastapi-backend

# Against prod database (default)
uv run alembic upgrade head

# Against dev database
APP_ENV=dev uv run alembic upgrade head
```

### 5. Seed Sample Data (Dev)

```bash
cd fastapi-backend
APP_ENV=dev uv run python -m scripts.seed_sample_data --clean
```

This creates 10 demo users (password: `Demo1234!`), 3 applications, 8 projects, 64 tasks, comments, checklists, and 32 knowledge base documents.

### 6. Start the Backend Server

```bash
cd fastapi-backend

# Dev environment
APP_ENV=dev uv run uvicorn app.main:app --reload --port 8001

# Prod environment (default)
uv run uvicorn app.main:app --reload --port 8001
```

The API is now available at:
- **API**: http://localhost:8001
- **OpenAPI Docs**: http://localhost:8001/docs
- **WebSocket**: ws://localhost:8001/ws

### 7. Start the Background Worker

The background worker handles asynchronous tasks like document embedding for AI search. Run it in a separate terminal:

```bash
cd fastapi-backend

# Match the same APP_ENV as the API server
APP_ENV=dev uv run arq app.worker.WorkerSettings
```

> **Note**: The worker is optional for basic usage but required for AI-powered document search and embedding features.

## Frontend Setup

### 1. Install Node Dependencies

```bash
cd electron-app
npm install
```

Key dependencies include:
- `electron` - Desktop framework
- `react` - UI library
- `@tanstack/react-query` - Server state
- `zustand` - Client state
- `@radix-ui/*` - UI primitives
- `tailwindcss` - Styling
- `@tiptap/*` - Rich text editor
- `@dnd-kit/*` - Drag-and-drop
- `recharts` - Charts and data visualization
- `react-drawio` - Diagram editing

### 2. Configure Environment

Create `electron-app/.env`:

```env
VITE_API_URL=http://localhost:8001
VITE_MINIO_URL=http://<your-minio-vm-ip>:9000
```

### 3. Start Development Server

```bash
cd electron-app
npm run dev
```

This starts:
- Vite dev server with HMR
- Electron main process
- React renderer process

## Verification

### Check Backend Health

```bash
curl http://localhost:8001/health
# Expected: {"status": "healthy"}
```

### Check API Documentation

Open http://localhost:8001/docs in your browser to see the interactive Swagger UI.

### Test Login

1. If you seeded sample data, use any demo account (e.g. `alice@demo.com` / `Demo1234!`)
2. Or register a new user via the app
3. Or create via API:

```bash
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com", "password": "TestPassword123!", "display_name": "Developer"}'
```

### Verify AI Features

AI features require at least one LLM provider to be configured. You can check this in two ways:

1. **Via the UI**: Open the Settings panel and navigate to the AI configuration section. Add your provider API key or Ollama endpoint.
2. **Via the admin API**: The AI endpoints are available under `/api/ai/` once a provider is configured.

### Verify Document Search

After creating documents in the Knowledge Base, Meilisearch should index them automatically. You can verify by searching from the Knowledge Base search bar or by querying Meilisearch directly:

```bash
# Dev index
curl http://<your-meili-vm-ip>:7700/indexes/documents_dev/search \
  -H "Authorization: Bearer <your-meili-key>" \
  -H "Content-Type: application/json" \
  -d '{"q": "test"}'
```

## Common Commands

### Backend

```bash
# Run server with auto-reload (dev)
APP_ENV=dev uv run uvicorn app.main:app --reload --port 8001

# Run server with auto-reload (prod)
uv run uvicorn app.main:app --reload --port 8001

# Run background worker
APP_ENV=dev uv run arq app.worker.WorkerSettings

# Run tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ --cov=app --cov-report=html

# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations (dev)
APP_ENV=dev uv run alembic upgrade head

# Rollback migration
uv run alembic downgrade -1

# Seed sample data (dev)
APP_ENV=dev uv run python -m scripts.seed_sample_data --clean
```

### Frontend

```bash
# Development mode
npm run dev

# Type checking
npm run typecheck

# Lint
npm run lint

# Lint and fix
npm run lint:fix

# Run tests
npm test

# Build for production
npm run build

# Package Electron app
npm run package

# Publish release to GitHub (requires GH_TOKEN env var)
npm version patch && npx electron-vite build && npx electron-builder --publish always

# E2E smoke tests
npm run e2e:smoke

# E2E two-client collaboration tests
npm run e2e:two-client

# E2E knowledge base tests
npm run e2e:knowledge
```

## Troubleshooting

### PostgreSQL Connection Issues

1. Ensure PostgreSQL is running: `pg_isready -h <your-db-vm-ip> -p 5432`
2. Check firewall rules allow port 5432
3. Verify user credentials and database exist
4. Check `pg_hba.conf` for authentication settings

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli -h <your-redis-vm-ip> -a <password> ping
# Expected: PONG

# Test dev DB (1)
redis-cli -h <your-redis-vm-ip> -a <password> -n 1 ping
```

### MinIO Bucket Verification

Verify dev buckets exist at http://<your-minio-vm-ip>:9001:
1. Login with your MinIO credentials
2. Check that `pm-attachments-dev` and `pm-images-dev` exist (dev)
3. Check that `pm-attachments` and `pm-images` exist (prod)

### WebSocket Connection Fails

1. Check CORS configuration in `app/main.py`
2. Verify JWT token is valid
3. Check browser console for errors

### Alembic Migration Errors

```bash
# Check current migration status
uv run alembic current

# View migration history
uv run alembic history

# Stamp database (if tables exist but migration tracking is off)
uv run alembic stamp head
```

## Next Steps

- Read [Architecture Overview](./architecture.md) to understand the system design
- Review [Backend Guide](./backend.md) for API development
- Check [Frontend Guide](./frontend.md) for UI development
