"""Pydantic schemas for ProjectAssignment model validation."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .invitation import UserSummary


class ProjectSummary(BaseModel):
    """Minimal project information for assignment display."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Project unique identifier",
    )
    name: str = Field(
        ...,
        description="Project name",
    )
    short_code: Optional[str] = Field(
        None,
        description="Project short code",
    )


class AssignmentBase(BaseModel):
    """Base schema with common assignment fields."""

    pass


class AssignmentCreate(AssignmentBase):
    """Schema for creating a new project assignment."""

    user_id: UUID = Field(
        ...,
        description="ID of the user to assign to the project",
    )


class AssignmentResponse(AssignmentBase):
    """Schema for project assignment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique assignment identifier",
    )
    project_id: UUID = Field(
        ...,
        description="ID of the project",
    )
    user_id: UUID = Field(
        ...,
        description="ID of the assigned user",
    )
    assigned_by: UUID = Field(
        ...,
        description="ID of the user who made the assignment",
    )
    created_at: datetime = Field(
        ...,
        description="When the assignment was created",
    )


class AssignmentWithUser(AssignmentResponse):
    """Schema for project assignment with user details."""

    model_config = ConfigDict(from_attributes=True)

    user: Optional[UserSummary] = Field(
        None,
        description="Assigned user details",
    )
    assigner: Optional[UserSummary] = Field(
        None,
        description="User who made the assignment",
    )


class AssignmentWithProject(AssignmentResponse):
    """Schema for project assignment with project details."""

    model_config = ConfigDict(from_attributes=True)

    project: Optional[ProjectSummary] = Field(
        None,
        description="Project details",
    )


class AssignmentWithDetails(AssignmentResponse):
    """Schema for project assignment with full related entity details."""

    model_config = ConfigDict(from_attributes=True)

    user: Optional[UserSummary] = Field(
        None,
        description="Assigned user details",
    )
    assigner: Optional[UserSummary] = Field(
        None,
        description="User who made the assignment",
    )
    project: Optional[ProjectSummary] = Field(
        None,
        description="Project details",
    )


class AssignmentList(BaseModel):
    """Schema for paginated assignment list response."""

    items: List[AssignmentWithUser] = Field(
        ...,
        description="List of project assignments",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of assignments",
    )
    skip: int = Field(
        ...,
        ge=0,
        description="Number of items skipped",
    )
    limit: int = Field(
        ...,
        ge=1,
        description="Maximum items per page",
    )
