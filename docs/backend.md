# Backend Guide

The backend is built with FastAPI, a modern Python web framework with automatic OpenAPI documentation, async support, and excellent performance.

## Project Structure

```
fastapi-backend/
├── app/
│   ├── main.py              # Application entry point
│   ├── config.py            # Pydantic Settings
│   ├── database.py          # SQLAlchemy async engine (pool_size=50, max_overflow=100)
│   ├── models/              # 32 SQLAlchemy models
│   ├── schemas/             # 24 Pydantic schema files
│   ├── routers/             # 28 router files
│   ├── services/            # 20 service files
│   ├── ai/                  # 29 AI module files
│   │   ├── agent/           # LangGraph agent
│   │   │   ├── graph.py     # 7-node pipeline
│   │   │   ├── state.py     # TypedDict state
│   │   │   ├── constants.py # Runtime-configurable via getters
│   │   │   ├── prompts.py   # System prompts per node
│   │   │   ├── routing.py   # Intent classification
│   │   │   ├── nodes/       # 6 pipeline nodes
│   │   │   └── tools/       # 16 tool files (51 tools)
│   │   ├── providers/       # OpenAI, Anthropic, Ollama
│   │   ├── embedding_service.py
│   │   ├── chunking_service.py
│   │   ├── retrieval_service.py
│   │   ├── pdf_export.py
│   │   ├── excel_export.py
│   │   └── ...
│   ├── websocket/           # WebSocket handlers
│   ├── dependencies/        # DI + Redis gate
│   └── utils/               # Shared utilities
├── alembic/                 # Database migrations
│   ├── versions/            # Migration scripts
│   └── env.py               # Alembic configuration
├── tests/                   # Test suite (90+ files, 901+ tests)
└── pyproject.toml           # Python dependencies and tool config
```

## Application Entry Point

### main.py

The FastAPI application is configured in `app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Warm up DB pool, connect Redis, initialize WebSocket manager,
    #          start Redis pub/sub listener, start health monitor
    yield
    # Shutdown: Cleanup resources

app = FastAPI(
    title="PM Desktop API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers (28 total)
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(applications_router, prefix="/applications", tags=["applications"])
app.include_router(projects_router, prefix="/projects", tags=["projects"])
app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
# ... 24 more routers

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    # WebSocket connection handling
    pass

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### config.py

Environment configuration using Pydantic Settings:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database (PostgreSQL)
    db_server: str
    db_name: str
    db_user: str
    db_password: str
    db_port: int = 5432
    db_pool_size: int = 50
    db_max_overflow: int = 100

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    redis_socket_timeout: float = 5.0
    redis_retry_on_timeout: bool = True
    redis_required: bool = False

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool = False

    # Meilisearch
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_api_key: str = ""

    # WebSocket
    ws_max_connections_per_user: int = 50
    ws_max_message_size: int = 65536

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus
        return (
            f"postgresql+asyncpg://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_server}:{self.db_port}/{self.db_name}"
        )

settings = Settings()
```

## MinIO File Storage

PM Desktop uses MinIO for all file and image storage. Files are never stored in PostgreSQL — only metadata (bucket, key, size) is persisted in the `Attachments` table, while the binary content lives in MinIO.

### Buckets

| Bucket | Purpose | Routing Rule |
|--------|---------|-------------|
| `pm-images` | Image files (PNG, JPEG, GIF, WebP) | `content_type.startswith("image/")` |
| `pm-attachments` | All non-image files (PDF, DOCX, ZIP, etc.) | Everything else |

Buckets are created automatically on service initialization via `ensure_buckets_exist()` in `minio_service.py`. Creation is idempotent.

### Object Path Pattern

All objects follow the path structure:

```
{entity_type}/{entity_id}/{uuid8}_{filename}
```

- `entity_type` — one of: `task`, `comment`, `document`
- `entity_id` — UUID of the parent entity
- `uuid8` — first 8 characters of a `uuid4()` for uniqueness
- `filename` — original filename with `/` and `\` replaced by `_`

### Storage Paths by Operation

| Operation | Entity Type | Bucket | Example Path |
|-----------|-------------|--------|-------------|
| Task attachment upload | `task` | `pm-attachments` or `pm-images` | `task/{task_id}/a1b2c3d4_report.pdf` |
| Comment attachment upload | `comment` | `pm-attachments` or `pm-images` | `comment/{comment_id}/5f6e7d8c_screenshot.png` |
| Document editor image | `document` | `pm-images` | `document/{document_id}/9a8b7c6d_photo.jpg` |
| Draw.io diagram preview | `document` | `pm-images` | `document/{document_id}/e3f4a5b6_diagram.png` |

### Size Limits

| File Category | Max Size | Constant |
|---------------|----------|----------|
| General files | 100 MB (104,857,600 bytes) | `MAX_FILE_SIZE` |
| Image files | 10 MB (10,485,760 bytes) | `MAX_IMAGE_SIZE` |
| Draw.io diagram previews | 10 MB (10,485,760 bytes) | `MAX_DRAWIO_PNG_SIZE` (frontend) |

### Allowed Image MIME Types

Only these image types are accepted (others return `415`):

- `image/png`
- `image/jpeg`
- `image/gif`
- `image/webp`

### Presigned URL Expiry

| URL Type | Expiry | Constant |
|----------|--------|----------|
| Download URLs | 1 hour | `DEFAULT_URL_EXPIRY` |
| Upload URLs | 2 hours | `UPLOAD_URL_EXPIRY` |

Frontend caches download URLs with a 5-minute `staleTime` and 15-minute `gcTime` (URLs are never persisted to IndexedDB since they expire).

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/files/upload` | Upload file (multipart form) |
| `GET` | `/api/files` | List user's attachments |
| `GET` | `/api/files/{id}` | Get file metadata + download URL |
| `GET` | `/api/files/{id}/info` | Get metadata only |
| `GET` | `/api/files/{id}/download-url` | Generate fresh presigned URL |
| `POST` | `/api/files/download-urls` | Batch presigned URLs (max 50 IDs) |
| `PUT` | `/api/files/{id}` | Update attachment metadata |
| `DELETE` | `/api/files/{id}` | Delete file from MinIO + DB |
| `GET` | `/api/files/entity/{type}/{id}` | List attachments for an entity |

