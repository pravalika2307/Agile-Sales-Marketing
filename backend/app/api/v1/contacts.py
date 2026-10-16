"""Contact management API endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.contact import ContactCreate, ContactResponse, ContactUpdate
from app.services import contact_service
from app.services.contact_service import DuplicateContactError, InvalidCompanyReferenceError

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post(
    "",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contact prospect",
    description="Creates a contact within the authenticated tenant organization. Can link to an existing company in the same organization.",
)
async def create_contact(
    data: ContactCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactResponse:
    try:
        contact = contact_service.create_contact(db, current_org.id, data)
    except DuplicateContactError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except InvalidCompanyReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return ContactResponse.model_validate(contact)


@router.get(
    "",
    response_model=List[ContactResponse],
    status_code=status.HTTP_200_OK,
    summary="List contacts",
    description="List contacts belonging to the authenticated organization with optional filtering.",
)
async def list_contacts(
    response: Response,
    search: Optional[str] = Query(None, description="Search across first name, last name, or email"),
    lead_status: Optional[str] = Query(None, description="Filter by lead status"),
    company_id: Optional[uuid.UUID] = Query(None, description="Filter by company ID"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=500, description="Page size limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[ContactResponse]:
    contacts, total = contact_service.list_contacts(
        db,
        current_org.id,
        search=search,
        lead_status=lead_status,
        company_id=company_id,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [ContactResponse.model_validate(c) for c in contacts]


@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Get contact by ID",
    description="Retrieve a single contact by ID within the authenticated organization.",
)
async def get_contact(
    contact_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactResponse:
    contact = contact_service.get_contact(db, current_org.id, contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )
    return ContactResponse.model_validate(contact)


@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Update contact",
    description="Partially update a contact within the authenticated organization.",
)
async def update_contact(
    contact_id: uuid.UUID,
    data: ContactUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ContactResponse:
    try:
        contact = contact_service.update_contact(db, current_org.id, contact_id, data)
    except DuplicateContactError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except InvalidCompanyReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )
    return ContactResponse.model_validate(contact)


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete contact",
    description="Delete a contact within the authenticated organization.",
)
async def delete_contact(
    contact_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = contact_service.delete_contact(db, current_org.id, contact_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )
