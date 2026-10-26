"""CampaignStep domain service managing sequence steps and templates."""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.campaign_step import CampaignStep
from app.schemas.campaign_step import CampaignStepCreate, CampaignStepUpdate

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class CampaignStepServiceError(Exception):
    """Base exception for campaign step operations."""
    pass


class CampaignNotFoundError(CampaignStepServiceError):
    """Raised when the referenced campaign is not found in the tenant organization."""
    pass


class CampaignStepNotFoundError(CampaignStepServiceError):
    """Raised when a specific campaign step is not found in the tenant organization."""
    pass


class StepNumberAlreadyExistsError(CampaignStepServiceError):
    """Raised when attempting to create a step with a step_number that already exists."""
    pass


class CannotDeleteOnlyStep1Error(CampaignStepServiceError):
    """Raised when attempting to delete the only Step 1 of a campaign."""
    pass


class InvalidStepConfigurationError(CampaignStepServiceError):
    """Raised when invalid step parameters are provided."""
    pass


# ── Step CRUD Operations ──────────────────────────────────────────────────────

def create_campaign_step(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    data: CampaignStepCreate,
) -> CampaignStep:
    """
    Creates a new sequential step in a campaign.
    Enforces tenant ownership, step_number uniqueness, and valid configurations.
    """
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    if data.step_number < 1:
        raise InvalidStepConfigurationError("step_number must be greater than or equal to 1.")

    if data.delay_days < 0:
        raise InvalidStepConfigurationError("delay_days must be non-negative.")

    if data.delay_hours < 0 or data.delay_hours >= 24:
        raise InvalidStepConfigurationError("delay_hours must be between 0 and 23.")

    # Check for duplicate step_number within the campaign
    existing = (
        db.query(CampaignStep)
        .filter(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.step_number == data.step_number,
        )
        .first()
    )
    if existing:
        raise StepNumberAlreadyExistsError(
            f"Step number {data.step_number} already exists in campaign '{campaign_id}'."
        )

    step = CampaignStep(
        organization_id=org_id,
        campaign_id=campaign_id,
        step_number=data.step_number,
        step_type=data.step_type,
        subject_template=data.subject_template,
        body_template=data.body_template,
        delay_days=data.delay_days,
        delay_hours=data.delay_hours,
        is_active=data.is_active,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def list_campaign_steps(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> List[CampaignStep]:
    """Lists all sequence steps for a campaign ordered by step_number ascending."""
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    return (
        db.query(CampaignStep)
        .filter(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.organization_id == org_id,
        )
        .order_by(CampaignStep.step_number.asc())
        .all()
    )


def get_campaign_step(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
) -> Optional[Any]:
    """Retrieves a specific campaign step strictly scoped to the tenant organization."""
    db_step = (
        db.query(CampaignStep)
        .filter(
            CampaignStep.id == step_id,
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.organization_id == org_id,
        )
        .first()
    )
    if db_step:
        return db_step

    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        return None

    from app.services.workflow_service import get_campaign_ordered_steps
    steps = get_campaign_ordered_steps(db, campaign)
    return next((s for s in steps if s.id == step_id), None)


def update_campaign_step(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
    data: CampaignStepUpdate,
) -> Optional[CampaignStep]:
    """
    Partially updates template and configuration fields of a campaign step.
    Does NOT allow updating step_number, campaign_id, or organization_id.
    """
    step = get_campaign_step(db, org_id, campaign_id, step_id)
    if not step:
        return None

    update_dict = data.model_dump(exclude_unset=True)

    if "delay_days" in update_dict and update_dict["delay_days"] is not None:
        if update_dict["delay_days"] < 0:
            raise InvalidStepConfigurationError("delay_days must be non-negative.")
        step.delay_days = update_dict["delay_days"]

    if "delay_hours" in update_dict and update_dict["delay_hours"] is not None:
        if update_dict["delay_hours"] < 0 or update_dict["delay_hours"] >= 24:
            raise InvalidStepConfigurationError("delay_hours must be between 0 and 23.")
        step.delay_hours = update_dict["delay_hours"]

    if "subject_template" in update_dict:
        step.subject_template = update_dict["subject_template"]

    if "body_template" in update_dict:
        step.body_template = update_dict["body_template"]

    if "is_active" in update_dict and update_dict["is_active"] is not None:
        step.is_active = update_dict["is_active"]

    db.commit()
    db.refresh(step)
    return step


def delete_campaign_step(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    step_id: uuid.UUID,
) -> bool:
    """
    Deletes a campaign step.
    Safety rule: If campaign has only one step and it is Step 1, deletion is rejected.
    """
    step = get_campaign_step(db, org_id, campaign_id, step_id)
    if not step:
        return False

    total_steps = (
        db.query(CampaignStep)
        .filter(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.organization_id == org_id,
        )
        .count()
    )

    if total_steps == 1 and step.step_number == 1:
        raise CannotDeleteOnlyStep1Error(
            "Cannot delete the only Step 1 of a campaign. You can deactivate it instead."
        )

    db.delete(step)
    db.commit()
    return True
