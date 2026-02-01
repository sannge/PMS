"""Pydantic schemas for DocumentFolder model validation."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FolderCreate(BaseModel):
    """Schema for creating a new folder."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Folder name",
        examples=["Architecture Docs"],
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="Parent folder ID (null = root level)",
    )
    scope: Literal["application", "project", "personal"] = Field(
        ...,
        description="Scope type determining which FK to set",
    )
    scope_id: UUID = Field(
        ...,
        description="ID of the application, project, or user (personal scope)",
    )


class FolderUpdate(BaseModel):
    """Schema for updating a folder."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Folder name",
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="Move folder under new parent (triggers materialized path recalculation)",
    )
    sort_order: Optional[int] = Field(
        None,
        description="Sort position within siblings",
    )


class FolderResponse(BaseModel):
    """Schema for folder response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: Optional[UUID] = None
    materialized_path: str = "/"
    depth: int = 0
    name: str
    sort_order: int = 0
    application_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class FolderTreeNode(BaseModel):
    """Schema for a node in the folder tree response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: Optional[UUID] = None
    materialized_path: str = "/"
    depth: int = 0
    sort_order: int = 0
    children: list["FolderTreeNode"] = Field(default_factory=list)
    document_count: int = 0


# Required for self-referential model
FolderTreeNode.model_rebuild()
