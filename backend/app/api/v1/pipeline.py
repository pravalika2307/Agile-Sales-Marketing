"""Pipeline and PipelineStage management API endpoints."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineResponse,
    PipelineStageCreate,
    PipelineStageResponse,
    PipelineStageUpdate,
    PipelineUpdate,
)
from app.services import pipeline_service

router = APIRouter(tags=["Pipelines"])


# ── Pipelines Endpoints ───────────────────────────────────────────────────────

@router.post(
    "/pipelines",
    response_model=PipelineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new sales pipeline",
    description="Creates a sales pipeline for the authenticated organization.",
)
async def create_pipeline(
    data: PipelineCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    pipeline = pipeline_service.create_pipeline(db, current_org.id, data)
    return PipelineResponse.model_validate(pipeline)


@router.get(
    "/pipelines",
    response_model=List[PipelineResponse],
    status_code=status.HTTP_200_OK,
    summary="List sales pipelines",
    description="Lists all sales pipelines belonging to the authenticated organization.",
)
async def list_pipelines(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[PipelineResponse]:
    pipelines = pipeline_service.list_pipelines(db, current_org.id)
    return [PipelineResponse.model_validate(p) for p in pipelines]


@router.get(
    "/pipelines/{pipeline_id}",
    response_model=PipelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Get pipeline by ID",
    description="Retrieves a specific sales pipeline and its ordered stages.",
)
async def get_pipeline(
    pipeline_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    pipeline = pipeline_service.get_pipeline(db, current_org.id, pipeline_id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found.",
        )
    return PipelineResponse.model_validate(pipeline)


@router.patch(
    "/pipelines/{pipeline_id}",
    response_model=PipelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Update pipeline",
    description="Partially update a sales pipeline.",
)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    data: PipelineUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    pipeline = pipeline_service.update_pipeline(db, current_org.id, pipeline_id, data)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found.",
        )
    return PipelineResponse.model_validate(pipeline)


@router.delete(
    "/pipelines/{pipeline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete pipeline",
    description="Deletes a pipeline and all its stages.",
)
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = pipeline_service.delete_pipeline(db, current_org.id, pipeline_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found.",
        )


# ── Pipeline Stages Endpoints ─────────────────────────────────────────────────

@router.post(
    "/pipelines/{pipeline_id}/stages",
    response_model=PipelineStageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create stage in pipeline",
    description="Creates a new stage within an existing pipeline.",
)
async def create_stage(
    pipeline_id: uuid.UUID,
    data: PipelineStageCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PipelineStageResponse:
    stage = pipeline_service.create_stage(db, current_org.id, pipeline_id, data)
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found.",
        )
    return PipelineStageResponse.model_validate(stage)


@router.get(
    "/pipelines/{pipeline_id}/stages",
    response_model=List[PipelineStageResponse],
    status_code=status.HTTP_200_OK,
    summary="List stages for pipeline",
    description="Lists all stages for a pipeline in visual order.",
)
async def list_stages(
    pipeline_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[PipelineStageResponse]:
    stages = pipeline_service.list_stages(db, current_org.id, pipeline_id)
    if stages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found.",
        )
    return [PipelineStageResponse.model_validate(s) for s in stages]


@router.patch(
    "/pipeline-stages/{stage_id}",
    response_model=PipelineStageResponse,
    status_code=status.HTTP_200_OK,
    summary="Update pipeline stage",
    description="Partially update a pipeline stage name, order_index, or probability_pct.",
)
async def update_stage(
    stage_id: uuid.UUID,
    data: PipelineStageUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> PipelineStageResponse:
    stage = pipeline_service.update_stage(db, current_org.id, stage_id, data)
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline stage not found.",
        )
    return PipelineStageResponse.model_validate(stage)


@router.delete(
    "/pipeline-stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete pipeline stage",
    description="Deletes a pipeline stage.",
)
async def delete_stage(
    stage_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = pipeline_service.delete_stage(db, current_org.id, stage_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline stage not found.",
        )
