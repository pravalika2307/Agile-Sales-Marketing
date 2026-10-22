"""Outbound Retell AI Voice Orchestration Service.

Handles:
- Phone validation and caller ID verification
- Lead/contact dynamic variable mapping into Retell LLM dynamic variables
- Fail-closed safe calling controls (test mode simulation when live calls disabled)
- Safe CallRecord and Outreach state tracking (status='sending' during call in-flight)
- Duplicate dispatch protection and consent/suppression verification
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.services.outreach.service import (
    AlreadySentError,
    CampaignCompletedError,
    CampaignNotFoundError,
    CancelledOutreachError,
    ContactNotFoundError,
    CurrentlySendingError,
    InconsistentEnrollmentError,
    InvalidOutreachTransitionError,
    OutreachNotFoundError,
    OutreachServiceError,
    ProviderDeliveryError,
    SuppressedRecipientError,
)
from app.services.outreach.voice_agent import build_voice_dynamic_variables
from app.services.sms.base import normalize_phone_number
from app.services.voice.retell_client import (
    RetellAPIError,
    RetellAuthenticationError,
    RetellClient,
    RetellConfigurationError,
    RetellError,
    RetellNotFoundError,
    RetellPermissionError,
    RetellRateLimitError,
    RetellTimeoutError,
    get_retell_client,
)

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class VoiceServiceError(OutreachServiceError):
    """Base exception for voice service operations."""
    pass


class InvalidPhoneNumberError(VoiceServiceError):
    """Raised when phone number is missing, unparseable, or not valid E.164."""
    pass


class VoiceConsentSuppressedError(VoiceServiceError):
    """Raised when contact has opted out or is suppressed from voice calls."""
    pass


class VoiceConfigurationError(VoiceServiceError):
    """Raised when Retell credentials, caller ID, or outbound agent ID is unconfigured."""
    pass


class VoiceLiveCallingDisabledError(VoiceServiceError):
    """Raised when live voice calling is attempted while live calling is disabled."""
    pass


# ── Phone & Consent Validation ────────────────────────────────────────────────

def validate_recipient_phone(phone: Optional[str]) -> Tuple[bool, str, Optional[str]]:
    """
    Validates and normalizes phone number to E.164 standard format.
    Returns: (is_valid, formatted_phone, error_message).
    """
    if not phone or not isinstance(phone, str) or not phone.strip():
        return False, "", "Recipient phone number is missing or empty."

    is_valid, formatted, err = normalize_phone_number(phone.strip())
    if not is_valid:
        return False, phone, err or "Invalid phone number format."

    return True, formatted, None


def check_voice_consent(contact_or_lead: Any) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether a prospect is eligible for outbound voice calling.
    Fail-closed: Returns (False, reason) if opted out, unsubscribed, or suppressed.
    """
    if not contact_or_lead:
        return False, "Target contact or lead record is missing."

    lead_status = getattr(contact_or_lead, "lead_status", None)
    if lead_status in ("opted_out", "unsubscribed"):
        return False, f"Contact is suppressed/opted-out (status='{lead_status}')."

    status = getattr(contact_or_lead, "status", None)
    if status in ("opted_out", "rejected"):
        return False, f"Lead is suppressed/opted-out (status='{status}')."

    # Check explicit DNC field if present
    if getattr(contact_or_lead, "do_not_call", False) or getattr(contact_or_lead, "do_not_contact", False):
        return False, "Recipient is marked Do Not Call (DNC)."

    return True, None


# ── Outbound Call Initiation (Safe Mock / Live Provider) ───────────────────────

def initiate_outbound_call(
    from_number: str,
    to_number: str,
    agent_id: str,
    dynamic_variables: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    retell_client: Optional[RetellClient] = None,
    force_mock: bool = False,
) -> Dict[str, Any]:
    """
    Initiates an outbound phone call with strict fail-closed safety controls.

    Guarantees:
    - If force_mock is True OR settings.is_retell_live_calling_allowed is False:
      Operates in safe mock/simulation mode. No external HTTP request or live call is made.
    - Only issues real Retell API calls when live calling is explicitly authorized:
      (RETELL_ENABLED=True, RETELL_ALLOW_LIVE_CALLS=True, valid credentials, valid from_number).
    - Never leaks API keys or secrets in logs or responses.
    """
    is_live_allowed = getattr(settings, "is_retell_live_calling_allowed", False)

    # Test Mode / Safe Mock Simulation
    if force_mock or not is_live_allowed:
        logger.info(
            "Retell live calling is disabled (test mode active). Simulating outbound call from %s to %s with agent %s",
            from_number,
            to_number,
            agent_id,
        )
        simulated_call_id = f"call_mock_{uuid.uuid4().hex[:16]}"
        return {
            "call_id": simulated_call_id,
            "call_status": "registered",
            "agent_id": agent_id,
            "from_number": from_number,
            "to_number": to_number,
            "direction": "outbound",
            "metadata": metadata or {},
            "retell_llm_dynamic_variables": dynamic_variables or {},
            "start_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "simulated": True,
        }

    # Live Calling Execution
    client = retell_client or get_retell_client()
    return client.create_phone_call(
        from_number=from_number,
        to_number=to_number,
        override_agent_id=agent_id,
        dynamic_variables=dynamic_variables,
        metadata=metadata,
    )


