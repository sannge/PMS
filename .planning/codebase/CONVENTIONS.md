# Coding Conventions

**Analysis Date:** 2026-01-31

## Naming Patterns

**Files:**
- Components: kebab-case (e.g., `task-detail.tsx`, `notification-bell.tsx`)
- Services: kebab-case (e.g., `auth_service.py`, `minio_service.py`)
- Schemas: PascalCase classes (e.g., `TaskCreate`, `UserResponse`)
- Models: PascalCase classes (e.g., `User`, `Task`, `Project`)
- Hooks: camelCase with `use-` prefix (e.g., `use-auth.ts`, `use-websocket.ts`)
- Routers: kebab-case (e.g., `auth.py`, `tasks.py`)

**Functions:**
- TypeScript: camelCase (e.g., `handleStatusChange`, `getTaskTypeIcon`)
- Python: snake_case (e.g., `create_access_token`, `verify_password`)
- Helper functions: Prefixed with meaningful context (e.g., `getTaskTypeIcon`, `formatDate`)

**Variables:**
- TypeScript: camelCase for all variables and state (e.g., `isLoading`, `pendingTask`, `hasDescriptionChanges`)
- Python: snake_case (e.g., `is_authenticated`, `auth_headers`)
- Constants: UPPER_SNAKE_CASE (e.g., `AUTH_STORAGE_KEY`, `TEST_DATABASE_URL`)

**Types:**
- TypeScript: PascalCase interfaces/types (e.g., `TaskDetailProps`, `AuthState`, `TaskStatus`)
- Python: PascalCase for Pydantic models (e.g., `TaskCreate`, `UserResponse`)
- Type imports: Explicit `type` keyword (e.g., `import type { Task, User }`)

## Code Style

**Formatting:**
- No ESLint config file found in root (styles enforced via git hooks/CI)
- TypeScript: Strict mode enabled in `tsconfig.json`
- TypeScript compiler options:
  - `strict: true`
  - `noUnusedLocals: true`
  - `noUnusedParameters: true`
  - `noFallthroughCasesInSwitch: true`
- Python: No explicit formatter configured, uses standard conventions

**Linting:**
- TypeScript: ESLint with zero-warnings policy (`--max-warnings 0`)
- Command: `npm run lint` (reports unused disable directives)
- Python: Ruff for linting
- Command: `ruff check .`

## Import Organization

**Order (TypeScript):**
1. React core imports (`import { ... } from 'react'`)
2. Third-party library imports (`from '@radix-ui'`, `from 'lucide-react'`)
3. Relative imports from `@/` alias (`from '@/lib/utils'`, `from '@/hooks/'`)
4. Type imports separated with `import type` keyword

**Example from `task-detail.tsx`:**
```typescript
import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { X, ExternalLink, Trash2, ... } from 'lucide-react'
import type { Task, TaskStatusValue as TaskStatus } from '@/hooks/use-queries'
import { useProjectMembers } from '@/hooks/use-members'
```

**Path Aliases (TypeScript):**
- `@/*`: maps to `src/renderer/*`
- `@/components/*`: maps to `src/renderer/components/*`
- `@/lib/*`: maps to `src/renderer/lib/*`
- `@/hooks/*`: maps to `src/renderer/hooks/*`
- `@/stores/*`: maps to `src/renderer/stores/*`
- `@/pages/*`: maps to `src/renderer/pages/*`

**Order (Python):**
1. Standard library (`import uuid`, `from datetime import ...`)
2. Third-party imports (`from fastapi import ...`, `from sqlalchemy import ...`)
3. Relative imports from app (`from ..models import ...`, `from ..services import ...`)

## Error Handling

**Python Patterns:**
- Use `HTTPException` for API errors with explicit `status_code` and `detail` message
- Example:
  ```python
  raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="User does not have permission to update this task"
  )
  ```
- Type hints required for all function parameters and return values
- Optional types use `Optional[T]` from typing

**TypeScript Patterns:**
- Error objects have `message` and optional `code`/`field` properties
- Example error interface:
  ```typescript
  export interface AuthError {
    message: string
    code?: string
    field?: string
  }
  ```
- Async operations return `Promise<boolean>` to indicate success/failure
- Example:
  ```typescript
  const handleStatusChange = useCallback((status: TaskStatus) => {
    if (onUpdate) {
      onUpdate({ status })
    }
  }, [onUpdate])
  ```

