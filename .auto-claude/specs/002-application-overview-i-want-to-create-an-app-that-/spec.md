# Specification: Desktop Jira Clone with OneNote Integration

## Overview

Build a production-ready **desktop project management application** that combines Jira's advanced project management capabilities with OneNote-style note-taking features. The application introduces a novel hierarchical structure: **Application > Projects > Tasks**, allowing users to organize multiple projects under a single application umbrella. Key features include real-time collaboration via WebSockets, rich note-taking with multi-tab support, document/image uploads to MinIO object storage, notification system, and comprehensive project management tools (roadmaps, sprints, issue tracking). The application is built with Electron + React for the desktop frontend and Python FastAPI for the backend.

## Workflow Type

**Type**: feature

**Rationale**: This is a complete greenfield application build requiring multiple interconnected features, new database schema design, frontend/backend architecture setup, and comprehensive testing infrastructure. The feature workflow is appropriate for this multi-phase, iterative development approach.

## Task Scope

### Services Involved
- **electron-app** (primary) - Desktop frontend application with React, ShadCN UI, and Tailwind CSS
- **fastapi-backend** (primary) - Python REST API and WebSocket server
- **sql-server** (integration) - External SQL Server database (10.18.138.240)
- **minio-storage** (integration) - External MinIO object storage (API: 10.18.136.10:9000, Console: 10.18.136.10:9001)

### This Task Will:
- [ ] Set up Electron + React project structure with proper IPC communication
- [ ] Initialize ShadCN UI component library with Tailwind CSS
- [ ] Create FastAPI backend with REST endpoints and WebSocket support
- [ ] Design and implement SQL Server database schema (Applications, Projects, Tasks, Notes, Users)
- [ ] Implement authentication and multi-user support
- [ ] Build Application/Project/Task CRUD operations with hierarchical management
- [ ] Create note-taking system with multi-tab interface, rich text editing
- [ ] Implement file upload/download to MinIO (documents, images, recordings)
- [ ] Build real-time collaboration via WebSockets with conflict resolution
- [ ] Create notification system for updates and alerts
- [ ] Implement comprehensive Playwright E2E tests for all features

### Out of Scope:
- Graph DB / Vector DB integration for LLM knowledge base (deferred for future)
- AI-powered features leveraging note content
- Web deployment (desktop-only)
- Mobile applications
- Code signing and distribution packaging (initial phase)

## Service Context

### electron-app (Frontend)

**Tech Stack:**
- Language: TypeScript
- Framework: Electron 30.x + React 18.x
- UI Library: ShadCN UI + Tailwind CSS 3.x
- Build Tool: electron-vite
- Packaging: electron-builder

**Key Directories:**
```
/electron-app
├── src/
│   ├── main/           # Electron main process
│   │   ├── index.ts    # Main entry point
│   │   └── ipc/        # IPC handlers
│   ├── preload/        # Preload scripts (contextBridge)
│   │   └── index.ts
│   └── renderer/       # React application
│       ├── App.tsx
│       ├── components/
│       │   └── ui/     # ShadCN components
│       ├── pages/
│       ├── hooks/
│       ├── stores/     # State management
│       └── lib/
├── public/
├── electron-builder.json
├── tailwind.config.js
├── components.json     # ShadCN config
└── package.json
```

**Entry Point:** `src/main/index.ts`

**How to Run:**
```bash
cd electron-app
npm install
npm run dev
```

**Port:** N/A (Desktop application)

---

### fastapi-backend (Backend)

**Tech Stack:**
- Language: Python 3.11+
- Framework: FastAPI 0.115.x
- ASGI Server: uvicorn[standard]
- Database: SQL Server via pyodbc / aioodbc
- Object Storage: MinIO SDK (minio)
- WebSockets: Built-in FastAPI support + websockets package
- Additional Required Packages:
  - python-multipart (required for file uploads)
  - pydantic-settings (environment variable management)
  - alembic (database migrations)
  - websockets (WebSocket support)

