"""Pydantic schemas for OAuth subscription connection endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class OAuthInitiateRequest(BaseModel):
    """Request to initiate an OAuth flow with a provider."""

    provider_type: Literal["openai", "anthropic"] = Field(
        ...,
        description="AI provider to connect via OAuth",
    )
    redirect_uri: str = Field(
        ...,
        max_length=2048,
        description="Electron localhost callback URL",
    )


class OAuthInitiateResponse(BaseModel):
    """Response with the OAuth authorization URL to open."""

    auth_url: str = Field(
        ...,
        description="Full URL to open in browser for authorization",
    )
    state: str = Field(
        ...,
        description="State token for CSRF validation",
    )
    expires_in: int = Field(
        600,
        description="State token validity in seconds",
    )


class OAuthCallbackRequest(BaseModel):
    """Request containing the OAuth callback parameters."""

    provider_type: Literal["openai", "anthropic"] = Field(
        ...,
        description="AI provider that issued the callback",
    )
    code: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Authorization code from provider",
    )
    state: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="State token for CSRF validation",
    )
    redirect_uri: str = Field(
        ...,
        max_length=2048,
        description="Must match the redirect_uri from initiate",
    )


class OAuthTokenResponse(BaseModel):
    """Internal token response -- never returned to client."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int = 3600
    scope: Optional[str] = None


class OAuthConnectionStatus(BaseModel):
    """Status of a user's OAuth connection (never includes tokens)."""

    connected: bool = Field(
        ...,
        description="Whether the user has an active OAuth connection",
    )
    provider_type: Optional[str] = Field(
        None,
        description="Connected provider type",
    )
    auth_method: Optional[Literal["api_key", "oauth"]] = Field(
        None,
        description="Authentication method of the connection",
    )
    provider_user_id: Optional[str] = Field(
        None,
        description="Provider's user ID (if available)",
    )
    connected_at: Optional[datetime] = Field(
        None,
        description="When the connection was established",
    )
    token_expires_at: Optional[datetime] = Field(
        None,
        description="When the OAuth access token expires",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes granted",
    )


class OAuthDisconnectResponse(BaseModel):
    """Response after disconnecting an OAuth provider."""

    disconnected: bool = Field(
        ...,
        description="Whether the disconnection was successful",
    )
    fallback: str = Field(
        ...,
        description="What the user falls back to after disconnect",
    )
