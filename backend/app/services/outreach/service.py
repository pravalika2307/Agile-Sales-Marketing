"""Outreach domain service handling creation, lifecycle transitions, event auditing, and provider delivery."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.contact_list import ContactList, ContactListMember
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.schemas.outreach import OutreachCreate, OutreachUpdate
from app.services.campaign_steps.template_renderer import (
    find_unresolved_placeholders,
    render_email_html,
    render_template,
)
from app.services.organization_config import (
    MissingBookingUrlError,
    get_organization_booking_url,
)
from app.services.outreach.base import (
    EmailMessage,
    EmailProvider,
    MockEmailProvider,
)
from app.services.outreach.providers import get_email_provider

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class OutreachServiceError(Exception):
    """Base exception for outreach service operations."""
    pass


class SuppressedRecipientError(OutreachServiceError):
    """Raised when recipient contact has opted out, is suppressed, or suppression state cannot be verified."""
    pass


class UnresolvedTemplatePlaceholderError(OutreachServiceError):
    """Raised when outreach content contains unresolved template placeholders before delivery."""
    pass


class OutreachNotFoundError(OutreachServiceError):
    """Raised when outreach record is not found in the tenant organization."""
    pass


class CampaignNotFoundError(OutreachServiceError):
    """Raised when referenced campaign does not exist in the tenant organization."""
    pass


class ContactNotFoundError(OutreachServiceError):
    """Raised when referenced contact does not exist in the tenant organization."""
    pass


class CampaignContactNotFoundError(OutreachServiceError):
    """Raised when referenced campaign enrollment does not exist in the tenant organization."""
    pass


class InconsistentEnrollmentError(OutreachServiceError):
    """Raised when campaign_contact does not match the provided campaign or contact."""
    pass


class AmbiguousReplyAssociationError(OutreachServiceError):
    """Raised when an inbound email reply cannot be unambiguously associated with a single tenant or outreach."""
    pass


class CampaignCompletedError(OutreachServiceError):
    """Raised when attempting outreach execution on a completed campaign."""
    pass


class InvalidOutreachTransitionError(OutreachServiceError):
    """Raised when an illegal outreach status transition is attempted."""
    pass


class AlreadySentError(InvalidOutreachTransitionError):
    """Raised when attempting to send an outreach that has already been sent."""
    pass


class CurrentlySendingError(InvalidOutreachTransitionError):
    """Raised when attempting to send an outreach that is currently in 'sending' status."""
    pass


class CancelledOutreachError(InvalidOutreachTransitionError):
    """Raised when attempting to send a cancelled outreach."""
    pass


class InvalidRecipientEmailError(OutreachServiceError):
    """Raised when recipient contact has an invalid or missing email address."""
    pass


class EmptyOutreachBodyError(OutreachServiceError):
    """Raised when outreach body is missing or empty before sending."""
    pass


class UnsupportedChannelError(OutreachServiceError):
    """Raised when outreach channel is not supported for delivery."""
    pass


class ProviderDeliveryError(OutreachServiceError):
    """Raised when external email provider delivery fails."""
    pass


# ── Outreach Operations ───────────────────────────────────────────────────────

def create_outreach(
    db: Session,
    org_id: uuid.UUID,
    data: OutreachCreate,
    commit: bool = True,
) -> Outreach:
    """
    Create a new outreach interaction in 'draft' status with an initial 'created' audit event.
    Strictly verifies campaign, contact, and enrollment tenant ownership and internal consistency.
    """
    # 1. Verify Campaign belongs to tenant
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == data.campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{data.campaign_id}' not found.")

    # 2. Verify Contact belongs to tenant
    contact = (
        db.query(Contact)
        .filter(Contact.id == data.contact_id, Contact.organization_id == org_id)
        .first()
    )
    if not contact:
        raise ContactNotFoundError(f"Contact '{data.contact_id}' not found.")

    # 3. Verify or resolve CampaignContact enrollment
    if data.campaign_contact_id:
        campaign_contact = (
            db.query(CampaignContact)
            .filter(
                CampaignContact.id == data.campaign_contact_id,
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.contact_id == contact.id,
            )
            .first()
        )
        if not campaign_contact:
            raise CampaignContactNotFoundError(
                f"CampaignContact '{data.campaign_contact_id}' not found or does not link contact '{data.contact_id}' to campaign '{data.campaign_id}'."
            )
    else:
        campaign_contact = (
            db.query(CampaignContact)
            .filter(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.contact_id == contact.id,
            )
            .first()
        )
        if not campaign_contact:
            campaign_contact = CampaignContact(
                campaign_id=campaign.id,
                contact_id=contact.id,
                enrollment_status="queued",
            )
            db.add(campaign_contact)
            db.flush()

    # 4. Create Outreach in draft status
    outreach = Outreach(
        organization_id=org_id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=campaign_contact.id,
        recipient=contact.email if contact else None,
        channel=data.channel,
        status="draft",
        subject=data.subject.strip() if data.subject else None,
        body=data.body,
        scheduled_at=data.scheduled_at,
    )
    db.add(outreach)
    db.flush()

    # 5. Record initial 'created' audit event
    created_event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="created",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(created_event)

    if commit:
        db.commit()
        db.refresh(outreach)
    return outreach


def get_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
) -> Optional[Outreach]:
    """Retrieve an outreach record strictly scoped to the tenant organization."""
    return (
        db.query(Outreach)
        .filter(Outreach.id == outreach_id, Outreach.organization_id == org_id)
        .first()
    )


def list_outreach(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: Optional[uuid.UUID] = None,
    contact_id: Optional[uuid.UUID] = None,
    lead_id: Optional[uuid.UUID] = None,
    list_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Outreach], int]:
    """List outreach records belonging to the tenant organization with optional filtering."""
    query = db.query(Outreach).filter(Outreach.organization_id == org_id)

    if campaign_id:
        query = query.filter(Outreach.campaign_id == campaign_id)

    if contact_id:
        query = query.filter(Outreach.contact_id == contact_id)

    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.organization_id == org_id).first()
        if not lead:
            return [], 0
        lead_conditions = []
        if lead.contact_id:
            lead_conditions.append(Outreach.contact_id == lead.contact_id)
        if lead.email:
            lead_conditions.append(Outreach.recipient == lead.email)
        call_ids = [
            r[0]
            for r in db.query(CallRecord.id)
            .filter(CallRecord.lead_id == lead.id, CallRecord.organization_id == org_id)
            .all()
        ]
        if call_ids:
            lead_conditions.append(Outreach.call_record_id.in_(call_ids))
        if lead_conditions:
            query = query.filter(or_(*lead_conditions))
        else:
            return [], 0

    if list_id:
        cl = db.query(ContactList).filter(ContactList.id == list_id, ContactList.organization_id == org_id).first()
        if not cl:
            return [], 0
        members = db.query(ContactListMember).filter(ContactListMember.contact_list_id == list_id).all()
        member_contact_ids = [m.contact_id for m in members if m.contact_id]
        member_lead_ids = [m.lead_id for m in members if m.lead_id]
        lead_emails = []
        if member_lead_ids:
            lead_emails = [
                row[0]
                for row in db.query(Lead.email)
                .filter(Lead.id.in_(member_lead_ids), Lead.organization_id == org_id, Lead.email.isnot(None))
                .all()
            ]
        list_conditions = []
        if member_contact_ids:
            list_conditions.append(Outreach.contact_id.in_(member_contact_ids))
        if lead_emails:
            list_conditions.append(Outreach.recipient.in_(lead_emails))
        if list_conditions:
            query = query.filter(or_(*list_conditions))
        else:
            return [], 0

    if status and status.strip():
        query = query.filter(Outreach.status == status.strip().lower())

    if channel and channel.strip():
        query = query.filter(Outreach.channel == channel.strip().lower())

    total = query.count()
    outreaches = (
        query.order_by(Outreach.created_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 100))
        .all()
    )
    return outreaches, total


def update_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    data: OutreachUpdate,
) -> Optional[Outreach]:
    """Partially update editable fields of an outreach record."""
    outreach = get_outreach(db, org_id, outreach_id)
    if not outreach:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if field == "subject" and isinstance(val, str):
            val = val.strip()
        setattr(outreach, field, val)

    db.commit()
    db.refresh(outreach)
    return outreach


def schedule_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    scheduled_at: Optional[datetime] = None,
) -> Outreach:
    """
    Transition outreach to 'scheduled'.
    Allowed from: 'draft', 'failed'.
    """
    outreach = get_outreach(db, org_id, outreach_id)
    if not outreach:
        raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")

    if outreach.status not in ("draft", "failed"):
        raise InvalidOutreachTransitionError(
            f"Cannot schedule outreach in status '{outreach.status}'. Must be 'draft' or 'failed'."
        )

    outreach.status = "scheduled"
    if scheduled_at:
        outreach.scheduled_at = scheduled_at

    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="scheduled",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)

    db.commit()
    db.refresh(outreach)
    return outreach


def send_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    provider: Optional[EmailProvider] = None,
    raise_on_failure: bool = False,
) -> Outreach:
    """
    Execute explicit synchronous delivery for an outreach message.
    Allowed initial status: 'draft' (also supports 'scheduled' for lifecycle compatibility).
    Protects against duplicate sends, concurrent executions, and cross-tenant data.
    """
    # 1. Row locking where supported (PostgreSQL)
    query = db.query(Outreach).filter(
        Outreach.id == outreach_id,
        Outreach.organization_id == org_id,
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    outreach = query.first()
    if not outreach:
        raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")

    # 2. Strict tenant and relationship verification
    if not outreach.campaign or outreach.campaign.organization_id != org_id:
        raise CampaignNotFoundError("Referenced campaign not found or belongs to another tenant.")

    if not outreach.contact or outreach.contact.organization_id != org_id:
        raise ContactNotFoundError("Referenced contact not found or belongs to another tenant.")

    if (
        not outreach.campaign_contact
        or outreach.campaign_contact.campaign_id != outreach.campaign_id
        or outreach.campaign_contact.contact_id != outreach.contact_id
    ):
        raise InconsistentEnrollmentError("Inconsistent campaign contact enrollment.")

    if outreach.campaign.status == "completed":
        raise CampaignCompletedError("Cannot execute outreach for a completed campaign.")

    # 3. Channel verification
    if outreach.channel == "sms":
        from app.services.sms.service import send_sms_outreach
        return send_sms_outreach(
            db=db,
            org_id=org_id,
            outreach_id=outreach_id,
            raise_on_failure=raise_on_failure,
        )
    elif outreach.channel != "email":
        raise UnsupportedChannelError(
            f"Cannot send outreach with channel '{outreach.channel}'. Only 'email' and 'sms' are supported."
        )

    # 4. Idempotency & duplicate send protection
    if outreach.status == "sent":
        raise AlreadySentError("Outreach has already been sent.")
    if outreach.status == "sending":
        raise CurrentlySendingError("Outreach is currently in the process of sending.")
    if outreach.status == "cancelled":
        raise CancelledOutreachError("Cannot send a cancelled outreach.")
    if outreach.status == "failed":
        raise InvalidOutreachTransitionError("Cannot directly send failed outreach. Use retry.")
    if outreach.status not in ("draft", "scheduled"):
        raise InvalidOutreachTransitionError(
            f"Cannot send outreach in status '{outreach.status}'. Allowed initial status is 'draft'."
        )

    # 4.5 Authoritative Recipient Opt-Out & Suppression Guard (Fail-closed)
    contact = outreach.contact
    if not contact:
        raise ContactNotFoundError("Referenced contact record is missing. Failing closed.")

    is_suppressed = False
    suppression_reason = ""

    # Primary check: contact lead_status
    if contact.lead_status in ("opted_out", "unsubscribed"):
        is_suppressed = True
        suppression_reason = f"Contact lead_status is '{contact.lead_status}'"

    # Secondary check: associated Lead record in this tenant
    if not is_suppressed and contact.email:
        from app.models.lead import Lead
        matching_lead = (
            db.query(Lead)
            .filter(
                Lead.organization_id == org_id,
                Lead.email == contact.email,
            )
            .first()
        )
        if matching_lead and matching_lead.status in ("opted_out", "rejected"):
            is_suppressed = True
            suppression_reason = f"Associated lead status is '{matching_lead.status}'"

    if is_suppressed:
        logger.warning(
            "Blocked outreach %s delivery due to recipient suppression: %s (contact_id=%s)",
            outreach.id,
            suppression_reason,
            contact.id,
        )
        outreach.status = "cancelled"
        cancel_event = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="cancelled",
            event_metadata={"reason": f"Recipient suppressed/opted-out: {suppression_reason}"},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(cancel_event)
        db.commit()
        db.refresh(outreach)
        raise SuppressedRecipientError(
            f"Cannot send outreach: recipient is opted out or suppressed ({suppression_reason})."
        )

    # 5. Required email & content validation
    recipient_email = (outreach.contact.email or "").strip()
    if not recipient_email or "@" not in recipient_email:
        raise InvalidRecipientEmailError("Contact has no valid non-empty email address.")

    if not outreach.body or not outreach.body.strip():
        raise EmptyOutreachBodyError("Outreach body must be present before sending.")

    # 5.5 Ensure template rendering and final validation guard (Requirement 4 & 6)
    contact = outreach.contact
    company = None
    if contact:
        company = contact.company if getattr(contact, "company", None) else (
            db.query(Company).filter(Company.id == contact.company_id).first()
            if contact.company_id else None
        )

    booking_url = get_organization_booking_url(db, org_id)

    if outreach.subject:
        outreach.subject = render_template(outreach.subject, contact=contact, company=company)
    if outreach.body:
        if booking_url:
            outreach.body = render_template(
                outreach.body,
                contact=contact,
                company=company,
                booking_link=booking_url,
                enforce_booking_cta=True,
            )
        else:
            has_booking_placeholder = any(
                ph in outreach.body
                for ph in ("{booking_link}", "{{booking_link}}", "{booking_url}", "{{booking_url}}")
            )
            outreach.body = render_template(
                outreach.body,
                contact=contact,
                company=company,
                booking_link=None,
                enforce_booking_cta=has_booking_placeholder,
            )

    unresolved_subject = find_unresolved_placeholders(outreach.subject)
    unresolved_body = find_unresolved_placeholders(outreach.body)
    all_unresolved = list(dict.fromkeys(unresolved_subject + unresolved_body))

    if all_unresolved:
        non_booking_unresolved = [
            p for p in all_unresolved
            if p not in ("{booking_link}", "{{booking_link}}", "{booking_url}", "{{booking_url}}")
        ]
        if non_booking_unresolved:
            error_msg = (
                f"Cannot send outreach: content contains unresolved template placeholder(s): "
                f"{', '.join(all_unresolved)}. Missing required contact or company details."
            )
            logger.warning(
                "Blocked outreach %s sending due to unresolved placeholders: %s",
                outreach.id,
                all_unresolved,
            )
            raise UnresolvedTemplatePlaceholderError(error_msg)

        if "{booking_link}" in all_unresolved or "{{booking_link}}" in all_unresolved or "{booking_url}" in all_unresolved:
            org_label = str(getattr(outreach.campaign.organization if outreach.campaign else None, "name", None) or org_id)
            error_msg = (
                f"Cannot send outreach: organization '{org_label}' has no configured meeting-booking URL. "
                f"Every campaign email requires a valid booking destination (canonical variable {{booking_link}})."
            )
            logger.warning("Blocked outreach %s sending: %s", outreach.id, error_msg)
            raise MissingBookingUrlError(error_msg)

    # 6. Safe transition to 'sending' and persist before external provider call
    outreach.status = "sending"
    sending_event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="sending",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(sending_event)
    db.commit()

    # 7. Invoke provider
    active_provider = provider or get_email_provider()
    html_body = render_email_html(outreach.body.strip(), booking_url=booking_url)
    message = EmailMessage(
        to_email=recipient_email,
        subject=outreach.subject or "(No Subject)",
        body=outreach.body.strip(),
        metadata={
            "outreach_id": str(outreach.id),
            "campaign_id": str(outreach.campaign_id),
            "html_body": html_body,
        },
    )
    result = active_provider.send(message)

    # 8. Transition to 'sent' or 'failed' based on provider result
    if result.success:
        outreach.status = "sent"
        outreach.provider = result.provider
        outreach.provider_message_id = result.provider_message_id
        if not outreach.recipient and recipient_email:
            outreach.recipient = recipient_email
        outreach.sent_at = datetime.now(timezone.utc)

        sent_event = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="sent",
            event_metadata={"provider_message_id": result.provider_message_id},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(sent_event)
    else:
        outreach.status = "failed"
        outreach.provider = result.provider
        outreach.provider_message_id = None

        failed_event = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="failed",
            event_metadata={"error": result.error_message},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(failed_event)

    db.commit()
    db.refresh(outreach)

    if not result.success and raise_on_failure:
        raise ProviderDeliveryError(f"Email delivery failed: {result.error_message}")

    return outreach



def cancel_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
) -> Outreach:
    """
    Transition outreach to 'cancelled'.
    Allowed from: 'draft', 'scheduled'.
    """
    outreach = get_outreach(db, org_id, outreach_id)
    if not outreach:
        raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")

    if outreach.status not in ("draft", "scheduled"):
        raise InvalidOutreachTransitionError(
            f"Cannot cancel outreach in status '{outreach.status}'. Must be 'draft' or 'scheduled'."
        )

    outreach.status = "cancelled"
    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="cancelled",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)

    db.commit()
    db.refresh(outreach)
    return outreach


def list_outreach_events(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
) -> List[OutreachEvent]:
    """List audit events for an outreach item scoped to the tenant organization."""
    outreach = get_outreach(db, org_id, outreach_id)
    if not outreach:
        raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")

    return (
        db.query(OutreachEvent)
        .filter(OutreachEvent.outreach_id == outreach_id, OutreachEvent.organization_id == org_id)
        .order_by(OutreachEvent.occurred_at.asc(), OutreachEvent.created_at.asc())
        .all()
    )


def retry_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    provider: Optional[EmailProvider] = None,
    raise_on_failure: bool = False,
) -> Outreach:
    """
    Retry delivery for a failed outreach message.
    Resets status from 'failed' to 'draft' and executes send_outreach() with all suppression and tenant guards.
    """
    outreach = get_outreach(db, org_id, outreach_id)
    if not outreach:
        raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")
    if outreach.status != "failed":
        raise InvalidOutreachTransitionError(
            f"Cannot retry outreach in status '{outreach.status}'. Allowed status to retry is 'failed'."
        )
    outreach.status = "draft"
    db.commit()
    return send_outreach(db, org_id, outreach_id, provider=provider, raise_on_failure=raise_on_failure)

