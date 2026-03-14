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
    email_verified: bool = Field(
        False,
        description="Whether the user's email is verified",
    )
    is_developer: bool = Field(
        False,
        description="Whether the user has developer access for AI configuration",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="When the user was created",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="When the user was last updated",
    )


class RegisterResponse(BaseModel):
    """Response returned after successful registration."""

    message: str = Field(
        ...,
        description="Confirmation message",
    )
    email: EmailStr = Field(
        ...,
        description="Email address the verification code was sent to",
    )


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str = Field(..., description="Response message")


class VerifyEmailRequest(BaseModel):
    """Request to verify email with a 6-digit code."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit verification code",
    )


class ResendVerificationRequest(BaseModel):
    """Request to resend verification code."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )


class ForgotPasswordRequest(BaseModel):
    """Request to initiate password reset."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )


class ResetPasswordRequest(BaseModel):
    """Request to reset password with code."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit reset code",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password",
    )


class Login2FAResponse(BaseModel):
    """Response when login requires 2FA code verification."""

    requires_2fa: bool = Field(
        True,
        description="Always True, indicating 2FA is needed",
    )
    email: str = Field(
        ...,
        description="Email address the verification code was sent to",
    )
    message: str = Field(
        "Verification code sent to your email",
        description="User-facing message",
    )


class TokenWithRefresh(BaseModel):
    """Token response with both access and refresh tokens."""

    access_token: str = Field(..., description="Short-lived JWT access token")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token")
    token_type: str = Field("bearer", description="Token type")


class RefreshTokenRequest(BaseModel):
    """Request to refresh an access token."""

    refresh_token: str = Field(..., description="Current refresh token")


class RevokeTokenRequest(BaseModel):
    """Request to revoke a refresh token."""

    refresh_token: str = Field(..., description="Refresh token to revoke")


class VerifyLoginRequest(BaseModel):
    """Request to verify a login 2FA code."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit verification code",
    )


class UserInDB(UserResponse):
    """Schema for user data including password hash (internal use only)."""

    password_hash: str = Field(
        ...,
        description="Hashed password (never expose this)",
    )
