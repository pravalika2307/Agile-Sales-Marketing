"""Campaign and Contact Enrollment API endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.campaign import (
    BulkEnrollmentRequest,
    BulkEnrollmentResponse,
    CampaignContactResponse,
    CampaignContactStatusUpdate,
    CampaignCreate,
    CampaignEnrollmentRequest,
    CampaignResponse,
    CampaignUpdate,
)
from app.schemas.workflow import (
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    WorkflowConfig,
    WorkflowSaveRequest,
    WorkflowSaveResponse,
    WorkflowValidationResult,
)
from app.schemas.contact_list import (
    CampaignListAttachRequest,
    CampaignListAttachResponse,
    CampaignListItem,
    CampaignListSyncResponse,
    ContactListResponse,
)
from app.schemas.email_template import AIEmailGenerateRequest, AIEmailGenerateResponse
from app.services.campaign_steps.ai_template_service import (
    AITemplateConfigurationError,
    AITemplateGenerationError,
    generate_email_template,
)
from app.services import campaign_service, contact_list_service
from app.services.campaign_service import (
    CampaignNotFoundError,
    ContactAlreadyEnrolledError,
    ContactNotFoundError,
    InvalidCampaignTransitionError,
    InvalidEnrollmentStatusError,
)
from app.services.contact_list_service import ContactListNotFoundError
from app.services.workflow_service import (
    get_or_recover_campaign_workflow,
    preview_template_content,
    save_campaign_workflow,
    validate_workflow,
)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


# ── Campaign CRUD ─────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new campaign",
    description="Creates a campaign in draft status for the authenticated organization.",
)
async def create_campaign(
    data: CampaignCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignResponse:
    campaign = campaign_service.create_campaign(db, current_org.id, data)
    return CampaignResponse.model_validate(campaign)


@router.get(
    "",
    response_model=List[CampaignResponse],
    status_code=status.HTTP_200_OK,
    summary="List campaigns",
    description="Lists campaigns belonging to the authenticated organization with filtering.",
)
async def list_campaigns(
    response: Response,
    status: Optional[str] = Query(None, description="Filter by status (draft, active, paused, completed)"),
    type: Optional[str] = Query(None, description="Filter by type (sales_outbound, marketing_social, hybrid)"),
    search: Optional[str] = Query(None, description="Search campaigns by name"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[CampaignResponse]:
    campaigns, total = campaign_service.list_campaigns(
        db,
        current_org.id,
        status=status,
        campaign_type=type,
        search=search,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [CampaignResponse.model_validate(c) for c in campaigns]


@router.post(
    "/templates/generate-ai",
    response_model=AIEmailGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate email template with AI (AWS Bedrock)",
    description="Uses AWS Bedrock Claude Sonnet 4.5 to generate email subject and body content.",
)
async def generate_ai_email_endpoint(
    payload: AIEmailGenerateRequest,
    current_org: Organization = Depends(get_current_organization),
) -> AIEmailGenerateResponse:
    try:
        return generate_email_template(payload)
    except AITemplateConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except AITemplateGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.get(
    "/{campaign_id}",
    response_model=CampaignResponse,
    status_code=status.HTTP_200_OK,
    summary="Get campaign by ID",
    description="Retrieves a specific campaign belonging to the authenticated organization.",
)
async def get_campaign(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignResponse:
    campaign = campaign_service.get_campaign(db, current_org.id, campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found.",
        )
    return CampaignResponse.model_validate(campaign)


@router.patch(
    "/{campaign_id}",
    response_model=CampaignResponse,
    status_code=status.HTTP_200_OK,
    summary="Update campaign",
    description="Partially updates a campaign.",
)
async def update_campaign(
    campaign_id: uuid.UUID,
    data: CampaignUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignResponse:
    campaign = campaign_service.update_campaign(db, current_org.id, campaign_id, data)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found.",
        )
    return CampaignResponse.model_validate(campaign)


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete campaign",
    description="Deletes a campaign and cascades deletion to enrolled contact links.",
)
async def delete_campaign(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = campaign_service.delete_campaign(db, current_org.id, campaign_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found.",
        )


# ── Campaign Lifecycle ────────────────────────────────────────────────────────

@router.post(
    "/{campaign_id}/activate",
    response_model=CampaignResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate campaign",
    description="Transitions a draft or paused campaign to active.",
)
async def activate_campaign(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignResponse:
    try:
        campaign = campaign_service.activate_campaign(db, current_org.id, campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidCampaignTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CampaignResponse.model_validate(campaign)


@router.post(
    "/{campaign_id}/pause",
    response_model=CampaignResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause campaign",
    description="Transitions an active campaign to paused.",
)
async def pause_campaign(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignResponse:
    try:
        campaign = campaign_service.pause_campaign(db, current_org.id, campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidCampaignTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CampaignResponse.model_validate(campaign)


@router.post(
    "/{campaign_id}/complete",
    response_model=CampaignResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete campaign",
    description="Transitions an active or paused campaign to completed.",
)
async def complete_campaign(
    campaign_id: uuid.UUID,
    force: bool = Query(False, description="Force completion even if in-progress contacts or draft outreach exist"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignResponse:
    try:
        campaign = campaign_service.complete_campaign(db, current_org.id, campaign_id, force=force)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidCampaignTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CampaignResponse.model_validate(campaign)


# ── Contact Enrollment ────────────────────────────────────────────────────────

@router.post(
    "/{campaign_id}/contacts/bulk",
    response_model=BulkEnrollmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk enroll contacts",
    description="Enrolls multiple contacts into a campaign safely, reporting enrolled, already enrolled, and rejected IDs.",
)
async def bulk_enroll_contacts(
    campaign_id: uuid.UUID,
    payload: BulkEnrollmentRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> BulkEnrollmentResponse:
    try:
        result = campaign_service.bulk_enroll_contacts(
            db, current_org.id, campaign_id, payload.contact_ids
        )
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return BulkEnrollmentResponse.model_validate(result)


@router.post(
    "/{campaign_id}/contacts/{contact_id}",
    response_model=CampaignContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll a contact in a campaign",
    description="Enrolls a single contact into a campaign. Both must belong to the authenticated organization.",
)
async def enroll_contact(
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: Optional[CampaignEnrollmentRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignContactResponse:
    status_val = payload.enrollment_status if payload else "queued"
    try:
        enrollment = campaign_service.enroll_contact(
            db,
            current_org.id,
            campaign_id,
            contact_id,
            enrollment_status=status_val or "queued",
        )
    except (CampaignNotFoundError, ContactNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ContactAlreadyEnrolledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CampaignContactResponse.model_validate(enrollment)


@router.delete(
    "/{campaign_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a contact from a campaign",
    description="Removes a contact's enrollment from a campaign.",
)
async def remove_enrollment(
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    try:
        removed = campaign_service.remove_enrollment(db, current_org.id, campaign_id, contact_id)
    except (CampaignNotFoundError, ContactNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact enrollment not found.",
        )


@router.get(
    "/{campaign_id}/contacts",
    response_model=List[CampaignContactResponse],
    status_code=status.HTTP_200_OK,
    summary="List enrolled contacts",
    description="Lists contacts enrolled in a campaign.",
)
async def list_enrolled_contacts(
    campaign_id: uuid.UUID,
    response: Response,
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[CampaignContactResponse]:
    try:
        enrollments, total = campaign_service.list_enrolled_contacts(
            db, current_org.id, campaign_id, skip=skip, limit=limit
        )
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    response.headers["X-Total-Count"] = str(total)
    return [CampaignContactResponse.model_validate(e) for e in enrollments]


@router.patch(
    "/{campaign_id}/contacts/{contact_id}/status",
    response_model=CampaignContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Update contact enrollment status",
    description="Updates the enrollment status of a contact in a campaign.",
)
async def update_enrollment_status(
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: CampaignContactStatusUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignContactResponse:
    try:
        enrollment = campaign_service.update_enrollment_status(
            db, current_org.id, campaign_id, contact_id, payload.enrollment_status
        )
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidEnrollmentStatusError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact enrollment not found.",
        )
    return CampaignContactResponse.model_validate(enrollment)


# ── Workflow Builder & Template Preview Endpoints ─────────────────────────────

@router.get(
    "/{campaign_id}/workflow",
    response_model=WorkflowConfig,
    status_code=status.HTTP_200_OK,
    summary="Get campaign workflow configuration",
    description="Recovers or retrieves the visual workflow graph for a campaign with 100% backward compatibility.",
)
async def get_campaign_workflow_endpoint(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> WorkflowConfig:
    try:
        return get_or_recover_campaign_workflow(db, current_org.id, campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put(
    "/{campaign_id}/workflow",
    response_model=WorkflowSaveResponse,
    status_code=status.HTTP_200_OK,
    summary="Save campaign workflow configuration",
    description="Persists workflow nodes/edges, synchronizes email sequence steps, and validates configurations.",
)
async def save_campaign_workflow_endpoint(
    campaign_id: uuid.UUID,
    payload: WorkflowSaveRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> WorkflowSaveResponse:
    try:
        return save_campaign_workflow(
            db,
            current_org.id,
            campaign_id,
            payload.workflow_config,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{campaign_id}/workflow/validate",
    response_model=WorkflowValidationResult,
    status_code=status.HTTP_200_OK,
    summary="Validate workflow configuration",
    description="Checks workflow graph for errors, incomplete steps, unconfigured providers, and unsupported conditions.",
)
async def validate_workflow_endpoint(
    campaign_id: uuid.UUID,
    payload: WorkflowConfig,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> WorkflowValidationResult:
    campaign = campaign_service.get_campaign(db, current_org.id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign '{campaign_id}' not found.")
    return validate_workflow(payload)


@router.post(
    "/{campaign_id}/workflow/preview-template",
    response_model=TemplatePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview email step template",
    description="Renders subject and body templates using genuine persisted contact data and reports unresolved placeholders.",
)
async def preview_step_template_endpoint(
    campaign_id: uuid.UUID,
    payload: TemplatePreviewRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> TemplatePreviewResponse:
    campaign = campaign_service.get_campaign(db, current_org.id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign '{campaign_id}' not found.")
    return preview_template_content(db, current_org.id, payload, campaign_id=campaign.id)


@router.post(
    "/{campaign_id}/workflow/generate-email",
    response_model=AIEmailGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate email template for campaign with AI (AWS Bedrock)",
    description="Generates email subject and body using campaign context with AWS Bedrock Claude Sonnet 4.5.",
)
async def generate_campaign_email_endpoint(
    campaign_id: uuid.UUID,
    payload: AIEmailGenerateRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> AIEmailGenerateResponse:
    campaign = campaign_service.get_campaign(db, current_org.id, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign '{campaign_id}' not found.")

    if not payload.campaign_name:
        payload.campaign_name = campaign.name

    try:
        return generate_email_template(payload)
    except AITemplateConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except AITemplateGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )



# ── Campaign List Associations ───────────────────────────────────────────────

@router.get(
    "/{campaign_id}/lists",
    response_model=List[ContactListResponse],
    status_code=status.HTTP_200_OK,
    summary="List contact lists attached to campaign",
    description="Returns all contact lists associated with the given campaign.",
)
async def list_campaign_lists_endpoint(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[ContactListResponse]:
    try:
        return contact_list_service.list_campaign_attached_lists(db, current_org.id, campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{campaign_id}/lists",
    response_model=CampaignListAttachResponse,
    status_code=status.HTTP_200_OK,
    summary="Attach a contact list to a campaign",
    description="Associates a list with a campaign and synchronizes eligible members without triggering real outreach.",
)
async def attach_list_to_campaign_endpoint(
    campaign_id: uuid.UUID,
    payload: CampaignListAttachRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignListAttachResponse:
    try:
        return contact_list_service.attach_list_to_campaign(
            db, current_org.id, campaign_id, payload.contact_list_id
        )
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ContactListNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "/{campaign_id}/lists/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Detach a contact list from a campaign",
    description="Removes the campaign-list link while strictly preserving campaign enrollments and outreach history.",
)
async def detach_list_from_campaign_endpoint(
    campaign_id: uuid.UUID,
    list_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Response:
    success = contact_list_service.detach_list_from_campaign(db, current_org.id, campaign_id, list_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List is not attached to this campaign.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{campaign_id}/lists/{list_id}/sync",
    response_model=CampaignListSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync new members from contact list into campaign",
    description="Explicitly synchronizes newly added members into the campaign without resetting existing enrollments.",
)
async def sync_list_to_campaign_endpoint(
    campaign_id: uuid.UUID,
    list_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignListSyncResponse:
    try:
        return contact_list_service.sync_list_to_campaign(db, current_org.id, campaign_id, list_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ContactListNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


