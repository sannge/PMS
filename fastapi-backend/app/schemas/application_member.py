"""Pydantic schemas for ApplicationMember model validation."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .invitation import ApplicationRole, UserSummary, ApplicationSummary


class MemberBase(BaseModel):
    """Base schema with common member fields."""

    role: ApplicationRole = Field(
        ...,
        description="Role of the member in the application",
        examples=["owner", "editor", "viewer"],
    )


class MemberCreate(MemberBase):
    """Schema for creating a new application member."""

    user_id: UUID = Field(
        ...,
        description="ID of the user to add as member",
    )
    invitation_id: Optional[UUID] = Field(
        None,
        description="ID of the invitation that created this membership",
    )


class MemberUpdate(BaseModel):
    """Schema for updating an application member."""

    role: Optional[ApplicationRole] = Field(
        None,
        description="New role for the member",
        examples=["editor", "viewer"],
    )


class MemberResponse(MemberBase):
    """Schema for application member response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique member identifier",
    )
    application_id: UUID = Field(
        ...,
        description="ID of the application",
    )
    user_id: UUID = Field(
        ...,
        description="ID of the user",
    )
    invitation_id: Optional[UUID] = Field(
        None,
        description="ID of the invitation that created this membership",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the membership was created",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the membership was last updated",
    )


class MemberWithUser(MemberResponse):
    """Schema for application member with user details."""

    model_config = ConfigDict(from_attributes=True)

    # Internal user object - excluded from serialization
    user: Optional[UserSummary] = Field(
        None,
        description="User details",
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


class MemberWithApplication(MemberResponse):
    """Schema for application member with application details."""

    model_config = ConfigDict(from_attributes=True)

    application: Optional[ApplicationSummary] = Field(
        None,
        description="Application details",
    )


class MemberList(BaseModel):
    """Schema for paginated member list response."""

    items: List[MemberWithUser] = Field(
        ...,
        description="List of application members",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of members",
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


