"""Campaign and Campaign Contact domain service managing tenant-scoped operations and lifecycle."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.campaign import (
    ALLOWED_CAMPAIGN_STATUSES,
    ALLOWED_CAMPAIGN_TYPES,
    ALLOWED_ENROLLMENT_STATUSES,
    Campaign,
    CampaignContact,
)
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact
from app.models.outreach import Outreach
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.schemas.workflow import KNOWN_TEMPLATE_VARIABLES
from app.services.campaign_steps.template_renderer import find_unresolved_placeholders

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class CampaignServiceError(Exception):
    """Base exception for campaign service errors."""
    pass


class CampaignNotFoundError(CampaignServiceError):
    """Raised when a campaign is not found in the tenant organization."""
    pass


class ContactNotFoundError(CampaignServiceError):
    """Raised when a contact is not found in the tenant organization."""
    pass


class InvalidCampaignTransitionError(CampaignServiceError):
    """Raised when an illegal campaign status transition is attempted."""
    pass


class ContactAlreadyEnrolledError(CampaignServiceError):
    """Raised when a contact is already enrolled in the campaign."""
    pass


class InvalidEnrollmentStatusError(CampaignServiceError):
    """Raised when an invalid enrollment status is specified."""
    pass


# ── Campaign CRUD Operations ──────────────────────────────────────────────────

def create_campaign(
    db: Session,
    org_id: uuid.UUID,
    data: CampaignCreate,
) -> Campaign:
    """Create a new campaign for the organization in 'draft' status."""
    campaign = Campaign(
        organization_id=org_id,
        name=data.name.strip(),
        type=data.type,
        status="draft",
        description=data.description.strip() if data.description else None,
        schedule_settings=data.schedule_settings,
        workflow_config=data.workflow_config,
    )
    db.add(campaign)
    db.flush()

    # Synchronize steps: if custom workflow email steps provided, create them; else create default Step 1
    has_custom_steps = False
    if data.workflow_config and isinstance(data.workflow_config, dict):
        wf_nodes = data.workflow_config.get("nodes", [])
        email_nodes = [n for n in wf_nodes if isinstance(n, dict) and n.get("type") == "email"]
        if email_nodes:
            has_custom_steps = True
            for step_num, node in enumerate(email_nodes, start=1):
                cfg = node.get("config", {}) or {}
                step = CampaignStep(
                    organization_id=org_id,
                    campaign_id=campaign.id,
                    step_number=step_num,
                    step_type="email",
                    delay_days=int(cfg.get("delay_days", 0) or 0),
                    delay_hours=int(cfg.get("delay_hours", 0) or 0),
                    is_active=bool(cfg.get("is_active", True)),
                    subject_template=cfg.get("subject") or cfg.get("subject_template"),
                    body_template=cfg.get("body") or cfg.get("body_template"),
                )
                db.add(step)

    if not has_custom_steps:
        default_step = CampaignStep(
            organization_id=org_id,
            campaign_id=campaign.id,
            step_number=1,
            step_type="email",
            delay_days=0,
            delay_hours=0,
            is_active=True,
            subject_template=None,
            body_template=None,
        )
        db.add(default_step)

    db.commit()
    db.refresh(campaign)
    return campaign


def get_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> Optional[Campaign]:
    """Retrieve a campaign strictly scoped to the tenant organization."""
    return (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )


def list_campaigns(
    db: Session,
    org_id: uuid.UUID,
    status: Optional[str] = None,
    campaign_type: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Campaign], int]:
    """
    List campaigns for an organization with optional filtering.
    Returns (campaigns, total_count).
    """
    query = db.query(Campaign).filter(Campaign.organization_id == org_id)

    if status and status.strip():
        query = query.filter(Campaign.status == status.strip().lower())

    if campaign_type and campaign_type.strip():
        query = query.filter(Campaign.type == campaign_type.strip().lower())

    if search and search.strip():
        query = query.filter(Campaign.name.ilike(f"%{search.strip()}%"))

    total = query.count()
    campaigns = (
        query.order_by(Campaign.created_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 100))
        .all()
    )
    return campaigns, total


def update_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    data: CampaignUpdate,
) -> Optional[Campaign]:
    """Partially update a campaign strictly scoped to the tenant organization."""
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if field == "name" and isinstance(val, str):
            val = val.strip()
        setattr(campaign, field, val)

    db.commit()
    db.refresh(campaign)
    return campaign


def delete_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> bool:
    """
    Safely delete a campaign strictly scoped to the tenant organization.
    Preserves shared CRM Contacts, Leads, and historical outreach/call audit records.
    Cancels pending draft/scheduled outreaches and prevents future sequence execution.
    """
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        return False

    # 1. Cancel pending draft/scheduled outreaches for this campaign
    db.query(Outreach).filter(
        Outreach.campaign_id == campaign.id,
        Outreach.status.in_(["draft", "scheduled"]),
    ).update({Outreach.status: "cancelled"}, synchronize_session=False)

    # 2. Preserve historical outreach records by dissociating campaign foreign keys before cascade
    db.query(Outreach).filter(
        Outreach.campaign_id == campaign.id,
    ).update(
        {Outreach.campaign_id: None, Outreach.campaign_contact_id: None},
        synchronize_session=False,
    )

    # 3. Delete campaign (safely cascades CampaignStep and CampaignContact join records)
    db.delete(campaign)
    db.commit()
    return True



# ── Campaign Lifecycle Operations ─────────────────────────────────────────────

def activate_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> Campaign:
    """
    Transition campaign status to 'active'.
    Valid source statuses: 'draft', 'paused'.
    """
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    if campaign.status not in ("draft", "paused"):
        raise InvalidCampaignTransitionError(
            f"Cannot activate campaign with status '{campaign.status}'. Must be 'draft' or 'paused'."
        )

    # Validate active step templates before activation
    for step in campaign.steps:
        if step.is_active:
            for text_val, field_name in [(step.subject_template, "subject"), (step.body_template, "body")]:
                if text_val:
                    unresolved = find_unresolved_placeholders(text_val)
                    for ph in unresolved:
                        clean_var = ph.strip("{}").strip().lower()
                        if clean_var not in KNOWN_TEMPLATE_VARIABLES:
                            raise InvalidCampaignTransitionError(
                                f"Cannot activate campaign '{campaign_id}': Step {step.step_number} contains invalid placeholder '{ph}' in {field_name}."
                            )

    campaign.status = "active"
    db.commit()
    db.refresh(campaign)
    return campaign


def pause_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> Campaign:
    """
    Transition campaign status to 'paused'.
    Valid source status: 'active'.
    """
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    if campaign.status != "active":
        raise InvalidCampaignTransitionError(
            f"Cannot pause campaign with status '{campaign.status}'. Must be 'active'."
        )

    campaign.status = "paused"
    db.commit()
    db.refresh(campaign)
    return campaign


def complete_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    force: bool = False,
) -> Campaign:
    """
    Transition campaign status to 'completed'.
    Valid source statuses: 'active', 'paused'.

    Completion Rule:
    A campaign cannot transition to 'completed' if:
    1. Any enrolled contact remains 'in_progress' (active sequence work is pending).
    2. Any generated outreach message for the campaign remains in 'draft' status.

    If 'force=True' is explicitly passed (e.g. administrative closure/cancellation),
    the transition is permitted without automatically sending or scheduling messages.
    """
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    if campaign.status not in ("active", "paused"):
        raise InvalidCampaignTransitionError(
            f"Cannot complete campaign with status '{campaign.status}'. Must be 'active' or 'paused'."
        )

    if not force:
        # Check for in-progress contact enrollments
        in_progress_count = (
            db.query(CampaignContact)
            .filter(
                CampaignContact.campaign_id == campaign_id,
                CampaignContact.enrollment_status == "in_progress",
            )
            .count()
        )
        if in_progress_count > 0:
            raise InvalidCampaignTransitionError(
                f"Cannot complete campaign '{campaign_id}': {in_progress_count} enrolled contact(s) "
                f"remain in-progress. Active sequence steps must be completed or skipped first."
            )

        # Check for draft outreach records awaiting review/delivery
        draft_outreach_count = (
            db.query(Outreach)
            .filter(
                Outreach.campaign_id == campaign_id,
                Outreach.organization_id == org_id,
                Outreach.status == "draft",
            )
            .count()
        )
        if draft_outreach_count > 0:
            raise InvalidCampaignTransitionError(
                f"Cannot complete campaign '{campaign_id}': {draft_outreach_count} generated outreach message(s) "
                f"remain in draft. Outreach must be sent, cancelled, or force-completed."
            )

    campaign.status = "completed"
    db.commit()
    db.refresh(campaign)
    return campaign


# ── Contact Enrollment Operations ─────────────────────────────────────────────

def _verify_tenant_contact(
    db: Session,
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> Contact:
    """Verify contact exists and belongs to the tenant organization."""
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.organization_id == org_id)
        .first()
    )
    if not contact:
        raise ContactNotFoundError(f"Contact '{contact_id}' not found in current organization.")
    return contact


def enroll_contact(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    enrollment_status: str = "queued",
) -> CampaignContact:
    """Enroll a contact into a campaign. Both must belong to the tenant organization."""
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    _verify_tenant_contact(db, org_id, contact_id)

    # Check for existing enrollment
    existing = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id == contact_id,
        )
        .first()
    )
    if existing:
        raise ContactAlreadyEnrolledError(
            f"Contact '{contact_id}' is already enrolled in campaign '{campaign_id}'."
        )

    clean_status = enrollment_status.strip().lower()
    if clean_status not in ALLOWED_ENROLLMENT_STATUSES:
        clean_status = "queued"

    enrollment = CampaignContact(
        campaign_id=campaign_id,
        contact_id=contact_id,
        enrollment_status=clean_status,
        current_step=0,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def bulk_enroll_contacts(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    contact_ids: List[uuid.UUID],
) -> Dict[str, List[uuid.UUID]]:
    """
    Safely bulk enroll contacts into a campaign.
    Returns categorized result dictionary:
    { "enrolled": [...], "already_enrolled": [...], "rejected": [...] }
    """
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    if not contact_ids:
        return {"enrolled": [], "already_enrolled": [], "rejected": []}

    # Query tenant contacts among the requested IDs
    valid_contacts = (
        db.query(Contact.id)
        .filter(Contact.organization_id == org_id, Contact.id.in_(contact_ids))
        .all()
    )
    valid_contact_set = {c[0] for c in valid_contacts}

    # Query existing enrollments for this campaign
    existing_enrollments = (
        db.query(CampaignContact.contact_id)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id.in_(contact_ids),
        )
        .all()
    )
    existing_enrolled_set = {e[0] for e in existing_enrollments}

    enrolled: List[uuid.UUID] = []
    already_enrolled: List[uuid.UUID] = []
    rejected: List[uuid.UUID] = []
    new_enrollments: List[CampaignContact] = []

    # Maintain seen set to prevent internal batch duplicates
    seen_in_batch: set[uuid.UUID] = set()

    for cid in contact_ids:
        if cid in seen_in_batch:
            continue
        seen_in_batch.add(cid)

        if cid not in valid_contact_set:
            rejected.append(cid)
        elif cid in existing_enrolled_set:
            already_enrolled.append(cid)
        else:
            enrollment = CampaignContact(
                campaign_id=campaign_id,
                contact_id=cid,
                enrollment_status="queued",
                current_step=0,
            )
            new_enrollments.append(enrollment)
            enrolled.append(cid)

    if new_enrollments:
        db.add_all(new_enrollments)
        db.commit()

    return {
        "enrolled": enrolled,
        "already_enrolled": already_enrolled,
        "rejected": rejected,
    }


def list_enrolled_contacts(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[CampaignContact], int]:
    """List enrolled contacts for a campaign scoped to the tenant organization."""
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    query = (
        db.query(CampaignContact)
        .options(
            joinedload(CampaignContact.contact).joinedload(Contact.company)
        )
        .filter(CampaignContact.campaign_id == campaign_id)
    )
    total = query.count()
    enrollments = (
        query.order_by(CampaignContact.enrolled_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 100))
        .all()
    )
    return enrollments, total


def remove_enrollment(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> bool:
    """
    Safely remove a contact's enrollment from a specific campaign.
    Preserves CRM Contact globally, Leads, and historical outreach records.
    Cancels pending draft/scheduled outreaches for this enrollment so future steps cannot execute.
    """
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    _verify_tenant_contact(db, org_id, contact_id)

    enrollment = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id == contact_id,
        )
        .first()
    )
    if not enrollment:
        return False

    # 1. Cancel pending draft/scheduled outreaches for this specific contact in this campaign
    db.query(Outreach).filter(
        Outreach.campaign_contact_id == enrollment.id,
        Outreach.status.in_(["draft", "scheduled"]),
    ).update({Outreach.status: "cancelled"}, synchronize_session=False)

    # 2. Preserve historical outreach records by dissociating campaign_contact_id before deletion
    db.query(Outreach).filter(
        Outreach.campaign_contact_id == enrollment.id,
    ).update({Outreach.campaign_contact_id: None}, synchronize_session=False)

    # 3. Delete the enrollment record
    db.delete(enrollment)
    db.commit()
    return True



def update_enrollment_status(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    contact_id: uuid.UUID,
    new_status: str,
) -> Optional[CampaignContact]:
    """Update enrollment status of an enrolled contact."""
    campaign = get_campaign(db, org_id, campaign_id)
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    clean_status = new_status.strip().lower()
    if clean_status not in ALLOWED_ENROLLMENT_STATUSES:
        raise InvalidEnrollmentStatusError(
            f"Invalid enrollment status '{new_status}'. Allowed values: {sorted(list(ALLOWED_ENROLLMENT_STATUSES))}"
        )

    enrollment = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id == contact_id,
        )
        .first()
    )
    if not enrollment:
        return None

    enrollment.enrollment_status = clean_status
    db.commit()
    db.refresh(enrollment)
    return enrollment
