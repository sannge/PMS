"""Pydantic schemas for Project model validation."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """Base schema with common project fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project name",
        examples=["Website Redesign"],
    )
    key: str = Field(
        ...,
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z][A-Z0-9]*$",
        description="Project key (uppercase letters and numbers, e.g., 'PROJ')",
        examples=["PROJ", "WEB1", "API"],
    )
    description: Optional[str] = Field(
        None,
        description="Project description",
        examples=["Complete website redesign with new branding"],
    )
    project_type: Optional[str] = Field(
        "kanban",
        description="Project type (scrum, kanban, etc.)",
        examples=["kanban", "scrum"],
    )


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""

    application_id: UUID = Field(
        ...,
        description="ID of the parent application",
    )
    project_owner_user_id: Optional[UUID] = Field(
        None,
        description="ID of the project owner (defaults to creator if not specified)",
    )


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Project name",
    )
    description: Optional[str] = Field(
        None,
        description="Project description",
    )
    project_type: Optional[str] = Field(
        None,
        description="Project type (scrum, kanban, etc.)",
    )
    project_owner_user_id: Optional[UUID] = Field(
        None,
        description="ID of the project owner",
    )
    row_version: Optional[int] = Field(
        None,
        ge=1,
        description="Row version for optimistic concurrency control",
    )


class ProjectResponse(ProjectBase):
    """Schema for project response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique project identifier",
    )
    application_id: UUID = Field(
        ...,
        description="ID of the parent application",
    )
    created_by: Optional[UUID] = Field(
        None,
        description="ID of the user who created the project",
    )
    project_owner_user_id: Optional[UUID] = Field(
        None,
        description="ID of the project owner",
    )
    derived_status_id: Optional[UUID] = Field(
        None,
        description="ID of the derived status (FK to TaskStatuses)",
    )
    derived_status: Optional[str] = Field(
        None,
        description="Name of the derived status (Todo, In Progress, Issue, Done)",
    )
    override_status_id: Optional[UUID] = Field(
        None,
        description="ID of the override status (FK to TaskStatuses)",
    )
    override_reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for the status override",
    )
    override_by_user_id: Optional[UUID] = Field(
        None,
        description="ID of the user who set the override",
    )
    override_expires_at: Optional[datetime] = Field(
        None,
        description="When the status override expires",
    )
    row_version: int = Field(
        1,
        description="Row version for optimistic concurrency control",
    )
    created_at: datetime = Field(
        ...,
        description="When the project was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When the project was last updated",
    )


class ProjectWithTasks(ProjectResponse):
    """Schema for project response with tasks count."""

    tasks_count: int = Field(
        0,
        description="Number of tasks in this project",
    )


class ProjectStatusOverride(BaseModel):
    """Schema for overriding project status (Owner-only)."""

    override_status_id: UUID = Field(
        ...,
        description="ID of the status to override to (FK to TaskStatuses)",
    )
    override_reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Reason for the status override",
        examples=["Waiting for external dependency", "Project on hold per stakeholder request"],
    )
    override_expires_at: Optional[datetime] = Field(
        None,
        description="When the override should expire and revert to derived status",
    )


class ProjectStatusOverrideClear(BaseModel):
    """Schema for clearing project status override."""

    pass  # No fields needed - just clears the override
