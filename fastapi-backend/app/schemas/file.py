"""Pydantic schemas for Attachment/File model validation."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    """Entity type enumeration for polymorphic attachments."""

    TASK = "task"
    COMMENT = "comment"
    DOCUMENT = "document"


class AttachmentBase(BaseModel):
    """Base schema with common attachment fields."""

    file_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Original file name",
        examples=["document.pdf", "screenshot.png"],
    )
    file_type: Optional[str] = Field(
        None,
        max_length=100,
        description="MIME type of the file",
        examples=["application/pdf", "image/png"],
    )
    file_size: Optional[int] = Field(
        None,
        ge=0,
        description="File size in bytes",
        examples=[1024, 102400],
    )


class AttachmentCreate(AttachmentBase):
    """Schema for creating a new attachment record."""

    minio_bucket: Optional[str] = Field(
        None,
        max_length=100,
        description="MinIO bucket name",
        examples=["pm-attachments"],
    )
    minio_key: Optional[str] = Field(
        None,
        max_length=500,
        description="MinIO object key (path)",
        examples=["tasks/uuid/document.pdf"],
    )
    entity_type: Optional[EntityType] = Field(
        None,
        description="Type of entity this is attached to",
        examples=["task", "comment", "document"],
    )
    entity_id: Optional[UUID] = Field(
        None,
        description="ID of the entity this is attached to",
    )
    task_id: Optional[UUID] = Field(
        None,
        description="ID of the task (when attaching to a task)",
    )
    comment_id: Optional[UUID] = Field(
        None,
        description="ID of the comment (when attaching to a comment)",
    )


class AttachmentUpdate(BaseModel):
    """Schema for updating an attachment."""

    file_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Original file name",
    )


class AttachmentResponse(AttachmentBase):
    """Schema for attachment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique attachment identifier",
    )
    minio_bucket: Optional[str] = Field(
        None,
        description="MinIO bucket name",
    )
    minio_key: Optional[str] = Field(
        None,
        description="MinIO object key (path)",
    )
    entity_type: Optional[str] = Field(
        None,
        description="Type of entity this is attached to",
    )
    entity_id: Optional[UUID] = Field(
        None,
        description="ID of the entity this is attached to",
    )
    task_id: Optional[UUID] = Field(
        None,
        description="ID of the associated task",
    )
    comment_id: Optional[UUID] = Field(
        None,
        description="ID of the associated comment",
    )
    uploaded_by: Optional[UUID] = Field(
        None,
        description="ID of the user who uploaded the file",
    )
    created_at: datetime = Field(
        ...,
        description="When the attachment was created",
    )


class FileUploadResponse(BaseModel):
    """Schema for file upload response with presigned URL."""

    attachment: AttachmentResponse = Field(
        ...,
        description="Created attachment record",
    )
    upload_url: Optional[str] = Field(
        None,
        description="Presigned URL for uploading the file",
    )


class FileDownloadResponse(BaseModel):
    """Schema for file download response with presigned URL."""

    attachment: AttachmentResponse = Field(
        ...,
        description="Attachment record",
    )
    download_url: str = Field(
        ...,
        description="Presigned URL for downloading the file",
    )


class BatchDownloadUrlsRequest(BaseModel):
    """Schema for batch download URLs request."""

    ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=50,  # Limit batch size to prevent abuse
        description="List of attachment IDs to get download URLs for",
    )
