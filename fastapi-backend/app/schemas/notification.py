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


class EntityType(str, Enum):
    """Entity type enumeration for notification context."""

    TASK = "task"
    NOTE = "note"
    PROJECT = "project"
    APPLICATION = "application"
    COMMENT = "comment"


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


class NotificationBulkUpdate(BaseModel):
    """Schema for bulk updating notifications."""

    notification_ids: List[UUID] = Field(
        ...,
        min_length=1,
        description="List of notification IDs to update",
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
