# Backend Guide

The backend is built with FastAPI, a modern Python web framework with automatic OpenAPI documentation, async support, and excellent performance.

## Project Structure

```
fastapi-backend/
├── app/
│   ├── main.py              # Application entry point
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy setup
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # API endpoint definitions
│   ├── services/            # Business logic layer
│   ├── websocket/           # WebSocket handlers
│   └── worker.py            # ARQ background job worker
├── alembic/                 # Database migrations
│   ├── versions/            # Migration scripts
│   └── env.py               # Alembic configuration
├── tests/                   # Test suite
└── requirements.txt         # Python dependencies
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
    # Startup: Initialize presence manager, connections
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

# Include all routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(applications.router, prefix="/applications", tags=["applications"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
# ... more routers

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
    pool_timeout=15,                      # Fail fast (15s timeout)
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

# Dependency for database session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

## Models Layer

Models define the database schema using SQLAlchemy ORM.

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

### Model Organization

| Model | File | Purpose |
|-------|------|---------|
| User | `models/user.py` | User accounts and profiles |
| Application | `models/application.py` | Top-level project containers |
| ApplicationMember | `models/application_member.py` | App role assignments |
| Project | `models/project.py` | Project boards |
| ProjectMember | `models/project_member.py` | Project role assignments |
| Task | `models/task.py` | Tasks/issues |
| TaskStatus | `models/task_status.py` | Status columns per project |
| Comment | `models/comment.py` | Task comments |
| Mention | `models/mention.py` | @mention tracking |
| Checklist | `models/checklist.py` | Task checklists |
| ChecklistItem | `models/checklist_item.py` | Checklist items |
| Attachment | `models/attachment.py` | File attachments |
| Notification | `models/notification.py` | User notifications |
| Invitation | `models/invitation.py` | App invitations |
| DocumentFolder | `models/document_folder.py` | Knowledge base folder hierarchy |
| Document | `models/document.py` | Knowledge base documents |
| DocumentSnapshot | `models/document_snapshot.py` | Document version snapshots (placeholder) |
| DocumentTag | `models/document_tag.py` | Custom tags for documents |
| DocumentTagAssignment | `models/document_tag_assignment.py` | Document-to-tag associations |
| ProjectAssignment | `models/project_assignment.py` | User work assignments to projects |
| ProjectTaskStatusAgg | `models/project_task_status_agg.py` | Aggregated task status counts per project |

## Schemas Layer

Pydantic schemas define request/response validation and serialization.

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

### Schema Categories

| Category | Purpose | Example |
|----------|---------|---------|
| `*Create` | Request body for creating | `TaskCreate` |
| `*Update` | Request body for updating | `TaskUpdate` |
| `*Response` | Response serialization | `TaskResponse` |
| `*Base` | Shared fields | `TaskBase` |
| `*Query` | Query parameters | `TaskQuery` |

## Routers Layer

Routers define API endpoints and route handling.

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
    # Check user has access to project
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
    # Check user has access to project
    await check_project_access(db, task_data.project_id, current_user.id)

    # Create task
    task = Task(
        **task_data.dict(),
        reporter_id=current_user.id
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Broadcast via WebSocket
    await handle_task_created(task)

    return task

@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task_data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing task."""
    result = await db.execute(select(Task).filter(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check user has access
    await check_project_access(db, task.project_id, current_user.id)

    # Update fields
    for field, value in task_data.dict(exclude_unset=True).items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)

    # Broadcast via WebSocket
    await handle_task_updated(task)

    return task

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a task."""
    result = await db.execute(select(Task).filter(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check user has access
    await check_project_access(db, task.project_id, current_user.id)

    project_id = task.project_id
    await db.delete(task)
    await db.commit()

    # Broadcast via WebSocket
    await handle_task_deleted(task_id, project_id)
```

### Available Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/auth` | Login, register, logout, current user |
| `applications.py` | `/api/applications` | Application CRUD |
| `application_members.py` | `/api/applications/{id}/members` | App membership |
| `projects.py` | `/api/projects` | Project CRUD and status override |
| `project_members.py` | `/api/projects/{id}/members` | Project membership |
| `project_assignments.py` | `/api/projects/{id}/assignments` | Work assignments |
| `tasks.py` | `/api/tasks` | Task CRUD, Kanban operations, archiving |
| `comments.py` | `/api/comments` | Comment threads with @mentions |
| `checklists.py` | `/api/checklists` | Checklist and item management |
| `files.py` | `/api/files` | File upload/download via MinIO |
| `notifications.py` | `/api/notifications` | User notifications |
| `invitations.py` | `/api/invitations` | App invitations |
| `users.py` | `/api/users` | User search/lookup |
| `documents.py` | `/api` | Knowledge base document CRUD |
| `document_folders.py` | `/api` | Folder hierarchy management |
| `document_tags.py` | `/api` | Document tag management |
| `document_locks.py` | `/document-locks` | Document lock acquire/release |
| `document_search.py` | `/document-search` | Full-text search via Meilisearch |

