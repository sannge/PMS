"""Pydantic schemas for document lock API."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LockHolder(BaseModel):
    """Schema for lock holder information."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str = Field(..., description="UUID of the lock holder")
    user_name: str = Field(..., description="Display name of the lock holder")
    acquired_at: Optional[float] = Field(
        None, description="Unix timestamp when lock was acquired"
    )


class DocumentLockResponse(BaseModel):
    """Schema for document lock status response."""

    locked: bool = Field(..., description="Whether the document is currently locked")
    lock_holder: Optional[LockHolder] = Field(
        None, description="Lock holder info if locked"
    )