# ── High-Level Voice Outreach Dispatch ────────────────────────────────────────

def send_voice_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    retell_client: Optional[RetellClient] = None,
    raise_on_failure: bool = False,
    force_mock: bool = False,
) -> Outreach:
    """
    Dispatches an outbound voice campaign outreach call.

    Guarantees:
    1. Tenant isolation: Strictly enforces organization ownership for Campaign, Contact, and Enrollment.
    2. Idempotency: Prevents double-dials if already sent, sending, or active.
    3. State Integrity: Transitions outreach to 'sending' (never 'sent' before conversation completes).
    4. CallRecord linkage: Creates and links CallRecord to the outreach interaction and campaign.
    5. Fail-Closed: Simulates in test mode unless live calling is explicitly enabled.
    6. Audit Logging: Records OutreachEvent for sending/failed transitions.
    """
    # 1. Fetch outreach with row locking where supported
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

    # 3. Status and duplicate send protection
    if outreach.status == "sent":
        raise AlreadySentError("Voice outreach has already been sent/completed.")
    if outreach.status == "sending":
        raise CurrentlySendingError("Voice outreach call is currently in-flight/sending.")
    if outreach.status == "cancelled":
        raise CancelledOutreachError("Cannot initiate a cancelled voice outreach.")
    if outreach.status == "failed":
        raise InvalidOutreachTransitionError("Cannot directly initiate failed outreach. Use retry.")
    if outreach.status not in ("draft", "scheduled"):
        raise InvalidOutreachTransitionError(
            f"Cannot initiate voice outreach in status '{outreach.status}'. Allowed initial status is 'draft'."
        )

    # 4. Consent and suppression verification
    contact = outreach.contact
    is_consent_ok, consent_reason = check_voice_consent(contact)
    if not is_consent_ok:
        logger.warning(
            "Blocked voice outreach %s: %s (contact_id=%s)",
            outreach.id,
            consent_reason,
            contact.id,
        )
        outreach.status = "cancelled"
        cancel_evt = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="cancelled",
            event_metadata={"reason": consent_reason},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(cancel_evt)
        db.commit()
        db.refresh(outreach)
        raise SuppressedRecipientError(f"Cannot dispatch voice call: {consent_reason}")

    # 5. Destination phone validation
    raw_phone = outreach.recipient if outreach.recipient else (contact.phone if contact else None)
    is_valid_phone, formatted_phone, phone_err = validate_recipient_phone(raw_phone)
    if not is_valid_phone:
        logger.warning("Voice outreach %s failed: %s (raw='%s')", outreach.id, phone_err, raw_phone)
        outreach.status = "failed"
        fail_evt = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="failed",
            event_metadata={"error": phone_err or "Invalid phone number"},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(fail_evt)
        db.commit()
        db.refresh(outreach)
        if raise_on_failure:
            raise InvalidPhoneNumberError(phone_err or "Invalid destination phone number")
        return outreach

    # 6. Resolve Caller ID (from_number) and Outbound Agent ID
    camp = outreach.campaign
    camp_wf = camp.workflow_config if (camp and isinstance(camp.workflow_config, dict)) else {}
    from_number = None
    agent_id = None

    # Check workflow nodes for custom voice config
    for n in camp_wf.get("nodes", []):
        if isinstance(n, dict) and n.get("type") == "voice":
            c = n.get("config", {}) or {}
            if c.get("from_number"):
                from_number = str(c["from_number"]).strip()
            if c.get("agent_id"):
                agent_id = str(c["agent_id"]).strip()
            break

    from_number = from_number or getattr(settings, "RETELL_FROM_NUMBER", None)
    agent_id = agent_id or getattr(settings, "RETELL_AGENT_ID", None)

    if not from_number:
        err_msg = "Retell outbound from_number (caller ID) is not configured in settings or campaign workflow."
        logger.error("Voice outreach %s failed: %s", outreach.id, err_msg)
        outreach.status = "failed"
        db.add(
            OutreachEvent(
                organization_id=org_id,
                outreach_id=outreach.id,
                event_type="failed",
                event_metadata={"error": err_msg},
                occurred_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.refresh(outreach)
        if raise_on_failure:
            raise VoiceConfigurationError(err_msg)
        return outreach

    if not agent_id:
        err_msg = "Retell outbound agent_id is not configured in settings or campaign workflow."
        logger.error("Voice outreach %s failed: %s", outreach.id, err_msg)
        outreach.status = "failed"
        db.add(
            OutreachEvent(
                organization_id=org_id,
                outreach_id=outreach.id,
                event_type="failed",
                event_metadata={"error": err_msg},
                occurred_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.refresh(outreach)
        if raise_on_failure:
            raise VoiceConfigurationError(err_msg)
        return outreach

    # 7. Check if an active call record already exists for this outreach
    if outreach.call_record_id:
        existing_call = db.get(CallRecord, outreach.call_record_id)
        if existing_call and existing_call.call_status in ("registered", "in_progress", "ended", "analyzed"):
            logger.info("Call already active for outreach %s (call_id=%s)", outreach.id, existing_call.call_id)
            return outreach

    # 8. Build dynamic variables and metadata
    company = contact.company if getattr(contact, "company", None) else (
        db.query(Company).filter(Company.id == contact.company_id).first()
        if contact.company_id else None
    )
    matching_lead = (
        db.query(Lead)
        .filter(Lead.organization_id == org_id, Lead.contact_id == contact.id)
        .first()
    )
    if not matching_lead and contact.email:
        matching_lead = (
            db.query(Lead)
            .filter(Lead.organization_id == org_id, Lead.email == contact.email)
            .first()
        )

    dynamic_vars = build_voice_dynamic_variables(
        contact=contact,
        company=company,
        campaign=camp,
        organization=camp.organization,
        lead=matching_lead,
    )

    metadata = {
        "organization_id": str(org_id),
        "campaign_id": str(camp.id),
        "contact_id": str(contact.id),
        "campaign_contact_id": str(outreach.campaign_contact_id) if outreach.campaign_contact_id else None,
        "outreach_id": str(outreach.id),
    }

    # 9. Durable persistence: Create CallRecord and transition outreach to 'sending'
    # State invariant: status='sending' indicates in-flight call; not mistaken for completed conversation
    outreach.status = "sending"
    outreach.provider = "retell"
    outreach.recipient = formatted_phone

    pending_call_id = f"pending_{uuid.uuid4().hex[:12]}"
    call_record = CallRecord(
        organization_id=org_id,
        campaign_id=camp.id,
        contact_id=contact.id,
        lead_id=matching_lead.id if matching_lead else None,
        call_id=pending_call_id,
        agent_id=agent_id,
        direction="outbound",
        call_status="registered",
        caller_phone=from_number,
        to_phone=formatted_phone,
        collected_variables=dynamic_vars,
        metadata_json=metadata,
        followup_status="none",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call_record)
    db.flush()

    outreach.call_record_id = call_record.id
    sending_evt = OutreachEvent(
        organization_id=org_id,
        outreach_id=outreach.id,
        event_type="sending",
        event_metadata={
            "agent_id": agent_id,
            "caller_phone": from_number,
            "to_phone": formatted_phone,
        },
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(sending_evt)
    db.commit()

    # 10. Dispatch call to Retell (mock or live)
    try:
        call_resp = initiate_outbound_call(
            from_number=from_number,
            to_number=formatted_phone,
            agent_id=agent_id,
            dynamic_variables=dynamic_vars,
            metadata=metadata,
            retell_client=retell_client,
            force_mock=force_mock,
        )

        accepted_call_id = str(call_resp.get("call_id") or "")
        if not accepted_call_id:
            raise RetellAPIError(500, "Retell API response did not contain a call_id.")

        call_record.call_id = accepted_call_id
        call_record.call_status = str(call_resp.get("call_status") or "registered")
        outreach.provider_message_id = accepted_call_id
        # State: outreach remains 'sending' until call is analyzed / ended
        db.commit()
        db.refresh(outreach)
        logger.info(
            "Voice call initiated successfully for outreach %s: call_id=%s, status=%s",
            outreach.id,
            accepted_call_id,
            call_record.call_status,
        )
        return outreach

    except Exception as exc:
        raw_err = str(exc)
        api_key = getattr(settings, "RETELL_API_KEY", None)
        sanitized_err = raw_err.replace(api_key, "********") if api_key and api_key in raw_err else raw_err
        logger.error("Failed to initiate Retell call for outreach %s: %s", outreach.id, sanitized_err)

        outreach.status = "failed"
        call_record.call_status = "failed"
        call_record.disconnection_reason = sanitized_err[:100]

        fail_evt = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="failed",
            event_metadata={"error": sanitized_err},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(fail_evt)
        db.commit()
        db.refresh(outreach)

        if raise_on_failure:
            raise ProviderDeliveryError(f"Retell call initiation failed: {sanitized_err}") from exc
        return outreach
