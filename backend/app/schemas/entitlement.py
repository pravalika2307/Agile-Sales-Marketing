"""Entitlement and channel upgrade schemas."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_COMMUNICATION_CHANNELS = {
    "email",
    "sms",
    "voice",
    "ringless_voicemail",
    "physical_mail",
}

ENTITLEMENT_STATUSES = {
    "included",
    "available",
    "upgrade_required",
    "upgrade_requested",
    "awaiting_approval",
    "approved",
    "suspended",
}

UPGRADE_REQUEST_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "cancelled",
}


class ChannelCapabilityResponse(BaseModel):
    """Public representation of an outreach communication channel and tenant entitlement status."""
    model_config = ConfigDict(from_attributes=True)

    channel: str = Field(..., description="Unique channel key: email, sms, voice, ringless_voicemail, physical_mail")
    display_name: str = Field(..., description="Human-readable channel title")
    description: str = Field(..., description="Channel description and use case")
    status: str = Field(..., description="included, available, upgrade_required, upgrade_requested, awaiting_approval, approved, suspended")
    is_unlocked: bool = Field(..., description="Whether this channel can currently be dispatched by this tenant")
    pricing_model: str = Field(..., description="Billing mechanism (included, per-message, per-minute, per-postcard)")
    provider: str = Field(..., description="Underlying provider (AWS SES / Namecheap, Twilio, Retell AI, Poplar)")
    features: List[str] = Field(default_factory=list, description="Supported capabilities, e.g. MMS media attachments, personalization")
    limits: Dict[str, Any] = Field(default_factory=dict, description="Operational limits, e.g. char limits, segment limits")
    allocated_quota: Optional[int] = Field(None, description="Monthly allocated message/call quota if configured")
    current_usage: int = Field(0, description="Current consumption count in billing cycle")


class ChannelListResponse(BaseModel):
    """List of all available channels and their tenant entitlement statuses."""
    organization_id: uuid.UUID
    billing_status: str
    channels: List[ChannelCapabilityResponse]


class ChannelUpgradeRequestPayload(BaseModel):
    """Payload submitted by a tenant requesting channel unlock/upgrade approval."""
    channel: str = Field(..., description="Channel being requested: sms, voice, ringless_voicemail, physical_mail")
    estimated_volume: Optional[str] = Field(None, description="Expected monthly dispatch volume (e.g. 1000/month)")
    justification: Optional[str] = Field(None, description="Business justification or campaign description")

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_COMMUNICATION_CHANNELS:
            raise ValueError(
                f"Invalid channel '{v}'. Allowed channels: {sorted(list(ALLOWED_COMMUNICATION_CHANNELS))}"
            )
        if clean == "email":
            raise ValueError("Email is already included by default in your subscription plan.")
        return clean


class ChannelUpgradeRequestResponse(BaseModel):
    """Confirmation response after submitting an upgrade request."""
    request_id: Optional[uuid.UUID] = None
    organization_id: uuid.UUID
    channel: str
    status: str
    requested_at: datetime
    message: str


class UpgradeRequestDetailResponse(BaseModel):
    """Detailed representation of an upgrade request for tenant or platform administrator review."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: Optional[str] = None
    channel: str
    requesting_user_id: Optional[uuid.UUID] = None
    requesting_user_email: Optional[str] = None
    status: str
    estimated_volume: Optional[str] = None
    business_justification: Optional[str] = None
    reviewing_admin_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AdminUpgradeDecisionPayload(BaseModel):
    """Administrative decision on a pending channel upgrade request."""
    action: Literal["approve", "reject"] = Field(..., description="'approve' to unlock channel, 'reject' to decline")
    allocated_quota: Optional[int] = Field(None, description="Optional monthly unit quota assigned upon approval")
    rejection_reason: Optional[str] = Field(None, description="Required reason when rejecting an upgrade request")
    admin_notes: Optional[str] = Field(None, description="Internal notes for operations record")

    @field_validator("allocated_quota")
    @classmethod
    def validate_allocated_quota(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("Allocated monthly quota must be a positive integer greater than 0.")
        return v

    @field_validator("rejection_reason")
    @classmethod
    def validate_rejection_reason(cls, v: Optional[str], info: Any) -> Optional[str]:
        # If action is reject, justification is mandatory
        data = info.data
        if data.get("action") == "reject" and (not v or not v.strip()):
            raise ValueError("A clear rejection reason is mandatory when declining an upgrade request.")
        return v.strip() if v else None


class EntitlementAuditLogResponse(BaseModel):
    """Immutable audit trail item for entitlement actions."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    channel: str
    action: str
    actor_user_id: Optional[uuid.UUID] = None
    actor_role: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime
