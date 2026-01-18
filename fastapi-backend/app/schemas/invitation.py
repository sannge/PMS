"""Pydantic schemas for Invitation model validation."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationRole(str, Enum):
    """Application role enumeration for user permissions."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class InvitationStatus(str, Enum):
    """Invitation status enumeration."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class InvitationBase(BaseModel):
    """Base schema with common invitation fields."""

    role: ApplicationRole = Field(
        ...,
        description="Role to assign to the invitee",
        examples=["editor", "viewer"],
    )


class InvitationCreate(InvitationBase):
    """Schema for creating a new invitation."""

    invitee_id: UUID = Field(
        ...,
        description="ID of the user being invited",
    )


class InvitationUpdate(BaseModel):
    """Schema for updating an invitation (accept/reject)."""

    status: InvitationStatus = Field(
        ...,
        description="New status for the invitation",
        examples=["accepted", "rejected"],
    )


class UserSummary(BaseModel):
    """Minimal user information for invitation display."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="User unique identifier",
    )
    email: str = Field(
        ...,
        description="User email address",
    )
    full_name: Optional[str] = Field(
        None,
        description="User full name",
    )


class ApplicationSummary(BaseModel):
    """Minimal application information for invitation display."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Application unique identifier",
    )
    name: str = Field(
        ...,
        description="Application name",
    )


class InvitationResponse(InvitationBase):
    """Schema for invitation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique invitation identifier",
    )
    application_id: UUID = Field(
        ...,
        description="ID of the application",
    )
    inviter_id: UUID = Field(
        ...,
        description="ID of the user who sent the invitation",
    )
    invitee_id: UUID = Field(
        ...,
        description="ID of the user being invited",
    )
    status: InvitationStatus = Field(
        ...,
        description="Current status of the invitation",
    )
    created_at: datetime = Field(
        ...,
        description="When the invitation was created",
    )
    responded_at: Optional[datetime] = Field(
        None,
        description="When the invitation was responded to",
    )


class InvitationWithDetails(InvitationResponse):
    """Schema for invitation with related entity details."""

    model_config = ConfigDict(from_attributes=True)

    inviter: Optional[UserSummary] = Field(
        None,
        description="User who sent the invitation",
    )
    invitee: Optional[UserSummary] = Field(
        None,
        description="User being invited",
    )
    application: Optional[ApplicationSummary] = Field(
        None,
        description="Application being shared",
    )


class InvitationList(BaseModel):
    """Schema for paginated invitation list response."""

    items: List[InvitationWithDetails] = Field(
        ...,
        description="List of invitations",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of invitations",
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
