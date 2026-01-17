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


class TaskStatus(str, Enum):
    """Task status enumeration."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    """Task priority enumeration."""

    LOWEST = "lowest"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HIGHEST = "highest"


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
        description="Detailed task description",
        examples=["Add JWT-based authentication with login and logout endpoints"],
    )
    task_type: TaskType = Field(
        TaskType.STORY,
        description="Type of task",
        examples=["story", "bug"],
    )
    status: TaskStatus = Field(
        TaskStatus.TODO,
        description="Current task status",
        examples=["todo", "in_progress"],
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
        description="Detailed task description",
    )
    task_type: Optional[TaskType] = Field(
        None,
        description="Type of task",
    )
    status: Optional[TaskStatus] = Field(
        None,
        description="Current task status",
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
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent task",
    )
    sprint_id: Optional[UUID] = Field(
        None,
        description="ID of the sprint",
    )
    created_at: datetime = Field(
        ...,
        description="When the task was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When the task was last updated",
    )


class TaskWithSubtasks(TaskResponse):
    """Schema for task response with subtasks count."""

    subtasks_count: int = Field(
        0,
        description="Number of subtasks",
    )
