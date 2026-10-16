"""Provider-independent outreach tracking and response event service."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.campaign import CampaignContact
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import User
from app.services.outreach.service import (
    AmbiguousReplyAssociationError,
    OutreachNotFoundError,
    OutreachServiceError,
)

logger = logging.getLogger(__name__)


class InvalidTrackingStateError(OutreachServiceError):
    """Raised when an outreach item is in an invalid state for recording tracking events."""
    pass


def _resolve_and_validate_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
) -> Outreach:
    """
    Resolve outreach within the authenticated organization and validate delivery state.
    Tracking events are only accepted for outreach in 'sent' status.
    """
    outreach = (
        db.query(Outreach)
        .filter(Outreach.id == outreach_id, Outreach.organization_id == org_id)
        .first()
    )
    if not outreach:
        raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")

    if outreach.status != "sent":
        raise InvalidTrackingStateError(
            f"Cannot record tracking events for outreach with status '{outreach.status}'. Must be 'sent'."
        )

    return outreach


def _find_duplicate_event(
    db: Session,
    outreach_id: uuid.UUID,
    event_type: str,
    new_metadata: Optional[Dict[str, Any]],
) -> Optional[OutreachEvent]:
    """
    Check if an OutreachEvent of the same type with matching provider event identifier
    has already been recorded for this outreach. Prevents duplicate event inserts on webhook retries.
    """
    existing_events = (
        db.query(OutreachEvent)
        .filter(
            OutreachEvent.outreach_id == outreach_id,
            OutreachEvent.event_type == event_type,
        )
        .all()
    )
    if not existing_events:
        return None

    if not new_metadata:
        return None

    new_sns_id = new_metadata.get("sns_message_id")
    new_provider_id = (
        new_metadata.get("provider_event_id")
        or new_metadata.get("provider_message_id")
        or new_metadata.get("ses_event", {}).get("mail", {}).get("messageId")
    )

    for evt in existing_events:
        meta = evt.event_metadata or {}
        # 1. Match by SNS message ID
        if new_sns_id and meta.get("sns_message_id") == new_sns_id:
            return evt

        # 2. Match by Provider Event / Message ID
        exist_provider_id = (
            meta.get("provider_event_id")
            or meta.get("provider_message_id")
            or meta.get("ses_event", {}).get("mail", {}).get("messageId")
        )
        if new_provider_id and exist_provider_id == new_provider_id:
            if event_type in ("delivered", "bounced", "replied"):
                return evt
            # For open and click, also compare timestamp if present
            new_ses_timestamp = (
                new_metadata.get("ses_event", {}).get("open", {}).get("timestamp")
                or new_metadata.get("ses_event", {}).get("click", {}).get("timestamp")
            )
            exist_ses_timestamp = (
                meta.get("ses_event", {}).get("open", {}).get("timestamp")
                or meta.get("ses_event", {}).get("click", {}).get("timestamp")
            )
            if new_ses_timestamp and exist_ses_timestamp == new_ses_timestamp:
                return evt

        # 3. For inbound replies without provider message IDs: match sender and snippet
        if event_type == "replied":
            if (
                new_metadata.get("from_email")
                and meta.get("from_email") == new_metadata.get("from_email")
                and (
                    new_metadata.get("snippet") == meta.get("snippet")
                    or new_metadata.get("body") == meta.get("body")
                )
            ):
                return evt

    return None


def record_delivered(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    event_metadata: Optional[Dict[str, Any]] = None,
) -> OutreachEvent:
    """Record a delivered event. Idempotently sets first_delivered_at without mutating status."""
    outreach = _resolve_and_validate_outreach(db, org_id, outreach_id)

    # Check for duplicate delivery event
    dup = _find_duplicate_event(db, outreach.id, "delivered", event_metadata)
    if dup:
        logger.debug("Duplicate delivered event ignored for outreach %s", outreach.id)
        return dup

    now = datetime.now(timezone.utc)
    if outreach.first_delivered_at is None:
        outreach.first_delivered_at = now

    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="delivered",
        event_metadata=event_metadata,
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_opened(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    event_metadata: Optional[Dict[str, Any]] = None,
) -> OutreachEvent:
    """Record an opened event. Idempotently sets first_opened_at without mutating status."""
    outreach = _resolve_and_validate_outreach(db, org_id, outreach_id)

    # Check for duplicate opened event
    dup = _find_duplicate_event(db, outreach.id, "opened", event_metadata)
    if dup:
        logger.debug("Duplicate opened event ignored for outreach %s", outreach.id)
        return dup

    now = datetime.now(timezone.utc)
    if outreach.first_opened_at is None:
        outreach.first_opened_at = now

    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="opened",
        event_metadata=event_metadata,
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_clicked(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    event_metadata: Optional[Dict[str, Any]] = None,
) -> OutreachEvent:
    """Record a clicked event. Idempotently sets first_clicked_at without mutating status."""
    outreach = _resolve_and_validate_outreach(db, org_id, outreach_id)

    # Check for duplicate clicked event
    dup = _find_duplicate_event(db, outreach.id, "clicked", event_metadata)
    if dup:
        logger.debug("Duplicate clicked event ignored for outreach %s", outreach.id)
        return dup

    now = datetime.now(timezone.utc)
    if outreach.first_clicked_at is None:
        outreach.first_clicked_at = now

    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="clicked",
        event_metadata=event_metadata,
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_replied(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    event_metadata: Optional[Dict[str, Any]] = None,
) -> OutreachEvent:
    """
    Record a replied event.
    Idempotently sets first_replied_at.
    Updates contact lead_status to 'replied' unless contact is 'opted_out'.
    """
    outreach = _resolve_and_validate_outreach(db, org_id, outreach_id)

    # Check for duplicate replied event
    dup = _find_duplicate_event(db, outreach.id, "replied", event_metadata)
    if dup:
        logger.debug("Duplicate replied event ignored for outreach %s", outreach.id)
        return dup

    now = datetime.now(timezone.utc)
    if outreach.first_replied_at is None:
        outreach.first_replied_at = now

    # Update associated contact lead_status if not opted_out
    if outreach.contact_id:
        contact = (
            db.query(Contact)
            .filter(Contact.id == outreach.contact_id, Contact.organization_id == org_id)
            .first()
        )
        if contact and contact.lead_status != "opted_out":
            contact.lead_status = "replied"

    # Stop future campaign steps for this prospect enrollment
    if outreach.campaign_contact_id:
        cc = (
            db.query(CampaignContact)
            .filter(CampaignContact.id == outreach.campaign_contact_id)
            .first()
        )
        if cc and cc.enrollment_status != "replied":
            cc.enrollment_status = "replied"
            # Cancel any pending draft or scheduled outreaches for this enrollment
            pending_outreaches = (
                db.query(Outreach)
                .filter(
                    Outreach.campaign_contact_id == cc.id,
                    Outreach.id != outreach.id,
                    Outreach.status.in_(["draft", "scheduled"]),
                )
                .all()
            )
            for pending in pending_outreaches:
                pending.status = "cancelled"
                cancel_event = OutreachEvent(
                    organization_id=org_id,
                    outreach_id=pending.id,
                    event_type="cancelled",
                    event_metadata={"reason": "Prospect replied to campaign outreach"},
                    occurred_at=now,
                )
                db.add(cancel_event)

    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="replied",
        event_metadata=event_metadata,
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_bounced(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    event_metadata: Optional[Dict[str, Any]] = None,
) -> OutreachEvent:
    """
    Record a bounced event.
    Idempotently sets first_bounced_at.
    Halts CampaignContact cadence and cancels pending steps without deleting Contact or modifying Deal status.
    """
    outreach = _resolve_and_validate_outreach(db, org_id, outreach_id)

    # Check for duplicate bounced event
    dup = _find_duplicate_event(db, outreach.id, "bounced", event_metadata)
    if dup:
        logger.debug("Duplicate bounced event ignored for outreach %s", outreach.id)
        return dup

    now = datetime.now(timezone.utc)
    if outreach.first_bounced_at is None:
        outreach.first_bounced_at = now

    # Stop future campaign steps for this bounced prospect enrollment
    if outreach.campaign_contact_id:
        cc = (
            db.query(CampaignContact)
            .filter(CampaignContact.id == outreach.campaign_contact_id)
            .first()
        )
        if cc and cc.enrollment_status != "bounced":
            cc.enrollment_status = "bounced"
            pending_outreaches = (
                db.query(Outreach)
                .filter(
                    Outreach.campaign_contact_id == cc.id,
                    Outreach.id != outreach.id,
                    Outreach.status.in_(["draft", "scheduled"]),
                )
                .all()
            )
            for pending in pending_outreaches:
                pending.status = "cancelled"
                cancel_event = OutreachEvent(
                    organization_id=org_id,
                    outreach_id=pending.id,
                    event_type="cancelled",
                    event_metadata={"reason": "Outreach delivery bounced"},
                    occurred_at=now,
                )
                db.add(cancel_event)

    event = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="bounced",
        event_metadata=event_metadata,
        occurred_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def associate_inbound_reply(
    db: Session,
    from_email: str,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    provider_message_id: Optional[str] = None,
    org_id: Optional[uuid.UUID] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
) -> Tuple[Outreach, OutreachEvent]:
    """
    Associates an incoming email reply with the correct Contact, Campaign, and Outreach record.
    Enforces strict tenant isolation, verified destination mailbox routing, and fail-closed handling
    when matching is ambiguous across organizations.
    """
    clean_from = (from_email or "").strip().lower()
    if not clean_from:
        raise ValueError("Sender email address (from_email) is required for reply association.")

    clean_to = (to_email or "").strip().lower() if to_email else None
    outreach: Optional[Outreach] = None

    # Strategy 1: Match by In-Reply-To or References message headers
    candidate_msg_ids: List[str] = []
    for ref_header in (in_reply_to, references):
        if ref_header:
            for token in ref_header.replace(",", " ").split():
                clean_token = token.strip("<>").strip()
                if clean_token:
                    candidate_msg_ids.append(clean_token)
                    if "@" in clean_token:
                        candidate_msg_ids.append(clean_token.split("@")[0])

    if candidate_msg_ids:
        query = db.query(Outreach).filter(
            or_(
                Outreach.provider_message_id.in_(candidate_msg_ids),
                Outreach.provider_message_id.in_([f"<{c}>" for c in candidate_msg_ids]),
            )
        )
        if org_id:
            query = query.filter(Outreach.organization_id == org_id)

        candidate_outreach = query.order_by(Outreach.sent_at.desc(), Outreach.created_at.desc()).first()
        if candidate_outreach:
            # Sender Verification: Verify sender email matches the outreach recipient / contact
            expected_recip = (
                candidate_outreach.recipient
                or (candidate_outreach.contact.email if candidate_outreach.contact else "")
            ).strip().lower()
            if clean_from != expected_recip:
                raise ValueError(
                    f"Reply sender '{from_email}' does not match original outreach recipient '{expected_recip}'."
                )

            # Destination Mailbox Cross-Tenant Conflict Verification
            if clean_to:
                mailbox_user = db.query(User).filter(User.email.ilike(clean_to)).first()
                if mailbox_user and mailbox_user.organization_id != candidate_outreach.organization_id:
                    raise AmbiguousReplyAssociationError(
                        f"Cross-tenant conflict: destination mailbox '{to_email}' belongs to organization "
                        f"'{mailbox_user.organization_id}', but referenced outreach belongs to organization '{candidate_outreach.organization_id}'."
                    )

            outreach = candidate_outreach

    # Strategy 2: Missing or unmatchable threading headers -> Safe Fallback with Tenant Resolution
    if not outreach:
        # Step 2a: Resolve target tenant
        target_org_id = org_id

        # Check if destination mailbox resolves a tenant user
        if not target_org_id and clean_to:
            mailbox_user = db.query(User).filter(User.email.ilike(clean_to)).first()
            if mailbox_user:
                target_org_id = mailbox_user.organization_id

        # Step 2b: Discover which organizations have sent outreach to this recipient
        all_matching_outreaches = (
            db.query(Outreach.organization_id)
            .filter(
                or_(
                    Outreach.recipient.ilike(clean_from),
                    Outreach.contact.has(Contact.email.ilike(clean_from)),
                ),
                Outreach.status.in_(["sent", "sending"]),
            )
            .distinct()
            .all()
        )
        matching_org_ids = [row[0] for row in all_matching_outreaches]

        if not matching_org_ids:
            raise OutreachNotFoundError(
                f"No active sent outreach found to associate with reply from '{from_email}'."
            )

        if not target_org_id:
            if len(matching_org_ids) > 1:
                # Ambiguous: Multiple organizations have sent outreach to this prospect!
                # Fail closed rather than guessing or picking the most recent global match.
                raise AmbiguousReplyAssociationError(
                    f"Ambiguous tenant resolution: multiple organizations ({len(matching_org_ids)}) have active outreach "
                    f"to '{from_email}'. In-Reply-To threading headers or a verified tenant destination mailbox (to_email) are required."
                )
            else:
                target_org_id = matching_org_ids[0]
        else:
            # Verify target_org_id actually has outreach for this recipient
            if target_org_id not in matching_org_ids:
                raise OutreachNotFoundError(
                    f"No active sent outreach found for recipient '{from_email}' in organization '{target_org_id}'."
                )

        # Query strictly within target_org_id
        contact_ids = [
            c[0]
            for c in db.query(Contact.id)
            .filter(Contact.organization_id == target_org_id, Contact.email.ilike(clean_from))
            .all()
        ]
        conditions = [Outreach.recipient.ilike(clean_from)]
        if contact_ids:
            conditions.append(Outreach.contact_id.in_(contact_ids))

        outreach = (
            db.query(Outreach)
            .filter(
                Outreach.organization_id == target_org_id,
                or_(*conditions),
                Outreach.status.in_(["sent", "sending"]),
            )
            .order_by(Outreach.sent_at.desc(), Outreach.created_at.desc())
            .first()
        )

    if not outreach:
        raise OutreachNotFoundError(
            f"No active sent outreach found to associate with reply from '{from_email}'."
        )

    # Format event metadata with genuine reply content
    metadata: Dict[str, Any] = {
        "source": "inbound_reply",
        "from_email": clean_from,
        "to_email": to_email,
        "subject": subject,
        "body": body,
        "snippet": (body[:300] + "...") if body and len(body) > 300 else body,
        "in_reply_to": in_reply_to,
        "references": references,
        "provider_message_id": provider_message_id,
    }
    if raw_payload:
        metadata["raw_payload"] = raw_payload

    event = record_replied(
        db=db,
        org_id=outreach.organization_id,
        outreach_id=outreach.id,
        event_metadata=metadata,
    )
    return outreach, event
