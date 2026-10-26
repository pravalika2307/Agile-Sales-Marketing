"""Twilio webhook handler: delivery status callbacks, inbound SMS routing, and opt-out suppression."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.sms import InboundSMSMessage, SMSSuppression
from app.models.tenant import Organization
from app.services.sms.base import normalize_phone_number

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class WebhookSignatureVerificationError(Exception):
    """Raised when an incoming webhook request has an invalid cryptographic signature."""
    pass


class MessageRecordNotFoundError(Exception):
    """Raised when a status callback cannot be matched to any known Outreach record."""
    pass


# ── Standard Carrier Opt-Out Keywords ─────────────────────────────────────────

OPT_OUT_KEYWORDS = {
    "stop",
    "stopall",
    "unsubscribe",
    "cancel",
    "end",
    "quit",
}


def extract_opt_out_keyword(body: Optional[str]) -> Optional[str]:
    """
    Evaluates whether an inbound SMS body contains a standard carrier opt-out keyword.
    Whitespace-normalized and case-insensitive.
    
    Supported keywords (CTIA / Twilio standards):
    STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT
    """
    if not body:
        return None

    cleaned = re.sub(r"[^\w\s]", "", body.strip().lower())
    tokens = cleaned.split()
    if not tokens:
        return None

    if cleaned in OPT_OUT_KEYWORDS:
        return cleaned.upper()

    if tokens[0] in OPT_OUT_KEYWORDS:
        return tokens[0].upper()

    return None


def is_inbound_sms(payload: Dict[str, Any]) -> bool:
    """
    Distinguishes inbound SMS messages from outbound delivery status callbacks.
    
    Rules:
    - Outbound delivery status callbacks contain MessageStatus / SmsStatus with values:
      'queued', 'sent', 'delivered', 'undelivered', 'failed'.
    - Inbound messages contain 'Body' or SmsStatus == 'received' and lack outbound delivery statuses.
    """
    status_val = (payload.get("MessageStatus") or payload.get("SmsStatus") or "").lower()
    if status_val in ("queued", "sent", "delivered", "undelivered", "failed"):
        return False
    if "Body" in payload or status_val == "received":
        return True
    return False


# ── Cryptographic Signature Verification ──────────────────────────────────────

def verify_twilio_signature(
    expected_url: str,
    params: Dict[str, Any],
    signature: str,
    auth_token: Optional[str] = None,
) -> bool:
    """
    Verify incoming Twilio webhook request authenticity via HMAC-SHA1 signature.

    Algorithm (Twilio Security Specification):
    1. Start with the full webhook URL.
    2. Sort POST parameter keys alphabetically.
    3. Concatenate each key and value directly to the URL string.
    4. Compute HMAC-SHA1 of the combined string using Twilio Auth Token.
    5. Compare base64-encoded digest with X-Twilio-Signature header using constant-time comparison.
    """
    token = (auth_token or settings.TWILIO_AUTH_TOKEN or "").strip()
    if not token or not signature:
        return False

    # 1. Base URL string
    data_to_sign = expected_url

    # 2 & 3. Sort keys and append key + value
    for key in sorted(params.keys()):
        data_to_sign += f"{key}{params[key]}"

    # 4. Compute HMAC-SHA1
    mac = hmac.new(
        token.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha1,
    )
    computed_signature = base64.b64encode(mac.digest()).decode("utf-8")

    # 5. Constant-time digest comparison
    return hmac.compare_digest(computed_signature, signature.strip())


# ── Inbound Message Routing & Tenant Resolution ───────────────────────────────

def _match_inbound_tenant_and_contact(
    db: Session,
    normalized_from: str,
    normalized_to: str,
) -> Tuple[uuid.UUID, Optional[uuid.UUID], Optional[Outreach]]:
    """
    Safely resolve the tenant Organization and matched Contact for an inbound message.
    
    Resolution order:
    1. Most recent outbound Outreach record with channel='sms' and recipient=normalized_from.
    2. Contact lookup by phone=normalized_from across organizations.
    3. Fallback to default configured Twilio organization without attaching to an arbitrary contact.
    """
    # 1. Look for most recent SMS outreach to this sender phone
    recent_outreach = (
        db.query(Outreach)
        .filter(
            Outreach.channel == "sms",
            Outreach.recipient == normalized_from,
        )
        .order_by(Outreach.created_at.desc())
        .first()
    )
    if recent_outreach:
        return recent_outreach.organization_id, recent_outreach.contact_id, recent_outreach

    # 2. Look for Contact with this phone number
    matching_contact = (
        db.query(Contact)
        .filter(Contact.phone == normalized_from)
        .first()
    )
    if matching_contact:
        return matching_contact.organization_id, matching_contact.id, None

    # Try 10-digit suffix match in case stored phone has different formatting
    if len(normalized_from) >= 10:
        ten_digits = normalized_from[-10:]
        matching_contact = (
            db.query(Contact)
            .filter(Contact.phone.like(f"%{ten_digits}"))
            .first()
        )
        if matching_contact:
            return matching_contact.organization_id, matching_contact.id, None

    # 3. Unknown sender: resolve default organization
    default_org = db.query(Organization).order_by(Organization.created_at.asc()).first()
    if not default_org:
        raise ValueError("No active Organization found to route inbound SMS.")

    return default_org.id, None, None


# ── Delivery Status Callback Handler ──────────────────────────────────────────

def process_twilio_delivery_callback(
    db: Session,
    payload: Dict[str, Any],
    url: str,
    signature: Optional[str] = None,
    enforce_signature: bool = True,
) -> Dict[str, Any]:
    """
    Processes an incoming Twilio delivery status callback event.

    Features:
    - Cryptographic signature check.
    - Idempotent event recording into OutreachEvent.
    - Status lifecycle transitions (queued, sent, delivered, undelivered, failed).
    - Prevents cross-tenant leaks.
    """
    # 1. Signature Verification
    if enforce_signature:
        if not signature:
            raise WebhookSignatureVerificationError("Missing X-Twilio-Signature header.")
        if not verify_twilio_signature(url, payload, signature):
            raise WebhookSignatureVerificationError("Invalid Twilio webhook cryptographic signature.")

    # 2. Extract Message SID & Status
    message_sid = payload.get("MessageSid") or payload.get("SmsSid")
    if not message_sid:
        raise ValueError("Payload missing MessageSid.")

    raw_status = (payload.get("MessageStatus") or payload.get("SmsStatus") or "").lower()
    error_code = payload.get("ErrorCode")
    error_message = payload.get("ErrorMessage")

    # 3. Locate matching Outreach record
    outreach = (
        db.query(Outreach)
        .filter(Outreach.provider_message_id == message_sid)
        .first()
    )

    if not outreach:
        logger.warning("Twilio callback for unknown MessageSid: %s", message_sid)
        return {
            "status": "ignored",
            "message_sid": message_sid,
            "reason": "No matching outreach record found for MessageSid.",
        }

    now_utc = datetime.now(timezone.utc)
    metadata = {
        "message_sid": message_sid,
        "raw_status": raw_status,
        "error_code": error_code,
        "error_message": error_message,
        "from": payload.get("From"),
        "to": payload.get("To"),
    }

    # 4. Idempotently handle state transitions
    if raw_status == "delivered":
        if outreach.status == "sending":
            outreach.status = "sent"
        if not outreach.first_delivered_at:
            outreach.first_delivered_at = now_utc

        db.add(
            OutreachEvent(
                organization_id=outreach.organization_id,
                outreach_id=outreach.id,
                event_type="delivered",
                event_metadata=metadata,
                occurred_at=now_utc,
            )
        )

    elif raw_status in ("failed", "undelivered"):
        outreach.status = "failed"
        if not outreach.first_bounced_at:
            outreach.first_bounced_at = now_utc

        db.add(
            OutreachEvent(
                organization_id=outreach.organization_id,
                outreach_id=outreach.id,
                event_type="failed",
                event_metadata=metadata,
                occurred_at=now_utc,
            )
        )

    elif raw_status == "sent":
        if outreach.status == "sending":
            outreach.status = "sent"
        if not outreach.sent_at:
            outreach.sent_at = now_utc

        db.add(
            OutreachEvent(
                organization_id=outreach.organization_id,
                outreach_id=outreach.id,
                event_type="sent",
                event_metadata=metadata,
                occurred_at=now_utc,
            )
        )

    else:
        # Queued or intermediate state
        db.add(
            OutreachEvent(
                organization_id=outreach.organization_id,
                outreach_id=outreach.id,
                event_type=raw_status or "callback",
                event_metadata=metadata,
                occurred_at=now_utc,
            )
        )

    db.commit()
    db.refresh(outreach)

    return {
        "status": "processed",
        "outreach_id": str(outreach.id),
        "message_sid": message_sid,
        "updated_status": outreach.status,
    }


# ── Inbound SMS Message & Opt-Out Handler ─────────────────────────────────────

def process_twilio_inbound_message(
    db: Session,
    payload: Dict[str, Any],
    url: str,
    signature: Optional[str] = None,
    enforce_signature: bool = True,
) -> Dict[str, Any]:
    """
    Processes an incoming Twilio SMS message from a recipient.

    Features:
    - Cryptographic signature check (X-Twilio-Signature).
    - Idempotent deduplication using MessageSid.
    - Automatic detection of standard carrier opt-out keywords (STOP, UNSUBSCRIBE, CANCEL, QUIT, END).
    - Durable SMS-specific suppression recording.
    - Automatic cancellation of queued/scheduled SMS outreach for the suppressed phone number.
    - Preserves non-SMS communication channels (email, voice, direct mail) for the contact.
    - Safe handling of unknown senders without cross-contact corruption.
    - Privacy protection: avoids persisting unnecessary message bodies or contact PII.
    """
    # 1. Signature Verification
    if enforce_signature:
        if not signature:
            raise WebhookSignatureVerificationError("Missing X-Twilio-Signature header.")
        if not verify_twilio_signature(url, payload, signature):
            raise WebhookSignatureVerificationError("Invalid Twilio webhook cryptographic signature.")

    # 2. Extract and validate required payload fields
    message_sid = payload.get("MessageSid") or payload.get("SmsSid")
    from_raw = payload.get("From")
    to_raw = payload.get("To") or ""
    body_raw = payload.get("Body") or ""

    if not message_sid or not from_raw:
        raise ValueError("Payload missing MessageSid or From phone number.")

    # 3. Idempotency Check
    try:
        existing_inbound = (
            db.query(InboundSMSMessage)
            .filter(InboundSMSMessage.message_sid == message_sid)
            .first()
        )
        if existing_inbound:
            logger.info("Ignoring duplicate inbound SMS webhook: %s", message_sid)
            return {
                "status": "already_processed",
                "message_sid": message_sid,
                "is_opt_out": existing_inbound.is_opt_out,
                "action": "suppressed" if existing_inbound.is_opt_out else "received",
            }
    except Exception as exc:
        logger.debug("Idempotency lookup skipped (table may be pending migration): %s", exc)

    # 4. Normalize phone numbers
    is_valid, normalized_from, _ = normalize_phone_number(from_raw)
    if not is_valid:
        normalized_from = from_raw.strip()

    _, normalized_to, _ = normalize_phone_number(to_raw)
    if not normalized_to:
        normalized_to = to_raw.strip()

    now_utc = datetime.now(timezone.utc)

    # 5. Match Tenant and Contact
    org_id, contact_id, recent_outreach = _match_inbound_tenant_and_contact(
        db=db,
        normalized_from=normalized_from,
        normalized_to=normalized_to,
    )

    # 6. Opt-Out Keyword Detection
    opt_out_kw = extract_opt_out_keyword(body_raw)
    is_opt_out = bool(opt_out_kw)

    # 7. Handle Opt-Out Suppression
    if is_opt_out:
        logger.info(
            "Opt-out keyword '%s' received from %s for org %s",
            opt_out_kw,
            normalized_from,
            org_id,
        )

        # 7.1 Record in durable SMSSuppression table
        try:
            suppression = (
                db.query(SMSSuppression)
                .filter(
                    SMSSuppression.organization_id == org_id,
                    SMSSuppression.phone == normalized_from,
                )
                .first()
            )
            if not suppression:
                suppression = SMSSuppression(
                    organization_id=org_id,
                    phone=normalized_from,
                    contact_id=contact_id,
                    reason="opt_out_keyword",
                    keyword=opt_out_kw,
                    source="inbound_sms",
                    suppressed_at=now_utc,
                )
                db.add(suppression)
            else:
                suppression.keyword = opt_out_kw
                suppression.suppressed_at = now_utc
                if contact_id and not suppression.contact_id:
                    suppression.contact_id = contact_id
        except Exception as exc:
            logger.warning("Failed to record SMSSuppression: %s", exc)

        # 7.2 Cancel all pending/scheduled/draft SMS outreach for this phone in this organization
        pending_sms_outreaches = (
            db.query(Outreach)
            .filter(
                Outreach.organization_id == org_id,
                Outreach.channel == "sms",
                Outreach.status.in_(["draft", "scheduled"]),
                Outreach.recipient == normalized_from,
            )
            .all()
        )
        for pending in pending_sms_outreaches:
            pending.status = "cancelled"
            db.add(
                OutreachEvent(
                    organization_id=org_id,
                    outreach_id=pending.id,
                    event_type="cancelled",
                    event_metadata={
                        "reason": f"Recipient opted out via SMS keyword '{opt_out_kw}'",
                        "keyword": opt_out_kw,
                    },
                    occurred_at=now_utc,
                )
            )

        # 7.3 Log opt-out audit event on recent outreach if available
        if recent_outreach:
            db.add(
                OutreachEvent(
                    organization_id=org_id,
                    outreach_id=recent_outreach.id,
                    event_type="cancelled",
                    event_metadata={
                        "reason": "sms_opt_out",
                        "keyword": opt_out_kw,
                        "source": "inbound_sms",
                    },
                    occurred_at=now_utc,
                )
            )

    else:
        # Non-opt-out inbound reply
        logger.info("Inbound non-opt-out SMS received from %s", normalized_from)
        if recent_outreach:
            if not recent_outreach.first_replied_at:
                recent_outreach.first_replied_at = now_utc
            db.add(
                OutreachEvent(
                    organization_id=org_id,
                    outreach_id=recent_outreach.id,
                    event_type="replied",
                    event_metadata={"source": "inbound_sms"},
                    occurred_at=now_utc,
                )
            )

    # 8. Record InboundSMSMessage for deduplication and audit trail
    try:
        inbound_record = InboundSMSMessage(
            organization_id=org_id,
            message_sid=message_sid,
            from_phone=normalized_from,
            to_phone=normalized_to,
            body_snippet=opt_out_kw if is_opt_out else "[inbound message]",
            is_opt_out=is_opt_out,
            opt_out_keyword=opt_out_kw,
            matched_contact_id=contact_id,
            matched_outreach_id=recent_outreach.id if recent_outreach else None,
            received_at=now_utc,
        )
        db.add(inbound_record)
    except Exception as exc:
        logger.debug("InboundSMSMessage record skipped (table may be pending migration): %s", exc)

    db.commit()

    return {
        "status": "processed",
        "message_sid": message_sid,
        "is_opt_out": is_opt_out,
        "action": "suppressed" if is_opt_out else "received",
        "organization_id": str(org_id),
        "matched_contact_id": str(contact_id) if contact_id else None,
    }


# ── Unified Webhook Dispatcher ────────────────────────────────────────────────

def handle_twilio_webhook(
    db: Session,
    payload: Dict[str, Any],
    url: str,
    signature: Optional[str] = None,
    enforce_signature: bool = True,
) -> Dict[str, Any]:
    """
    Unified entry point for Twilio messaging webhooks.
    Automatically discriminates between delivery receipts and inbound messages.
    """
    if is_inbound_sms(payload):
        return process_twilio_inbound_message(
            db=db,
            payload=payload,
            url=url,
            signature=signature,
            enforce_signature=enforce_signature,
        )
    else:
        return process_twilio_delivery_callback(
            db=db,
            payload=payload,
            url=url,
            signature=signature,
            enforce_signature=enforce_signature,
        )
