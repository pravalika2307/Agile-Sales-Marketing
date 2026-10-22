"""Inbound email message ingestion service with CRM matching and untrusted content protection."""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.crm import Company, Contact
from app.models.inbound_email import InboundEmail
from app.models.lead import Lead
from app.services.graph.client import GraphMessage

logger = logging.getLogger(__name__)

# Pattern to strip potential HTML script tags and dangerous event handlers from previews
SCRIPT_TAG_REGEX = re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL)
HTML_TAG_REGEX = re.compile(r"<[^>]+>")


@dataclass
class IngestionSummary:
    """Summary metrics of an inbound email ingestion batch."""
    fetched: int = 0
    imported: int = 0
    matched: int = 0
    unmatched: int = 0
    skipped: int = 0
    errors: int = 0


def sanitize_body_preview(text: Optional[str], max_len: int = 250) -> str:
    """
    Creates a safe, truncated text preview of untrusted message content.
    Strips raw HTML tags and escapes potential script injections.
    """
    if not text:
        return ""
    no_script = SCRIPT_TAG_REGEX.sub("", text)
    clean_text = HTML_TAG_REGEX.sub(" ", no_script)
    # Collapse multiple whitespaces
    collapsed = " ".join(clean_text.split())
    if len(collapsed) > max_len:
        return collapsed[:max_len].rstrip() + "..."
    return collapsed


def match_sender_to_crm(
    db: Session,
    org_id: uuid.UUID,
    sender_email: str,
) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID], Optional[uuid.UUID]]:
    """
    Matches the incoming email sender against existing CRM entities within the tenant's organization:
    1. Match Contact record by lowercase email.
    2. If Contact not found, match Lead record by lowercase email.
    3. Resolve Company via contact/lead company link or domain matching.

    Returns:
        (matched_contact_id, matched_lead_id, matched_company_id)
    """
    clean_email = sender_email.strip().lower()
    if not clean_email:
        return None, None, None

    matched_contact: Optional[Contact] = None
    matched_lead: Optional[Lead] = None
    matched_company_id: Optional[uuid.UUID] = None

    # 1. Check Contacts within the same tenant organization
    try:
        matched_contact = (
            db.query(Contact)
            .filter(
                Contact.organization_id == org_id,
                func.lower(Contact.email) == clean_email,
            )
            .first()
        )
    except (ProgrammingError, OperationalError) as exc:
        logger.debug("Failed querying Contact table for matching: %s", exc)
        db.rollback()

    if matched_contact:
        matched_company_id = matched_contact.company_id
        return matched_contact.id, None, matched_company_id

    # 2. Check Leads within the same tenant organization
    try:
        matched_lead = (
            db.query(Lead)
            .filter(
                Lead.organization_id == org_id,
                func.lower(Lead.email) == clean_email,
            )
            .first()
        )
    except (ProgrammingError, OperationalError) as exc:
        logger.debug("Failed querying Lead table for matching: %s", exc)
        db.rollback()

    if matched_lead:
        matched_company_id = matched_lead.company_id
        return None, matched_lead.id, matched_company_id

    # 3. If neither individual contact nor lead matches, attempt domain matching against Companies
    if "@" in clean_email:
        domain = clean_email.split("@")[1].strip()
        common_consumer_domains = {
            "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com"
        }
        if domain and domain not in common_consumer_domains:
            try:
                company = (
                    db.query(Company)
                    .filter(
                        Company.organization_id == org_id,
                        func.lower(Company.domain) == domain.lower(),
                    )
                    .first()
                )
                if company:
                    matched_company_id = company.id
            except (ProgrammingError, OperationalError):
                db.rollback()

    return None, None, matched_company_id


