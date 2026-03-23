"""Pydantic schemas for FolderFile model validation."""

import re
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FolderFileResponse(BaseModel):
    """Schema for folder file API response (excludes internal storage paths)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folder_id: Optional[UUID] = None
    application_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    original_name: str
    display_name: str
    mime_type: str = "application/octet-stream"
    file_size: int
    file_extension: str
    has_thumbnail: bool = False
    extraction_status: Literal["pending", "processing", "completed", "failed", "unsupported"] = "pending"
    extracted_metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_status: Literal["none", "stale", "syncing", "synced", "failed"] = "none"
    embedding_updated_at: Optional[datetime] = None
    sort_order: int = 0
    created_by: Optional[UUID] = None
    row_version: int = 1
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _set_has_thumbnail(cls, values: Any) -> Any:
        """Derive has_thumbnail from the ORM thumbnail_key attribute."""
        if isinstance(values, dict):
            values["has_thumbnail"] = bool(values.get("thumbnail_key"))
            return values
        # ORM model with from_attributes — read thumbnail_key directly
        tk = getattr(values, "thumbnail_key", None)
        try:
            values.__dict__["has_thumbnail"] = bool(tk)
        except (TypeError, AttributeError):
            pass
        return values


class FolderFileInternalResponse(FolderFileResponse):
    """Extended schema for internal/worker use. Includes storage paths and content."""

    storage_bucket: str
    storage_key: str
    content_plain: Optional[str] = None


class FolderFileListItem(BaseModel):
    """Schema for lightweight file list item (tree/sidebar views)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_name: str
    display_name: str
    file_extension: str
    mime_type: str
    file_size: int
    extraction_status: Literal["pending", "processing", "completed", "failed", "unsupported"] = "pending"
    embedding_status: Literal["none", "stale", "syncing", "synced", "failed"] = "none"
    sort_order: int = 0
    folder_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    row_version: int = 1
    created_at: datetime
    updated_at: datetime


class FolderFileUpdate(BaseModel):
    """Schema for updating a folder file.

    Supports renaming, moving to another folder, and reordering.
    row_version is required for optimistic concurrency control.
    """

    display_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New display name for the file",
    )
    folder_id: Optional[UUID] = Field(
        None,
        description="Move file to this folder",
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

    @field_validator("display_name", mode="before")
    @classmethod
    def sanitize_display_name(cls, v: str | None) -> str | None:
        """Strip null bytes, control characters, angle brackets, and path separators."""
        if v is None:
            return v
        # Remove null bytes, C0/C1 control chars (except tab/newline), DEL,
        # and angle brackets that could allow HTML injection.
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f<>]", "", v)
        # F-123: Remove path separators to prevent directory traversal
        sanitized = sanitized.replace("/", "").replace("\\", "")
        return sanitized.strip()


class FolderFileListResponse(BaseModel):
    """Wrapper response for list endpoint (CRIT-3: frontend expects {items: []})."""

    items: list[FolderFileListItem]


class FolderFileDownloadUrlResponse(BaseModel):
    """Schema for download URL endpoint response."""

    file_id: str
    display_name: str
    original_name: str
    download_url: str


class FolderFileReplaceResponse(BaseModel):
    """Schema for file replace (re-upload) response."""

    id: UUID
    display_name: str
    extraction_status: Literal["pending", "processing", "completed", "failed", "unsupported"] = "pending"
    message: str = "File replaced successfully"
