"""Pre-call Lead Intelligence & Research API endpoints."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.lead import Lead
from app.models.lead_research import LeadResearch
from app.models.tenant import Organization
from app.schemas.lead_research import (
    LeadResearchResponse,
    LeadResearchTriggerRequest,
    LeadResearchVoiceContextResponse,
)
from app.services.research import LeadNotFoundError, LeadResearchService

router = APIRouter(prefix="/leads", tags=["Lead Intelligence & Research"])


@router.get(
    "/{lead_id}/research",
    response_model=LeadResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Get pre-call intelligence for a lead",
    description="Retrieve the latest cached structured web research profile for a specific lead.",
)
async def get_lead_research(
    lead_id: uuid.UUID,
    max_age_days: int = Query(7, ge=1, le=90, description="Freshness threshold in days"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResearchResponse:
    # Verify lead exists and belongs to organization
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.organization_id == current_org.id)
        .first()
    )
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )

    research = (
        db.query(LeadResearch)
        .filter(LeadResearch.lead_id == lead_id, LeadResearch.organization_id == current_org.id)
        .first()
    )
    if not research:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No research profile found for lead '{lead_id}'. Trigger research first.",
        )

    resp = LeadResearchResponse.model_validate(research)
    resp.is_fresh = research.check_freshness(max_age_days=max_age_days)
    return resp


@router.post(
    "/{lead_id}/research",
    response_model=LeadResearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger or refresh pre-call research for a lead",
    description="Executes targeted web research and LLM structuring if stale, or returns fresh cached intelligence.",
)
async def trigger_lead_research(
    lead_id: uuid.UUID,
    data: Optional[LeadResearchTriggerRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResearchResponse:
    force_refresh = data.force_refresh if data else False
    max_age_days = data.max_age_days if data else 7

    service = LeadResearchService()
    try:
        research = await service.get_or_research_lead(
            db=db,
            org_id=current_org.id,
            lead_id=lead_id,
            max_age_days=max_age_days,
            force_refresh=force_refresh,
        )
    except LeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research generation failed: {str(exc)}",
        )

    resp = LeadResearchResponse.model_validate(research)
    resp.is_fresh = research.check_freshness(max_age_days=max_age_days)
    return resp


@router.get(
    "/{lead_id}/research/voice-context",
    response_model=LeadResearchVoiceContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get pre-call voice dynamic variables for Retell agent",
    description="Retrieve sanitized, conversational dynamic variables ready to pass into a Retell voice call.",
)
async def get_lead_voice_research_context(
    lead_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResearchVoiceContextResponse:
    research = (
        db.query(LeadResearch)
        .filter(LeadResearch.lead_id == lead_id, LeadResearch.organization_id == current_org.id)
        .first()
    )
    if not research:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No research found for lead '{lead_id}'.",
        )

    voice_vars = LeadResearchService.format_voice_dynamic_context(research)
    return LeadResearchVoiceContextResponse(
        lead_id=lead_id,
        researched_at=research.researched_at,
        research_status=research.research_status,
        voice_dynamic_variables=voice_vars,
    )
