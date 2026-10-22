"""Pydantic schemas for Inbound Email and Microsoft Graph Integration."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class MatchedEntityInfo(BaseModel):
    """Snapshot details of CRM Contact, Lead, or Company matched to incoming email."""
    model_config = ConfigDict(from_attributes=True)

    contact_id: Optional[uuid.UUID] = None
    contact_name: Optional[str] = None
    contact_job_title: Optional[str] = None
    contact_lead_status: Optional[str] = None

    lead_id: Optional[uuid.UUID] = None
    lead_score: Optional[int] = None
    lead_temperature: Optional[str] = None
    lead_company_name: Optional[str] = None

    company_id: Optional[uuid.UUID] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None


class InboundEmailResponse(BaseModel):
    """Summary representation of an ingested inbound email message."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    graph_message_id: str
    graph_conversation_id: Optional[str] = None
    internet_message_id: Optional[str] = None
    sender_email: str
    sender_name: Optional[str] = None
    recipient_email: str
    subject: Optional[str] = None
    body_preview: Optional[str] = None
    received_at: datetime
    is_read: bool
    has_attachments: bool
    sync_status: str
    manual_review_status: str
    matched_contact_id: Optional[uuid.UUID] = None
    matched_lead_id: Optional[uuid.UUID] = None
    matched_company_id: Optional[uuid.UUID] = None
    matched_entity: Optional[MatchedEntityInfo] = None
    created_at: datetime


class InboundEmailDetailResponse(InboundEmailResponse):
    """Detailed representation of an ingested inbound email, including body and untrusted guard."""
    body_content: Optional[str] = None
    body_content_type: str = "html"
    review_notes: Optional[str] = None
    raw_metadata: Optional[Dict[str, Any]] = None
    is_untrusted_content: bool = Field(
        default=True,
        description="Flag indicating external message content must be treated as untrusted input.",
    )


class InboundEmailListResponse(BaseModel):
    """Paginated list of inbound emails with status metrics."""
    items: List[InboundEmailResponse]
    total: int
    unmatched_count: int
    unread_count: int
    page: int
    limit: int


class ManualReviewUpdatePayload(BaseModel):
    """Payload to update the manual review state of an unmatched inbound email."""
    status: Literal["reviewed", "dismissed", "archived", "pending"]
    review_notes: Optional[str] = Field(None, max_length=2000)


class GraphSyncTriggerRequest(BaseModel):
    """Parameters to trigger a manual synchronization of the support mailbox."""
    max_messages: Optional[int] = Field(50, ge=1, le=250, description="Max messages to fetch")
    folder: Optional[str] = Field("Inbox", description="Mail folder to inspect (defaults to Inbox)")


class GraphSyncResultResponse(BaseModel):
    """Results of a Microsoft Graph mailbox synchronization run."""
    model_config = ConfigDict(from_attributes=True)

    sync_run_id: uuid.UUID
    organization_id: uuid.UUID
    mailbox: str
    status: str
    messages_fetched: int
    messages_imported: int
    messages_matched: int
    messages_unmatched: int
    messages_skipped: int
    checkpoint_delta_link: Optional[str] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class GraphCheckpointStatusResponse(BaseModel):
    """Synchronization checkpoint state and active concurrency lock status."""
    model_config = ConfigDict(from_attributes=True)

    mailbox: str
    has_checkpoint: bool
    is_syncing: bool
    last_sync_status: str
    last_successful_sync_at: Optional[datetime] = None
    sync_started_at: Optional[datetime] = None
    total_imported: int = 0
    error_message: Optional[str] = None


class GraphConfigStatusResponse(BaseModel):
    """Configuration and safety inspection response for Microsoft Graph integration."""
    configured: bool
    enabled: bool
    auto_sync_enabled: bool = False
    sync_interval_minutes: int = 10
    support_mailbox: str
    auth_flow: str
    approved_mailbox_only: bool = True
    permissions_required: List[str]
    mode: str
    message: str
