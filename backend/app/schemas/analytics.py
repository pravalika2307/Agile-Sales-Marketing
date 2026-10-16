"""Analytics Pydantic schemas for real-data reporting."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class LeadMetrics(BaseModel):
    total_leads: int = 0
    qualified_leads: int = 0
    status_breakdown: Dict[str, int] = {}
    temperature_breakdown: Dict[str, int] = {}


class CampaignMetricsOverview(BaseModel):
    total_campaigns: int = 0
    active_campaigns: int = 0
    draft_campaigns: int = 0
    paused_campaigns: int = 0
    completed_campaigns: int = 0
    enrolled_contacts: int = 0


class OutreachMetricsOverview(BaseModel):
    total_outreach: int = 0
    draft: int = 0
    scheduled: int = 0
    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
    bounced: int = 0
    failed: int = 0
    channel_breakdown: Dict[str, int] = {}


class VoiceCallMetricsOverview(BaseModel):
    total_calls: int = 0
    completed_calls: int = 0
    average_duration_seconds: Optional[float] = None
    outcome_breakdown: Dict[str, int] = {}


class PipelineMetricsOverview(BaseModel):
    total_deals: int = 0
    open_deals: int = 0
    won_deals: int = 0
    lost_deals: int = 0
    total_pipeline_value: float = 0.0
    won_pipeline_value: float = 0.0


class CampaignPerformanceSummary(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    status: str
    enrolled_contacts_count: int = 0
    outreach_count: int = 0
    sent_count: int = 0
    delivered_count: int = 0
    opened_count: int = 0
    replied_count: int = 0
    bounced_count: int = 0


class FunnelStageMetrics(BaseModel):
    stage_id: str
    stage_name: str
    count: int = 0
    conversion_rate_from_previous: Optional[float] = None
    conversion_rate_from_top: Optional[float] = None
    channel_breakdown: Dict[str, int] = {}
    description: str = ""
    formula: Optional[str] = None
    denominator_name: Optional[str] = None


class FunnelMetrics(BaseModel):
    stages: List[FunnelStageMetrics] = []
    total_leads: int = 0
    qualified_prospects: int = 0
    contacted_prospects: int = 0
    engaged_prospects: int = 0
    pipeline_opportunities: int = 0
    closed_won: int = 0
    # Backward compatibility fields (counts activities/records)
    contacted_records: int = 0
    engaged_records: int = 0
    contacted_breakdown: Dict[str, int] = {}
    engaged_breakdown: Dict[str, int] = {}
    # Explicit distinct prospect & activity tracking
    contacted_activities: Dict[str, int] = {}
    engaged_activities: Dict[str, int] = {}
    meetings_requested: int = 0
    confirmed_bookings: int = 0


class PositiveProspectResponse(BaseModel):
    """Surfaces positive prospect engagement for review and subjective deal value entry."""
    id: str
    lead_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None
    contact_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    channel: str  # "voice" | "email" | "inbound"
    response_type: str  # "meeting_requested" | "email_replied" | "qualified"
    response_preview: Optional[str] = None
    occurred_at: Optional[datetime] = None
    deal_id: Optional[uuid.UUID] = None
    deal_name: Optional[str] = None
    deal_amount: Optional[float] = None
    deal_status: Optional[str] = None
    pipeline_stage_id: Optional[uuid.UUID] = None
    pipeline_stage_name: Optional[str] = None


class AnalyticsOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    leads: LeadMetrics
    campaigns: CampaignMetricsOverview
    outreach: OutreachMetricsOverview
    voice: VoiceCallMetricsOverview
    pipeline: PipelineMetricsOverview
    campaign_performance: List[CampaignPerformanceSummary]
    funnel: Optional[FunnelMetrics] = None
    positive_responses: List[PositiveProspectResponse] = []


# ── Unified Activity Tracking Schemas ─────────────────────────────────────────

class EmailActivityDetails(BaseModel):
    status: str
    subject: Optional[str] = None
    body_preview: Optional[str] = None
    provider: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    bounced_at: Optional[datetime] = None
    is_delivered: bool = False
    is_replied: bool = False
    is_bounced: bool = False


class VoiceActivityDetails(BaseModel):
    call_id: str
    direction: str  # "inbound" | "outbound"
    call_status: str
    call_outcome: Optional[str] = None
    duration_seconds: Optional[int] = None
    caller_phone: Optional[str] = None
    to_phone: Optional[str] = None
    is_connected: bool = False
    disconnection_reason: Optional[str] = None
    summary: Optional[str] = None
    transcript_snippet: Optional[str] = None


class UnifiedActivityItem(BaseModel):
    id: str
    channel: str  # "email" | "voice"
    activity_type: str  # "email_sent", "email_delivered", "email_replied", "call_completed", etc.
    title: str
    description: Optional[str] = None
    occurred_at: datetime
    lead_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None
    campaign_id: Optional[uuid.UUID] = None
    campaign_name: Optional[str] = None
    contact_name: Optional[str] = None
    company_name: Optional[str] = None
    email_details: Optional[EmailActivityDetails] = None
    voice_details: Optional[VoiceActivityDetails] = None
    provenance: Dict[str, Any] = {}


class UnifiedActivityResponse(BaseModel):
    items: List[UnifiedActivityItem] = []
    total: int = 0
    skip: int = 0
    limit: int = 50

