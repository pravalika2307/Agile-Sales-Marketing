"""API endpoints for Contact Lists and Membership Management."""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.contact_list import (
    ContactListAddMembersRequest,
    ContactListAddMembersResponse,
    ContactListCatalogResponse,
    ContactListCreate,
    ContactListDetailResponse,
    ContactListMemberListResponse,
    ContactListResponse,
    ContactListUpdate,
)
from app.services import contact_list_service
from app.services.contact_list_service import (
    ContactListMemberNotFoundError,
    ContactListNotFoundError,
    DuplicateContactListNameError,
)

router = APIRouter(prefix="/lists", tags=["Lists"])


@router.post(
    "",
    response_model=ContactListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a named contact list",
    description="Creates a new static or dynamic lead/contact list for the organization.",
)
async def create_contact_list(
    data: ContactListCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactListResponse:
    try:
        created = contact_list_service.create_contact_list(db, current_org.id, data)
        return ContactListResponse(
            id=created.id,
            organization_id=created.organization_id,
            name=created.name,
            description=created.description,
            type=created.type,
            member_count=0,
            campaigns_count=0,
            created_at=created.created_at,
            updated_at=created.updated_at,
        )
    except DuplicateContactListNameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "",
    response_model=ContactListCatalogResponse,
    status_code=status.HTTP_200_OK,
    summary="List contact lists",
    description="Lists all contact lists for the organization with member and campaign counts.",
)
async def list_contact_lists(
    search: Optional[str] = Query(None, description="Filter lists by name or description substring"),
    list_type: Optional[str] = Query(None, description="Filter lists by type (source, industry, static)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactListCatalogResponse:
    items, total = contact_list_service.list_contact_lists(
        db, current_org.id, search=search, list_type=list_type, skip=skip, limit=limit
    )
    return ContactListCatalogResponse(items=items, total=total, skip=skip, limit=limit)


@router.post(
    "/sync-sources",
    status_code=status.HTTP_200_OK,
    summary="Synchronize source and category lists",
    description="Organizes existing leads into source-based and industry-based lists safely using verified metadata.",
)
async def sync_source_lists(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return contact_list_service.sync_source_and_category_lists(db, current_org.id)


@router.get(
    "/{list_id}",
    response_model=ContactListDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get contact list details",
    description="Returns detailed contact list information, email validity breakdown, associated campaigns, and activity metrics.",
)
async def get_contact_list(
    list_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactListDetailResponse:
    try:
        return contact_list_service.get_contact_list_detail(db, current_org.id, list_id)
    except ContactListNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put(
    "/{list_id}",
    response_model=ContactListResponse,
    status_code=status.HTTP_200_OK,
    summary="Update contact list",
    description="Updates list name or description with unique name check.",
)
async def update_contact_list(
    list_id: uuid.UUID,
    data: ContactListUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactListResponse:
    try:
        updated = contact_list_service.update_contact_list(db, current_org.id, list_id, data)
        # Fetch counts
        detail = contact_list_service.get_contact_list_detail(db, current_org.id, list_id)
        return ContactListResponse(
            id=updated.id,
            organization_id=updated.organization_id,
            name=updated.name,
            description=updated.description,
            type=updated.type,
            member_count=detail.member_count,
            campaigns_count=detail.campaigns_count,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )
    except ContactListNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DuplicateContactListNameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete(
    "/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete contact list",
    description="Deletes a contact list while strictly preserving underlying contacts, leads, campaigns, and outreach records.",
)
async def delete_contact_list(
    list_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Response:
    success = contact_list_service.delete_contact_list(db, current_org.id, list_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact list '{list_id}' not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{list_id}/members",
    response_model=ContactListMemberListResponse,
    status_code=status.HTTP_200_OK,
    summary="List members in a contact list",
    description="Returns members of a contact list with unresolved email indicators and pagination.",
)
async def list_contact_list_members(
    list_id: uuid.UUID,
    search: Optional[str] = Query(None, description="Search by name, email, or company"),
    has_unresolved_email: Optional[bool] = Query(None, description="Filter by unresolved email status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactListMemberListResponse:
    try:
        items, total = contact_list_service.list_members(
            db,
            current_org.id,
            list_id,
            search=search,
            has_unresolved_email=has_unresolved_email,
            skip=skip,
            limit=limit,
        )
        return ContactListMemberListResponse(items=items, total=total, skip=skip, limit=limit)
    except ContactListNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{list_id}/members",
    response_model=ContactListAddMembersResponse,
    status_code=status.HTTP_200_OK,
    summary="Add contacts or leads to a list",
    description="Adds CRM contacts or raw leads to a list. Deduplicates automatically and preserves unresolved leads.",
)
async def add_contact_list_members(
    list_id: uuid.UUID,
    payload: ContactListAddMembersRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactListAddMembersResponse:
    try:
        return contact_list_service.add_members_to_list(
            db,
            current_org.id,
            list_id,
            contact_ids=payload.contact_ids,
            lead_ids=payload.lead_ids,
        )
    except ContactListNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "/{list_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove a member from a list",
    description="Removes membership from the list while keeping underlying CRM contact and campaign enrollment untouched.",
)
async def remove_contact_list_member(
    list_id: uuid.UUID,
    member_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Response:
    try:
        deleted = contact_list_service.remove_member_from_list(db, current_org.id, list_id, member_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in list.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (ContactListNotFoundError, ContactListMemberNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
