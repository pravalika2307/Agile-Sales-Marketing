"""Pydantic schemas for AI-assisted campaign draft generation."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.workflow import WorkflowConfig, WorkflowValidationResult


class FilteredChannelReason(BaseModel):
    """Details on why a requested channel was excluded from the generated workflow."""
    channel: str
    reason: str


class AICampaignDraftRequest(BaseModel):
    """Payload to request an AI-generated campaign draft."""
    description: str = Field(
        ...,
        min_length=5,
        max_length=1500,
        description="Short natural language description of the campaign context and audience need",
    )
    target_audience: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Target industry, personas, or customer segment (e.g., 'VP of RevOps at mid-market B2B tech')",
    )
    objective: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Core campaign goal or call to action (e.g., 'Book a 15-minute briefing on revenue acceleration')",
    )
    channels: List[str] = Field(
        default_factory=lambda: ["email"],
        description="Requested communication channels to include: email, sms, voice, physical_mail",
    )
    campaign_duration_days: Optional[int] = Field(
        default=14,
        ge=1,
        le=90,
        description="Total duration in days over which the campaign sequence should execute",
    )
    followup_interval_days: Optional[int] = Field(
        default=3,
        ge=1,
        le=30,
        description="Suggested delay between successive outreach attempts",
    )
    campaign_type: str = Field(
        default="sales_outbound",
        description="sales_outbound, marketing_social, or hybrid",
    )
    tone: Optional[str] = Field(
        default="consultative",
        description="Tone of copy: consultative, professional, direct, or conversational",
    )
    save_as_draft: bool = Field(
        default=True,
        description="If True, persists a new Campaign record in 'draft' status and links the workflow",
    )
    force_mock: bool = Field(
        default=False,
        description="If True, uses deterministic template mock generator instead of calling AWS Bedrock",
    )

    @field_validator("description", "target_audience", "objective")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Field cannot be empty or whitespace only.")
        return clean

    @field_validator("channels")
    @classmethod
    def validate_channels_list(cls, v: List[str]) -> List[str]:
        if not v:
            return ["email"]
        cleaned = [c.strip().lower() for c in v if c and c.strip()]
        return cleaned or ["email"]


class AICampaignDraftResponse(BaseModel):
    """Structured response containing generated draft details and validated workflow graph."""
    campaign_id: Optional[uuid.UUID] = None
    campaign_name: str
    objective: str
    target_audience: str
    summary: str
    channels_used: List[str]
    channels_filtered_out: List[FilteredChannelReason] = Field(default_factory=list)
    workflow_config: WorkflowConfig
    validation: WorkflowValidationResult
    model_used: str
    ai_provider: str
    is_mock: bool = False
