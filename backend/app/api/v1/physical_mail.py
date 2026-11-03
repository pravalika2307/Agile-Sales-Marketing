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
from app.services.physical_mail.poplar_client import PoplarValidationError
from app.services.physical_mail.poplar_client import get_poplar_client
from app.services.physical_mail.service import (
    CampaignNotFoundError,
    DIMENSIONAL_SPECIFICATIONS,
    DuplicateSubmissionError,
    PhysicalMailService,
    PoplarPersistenceError,
    SUPPORTED_MAILPIECE_OPTIONS,
    UnapprovedCampaignError,
    validate_creative_asset,
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


class PhysicalMailConfigureRequest(BaseModel):
    workflow_mode: str = Field("connect", description="'connect' to link an existing Poplar campaign, or 'create' to create a new Poplar campaign")
    poplar_campaign_id: Optional[str] = Field(None, description="Existing Poplar Campaign ID to bind or link (for connect mode)")
    new_campaign_name: Optional[str] = Field(None, description="Name for newly created Poplar campaign (for create mode)")
    purpose: Optional[str] = Field("retention", description="Poplar campaign purpose (verified accepted value: 'retention')")
    sub_purpose: Optional[str] = Field("reactivation", description="Poplar sub-purpose (verified accepted value: 'reactivation')")
    description: Optional[str] = Field(None, description="Optional description for Poplar campaign")
    mailpiece_size: str = Field(..., description="Postcard or letter dimension ('4x6', '6x9', '6x11')")
    format_type: str = Field(..., description="Format style ('postcard', 'bw_envelope', 'color_envelope', 'bifold', 'trifold')")
    paper_type: str = Field(..., description="Stock quality ('premium_coated', 'premium_uncoated')")
    postage_class: str = Field(..., description="Mailing class ('usps_standard', 'usps_first_class')")
    design_url: Optional[str] = Field(None, description="Direct URL to artwork PDF/PNG")
    design_name: Optional[str] = Field(None, description="Descriptive artwork/design name")
    creative_id: Optional[str] = Field(None, description="Poplar Creative ID to attach from creative library")
    recipient_ids: Optional[List[uuid.UUID]] = Field(None, description="Optional target subset of recipients")


class PhysicalMailConfigureResponse(BaseModel):
    campaign_id: uuid.UUID
    poplar_campaign_id: Optional[str]
    creative_id: Optional[str] = None
    poplar_status: str
    poplar_name: Optional[str]
    mailpiece: Dict[str, Any]
    design: Dict[str, Any]
    unit_cost: float
    estimated_total_cost: float
    recipient_summary: Dict[str, Any]


class PhysicalMailHealthResponse(BaseModel):
    configured: bool
    connected: bool
    environment: str
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    mode: Optional[str] = None
    allow_live_sending: bool
    message: str
    error: Optional[str] = None


class PoplarCampaignItemResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


class PoplarCampaignListResponse(BaseModel):
    total: int
    campaigns: List[PoplarCampaignItemResponse]


class PoplarCreativeItemResponse(BaseModel):
    id: str
    name: str
    mail_type: Optional[str] = None
    creative_type: Optional[str] = None
    format: Optional[str] = None
    image_formats: Optional[str] = None
    state: Optional[str] = None
    thumbnail_url: Optional[str] = None
    associated_campaign_id: Optional[str] = None
    associated_campaign_name: Optional[str] = None


class PoplarCreativeListResponse(BaseModel):
    total: int
    creatives: List[PoplarCreativeItemResponse]


class CreativeValidateRequest(BaseModel):
    file_name: str
    file_size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    mailpiece_size: str = "4x6"


class CreativeValidateResponse(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    file_name: str
    spec: Dict[str, Any]


class PhysicalMailOptionsResponse(BaseModel):
    sizes: List[Dict[str, str]]
    formats: List[Dict[str, str]]
    postage_classes: List[Dict[str, str]]
    paper_types: List[Dict[str, str]]
    cost_estimates: Dict[str, float]

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
    "/physical-mail/health",
    response_model=PhysicalMailHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check live Poplar account connectivity and environment status",
)
def check_poplar_health(
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
) -> PhysicalMailHealthResponse:
    """Queries Poplar's GET /v1/me endpoint to confirm live test connectivity without exposing API keys."""
    if not settings.is_poplar_configured or not settings.POPLAR_ENABLED:
        return PhysicalMailHealthResponse(
            configured=False,
            connected=False,
            environment=settings.POPLAR_ENVIRONMENT,
            allow_live_sending=settings.is_poplar_live_sending_allowed,
            message="Poplar integration is unconfigured or disabled in environment.",
            error=None,
        )
    try:
        client = get_poplar_client()
        res = client.verify_connection()
        data = res.get("data", {})
        return PhysicalMailHealthResponse(
            configured=settings.is_poplar_configured,
            connected=res.get("connected", False),
            environment=settings.POPLAR_ENVIRONMENT,
            account_id=data.get("id"),
            account_name=data.get("name"),
            mode=data.get("mode"),
            allow_live_sending=settings.is_poplar_live_sending_allowed,
            message="Poplar test sandbox is connected and operational." if res.get("connected") else "Poplar API rejected credentials.",
            error=res.get("error"),
        )
    except Exception as exc:
        logger.warning("Poplar health check error: %s", exc)
        return PhysicalMailHealthResponse(
            configured=settings.is_poplar_configured,
            connected=False,
            environment=settings.POPLAR_ENVIRONMENT,
            allow_live_sending=settings.is_poplar_live_sending_allowed,
            message="Unable to reach Poplar API.",
            error=str(exc)[:200],
        )


@router.get(
    "/physical-mail/campaigns",
    response_model=PoplarCampaignListResponse,
    status_code=status.HTTP_200_OK,
    summary="List existing campaigns from connected Poplar account",
)
def list_poplar_campaigns_endpoint(
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PoplarCampaignListResponse:
    """Queries Poplar's GET /v1/campaigns endpoint to discover existing Poplar campaigns."""
    service = PhysicalMailService(db=db)
    try:
        raw_campaigns = service.list_poplar_campaigns()
        items = []
        for c in raw_campaigns:
            if isinstance(c, dict) and c.get("id"):
                items.append(
                    PoplarCampaignItemResponse(
                        id=str(c.get("id")),
                        name=str(c.get("name") or "Untitled Campaign"),
                        description=c.get("description"),
                        status=c.get("status"),
                        created_at=c.get("created_at"),
                    )
                )
        return PoplarCampaignListResponse(total=len(items), campaigns=items)
    except Exception as exc:
        logger.warning("Failed listing Poplar campaigns: %s", exc)
        return PoplarCampaignListResponse(total=0, campaigns=[])


@router.get(
    "/physical-mail/creatives",
    response_model=PoplarCreativeListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available direct mail creatives from Poplar account library",
)
def list_poplar_creatives(
    campaign_id: Optional[str] = Query(None, description="Optional Poplar campaign ID filter"),
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PoplarCreativeListResponse:
    """Retrieves available creative assets and thumbnails from the connected Poplar account."""
    service = PhysicalMailService(db=db)
    try:
        creatives = service.list_account_creatives(campaign_id=campaign_id)
        return PoplarCreativeListResponse(
            total=len(creatives),
            creatives=[PoplarCreativeItemResponse(**c) for c in creatives],
        )
    except Exception as exc:
        logger.warning("Failed listing Poplar creatives: %s", exc)
        return PoplarCreativeListResponse(total=0, creatives=[])


@router.post(
    "/physical-mail/validate-creative",
    response_model=CreativeValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate direct mail artwork asset specifications",
)
def validate_creative_endpoint(
    payload: CreativeValidateRequest,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
) -> CreativeValidateResponse:
    """Evaluates artwork dimensions, format, and file size limits according to Poplar guidelines."""
    res = validate_creative_asset(
        file_name=payload.file_name,
        file_size_bytes=payload.file_size_bytes,
        content_type=payload.content_type,
        mailpiece_size=payload.mailpiece_size,
    )
    return CreativeValidateResponse(**res)


@router.get(
    "/physical-mail/specs",
    status_code=status.HTTP_200_OK,
    summary="Get dimensional specifications and print guidelines for each format",
)
def get_physical_mail_specs(
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
) -> Dict[str, Any]:
    """Returns detailed dimensional guidelines (trim, bleed, safe zone, DPI) for all formats."""
    return DIMENSIONAL_SPECIFICATIONS

@router.get(
    "/physical-mail/options",
    response_model=PhysicalMailOptionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get supported mailpiece sizes, formats, paper types, and postage tiers",
)
def get_physical_mail_options(
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
) -> PhysicalMailOptionsResponse:
    """Returns all supported physical mail parameters and base pricing matrix."""
    return PhysicalMailOptionsResponse(**SUPPORTED_MAILPIECE_OPTIONS)


@router.post(
    "/campaigns/{campaign_id}/physical-mail/configure",
    response_model=PhysicalMailConfigureResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure mailpiece and create/link campaign resource in Poplar TEST account",
)
def configure_physical_mail_campaign(
    campaign_id: uuid.UUID,
    payload: PhysicalMailConfigureRequest,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PhysicalMailConfigureResponse:
    """
    Configures mailpiece parameters (size, format, paper, postage, design) and registers
    or links a corresponding Campaign resource in Poplar.
    Safe operation: creates Poplar campaign resource without purchasing postage or ordering fulfillment.
    """
    service = PhysicalMailService(db=db)
    try:
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign_id,
            mailpiece_size=payload.mailpiece_size,
            format_type=payload.format_type,
            paper_type=payload.paper_type,
            postage_class=payload.postage_class,
            design_url=payload.design_url,
            design_name=payload.design_name,
            poplar_campaign_id=payload.poplar_campaign_id,
            creative_id=payload.creative_id,
            recipient_ids=payload.recipient_ids,
            workflow_mode=payload.workflow_mode,
            new_campaign_name=payload.new_campaign_name,
            purpose=payload.purpose or "retention",
            sub_purpose=payload.sub_purpose or "reactivation",
            description=payload.description,
        )
        return PhysicalMailConfigureResponse(**res)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PoplarValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except PoplarPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": str(exc),
                "poplar_campaign_id": exc.poplar_campaign_id,
                "code": "POPLAR_PERSISTENCE_FAILED",
            },
        )


@router.get(
    "/campaigns/{campaign_id}/physical-mail/config",
    status_code=status.HTTP_200_OK,
    summary="Get saved physical mail configuration and Poplar remote campaign status",
)
def get_campaign_physical_mail_config(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieves physical mail configuration and verifies live status against Poplar."""
    service = PhysicalMailService(db=db)
    try:
        return service.get_campaign_physical_mail_config(org_id=org.id, campaign_id=campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

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
