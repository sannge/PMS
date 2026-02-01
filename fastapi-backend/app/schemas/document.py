"""Pydantic schemas for Document model validation."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Schema for creating a new document."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Document title",
        examples=["Getting Started Guide"],
    )
    scope: Literal["application", "project", "personal"] = Field(
        ...,
        description="Scope type determining which FK to set",
    )
    scope_id: UUID = Field(
        ...,
        description="ID of the application, project, or user (personal scope)",
    )
    folder_id: Optional[UUID] = Field(
        None,
        description="Folder to place the document in (null = unfiled)",
    )
    content_json: Optional[str] = Field(
        None,
        description="TipTap JSON content",
    )


class DocumentUpdate(BaseModel):
    """Schema for updating a document.

    Uses a sentinel approach for folder_id: if omitted (None), folder is not changed.
    To move to unfiled, explicitly pass folder_id as null in the JSON body.
    """

    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Document title",
    )
    folder_id: Optional[UUID] = Field(
        None,
        description="Move document to this folder (null = unfiled)",
    )
    content_json: Optional[str] = Field(
        None,
        description="TipTap JSON content",
    )
    sort_order: Optional[int] = Field(
        None,
        description="Sort position within folder",
    )
    row_version: int = Field(
        ...,
        ge=1,
        description="Current row_version for optimistic concurrency check",
    )


class DocumentResponse(BaseModel):
    """Schema for full document response (includes content)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    folder_id: Optional[UUID] = None
    title: str
    content_json: Optional[str] = None
    content_markdown: Optional[str] = None
    content_plain: Optional[str] = None
    sort_order: int = 0
    created_by: Optional[UUID] = None
    row_version: int = 1
    schema_version: int = 1
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DocumentListItem(BaseModel):
    """Schema for document list item (no content fields for performance)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    folder_id: Optional[UUID] = None
    sort_order: int = 0
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    """Paginated document list response with cursor."""

    items: list[DocumentListItem] = Field(
        ...,
        description="List of documents in this page",
    )
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for fetching the next page (null if no more items)",
    )
