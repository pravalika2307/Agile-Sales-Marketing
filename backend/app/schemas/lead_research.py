"""Pydantic schemas for Lead Intelligence & Pre-Call Research."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StructuredLeadIntelligence(BaseModel):
    """Normalized structured intelligence payload extracted from research."""
    company_summary: str = Field(..., description="1-3 sentence overview of what the company does")
    industry: Optional[str] = Field(None, description="Primary industry sector")
    company_size: Optional[str] = Field(None, description="Estimated company size or headcount range")
    location: Optional[str] = Field(None, description="Headquarters city and state/country")
    business_signals: List[str] = Field(default_factory=list, description="Key recent business signals or initiatives")
    potential_pain_points: List[str] = Field(default_factory=list, description="Likely operational or outbound pain points")
    personalization_points: List[str] = Field(default_factory=list, description="Specific hooks for personalization in voice or email outreach")
    research_summary: str = Field(..., description="Concise briefing summary designed for SDR agent context")
    source_urls: List[str] = Field(default_factory=list, description="Public web URLs used as research sources")


class LeadResearchResponse(BaseModel):
    """Schema returned by LeadResearch API endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    lead_id: uuid.UUID

    company_summary: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    location: Optional[str] = None

    business_signals: List[str] = Field(default_factory=list)
    potential_pain_points: List[str] = Field(default_factory=list)
    personalization_points: List[str] = Field(default_factory=list)

    research_summary: Optional[str] = None
    source_urls: List[str] = Field(default_factory=list)

    researched_at: datetime
    research_status: str
    error_message: Optional[str] = None
    is_fresh: bool = Field(True, description="Whether the research is within the freshness TTL")

    created_at: datetime
    updated_at: datetime


class LeadResearchTriggerRequest(BaseModel):
    """Request payload to initiate or refresh pre-call research."""
    force_refresh: bool = Field(
        False,
        description="If true, bypasses existing recent research and executes fresh research.",
    )
    max_age_days: int = Field(
        7,
        ge=1,
        le=90,
        description="Maximum age in days before research is deemed stale and refreshed.",
    )


class LeadResearchVoiceContextResponse(BaseModel):
    """Formatted research context ready to be merged into Retell dynamic variables."""
    lead_id: uuid.UUID
    researched_at: datetime
    research_status: str
    voice_dynamic_variables: Dict[str, str]
