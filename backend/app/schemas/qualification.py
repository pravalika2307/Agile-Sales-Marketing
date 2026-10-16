"""Pydantic schemas for Lead Qualification, Scoring Breakdown, and Campaign Eligibility (Phases 2, 3, 5)."""
from __future__ import annotations

import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class CriterionDetail(BaseModel):
    criterion: str
    points: int
    max_points: int
    status: str  # "matched", "unmatched", "missing_data", "not_configured"
    detail: str


class LeadQualificationEvaluateRequest(BaseModel):
    icp_id: Optional[uuid.UUID] = Field(None, description="Optional target ICP ID. Defaults to first active ICP in organization if not specified.")
    dry_run: bool = Field(False, description="If True, returns evaluation breakdown without persisting score or qualification status to database.")
    qualification_threshold: int = Field(50, ge=1, le=100, description="Minimum score required to qualify lead.")


class LeadQualificationResult(BaseModel):
    lead_id: uuid.UUID
    icp_id: Optional[uuid.UUID] = None
    icp_name: Optional[str] = None
    score: int
    temperature: str  # "cold", "warm", "hot"
    qualification_status: str  # "qualified", "disqualified", "reviewed", "new"
    is_qualified: bool
    is_assessed: bool
    qualification_reason: str
    criteria: List[CriterionDetail]
    matched_criteria_count: int
    missing_criteria_count: int
    unmatched_criteria_count: int


class LeadBatchEvaluateRequest(BaseModel):
    lead_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)
    icp_id: Optional[uuid.UUID] = None
    dry_run: bool = False
    qualification_threshold: int = 50


class LeadBatchEvaluateResult(BaseModel):
    total_evaluated: int
    qualified_count: int
    disqualified_count: int
    unassessed_count: int
    results: List[LeadQualificationResult]


class CampaignEligibilityCheckRequest(BaseModel):
    campaign_id: uuid.UUID


class CampaignEligibilityResult(BaseModel):
    lead_id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_name: str
    campaign_status: str
    is_eligible: bool
    reasons: List[str]
    suppression_reasons: List[str]
    contact_id: Optional[uuid.UUID] = None
    already_enrolled: bool = False


class LeadCampaignEnrollRequest(BaseModel):
    campaign_id: uuid.UUID


class LeadCampaignEnrollResult(BaseModel):
    lead_id: uuid.UUID
    campaign_id: uuid.UUID
    contact_id: uuid.UUID
    campaign_contact_id: Optional[uuid.UUID] = None
    status: str  # "enrolled", "already_enrolled", "rejected"
    message: str