## Services Layer

Services encapsulate business logic and cross-cutting concerns.

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
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)

def create_access_token(user_id: str, email: str) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

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
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.application_member import ApplicationMember
from app.models.project_member import ProjectMember

async def check_app_member(
    db: AsyncSession,
    application_id: UUID,
    user_id: UUID,
    required_role: str = None
) -> ApplicationMember:
    """Check if user is a member of the application."""
    result = await db.execute(
        select(ApplicationMember).filter(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this application"
        )

    if required_role:
        role_hierarchy = {"owner": 3, "editor": 2, "viewer": 1}
        if role_hierarchy.get(member.role, 0) < role_hierarchy.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role or higher"
            )

    return member

async def check_project_access(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID
) -> bool:
    """Check if user has access to a project."""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.application))
        .filter(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check app membership
    await check_app_member(db, project.application_id, user_id)

    return True
```

### Status Derivation Service

```python
# app/services/status_derivation_service.py
# ProjectTaskStatusAgg uses a single row per project with category-based counters:
#   total_tasks, todo_tasks, active_tasks, review_tasks, issue_tasks, done_tasks
# Counters are updated incrementally when tasks change status.

async def derive_project_status(db: AsyncSession, project_id: UUID) -> str:
    """Derive overall project status from task aggregation counters."""
    result = await db.execute(select(Project).filter(Project.id == project_id))
    project = result.scalar_one_or_none()

    # Check for manual override (with expiration)
    if project.override_status_id and project.override_expires_at:
        if project.override_expires_at > datetime.utcnow():
            return project.override_status_id

    # Read pre-computed aggregation (single row per project)
    agg = await db.execute(
        select(ProjectTaskStatusAgg)
        .filter(ProjectTaskStatusAgg.project_id == project_id)
    )
    # Derive status from category counts (todo, active, review, issue, done)
    # Logic uses category-based rules to determine overall project health
    pass
```

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
    # Log the error
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Return generic error to client
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

## Testing

### Test Structure

```
tests/
├── conftest.py                # Shared fixtures (test DB, auth, sample data)
├── test_auth.py               # Authentication and user creation
├── test_applications.py       # Application CRUD and members
├── test_projects.py           # Project CRUD, status derivation, archiving
├── test_tasks.py              # Task CRUD, subtasks, status moves, archiving
├── test_permissions.py        # Role-based access control
├── test_files.py              # MinIO file upload/download
├── test_minio.py              # MinIO service integration
├── test_websocket.py          # WebSocket connections and message routing
├── test_notifications.py      # Notification creation and delivery
├── test_comments.py           # Comment CRUD with mentions
├── test_content_converter.py  # TipTap JSON to Markdown/plain text
├── test_status_derivation.py  # Project status from task aggregations
├── test_user_cache.py         # Role caching and invalidation
├── test_arq_worker.py         # Background job scheduling
├── test_arq_multiworker.py    # Multi-worker Redis pub/sub
└── load/                      # Load testing utilities
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.config import settings
from app.database import Base, get_db

# Test database (PostgreSQL)
TEST_DATABASE_URL = settings.test_database_url
engine = create_async_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture(scope="function")
async def db():
    """Create a fresh database for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
def client(db):
    """Create a test client with database override."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
async def test_user(db):
    """Create a test user."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("testpass"),
        display_name="Test User"
    )
    db.add(user)
    await db.commit()
    return user

@pytest.fixture
def auth_headers(client, test_user):
    """Get authentication headers for test user."""
    response = client.post("/auth/login", data={
        "username": test_user.email,
        "password": "testpass"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

### Example Tests

```python
# tests/test_tasks.py
def test_create_task(client, auth_headers, test_project):
    """Test creating a new task."""
    response = client.post(
        "/tasks/",
        json={
            "title": "Test Task",
            "project_id": str(test_project.id),
            "task_type": "story"
        },
        headers=auth_headers
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Task"
    assert data["task_type"] == "story"

def test_get_tasks(client, auth_headers, test_project, test_task):
    """Test getting tasks for a project."""
    response = client.get(
        f"/tasks/{test_project.id}",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(test_task.id)

def test_unauthorized_access(client, test_project):
    """Test that unauthenticated requests are rejected."""
    response = client.get(f"/tasks/{test_project.id}")
    assert response.status_code == 401
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_tasks.py -v

# Run specific test
pytest tests/test_tasks.py::test_create_task -v
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
