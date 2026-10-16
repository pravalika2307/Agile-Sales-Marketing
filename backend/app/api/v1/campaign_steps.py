"""CampaignStep API endpoints for sequence and template management (Step 9)."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.campaign_step import (
    CampaignStepCreate,
    CampaignStepResponse,
    CampaignStepUpdate,
)
from app.services.campaign_steps import (
    CampaignNotFoundError,
    CampaignStepNotFoundError,
    CannotDeleteOnlyStep1Error,
    InvalidStepConfigurationError,
    StepNumberAlreadyExistsError,
    create_campaign_step,
    delete_campaign_step,
    get_campaign_step,
    list_campaign_steps,
    update_campaign_step,
)

router = APIRouter(prefix="/campaigns", tags=["Campaign Steps"])


@router.post(
    "/{campaign_id}/steps",
    response_model=CampaignStepResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create campaign step",
    description="Creates a new sequential outreach step in the specified campaign.",
)
async def create_step(
    campaign_id: uuid.UUID,
    data: CampaignStepCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignStepResponse:
    try:
        step = create_campaign_step(db, current_org.id, campaign_id, data)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except StepNumberAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except InvalidStepConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CampaignStepResponse.model_validate(step)


@router.get(
    "/{campaign_id}/steps",
    response_model=List[CampaignStepResponse],
    status_code=status.HTTP_200_OK,
    summary="List campaign steps",
    description="Lists all sequential steps configured for a campaign ordered by step_number ascending.",
)
async def list_steps(
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[CampaignStepResponse]:
    try:
        steps = list_campaign_steps(db, current_org.id, campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return [CampaignStepResponse.model_validate(s) for s in steps]


@router.get(
    "/{campaign_id}/steps/{step_id}",
    response_model=CampaignStepResponse,
    status_code=status.HTTP_200_OK,
    summary="Get campaign step by ID",
    description="Retrieves a specific campaign step scoped to the tenant organization.",
)
async def get_step(
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignStepResponse:
    step = get_campaign_step(db, current_org.id, campaign_id, step_id)
    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign step not found.",
        )
    return CampaignStepResponse.model_validate(step)


@router.patch(
    "/{campaign_id}/steps/{step_id}",
    response_model=CampaignStepResponse,
    status_code=status.HTTP_200_OK,
    summary="Update campaign step",
    description="Partially updates editable content and delay configurations of a campaign step.",
)
async def update_step(
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
    data: CampaignStepUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignStepResponse:
    try:
        step = update_campaign_step(db, current_org.id, campaign_id, step_id, data)
    except InvalidStepConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign step not found.",
        )
    return CampaignStepResponse.model_validate(step)


@router.delete(
    "/{campaign_id}/steps/{step_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete campaign step",
    description="Deletes a step from a campaign. Deletion is rejected if it is the only Step 1.",
)
async def delete_step(
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> Response:
    try:
        deleted = delete_campaign_step(db, current_org.id, campaign_id, step_id)
    except CannotDeleteOnlyStep1Error as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign step not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
