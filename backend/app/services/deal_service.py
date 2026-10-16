"""Deal domain service managing tenant-scoped operations, cross-tenant validation, and stage movement."""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.crm import (
    ALLOWED_DEAL_STATUSES,
    Company,
    Contact,
    Deal,
    Pipeline,
    PipelineStage,
)
from app.schemas.deal import DealCreate, DealUpdate

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class DealServiceError(Exception):
    """Base exception for deal service operations."""
    pass


class InvalidStageReferenceError(DealServiceError):
    """Raised when target pipeline stage does not exist in the tenant organization."""
    pass


class InvalidContactReferenceError(DealServiceError):
    """Raised when associated contact does not exist in the tenant organization."""
    pass


class InvalidCompanyReferenceError(DealServiceError):
    """Raised when associated company does not exist in the tenant organization."""
    pass


class CrossPipelineMovementError(DealServiceError):
    """Raised when attempting to move a deal to a stage in a different pipeline."""
    pass


class InvalidDealStatusError(DealServiceError):
    """Raised when an invalid deal status is specified."""
    pass


# ── Tenant Consistency Verification Helpers ───────────────────────────────────

def _verify_tenant_stage(db: Session, org_id: uuid.UUID, stage_id: uuid.UUID) -> PipelineStage:
    """
    Verify stage exists and belongs to a pipeline owned by the tenant organization.
    Raises InvalidStageReferenceError if not found or cross-tenant.
    """
    stage = (
        db.query(PipelineStage)
        .join(Pipeline, Pipeline.id == PipelineStage.pipeline_id)
        .filter(PipelineStage.id == stage_id, Pipeline.organization_id == org_id)
        .first()
    )
    if not stage:
        raise InvalidStageReferenceError(
            f"Pipeline stage '{stage_id}' not found in the current organization."
        )
    return stage


def _verify_tenant_contact(db: Session, org_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    """
    Verify contact exists and belongs to the tenant organization.
    Raises InvalidContactReferenceError if not found or cross-tenant.
    """
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.organization_id == org_id)
        .first()
    )
    if not contact:
        raise InvalidContactReferenceError(
            f"Contact '{contact_id}' not found in the current organization."
        )
    return contact


def _verify_tenant_company(db: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> Company:
    """
    Verify company exists and belongs to the tenant organization.
    Raises InvalidCompanyReferenceError if not found or cross-tenant.
    """
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.organization_id == org_id)
        .first()
    )
    if not company:
        raise InvalidCompanyReferenceError(
            f"Company '{company_id}' not found in the current organization."
        )
    return company


# ── Core Deal Operations ──────────────────────────────────────────────────────

def create_deal(
    db: Session,
    org_id: uuid.UUID,
    data: DealCreate,
) -> Deal:
    """
    Create a new deal strictly scoped to the tenant organization.
    Validates stage, contact, and company tenant ownership.
    """
    _verify_tenant_stage(db, org_id, data.pipeline_stage_id)

    if data.contact_id:
        _verify_tenant_contact(db, org_id, data.contact_id)

    if data.company_id:
        _verify_tenant_company(db, org_id, data.company_id)

    deal = Deal(
        organization_id=org_id,
        pipeline_stage_id=data.pipeline_stage_id,
        contact_id=data.contact_id,
        company_id=data.company_id,
        name=data.name.strip(),
        amount=float(data.amount) if isinstance(data.amount, Decimal) else data.amount,
        expected_close_date=data.expected_close_date,
        status=data.status or "open",
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


def get_deal(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
) -> Optional[Deal]:
    """Retrieve a deal by ID strictly scoped to the tenant organization."""
    return (
        db.query(Deal)
        .filter(Deal.id == deal_id, Deal.organization_id == org_id)
        .first()
    )


def list_deals(
    db: Session,
    org_id: uuid.UUID,
    status: Optional[str] = None,
    pipeline_id: Optional[uuid.UUID] = None,
    pipeline_stage_id: Optional[uuid.UUID] = None,
    contact_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Deal], int]:
    """
    List deals belonging to the tenant organization with optional filtering.
    Returns (deals, total_count).
    """
    query = db.query(Deal).filter(Deal.organization_id == org_id)

    if pipeline_id:
        query = query.join(PipelineStage, Deal.pipeline_stage_id == PipelineStage.id).filter(
            PipelineStage.pipeline_id == pipeline_id
        )

    if pipeline_stage_id:
        query = query.filter(Deal.pipeline_stage_id == pipeline_stage_id)

    if status and status.strip():
        query = query.filter(Deal.status == status.strip().lower())

    if contact_id:
        query = query.filter(Deal.contact_id == contact_id)

    if company_id:
        query = query.filter(Deal.company_id == company_id)

    if search and search.strip():
        query = query.filter(Deal.name.ilike(f"%{search.strip()}%"))

    total = query.count()
    deals = (
        query.order_by(Deal.created_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 100))
        .all()
    )
    return deals, total


