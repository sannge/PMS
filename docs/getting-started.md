# Getting Started

This guide covers setting up your development environment and running PM Desktop locally.

## System Requirements

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.12+ | Backend runtime |
| Node.js | 20 LTS+ | Frontend tooling |
| npm | 10+ | Package management |
| Microsoft SQL Server | 2019+ | Primary database |
| Redis | 7+ | Caching and pub/sub |
| MinIO | Latest | File storage |
| Git | 2.40+ | Version control |

### Optional Software

| Software | Version | Purpose |
|----------|---------|---------|
| Meilisearch | 1.6+ | Full-text search |
| Docker | 24+ | Container runtime for services |

### Recommended Development Tools

- **VS Code** or **PyCharm** - IDE with Python/TypeScript support
- **SQL Server Management Studio** or **Azure Data Studio** - Database management
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
- `pyodbc` - SQL Server driver
- `python-jose` - JWT handling
- `passlib` - Password hashing
- `redis` - Redis client
- `minio` - MinIO client
- `pytest` - Testing framework

### 3. Configure Environment Variables

Create `fastapi-backend/.env`:

```env
# Database (SQL Server)
DB_SERVER=localhost
DB_NAME=pm_desktop
DB_USER=sa
DB_PASSWORD=YourSecurePassword123!
DB_DRIVER=ODBC Driver 18 for SQL Server

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
MINIO_BUCKET=pm-desktop-files
MINIO_SECURE=false

# Meilisearch (Optional)
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_API_KEY=your-meilisearch-key

# WebSocket Settings
WS_MAX_CONNECTIONS_PER_USER=50
WS_MAX_MESSAGE_SIZE=65536
WS_PING_INTERVAL=30
WS_TOKEN_REVALIDATION_INTERVAL=1800
```

### 4. Set Up SQL Server Database

#### Option A: Local SQL Server

1. Install SQL Server 2019+ (Developer Edition is free)
2. Create database:

```sql
CREATE DATABASE pm_desktop;
GO
```

#### Option B: Docker

```bash
docker run -e "ACCEPT_EULA=Y" -e "SA_PASSWORD=YourSecurePassword123!" \
  -p 1433:1433 --name sqlserver \
  -d mcr.microsoft.com/mssql/server:2022-latest
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

### 8. Start the Backend Server

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
  sqlserver:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      ACCEPT_EULA: Y
      SA_PASSWORD: YourSecurePassword123!
    ports:
      - "1433:1433"
    volumes:
      - sqlserver_data:/var/opt/mssql

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
  sqlserver_data:
  minio_data:
  meilisearch_data:
```

Start all services:
```bash
docker-compose up -d
```

## Troubleshooting

### SQL Server Connection Issues

1. Ensure SQL Server is running and accepting TCP connections
2. Check firewall rules allow port 1433
3. Verify ODBC driver is installed:
   - Windows: SQL Server Native Client or ODBC Driver 18
   - macOS: `brew install microsoft/mssql-release/msodbcsql18`
   - Linux: Follow [Microsoft's guide](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)

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
- Learn about [Real-Time Communication](./websocket.md) for WebSocket features
