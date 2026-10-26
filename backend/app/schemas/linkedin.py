"""Pydantic schemas for LinkedIn integration endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class LinkedInStatusResponse(BaseModel):
    """
    Public integration status returned to frontend.
    Strictly redacted: tokens and client secrets are NEVER included in response payloads.
    """
    configured: bool = Field(..., description="Whether LinkedIn OAuth application credentials are configured on the backend.")
    connected: bool = Field(..., description="Whether this organization has an active, valid connected LinkedIn account.")
    status: str = Field(..., description="Status string: 'connected', 'disconnected', 'expired', or 'not_configured'.")
    member_id: Optional[str] = Field(default=None, description="LinkedIn member unique identifier (OpenID sub).")
    member_name: Optional[str] = Field(default=None, description="Connected member full name.")
    member_email: Optional[str] = Field(default=None, description="Connected member email address.")
    profile_picture_url: Optional[str] = Field(default=None, description="Connected member profile photo URL.")
    connected_at: Optional[datetime] = Field(default=None, description="Timestamp when account was authorized.")
    expires_at: Optional[datetime] = Field(default=None, description="Timestamp when the access token expires.")
    scopes: List[str] = Field(default_factory=list, description="List of granted OAuth scopes.")
    message: str = Field(..., description="Human-readable status summary.")


class LinkedInAuthorizeResponse(BaseModel):
    """Response returned when initiating LinkedIn OAuth flow."""
    authorization_url: str = Field(..., description="Target LinkedIn authorization URL.")
    state: str = Field(..., description="Cryptographically secure OAuth state parameter.")


class LinkedInDisconnectResponse(BaseModel):
    """Response returned when disconnecting LinkedIn integration."""
    success: bool = Field(..., description="Whether disconnection succeeded.")
    message: str = Field(..., description="Status message.")


class LinkedInCallbackResponse(BaseModel):
    """Direct API response for programmatic OAuth callback execution."""
    success: bool = Field(...)
    status: str = Field(...)
    member_id: Optional[str] = Field(default=None)
    member_name: Optional[str] = Field(default=None)
    message: str = Field(...)
