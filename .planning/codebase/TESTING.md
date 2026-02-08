# Testing Patterns

**Analysis Date:** 2026-01-31

## Test Framework

**Frontend Runner:**

- Vitest 1.3.1
- Config: `electron-app/vitest.config.ts`
- UI testing - Vercel's agent-browser(load agent-browser skill) covers all test cases(edge cases too)
- Environment: jsdom

**Backend Runner:**

- pytest 8.3.0 with pytest-asyncio 0.24.0
- Async HTTP testing: httpx (AsyncClient)
- Database: PostgreSQL for tests

**Run Commands:**

```bash
# Frontend - run all tests
npm run test

# Frontend - watch mode
npm run test:watch

# Frontend - coverage
npm run test:coverage

# Backend - run all tests
pytest tests/ -v

# Backend - specific test file
pytest tests/test_tasks.py -v

# Backend - coverage
pytest tests/ --cov=app
```

## Test File Organization

**Location (Frontend):**

- Co-located with source: `src/renderer/__tests__/` directory
- Test files use `.test.tsx` or `.test.ts` suffix
- Setup file: `src/renderer/__tests__/setup.ts` (global test configuration)

**Location (Backend):**

- Separate `tests/` directory at project root
- One test file per router/feature (e.g., `test_tasks.py`, `test_auth.py`)
- Shared fixtures in `tests/conftest.py`

**Naming:**

- Frontend: `<module>.test.tsx` (e.g., `auth-context.test.tsx`)
- Backend: `test_<module>.py` (e.g., `test_tasks.py`)

**Structure:**

```
electron-app/src/renderer/__tests__/
├── auth-context.test.tsx
├── notes-context.test.tsx
├── notification-ui-context.test.tsx
└── setup.ts

fastapi-backend/tests/
├── conftest.py              # Shared fixtures
├── test_applications.py
├── test_auth.py
├── test_tasks.py
├── test_websocket.py
└── load/                    # Load testing (Locust)
    ├── locustfile.py
    └── locustfile_shared_token.py
```

## Test Structure

**Frontend Test Suite (Vitest):**

```typescript
describe("Auth Context", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window.localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue(
      null,
    );
  });

  describe("useAuthStore", () => {
    it("returns initial state", () => {
      const { result } = renderHook(() => useAuthStore(), { wrapper });

      expect(result.current.user).toBeNull();
      expect(result.current.token).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
    });
  });
});
```

**Key Patterns:**

- Hierarchical `describe` blocks for feature grouping
- `beforeEach` for mock cleanup between tests
- Wrapper component for context/provider hooks
- `renderHook` from `@testing-library/react` for hook testing
- `act` wrapper for state updates in hooks

**Backend Test Suite (pytest):**

```python
@pytest.mark.asyncio
class TestListTasks:
    """Tests for listing tasks."""

    async def test_list_tasks_empty(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test listing tasks when none exist."""
        response = await client.get(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []
```

**Key Patterns:**

- `@pytest.mark.asyncio` decorator for async tests
- Class-based test grouping (one class per endpoint/feature)
- Fixtures as function parameters (dependency injection)
- Async/await for all database and HTTP operations
- Clear assertion messages (implicit via test method docstrings)

## Mocking

**Frontend Framework:**

- Vitest `vi` for mocking functions and modules
- `@testing-library/react` for component rendering and queries
- Mock window APIs (electronAPI, localStorage) in setup file

**Frontend Mocking Pattern:**

```typescript
// Setup (in setup.ts)
const mockElectronAPI = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  fetch: vi.fn(),
};

Object.defineProperty(window, "electronAPI", {
  value: mockElectronAPI,
  writable: true,
});

// Usage in tests
(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
  status: 200,
  data: mockTokenResponse,
});
```

**Backend Framework:**

- unittest.mock (`MagicMock`, `patch`) from standard library
- pytest fixtures for database and client setup

**Backend Mocking Pattern:**

```python
@pytest.fixture
def mock_minio_service():
    """Create a mock MinIO service."""
    with patch("app.services.minio_service.MinIOService") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        # Configure mock methods
        mock_instance.upload_file.return_value = "test/path/file.txt"
        mock_instance.delete_file.return_value = True

        yield mock_instance
```

**What to Mock:**

- HTTP calls to external APIs
- Database I/O operations (via AsyncClient with dependency override)
- File storage operations (MinIO)
- WebSocket connections
- Time-dependent operations (for deterministic tests)

**What NOT to Mock:**

- Core business logic (test the real logic)
- Database models and schema validation
- Authentication logic (test with real tokens)
- Permission checks (test actual rules)

## Fixtures and Factories

**Frontend Test Data:**

