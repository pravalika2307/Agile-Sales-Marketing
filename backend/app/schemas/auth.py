"""Authentication request and response schemas."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import OrganizationResponse, UserResponse


class RegisterRequest(BaseModel):
    """Payload for self-service user and organization registration."""
    email: EmailStr = Field(..., description="User's work email address")
    password: str = Field(..., min_length=8, description="Password (at least 8 characters)")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name of user")
    organization_name: str = Field(..., min_length=1, max_length=255, description="Name of company/organization")


class LoginRequest(BaseModel):
    """Payload for user authentication."""
    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")


class RefreshTokenRequest(BaseModel):
    """Payload for issuing a new access token using a valid refresh token."""
    refresh_token: str = Field(..., description="Signed refresh token")


class TokenResponse(BaseModel):
    """Access and refresh token pair."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Combined response returning authenticated user details and active tokens."""
    user: UserResponse
    tokens: TokenResponse
    organization: Optional[OrganizationResponse] = None
