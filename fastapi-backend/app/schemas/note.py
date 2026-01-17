"""Pydantic schemas for Note model validation."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NoteBase(BaseModel):
    """Base schema with common note fields."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Note title",
        examples=["Meeting Notes", "Project Ideas"],
    )
    content: Optional[str] = Field(
        None,
        description="Rich text content (HTML or JSON)",
        examples=["<p>Meeting notes from today...</p>"],
    )
    tab_order: int = Field(
        0,
        ge=0,
        description="Order of the note in tab bar",
        examples=[0, 1, 2],
    )


class NoteCreate(NoteBase):
    """Schema for creating a new note."""

    application_id: UUID = Field(
        ...,
        description="ID of the parent application",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent note (for hierarchy)",
    )


class NoteUpdate(BaseModel):
    """Schema for updating a note."""

    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Note title",
    )
    content: Optional[str] = Field(
        None,
        description="Rich text content (HTML or JSON)",
    )
    tab_order: Optional[int] = Field(
        None,
        ge=0,
        description="Order of the note in tab bar",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent note",
    )


class NoteResponse(NoteBase):
    """Schema for note response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique note identifier",
    )
    application_id: UUID = Field(
        ...,
        description="ID of the parent application",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="ID of the parent note",
    )
    created_by: Optional[UUID] = Field(
        None,
        description="ID of the user who created the note",
    )
    created_at: datetime = Field(
        ...,
        description="When the note was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When the note was last updated",
    )


class NoteWithChildren(NoteResponse):
    """Schema for note response with children count."""

    children_count: int = Field(
        0,
        description="Number of child notes",
    )


class NoteTree(NoteResponse):
    """Schema for hierarchical note tree structure."""

    children: List["NoteTree"] = Field(
        default_factory=list,
        description="Child notes in the hierarchy",
    )


# Required for self-referential Pydantic models
NoteTree.model_rebuild()