### Orphan Cleanup

Document attachments use content-aware orphan cleanup (not just CASCADE deletes):

1. `extract_attachment_ids()` walks the TipTap JSON tree and collects all `attachmentId` values from `image` and `drawio` nodes
2. `cleanup_orphaned_attachments()` runs on document save — compares DB attachment records against content references
3. Attachments not referenced in content AND older than the **5-minute grace period** (`CLEANUP_GRACE_PERIOD`) are deleted from both MinIO and the database
4. The grace period protects in-flight uploads that haven't been saved to content yet

Task and comment attachments rely on PostgreSQL CASCADE DELETE — when a task or comment is deleted, its attachment records are automatically removed.

### Error Responses

| Code | Scenario |
|------|----------|
| `400` | Missing filename or invalid request |
| `400` | Task is completed (cannot modify attachments) |
| `413` | File exceeds 100 MB limit |
| `413` | Image exceeds 10 MB limit |
| `415` | Unsupported image MIME type |
| `422` | Batch request exceeds 50 IDs |

## Database Layer

### database.py

SQLAlchemy async configuration with PostgreSQL connection pooling:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,      # 50 base connections
    max_overflow=settings.db_max_overflow,  # 100 additional when needed
    pool_timeout=60,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

# Dependency for database session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

## Models Layer (32 Models)

Models define the database schema using SQLAlchemy ORM.

### Model Organization

**Core Domain:**

| Model | File | Purpose |
|-------|------|---------|
| User | `models/user.py` | User accounts and profiles |
| Application | `models/application.py` | Top-level project containers |
| ApplicationMember | `models/application_member.py` | App role assignments |
| Project | `models/project.py` | Project boards |
| ProjectMember | `models/project_member.py` | Project role assignments |
| ProjectAssignment | `models/project_assignment.py` | Task assignments to projects |
| Task | `models/task.py` | Tasks/issues |
| TaskStatus | `models/task_status.py` | Status columns per project |
| ProjectTaskStatusAgg | `models/project_task_status_agg.py` | Denormalized status counts |

**Knowledge Base:**

| Model | File | Purpose |
|-------|------|---------|
| Document | `models/document.py` | Documents with `row_version`, `embedding_updated_at`, soft delete (`deleted_at`) |
| DocumentFolder | `models/document_folder.py` | Folder hierarchy |
| DocumentSnapshot | `models/document_snapshot.py` | Document version snapshots |
| DocumentTag | `models/document_tag.py` | Tag definitions |
| DocumentTagAssignment | `models/document_tag.py` | Tag-to-document assignments |
| DocumentChunk | `models/document_chunk.py` | Embedding vector chunks (pgvector) |
| FolderFile | `models/folder_file.py` | Files attached to folders |
| ImportJob | `models/import_job.py` | Document import job tracking |

**Collaboration:**

| Model | File | Purpose |
|-------|------|---------|
| Comment | `models/comment.py` | Task comments (threaded) |
| Mention | `models/mention.py` | @mention tracking |
| Attachment | `models/attachment.py` | File attachments |
| Checklist | `models/checklist.py` | Task checklists |
| ChecklistItem | `models/checklist_item.py` | Checklist items |

**AI Agent:**

| Model | File | Purpose |
|-------|------|---------|
| ChatSession | `models/chat_session.py` | Agent conversation sessions |
| ChatMessage | `models/chat_message.py` | Agent messages |
| AiProvider | `models/ai_provider.py` | Provider configs (encrypted API keys) |
| AiModel | `models/ai_model.py` | Model configurations |
| AiSystemPrompt | `models/ai_system_prompt.py` | System prompts |
| AgentConfiguration | `models/agent_config.py` | Runtime agent config (81 seed rows) |

**Other:**

