"""Deal management API endpoints."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.deal import (
    DealCreate,
    DealResponse,
    DealStageMove,
    DealStatusUpdate,
    DealUpdate,
)
from app.services import deal_service
from app.services.deal_service import (
    CrossPipelineMovementError,
    InvalidCompanyReferenceError,
    InvalidContactReferenceError,
    InvalidDealStatusError,
    InvalidStageReferenceError,
)

router = APIRouter(prefix="/deals", tags=["Deals"])


@router.post(
    "",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new deal",
    description="Creates a deal belonging strictly to the authenticated organization.",
)
async def create_deal(
    data: DealCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> DealResponse:
    try:
        deal = deal_service.create_deal(db, current_org.id, data)
    except (
        InvalidStageReferenceError,
        InvalidContactReferenceError,
        InvalidCompanyReferenceError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return DealResponse.model_validate(deal)


@router.get(
    "",
    response_model=List[DealResponse],
    status_code=status.HTTP_200_OK,
    summary="List deals",
    description="List deals belonging to the authenticated organization with optional filtering.",
)
async def list_deals(
    response: Response,
    status: Optional[str] = Query(None, description="Filter by deal status (open, won, lost)"),
    pipeline_id: Optional[uuid.UUID] = Query(None, description="Filter by pipeline ID"),
    pipeline_stage_id: Optional[uuid.UUID] = Query(None, description="Filter by stage ID"),
    contact_id: Optional[uuid.UUID] = Query(None, description="Filter by contact ID"),
    company_id: Optional[uuid.UUID] = Query(None, description="Filter by company ID"),
    search: Optional[str] = Query(None, description="Search deals by name"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page size limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[DealResponse]:
    deals, total = deal_service.list_deals(
        db,
        current_org.id,
        status=status,
        pipeline_id=pipeline_id,
        pipeline_stage_id=pipeline_stage_id,
        contact_id=contact_id,
        company_id=company_id,
        search=search,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [DealResponse.model_validate(d) for d in deals]


@router.get(
    "/{deal_id}",
    response_model=DealResponse,
    status_code=status.HTTP_200_OK,
    summary="Get deal by ID",
    description="Retrieve a single deal by ID within the authenticated organization.",
)
async def get_deal(
    deal_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> DealResponse:
    deal = deal_service.get_deal(db, current_org.id, deal_id)
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found.",
        )
    return DealResponse.model_validate(deal)


@router.patch(
    "/{deal_id}",
    response_model=DealResponse,
    status_code=status.HTTP_200_OK,
    summary="Update deal",
    description="Partially update a deal within the authenticated organization.",
)
async def update_deal(
    deal_id: uuid.UUID,
    data: DealUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> DealResponse:
    try:
        deal = deal_service.update_deal(db, current_org.id, deal_id, data)
    except (
        InvalidStageReferenceError,
        InvalidContactReferenceError,
        InvalidCompanyReferenceError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found.",
        )
    return DealResponse.model_validate(deal)


@router.delete(
    "/{deal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete deal",
    description="Delete a deal within the authenticated organization.",
)
async def delete_deal(
    deal_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = deal_service.delete_deal(db, current_org.id, deal_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found.",
        )


@router.patch(
    "/{deal_id}/stage",
    response_model=DealResponse,
    status_code=status.HTTP_200_OK,
    summary="Move deal stage",
    description="Move a deal to another stage within the same pipeline.",
)
async def move_deal_stage(
    deal_id: uuid.UUID,
    data: DealStageMove,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> DealResponse:
    try:
        deal = deal_service.move_deal_stage(db, current_org.id, deal_id, data.pipeline_stage_id)
    except InvalidStageReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except CrossPipelineMovementError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found.",
        )
    return DealResponse.model_validate(deal)


@router.patch(
    "/{deal_id}/status",
    response_model=DealResponse,
    status_code=status.HTTP_200_OK,
    summary="Update deal status",
    description="Update a deal's status to open, won, or lost.",
)
async def update_deal_status(
    deal_id: uuid.UUID,
    data: DealStatusUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> DealResponse:
    try:
        deal = deal_service.update_deal_status(db, current_org.id, deal_id, data.status)
    except InvalidDealStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found.",
        )
    return DealResponse.model_validate(deal)
