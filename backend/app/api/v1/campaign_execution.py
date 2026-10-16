"""Campaign execution and outreach orchestration API endpoints (Step 8 & Step 9)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.campaign_execution import (
    CampaignExecutionPreviewResponse,
    CampaignExecutionRequest,
    CampaignExecutionResponse,
    SchedulerTickRequest,
    SchedulerTickResponse,
)
from app.services.campaign_execution import (
    CampaignNotFoundError,
    InvalidCampaignExecutionStateError,
    execute_campaign,
    preview_campaign_execution,
)
from app.services.campaign_scheduler import CampaignSchedulerService

router = APIRouter(prefix="/campaigns", tags=["Campaign Execution"])


@router.post(
    "/{campaign_id}/execute/preview",
    response_model=CampaignExecutionPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview campaign outreach execution",
    description="Read-only dry run identifying eligible contacts for initial outreach with rendered Step 1 templates without mutating database records.",
)
async def preview_campaign_execution_endpoint(
    campaign_id: uuid.UUID,
    payload: Optional[CampaignExecutionRequest] = Body(None),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignExecutionPreviewResponse:
    sender_name = payload.sender_name if payload else None
    try:
        result = preview_campaign_execution(db, current_org.id, campaign_id, sender_name=sender_name)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidCampaignExecutionStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return result


@router.post(
    "/{campaign_id}/execute",
    response_model=CampaignExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute campaign outreach planning",
    description="Identifies eligible contacts and creates initial draft Outreach records with rendered Step 1 templates, advancing enrollment to in_progress.",
)
async def execute_campaign_endpoint(
    campaign_id: uuid.UUID,
    payload: Optional[CampaignExecutionRequest] = Body(None),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignExecutionResponse:
    sender_name = payload.sender_name if payload else None
    try:
        result = execute_campaign(db, current_org.id, campaign_id, sender_name=sender_name)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidCampaignExecutionStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return result


@router.post(
    "/scheduler/tick",
    response_model=SchedulerTickResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute campaign scheduler tick",
    description="Evaluates multi-day step progression across campaigns in the authenticated tenant organization. Respects dry_run and disabled settings.",
)
async def scheduler_tick_endpoint(
    payload: Optional[SchedulerTickRequest] = Body(None),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> SchedulerTickResponse:
    dry_run = payload.dry_run if payload else False
    auto_dispatch = payload.auto_dispatch if payload else False
    force = payload.force if payload else False
    sender_name = payload.sender_name if payload else None

    service = CampaignSchedulerService(db=db)
    result = service.tick(
        org_id=current_org.id,
        dry_run=dry_run,
        auto_dispatch=auto_dispatch,
        force=force,
        sender_name=sender_name,
    )
    return SchedulerTickResponse(
        status=result.status,
        message=result.message,
        dry_run=result.dry_run,
        planned_count=result.planned_count,
        completed_count=result.completed_count,
        dispatched_count=result.dispatched_count,
        skipped_count=result.skipped_count,
        halted_count=result.halted_count,
        error_count=result.error_count,
        details=result.details,
    )


@router.post(
    "/{campaign_id}/advance-steps",
    response_model=SchedulerTickResponse,
    status_code=status.HTTP_200_OK,
    summary="Advance sequence steps for a specific campaign",
    description="Evaluates and advances eligible contacts for a single campaign based on delay offsets and stop conditions.",
)
async def advance_campaign_steps_endpoint(
    campaign_id: uuid.UUID,
    payload: Optional[SchedulerTickRequest] = Body(None),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> SchedulerTickResponse:
    dry_run = payload.dry_run if payload else False
    auto_dispatch = payload.auto_dispatch if payload else False
    force = payload.force if payload else False
    sender_name = payload.sender_name if payload else None

    service = CampaignSchedulerService(db=db)
    result = service.tick(
        org_id=current_org.id,
        campaign_id=campaign_id,
        dry_run=dry_run,
        auto_dispatch=auto_dispatch,
        force=force,
        sender_name=sender_name,
    )
    return SchedulerTickResponse(
        status=result.status,
        message=result.message,
        dry_run=result.dry_run,
        planned_count=result.planned_count,
        completed_count=result.completed_count,
        dispatched_count=result.dispatched_count,
        skipped_count=result.skipped_count,
        halted_count=result.halted_count,
        error_count=result.error_count,
        details=result.details,
    )