| Model | File | Purpose |
|-------|------|---------|
| Notification | `models/notification.py` | User notifications |
| Invitation | `models/invitation.py` | App invitations |

### Example: Task Model

```python
# app/models/task.py
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime
import uuid

from app.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), default="story")  # story, bug, epic, subtask
    priority = Column(String(20), default="medium")
    task_rank = Column(String(255), nullable=True)   # Lexorank for ordering

    # Denormalized counts for performance
    checklist_total = Column(Integer, default=0)
    checklist_done = Column(Integer, default=0)

    # Foreign keys
    project_id = Column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    task_status_id = Column(PG_UUID(as_uuid=True), ForeignKey("task_statuses.id"), nullable=True)
    assignee_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reporter_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    parent_id = Column(PG_UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id])
    reporter = relationship("User", foreign_keys=[reporter_id])
    task_status = relationship("TaskStatus", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], back_populates="subtasks")
    subtasks = relationship("Task", back_populates="parent")
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    checklists = relationship("Checklist", back_populates="task", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="task", cascade="all, delete-orphan")
```

## Schemas Layer (24 Files)

Pydantic schemas define request/response validation and serialization.

### Schema Files

| File | Purpose |
|------|---------|
| `schemas/user.py` | User profiles |
| `schemas/application.py` | Application CRUD |
| `schemas/application_member.py` | Application membership |
| `schemas/project.py` | Project CRUD |
| `schemas/project_member.py` | Project membership |
| `schemas/project_assignment.py` | Project assignments |
| `schemas/task.py` | Task CRUD |
| `schemas/comment.py` | Comments |
| `schemas/checklist.py` | Checklists |
| `schemas/file.py` | File attachments |
| `schemas/document.py` | Document CRUD |
| `schemas/document_folder.py` | Folder hierarchy |
| `schemas/document_tag.py` | Document tags |
| `schemas/document_lock.py` | Document locks |
| `schemas/folder_file.py` | Folder files |
| `schemas/notification.py` | Notifications |
| `schemas/invitation.py` | Invitations |
| `schemas/dashboard.py` | Dashboard aggregations |
| `schemas/ai_chat.py` | AI chat requests/responses |
| `schemas/ai_config.py` | AI provider/model config |
| `schemas/oauth.py` | OAuth2 flows |
| `schemas/sql_query.py` | SQL query execution |
| `schemas/import_job.py` | Import jobs |

### Schema Conventions

| Category | Purpose | Example |
|----------|---------|---------|
| `*Create` | Request body for creating | `TaskCreate` |
| `*Update` | Request body for updating | `TaskUpdate` |
| `*Response` | Response serialization | `TaskResponse` |
| `*Base` | Shared fields | `TaskBase` |
| `*Query` | Query parameters | `TaskQuery` |

### Example: Task Schemas

```python
# app/schemas/task.py
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: str = Field(default="story")
    priority: str = Field(default="medium")

class TaskCreate(TaskBase):
    project_id: UUID
    task_status_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None
    parent_id: Optional[UUID] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: Optional[str] = None
    priority: Optional[str] = None
    task_status_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None
    task_rank: Optional[str] = None

class TaskResponse(TaskBase):
    id: UUID
    project_id: UUID
    task_status_id: Optional[UUID]
    assignee_id: Optional[UUID]
    reporter_id: UUID
    parent_id: Optional[UUID]
    task_rank: Optional[str]
    checklist_total: int
    checklist_done: int
    created_at: datetime
    updated_at: datetime

    # Nested objects (loaded via relationships)
    assignee: Optional["UserResponse"] = None
    reporter: Optional["UserResponse"] = None
    task_status: Optional["TaskStatusResponse"] = None

    class Config:
        from_attributes = True  # Enable ORM mode
```

## Routers Layer (28 Files)

Routers define API endpoints and route handling.

### Core Domain Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/auth` | Register, login, logout, password reset, 2FA, email verification |
| `applications.py` | `/applications` | Application CRUD |
| `application_members.py` | `/applications/{id}/members` | Application membership (roles) |
| `projects.py` | `/projects` | Project CRUD |
| `project_members.py` | `/projects/{id}/members` | Project membership and roles |
| `project_assignments.py` | `/project-assignments` | Task assignments to projects |
| `tasks.py` | `/tasks` | Task CRUD with status, priority, assignee |
| `comments.py` | `/comments` | Threaded comments with @-mentions |
| `checklists.py` | `/checklists` | Task checklists |
| `dashboard.py` | `/dashboard` | Dashboard aggregations |

### Knowledge Base Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `documents.py` | `/documents` | Document CRUD (includes trash, scopes-summary, permissions) |
| `document_folders.py` | `/document-folders` | Folder hierarchy (tree) |
| `document_tags.py` | `/document-tags` | Tag management |
| `document_locks.py` | `/document-locks` | Real-time locks (GET, POST, DELETE + batch) |
| `document_search.py` | `/document-search` | Meilisearch integration (search, health, reindex) |
| `folder_files.py` | `/folder-files` | Files in folders |

