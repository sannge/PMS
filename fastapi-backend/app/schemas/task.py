"""Pydantic schemas for Task model validation."""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskType(str, Enum):
    """Task type enumeration."""

    STORY = "story"
    BUG = "bug"
    EPIC = "epic"
    SUBTASK = "subtask"
    TASK = "task"


class TaskPriority(str, Enum):
    """Task priority enumeration."""

    LOWEST = "lowest"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HIGHEST = "highest"


class TaskStatusInfo(BaseModel):
    """Nested task status object in task responses."""

    id: UUID = Field(..., description="Task status ID")
    name: str = Field(..., description="Status name (e.g. 'Todo', 'In Progress')")
    category: str = Field(..., description="Status category (Todo, Active, Issue, Done)")
    rank: int = Field(..., description="Display ordering rank")

    model_config = ConfigDict(from_attributes=True)


class TaskUserInfo(BaseModel):
    """Minimal user information for task assignee/reporter display."""

    id: UUID = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    display_name: Optional[str] = Field(None, description="User display name")
    avatar_url: Optional[str] = Field(None, description="User avatar URL")

    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    """Base schema with common task fields."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Task title/summary",
        examples=["Implement user authentication"],
    )
    description: Optional[str] = Field(
        None,
        max_length=102400,  # 100KB max for rich text HTML content
        description="Detailed task description (rich text HTML)",
        examples=["Add JWT-based authentication with login and logout endpoints"],
    )
    task_type: TaskType = Field(
        TaskType.STORY,
        description="Type of task",
        examples=["story", "bug"],
    )
    priority: TaskPriority = Field(
        TaskPriority.MEDIUM,
        description="Task priority level",
        examples=["medium", "high"],
    )
    story_points: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Story point estimate",
        examples=[3, 5, 8],
    )
    due_date: Optional[date] = Field(
        None,
        description="Task due date",
        examples=["2024-12-31"],
    )


class TaskCreate(TaskBase):
    """Schema for creating a new task."""

    project_id: UUID = Field(
        ...,
        description="ID of the parent project",
    )
    assignee_id: Optional[UUID] = Field(
        None,
        description="ID of the assigned user",
    )
    reporter_id: Optional[UUID] = Field(
        None,
        description="ID of the reporting user",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent task (for subtasks)",
    )
    sprint_id: Optional[UUID] = Field(
        None,
        description="ID of the sprint",
    )
    task_status_id: Optional[UUID] = Field(
        None,
        description="ID of the task status (FK to TaskStatuses). If not provided, defaults to project's 'Todo' status.",
    )
    task_rank: Optional[str] = Field(
        None,
        max_length=50,
        description="Lexorank for ordering within status columns",
        examples=["0|hzzzzz:"],
    )


class TaskUpdate(BaseModel):
    """Schema for updating a task."""

    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description="Task title/summary",
    )
    description: Optional[str] = Field(
        None,
        max_length=102400,  # 100KB max for rich text HTML content
        description="Detailed task description (rich text HTML)",
    )
    task_type: Optional[TaskType] = Field(
        None,
        description="Type of task",
    )
    priority: Optional[TaskPriority] = Field(
        None,
        description="Task priority level",
    )
    assignee_id: Optional[UUID] = Field(
        None,
        description="ID of the assigned user",
    )
    story_points: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Story point estimate",
    )
    due_date: Optional[date] = Field(
        None,
        description="Task due date",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent task (for subtasks)",
    )
    sprint_id: Optional[UUID] = Field(
        None,
        description="ID of the sprint",
    )
    task_status_id: Optional[UUID] = Field(
        None,
        description="ID of the task status (FK to TaskStatuses)",
    )
    task_rank: Optional[str] = Field(
        None,
        max_length=50,
        description="Lexorank for ordering within status columns",
    )
    row_version: Optional[int] = Field(
        None,
        ge=1,
        description="Row version for optimistic concurrency control",
    )


class TaskResponse(TaskBase):
    """Schema for task response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique task identifier",
    )
    project_id: UUID = Field(
        ...,
        description="ID of the parent project",
    )
    task_key: str = Field(
        ...,
        description="Unique task key (e.g., 'PROJ-123')",
        examples=["PROJ-123"],
    )
    assignee_id: Optional[UUID] = Field(
        None,
        description="ID of the assigned user",
    )
    reporter_id: Optional[UUID] = Field(
        None,
        description="ID of the reporting user",
    )
    assignee: Optional[TaskUserInfo] = Field(
        None,
        description="Assignee user information",
    )
    reporter: Optional[TaskUserInfo] = Field(
        None,
        description="Reporter user information",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent task",
    )
    sprint_id: Optional[UUID] = Field(
        None,
        description="ID of the sprint",
    )
    task_status_id: UUID = Field(
        ...,
        description="ID of the task status (FK to TaskStatuses)",
    )
    task_status: Optional[TaskStatusInfo] = Field(
        None,
        description="Nested task status object with name, category, and rank",
    )
    task_rank: Optional[str] = Field(
        None,
        description="Lexorank for ordering within status columns",
        examples=["0|hzzzzz:"],
    )
    row_version: int = Field(
        1,
        description="Row version for optimistic concurrency control",
    )
    checklist_total: int = Field(
        0,
        description="Total checklist items across all checklists",
    )
    checklist_done: int = Field(
        0,
        description="Completed checklist items across all checklists",
    )
    created_at: datetime = Field(
        ...,
        description="When the task was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When the task was last updated",
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="When the task was completed (moved to done status)",
    )
    archived_at: Optional[datetime] = Field(
        None,
        description="When the task was archived (7+ days in done status)",
    )
    application_id: Optional[UUID] = Field(
        None,
        description="Application ID (populated in cross-app queries)",
    )
    application_name: Optional[str] = Field(
        None,
        description="Application name (populated in cross-app queries)",
    )


class TaskWithSubtasks(TaskResponse):
    """Schema for task response with subtasks count."""

    subtasks_count: int = Field(
        0,
        description="Number of subtasks",
    )


class TaskMove(BaseModel):
    """Schema for moving a task between status columns and/or reordering within a column.

    Supports Kanban-style drag-and-drop operations:
    - Moving to a different status column (changes status)
    - Reordering within the same column (changes rank)
    - Both at once (changes status and rank)

    Rank calculation:
    - Provide target_rank directly, OR
    - Provide before_task_id and/or after_task_id to auto-calculate rank
    """

    # Status change (optional - for moving between columns)
    target_status_id: Optional[UUID] = Field(
        None,
        description="New task_status_id to move the task to (FK to TaskStatuses)",
    )

    # Rank positioning (optional - for ordering within column)
    target_rank: Optional[str] = Field(
        None,
        max_length=50,
        description="Explicit lexorank position for the task",
    )
    before_task_id: Optional[UUID] = Field(
        None,
        description="ID of the task to position before (for auto rank calculation)",
    )
    after_task_id: Optional[UUID] = Field(
        None,
        description="ID of the task to position after (for auto rank calculation)",
    )

    # Concurrency control
    row_version: Optional[int] = Field(
        None,
        ge=1,
        description="Row version for optimistic concurrency control",
    )


class TaskCursorPage(BaseModel):
    """Paginated response for tasks with cursor-based pagination."""

    items: list[TaskResponse] = Field(
        ...,
        description="List of tasks in this page",
    )
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for fetching the next page (null if no more items)",
    )
    total: Optional[int] = Field(
        None,
        description="Total count of items (only included when requested)",
    )
    can_restore: Optional[bool] = Field(
        None,
        description="Whether the current user can restore/unarchive tasks (only included for archived tasks endpoint)",
    )
