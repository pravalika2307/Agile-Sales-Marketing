"""Outreach and OutreachEvent Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.outreach import (
    ALLOWED_OUTREACH_CHANNELS,
    ALLOWED_OUTREACH_EVENT_TYPES,
    ALLOWED_OUTREACH_STATUSES,
)


class OutreachCreate(BaseModel):
    """Payload to create an outreach draft."""
    campaign_id: uuid.UUID = Field(..., description="Target Campaign ID")
    contact_id: uuid.UUID = Field(..., description="Target Contact ID")
    campaign_contact_id: Optional[uuid.UUID] = Field(None, description="Existing CampaignContact enrollment ID")
    channel: str = Field("email", description="Outreach channel (e.g. email)")
    subject: Optional[str] = Field(None, max_length=255, description="Subject line for email outreach")
    body: Optional[str] = Field(None, description="Body content of the message")
    scheduled_at: Optional[datetime] = Field(None, description="Optional scheduled send timestamp")

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_OUTREACH_CHANNELS:
            raise ValueError(
                f"Invalid outreach channel '{v}'. Allowed channels: {sorted(list(ALLOWED_OUTREACH_CHANNELS))}"
            )
        return clean


class OutreachUpdate(BaseModel):
    """Payload to update an editable outreach draft or scheduled message."""
    subject: Optional[str] = Field(None, max_length=255)
    body: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class OutreachEventResponse(BaseModel):
    """Public representation of an outreach state change or audit event."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_id: uuid.UUID
    event_type: str
    event_metadata: Optional[Dict[str, Any]] = None
    occurred_at: datetime
    created_at: datetime


class CallRecordInfoResponse(BaseModel):
    """Safe public representation of a CallRecord linked to Outreach."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    call_id: str
    agent_id: Optional[str] = None
    direction: str
    call_status: str
    call_outcome: Optional[str] = None
    caller_phone: Optional[str] = None
    to_phone: Optional[str] = None
    duration_ms: Optional[int] = None
    disconnection_reason: Optional[str] = None
    summary: Optional[str] = None
    followup_status: Optional[str] = None
    followup_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    analyzed_at: Optional[datetime] = None


class OutreachResponse(BaseModel):
    """Complete safe public representation of an Outreach item."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_id: Optional[uuid.UUID] = None
    recipient: Optional[str] = None
    recipient_email: Optional[str] = None
    organization_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    campaign_name: Optional[str] = None
    contact_id: Optional[uuid.UUID] = None
    contact_name: Optional[str] = None
    company_name: Optional[str] = None
    campaign_contact_id: Optional[uuid.UUID] = None
    call_record_id: Optional[uuid.UUID] = None
    channel: str
    status: str
    subject: Optional[str] = None
    body: Optional[str] = None
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    first_delivered_at: Optional[datetime] = None
    first_opened_at: Optional[datetime] = None
    first_clicked_at: Optional[datetime] = None
    first_replied_at: Optional[datetime] = None
    first_bounced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    call_record: Optional[CallRecordInfoResponse] = None
    events: Optional[List[OutreachEventResponse]] = None