### Files and Users Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `files.py` | `/files` | File upload/download via MinIO |
| `users.py` | `/users` | User profiles |
| `invitations.py` | `/invitations` | User invitations |
| `notifications.py` | `/notifications` | Push notifications |

### AI Agent Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `ai_chat.py` | `/ai/chat` | Streaming chat, resume, time-travel/replay, cancel |
| `ai_config.py` | `/ai/config` | Provider/model configuration |
| `ai_oauth.py` | `/ai/oauth` | OAuth2 for external providers |
| `ai_query.py` | `/ai/query` | SQL generation and execution (query, validate, schema, export, index-status) |
| `ai_import.py` | `/ai/import` | Document import jobs |
| `chat_sessions.py` | `/chat-sessions` | Session management (CRUD + messages) |
| `admin_config.py` | `/admin/config` | Runtime agent config (GET, PUT, POST reset) |

### Example: Tasks Router

```python
# app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from app.services.auth_service import get_current_user
from app.services.permission_service import check_project_access
from app.websocket.handlers import handle_task_created, handle_task_updated

router = APIRouter()

@router.get("/{project_id}", response_model=List[TaskResponse])
async def get_tasks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all tasks for a project."""
    await check_project_access(db, project_id, current_user.id)

    result = await db.execute(
        select(Task)
        .filter(Task.project_id == project_id)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.task_status)
        )
        .order_by(Task.task_rank)
    )
    tasks = result.scalars().all()
    return tasks

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new task."""
    await check_project_access(db, task_data.project_id, current_user.id)

    task = Task(**task_data.dict(), reporter_id=current_user.id)
    db.add(task)
    await db.commit()
    await db.refresh(task)

    await handle_task_created(task)
    return task
```

## Services Layer (20 Files)

Services encapsulate business logic and cross-cutting concerns.

### Service Organization

**Core:**

| Service | File | Purpose |
|---------|------|---------|
| Auth | `services/auth_service.py` | JWT, 2FA, password hashing |
| Permission | `services/permission_service.py` | RBAC role hierarchy |
| User Cache | `services/user_cache_service.py` | User data caching |
| Notification | `services/notification_service.py` | Push notification delivery |
| Email | `services/email_service.py` | SMTP email delivery |

**Knowledge Base:**

| Service | File | Purpose |
|---------|------|---------|
| Document | `services/document_service.py` | Document CRUD business logic |
| Document Lock | `services/document_lock_service.py` | Redis-based document locking |
| Search | `services/search_service.py` | Meilisearch integration |

**Project and Task:**

| Service | File | Purpose |
|---------|------|---------|
| Status Derivation | `services/status_derivation_service.py` | Task status aggregation |
| Checklist | `services/checklist_service.py` | Checklist operations |
| Comment | `services/comment_service.py` | Comment operations |
| Task Helpers | `services/task_helpers.py` | Shared task utilities |

**Integration:**

| Service | File | Purpose |
|---------|------|---------|
| Redis | `services/redis_service.py` | Redis pub/sub and caching |
| MinIO | `services/minio_service.py` | S3 object storage |
| ARQ Helper | `services/arq_helper.py` | Background job processing |
| Dashboard | `services/dashboard_service.py` | Dashboard aggregation queries |
| Content Converter | `services/content_converter.py` | Content format conversion |
| Draw.io Graph | `services/drawio_graph_service.py` | Draw.io diagram processing |
| Archive | `services/archive_service.py` | Data archival |

### Authentication Service

```python
# app/services/auth_service.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency to get the current authenticated user."""
    payload = decode_token(token)
    user_id = payload.get("sub")
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

### Permission Service

```python
# app/services/permission_service.py
async def check_app_member(
    db: AsyncSession,
    application_id: UUID,
    user_id: UUID,
    required_role: str = None
) -> ApplicationMember:
    """Check if user is a member of the application."""
    # Role hierarchy: owner (3) > editor (2) > viewer (1)
    ...

async def check_project_access(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID
) -> bool:
    """Check if user has access to a project (via app membership)."""
    ...
