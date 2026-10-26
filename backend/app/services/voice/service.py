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
    auto_complete_mock: bool = False,
    mock_outcome: str = "INTERESTED",
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

        if auto_complete_mock and bool(call_resp.get("simulated")):
            complete_simulated_voice_call(
                db=db,
                org_id=org_id,
                outreach_id=outreach.id,
                outcome=mock_outcome,
            )
            db.refresh(outreach)

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


# ── Deterministic Mock Call Completion ────────────────────────────────────────

def complete_simulated_voice_call(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: Optional[uuid.UUID] = None,
    call_id: Optional[str] = None,
    outcome: str = "INTERESTED",
    meeting_requested: bool = False,
    callback_requested: bool = False,
    qualification_score: int = 85,
    call_summary: Optional[str] = None,
    disconnection_reason: Optional[str] = None,
    email_provider: Optional[Any] = None,
):
    """
    Deterministically completes a simulated/test outbound Retell voice call without
    initiating external Retell or email provider HTTP requests.

    Guarantees:
    1. Tenant isolation: Strictly validates Organization scope.
    2. Simulated Safety: Rejects execution if targeted call is a live Retell call.
    3. Idempotency: Duplicate completion triggers return duplicate=True without repeating
       email follow-ups or regressing states.
    4. Terminal State: Transitions voice outreach from 'sending' to terminal 'sent' or 'failed'.
    5. Follow-Up Dispatch: For positive outcomes, triggers safe Step 2 email follow-up
       via MockEmailProvider with booking URL, advancing CampaignContact to Step 2.
    """
    from app.schemas.voice import SimulateMockCallCompletionResponse
    from app.services.outreach.base import MockEmailProvider
    from app.services.outreach.voice_followup import VoiceFollowUpService

    outreach: Optional[Outreach] = None
    call_record: Optional[CallRecord] = None

    if outreach_id:
        outreach = (
            db.query(Outreach)
            .filter(Outreach.id == outreach_id, Outreach.organization_id == org_id)
            .first()
        )
        if not outreach:
            raise OutreachNotFoundError(f"Outreach '{outreach_id}' not found.")
        if outreach.call_record_id:
            call_record = db.get(CallRecord, outreach.call_record_id)
        if not call_record and outreach.provider_message_id:
            call_record = (
                db.query(CallRecord)
                .filter(
                    CallRecord.call_id == outreach.provider_message_id,
                    CallRecord.organization_id == org_id,
                )
                .first()
            )
    elif call_id:
        call_record = (
            db.query(CallRecord)
            .filter(
                CallRecord.call_id == call_id,
                CallRecord.organization_id == org_id,
            )
            .first()
        )
        if not call_record:
            raise VoiceServiceError(f"Call record '{call_id}' not found.")
        outreach = (
            db.query(Outreach)
            .filter(
                Outreach.call_record_id == call_record.id,
                Outreach.organization_id == org_id,
            )
            .first()
        )
        if not outreach and call_record.call_id:
            outreach = (
                db.query(Outreach)
                .filter(
                    Outreach.provider_message_id == call_record.call_id,
                    Outreach.organization_id == org_id,
                )
                .first()
            )
    else:
        raise VoiceServiceError("Either outreach_id or call_id must be provided.")

    target_call_id = (
        call_record.call_id
        if call_record
        else (outreach.provider_message_id if outreach else None)
    )
    if not target_call_id:
        target_call_id = f"call_mock_{uuid.uuid4().hex[:16]}"
        if call_record:
            call_record.call_id = target_call_id
        if outreach:
            outreach.provider_message_id = target_call_id
        db.commit()

    # Safety Guard: Ensure mock simulation call
    is_live_allowed = getattr(settings, "is_retell_live_calling_allowed", False)
    is_mock = (
        target_call_id.startswith("call_mock_")
        or (call_record and isinstance(call_record.metadata_json, dict) and call_record.metadata_json.get("simulated"))
        or (outreach and outreach.provider == "mock")
        or not is_live_allowed
    )
    if not is_mock and is_live_allowed:
        raise VoiceServiceError(
            "Cannot complete non-simulated call via mock completion handler. "
            "Call must be simulated with prefix 'call_mock_' or have simulated=True."
        )

    norm_outcome = (outcome or "INTERESTED").strip().upper()

    # Idempotency Check: Already in terminal state with processed follow-up
    if (
        call_record
        and call_record.call_status == "analyzed"
        and outreach
        and outreach.status in ("sent", "failed")
        and call_record.followup_status in ("sent", "skipped")
    ):
        logger.info(
            "Deterministic mock completion idempotent duplicate skipped for call_id=%s, outreach_id=%s",
            target_call_id,
            outreach.id if outreach else None,
        )
        return SimulateMockCallCompletionResponse(
            status="success",
            call_id=target_call_id,
            outreach_id=str(outreach.id) if outreach else None,
            call_status=call_record.call_status,
            outreach_status=outreach.status if outreach else "sent",
            call_outcome=call_record.call_outcome or norm_outcome,
            simulated=True,
            duplicate=True,
            followup_email_created=bool(call_record.followup_email_id),
            followup_email_id=str(call_record.followup_email_id) if call_record.followup_email_id else None,
            followup_status=call_record.followup_status,
            followup_reason=call_record.followup_reason or "Simulated call completion already processed (idempotent duplicate skipped)",
            message="Simulated call completion already processed (idempotent duplicate skipped).",
        )

    # Resolve contact and company information for variables
    contact = (
        outreach.contact
        if outreach and outreach.contact
        else (db.get(Contact, call_record.contact_id) if call_record and call_record.contact_id else None)
    )
    company = contact.company if contact and getattr(contact, "company", None) else None
    lead_name = (
        f"{contact.first_name} {contact.last_name}".strip()
        if contact and (contact.first_name or contact.last_name)
        else None
    )
    lead_email = contact.email if contact else None
    company_name = company.name if company else None

    # Construct synthetic Retell call_analyzed payload
    synthetic_payload: Dict[str, Any] = {
        "event": "call_analyzed",
        "call": {
            "call_id": target_call_id,
            "agent_id": call_record.agent_id if call_record else (getattr(settings, "RETELL_AGENT_ID", None) or "agent_mock_test"),
            "direction": "outbound",
            "call_status": "analyzed",
            "from_number": call_record.caller_phone if call_record else (getattr(settings, "RETELL_FROM_NUMBER", None) or "+18005550199"),
            "to_phone": call_record.to_phone if call_record else (outreach.recipient if outreach else None),
            "duration_ms": 45000,
            "disconnection_reason": disconnection_reason or ("call_completed" if norm_outcome not in ("NO_ANSWER", "UNAVAILABLE") else "no_answer"),
            "transcript": f"Simulated call transcript for prospect. Call completed with outcome {norm_outcome}.",
            "call_analysis": {
                "call_summary": call_summary or f"Simulated outbound call completed with outcome {norm_outcome}.",
                "call_outcome": norm_outcome,
                "custom_analysis_data": {
                    "call_outcome": norm_outcome,
                    "interest_level": "high" if norm_outcome in ("INTERESTED", "QUALIFIED", "MEETING_REQUESTED") else "low",
                    "meeting_requested": meeting_requested or (norm_outcome == "MEETING_REQUESTED"),
                    "callback_requested": callback_requested or (norm_outcome == "CALLBACK_REQUESTED"),
                    "do_not_contact": (norm_outcome == "DO_NOT_CONTACT"),
                    "qualification_score": qualification_score,
                    "lead_full_name": lead_name,
                    "email": lead_email,
                    "company_name": company_name,
                },
            },
            "metadata": {
                "organization_id": str(org_id),
                "outreach_id": str(outreach.id) if outreach else None,
                "campaign_id": str(outreach.campaign_id) if outreach and outreach.campaign_id else (str(call_record.campaign_id) if call_record and call_record.campaign_id else None),
                "contact_id": str(contact.id) if contact else None,
                "campaign_contact_id": str(outreach.campaign_contact_id) if outreach and outreach.campaign_contact_id else None,
                "simulated": True,
            },
        },
    }

    # Execute deterministic follow-up lifecycle with guaranteed MockEmailProvider
    service = VoiceFollowUpService(
        db=db,
        email_provider=email_provider or MockEmailProvider(),
        cooldown_hours=0,
    )
    result = service.process_call_analyzed(
        payload=synthetic_payload,
        org_id_override=org_id,
    )

    if outreach:
        outreach.provider = "mock"
        db.commit()
        db.refresh(outreach)
    if call_record:
        db.refresh(call_record)

    return SimulateMockCallCompletionResponse(
        status=result.get("status", "success"),
        call_id=target_call_id,
        outreach_id=str(outreach.id) if outreach else None,
        call_status=call_record.call_status if call_record else "analyzed",
        outreach_status=outreach.status if outreach else "sent",
        call_outcome=norm_outcome,
        simulated=True,
        duplicate=result.get("duplicate", False),
        followup_email_created=bool(result.get("email_sent")),
        followup_email_id=result.get("followup_email_id"),
        followup_status=result.get("followup_status"),
        followup_reason=result.get("followup_reason"),
        message=f"Simulated voice call completed with outcome '{norm_outcome}'.",
    )
