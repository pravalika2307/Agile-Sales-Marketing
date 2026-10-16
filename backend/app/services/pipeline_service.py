"""Pipeline domain service managing tenant-scoped pipelines and stages."""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.crm import Pipeline, PipelineStage
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineStageCreate,
    PipelineStageUpdate,
    PipelineUpdate,
)

logger = logging.getLogger(__name__)


# ── Pipeline Operations ───────────────────────────────────────────────────────

def create_pipeline(
    db: Session,
    org_id: uuid.UUID,
    data: PipelineCreate,
) -> Pipeline:
    """Create a new sales pipeline for the organization."""
    if data.is_default:
        # Unset previous default pipeline for this organization
        db.query(Pipeline).filter(
            Pipeline.organization_id == org_id,
            Pipeline.is_default.is_(True),
        ).update({"is_default": False})

    pipeline = Pipeline(
        organization_id=org_id,
        name=data.name.strip(),
        is_default=bool(data.is_default),
    )
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return pipeline


def get_pipeline(
    db: Session,
    org_id: uuid.UUID,
    pipeline_id: uuid.UUID,
) -> Optional[Pipeline]:
    """Retrieve a pipeline strictly scoped to the tenant organization."""
    return (
        db.query(Pipeline)
        .filter(Pipeline.id == pipeline_id, Pipeline.organization_id == org_id)
        .first()
    )


def list_pipelines(
    db: Session,
    org_id: uuid.UUID,
) -> List[Pipeline]:
    """List all pipelines for a tenant organization, default first."""
    return (
        db.query(Pipeline)
        .filter(Pipeline.organization_id == org_id)
        .order_by(Pipeline.is_default.desc(), Pipeline.created_at.asc())
        .all()
    )


def update_pipeline(
    db: Session,
    org_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    data: PipelineUpdate,
) -> Optional[Pipeline]:
    """Partially update a pipeline strictly scoped to the tenant organization."""
    pipeline = get_pipeline(db, org_id, pipeline_id)
    if not pipeline:
        return None

    update_dict = data.model_dump(exclude_unset=True)

    if update_dict.get("is_default") is True:
        # Unset other pipelines' default status
        db.query(Pipeline).filter(
            Pipeline.organization_id == org_id,
            Pipeline.id != pipeline_id,
            Pipeline.is_default.is_(True),
        ).update({"is_default": False})

    for field, val in update_dict.items():
        if val is not None and isinstance(val, str):
            val = val.strip()
        setattr(pipeline, field, val)

    db.commit()
    db.refresh(pipeline)
    return pipeline


def delete_pipeline(
    db: Session,
    org_id: uuid.UUID,
    pipeline_id: uuid.UUID,
) -> bool:
    """Delete a pipeline and cascade to its stages strictly scoped to the tenant organization."""
    pipeline = get_pipeline(db, org_id, pipeline_id)
    if not pipeline:
        return False

    db.delete(pipeline)
    db.commit()
    return True


# ── Pipeline Stage Operations ─────────────────────────────────────────────────

def create_stage(
    db: Session,
    org_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    data: PipelineStageCreate,
) -> Optional[PipelineStage]:
    """Create a stage within a pipeline owned by the tenant organization."""
    pipeline = get_pipeline(db, org_id, pipeline_id)
    if not pipeline:
        return None

    stage = PipelineStage(
        pipeline_id=pipeline_id,
        name=data.name.strip(),
        order_index=data.order_index,
        probability_pct=data.probability_pct,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


def get_stage(
    db: Session,
    org_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> Optional[PipelineStage]:
    """Retrieve a pipeline stage strictly scoped to the tenant organization."""
    return (
        db.query(PipelineStage)
        .join(Pipeline, Pipeline.id == PipelineStage.pipeline_id)
        .filter(PipelineStage.id == stage_id, Pipeline.organization_id == org_id)
        .first()
    )


def list_stages(
    db: Session,
    org_id: uuid.UUID,
    pipeline_id: uuid.UUID,
) -> Optional[List[PipelineStage]]:
    """List ordered stages for a pipeline owned by the tenant organization."""
    pipeline = get_pipeline(db, org_id, pipeline_id)
    if not pipeline:
        return None

    return (
        db.query(PipelineStage)
        .filter(PipelineStage.pipeline_id == pipeline_id)
        .order_by(PipelineStage.order_index.asc(), PipelineStage.created_at.asc())
        .all()
    )


def update_stage(
    db: Session,
    org_id: uuid.UUID,
    stage_id: uuid.UUID,
    data: PipelineStageUpdate,
) -> Optional[PipelineStage]:
    """Partially update a pipeline stage strictly scoped to the tenant organization."""
    stage = get_stage(db, org_id, stage_id)
    if not stage:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if val is not None and isinstance(val, str):
            val = val.strip()
        setattr(stage, field, val)

    db.commit()
    db.refresh(stage)
    return stage


def delete_stage(
    db: Session,
    org_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> bool:
    """Delete a pipeline stage strictly scoped to the tenant organization."""
    stage = get_stage(db, org_id, stage_id)
    if not stage:
        return False

    db.delete(stage)
    db.commit()
    return True