```

## AI Module (29 Files)

The AI module implements the Blair AI Copilot, a LangGraph-based agent with 51 tools (25 read + 26 write), hybrid search, and document processing.

### LLM Providers

| File | Purpose |
|------|---------|
| `ai/provider_interface.py` | Abstract base for all providers |
| `ai/openai_provider.py` | OpenAI API integration |
| `ai/anthropic_provider.py` | Anthropic API integration |
| `ai/ollama_provider.py` | Ollama local model integration |
| `ai/provider_registry.py` | Provider selection and routing |
| `ai/codex_provider.py` | Legacy Codex provider |

### Embeddings and Search

| File | Purpose |
|------|---------|
| `ai/embedding_service.py` | Vector generation (tiktoken tokenizer) |
| `ai/chunking_service.py` | Document chunking (table/canvas/slide boundaries, oversized fallback) |
| `ai/retrieval_service.py` | Hybrid search (semantic + BM25 + pg_trgm, RRF fusion) |
| `ai/embedding_normalizer.py` | Cosine similarity normalization |

### Document Processing

| File | Purpose |
|------|---------|
| `ai/file_extraction_service.py` | PDF/DOCX/PPTX text extraction |
| `ai/docling_service.py` | Document conversion via Docling |
| `ai/spreadsheet_extractor.py` | Excel extraction (python-calamine) |
| `ai/visio_extractor.py` | Visio diagram extraction |
| `ai/image_understanding_service.py` | Image analysis via LLM |
| `ai/pdf_export.py` | PDF generation (fpdf2) |
| `ai/excel_export.py` | Excel export (openpyxl) |

### Agent Infrastructure

| File | Purpose |
|------|---------|
| `ai/config_service.py` | Runtime config (in-memory cache + Redis pub/sub invalidation) |
| `ai/rate_limiter.py` | Per-user rate limiting |
| `ai/oauth_service.py` | OAuth2 token management |
| `ai/encryption.py` | API key encryption |
| `ai/sql_generator.py` | SQL generation from natural language |
| `ai/sql_executor.py` | SQL execution (SET TRANSACTION READ ONLY, 6s timeout) |
| `ai/sql_validator.py` | SQL safety validation (blocks EXPLAIN, LOCK) |
| `ai/schema_context.py` | Scoped DB schema for LLM context |
| `ai/telemetry.py` | Token usage tracking |
| `ai/exceptions.py` | AI-specific exception classes |
| `ai/agent_tools.py` | Tool registration utilities |

### Agent Graph (7-Node LangGraph Pipeline)

| File | Purpose |
|------|---------|
| `ai/agent/graph.py` | Pipeline definition (MAX_TOOL_CALLS=50) |
| `ai/agent/state.py` | TypedDict state definition |
| `ai/agent/constants.py` | Runtime getters (NOT frozen imports) |
| `ai/agent/prompts.py` | Per-node system prompts |
| `ai/agent/routing.py` | Intent classification |
| `ai/agent/rbac_context.py` | RBAC context for tool execution |
| `ai/agent/source_references.py` | Source reference accumulation |
| `ai/agent/copilotkit_runtime.py` | Optional CopilotKit AG-UI mount |

### Agent Nodes (6 Pipeline Nodes)

| File | Purpose |
|------|---------|
| `ai/agent/nodes/intake.py` | Message intake, research reset on HITL resume |
| `ai/agent/nodes/understand.py` | Query understanding and classification |
| `ai/agent/nodes/clarify.py` | Clarification question generation |
| `ai/agent/nodes/explore.py` | Tool execution and data gathering |
| `ai/agent/nodes/synthesize.py` | Multi-source result synthesis |
| `ai/agent/nodes/respond.py` | Final response generation |

### Agent Tools (51 Total: 25 Read + 26 Write)

| File | Tools | Purpose |
|------|-------|---------|
| `ai/agent/tools/identity_tools.py` | Read | Current user identity |
| `ai/agent/tools/application_tools.py` | Read | Application queries |
| `ai/agent/tools/application_write_tools.py` | Write (HITL) | Application CRUD |
| `ai/agent/tools/member_write_tools.py` | Write (HITL) | Application member management |
| `ai/agent/tools/project_tools.py` | Read | Project queries |
| `ai/agent/tools/project_write_tools.py` | Write (HITL) | Project CRUD |
| `ai/agent/tools/project_member_write_tools.py` | Write (HITL) | Project member management |
| `ai/agent/tools/task_tools.py` | Read + Write | Task queries + update/delete/comment |
| `ai/agent/tools/checklist_write_tools.py` | Write (HITL) | Checklist management |
| `ai/agent/tools/knowledge_tools.py` | Read + Write | Document queries + update/delete, PDF export |
| `ai/agent/tools/web_tools.py` | Read | DuckDuckGo search + URL scrape (SSRF protection) |
| `ai/agent/tools/write_tools.py` | Shared | Write tool infrastructure |
| `ai/agent/tools/utility_tools.py` | Read | list_capabilities tool |
| `ai/agent/tools/helpers.py` | Shared | Tool helper functions |
| `ai/agent/tools/context.py` | Shared | Tool execution context |

All HITL (Human-in-the-Loop) write tools require RBAC hierarchy validation before execution.

## WebSocket Layer

### Files

| File | Purpose |
|------|---------|
| `websocket/manager.py` | WebSocket connection manager, MessageType enum, room management |
| `websocket/handlers.py` | Event routing and broadcast handlers |
| `websocket/presence.py` | Online presence tracking |
| `websocket/room_auth.py` | Room access authorization |

### Message Types

**Connection:**

| Type | Description |
|------|-------------|
| `connected` | Client connected |
| `disconnected` | Client disconnected |
| `error` | Error message |
| `ping` / `pong` | Keepalive |

**Room Management:**

| Type | Description |
|------|-------------|
| `join_room` | Join a room |
| `leave_room` | Leave a room |
| `room_joined` | Room join confirmed |
| `room_left` | Room leave confirmed |

**Task Events:**

| Type | Description |
|------|-------------|
| `task_created` | Task created |
| `task_updated` | Task updated |
| `task_deleted` | Task deleted |
| `task_status_changed` | Task status changed |
| `task_moved` | Task moved (DnD) |

**Comment Events:**

| Type | Description |
|------|-------------|
| `comment_added` | Comment created |
| `comment_updated` | Comment edited |
| `comment_deleted` | Comment removed |

**Checklist Events:**

| Type | Description |
|------|-------------|
| `checklist_created` | Checklist created |
| `checklist_updated` | Checklist updated |
| `checklist_deleted` | Checklist deleted |
| `checklists_reordered` | Checklists reordered |
| `checklist_item_toggled` | Item checked/unchecked |
| `checklist_item_added` | Item added |
| `checklist_item_updated` | Item updated |
| `checklist_item_deleted` | Item deleted |
| `checklist_items_reordered` | Items reordered |

**Attachment Events:**

| Type | Description |
|------|-------------|
| `attachment_uploaded` | File upload succeeded |
| `attachment_deleted` | File deleted |

**Presence Events:**

| Type | Description |
|------|-------------|
| `presence_update` | User presence changed |
| `user_presence` | User online/offline |
| `user_typing` | User typing indicator |
| `user_viewing` | User viewing entity |
| `task_viewers` | Active task viewers |

**Project Events:**

| Type | Description |
|------|-------------|
| `project_created` | Project created |
| `project_updated` | Project updated |
| `project_deleted` | Project deleted |
| `project_status_changed` | Project status changed |

**Application Events:**

| Type | Description |
|------|-------------|
| `application_created` | Application created |
| `application_updated` | Application updated |
| `application_deleted` | Application deleted |

**Membership Events:**

| Type | Description |
|------|-------------|
| `invitation_received` | Invitation sent |
| `invitation_response` | Invitation accepted/rejected |
| `member_added` | App member added |
| `member_removed` | App member removed |
| `role_updated` | App role changed |
| `project_member_added` | Project member added |
| `project_member_removed` | Project member removed |
| `project_role_changed` | Project role changed |

**Document Events:**

| Type | Description |
|------|-------------|
| `document_created` | Document created |
| `document_updated` | Document updated |
| `document_deleted` | Document deleted |
| `document_locked` | Document locked for editing |
| `document_unlocked` | Document lock released |
| `document_force_taken` | Document lock force-taken |
| `document_embedding_synced` | Embedding sync complete |

**Folder/File Events:**

| Type | Description |
|------|-------------|
| `folder_created` | Folder created |
| `folder_updated` | Folder updated |
| `folder_deleted` | Folder deleted |
| `file_uploaded` | File uploaded to folder |
| `file_updated` | File metadata updated |
| `file_deleted` | File deleted |
| `file_extraction_completed` | File text extraction done |
| `file_extraction_failed` | File text extraction failed |

**AI Events:**

| Type | Description |
|------|-------------|
| `embedding_updated` | Document embedding updated |
| `entities_extracted` | Entities extracted from document |
| `import_completed` | Document import finished |
| `import_failed` | Document import failed |
| `reindex_progress` | Meilisearch reindex progress |

**Infrastructure:**

| Type | Description |
|------|-------------|
| `notification` | Push notification |
| `notification_read` | Notification marked read |
| `redis_status_changed` | Redis connectivity changed |

## Dependencies Layer

| File | Purpose |
|------|---------|
| `dependencies/redis_gate.py` | `require_redis` dependency — gates endpoints that need Redis |

## Utilities Layer

| File | Purpose |
|------|---------|
| `utils/security.py` | Security utilities |
| `utils/tasks.py` | Task-related utilities |
| `utils/timezone.py` | Timezone helpers (`utc_now()`) |

## Dependencies (pyproject.toml)

### Core Framework

| Package | Purpose |
|---------|---------|
| `fastapi[standard]>=0.115.0` | Web framework |
| `uvicorn[standard]>=0.32.0` | ASGI server |
| `pydantic-settings>=2.4.0` | Settings management |
| `python-multipart>=0.0.17` | Form data parsing |
| `sse-starlette>=2.0.0` | Server-Sent Events (AI streaming) |

### Database

| Package | Purpose |
|---------|---------|
| `sqlalchemy>=2.0.0` | ORM |
| `asyncpg>=0.29.0` | PostgreSQL async driver |
| `greenlet>=3.0.0` | SQLAlchemy async support |
| `psycopg2-binary>=2.9.9` | PostgreSQL sync driver |
| `alembic>=1.14.0` | Database migrations |
| `pgvector>=0.3.0` | Vector similarity search |

### Authentication and Security

| Package | Purpose |
|---------|---------|
| `python-jose[cryptography]>=3.3.0` | JWT tokens |
| `passlib[bcrypt]>=1.7.4` | Password hashing |
| `cryptography>=42.0.0` | API key encryption |
| `defusedxml>=0.7.0` | XXE prevention |

### Storage and Search

| Package | Purpose |
|---------|---------|
| `minio>=7.2.0` | S3-compatible object storage |
| `redis[hiredis]>=5.0.0` | Cache, pub/sub, locks |
| `msgpack>=1.0.0` | Binary serialization |
| `meilisearch-python-sdk>=5.5` | Full-text search |

### AI Agent (LangGraph)

| Package | Purpose |
|---------|---------|
| `langgraph>=1.0.0,<2.0.0` | Agent pipeline framework |
| `langgraph-checkpoint-postgres>=3.0.0,<4.0.0` | Persistent checkpoints |
| `psycopg[binary]>=3.1.0,<4.0.0` | Checkpoint driver |
| `langchain-core>=1.0.0,<2.0.0` | LangChain core abstractions |
| `langchain-openai>=1.0.0,<2.0.0` | OpenAI LangChain integration |
| `langchain-anthropic>=1.0.0,<2.0.0` | Anthropic LangChain integration |
| `tiktoken>=0.7.0` | Token counting |
| `sqlglot>=25.0.0` | SQL parsing and validation |

### AI Providers

| Package | Purpose |
|---------|---------|
| `openai>=1.30.0` | OpenAI API client |
| `anthropic>=0.40.0` | Anthropic API client |

### Document Processing

| Package | Purpose |
|---------|---------|
| `docling>=2.0.0,<3.0.0` | PDF/DOCX/PPTX conversion |
| `python-calamine>=0.6.0,<1.0.0` | Excel extraction (calamine) |
| `chardet>=5.0.0,<6.0.0` | Character encoding detection |
| `vsdx>=0.5.0,<1.0.0` | Visio file extraction |
| `python-magic-bin>=0.4.14` | MIME type detection |

### Export

| Package | Purpose |
|---------|---------|
| `fpdf2>=2.8.0,<3.0.0` | PDF generation |
| `openpyxl>=3.1.0` | Excel export |

### Web Tools

| Package | Purpose |
|---------|---------|
| `duckduckgo-search>=7.0.0,<8.0.0` | Web search |
| `trafilatura>=2.0.0,<3.0.0` | Web page content extraction |

### Background Jobs

| Package | Purpose |
|---------|---------|
| `arq>=0.26.0` | Redis-based job queue |

### Email

| Package | Purpose |
|---------|---------|
| `aiosmtplib>=3.0.0` | Async SMTP |

### Real-time

| Package | Purpose |
|---------|---------|
| `websockets>=13.0` | WebSocket protocol |

### Testing

| Package | Purpose |
|---------|---------|
| `pytest>=8.3.0` | Test framework |
| `pytest-asyncio>=0.24.0` | Async test support |
| `httpx>=0.27.0` | Async HTTP test client |

## Error Handling

### HTTP Exceptions

```python
from fastapi import HTTPException, status

