"""Inbound Email & Microsoft Graph API Endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_current_organization,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.tenant import Organization, User
from app.schemas.inbound_email import (
    GraphCheckpointStatusResponse,
    GraphConfigStatusResponse,
    GraphSyncResultResponse,
    GraphSyncTriggerRequest,
    InboundEmailDetailResponse,
    InboundEmailListResponse,
    ManualReviewUpdatePayload,
)
from app.services.graph.sync_service import (
    get_checkpoint_status,
    get_inbound_email_detail,
    list_inbound_emails,
    list_sync_runs,
    sync_support_mailbox,
    update_manual_review_status,
)

router = APIRouter(prefix="/inbound-emails", tags=["Inbound Email & Support Mailbox"])


@router.get(
    "/config-status",
    response_model=GraphConfigStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Microsoft Graph configuration and safety status",
)
def get_graph_config_status(
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
) -> GraphConfigStatusResponse:
    """Returns safe configuration inspection without leaking secrets or tokens."""
    configured = settings.is_graph_configured
    enabled = settings.MICROSOFT_GRAPH_ENABLED
    mailbox = settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX
    flow = settings.MICROSOFT_GRAPH_AUTH_FLOW

    if not configured:
        msg = (
            "Microsoft Graph credentials are not configured in environment. "
            "Set MICROSOFT_GRAPH_TENANT_ID, CLIENT_ID, and CLIENT_SECRET in .env."
        )
        mode = "unconfigured"
    elif not enabled:
        msg = (
            "Microsoft Graph is configured but disabled by fail-closed safety guard "
            "(MICROSOFT_GRAPH_ENABLED=False). Set MICROSOFT_GRAPH_ENABLED=True to permit live sync."
        )
        mode = "safety_disabled"
    else:
        msg = f"Microsoft Graph is configured and active for mailbox {mailbox}."
        mode = "active"

    return GraphConfigStatusResponse(
        configured=configured,
        enabled=enabled,
        auto_sync_enabled=settings.MICROSOFT_GRAPH_AUTO_SYNC_ENABLED,
        sync_interval_minutes=settings.MICROSOFT_GRAPH_SYNC_INTERVAL_MINUTES,
        support_mailbox=mailbox,
        auth_flow=flow,
        approved_mailbox_only=True,
        permissions_required=["Mail.Read"],
        mode=mode,
        message=msg,
    )


@router.get(
    "/checkpoint-status",
    response_model=GraphCheckpointStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get mailbox synchronization checkpoint and active lock status",
)
def get_mailbox_checkpoint_status(
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> GraphCheckpointStatusResponse:
    """Returns the current checkpoint delta status and concurrency lock state for the tenant."""
    return get_checkpoint_status(db=db, org_id=current_org.id)


@router.get(
    "/sync-runs",
    response_model=List[GraphSyncResultResponse],
    status_code=status.HTTP_200_OK,
    summary="List past synchronization runs for tenant",
)
def get_sync_runs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[GraphSyncResultResponse]:
    """Retrieves sync history records for the authenticated tenant."""
    return list_sync_runs(db=db, org_id=current_org.id, limit=limit)


@router.post(
    "/sync",
    response_model=GraphSyncResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger manual synchronization of the support mailbox",
)
def trigger_mailbox_sync(
    payload: Optional[GraphSyncTriggerRequest] = None,
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> GraphSyncResultResponse:
    """
    Manually initiates an inbound email fetch from the approved support mailbox.
    Blocked if MICROSOFT_GRAPH_ENABLED=False (fail-closed safety).
    Guarded against concurrent overlapping jobs.
    Strictly restricted to authorized administrative users within the primary internal organization.
    """
    # 1. Require authorized internal admin role
    if current_user.role not in ("owner", "admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to trigger support mailbox synchronization.",
        )

    # 2. Require explicitly configured MICROSOFT_GRAPH_PRIMARY_ORG_ID
    primary_org_str = (settings.MICROSOFT_GRAPH_PRIMARY_ORG_ID or "").strip()
    if not primary_org_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Support mailbox synchronization is disabled: MICROSOFT_GRAPH_PRIMARY_ORG_ID is not configured.",
        )

    try:
        primary_org_uuid = uuid.UUID(primary_org_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Support mailbox synchronization is disabled: MICROSOFT_GRAPH_PRIMARY_ORG_ID is invalid.",
        )

    # 3. Strictly restrict to the primary internal organization (reject all customer tenants)
    if current_org.id != primary_org_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Support mailbox synchronization is restricted to the authorized internal organization.",
        )

    # 4. Validate payload parameters
    max_msgs = payload.max_messages if payload and payload.max_messages is not None else 50
    if max_msgs < 1 or max_msgs > 250:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_messages must be between 1 and 250.",
        )

    fld = (payload.folder if payload and payload.folder else "Inbox").strip()
    if fld.lower() != "inbox":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the 'Inbox' folder is supported for support mailbox synchronization.",
        )

    result = sync_support_mailbox(
        db=db,
        org_id=current_org.id,
        max_messages=max_msgs,
        folder="Inbox",
        trigger="manual",
        use_delta=True,
    )
    return result


@router.get(
    "",
    response_model=InboundEmailListResponse,
    status_code=status.HTTP_200_OK,
    summary="List ingested inbound emails for current organization",
)
def get_inbound_emails(
    status: Optional[str] = Query(None, description="Sync status filter (matched, unmatched, all)"),
    review_status: Optional[str] = Query(None, description="Review status filter (pending, reviewed, dismissed, archived, all)"),
    search: Optional[str] = Query(None, description="Search term for sender or subject"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> InboundEmailListResponse:
    """Lists ingested messages scoped strictly to tenant organization."""
    return list_inbound_emails(
        db=db,
        org_id=current_org.id,
        status_filter=status,
        review_status_filter=review_status,
        search=search,
        page=page,
        limit=limit,
    )


@router.get(
    "/{email_id}",
    response_model=InboundEmailDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get inbound email message detail and CRM match snapshot",
)
def get_inbound_email(
    email_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> InboundEmailDetailResponse:
    """
    Returns full message detail including matched Contact/Lead entity.
    External message body is explicitly marked as untrusted input.
    """
    detail = get_inbound_email_detail(db=db, org_id=current_org.id, email_id=email_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inbound email with ID {email_id} not found in this organization.",
        )
    return detail


@router.post(
    "/{email_id}/review",
    response_model=InboundEmailDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update manual review status for an unmatched email",
)
def update_email_review(
    email_id: uuid.UUID,
    payload: ManualReviewUpdatePayload,
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> InboundEmailDetailResponse:
    """Updates manual review triage state and reviewer notes."""
    updated = update_manual_review_status(
        db=db,
        org_id=current_org.id,
        email_id=email_id,
        new_status=payload.status,
        notes=payload.review_notes,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inbound email with ID {email_id} not found in this organization.",
        )
    return updated
