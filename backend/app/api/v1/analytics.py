import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.analytics import AnalyticsOverviewResponse, UnifiedActivityResponse
from app.services.analytics_service import get_analytics_overview, get_unified_activities

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get analytics overview",
    description="Returns real, tenant-scoped operational metrics for leads, campaigns, outreach, voice calls, and pipeline.",
)
async def get_overview(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> AnalyticsOverviewResponse:
    return get_analytics_overview(db, current_org.id)


@router.get(
    "/activities",
    response_model=UnifiedActivityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unified activity stream",
    description="Returns a truthful chronological stream of verified email and voice activities, filtered by lead, contact, list, or campaign.",
)
async def get_activities(
    lead_id: Optional[uuid.UUID] = Query(None, description="Filter by Lead ID"),
    contact_id: Optional[uuid.UUID] = Query(None, description="Filter by Contact ID"),
    list_id: Optional[uuid.UUID] = Query(None, description="Filter by Contact List ID"),
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by Campaign ID"),
    channel: Optional[str] = Query(None, description="Filter by channel ('email' or 'voice')"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> UnifiedActivityResponse:
    return get_unified_activities(
        db,
        current_org.id,
        lead_id=lead_id,
        contact_id=contact_id,
        list_id=list_id,
        campaign_id=campaign_id,
        channel=channel,
        skip=skip,
        limit=limit,
    )

