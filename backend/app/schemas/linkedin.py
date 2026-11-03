"""Pydantic schemas for LinkedIn integration endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.core.normalization import normalize_linkedin_profile_url


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


import uuid
from typing import Any, Dict


class LinkedInCapabilityItem(BaseModel):
    """Specification of an individual LinkedIn API capability."""
    status: str = Field(..., description="'available', 'restricted', or 'unsupported'")
    scope_required: str = Field(..., description="OAuth scope or LinkedIn partner product required")
    scope_granted: bool = Field(..., description="Whether required scope is present in active connection")
    description: str = Field(..., description="Capability explanation and compliance notes")
    assisted_alternative: Optional[str] = Field(default=None, description="Assisted workflow behavior if API is restricted")


class LinkedInCapabilitiesResponse(BaseModel):
    """Complete LinkedIn API capability matrix with compliance and scope transparency."""
    configured: bool
    connected: bool
    member_id: Optional[str] = None
    member_name: Optional[str] = None
    granted_scopes: List[str] = Field(default_factory=list)
    capabilities: Dict[str, LinkedInCapabilityItem]
    workflow_mode: str = Field(default="assisted", description="'assisted' safe workflow")
    booking_url: str = Field(default="https://cal.com/agilereceivables/30min")
    connection_note_limit: int = 300


class LinkedInAssistedQueueItem(BaseModel):
    """Enrolled campaign contact ready for assisted LinkedIn outreach."""
    campaign_contact_id: uuid.UUID
    contact_id: uuid.UUID
    full_name: str
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_profile_url: Optional[str] = None
    has_linkedin_profile_url: bool = False
    lead_id: Optional[uuid.UUID] = None
    search_url: str
    connection_note: str
    followup_message: str
    booking_url: str
    outreach_id: Optional[uuid.UUID] = None
    outreach_status: str  # "pending", "copied", "sent"
    sent_at: Optional[datetime] = None


class LinkedInAssistedQueueResponse(BaseModel):
    """List of pending and completed assisted LinkedIn outreach items for a campaign."""
    campaign_id: uuid.UUID
    total: int
    pending_count: int
    completed_count: int
    items: List[LinkedInAssistedQueueItem]


class LinkedInConfirmActionRequest(BaseModel):
    """Request to manually confirm that a LinkedIn connection request or message was sent."""
    campaign_contact_id: uuid.UUID
    action_type: str = Field(default="connection_request", description="'connection_request' or 'direct_message'")
    notes: Optional[str] = Field(default=None, description="Optional manual execution notes")


class LinkedInConfirmActionResponse(BaseModel):
    """Response confirming recorded manual outreach action."""
    success: bool
    outreach_id: uuid.UUID
    status: str
    confirmed_at: datetime
    message: str

class LinkedInUpdateProspectProfileRequest(BaseModel):
    """Request to update a prospect LinkedIn profile URL."""
    linkedin_profile_url: str = Field(..., min_length=5, max_length=500, description="LinkedIn profile URL")

    @field_validator("linkedin_profile_url")
    @classmethod
    def validate_linkedin_profile_url(cls, v: str) -> str:
        norm = normalize_linkedin_profile_url(v)
        if not norm:
            raise ValueError("LinkedIn profile URL cannot be empty.")
        return norm


class LinkedInUpdateProspectProfileResponse(BaseModel):
    """Response confirming updated prospect LinkedIn profile URL."""
    success: bool
    campaign_contact_id: uuid.UUID
    contact_id: uuid.UUID
    linkedin_profile_url: str
    message: str

