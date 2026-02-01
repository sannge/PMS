"""Pydantic schemas for DocumentTag model validation."""

import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagCreate(BaseModel):
    """Schema for creating a new tag."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Tag display name",
        examples=["backend"],
    )
    color: Optional[str] = Field(
        None,
        description="Hex color code for UI display (e.g. '#FF5733')",
        examples=["#FF5733"],
    )
    scope: Literal["application", "personal"] = Field(
        ...,
        description="Scope type: 'application' for app/project docs, 'personal' for user docs",
    )
    scope_id: UUID = Field(
        ...,
        description="ID of the application or user",
    )

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate hex color format."""
        if v is not None and not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("Color must be a valid hex color code (e.g. '#FF5733')")
        return v


class TagUpdate(BaseModel):
    """Schema for updating a tag."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Tag display name",
    )
    color: Optional[str] = Field(
        None,
        description="Hex color code for UI display",
    )

    @field_validator("color")
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate hex color format."""
        if v is not None and not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("Color must be a valid hex color code (e.g. '#FF5733')")
        return v


class TagResponse(BaseModel):
    """Schema for tag response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: Optional[str] = None
    application_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    created_at: datetime


class TagAssignment(BaseModel):
    """Schema for assigning a tag to a document."""

    tag_id: UUID = Field(
        ...,
        description="ID of the tag to assign",
    )


class TagAssignmentResponse(BaseModel):
    """Schema for tag assignment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    tag_id: UUID
    created_at: datetime