def import_graph_messages(
    db: Session,
    org_id: uuid.UUID,
    messages: List[GraphMessage],
) -> IngestionSummary:
    """
    Ingests messages retrieved from the Microsoft Graph support mailbox into the database.

    SAFETY & INTEGRITY GUARANTEES:
    1. Read-only: Never deletes, moves, or alters emails on Microsoft 365 Exchange Online.
    2. Duplicate Prevention: Checks existing graph_message_id and internet_message_id within the tenant.
    3. Sender Matching: Maps recognized senders to Contact / Lead / Company records.
    4. Manual Review: Flags unmapped messages as 'unmatched' and 'pending' review.
    5. Untrusted Input: Strips scripts from preview, treats body content as untrusted input.
       Never executes instructions from incoming email content.
    6. No Auto-Replies: Ingests data strictly into CRM/inbox without initiating automated email replies.
    7. Multi-Tenant Isolation: Binds all records strictly to the caller's organization_id.
    """
    summary = IngestionSummary(fetched=len(messages))
    if not messages:
        return summary

    try:
        # Pre-fetch existing message identifiers for this tenant to optimize duplicate checking
        msg_ids = [m.id for m in messages if m.id]
        existing_rows = (
            db.query(InboundEmail.graph_message_id, InboundEmail.internet_message_id)
            .filter(
                InboundEmail.organization_id == org_id,
                InboundEmail.graph_message_id.in_(msg_ids),
            )
            .all()
        )
        existing_graph_ids = {r[0] for r in existing_rows}
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.warning(
            "InboundEmail table not yet migrated (%s). Cannot persist inbound emails to database. "
            "Proposed migration 'b3c4d5e6f7a8' is pending.",
            exc,
        )
        # Graceful return with fetched count
        return summary

    for msg in messages:
        # 1. Duplicate check by Graph Message ID
        if msg.id in existing_graph_ids:
            summary.skipped += 1
            continue

        # 2. Duplicate check by RFC 2822 Internet Message-ID
        if msg.internet_message_id:
            dup_msg_id = (
                db.query(InboundEmail.id)
                .filter(
                    InboundEmail.organization_id == org_id,
                    InboundEmail.internet_message_id == msg.internet_message_id,
                )
                .first()
            )
            if dup_msg_id:
                summary.skipped += 1
                continue

        # 3. Match sender to CRM entities
        contact_id, lead_id, company_id = match_sender_to_crm(db, org_id, msg.from_email)
        is_matched = bool(contact_id or lead_id or company_id)

        sync_status = "matched" if is_matched else "unmatched"
        manual_review_status = "reviewed" if is_matched else "pending"

        # 4. Safe sanitized preview of untrusted message content
        safe_preview = sanitize_body_preview(msg.body_preview or msg.body_content)

        # 5. Create InboundEmail record
        inbound_record = InboundEmail(
            organization_id=org_id,
            graph_message_id=msg.id,
            graph_conversation_id=msg.conversation_id,
            internet_message_id=msg.internet_message_id,
            sender_email=msg.from_email,
            sender_name=msg.from_name,
            recipient_email=msg.to_recipients[0] if msg.to_recipients else "support@agilereceivables.com",
            subject=msg.subject,
            body_preview=safe_preview,
            body_content=msg.body_content,
            body_content_type=msg.body_content_type or "html",
            received_at=msg.received_at,
            is_read=msg.is_read,
            has_attachments=msg.has_attachments,
            matched_contact_id=contact_id,
            matched_lead_id=lead_id,
            matched_company_id=company_id,
            sync_status=sync_status,
            manual_review_status=manual_review_status,
            raw_metadata={
                "to_recipients": msg.to_recipients,
                "importance": msg.raw_data.get("importance", "normal"),
                "has_attachments": msg.has_attachments,
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(inbound_record)
        existing_graph_ids.add(msg.id)
        summary.imported += 1

        if is_matched:
            summary.matched += 1
        else:
            summary.unmatched += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to commit batch of inbound emails: %s", exc)
        summary.errors += summary.imported
        summary.imported = 0

    return summary
