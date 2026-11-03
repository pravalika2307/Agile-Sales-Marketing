"""Campaign execution orchestration service (Step 8 & Step 9)."""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact, Company
from app.models.outreach import Outreach
from app.schemas.campaign_execution import (
    CampaignExecutionPreviewItem,
    CampaignExecutionPreviewResponse,
    CampaignExecutionResponse,
)
from app.schemas.outreach import OutreachCreate
from app.services.campaign_execution.rules import (
    NON_DUPLICATE_OUTREACH_STATUSES,
    EvaluationResult,
    evaluate_campaign_contact,
)
from app.services.campaign_steps.template_renderer import (
    find_unresolved_placeholders,
    render_template,
)
from app.services.outreach.service import create_outreach
from app.services.organization_config import get_organization_booking_url

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class CampaignExecutionError(Exception):
    """Base exception for campaign execution errors."""
    pass


class CampaignNotFoundError(CampaignExecutionError):
    """Raised when the specified campaign does not exist in the tenant organization."""
    pass


class InvalidCampaignExecutionStateError(CampaignExecutionError):
    """Raised when attempting execution on an inactive campaign."""
    pass


# ── Service Operations ────────────────────────────────────────────────────────

def preview_campaign_execution(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    sender_name: Optional[str] = None,
) -> CampaignExecutionPreviewResponse:
    """
    Evaluates eligible campaign contacts for outreach planning in a completely read-only preview dry-run.
    Renders Step 1 templates for preview without creating any database records or mutating any fields.
    """
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    campaign_contacts = (
        db.query(CampaignContact)
        .filter(CampaignContact.campaign_id == campaign.id)
        .order_by(CampaignContact.enrolled_at.asc())
        .all()
    )

    # Check for active Step 1 from visual workflow graph or legacy steps
    from app.services.workflow_service import get_campaign_ordered_steps
    ordered_steps = get_campaign_ordered_steps(db, campaign)
    step_1 = next((s for s in ordered_steps if s.step_number == 1 and s.is_active), None)

    eligible_ids: List[uuid.UUID] = []
    skipped_ids: List[uuid.UUID] = []
    rejected_ids: List[uuid.UUID] = []
    preview_items: List[CampaignExecutionPreviewItem] = []

    booking_url = get_organization_booking_url(db, org_id)

    for cc in campaign_contacts:
        contact = (
            db.query(Contact)
            .filter(Contact.id == cc.contact_id)
            .first()
        )
        existing_outreaches = (
            db.query(Outreach)
            .filter(Outreach.campaign_contact_id == cc.id)
            .all()
        )

        evaluation = evaluate_campaign_contact(campaign, cc, contact, existing_outreaches)

        if evaluation.result == EvaluationResult.SKIPPED:
            skipped_ids.append(cc.id)
        elif evaluation.result == EvaluationResult.REJECTED:
            rejected_ids.append(cc.id)
        elif evaluation.result == EvaluationResult.ELIGIBLE:
            if not step_1:
                # If no active Step 1 exists, contact cannot be executed
                skipped_ids.append(cc.id)
            else:
                step1_type = getattr(step_1, "step_type", "email") or "email"
                if step1_type == "sms":
                    if not (contact and contact.phone):
                        skipped_ids.append(cc.id)
                        continue
                    from app.services.sms.service import is_sms_suppressed
                    suppressed, _ = is_sms_suppressed(db, org_id, phone=contact.phone, contact=contact)
                    if suppressed:
                        skipped_ids.append(cc.id)
                        continue
                elif step1_type == "voice" and not (contact and contact.phone):
                    skipped_ids.append(cc.id)
                    continue
                elif step1_type == "physical_mail" and not (contact and (getattr(contact, "address_line_1", None) or getattr(contact, "postal_address_line1", None))):
                    skipped_ids.append(cc.id)
                    continue
                elif step1_type == "linkedin" and not (contact and (contact.first_name or contact.email)):
                    skipped_ids.append(cc.id)
                    continue
                elif step1_type == "email" and not (contact and contact.email):
                    skipped_ids.append(cc.id)
                    continue

                eligible_ids.append(cc.id)
                company = (
                    db.query(Company).filter(Company.id == contact.company_id).first()
                    if contact and contact.company_id
                    else None
                )

                if step1_type == "voice":
                    subject = step_1.subject_template or "AI Voice SDR Call"
                    body = step_1.body_template or "Outbound AI Voice SDR call via Retell."
                elif step1_type == "sms":
                    subject = None
                    body = render_template(
                        step_1.body_template,
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                        booking_link=booking_url,
                    )
                elif step1_type == "physical_mail":
                    subject = step_1.subject_template or "Poplar Direct Mail"
                    addr1 = getattr(contact, "address_line_1", None) or getattr(contact, "postal_address_line1", None) or "Address on file"
                    city = getattr(contact, "city", None) or getattr(contact, "postal_city", None) or ""
                    body = f"Physical mailing to {addr1}, {city}".strip()
                elif step1_type == "linkedin":
                    subject = step_1.subject_template or "LinkedIn Connection Request"
                    body = render_template(
                        step_1.body_template or "Hi {first_name}, noticed your leadership at {company}. We help streamline commercial billing and receivables with automated workflows. Would love to connect: {booking_link}",
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                        booking_link=booking_url or "https://cal.com/agilereceivables/30min",
                    )
                else:
                    subject = render_template(
                        step_1.subject_template,
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                    )
                    has_booking_ph = bool(
                        step_1.body_template
                        and any(
                            ph in step_1.body_template
                            for ph in ("{booking_link}", "{{booking_link}}", "{booking_url}", "{{booking_url}}")
                        )
                    )
                    body = render_template(
                        step_1.body_template,
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                        booking_link=booking_url,
                        enforce_booking_cta=bool(booking_url or has_booking_ph),
                    )

                preview_items.append(
                    CampaignExecutionPreviewItem(
                        campaign_contact_id=cc.id,
                        contact_id=cc.contact_id,
                        step_number=1,
                        subject=subject,
                        body=body,
                    )
                )

    return CampaignExecutionPreviewResponse(
        campaign_id=campaign.id,
        eligible_count=len(eligible_ids),
        eligible_campaign_contact_ids=eligible_ids,
        skipped_count=len(skipped_ids),
        skipped_campaign_contact_ids=skipped_ids,
        rejected_count=len(rejected_ids),
        rejected_campaign_contact_ids=rejected_ids,
        preview_items=preview_items,
    )


