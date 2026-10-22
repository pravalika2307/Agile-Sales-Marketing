"""High-level SMS orchestration service: rendering, consent, phone validation, and safe dispatch."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.services.campaign_steps.template_renderer import (
    DEFAULT_SENDER_NAME,
    find_unresolved_placeholders,
    render_template,
)
from app.services.organization_config import (
    MissingBookingUrlError,
    get_organization_booking_url,
)
from app.services.sms.base import (
    MockSMSProvider,
    SMSMessage,
    SMSProvider,
    SMSSendResult,
    calculate_sms_segments,
    normalize_phone_number,
)
from app.services.sms.twilio_provider import (
    TwilioLiveSendingDisabledError,
    TwilioSMSProvider,
)

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class SMSServiceError(Exception):
    """Base exception for SMS service operations."""
    pass


class InvalidPhoneNumberError(SMSServiceError):
    """Raised when phone number is missing, unparseable, or not valid E.164."""
    pass


class SMSConsentSuppressedError(SMSServiceError):
    """Raised when contact has opted out or lacks SMS consent."""
    pass


class SMSDeliveryError(SMSServiceError):
    """Raised when SMS delivery fails at the provider level."""
    pass


# ── Provider Factory ──────────────────────────────────────────────────────────

def get_sms_provider(force_mock: bool = False) -> SMSProvider:
    """
    Selects the active SMS provider based on safety configuration.

    Guarantees:
    - If force_mock is True: Always returns MockSMSProvider.
    - If TWILIO_ENABLED is False or TWILIO_ALLOW_LIVE_SENDING is False: Returns MockSMSProvider.
    - Only returns TwilioSMSProvider when live sending is explicitly configured and authorized.
    """
    if force_mock:
        return MockSMSProvider()

    if settings.is_twilio_live_sending_allowed:
        return TwilioSMSProvider()

    return MockSMSProvider()


# ── Phone & Consent Validation ────────────────────────────────────────────────

def validate_recipient_phone(phone: Optional[str]) -> Dict[str, Any]:
    """Validates and normalizes phone number to E.164 standard format."""
    is_valid, formatted, err = normalize_phone_number(phone)
    return {
        "is_valid": is_valid,
        "raw_phone": phone or "",
        "formatted_phone": formatted if is_valid else "",
        "error_message": err,
    }


def check_sms_consent(contact_or_lead: Any) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether a prospect is legally and operationally eligible for SMS outreach.

    Checks:
    1. Phone number presence.
    2. Phone number E.164 compliance.
    3. Explicit opt-out / suppression status (e.g. 'opted_out', 'unsubscribed').
    """
    if not contact_or_lead:
        return False, "Contact record not found."

    lead_status = getattr(contact_or_lead, "lead_status", None)
    if lead_status in ("opted_out", "unsubscribed"):
        return False, f"Recipient has opted out of communications (status: '{lead_status}')."

    phone = getattr(contact_or_lead, "phone", None)
    if not phone or not str(phone).strip():
        return False, "Recipient has no phone number recorded."

    is_valid, _, err = normalize_phone_number(str(phone))
    if not is_valid:
        return False, f"Recipient phone number is invalid: {err}"

    return True, None


# ── Template Rendering & Preview ──────────────────────────────────────────────

def render_sms_message(
    template_body: str,
    contact_data: Dict[str, Any],
    booking_url: Optional[str] = None,
    sender_name: Optional[str] = None,
    sender_company_name: Optional[str] = None,
) -> str:
    """
    Personalizes an SMS template string using contact metadata and organization variables.
    """
    if not template_body:
        return ""

    result = template_body
    s_name = sender_name or DEFAULT_SENDER_NAME
    s_company = sender_company_name or "Agile Sales & Marketing"
    b_url = booking_url or ""

    first_name = contact_data.get("first_name") or contact_data.get("contact.first_name") or ""
    last_name = contact_data.get("last_name") or contact_data.get("contact.last_name") or ""
    full_name = (
        f"{first_name} {last_name}".strip()
        or contact_data.get("full_name")
        or contact_data.get("contact.full_name")
        or ""
    )
    email = contact_data.get("email") or contact_data.get("contact.email") or ""
    phone = contact_data.get("phone") or contact_data.get("contact.phone") or ""
    company = (
        contact_data.get("company_name")
        or contact_data.get("company")
        or contact_data.get("contact.company")
        or contact_data.get("contact.company_name")
        or ""
    )

    replacements = {
        "{contact.first_name}": first_name,
        "{{contact.first_name}}": first_name,
        "{first_name}": first_name,
        "{{first_name}}": first_name,
        "{contact.last_name}": last_name,
        "{{contact.last_name}}": last_name,
        "{last_name}": last_name,
        "{{last_name}}": last_name,
        "{contact.full_name}": full_name,
        "{{contact.full_name}}": full_name,
        "{contact.email}": email,
        "{{contact.email}}": email,
        "{contact.phone}": phone,
        "{{contact.phone}}": phone,
        "{contact.company}": company,
        "{{contact.company}}": company,
        "{contact.company_name}": company,
        "{{contact.company_name}}": company,
        "{sender.name}": s_name,
        "{{sender.name}}": s_name,
        "{sender_name}": s_name,
        "{{sender_name}}": s_name,
        "{sender.company_name}": s_company,
        "{{sender.company_name}}": s_company,
        "{sender_company}": s_company,
        "{{sender_company}}": s_company,
        "{booking_link}": b_url,
        "{{booking_link}}": b_url,
        "{booking_url}": b_url,
        "{{booking_url}}": b_url,
    }

    for placeholder, val in replacements.items():
        if val:
            result = result.replace(placeholder, str(val))

    return result


