"""Pydantic schemas for ProjectMember model validation."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ProjectMemberRole(str, Enum):
    """Enum for project member roles.

    - ADMIN: Full control, can manage project members
    - MEMBER: Can edit/move tasks but cannot manage members
    """

    ADMIN = "admin"
    MEMBER = "member"


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
    role: ProjectMemberRole = Field(
        ProjectMemberRole.MEMBER,
        description="Role of the member (admin or member)",
    )
    added_by_user_id: Optional[UUID] = Field(
        None,
        description="ID of the user adding this member (usually set by the system)",
    )


class ProjectMemberUpdate(BaseModel):
    """Schema for updating a project member.

    Currently supports updating the member's role.
    """

    role: Optional[ProjectMemberRole] = Field(
        None,
        description="New role for the member (admin or member)",
    )


class UserSummary(BaseModel):
    """User summary for display in member lists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    display_name: Optional[str] = Field(None, description="User's display name")
    avatar_url: Optional[str] = Field(None, description="User's avatar URL")


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
    role: ProjectMemberRole = Field(
        ...,
        description="Role of the member (admin or member)",
    )
    added_by_user_id: Optional[UUID] = Field(
        None,
        description="ID of the user who added this member",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the membership was created",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the membership was last updated",
    )


class ProjectMemberWithUser(ProjectMemberResponse):
    """Schema for project member response with nested user info."""

    # Internal user object - excluded from serialization
    user: Optional[UserSummary] = Field(
        None,
        description="User details of the member",
        exclude=True,
    )

    # Flat user properties for frontend compatibility (computed from user)
    @computed_field
    @property
    def user_email(self) -> Optional[str]:
        """User email address."""
        return self.user.email if self.user else None

    @computed_field
    @property
    def user_display_name(self) -> Optional[str]:
        """User display name."""
        return self.user.display_name if self.user else None

    @computed_field
    @property
    def user_avatar_url(self) -> Optional[str]:
        """User avatar URL."""
        return self.user.avatar_url if self.user else None