# 400 Bad Request
raise HTTPException(status_code=400, detail="Invalid input")

# 401 Unauthorized
raise HTTPException(status_code=401, detail="Not authenticated")

# 403 Forbidden
raise HTTPException(status_code=403, detail="Not authorized")

# 404 Not Found
raise HTTPException(status_code=404, detail="Resource not found")

# 409 Conflict
raise HTTPException(status_code=409, detail="Resource already exists")

# 422 Validation Error (automatic from Pydantic)

# 500 Internal Server Error (unhandled exceptions)
```

### Custom Exception Handler

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

## Testing

### Overview

- Framework: pytest with pytest-asyncio
- Coverage target: 80%
- Test count: 901+ passing tests
- Test files: 90+ files in `fastapi-backend/tests/`
- Includes: unit tests, integration tests, load tests (Locust)

### Test Structure

```
tests/
├── conftest.py                      # Shared fixtures
├── load/                            # Load testing (Locust)
│   ├── locustfile.py
│   ├── locustfile_api_only.py
│   └── locustfile_shared_token.py
├── test_auth.py                     # Authentication
├── test_login_2fa.py                # 2FA login
├── test_password_reset.py           # Password reset
├── test_email_verification.py       # Email verification
├── test_email_service.py            # SMTP service
├── test_applications.py             # Application CRUD
├── test_projects.py                 # Project CRUD
├── test_tasks.py                    # Task CRUD
├── test_permissions.py              # RBAC
├── test_dashboard.py                # Dashboard
├── test_notifications.py            # Notifications
├── test_files.py                    # File upload/download
├── test_minio.py                    # MinIO integration
├── test_document_routes.py          # Document CRUD
├── test_document_service.py         # Document service
├── test_document_lock_service.py    # Document locking
├── test_folder_files_api.py         # Folder files API
├── test_folder_file_model.py        # Folder file model
├── test_file_search.py              # File search
├── test_status_derivation.py        # Status aggregation
├── test_content_converter.py        # Content conversion
├── test_markdown_converter.py       # Markdown conversion
├── test_user_cache.py               # User cache
├── test_presence_manager.py         # Presence tracking
├── test_websocket.py                # WebSocket
├── test_room_auth.py                # Room authorization
├── test_refresh_ws_tokens.py        # WS token refresh
├── test_subscription_token.py       # Subscription tokens
├── test_redis_health_gate.py        # Redis gate
├── test_ai_providers.py             # AI provider integration
├── test_ai_config_router.py         # AI config API
├── test_ai_config_panel.py          # AI config panel (14 tests)
├── test_ai_chat_helpers.py          # AI chat helpers
├── test_ai_query_router.py          # SQL query API
├── test_health_ai.py                # AI health checks
├── test_agent_graph.py              # Agent pipeline
├── test_agent_chat.py               # Agent chat
├── test_agent_config_service.py     # Agent config service
├── test_agent_rbac.py               # Agent RBAC
├── test_agent_tools.py              # Agent tools
├── test_agent_tools_read.py         # Read tools
├── test_agent_tools_write.py        # Write tools
├── test_application_write_tools.py  # Application write tools
├── test_member_write_tools.py       # Member write tools
├── test_project_write_tools.py      # Project write tools
├── test_project_member_write_tools.py # Project member write tools
├── test_checklist_write_tools.py    # Checklist write tools
├── test_document_write_tools.py     # Document write tools
├── test_task_write_tools_expanded.py # Task write tools
├── test_web_tools.py                # Web search/scrape
├── test_capabilities_tool.py        # Capabilities listing
├── test_tools_helpers.py            # Tool helpers
├── test_intake_node.py              # Intake node
├── test_understand_node.py          # Understand node
├── test_clarify_node.py             # Clarify node
├── test_explore_node.py             # Explore node
├── test_explore_tools_node.py       # Explore tools
├── test_synthesize_node.py          # Synthesize node
├── test_respond_node.py             # Respond node
├── test_routing.py                  # Intent routing
├── test_system_prompt.py            # System prompts
├── test_pipeline_integration.py     # Pipeline integration
├── test_context_management.py       # Context management
├── test_context_summarization.py    # Context summarization
├── test_embedding_service.py        # Embedding generation
├── test_embedding_normalizer.py     # Embedding normalization
├── test_retrieval_service.py        # Hybrid search
├── test_chunking.py                 # Document chunking
├── test_file_chunking.py            # File chunking
├── test_file_extraction.py          # File extraction
├── test_file_extraction_worker.py   # Extraction worker
├── test_docling_service.py          # Docling
├── test_image_understanding.py      # Image understanding
├── test_import_router.py            # Import API
├── test_process_import.py           # Import processing
├── test_codex_provider.py           # Codex provider
├── test_oauth_service.py            # OAuth service
├── test_schema_context.py           # Schema context
├── test_sql_generator.py            # SQL generation
├── test_sql_executor.py             # SQL execution
├── test_sql_validator.py            # SQL validation
├── test_rate_limiter.py             # Rate limiting
├── test_telemetry.py                # Telemetry
├── test_excel_export.py             # Excel export
├── test_arq_worker.py               # ARQ worker
├── test_arq_multiworker.py          # Multi-worker
├── test_phase9_cost_safety.py       # Cost/safety controls (42 tests)
└── test_phase9_embedding_quality.py # Embedding quality (34 tests)
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=app --cov-report=html