def preview_sms_step(
    template_body: str,
    contact_data: Dict[str, Any],
    booking_url: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Renders an SMS template preview and returns text metrics (character count, segments, encoding).
    """
    rendered = render_sms_message(
        template_body=template_body,
        contact_data=contact_data,
        booking_url=booking_url,
        sender_name=sender_name,
    )
    unresolved = find_unresolved_placeholders(rendered)
    calc = calculate_sms_segments(rendered)

    recipient_phone = contact_data.get("phone") or contact_data.get("contact.phone") or ""
    phone_val = validate_recipient_phone(recipient_phone)

    return {
        "rendered_body": rendered,
        "character_count": calc["character_count"],
        "segment_count": calc["segment_count"],
        "encoding": calc["encoding"],
        "remaining_in_segment": calc["remaining_in_segment"],
        "max_per_segment": calc["max_per_segment"],
        "unresolved_placeholders": list(unresolved),
        "phone_validation": phone_val,
    }


# ── Dispatch Orchestration ───────────────────────────────────────────────────

def send_sms_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    provider: Optional[SMSProvider] = None,
    raise_on_failure: bool = False,
) -> Outreach:
    """
    Executes delivery of an SMS outreach item.
    Enforces strict tenant isolation, consent verification, and safe fail-closed provider dispatch.
    """
    # 1. Fetch outreach with row lock where supported
    query = db.query(Outreach).filter(
        Outreach.id == outreach_id,
        Outreach.organization_id == org_id,
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    outreach = query.first()

    if not outreach:
        raise SMSServiceError(f"Outreach '{outreach_id}' not found.")

    if outreach.channel != "sms":
        raise SMSServiceError(
            f"Cannot send outreach '{outreach_id}' with SMS service: channel is '{outreach.channel}'."
        )

    # 2. Duplicate send & status checks
    if outreach.status == "sent":
        raise SMSServiceError("Outreach has already been sent.")
    if outreach.status == "sending":
        raise SMSServiceError("Outreach is currently in the process of sending.")
    if outreach.status not in ("draft", "scheduled"):
        raise SMSServiceError(f"Cannot send outreach in status '{outreach.status}'. Allowed initial status is 'draft'.")

    # 3. Contact & Consent Verification
    contact = outreach.contact
    if not contact:
        raise SMSServiceError("Referenced contact record is missing.")

    is_eligible, ineligibility_reason = check_sms_consent(contact)
    if not is_eligible:
        raise SMSConsentSuppressedError(f"SMS delivery blocked: {ineligibility_reason}")

    # 4. Resolve recipient phone number
    target_phone = outreach.recipient or contact.phone
    is_valid, formatted_phone, phone_err = normalize_phone_number(target_phone)
    if not is_valid:
        raise InvalidPhoneNumberError(f"Recipient phone number is invalid: {phone_err}")

    # Update recipient to canonical E.164
    outreach.recipient = formatted_phone

    # 5. Resolve body and booking URL if placeholder present
    body_text = outreach.body or ""
    if "{booking_link}" in body_text or "{booking_url}" in body_text:
        booking_url = get_organization_booking_url(db, org_id)
        if not booking_url:
            raise MissingBookingUrlError(
                "SMS body contains {booking_link} but organization has no booking URL configured."
            )
        body_text = body_text.replace("{booking_link}", booking_url).replace("{booking_url}", booking_url)
        outreach.body = body_text

    # 6. Check for any remaining unresolved placeholders
    unresolved = find_unresolved_placeholders(body_text)
    if unresolved:
        raise SMSServiceError(f"SMS contains unresolved template placeholders: {', '.join(unresolved)}")

    # 7. Select provider (defaults to MockSMSProvider when live sending disabled)
    active_provider = provider or get_sms_provider()

    # 8. Transition status to 'sending' and record event
    outreach.status = "sending"
    now_utc = datetime.now(timezone.utc)
    db.add(
        OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="sending",
            event_metadata={"provider": active_provider.provider_name, "recipient": formatted_phone},
            occurred_at=now_utc,
        )
    )
    db.commit()

    # 9. Deliver via provider
    msg = SMSMessage(
        to_phone=formatted_phone,
        body=outreach.body or "",
        metadata={"outreach_id": str(outreach.id), "org_id": str(org_id)},
    )
    result: SMSSendResult = active_provider.send(msg)

    # 10. Process result
    if result.success:
        outreach.status = "sent"
        outreach.provider = result.provider
        outreach.provider_message_id = result.provider_message_id
        outreach.sent_at = result.timestamp
        db.add(
            OutreachEvent(
                organization_id=org_id,
                outreach_id=outreach.id,
                event_type="sent",
                event_metadata={
                    "provider": result.provider,
                    "provider_message_id": result.provider_message_id,
                    "segments": result.segment_count,
                    "encoding": result.encoding,
                },
                occurred_at=result.timestamp,
            )
        )
    else:
        outreach.status = "failed"
        outreach.provider = result.provider
        db.add(
            OutreachEvent(
                organization_id=org_id,
                outreach_id=outreach.id,
                event_type="failed",
                event_metadata={
                    "provider": result.provider,
                    "error_message": result.error_message,
                },
                occurred_at=result.timestamp,
            )
        )
        if raise_on_failure:
            db.commit()
            raise SMSDeliveryError(f"Provider delivery failed: {result.error_message}")

    db.commit()
    db.refresh(outreach)
    return outreach
