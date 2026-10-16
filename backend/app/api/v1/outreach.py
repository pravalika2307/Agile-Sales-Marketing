"""Outreach and message lifecycle API endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.outreach import Outreach
from app.models.tenant import Organization
from app.schemas.outreach import (
    CallRecordInfoResponse,
    OutreachCreate,
    OutreachEventResponse,
    OutreachResponse,
    OutreachUpdate,
)
from app.services.outreach import service as outreach_service
from app.services.outreach.service import (
    AlreadySentError,
    CampaignCompletedError,
    CampaignContactNotFoundError,
    CampaignNotFoundError,
    CancelledOutreachError,
    ContactNotFoundError,
    CurrentlySendingError,
    EmptyOutreachBodyError,
    InconsistentEnrollmentError,
    InvalidOutreachTransitionError,
    InvalidRecipientEmailError,
    OutreachNotFoundError,
    ProviderDeliveryError,
    SuppressedRecipientError,
    UnresolvedTemplatePlaceholderError,
    UnsupportedChannelError,
)
from app.services.organization_config import MissingBookingUrlError

router = APIRouter(prefix="/outreach", tags=["Outreach"])


def _serialize_outreach(o: Outreach) -> OutreachResponse:
    """Enrich Outreach with linked contact, campaign, and call_record info."""
    contact_name = None
    company_name = None
    if o.contact:
        contact_name = f"{o.contact.first_name} {o.contact.last_name}".strip()
        if o.contact.company:
            company_name = o.contact.company.name

    campaign_name = None
    if o.campaign:
        campaign_name = o.campaign.name
    elif o.call_record:
        campaign_name = f"Voice Follow-up: {o.call_record.call_id}"

    recipient = o.recipient or o.recipient_email
    if not recipient and o.contact:
        recipient = o.contact.email

    call_rec = None
    if o.call_record:
        call_rec = CallRecordInfoResponse.model_validate(o.call_record)

    events_list = [OutreachEventResponse.model_validate(e) for e in o.events] if o.events else []

    return OutreachResponse(
        id=o.id,
        outreach_id=o.id,
        recipient=recipient,
        recipient_email=recipient,
        organization_id=o.organization_id,
        campaign_id=o.campaign_id,
        campaign_name=campaign_name,
        contact_id=o.contact_id,
        contact_name=contact_name,
        company_name=company_name,
        campaign_contact_id=o.campaign_contact_id,
        call_record_id=o.call_record_id,
        channel=o.channel,
        status=o.status,
        subject=o.subject,
        body=o.body,
        provider=o.provider,
        provider_message_id=o.provider_message_id,
        scheduled_at=o.scheduled_at,
        sent_at=o.sent_at,
        first_delivered_at=o.first_delivered_at,
        first_opened_at=o.first_opened_at,
        first_clicked_at=o.first_clicked_at,
        first_replied_at=o.first_replied_at,
        first_bounced_at=o.first_bounced_at,
        created_at=o.created_at,
        updated_at=o.updated_at,
        call_record=call_rec,
        events=events_list,
    )


@router.post(
    "",
    response_model=OutreachResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create outreach message",
    description="Creates an outreach item in draft status for an enrolled contact.",
)
async def create_outreach(
    data: OutreachCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    try:
        outreach = outreach_service.create_outreach(db, current_org.id, data)
    except (
        CampaignNotFoundError,
        ContactNotFoundError,
        CampaignContactNotFoundError,
        InconsistentEnrollmentError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return _serialize_outreach(outreach)


@router.get(
    "",
    response_model=List[OutreachResponse],
    status_code=status.HTTP_200_OK,
    summary="List outreach messages",
    description="Lists outreach items belonging to the authenticated organization with optional filtering.",
)
async def list_outreach(
    response: Response,
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by Campaign ID"),
    contact_id: Optional[uuid.UUID] = Query(None, description="Filter by Contact ID"),
    lead_id: Optional[uuid.UUID] = Query(None, description="Filter by Lead ID"),
    list_id: Optional[uuid.UUID] = Query(None, description="Filter by Contact List ID"),
    status: Optional[str] = Query(None, description="Filter by status (draft, scheduled, sending, sent, failed, cancelled)"),
    channel: Optional[str] = Query(None, description="Filter by channel (e.g. email)"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[OutreachResponse]:
    outreaches, total = outreach_service.list_outreach(
        db,
        current_org.id,
        campaign_id=campaign_id,
        contact_id=contact_id,
        lead_id=lead_id,
        list_id=list_id,
        status=status,
        channel=channel,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [_serialize_outreach(o) for o in outreaches]


@router.get(
    "/{outreach_id}",
    response_model=OutreachResponse,
    status_code=status.HTTP_200_OK,
    summary="Get outreach by ID",
    description="Retrieves a specific outreach item belonging to the authenticated organization.",
)
async def get_outreach(
    outreach_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    outreach = outreach_service.get_outreach(db, current_org.id, outreach_id)
    if not outreach:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach not found.",
        )
    return _serialize_outreach(outreach)


@router.patch(
    "/{outreach_id}",
    response_model=OutreachResponse,
    status_code=status.HTTP_200_OK,
    summary="Update outreach message",
    description="Updates editable content fields (subject, body, scheduled_at) of an outreach item.",
)
async def update_outreach(
    outreach_id: uuid.UUID,
    data: OutreachUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    outreach = outreach_service.update_outreach(db, current_org.id, outreach_id, data)
    if not outreach:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outreach not found.",
        )
    return _serialize_outreach(outreach)



@router.post(
    "/{outreach_id}/schedule",
    response_model=OutreachResponse,
    status_code=status.HTTP_200_OK,
    summary="Schedule outreach",
    description="Transitions an outreach item from draft or failed to scheduled.",
)
async def schedule_outreach(
    outreach_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    try:
        outreach = outreach_service.schedule_outreach(db, current_org.id, outreach_id)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidOutreachTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _serialize_outreach(outreach)


@router.post(
    "/{outreach_id}/send",
    response_model=OutreachResponse,
    status_code=status.HTTP_200_OK,
    summary="Send outreach",
    description="Executes delivery for a draft or scheduled outreach item via configured email provider.",
)
async def send_outreach(
    outreach_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    try:
        outreach = outreach_service.send_outreach(
            db,
            current_org.id,
            outreach_id,
            raise_on_failure=True,
        )
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (AlreadySentError, CurrentlySendingError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except (
        CancelledOutreachError,
        InvalidOutreachTransitionError,
        InvalidRecipientEmailError,
        EmptyOutreachBodyError,
        UnsupportedChannelError,
        CampaignCompletedError,
        CampaignNotFoundError,
        ContactNotFoundError,
        CampaignContactNotFoundError,
        InconsistentEnrollmentError,
        UnresolvedTemplatePlaceholderError,
        SuppressedRecipientError,
        MissingBookingUrlError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ProviderDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return _serialize_outreach(outreach)


@router.post(
    "/{outreach_id}/retry",
    response_model=OutreachResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry failed outreach",
    description="Retries a failed outreach item, strictly enforcing all suppression and tenant guards.",
)
async def retry_outreach_endpoint(
    outreach_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    try:
        outreach = outreach_service.retry_outreach(
            db,
            current_org.id,
            outreach_id,
            raise_on_failure=True,
        )
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (AlreadySentError, CurrentlySendingError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except (
        CancelledOutreachError,
        InvalidOutreachTransitionError,
        InvalidRecipientEmailError,
        EmptyOutreachBodyError,
        UnsupportedChannelError,
        CampaignCompletedError,
        CampaignNotFoundError,
        ContactNotFoundError,
        CampaignContactNotFoundError,
        InconsistentEnrollmentError,
        UnresolvedTemplatePlaceholderError,
        SuppressedRecipientError,
        MissingBookingUrlError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ProviderDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return _serialize_outreach(outreach)


@router.post(
    "/{outreach_id}/cancel",
    response_model=OutreachResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel outreach",
    description="Transitions a draft or scheduled outreach item to cancelled.",
)
async def cancel_outreach(
    outreach_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    try:
        outreach = outreach_service.cancel_outreach(db, current_org.id, outreach_id)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidOutreachTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _serialize_outreach(outreach)


@router.get(
    "/{outreach_id}/events",
    response_model=List[OutreachEventResponse],
    status_code=status.HTTP_200_OK,
    summary="List outreach events",
    description="Lists lifecycle audit events for an outreach message.",
)
async def list_outreach_events(
    outreach_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[OutreachEventResponse]:
    try:
        events = outreach_service.list_outreach_events(db, current_org.id, outreach_id)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return [OutreachEventResponse.model_validate(e) for e in events]