# Run specific test file
uv run pytest tests/test_tasks.py -v

# Run specific test
uv run pytest tests/test_tasks.py::test_create_task -v
```

## Best Practices

### 1. Use Dependency Injection

```python
# Good: Dependencies injected
@router.get("/tasks/{id}")
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pass

# Bad: Creating dependencies inside function
@router.get("/tasks/{id}")
async def get_task(task_id: UUID):
    db = AsyncSessionLocal()  # Don't do this
    pass
```

### 2. Use Eager Loading

```python
# Good: Load related objects in one query
result = await db.execute(
    select(Task)
    .options(
        selectinload(Task.assignee),
        selectinload(Task.comments)
    )
    .filter(Task.project_id == project_id)
)
tasks = result.scalars().all()

# Bad: N+1 query problem
result = await db.execute(select(Task).filter(Task.project_id == project_id))
tasks = result.scalars().all()
for task in tasks:
    print(task.assignee.name)  # Extra query for each task
```

### 3. Use Pydantic for Validation

```python
# Good: Pydantic validates automatically
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")

# Bad: Manual validation
@router.post("/tasks/")
async def create_task(data: dict):
    if not data.get("title"):  # Don't do this
        raise HTTPException(status_code=400, detail="Title required")
```

### 4. Handle Errors Consistently

```python
# Good: Consistent error responses
if not task:
    raise HTTPException(status_code=404, detail="Task not found")

# Bad: Inconsistent error handling
if not task:
    return {"error": "not found"}  # Don't do this
```

### 5. Use Transactions

```python
# Good: Use transactions for multiple operations
try:
    task = Task(**data)
    db.add(task)

    notification = Notification(...)
    db.add(notification)

    await db.commit()
except Exception:
    await db.rollback()
    raise
```

### 6. Runtime Agent Constants (Blair AI)

```python
# Good: Runtime getter called at execution time
from app.ai.agent.constants import get_max_tool_calls

max_calls = get_max_tool_calls()  # Reads from config_service

# Bad: Frozen at import time
from app.ai.agent.constants import MAX_TOOL_CALLS  # Freezes value at import
```
