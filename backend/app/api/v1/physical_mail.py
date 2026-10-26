"""API endpoints for Poplar physical mail campaigns, address verification, cost preview, and submission."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_organization
from app.core.config import settings
from app.core.database import get_db
from app.models.tenant import Organization, User
from app.services.physical_mail.service import (
    CampaignNotFoundError,
    DuplicateSubmissionError,
    PhysicalMailService,
    UnapprovedCampaignError,
)
from app.services.physical_mail.tracker import (
    PhysicalMailTracker,
)
from app.services.physical_mail.webhook import (
    PoplarCrossTenantError,
    PoplarMalformedPayloadError,
    PoplarSignatureVerificationError,
    PoplarWebhookService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Physical Direct Mail"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PhysicalMailValidateResponse(BaseModel):
    campaign_id: uuid.UUID
    total_recipients: int
    valid_count: int
    invalid_count: int
    valid_recipients: List[Dict[str, Any]]
    invalid_recipients: List[Dict[str, Any]]


class PhysicalMailPreviewResponse(BaseModel):
    campaign_id: uuid.UUID
    poplar_campaign_id: str
    poplar_creative_id: Optional[str]
    unit_cost: float
    total_recipients: int
    valid_count: int
    invalid_count: int
    estimated_total_cost: float
    sample_preview: Optional[Dict[str, Any]]
    invalid_recipients: List[Dict[str, Any]]
    approval_required: bool = True


class PhysicalMailApproveRequest(BaseModel):
    approved: bool = Field(..., description="Explicit user confirmation authorizing print and postage costs")
    approval_token: str = Field(..., min_length=4, max_length=100, description="Idempotency token")
    poplar_campaign_id: Optional[str] = None
    poplar_creative_id: Optional[str] = None
    recipient_ids: Optional[List[uuid.UUID]] = None


class PhysicalMailSubmissionResponse(BaseModel):
    campaign_id: uuid.UUID
    total_processed: int
    total_submitted: int
    total_failed: int
    estimated_cost: float
    outcomes: List[Dict[str, Any]]


class PhysicalMailStatusResponse(BaseModel):
    configured: bool
    environment: str
    allow_live_sending: bool
    base_url: str
    default_campaign_id: Optional[str]
    default_creative_id: Optional[str]


class PoplarWebhookItemResponse(BaseModel):
    mailing_id: Optional[str] = None
    identifier: Optional[str] = None
    outreach_id: Optional[uuid.UUID] = None
    status: str
    action: str
    reason: Optional[str] = None
    duplicate: bool = False


class PoplarWebhookResponse(BaseModel):
    status: str
    event_type: str
    total_items: int
    processed_count: int
    duplicate_count: int
    ignored_count: int
    outcomes: List[PoplarWebhookItemResponse] = []


class PhysicalMailSyncResponse(BaseModel):
    campaign_id: uuid.UUID
    total_checked: int
    total_updated: int
    total_delivered: int
    total_failed: int
    results: List[Dict[str, Any]]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/physical-mail/status",
    response_model=PhysicalMailStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Poplar physical mail configuration status",
)
def get_physical_mail_status(
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
) -> PhysicalMailStatusResponse:
    """Returns Poplar provider configuration without leaking API keys."""
    return PhysicalMailStatusResponse(
        configured=settings.is_poplar_configured,
        environment=settings.POPLAR_ENVIRONMENT,
        allow_live_sending=settings.is_poplar_live_sending_allowed,
        base_url=settings.POPLAR_BASE_URL,
        default_campaign_id=settings.POPLAR_DEFAULT_CAMPAIGN_ID,
        default_creative_id=settings.POPLAR_DEFAULT_CREATIVE_ID,
    )


@router.post(
    "/campaigns/{campaign_id}/physical-mail/validate",
    response_model=PhysicalMailValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate postal addresses for a campaign's enrolled recipients",
)
def validate_campaign_physical_mail(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PhysicalMailValidateResponse:
    """Evaluates recipient addresses against USPS domestic standards."""
    service = PhysicalMailService(db=db)
    try:
        report = service.validate_campaign_recipients(org_id=org.id, campaign_id=campaign_id)
        return PhysicalMailValidateResponse(
            campaign_id=report.campaign_id,
            total_recipients=report.total_recipients,
            valid_count=report.valid_count,
            invalid_count=report.invalid_count,
            valid_recipients=[
                {
                    "recipient_id": str(i.recipient_id),
                    "full_name": i.full_name,
                    "company_name": i.company_name,
                    "address": i.cleaned_address,
                }
                for i in report.valid_recipients
            ],
            invalid_recipients=[
                {
                    "recipient_id": str(i.recipient_id),
                    "full_name": i.full_name,
                    "company_name": i.company_name,
                    "errors": i.errors,
                }
                for i in report.invalid_recipients
            ],
        )
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/campaigns/{campaign_id}/physical-mail/preview",
    response_model=PhysicalMailPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview personalized direct mail and estimated production cost",
)
def preview_campaign_physical_mail(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PhysicalMailPreviewResponse:
    """Pre-flight audit providing personalized merge preview and total budget estimate."""
    service = PhysicalMailService(db=db)
    try:
        result = service.preview_campaign_mail(org_id=org.id, campaign_id=campaign_id)
        return PhysicalMailPreviewResponse(
            campaign_id=result.campaign_id,
            poplar_campaign_id=result.poplar_campaign_id,
            poplar_creative_id=result.poplar_creative_id,
            unit_cost=result.unit_cost,
            total_recipients=result.total_recipients,
            valid_count=result.valid_count,
            invalid_count=result.invalid_count,
            estimated_total_cost=result.estimated_total_cost,
            sample_preview=result.sample_preview,
            invalid_recipients=result.invalid_recipients,
            approval_required=True,
        )
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/campaigns/{campaign_id}/physical-mail/approve-and-submit",
    response_model=PhysicalMailSubmissionResponse,
    status_code=status.HTTP_200_OK,
    summary="Explicitly authorize and dispatch physical mail campaign to Poplar",
)
def approve_and_submit_physical_mail(
    campaign_id: uuid.UUID,
    payload: PhysicalMailApproveRequest,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PhysicalMailSubmissionResponse:
    """
    Submits physical mail for all valid campaign recipients.
    Requires explicit approval=True. Fail-closed: Simulates in test mode unless live sending is enabled.
    """
    service = PhysicalMailService(db=db)
    try:
        submission = service.submit_approved_campaign(
            org_id=org.id,
            campaign_id=campaign_id,
            approved=payload.approved,
            approval_token=payload.approval_token,
            poplar_campaign_id=payload.poplar_campaign_id,
            poplar_creative_id=payload.poplar_creative_id,
            recipient_ids=payload.recipient_ids,
        )
        return PhysicalMailSubmissionResponse(
            campaign_id=submission.campaign_id,
            total_processed=submission.total_processed,
            total_submitted=submission.total_submitted,
            total_failed=submission.total_failed,
            estimated_cost=submission.estimated_cost,
            outcomes=[
                {
                    "recipient_id": str(o.recipient_id),
                    "outreach_id": str(o.outreach_id),
                    "success": o.success,
                    "status": o.status,
                    "mailing_id": o.mailing_id,
                    "proof_url": o.proof_url,
                    "error": o.error,
                    "simulated": o.simulated,
                }
                for o in submission.outcomes
            ],
        )
    except UnapprovedCampaignError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/physical-mail/webhook",
    response_model=PoplarWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Poplar physical mail webhook callback",
    description="Receives Poplar direct mail attribution and event webhooks with X-SLM-Signature verification.",
)
async def poplar_webhook_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    x_slm_signature: Optional[str] = Header(None, alias="X-SLM-Signature"),
    org_id: Optional[uuid.UUID] = Query(None, description="Optional tenant scoping hint"),
) -> PoplarWebhookResponse:
    """
    Dedicated Poplar webhook endpoint for direct mail attribution and event updates.
    Verifies cryptographic X-SLM-Signature, prevents cross-tenant leakage,
    idempotently processes events, and advances outreach/campaign records.
    """
    raw_body = await request.body()
    service = PoplarWebhookService(db=db)
    try:
        result = service.process_webhook(
            raw_body=raw_body,
            signature=x_slm_signature,
            org_id_hint=org_id,
        )
        return PoplarWebhookResponse(
            status=result.status,
            event_type=result.event_type,
            total_items=result.total_items,
            processed_count=result.processed_count,
            duplicate_count=result.duplicate_count,
            ignored_count=result.ignored_count,
            outcomes=[
                PoplarWebhookItemResponse(
                    mailing_id=o.mailing_id,
                    identifier=o.identifier,
                    outreach_id=o.outreach_id,
                    status=o.status,
                    action=o.action,
                    reason=o.reason,
                    duplicate=o.duplicate,
                )
                for o in result.outcomes
            ],
        )
    except PoplarSignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )
    except PoplarMalformedPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except PoplarCrossTenantError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.post(
    "/campaigns/{campaign_id}/physical-mail/sync",
    response_model=PhysicalMailSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Synchronize in-flight physical mail fulfillment and USPS delivery statuses",
)
def sync_campaign_physical_mail(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PhysicalMailSyncResponse:
    """
    Queries Poplar's GET /v1/mailing/:id endpoint to advance in-flight physical mail statuses.
    Fulfillment tracking (production, in_transit, delivered, exception) is polled programmatically.
    """
    tracker = PhysicalMailTracker(db=db)
    summary = tracker.sync_campaign_mailings(org_id=org.id, campaign_id=campaign_id)
    return PhysicalMailSyncResponse(
        campaign_id=summary.campaign_id,
        total_checked=summary.total_checked,
        total_updated=summary.total_updated,
        total_delivered=summary.total_delivered,
        total_failed=summary.total_failed,
        results=[
            {
                "outreach_id": str(r.outreach_id),
                "mailing_id": r.mailing_id,
                "previous_status": r.previous_status,
                "new_status": r.new_status,
                "poplar_status": r.poplar_status,
                "updated": r.updated,
                "error": r.error,
            }
            for r in summary.results
        ],
    )