- Inline mock data in test files
- Example:
  ```typescript
  const mockTokenResponse = {
    access_token: "test-token",
    token_type: "bearer",
  };
  const mockUser = {
    id: "123",
    email: "test@test.com",
    display_name: "Test User",
    avatar_url: null,
    created_at: "2024-01-01",
    updated_at: "2024-01-01",
  };
  ```

**Backend Fixtures:**
Location: `fastapi-backend/tests/conftest.py`

**Core Fixtures:**

```python
@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create async test engine with PostgreSQL."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
    # Drop/create tables, yield, then cleanup
    yield engine

@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async test database session."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, ...)
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with database dependency override."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), ...) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

**Data Fixtures (created in conftest.py):**

```python
@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        password_hash=get_test_password_hash("TestPassword123!"),
        display_name="Test User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_project(db_session: AsyncSession, test_application: Application) -> Project:
    """Create a test project."""
    project = Project(
        id=uuid4(),
        application_id=test_application.id,
        name="Test Project",
        key="TEST",
        description="A test project",
        project_type="kanban",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project

@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Create authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}
```

## Coverage

**Requirements:**

- No enforced minimum (target: 80% for backend)
- Frontend tests focus on critical paths and hooks

**View Coverage:**

```bash
# Backend HTML report
pytest tests/ --cov=app --cov-report=html
# Open htmlcov/index.html

# Frontend coverage
npm run test:coverage
# Open coverage/index.html
```

## Test Types

**Frontend Unit Tests:**

- Scope: Individual hooks and context providers
- Approach: Use `renderHook` with `@testing-library/react`
- Example: `auth-context.test.tsx` tests login, logout, register flows
- Coverage: Happy paths and error scenarios
- Do NOT test: Individual component rendering (use E2E instead)

**Frontend Integration Tests:**

- Scope: Multiple hooks working together, context state persistence
- Approach: Render components that use hooks, interact with them
- Location: Same as unit tests (both in `__tests__/` directory)

**Backend Unit Tests:**

- Scope: Individual endpoints with mocked dependencies
- Approach: Use `AsyncClient` with fixture-based test data
- Example: `test_tasks.py` tests CRUD operations, filtering, pagination
- Coverage: Success cases, validation errors, permission checks
- Use mocks for: External APIs (MinIO), Redis, notifications

**Backend Integration Tests:**

- Scope: Multiple endpoints working together
- Approach: Full database + client setup via fixtures
- Example: Create task → update status → verify notification sent
- Does NOT mock: Database, core business logic

**E2E Tests:**

- Framework: agent-browser (planned/documented)
- Trigger: After each feature completion
- Scope: Full user workflows from UI through API to database
- Coverage: User journeys, real-time updates, multi-user interactions

## Common Patterns

**Async Testing (Frontend):**

```typescript
it("successfully logs in user", async () => {
  (window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    status: 200,
    data: mockTokenResponse,
  });

  const { result } = renderHook(() => useAuthStore(), { wrapper });

  let success: boolean;
  await act(async () => {
    success = await result.current.login({
      email: "test@test.com",
      password: "password",
    });
  });

  expect(success!).toBe(true);
  expect(result.current.token).toBe("test-token");
});
```

**Async Testing (Backend):**

```python
async def test_create_task(
    self, client: AsyncClient, auth_headers: dict, test_project: Project
):
    """Test creating a new task."""
    response = await client.post(
        f"/api/projects/{test_project.id}/tasks",
        json={
            "title": "New Task",
            "description": "Task description",
            "task_type": "story",
            "priority": "high",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "New Task"
    assert data["task_key"].startswith("TEST-")
```

**Error Testing (Frontend):**

```typescript
it("handles login failure", async () => {
  (window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    status: 401,
    data: { detail: "Invalid credentials" },
  });

  const { result } = renderHook(() => useAuthStore(), { wrapper });

  let success: boolean;
  await act(async () => {
    success = await result.current.login({
      email: "test@test.com",
      password: "wrong",
    });
  });

  expect(success!).toBe(false);
  expect(result.current.error?.message).toBe("Invalid credentials");
});
```

**Error Testing (Backend):**

```python
async def test_create_task_invalid_data(
    self, client: AsyncClient, auth_headers: dict, test_project: Project
):
    """Test creating task with invalid data."""
    response = await client.post(
        f"/api/projects/{test_project.id}/tasks",
        json={"title": ""},  # Missing required field
        headers=auth_headers,
    )

    assert response.status_code == 422
    error = response.json()
    assert "detail" in error
```

**Database Transaction Testing (Backend):**

- All tests run in transactions that rollback after completion
- `conftest.py` creates clean database for each test function (scope="function")
- Use `await db_session.rollback()` in fixture teardown to ensure cleanup
- Example from `conftest.py`:
  ```python
  @pytest_asyncio.fixture(scope="function")
  async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
      async with async_session() as session:
          yield session
          await session.rollback()  # Automatic cleanup
  ```

---

_Testing analysis: 2026-01-31_
