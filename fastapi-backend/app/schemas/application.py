"""Pydantic schemas for Application model validation."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OwnershipType(str, Enum):
    """Ownership type enumeration for application access."""

    CREATED = "created"
    INVITED = "invited"


class ApplicationBase(BaseModel):
    """Base schema with common application fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Application name",
        examples=["My Project Portfolio"],
    )
    description: Optional[str] = Field(
        None,
        description="Application description",
        examples=["A collection of related projects"],
    )


class ApplicationCreate(ApplicationBase):
    """Schema for creating a new application."""

    pass


class ApplicationUpdate(BaseModel):
    """Schema for updating an application."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Application name",
    )
    description: Optional[str] = Field(
        None,
        description="Application description",
    )


class ApplicationResponse(ApplicationBase):
    """Schema for application response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique application identifier",
    )
    owner_id: Optional[UUID] = Field(
        None,
        description="ID of the application owner",
    )
    created_at: datetime = Field(
        ...,
        description="When the application was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When the application was last updated",
    )


class ApplicationWithProjects(ApplicationResponse):
    """Schema for application response with projects count."""

    projects_count: int = Field(
        0,
        description="Number of projects in this application",
    )
    ownership_type: Optional[OwnershipType] = Field(
        None,
        description="Whether the user created this application or was invited",
    )
    user_role: Optional[str] = Field(
        None,
        description="The current user's role in this application (owner, editor, viewer)",
    )