def execute_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    sender_name: Optional[str] = None,
) -> CampaignExecutionResponse:
    """
    Identifies eligible campaign contacts and creates initial draft Outreach records using rendered Step 1 templates.
    Transitions enrolled contacts from 'queued' to 'in_progress' and sets current_step = 1.
    Prevents duplicate creation and rejects inconsistent relationships.
    Does NOT send real or mock emails.
    """
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    if campaign.status != "active":
        raise InvalidCampaignExecutionStateError(
            f"Cannot execute campaign '{campaign_id}' with status '{campaign.status}'. Must be 'active'."
        )

    # Check for active Step 1 from visual workflow graph or legacy steps
    from app.services.workflow_service import get_campaign_ordered_steps
    ordered_steps = get_campaign_ordered_steps(db, campaign)
    step_1 = next((s for s in ordered_steps if s.step_number == 1 and s.is_active), None)

    campaign_contacts = (
        db.query(CampaignContact)
        .filter(CampaignContact.campaign_id == campaign.id)
        .order_by(CampaignContact.enrolled_at.asc())
        .all()
    )

    eligible_contacts: List[CampaignContact] = []
    skipped_ids: List[uuid.UUID] = []
    rejected_ids: List[uuid.UUID] = []

    for cc in campaign_contacts:
        contact = (
            db.query(Contact)
            .filter(Contact.id == cc.contact_id)
            .first()
        )
        existing_outreaches = (
            db.query(Outreach)
            .filter(Outreach.campaign_contact_id == cc.id)
            .all()
        )

        evaluation = evaluate_campaign_contact(campaign, cc, contact, existing_outreaches)

        if evaluation.result == EvaluationResult.SKIPPED:
            skipped_ids.append(cc.id)
        elif evaluation.result == EvaluationResult.REJECTED:
            rejected_ids.append(cc.id)
        elif evaluation.result == EvaluationResult.ELIGIBLE:
            if not step_1:
                # No active Step 1 found -> skip outreach creation
                skipped_ids.append(cc.id)
            else:
                step1_type = getattr(step_1, "step_type", "email") or "email"
                if step1_type in ("voice", "sms") and not (contact and contact.phone):
                    skipped_ids.append(cc.id)
                    continue
                elif step1_type == "physical_mail" and not (contact and (getattr(contact, "address_line_1", None) or getattr(contact, "postal_address_line1", None))):
                    skipped_ids.append(cc.id)
                    continue
                elif step1_type == "linkedin" and not (contact and (contact.first_name or contact.email)):
                    skipped_ids.append(cc.id)
                    continue
                elif step1_type == "email" and not (contact and contact.email):
                    skipped_ids.append(cc.id)
                    continue
                eligible_contacts.append(cc)

    created_outreach_ids: List[uuid.UUID] = []
    booking_url = get_organization_booking_url(db, org_id)

    for cc in eligible_contacts:
        try:
            with db.begin_nested():
                # Concurrency duplicate safety check
                existing = (
                    db.query(Outreach)
                    .filter(
                        Outreach.campaign_contact_id == cc.id,
                        Outreach.status.in_(NON_DUPLICATE_OUTREACH_STATUSES),
                    )
                    .first()
                )
                if existing:
                    skipped_ids.append(cc.id)
                    continue

                contact = (
                    db.query(Contact)
                    .filter(Contact.id == cc.contact_id)
                    .first()
                )
                company = (
                    db.query(Company).filter(Company.id == contact.company_id).first()
                    if contact and contact.company_id
                    else None
                )

                step1_type = getattr(step_1, "step_type", "email") or "email"

                if step1_type == "voice":
                    rendered_subject = step_1.subject_template or "AI Voice SDR Call"
                    rendered_body = step_1.body_template or "Outbound AI Voice SDR call via Retell."
                    outreach_recipient = contact.phone
                elif step1_type == "sms":
                    from app.services.sms.service import is_sms_suppressed
                    suppressed, suppression_reason = is_sms_suppressed(db, org_id, phone=contact.phone, contact=contact)
                    if suppressed:
                        logger.warning("Blocked SMS dispatch for contact %s: %s", contact.id, suppression_reason)
                        rejected_ids.append(cc.id)
                        continue
                    rendered_subject = None
                    rendered_body = render_template(
                        step_1.body_template,
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                        booking_link=booking_url,
                    )
                    outreach_recipient = contact.phone
                elif step1_type == "physical_mail":
                    rendered_subject = step_1.subject_template or "Poplar Direct Mail"
                    addr1 = getattr(contact, "address_line_1", None) or getattr(contact, "postal_address_line1", None) or "Address on file"
                    city = getattr(contact, "city", None) or getattr(contact, "postal_city", None) or ""
                    rendered_body = f"Physical mailing to {addr1}, {city}".strip()
                    outreach_recipient = addr1
                elif step1_type == "linkedin":
                    rendered_subject = step_1.subject_template or "LinkedIn Connection Request"
                    rendered_body = render_template(
                        step_1.body_template or "Hi {first_name}, noticed your leadership at {company}. We help streamline commercial billing and receivables with automated workflows. Would love to connect: {booking_link}",
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                        booking_link=booking_url or "https://cal.com/agilereceivables/30min",
                    )
                    outreach_recipient = getattr(contact, "linkedin_url", None) or contact.email or f"{contact.first_name} {contact.last_name}"
                else:
                    # Email Step
                    rendered_subject = render_template(
                        step_1.subject_template if step_1 else None,
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                    )
                    has_booking_ph = bool(
                        step_1
                        and step_1.body_template
                        and any(
                            ph in step_1.body_template
                            for ph in ("{booking_link}", "{{booking_link}}", "{booking_url}", "{{booking_url}}")
                        )
                    )
                    rendered_body = render_template(
                        step_1.body_template if step_1 else None,
                        contact=contact,
                        company=company,
                        sender_name=sender_name,
                        booking_link=booking_url,
                        enforce_booking_cta=bool(booking_url or has_booking_ph),
                    )
                    outreach_recipient = contact.email

                # Safety check: Unresolved placeholders block email/sms outreach dispatch
                if step1_type in ("email", "sms"):
                    unresolved_tokens = (find_unresolved_placeholders(rendered_subject) if rendered_subject else []) + (find_unresolved_placeholders(rendered_body) if rendered_body else [])
                    if unresolved_tokens:
                        logger.warning(
                            "Blocked dispatch for campaign contact %s due to unresolved placeholders: %s",
                            cc.id,
                            unresolved_tokens,
                        )
                        rejected_ids.append(cc.id)
                        continue

                outreach_payload = OutreachCreate(
                    campaign_id=campaign.id,
                    contact_id=cc.contact_id,
                    campaign_contact_id=cc.id,
                    channel=step1_type,
                    subject=rendered_subject,
                    body=rendered_body,
                    scheduled_at=None,
                )
                outreach = create_outreach(db, org_id, outreach_payload, commit=False)
                if outreach_recipient:
                    outreach.recipient = outreach_recipient
                cc.enrollment_status = "in_progress"
                cc.current_step = 1
                db.flush()

            db.commit()
            created_outreach_ids.append(outreach.id)
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to create outreach for campaign_contact %s: %s", cc.id, exc)
            rejected_ids.append(cc.id)

    return CampaignExecutionResponse(
        campaign_id=campaign.id,
        eligible_count=len(eligible_contacts),
        created_count=len(created_outreach_ids),
        skipped_count=len(skipped_ids),
        rejected_count=len(rejected_ids),
        created_outreach_ids=created_outreach_ids,
        skipped_campaign_contact_ids=skipped_ids,
        rejected_campaign_contact_ids=rejected_ids,
    )

