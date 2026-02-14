"""Pydantic schemas for Comment and Mention models."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommentAttachmentResponse(BaseModel):
    """Schema for attachment info in comment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique attachment identifier")
    file_name: str = Field(..., description="Original file name")
    file_type: Optional[str] = Field(None, description="MIME type of the file")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    created_at: datetime = Field(..., description="When the attachment was created")


class MentionResponse(BaseModel):
    """Schema for mention response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique mention identifier",
    )
    user_id: UUID = Field(
        ...,
        description="ID of the mentioned user",
    )
    user_name: Optional[str] = Field(
        None,
        description="Display name of the mentioned user",
    )
    created_at: datetime = Field(
        ...,
        description="When the mention was created",
    )


class CommentCreate(BaseModel):
    """Schema for creating a new comment."""

    body_json: Optional[Dict[str, Any]] = Field(
        None,
        description="TipTap JSON content for rich text rendering",
    )
    body_text: Optional[str] = Field(
        None,
        max_length=50000,
        description="Plain text content (extracted from body_json or provided directly)",
    )
    attachment_ids: Optional[List[UUID]] = Field(
        None,
        description="List of attachment IDs to link to this comment",
    )

    @model_validator(mode="after")
    def validate_content(self) -> "CommentCreate":
        """Ensure either body_json or body_text is provided."""
        if not self.body_json and not self.body_text:
            raise ValueError("Either body_json or body_text must be provided")
        return self


class CommentUpdate(BaseModel):
    """Schema for updating a comment."""

    body_json: Optional[Dict[str, Any]] = Field(
        None,
        description="TipTap JSON content for rich text rendering",
    )
    body_text: Optional[str] = Field(
        None,
        max_length=50000,
        description="Plain text content",
    )


class CommentResponse(BaseModel):
    """Schema for comment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique comment identifier",
    )
    task_id: UUID = Field(
        ...,
        description="ID of the parent task",
    )
    author_id: UUID = Field(
        ...,
        description="ID of the comment author",
    )
    author_name: Optional[str] = Field(
        None,
        description="Display name of the author",
    )
    author_avatar_url: Optional[str] = Field(
        None,
        description="Avatar URL of the author",
    )
    body_json: Optional[Dict[str, Any]] = Field(
        None,
        description="TipTap JSON content for rich text rendering",
    )
    body_text: Optional[str] = Field(
        None,
        description="Plain text content for display and search",
    )
    is_deleted: bool = Field(
        False,
        description="Whether the comment has been soft deleted",
    )
    created_at: datetime = Field(
        ...,
        description="When the comment was created",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the comment was last updated",
    )
    mentions: List[MentionResponse] = Field(
        default_factory=list,
        description="List of @mentions in this comment",
    )
    attachments: List[CommentAttachmentResponse] = Field(
        default_factory=list,
        description="List of file attachments on this comment",
    )


class CommentListResponse(BaseModel):
    """Schema for paginated comment list response."""

    items: List[CommentResponse] = Field(
        ...,
        description="List of comments",
    )
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for fetching next page (ISO datetime string)",
    )