## Logging

**Framework:**
- TypeScript: `console.*` (no centralized logger)
- Python: `logging` module (standard library)

**Patterns:**
- Minimal logging in components (only for debugging)
- API errors logged via FastAPI exception handling
- Database operations logged via SQLAlchemy debug mode
- WebSocket events logged in handlers and services

## Comments

**When to Comment:**
- Complex business logic (e.g., status derivation, permission checks)
- Non-obvious algorithms or calculations
- Important side effects or state mutations
- Integration points with external services

**JSDoc/TSDoc:**
- Used extensively in component files with large prop interfaces
- Example from `task-detail.tsx`:
  ```typescript
  /**
   * Task Detail Component
   *
   * Slide-over panel for viewing and editing task details.
   * Provides a comprehensive view of task information with inline editing.
   *
   * Features:
   * - Slide-over panel animation
   * - Task header with key and type
   * ...
   */
  ```
- Props interfaces documented with inline comments
- Example:
  ```typescript
  export interface TaskDetailProps {
    /**
     * Task to display
     */
    task: Task
    /**
     * Whether the panel is open
     */
    isOpen: boolean
  }
  ```

**Python Docstrings:**
- Module-level docstrings describe purpose and scope
- Class docstrings include full attribute documentation
- Example from `task.py`:
  ```python
  class Task(Base):
      """
      Task model representing issues/tasks within a project.

      Tasks are the lowest level of the hierarchy: Application > Projects > Tasks
      ...

      Attributes:
          id: Unique identifier (UUID)
          project_id: FK to parent project
          ...
      """
  ```
- Function docstrings include Args, Returns, and Raises sections

## Function Design

**Size:**
- Keep components and functions under 300 lines where practical
- Extract sub-components for complex UI logic
- Example: `TaskAttachmentsSection` extracted from `TaskDetail` for clarity

**Parameters:**
- Use object destructuring for functions with multiple params
- Example:
  ```typescript
  function EditableField({
    label,
    value,
    placeholder,
    multiline = false,
    onSave,
    disabled = false,
  }: EditableFieldProps): JSX.Element
  ```
- Pydantic models used for API request/response bodies (not individual params)

**Return Values:**
- React components return `JSX.Element | null` (explicit null when not rendering)
- Async operations return `Promise<T>` with explicit type
- Use explicit type annotations (not implicit inference)

## Module Design

**Exports:**
- Barrel files re-export related components/hooks for clean imports
- Located at `index.ts` or `index.py` in component/hook directories
- Example from `checklists/index.ts`:
  ```typescript
  export { ChecklistItem } from './ChecklistItem'
  export type { ChecklistItemProps } from './ChecklistItem'
  ```

**Barrel Files:**
- Frontend: Used extensively for components and hooks
- Backend: Used in `schemas/__init__.py` to re-export Pydantic models
- Example from `schemas/__init__.py`:
  ```python
  __all__ = [
      "ApplicationCreate",
      "ApplicationResponse",
      ...
  ]
  ```

## Component Structure (React)

**Structural Pattern:**
- Section comments dividing major logical blocks (e.g., `// ============================================================================`)
- Order: Types → Constants → Helper Functions → Sub-Components → Main Component
- Example from `task-detail.tsx`:
  ```typescript
  // ============================================================================
  // Types
  // ============================================================================

  export interface TaskDetailProps { ... }

  // ============================================================================
  // Constants
  // ============================================================================

  const PRIORITIES: ... = [...]

  // ============================================================================
  // Helper Functions
  // ============================================================================

  function getTaskTypeIcon(taskType: TaskType): JSX.Element { ... }
  ```

## Service/Router Structure (Python)

**Structural Pattern:**
- Module docstring explaining purpose
- Imports organized by category
- Type hints on all functions
- Pydantic models for request/response bodies
- Example from `auth_service.py`:
  ```python
  """Authentication service with JWT token generation and user management."""

  from datetime import datetime, timedelta, timezone
  from typing import Optional
  from uuid import UUID

  from fastapi import Depends, HTTPException, status
  from jose import JWTError, jwt
  from pydantic import BaseModel
  ```

---

*Convention analysis: 2026-01-31*
