"""Pydantic schemas for ProjectMember model validation."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectMemberBase(BaseModel):
    """Base schema with common project member fields."""

    user_id: UUID = Field(
        ...,
        description="ID of the user being added as a project member",
    )


class ProjectMemberCreate(ProjectMemberBase):
    """Schema for creating a new project member."""

    project_id: UUID = Field(
        ...,
        description="ID of the project to add the member to",
    )
    added_by_user_id: Optional[UUID] = Field(
        None,
        description="ID of the user adding this member (usually set by the system)",
    )


class ProjectMemberUpdate(BaseModel):
    """Schema for updating a project member.

    Note: Project membership is mostly immutable. This schema exists
    for API consistency but has limited use cases.
    """

    # Currently no updatable fields for project membership
    # The relationship is either active (exists) or removed (deleted)
    pass


class ProjectMemberResponse(BaseModel):
    """Schema for project member response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique project member identifier",
    )
    project_id: UUID = Field(
        ...,
        description="ID of the project",
    )
    user_id: UUID = Field(
        ...,
        description="ID of the member user",
    )
    added_by_user_id: Optional[UUID] = Field(
        None,
        description="ID of the user who added this member",
    )
    created_at: datetime = Field(
        ...,
        description="When the membership was created",
    )


class ProjectMemberWithUser(ProjectMemberResponse):
    """Schema for project member response with nested user info."""

    user_email: Optional[str] = Field(
        None,
        description="Email of the member user",
    )
    user_display_name: Optional[str] = Field(
        None,
        description="Display name of the member user",
    )
