"""Pydantic schemas for Checklist and ChecklistItem models."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChecklistItemCreate(BaseModel):
    """Schema for creating a new checklist item."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Item text content",
    )


class ChecklistItemUpdate(BaseModel):
    """Schema for updating a checklist item."""

    content: Optional[str] = Field(
        None,
        min_length=1,
        max_length=10000,
        description="Item text content",
    )
    is_done: Optional[bool] = Field(
        None,
        description="Completion status",
    )


class ChecklistItemResponse(BaseModel):
    """Schema for checklist item response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique item identifier",
    )
    checklist_id: UUID = Field(
        ...,
        description="ID of the parent checklist",
    )
    content: str = Field(
        ...,
        description="Item text content",
    )
    is_done: bool = Field(
        False,
        description="Completion status",
    )
    completed_by: Optional[UUID] = Field(
        None,
        description="ID of the user who completed the item",
    )
    completed_by_name: Optional[str] = Field(
        None,
        description="Display name of the user who completed the item",
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="When the item was completed",
    )
    rank: str = Field(
        ...,
        description="Lexorank for ordering within checklist",
    )
    created_at: datetime = Field(
        ...,
        description="When the item was created",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the item was last updated",
    )


class ChecklistCreate(BaseModel):
    """Schema for creating a new checklist."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Checklist name",
    )


class ChecklistUpdate(BaseModel):
    """Schema for updating a checklist."""

    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Checklist name",
    )


class ChecklistResponse(BaseModel):
    """Schema for checklist response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique checklist identifier",
    )
    task_id: UUID = Field(
        ...,
        description="ID of the parent task",
    )
    title: str = Field(
        ...,
        description="Checklist name",
    )
    rank: str = Field(
        ...,
        description="Lexorank for ordering within task",
    )
    total_items: int = Field(
        0,
        description="Total number of items in checklist",
    )
    completed_items: int = Field(
        0,
        description="Number of completed items",
    )
    progress_percent: int = Field(
        0,
        ge=0,
        le=100,
        description="Completion percentage (0-100)",
    )
    created_at: datetime = Field(
        ...,
        description="When the checklist was created",
    )
    items: List[ChecklistItemResponse] = Field(
        default_factory=list,
        description="Checklist items in rank order",
    )


class ReorderRequest(BaseModel):
    """Schema for reordering a checklist or item."""

    before_id: Optional[UUID] = Field(
        None,
        description="ID of the item/checklist to place after (null = first position)",
    )
    after_id: Optional[UUID] = Field(
        None,
        description="ID of the item/checklist to place before (null = last position)",
    )
    target_rank: Optional[str] = Field(
        None,
        description="Direct Lexorank value (alternative to before/after)",
    )
