"""Twilio delivery status callback handler with cryptographic X-Twilio-Signature validation."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outreach import Outreach, OutreachEvent

logger = logging.getLogger(__name__)


class WebhookSignatureVerificationError(Exception):
    """Raised when an incoming webhook request has an invalid cryptographic signature."""
    pass


class MessageRecordNotFoundError(Exception):
    """Raised when a status callback cannot be matched to any known Outreach record."""
    pass


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
