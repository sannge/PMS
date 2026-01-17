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
