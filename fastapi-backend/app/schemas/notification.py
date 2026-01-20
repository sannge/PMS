"""Pydantic schemas for Notification model validation."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    """Notification type enumeration."""

    TASK_ASSIGNED = "task_assigned"
    TASK_UPDATED = "task_updated"
    TASK_COMMENTED = "task_commented"
    MENTION = "mention"
    STATUS_CHANGE = "status_change"
    DUE_DATE_REMINDER = "due_date_reminder"
    PROJECT_INVITE = "project_invite"
    SYSTEM = "system"
    # Application invitation notification types
    APPLICATION_INVITE = "application_invite"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_REJECTED = "invitation_rejected"
    ROLE_CHANGED = "role_changed"
    MEMBER_REMOVED = "member_removed"
    PROJECT_ASSIGNED = "project_assigned"
    # Project member management notification types
    PROJECT_MEMBER_ADDED = "project_member_added"
    PROJECT_MEMBER_REMOVED = "project_member_removed"
    PROJECT_ROLE_CHANGED = "project_role_changed"
    TASK_REASSIGNMENT_NEEDED = "task_reassignment_needed"


class EntityType(str, Enum):
    """Entity type enumeration for notification context."""

    TASK = "task"
    NOTE = "note"
    PROJECT = "project"
    APPLICATION = "application"
    COMMENT = "comment"
    # New entity types for invitation system
    INVITATION = "invitation"
    APPLICATION_MEMBER = "application_member"
    PROJECT_MEMBER = "project_member"


class NotificationBase(BaseModel):
    """Base schema with common notification fields."""

    type: NotificationType = Field(
        ...,
        description="Type of notification",
        examples=["task_assigned", "mention"],
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Notification title",
        examples=["New task assigned to you"],
    )
    message: Optional[str] = Field(
        None,
        description="Detailed notification message",
        examples=["You have been assigned to task PROJ-123: Implement authentication"],
    )
    entity_type: Optional[EntityType] = Field(
        None,
        description="Type of related entity",
        examples=["task", "note"],
    )
    entity_id: Optional[UUID] = Field(
        None,
        description="ID of the related entity",
    )


class NotificationCreate(NotificationBase):
    """Schema for creating a new notification."""

    user_id: UUID = Field(
        ...,
        description="ID of the user receiving the notification",
    )


class NotificationUpdate(BaseModel):
    """Schema for updating a notification."""

    is_read: Optional[bool] = Field(
        None,
        description="Whether the notification has been read",
    )


class NotificationResponse(NotificationBase):
    """Schema for notification response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique notification identifier",
    )
    user_id: UUID = Field(
        ...,
        description="ID of the user receiving the notification",
    )
    is_read: bool = Field(
        False,
        description="Whether the notification has been read",
    )
    created_at: datetime = Field(
        ...,
        description="When the notification was created",
    )
    entity_status: Optional[str] = Field(
        None,
        description="Current status of the related entity (e.g., invitation status: pending, accepted, rejected)",
    )


class NotificationBulkUpdate(BaseModel):
    """Schema for bulk updating notifications."""

    notification_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,  # Limit to prevent DoS via large bulk operations
        description="List of notification IDs to update (max 100)",
    )
    is_read: bool = Field(
        ...,
        description="New read status for all notifications",
    )


class NotificationCount(BaseModel):
    """Schema for notification count response."""

    total: int = Field(
        ...,
        ge=0,
        description="Total number of notifications",
    )
    unread: int = Field(
        ...,
        ge=0,
        description="Number of unread notifications",
    )