def update_deal(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
    data: DealUpdate,
) -> Optional[Deal]:
    """Partially update a deal strictly scoped to the tenant organization."""
    deal = get_deal(db, org_id, deal_id)
    if not deal:
        return None

    update_dict = data.model_dump(exclude_unset=True)

    if "pipeline_stage_id" in update_dict and update_dict["pipeline_stage_id"] is not None:
        _verify_tenant_stage(db, org_id, update_dict["pipeline_stage_id"])

    if "contact_id" in update_dict and update_dict["contact_id"] is not None:
        _verify_tenant_contact(db, org_id, update_dict["contact_id"])

    if "company_id" in update_dict and update_dict["company_id"] is not None:
        _verify_tenant_company(db, org_id, update_dict["company_id"])

    for field, val in update_dict.items():
        if field == "name" and isinstance(val, str):
            val = val.strip()
        elif field == "status" and isinstance(val, str):
            val = val.strip().lower()
        elif field == "amount" and isinstance(val, Decimal):
            val = float(val)
        setattr(deal, field, val)

    db.commit()
    db.refresh(deal)
    return deal


def delete_deal(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
) -> bool:
    """Delete a deal strictly scoped to the tenant organization."""
    deal = get_deal(db, org_id, deal_id)
    if not deal:
        return False

    db.delete(deal)
    db.commit()
    return True


def move_deal_stage(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
    target_stage_id: uuid.UUID,
) -> Optional[Deal]:
    """
    Move a deal to a new stage within the same pipeline.
    Validates tenant ownership and ensures target stage belongs to the same pipeline.
    Does not automatically alter deal status (open/won/lost).
    """
    deal = get_deal(db, org_id, deal_id)
    if not deal:
        return None

    target_stage = _verify_tenant_stage(db, org_id, target_stage_id)

    # Get current stage to check pipeline identity
    current_stage = (
        db.query(PipelineStage)
        .filter(PipelineStage.id == deal.pipeline_stage_id)
        .first()
    )

    if current_stage and current_stage.pipeline_id != target_stage.pipeline_id:
        raise CrossPipelineMovementError(
            f"Cannot move deal to a stage in a different pipeline (from {current_stage.pipeline_id} to {target_stage.pipeline_id})."
        )

    deal.pipeline_stage_id = target_stage_id
    db.commit()
    db.refresh(deal)
    return deal


def update_deal_status(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
    new_status: str,
) -> Optional[Deal]:
    """Update deal status to open, won, or lost strictly scoped to tenant organization."""
    clean_status = new_status.strip().lower()
    if clean_status not in ALLOWED_DEAL_STATUSES:
        raise InvalidDealStatusError(
            f"Invalid status '{new_status}'. Allowed values: {sorted(list(ALLOWED_DEAL_STATUSES))}"
        )

    deal = get_deal(db, org_id, deal_id)
    if not deal:
        return None

    deal.status = clean_status
    db.commit()
    db.refresh(deal)
    return deal


def mark_deal_won(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
) -> Optional[Deal]:
    """Convenience function to mark a deal as won."""
    return update_deal_status(db, org_id, deal_id, "won")


def mark_deal_lost(
    db: Session,
    org_id: uuid.UUID,
    deal_id: uuid.UUID,
) -> Optional[Deal]:
    """Convenience function to mark a deal as lost."""
    return update_deal_status(db, org_id, deal_id, "lost")
