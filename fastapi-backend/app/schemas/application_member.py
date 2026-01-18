"""Pydantic schemas for ApplicationMember model validation."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .invitation import ApplicationRole, UserSummary, ApplicationSummary


class MemberBase(BaseModel):
    """Base schema with common member fields."""

    role: ApplicationRole = Field(
        ...,
        description="Role of the member in the application",
        examples=["owner", "editor", "viewer"],
    )
    is_manager: bool = Field(
        False,
        description="Whether the member has manager privileges (editors only)",
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
    is_manager: Optional[bool] = Field(
        None,
        description="Whether to grant/revoke manager privileges",
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
    created_at: datetime = Field(
        ...,
        description="When the membership was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When the membership was last updated",
    )


class MemberWithUser(MemberResponse):
    """Schema for application member with user details."""

    model_config = ConfigDict(from_attributes=True)

    user: Optional[UserSummary] = Field(
        None,
        description="User details",
    )


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


class ManagerAssignment(BaseModel):
    """Schema for manager role assignment request."""

    is_manager: bool = Field(
        ...,
        description="Whether to grant or revoke manager privileges",
    )
