"""Ideal Customer Profile (ICP) API endpoints."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.icp import (
    IdealCustomerProfileCreate,
    IdealCustomerProfileResponse,
    IdealCustomerProfileUpdate,
)
from app.schemas.lead import LeadGenerationRequest, LeadResponse
from app.services import icp_service
from app.services.lead_generation import generate_leads

router = APIRouter(prefix="/icps", tags=["Ideal Customer Profiles"])


@router.post(
    "",
    response_model=IdealCustomerProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an Ideal Customer Profile",
    description="Defines target company and persona criteria for B2B prospect generation.",
)
async def create_icp(
    data: IdealCustomerProfileCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> IdealCustomerProfileResponse:
    icp = icp_service.create_icp(db, current_org.id, data)
    return IdealCustomerProfileResponse.model_validate(icp)


@router.get(
    "",
    response_model=List[IdealCustomerProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="List Ideal Customer Profiles",
    description="List all ICP definitions belonging to the authenticated tenant organization.",
)
async def list_icps(
    response: Response,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[IdealCustomerProfileResponse]:
    icps, total = icp_service.list_icps(
        db,
        current_org.id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [IdealCustomerProfileResponse.model_validate(item) for item in icps]


@router.get(
    "/{icp_id}",
    response_model=IdealCustomerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get an Ideal Customer Profile",
    description="Retrieve a single ICP definition by ID within the current tenant.",
)
async def get_icp(
    icp_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> IdealCustomerProfileResponse:
    icp = icp_service.get_icp(db, current_org.id, icp_id)
    return IdealCustomerProfileResponse.model_validate(icp)


@router.patch(
    "/{icp_id}",
    response_model=IdealCustomerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an Ideal Customer Profile",
    description="Partially update ICP definition criteria.",
)
async def update_icp(
    icp_id: uuid.UUID,
    data: IdealCustomerProfileUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> IdealCustomerProfileResponse:
    icp = icp_service.update_icp(db, current_org.id, icp_id, data)
    return IdealCustomerProfileResponse.model_validate(icp)


@router.delete(
    "/{icp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an Ideal Customer Profile",
    description="Deletes an ICP definition belonging to the authenticated tenant.",
)
async def delete_icp(
    icp_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    icp_service.delete_icp(db, current_org.id, icp_id)


@router.post(
    "/{icp_id}/generate",
    status_code=status.HTTP_200_OK,
    summary="Generate prospects from ICP",
    description="Search and create candidate Lead prospects based on the target ICP criteria.",
)
async def generate_prospects(
    icp_id: uuid.UUID,
    payload: LeadGenerationRequest = LeadGenerationRequest(limit=10),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    result = generate_leads(
        db=db,
        current_org=current_org,
        icp_id=icp_id,
        limit=payload.limit,
    )
    return {
        "created_count": result["created_count"],
        "skipped_count": result["skipped_count"],
        "leads": [LeadResponse.model_validate(l) for l in result["leads"]],
    }
