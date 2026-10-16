"""Company management API endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate
from app.services import company_service
from app.services.company_service import DuplicateCompanyError

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company account",
    description="Creates a company account within the authenticated tenant organization.",
)
async def create_company(
    data: CompanyCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CompanyResponse:
    try:
        company = company_service.create_company(db, current_org.id, data)
    except DuplicateCompanyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return CompanyResponse.model_validate(company)


@router.get(
    "",
    response_model=List[CompanyResponse],
    status_code=status.HTTP_200_OK,
    summary="List companies",
    description="List companies belonging to the authenticated organization with optional filtering.",
)
async def list_companies(
    response: Response,
    search: Optional[str] = Query(None, description="Search by company name"),
    industry: Optional[str] = Query(None, description="Filter by industry"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=500, description="Page size limit"),
    page: Optional[int] = Query(None, ge=1, description="1-based page number"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[CompanyResponse]:
    offset = skip
    if page is not None:
        offset = (page - 1) * limit

    companies, total = company_service.list_companies(
        db,
        current_org.id,
        search=search,
        industry=industry,
        skip=offset,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [CompanyResponse.model_validate(c) for c in companies]


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get company by ID",
    description="Retrieve a single company by ID within the authenticated organization.",
)
async def get_company(
    company_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CompanyResponse:
    company = company_service.get_company(db, current_org.id, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )
    return CompanyResponse.model_validate(company)


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
    status_code=status.HTTP_200_OK,
    summary="Update company",
    description="Partially update a company within the authenticated organization.",
)
async def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CompanyResponse:
    company = company_service.update_company(db, current_org.id, company_id, data)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )
    return CompanyResponse.model_validate(company)


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete company",
    description="Delete a company within the authenticated organization.",
)
async def delete_company(
    company_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = company_service.delete_company(db, current_org.id, company_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )
