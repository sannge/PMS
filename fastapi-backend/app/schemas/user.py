"""Pydantic schemas for User model validation."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Base schema with common user fields."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
        examples=["user@example.com"],
    )
    display_name: Optional[str] = Field(
        None,
        max_length=100,
        description="User's display name",
        examples=["John Doe"],
    )


class UserCreate(UserBase):
    """Schema for creating a new user (registration)."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="User's password (will be hashed)",
        examples=["SecureP@ssw0rd!"],
    )


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    display_name: Optional[str] = Field(
        None,
        max_length=100,
        description="User's display name",
    )
    avatar_url: Optional[str] = Field(
        None,
        max_length=500,
        description="URL to user's avatar image",
    )


class UserResponse(UserBase):
    """Schema for user response (public data only)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Unique user identifier",
    )
    avatar_url: Optional[str] = Field(
        None,
        description="URL to user's avatar image",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the user was created",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the user was last updated",
    )


class UserInDB(UserResponse):
    """Schema for user data including password hash (internal use only)."""

    password_hash: str = Field(
        ...,
        description="Hashed password (never expose this)",
    )
