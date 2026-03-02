"""Pydantic schemas for ImportJob model validation."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImportJobCreate(BaseModel):
    """Schema for creating a new import job (request body)."""

    file_name: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Original filename of the uploaded file",
        examples=["quarterly-report.pdf"],
    )
    file_type: Literal["pdf", "docx", "pptx"] = Field(
        ...,
        description="File format",
    )
    file_size: int = Field(
        ...,
        gt=0,
        description="File size in bytes",
    )
    scope: Literal["application", "project", "personal"] = Field(
        ...,
        description="Target scope for the imported document",
    )
    scope_id: UUID = Field(
        ...,
        description="UUID of the application, project, or user",
    )
    folder_id: Optional[UUID] = Field(
        None,
        description="Target folder UUID (null = unfiled)",
    )


class ImportJobResponse(BaseModel):
    """Schema for import job response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    file_name: str
    file_type: Literal["pdf", "docx", "pptx"]
    file_size: int
    title: Optional[str] = None
    status: Literal["pending", "processing", "completed", "failed"]
    progress_pct: int
    document_id: Optional[UUID] = None
    scope: Literal["application", "project", "personal"]
    scope_id: UUID
    folder_id: Optional[UUID] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ImportJobListResponse(BaseModel):
    """Paginated import job list response."""

    items: list[ImportJobResponse]
    total: int
    limit: int
    offset: int