**Key Directories:**
```
/fastapi-backend
├── app/
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Configuration
│   ├── database.py          # Database connection
│   ├── models/              # SQLAlchemy models
│   │   ├── user.py
│   │   ├── application.py
│   │   ├── project.py
│   │   ├── task.py
│   │   └── note.py
│   ├── schemas/             # Pydantic schemas
│   ├── routers/             # API routes
│   │   ├── auth.py
│   │   ├── applications.py
│   │   ├── projects.py
│   │   ├── tasks.py
│   │   ├── notes.py
│   │   ├── files.py
│   │   └── notifications.py
│   ├── services/            # Business logic
│   ├── websocket/           # WebSocket handlers
│   │   ├── manager.py       # Connection manager
│   │   └── handlers.py
│   └── utils/
├── tests/
├── requirements.txt
└── .env
```

**Entry Point:** `app/main.py`

**How to Run:**
```bash
cd fastapi-backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Port:** 8000

---

### External Infrastructure

**SQL Server Database:**
- Server: 10.18.138.240
- Database: PMDB
- Username: pmdbuser
- Password: never!again

**MinIO Object Storage:**
- API Endpoint: 10.18.136.10:9000 (for SDK connections)
- Console URL: 10.18.136.10:9001 (web interface)
- Access Key: minioadmin
- Secret Key: Windows2

## Files to Create

Since this is a greenfield project, all files need to be created:

### Electron Frontend

| File | Purpose |
|------|---------|
| `electron-app/package.json` | Project dependencies and scripts |
| `electron-app/electron-builder.json` | Electron packaging configuration |
| `electron-app/tailwind.config.js` | Tailwind CSS configuration |
| `electron-app/postcss.config.js` | PostCSS configuration for Tailwind |
| `electron-app/tsconfig.json` | TypeScript configuration with path aliases |
| `electron-app/components.json` | ShadCN UI configuration |
| `electron-app/vite.config.ts` | Vite build configuration |
| `electron-app/src/main/index.ts` | Electron main process entry |
| `electron-app/src/preload/index.ts` | Preload script with contextBridge |
| `electron-app/src/renderer/index.html` | HTML entry point |
| `electron-app/src/renderer/main.tsx` | React entry with createRoot |
| `electron-app/src/renderer/App.tsx` | Root React component |
| `electron-app/src/renderer/globals.css` | Global styles with Tailwind directives |

### FastAPI Backend

| File | Purpose |
|------|---------|
| `fastapi-backend/requirements.txt` | Python dependencies |
| `fastapi-backend/.env` | Environment variables |
| `fastapi-backend/app/main.py` | FastAPI application setup |
| `fastapi-backend/app/config.py` | Configuration management |
| `fastapi-backend/app/database.py` | SQL Server connection setup |
| `fastapi-backend/app/models/*.py` | SQLAlchemy ORM models |
| `fastapi-backend/app/schemas/*.py` | Pydantic request/response schemas |
| `fastapi-backend/app/routers/*.py` | API endpoint routers |
| `fastapi-backend/app/websocket/manager.py` | WebSocket connection manager |
| `fastapi-backend/app/services/minio_service.py` | MinIO integration service |

### Testing

| File | Purpose |
|------|---------|
| `tests/playwright.config.ts` | Playwright configuration |
| `tests/e2e/*.spec.ts` | End-to-end test files |

## Files to Reference

These external resources demonstrate patterns to follow:

| Reference | Pattern to Copy |
|-----------|----------------|
| Jira UI/UX | Board views, issue detail panels, navigation structure |
| OneNote | Tab-based note organization, rich text editing interface |
| ShadCN UI documentation | Component usage patterns, theming |
| FastAPI documentation | WebSocket patterns, dependency injection |

## Patterns to Follow

### Pattern 1: Electron IPC Communication (Secure)

**Main Process Handler (main/ipc/handlers.ts):**
```typescript
import { ipcMain } from 'electron';

// Register IPC handlers
ipcMain.handle('api:fetch', async (event, { endpoint, options }) => {
  const response = await fetch(`http://localhost:8000${endpoint}`, options);
  return response.json();
});

ipcMain.handle('storage:upload', async (event, { file, bucket }) => {
  // Handle file upload via backend
});
```

**Preload Script (preload/index.ts):**
```typescript
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  fetch: (endpoint: string, options?: RequestInit) =>
    ipcRenderer.invoke('api:fetch', { endpoint, options }),
  uploadFile: (file: File, bucket: string) =>
    ipcRenderer.invoke('storage:upload', { file, bucket }),
});
```

**Key Points:**
- Always use `contextBridge` - never expose Node.js APIs directly
- `contextIsolation: true` is mandatory for security
- All IPC communication goes through defined channels

---

### Pattern 2: FastAPI WebSocket Connection Manager

**websocket/manager.py:**
```python
from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)

    async def broadcast(self, room_id: str, message: dict, exclude: WebSocket = None):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                if connection != exclude:
                    await connection.send_json(message)

manager = ConnectionManager()
```

**Key Points:**
- Room-based connections for collaborative editing
- Broadcast functionality for real-time updates
- Proper disconnect handling to prevent memory leaks

---

### Pattern 3: ShadCN Component Usage

**Example Button with Loading State:**
```tsx
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

function SubmitButton({ isLoading, children }: Props) {
  return (
    <Button disabled={isLoading}>
      {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      {children}
    </Button>
  );
}
```

**Key Points:**
- Components live in `src/components/ui/`
- Use path alias `@/components` for imports
- Add components via CLI: `npx shadcn@latest add button`

---

### Pattern 4: SQL Server with SQLAlchemy

**database.py:**
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# SQL Server connection string
DATABASE_URL = (
    f"mssql+pyodbc://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_SERVER}/{settings.DB_NAME}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Key Points:**
- Use `pyodbc` driver for SQL Server
- Dependency injection for database sessions
- Proper connection cleanup

---

### Pattern 5: FastAPI CORS Middleware

**main.py:**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PM API", version="1.0.0")

# CORS Middleware - required for Electron app requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Key Points:**
- CORS middleware must be added explicitly for cross-origin requests
- Electron renderer makes requests from `file://` or localhost origin
- Configure `allow_origins` appropriately for production security

## Requirements

### Functional Requirements

1. **User Authentication & Authorization**
   - Description: Users can register, login, and manage sessions. JWT-based authentication with role-based access control.
   - Acceptance: Users can sign up, login, logout, and access only authorized resources.

2. **Application Management (Novel Hierarchy)**
   - Description: Users can create, read, update, delete Applications. Each Application serves as a container for multiple Projects.
   - Acceptance: CRUD operations work correctly. Projects are properly nested under Applications.

3. **Project Management**
   - Description: Full Jira-like project management including projects, boards, sprints, and backlog management.
   - Acceptance: Users can create projects with boards, manage sprints, and organize work items.

4. **Task/Issue Management**
   - Description: Create and manage tasks/issues with status, priority, assignees, labels, comments, and attachments.
   - Acceptance: Tasks support all standard Jira fields. Status transitions work correctly.

5. **Note-Taking System**
   - Description: OneNote-like note-taking with multi-tab interface, rich text editing, and organization features.
   - Acceptance: Users can create multiple tabs, edit notes with rich text, organize hierarchically.

6. **File Upload/Download**
   - Description: Upload documents, images, and recordings to MinIO storage. Attach files to tasks and notes.
   - Acceptance: Files upload to MinIO successfully. Download and preview works for supported formats.

7. **Real-Time Collaboration**
   - Description: WebSocket-based real-time updates for collaborative editing, task changes, and notifications.
   - Acceptance: Multiple users see real-time updates. Conflict resolution handles concurrent edits.

8. **Notification System**
   - Description: In-app notifications for task assignments, mentions, status changes, and other events.
   - Acceptance: Users receive timely notifications. Mark as read/unread works correctly.

9. **Roadmap/Timeline View**
   - Description: Visual roadmap showing project timeline, milestones, and dependencies.
   - Acceptance: Roadmap renders correctly. Drag-and-drop scheduling works.

### Non-Functional Requirements

1. **Performance** - Application loads within 3 seconds. API responses under 500ms.
2. **Security** - Secure IPC, encrypted credentials, SQL injection prevention, XSS protection.
3. **Reliability** - Graceful error handling, offline capability consideration, data integrity.
4. **Maintainability** - Clean code architecture, comprehensive documentation, test coverage >80%.

### Edge Cases

1. **Concurrent Editing Conflicts** - When multiple users edit the same note/task simultaneously, use operational transforms or last-write-wins with merge UI.
2. **WebSocket Disconnection** - Handle reconnection gracefully, queue pending updates, sync on reconnect.
3. **Large File Uploads** - Implement chunked uploads for files >10MB, show progress, handle interruptions.
4. **Offline Mode** - Queue operations when offline, sync when connection restored.
5. **Database Connection Loss** - Retry logic, user feedback, prevent data loss.
6. **Session Expiry** - Handle JWT expiration gracefully, refresh tokens, redirect to login.

## Implementation Notes

### DO
- Follow Electron security best practices (contextIsolation, no nodeIntegration in renderer)
- Use ShadCN CLI to add components (`npx shadcn@latest add [component]`)
- Configure Tailwind content paths to include all source files
- Implement WebSocket connection manager pattern for broadcasts
- Use proper dependency injection in FastAPI
- Create comprehensive Pydantic schemas for all API inputs/outputs
- Write tests alongside feature implementation
- Use meaningful commit messages and atomic commits
- Add CORS middleware for Electron-to-backend communication
- Install python-multipart for file upload support
- Use pydantic-settings for environment variable management
- Use Alembic for database schema migrations

### DON'T
- Don't expose Node.js APIs directly to renderer process
- Don't skip `await websocket.accept()` before sending/receiving
- Don't use dynamic Tailwind class names (breaks purging)
- Don't store credentials in code - use environment variables
- Don't skip error handling for database/storage operations
- Don't implement real-time features without proper disconnect handling
- Don't confuse MinIO API port (9000) with Console port (9001) - SDK uses API port
- Don't forget to install websockets package for FastAPI WebSocket support

## Database Schema

### Core Tables

```sql
-- Users table
CREATE TABLE Users (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    email NVARCHAR(255) UNIQUE NOT NULL,
    password_hash NVARCHAR(255) NOT NULL,
    display_name NVARCHAR(100),
    avatar_url NVARCHAR(500),
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);

-- Applications (top-level container)
CREATE TABLE Applications (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    name NVARCHAR(255) NOT NULL,
    description NVARCHAR(MAX),
    owner_id UNIQUEIDENTIFIER REFERENCES Users(id),
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);

-- Projects (under Applications)
CREATE TABLE Projects (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    application_id UNIQUEIDENTIFIER REFERENCES Applications(id),
    name NVARCHAR(255) NOT NULL,
    key NVARCHAR(10) NOT NULL, -- e.g., "PROJ"
    description NVARCHAR(MAX),
    project_type NVARCHAR(50), -- scrum, kanban, etc.
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);

-- Tasks/Issues
CREATE TABLE Tasks (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    project_id UNIQUEIDENTIFIER REFERENCES Projects(id),
    task_key NVARCHAR(20) NOT NULL, -- e.g., "PROJ-123"
    title NVARCHAR(500) NOT NULL,
    description NVARCHAR(MAX),
    task_type NVARCHAR(50), -- story, bug, epic, subtask
    status NVARCHAR(50) DEFAULT 'todo',
    priority NVARCHAR(20) DEFAULT 'medium',
    assignee_id UNIQUEIDENTIFIER REFERENCES Users(id),
    reporter_id UNIQUEIDENTIFIER REFERENCES Users(id),
    parent_id UNIQUEIDENTIFIER REFERENCES Tasks(id), -- for subtasks
    sprint_id UNIQUEIDENTIFIER,
    story_points INT,
    due_date DATE,
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);

-- Notes (OneNote-style)
CREATE TABLE Notes (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    application_id UNIQUEIDENTIFIER REFERENCES Applications(id),
    parent_id UNIQUEIDENTIFIER REFERENCES Notes(id), -- for hierarchy
    title NVARCHAR(255) NOT NULL,
    content NVARCHAR(MAX), -- Rich text content (HTML or JSON)
    tab_order INT DEFAULT 0,
    created_by UNIQUEIDENTIFIER REFERENCES Users(id),
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
);

-- File Attachments (MinIO references)
CREATE TABLE Attachments (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    file_name NVARCHAR(255) NOT NULL,
    file_type NVARCHAR(100),
    file_size BIGINT,
    minio_bucket NVARCHAR(100),
    minio_key NVARCHAR(500),
    uploaded_by UNIQUEIDENTIFIER REFERENCES Users(id),
    -- Polymorphic association
    entity_type NVARCHAR(50), -- 'task', 'note', 'comment'
    entity_id UNIQUEIDENTIFIER,
    created_at DATETIME2 DEFAULT GETDATE()
);

-- Notifications
CREATE TABLE Notifications (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    user_id UNIQUEIDENTIFIER REFERENCES Users(id),
    type NVARCHAR(50), -- task_assigned, mention, etc.
    title NVARCHAR(255),
    message NVARCHAR(MAX),
    is_read BIT DEFAULT 0,
    entity_type NVARCHAR(50),
    entity_id UNIQUEIDENTIFIER,
    created_at DATETIME2 DEFAULT GETDATE()
);
```

## Development Environment

### Prerequisites
- Node.js 18+ (for Electron/React)
- Python 3.11+ (for FastAPI)
- ODBC Driver 17 for SQL Server
- Access to SQL Server (10.18.138.240)
- Access to MinIO (API: 10.18.136.10:9000, Console: 10.18.136.10:9001)

### Start Services

```bash
# Terminal 1: Start FastAPI Backend
cd fastapi-backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start Electron App (Development)
cd electron-app
npm install
npm run dev
```

### Service URLs
- **FastAPI Backend**: http://localhost:8000
- **FastAPI Docs**: http://localhost:8000/docs
- **SQL Server**: 10.18.138.240:1433
- **MinIO API**: http://10.18.136.10:9000 (use this for SDK connections)
- **MinIO Console**: http://10.18.136.10:9001 (web UI only)

### Required Environment Variables

**fastapi-backend/.env:**
```env
# Database
DB_SERVER=10.18.138.240
DB_NAME=PMDB
DB_USER=pmdbuser
DB_PASSWORD=never!again

# MinIO (NOTE: API port is typically 9000, console is 9001)
MINIO_ENDPOINT=10.18.136.10:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=Windows2
MINIO_SECURE=false

# Auth
JWT_SECRET=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440

# Server
HOST=0.0.0.0
PORT=8000
```

**electron-app/.env:**
```env
VITE_API_URL=http://localhost:8000
```

## Success Criteria

The task is complete when:

1. [ ] Electron application launches successfully and displays the main UI
2. [ ] User authentication (register, login, logout) works correctly
3. [ ] Application > Project > Task hierarchy is fully functional
4. [ ] Users can create, edit, and manage tasks with all Jira-like fields
5. [ ] Note-taking with multi-tab interface works correctly
6. [ ] File uploads to MinIO succeed and files can be retrieved
7. [ ] Real-time collaboration via WebSockets updates all connected clients
8. [ ] Notification system delivers alerts for relevant events
9. [ ] No console errors in development mode
10. [ ] All existing functionality verified via Playwright E2E tests
11. [ ] Test coverage meets >80% target

## QA Acceptance Criteria

**CRITICAL**: These criteria must be verified by the QA Agent before sign-off.

### Unit Tests
| Test | File | What to Verify |
|------|------|----------------|
| Auth Service Tests | `fastapi-backend/tests/test_auth.py` | JWT generation, password hashing, token validation |
| Application CRUD Tests | `fastapi-backend/tests/test_applications.py` | Create, read, update, delete Applications |
| Project CRUD Tests | `fastapi-backend/tests/test_projects.py` | Project operations within Applications |
| Task CRUD Tests | `fastapi-backend/tests/test_tasks.py` | Task creation, status transitions, assignments |
| Note CRUD Tests | `fastapi-backend/tests/test_notes.py` | Note creation, editing, tab management |
| MinIO Service Tests | `fastapi-backend/tests/test_minio.py` | File upload, download, deletion |
| WebSocket Tests | `fastapi-backend/tests/test_websocket.py` | Connection, broadcast, disconnect handling |

### Integration Tests
| Test | Services | What to Verify |
|------|----------|----------------|
| Auth Flow | Frontend + Backend | Login form submits to API, JWT stored, protected routes work |
| Task Board | Frontend + Backend + DB | Creating task reflects in database, UI updates |
| File Upload | Frontend + Backend + MinIO | File uploads through API to MinIO, URL returned |
| Real-time Updates | Frontend + Backend (WS) | Changes broadcast to connected clients |
| Notification Delivery | Backend + WebSocket | Events trigger notifications, delivered via WebSocket |

### End-to-End Tests
| Flow | Steps | Expected Outcome |
|------|-------|------------------|
| User Registration | 1. Open app 2. Click register 3. Fill form 4. Submit | User created, redirected to dashboard |
| Create Application | 1. Login 2. Click "New Application" 3. Fill details 4. Save | Application appears in sidebar |
| Create Project | 1. Select Application 2. Click "New Project" 3. Configure 4. Save | Project created under Application |
| Task Workflow | 1. Create task 2. Edit details 3. Change status 4. Assign user | Task moves through workflow correctly |
| Note Taking | 1. Open notes 2. Create tab 3. Write content 4. Save | Note persisted, content preserved |
| File Attachment | 1. Open task 2. Click attach 3. Select file 4. Upload | File uploaded, preview available |
| Real-time Collab | 1. Open task in 2 windows 2. Edit in window 1 | Changes appear in window 2 instantly |
| Offline Recovery | 1. Disconnect network 2. Make changes 3. Reconnect | Changes synced after reconnection |

### Browser Verification (Electron)
| Page/Component | Navigation | Checks |
|----------------|------------|--------|
| Login Screen | App launch | Form renders, validation works |
| Dashboard | Post-login | Applications list loads, sidebar works |
| Application View | Click application | Projects displayed, CRUD buttons work |
| Project Board | Click project | Board/backlog renders, drag-drop works |
| Task Detail | Click task | All fields editable, comments work |
| Notes Panel | Click notes tab | Tabs render, rich editor works |
| Settings | Click profile | User settings editable |

### Database Verification
| Check | Query/Command | Expected |
|-------|---------------|----------|
| Tables Created | `SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_CATALOG = 'PMDB'` | All tables exist |
| User Created | `SELECT * FROM Users WHERE email = 'test@test.com'` | User record exists after registration |
| Hierarchy Intact | `SELECT p.* FROM Projects p JOIN Applications a ON p.application_id = a.id` | Projects linked to Applications |
| Attachments Linked | `SELECT * FROM Attachments WHERE entity_type = 'task'` | Files associated with entities |

### MinIO Verification
| Check | Command | Expected |
|-------|---------|----------|
| Bucket Exists | `mc ls minio/pm-attachments` | Bucket created |
| File Uploaded | `mc ls minio/pm-attachments/[file-key]` | File exists after upload |
| File Accessible | `mc cat minio/pm-attachments/[file-key]` | File content retrievable |

### QA Sign-off Requirements
- [ ] All unit tests pass (pytest for backend, vitest for frontend)
- [ ] All integration tests pass
- [ ] All E2E Playwright tests pass
- [ ] Electron app launches without errors on Windows
- [ ] Database schema deployed correctly to PMDB
- [ ] MinIO integration working (upload/download verified)
- [ ] WebSocket connections stable (no unexpected disconnects)
- [ ] No security vulnerabilities (IPC secure, no credential exposure)
- [ ] No regressions in existing functionality
- [ ] Code follows established patterns
- [ ] Performance metrics acceptable (<3s load, <500ms API)

## Implementation Phases (Recommended Order)

### Phase 1: Foundation Setup
1. Create project directory structure
2. Initialize Electron + React with electron-vite
3. Configure Tailwind CSS and ShadCN UI
4. Set up FastAPI project structure
5. Configure SQL Server connection
6. Create database schema/migrations

### Phase 2: Authentication
1. Implement user registration API
2. Implement login/logout API with JWT
3. Build login/register UI components
4. Set up protected routes and auth context

### Phase 3: Core Hierarchy (Application > Project > Task)
1. Build Application CRUD API and UI
2. Build Project CRUD API and UI
3. Build Task CRUD API and UI
4. Implement board/list views

### Phase 4: Note-Taking System
1. Build Notes API (CRUD, hierarchy)
2. Create tab management UI
3. Implement rich text editor
4. Add note organization features

### Phase 5: File Management
1. Configure MinIO integration service
2. Build file upload/download API
3. Create attachment UI components
4. Implement file preview

### Phase 6: Real-Time Features
1. Implement WebSocket connection manager
2. Add real-time task updates
3. Add collaborative note editing
4. Build notification system

### Phase 7: Testing & Polish
1. Write comprehensive Playwright E2E tests
2. Performance optimization
3. Error handling improvements
4. UI/UX refinements
