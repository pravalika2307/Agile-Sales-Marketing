"""Tenant communication channel entitlements and upgrade request API endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_current_admin_user,
    get_current_organization,
    get_current_platform_admin_user,
)
from app.core.database import get_db
from app.models.tenant import Organization, User
from app.schemas.entitlement import (
    AdminUpgradeDecisionPayload,
    ChannelListResponse,
    ChannelUpgradeRequestPayload,
    ChannelUpgradeRequestResponse,
    UpgradeRequestDetailResponse,
)
from app.services.entitlements_service import (
    get_tenant_channel_capabilities,
    list_upgrade_requests,
    process_upgrade_decision,
    request_channel_upgrade,
)

router = APIRouter(prefix="/entitlements", tags=["Entitlements & Channel Upgrades"])


@router.get(
    "/channels",
    response_model=ChannelListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available communication channels and tenant entitlement status",
    description="Returns all platform channels (Email, SMS/MMS, AI Voice, Voicemail, Mail) and tenant unlock status.",
)
async def list_channel_capabilities(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ChannelListResponse:
    try:
        return get_tenant_channel_capabilities(db, current_org.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/upgrade-request",
    response_model=ChannelUpgradeRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit channel upgrade request for administrative approval",
    description="Allows a subscribing tenant to request activation of locked channels (SMS, Voice, RVM, Physical Mail).",
)
async def submit_channel_upgrade_request(
    payload: ChannelUpgradeRequestPayload,
    current_user: User = Depends(get_current_active_user),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ChannelUpgradeRequestResponse:
    try:
        return request_channel_upgrade(db, current_org.id, current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.get(
    "/upgrade-requests",
    response_model=List[UpgradeRequestDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="List upgrade requests submitted by the current organization",
    description="Returns status history of channel upgrade requests for the authenticated tenant.",
)
async def list_my_upgrade_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[UpgradeRequestDetailResponse]:
    return list_upgrade_requests(db, org_id=current_org.id, status_filter=status_filter)


@router.get(
    "/admin/upgrade-requests",
    response_model=List[UpgradeRequestDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="List all tenant upgrade requests (Platform Admin only)",
    description="Allows authorized platform operations administrators to view pending channel requests across all tenants.",
)
async def admin_list_all_upgrade_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    platform_admin: User = Depends(get_current_platform_admin_user),
    db: Session = Depends(get_db),
) -> List[UpgradeRequestDetailResponse]:
    return list_upgrade_requests(db, org_id=None, status_filter=status_filter)


@router.post(
    "/admin/upgrade-requests/{request_id}/decision",
    response_model=UpgradeRequestDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Review and decide on a channel upgrade request (Platform Admin only)",
    description="Approves or rejects a tenant's channel upgrade request with audit logging.",
)
async def admin_decide_upgrade_request(
    request_id: uuid.UUID,
    payload: AdminUpgradeDecisionPayload,
    platform_admin: User = Depends(get_current_platform_admin_user),
    db: Session = Depends(get_db),
) -> UpgradeRequestDetailResponse:
    try:
        return process_upgrade_decision(db, platform_admin, request_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
