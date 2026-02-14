# Getting Started

This guide covers setting up your development environment and running PM Desktop locally.

## System Requirements

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.12+ | Backend runtime |
| Node.js | 20 LTS+ | Frontend tooling |
| npm | 10+ | Package management |
| PostgreSQL | 14+ | Primary database |
| Redis | 7+ | Caching and pub/sub |
| MinIO | Latest | File storage |
| Meilisearch | 1.6+ | Full-text search engine |
| Git | 2.40+ | Version control |

### Optional Software

| Software | Version | Purpose |
|----------|---------|---------|
| Docker | 24+ | Container runtime for services |

### Recommended Development Tools

- **VS Code** or **PyCharm** - IDE with Python/TypeScript support
- **pgAdmin** or **DBeaver** - Database management
- **Redis Insight** - Redis GUI
- **Postman** or **Insomnia** - API testing

## Backend Setup

### 1. Create Python Virtual Environment

```bash
cd fastapi-backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies include:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `sqlalchemy` - ORM
- `alembic` - Migrations
- `asyncpg` - PostgreSQL async driver
- `python-jose` - JWT handling
- `passlib` - Password hashing
- `redis` - Redis client
- `minio` - MinIO client
- `pytest` - Testing framework

### 3. Configure Environment Variables

Create `fastapi-backend/.env`:

```env
# Database (PostgreSQL)
DB_SERVER=localhost
DB_PORT=5432
DB_NAME=PMDB
DB_USER=pmdbuser
DB_PASSWORD=YourSecurePassword123!

# Connection pool
DB_POOL_SIZE=50
DB_MAX_OVERFLOW=100

# JWT Authentication
JWT_SECRET=your-super-secret-jwt-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO (File Storage)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false

# Meilisearch
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_API_KEY=your-meilisearch-key

# WebSocket Settings
WS_MAX_CONNECTIONS_PER_USER=50
```

### 4. Set Up PostgreSQL Database

#### Option A: Local PostgreSQL

1. Install PostgreSQL 14+ from https://www.postgresql.org/download/
2. Create database and user:

```sql
CREATE USER pmdbuser WITH PASSWORD 'YourSecurePassword123!';
CREATE DATABASE PMDB OWNER pmdbuser;
```

#### Option B: Docker

```bash
docker run -e POSTGRES_USER=pmdbuser -e POSTGRES_PASSWORD=YourSecurePassword123! \
  -e POSTGRES_DB=PMDB -p 5432:5432 --name postgres \
  -d postgres:16-alpine
```

### 5. Run Database Migrations

```bash
cd fastapi-backend
alembic upgrade head
```

This creates all required tables:
- `users` - User accounts
- `applications` - Top-level containers
- `application_members` - App membership
- `projects` - Project boards
- `project_members` - Project membership
- `tasks` - Task/issue tracking
- `task_statuses` - Status columns
- `comments` - Task comments
- `mentions` - @mention tracking
- `checklists` - Task checklists
- `checklist_items` - Checklist items
- `attachments` - File metadata
- `notifications` - User notifications
- `invitations` - App invitations
- `document_folders` - Knowledge base folder hierarchy
- `documents` - Knowledge base documents
- `document_snapshots` - Document version history

### 6. Start Redis

#### Option A: Local Installation

```bash
redis-server
```

#### Option B: Docker

```bash
docker run -p 6379:6379 --name redis -d redis:7-alpine
```

### 7. Start MinIO

#### Docker (Recommended)

```bash
docker run -p 9000:9000 -p 9001:9001 --name minio \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  -d minio/minio server /data --console-address ":9001"
```

Access MinIO Console at http://localhost:9001 to create the `pm-desktop-files` bucket.

### 8. Start Meilisearch

#### Docker (Recommended)

```bash
docker run -p 7700:7700 --name meilisearch \
  -e MEILI_ENV=development \
  -e MEILI_MASTER_KEY=your-meilisearch-key \
  -d getmeili/meilisearch:v1.6
```

Access Meilisearch at http://localhost:7700 to verify it's running.

### 9. Start the Backend Server

```bash
cd fastapi-backend
uvicorn app.main:app --reload --port 8001
```

The API is now available at:
- **API**: http://localhost:8001
- **OpenAPI Docs**: http://localhost:8001/docs
- **WebSocket**: ws://localhost:8001/ws

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

### 2. Configure Environment

Create `electron-app/.env`:

```env
VITE_API_URL=http://localhost:8001
VITE_WS_URL=ws://localhost:8001/ws
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

1. Register a new user via the app
2. Or create via API:

```bash
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com", "password": "TestPassword123!", "display_name": "Developer"}'
```

## Common Commands

### Backend

```bash
# Run server with auto-reload
uvicorn app.main:app --reload --port 8001

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=app --cov-report=html

# Lint code
ruff check .

# Format code
ruff format .

# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
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
```

## Docker Compose (All Services)

For convenience, you can run all services with Docker Compose:

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: pmdbuser
      POSTGRES_PASSWORD: YourSecurePassword123!
      POSTGRES_DB: PMDB
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  meilisearch:
    image: getmeili/meilisearch:v1.6
    environment:
      MEILI_ENV: development
      MEILI_MASTER_KEY: your-meilisearch-key
    ports:
      - "7700:7700"
    volumes:
      - meilisearch_data:/meili_data

volumes:
  postgres_data:
  minio_data:
  meilisearch_data:
```

Start all services:
```bash
docker-compose up -d
```

## Troubleshooting

### PostgreSQL Connection Issues

1. Ensure PostgreSQL is running: `pg_isready -h localhost -p 5432`
2. Check firewall rules allow port 5432
3. Verify user credentials and database exist
4. Check `pg_hba.conf` for authentication settings

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli ping
# Expected: PONG
```

### MinIO Bucket Creation

If the bucket doesn't exist, create it:
1. Go to http://localhost:9001
2. Login with minioadmin/minioadmin
3. Create bucket named `pm-desktop-files`

### WebSocket Connection Fails

1. Check CORS configuration in `app/main.py`
2. Verify JWT token is valid
3. Check browser console for errors

### Alembic Migration Errors

```bash
# Check current migration status
alembic current

# View migration history
alembic history

# Stamp database (if tables exist but migration tracking is off)
alembic stamp head
```

## Next Steps

- Read [Architecture Overview](./architecture.md) to understand the system design
- Review [Backend Guide](./backend.md) for API development
- Check [Frontend Guide](./frontend.md) for UI development
