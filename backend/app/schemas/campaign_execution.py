"""Campaign execution and outreach orchestration Pydantic schemas."""
from __future__ import annotations

import uuid
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CampaignExecutionRequest(BaseModel):
    """Optional configuration payload for execution or preview requests."""
    sender_name: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Optional sender name override used for template rendering (defaults to 'Agile Sales & Marketing')",
    )


class CampaignExecutionPreviewItem(BaseModel):
    """Rendered content preview for an individual eligible campaign contact."""
    model_config = ConfigDict(from_attributes=True)

    campaign_contact_id: uuid.UUID
    contact_id: uuid.UUID
    step_number: int = 1
    subject: Optional[str] = None
    body: Optional[str] = None


class CampaignExecutionPreviewResponse(BaseModel):
    """Result of a read-only preview dry-run for campaign outreach planning."""
    model_config = ConfigDict(from_attributes=True)

    campaign_id: uuid.UUID = Field(..., description="Target Campaign ID")
    eligible_count: int = Field(..., ge=0, description="Total number of eligible contacts ready for outreach")
    eligible_campaign_contact_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of CampaignContact enrollments that qualify for initial outreach",
    )
    skipped_count: int = Field(..., ge=0, description="Total number of skipped enrollments")
    skipped_campaign_contact_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of CampaignContact enrollments skipped due to state, opt-out, or duplicate outreach",
    )
    rejected_count: int = Field(..., ge=0, description="Total number of rejected enrollments due to inconsistency")
    rejected_campaign_contact_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of CampaignContact enrollments rejected due to inconsistent relationships",
    )
    preview_items: List[CampaignExecutionPreviewItem] = Field(
        default_factory=list,
        description="Rendered preview items for eligible contacts",
    )


class CampaignExecutionResponse(BaseModel):
    """Result of campaign execution planning creating initial draft outreach items."""
    model_config = ConfigDict(from_attributes=True)

    campaign_id: uuid.UUID = Field(..., description="Target Campaign ID")
    eligible_count: int = Field(..., ge=0, description="Total number of eligible contacts evaluated")
    created_count: int = Field(..., ge=0, description="Number of outreach records successfully created")
    skipped_count: int = Field(..., ge=0, description="Total number of skipped enrollments")
    rejected_count: int = Field(..., ge=0, description="Total number of rejected enrollments")
    created_outreach_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of created Outreach draft records",
    )
    skipped_campaign_contact_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of CampaignContact enrollments that were skipped",
    )
    rejected_campaign_contact_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of CampaignContact enrollments that were rejected",
    )


class SchedulerTickRequest(BaseModel):
    """Configuration payload for manual or automated scheduler tick execution."""
    dry_run: bool = Field(default=False, description="Simulate execution without database mutations or provider calls")
    auto_dispatch: bool = Field(default=False, description="Deliver scheduled messages that are due")
    force: bool = Field(default=False, description="Force run even if SCHEDULER_ENABLED is False")
    sender_name: Optional[str] = Field(default=None, description="Sender name override for template rendering")


class SchedulerTickResponse(BaseModel):
    """Result of a scheduler tick execution."""
    model_config = ConfigDict(from_attributes=True)

    status: str
    message: Optional[str] = None
    dry_run: bool
    planned_count: int
    completed_count: int
    dispatched_count: int
    skipped_count: int
    halted_count: int
    error_count: int
    details: List[dict] = Field(default_factory=list)

