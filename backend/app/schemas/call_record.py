"""Pydantic schemas for Retell voice call webhook and CallRecord management."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RetellCallVariables(BaseModel):
    """Structured variables extracted from Retell voice calls."""
    lead_full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    interest_level: Optional[str] = None
    call_outcome: Optional[str] = None
    meeting_requested: bool = False
    callback_requested: bool = False
    do_not_contact: bool = False


class FollowUpDecision(BaseModel):
    """Result of evaluating post-call deterministic email rules."""
    should_send_email: bool
    followup_type: str  # "interested_followup", "meeting_followup", "callback_followup", "qualified_followup", "none"
    reason: str
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None


class CallRecordResponse(BaseModel):
    """API response schema for a stored CallRecord."""
    id: uuid.UUID
    organization_id: uuid.UUID
    call_id: str
    agent_id: str
    direction: str
    call_status: str
    call_outcome: Optional[str] = None
    caller_phone: Optional[str] = None
    to_phone: Optional[str] = None
    duration_ms: Optional[int] = None
    disconnection_reason: Optional[str] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None
    collected_variables: Optional[Dict[str, Any]] = None
    call_analysis: Optional[Dict[str, Any]] = None
    followup_status: str
    followup_reason: Optional[str] = None
    followup_email_id: Optional[uuid.UUID] = None
    followup_idempotency_key: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    analyzed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RetellWebhookResponse(BaseModel):
    """Response returned to Retell webhook caller."""
    status: str
    call_id: str
    event: str
    followup_status: Optional[str] = None
    followup_reason: Optional[str] = None
    followup_email_id: Optional[str] = None
    duplicate: bool = False
