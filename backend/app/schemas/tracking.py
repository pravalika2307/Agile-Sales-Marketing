"""Outreach email tracking and response event Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrackingEventCreate(BaseModel):
    """Payload for recording an internal tracking event."""
    event_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional safe event metadata payload (e.g. user-agent, url, bounce reason)",
    )


class TrackingEventResponse(BaseModel):
    """Safe public representation of a recorded outreach tracking event."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outreach_id: uuid.UUID
    event_type: str
    event_metadata: Optional[Dict[str, Any]] = None
    occurred_at: datetime
    created_at: datetime


class InboundReplyCreate(BaseModel):
    """Payload for inbound email reply webhook and association."""
    from_email: str = Field(..., description="Sender email address")
    to_email: Optional[str] = Field(None, description="Recipient / to email address")
    subject: Optional[str] = Field(None, description="Reply subject line")
    body: Optional[str] = Field(None, description="Reply body text")
    in_reply_to: Optional[str] = Field(None, description="In-Reply-To header / message ID")
    references: Optional[str] = Field(None, description="References header / message IDs")
    provider_message_id: Optional[str] = Field(None, description="Provider message ID of the inbound email")
    raw_payload: Optional[Dict[str, Any]] = Field(None, description="Optional raw webhook payload")


class InboundReplyResponse(BaseModel):
    """Result of inbound reply association."""
    status: str
    outreach_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    campaign_id: Optional[uuid.UUID] = None
    event_id: uuid.UUID
    event_type: str = "replied"
    from_email: str
    subject: Optional[str] = None
