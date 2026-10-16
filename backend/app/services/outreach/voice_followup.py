"""
Retell Voice Call Follow-Up Service.

Coordinates:
- Retell webhook signature verification (HMAC-SHA256).
- Structured variable extraction & validation from Retell payloads.
- Safe lead/contact resolution without destructive overwrites.
- Deterministic email decision rules engine.
- Safe voice follow-up email template rendering.
- Strict idempotency enforcement using (call_id + followup_type).
- Delivery execution via existing EmailProvider abstraction (Resend/SES/Mock).
- Outreach & OutreachEvent audit logging.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VoiceFollowUpError(Exception):
    """Base exception for voice follow-up operations."""
    pass


class UnresolvedOrganizationError(VoiceFollowUpError):
    """Raised when an incoming voice call cannot be deterministically mapped to a tenant organization."""
    pass


from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.normalization import normalize_email
from app.models.call_record import CallRecord
from app.models.crm import Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization
from app.services.outreach.base import EmailMessage, EmailProvider
from app.services.outreach.providers import get_email_provider


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_DIGITS_REGEX = re.compile(r"\d")


# Supported outcome constants
OUTCOME_INTERESTED = "INTERESTED"
OUTCOME_QUALIFIED = "QUALIFIED"
OUTCOME_MEETING_REQUESTED = "MEETING_REQUESTED"
OUTCOME_CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
OUTCOME_NOT_INTERESTED = "NOT_INTERESTED"
OUTCOME_DO_NOT_CONTACT = "DO_NOT_CONTACT"
OUTCOME_WRONG_PERSON = "WRONG_PERSON"
OUTCOME_UNKNOWN = "UNKNOWN"

# Follow-up type constants
FOLLOWUP_TYPE_INTERESTED = "interested_followup"
FOLLOWUP_TYPE_QUALIFIED = "qualified_followup"
FOLLOWUP_TYPE_MEETING = "meeting_followup"
FOLLOWUP_TYPE_CALLBACK = "callback_followup"
FOLLOWUP_TYPE_NONE = "none"


@dataclass
class ExtractedCallData:
    """Safely normalized call details and structured variables from Retell."""
    call_id: str
    agent_id: str
    direction: str
    call_status: str
    call_outcome: str
    caller_phone: Optional[str]
    to_phone: Optional[str]
    duration_ms: Optional[int]
    disconnection_reason: Optional[str]
    summary: Optional[str]
    transcript: Optional[str]
    # Structured variables
    lead_full_name: Optional[str]
    email: Optional[str]
    phone_number: Optional[str]
    company_name: Optional[str]
    job_title: Optional[str]
    interest_level: Optional[str]
    meeting_requested: bool
    callback_requested: bool
    do_not_contact: bool
    # Source entity identifiers
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    campaign_id: Optional[str] = None
    # Raw dictionaries
    collected_variables: Dict[str, Any] = field(default_factory=dict)
    call_analysis: Dict[str, Any] = field(default_factory=dict)
    metadata_json: Dict[str, Any] = field(default_factory=dict)
    # Timestamps
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    analyzed_at: Optional[datetime] = None


@dataclass
class FollowUpDecision:
    """Outcome of evaluating deterministic email decision rules."""
    should_send_email: bool
    followup_type: str
    reason: str
    recipient_email: Optional[str]
    recipient_name: Optional[str]
    is_missing_email: bool = False


class VoiceFollowUpService:
    """
    Core domain service managing the post-call Retell to Email Follow-Up lifecycle.
    """

    def __init__(
        self,
        db: Session,
        email_provider: Optional[EmailProvider] = None,
        cooldown_hours: Optional[int] = None,
    ) -> None:
        self.db = db
        self.email_provider = email_provider or get_email_provider()
        self.cooldown_hours = (
            cooldown_hours
            if cooldown_hours is not None
            else getattr(settings, "VOICE_FOLLOWUP_COOLDOWN_HOURS", 24)
        )

    # ── Signature Verification ────────────────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(
        raw_body: bytes,
        signature_header: Optional[str],
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verify the Retell AI webhook signature.
        Retell signs payloads using HMAC-SHA256 with the Retell API Key or webhook secret.
        Supports standard Retell format: `v=<timestamp>,d=<digest>` as well as raw hex digest.
        """
        # Build list of candidate secrets to check
        candidate_secrets: List[str] = []
        for s in (secret, settings.RETELL_WEBHOOK_SECRET, settings.RETELL_API_KEY):
            if s and s.strip() and s.strip() not in candidate_secrets:
                candidate_secrets.append(s.strip())

        if not candidate_secrets or not signature_header:
            return False

        sig_header = signature_header.strip()

        # Format 1: `v=<timestamp>,d=<digest>` or `t=<timestamp>,v1=<digest>` or `t=<timestamp>,v=<digest>`
        if "=" in sig_header:
            parts = dict(
                item.strip().split("=", 1)
                for item in sig_header.split(",")
                if "=" in item
            )
            if "d" in parts:
                digest = parts["d"]
                timestamp = parts.get("v") or parts.get("t") or ""
            elif "v1" in parts:
                digest = parts["v1"]
                timestamp = parts.get("t") or parts.get("v") or ""
            elif "v" in parts and "t" in parts:
                digest = parts["v"]
                timestamp = parts["t"]
            else:
                digest = ""
                timestamp = ""

            if not timestamp or not digest:
                return False

            raw_str = raw_body.decode("utf-8", errors="replace")
            content_1 = f"{raw_str}{timestamp}".encode("utf-8")
            content_2 = f"{timestamp}.{raw_str}".encode("utf-8")

            for effective_secret in candidate_secrets:
                secret_bytes = effective_secret.encode("utf-8")
                # Format 1A: Official Retell standard: raw_body + timestamp
                d1 = hmac.new(secret_bytes, content_1, hashlib.sha256).hexdigest()
                if hmac.compare_digest(d1, digest):
                    return True

                # Format 1B: Alternate timestamp.raw_body
                d2 = hmac.new(secret_bytes, content_2, hashlib.sha256).hexdigest()
                if hmac.compare_digest(d2, digest):
                    return True

            return False

        # Format 2: Raw hex digest
        for effective_secret in candidate_secrets:
            secret_bytes = effective_secret.encode("utf-8")
            expected_digest = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected_digest, sig_header):
                return True

        return False

    # ── Data Extraction & Validation ──────────────────────────────────────────

    @staticmethod
    def validate_email(email: Optional[str]) -> Optional[str]:
        """Validate and normalize an email address."""
        if not email or not isinstance(email, str):
            return None
        cleaned = email.strip().lower()
        if EMAIL_REGEX.match(cleaned):
            return cleaned
        return None

    @staticmethod
    def validate_phone(phone: Optional[str]) -> Optional[str]:
        """Validate and clean a phone number."""
        if not phone or not isinstance(phone, str):
            return None
        cleaned = phone.strip()
        digits = PHONE_DIGITS_REGEX.findall(cleaned)
        if len(digits) >= 7:
            return cleaned
        return None

    @classmethod
    def extract_call_data(cls, payload: Dict[str, Any]) -> ExtractedCallData:
        """
        Safely inspect and extract call metadata, analysis, and structured variables
        from a Retell webhook payload. Defensively handles nested 'call' or flat payloads.
        """
        call_dict = payload.get("call") if isinstance(payload.get("call"), dict) else payload

        call_id = str(call_dict.get("call_id") or payload.get("call_id") or "").strip()
        agent_id = str(call_dict.get("agent_id") or payload.get("agent_id") or "").strip()
        direction = str(call_dict.get("direction") or "inbound").lower()
        if direction not in ("inbound", "outbound"):
            direction = "inbound"

        call_status = str(call_dict.get("call_status") or payload.get("event") or "ended").lower()
        caller_phone = call_dict.get("from_number") or call_dict.get("caller_number")
        to_phone = call_dict.get("to_number")
        duration_ms = call_dict.get("duration_ms")
        disconnection_reason = call_dict.get("disconnection_reason")
        transcript = call_dict.get("transcript")

        call_analysis = call_dict.get("call_analysis") or {}
        if not isinstance(call_analysis, dict):
            call_analysis = {}

        summary = (
            call_analysis.get("call_summary")
            or call_dict.get("summary")
            or call_dict.get("call_summary")
        )

        collected_vars = call_dict.get("collected_dynamic_variables") or {}
        if not isinstance(collected_vars, dict):
            collected_vars = {}

        custom_analysis = call_analysis.get("custom_analysis_data") or {}
        if not isinstance(custom_analysis, dict):
            custom_analysis = {}

        metadata = call_dict.get("metadata") or payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        # Merge variable lookup sources (custom_analysis takes precedence, then collected_vars, then metadata)
        def lookup(*keys: str) -> Optional[Any]:
            for k in keys:
                if k in custom_analysis and custom_analysis[k] is not None:
                    return custom_analysis[k]
                if k in collected_vars and collected_vars[k] is not None:
                    return collected_vars[k]
                if k in metadata and metadata[k] is not None:
                    return metadata[k]
            return None

        # 1. lead_full_name
        raw_name = lookup("lead_full_name", "caller_name", "name", "full_name")
        first = lookup("lead_first_name", "first_name")
        last = lookup("lead_last_name", "last_name")
        if not raw_name and (first or last):
            raw_name = f"{first or ''} {last or ''}".strip()
        lead_full_name = str(raw_name).strip() if raw_name else None

        # 2. email
        raw_email = lookup("email", "caller_email", "lead_email", "customer_email", "prospect_email", "contact_email")
        validated_email = cls.validate_email(str(raw_email)) if raw_email else None

        # 3. phone_number
        raw_phone = lookup("phone_number", "phone", "lead_phone", "caller_phone") or caller_phone
        validated_phone = cls.validate_phone(str(raw_phone)) if raw_phone else None

        # 4. company_name
        raw_company = lookup("company_name", "company", "caller_company", "prospect_company_name")
        company_name = str(raw_company).strip() if raw_company else None

        # 5. job_title
        raw_job = lookup("job_title", "title", "prospect_job_title")
        job_title = str(raw_job).strip() if raw_job else None

        # 6. Raw inputs for outcome and interest
        raw_interest = lookup("interest_level", "interest")
        raw_outcome = lookup("call_outcome", "outcome") or call_analysis.get("call_outcome")
        raw_qual_outcome = lookup("qualification_outcome")
        raw_next_step = lookup("next_step_action", "requested_followup")

        interest_level = str(raw_interest).strip().lower() if raw_interest else None

        # Deterministic mapping: qualification_outcome
        if raw_qual_outcome:
            qual_str = str(raw_qual_outcome).strip().lower()
            if qual_str == "interested":
                interest_level = interest_level or "high"
                if not raw_outcome:
                    raw_outcome = OUTCOME_INTERESTED
            elif qual_str == "somewhat_interested":
                interest_level = interest_level or "medium"
                if not raw_outcome:
                    raw_outcome = OUTCOME_INTERESTED
            elif qual_str == "qualified":
                interest_level = interest_level or "high"
                if not raw_outcome:
                    raw_outcome = OUTCOME_QUALIFIED
            elif qual_str == "callback_requested":
                if not raw_outcome:
                    raw_outcome = OUTCOME_CALLBACK_REQUESTED
            elif qual_str in ("not_interested", "unqualified"):
                if not raw_outcome:
                    raw_outcome = OUTCOME_NOT_INTERESTED
            elif qual_str == "wrong_person":
                if not raw_outcome:
                    raw_outcome = OUTCOME_WRONG_PERSON
            elif qual_str == "do_not_call":
                if not raw_outcome:
                    raw_outcome = OUTCOME_DO_NOT_CONTACT
            elif qual_str == "unavailable":
                if not raw_outcome:
                    raw_outcome = "UNAVAILABLE"

        # Deterministic mapping: next_step_action / requested_followup
        next_step_str = str(raw_next_step).strip().lower() if raw_next_step else ""
        if next_step_str:
            if any(token in next_step_str for token in ("send_info_email", "info_email", "send_email", "send pricing", "send info")):
                # Prospect verbally requested info/follow-up email; if not negative, eligible for interested follow-up
                if raw_outcome not in (OUTCOME_DO_NOT_CONTACT, OUTCOME_WRONG_PERSON, OUTCOME_NOT_INTERESTED):
                    raw_outcome = raw_outcome or OUTCOME_INTERESTED
                    interest_level = interest_level or "high"
            elif any(token in next_step_str for token in ("demo", "book_demo", "schedule_demo", "meeting")):
                raw_outcome = OUTCOME_MEETING_REQUESTED
            elif "callback" in next_step_str:
                raw_outcome = OUTCOME_CALLBACK_REQUESTED
            elif any(token in next_step_str for token in ("dnc", "do_not_call", "mark_dnc")):
                raw_outcome = OUTCOME_DO_NOT_CONTACT

        # 7. Normalized call_outcome
        normalized_outcome = cls._normalize_outcome(raw_outcome, interest_level)

        # 8. meeting_requested
        raw_meeting = lookup("meeting_requested", "demo_requested", "meeting_scheduled")
        meeting_requested = cls._to_bool(raw_meeting) or any(
            t in str(raw_outcome).lower() or t in next_step_str for t in ("demo", "meeting")
        )

        # 9. callback_requested
        raw_callback = lookup("callback_requested", "callback")
        callback_requested = cls._to_bool(raw_callback) or ("callback" in str(raw_outcome).lower() or "callback" in next_step_str)

        # 10. do_not_contact
        raw_dnc = lookup("do_not_contact", "do_not_call", "dnc")
        do_not_contact = cls._to_bool(raw_dnc) or (normalized_outcome == OUTCOME_DO_NOT_CONTACT) or any(
            t in next_step_str for t in ("dnc", "do_not_call")
        )

        # Entity Identifiers
        raw_lead_id = lookup("lead_id")
        lead_id = str(raw_lead_id).strip() if raw_lead_id else None

        raw_contact_id = lookup("contact_id")
        contact_id = str(raw_contact_id).strip() if raw_contact_id else None

        raw_campaign_id = lookup("campaign_id")
        campaign_id = str(raw_campaign_id).strip() if raw_campaign_id else None

        # Parse timestamps safely
        started_at = cls._parse_timestamp(call_dict.get("start_timestamp"))
        ended_at = cls._parse_timestamp(call_dict.get("end_timestamp"))
        analyzed_at = datetime.now(timezone.utc)

        return ExtractedCallData(
            call_id=call_id,
            agent_id=agent_id,
            direction=direction,
            call_status=call_status,
            call_outcome=normalized_outcome,
            caller_phone=validated_phone or caller_phone,
            to_phone=to_phone,
            duration_ms=duration_ms,
            disconnection_reason=disconnection_reason,
            summary=summary,
            transcript=transcript,
            lead_full_name=lead_full_name,
            email=validated_email,
            phone_number=validated_phone,
            company_name=company_name,
            job_title=job_title,
            interest_level=interest_level,
            meeting_requested=meeting_requested,
            callback_requested=callback_requested,
            do_not_contact=do_not_contact,
            lead_id=lead_id,
            contact_id=contact_id,
            campaign_id=campaign_id,
            collected_variables=collected_vars,
            call_analysis=call_analysis,
            metadata_json=metadata,
            started_at=started_at,
            ended_at=ended_at,
            analyzed_at=analyzed_at,
        )

    @staticmethod
    def _to_bool(val: Any) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes", "y")
        return False

    @staticmethod
    def _normalize_outcome(raw: Any, interest_level: Optional[str]) -> str:
        text = str(raw or "").strip().upper()
        if not text:
            if interest_level in ("high", "interested", "medium"):
                return OUTCOME_INTERESTED
            return OUTCOME_UNKNOWN

        if "DO_NOT" in text or "DNC" in text or "UNSUBSCRIBE" in text:
            return OUTCOME_DO_NOT_CONTACT
        if "WRONG" in text:
            return OUTCOME_WRONG_PERSON
        if "NOT_INTERESTED" in text or "UNQUALIFIED" in text:
            return OUTCOME_NOT_INTERESTED
        if "MEETING" in text or "DEMO" in text:
            return OUTCOME_MEETING_REQUESTED
        if "CALLBACK" in text:
            return OUTCOME_CALLBACK_REQUESTED
        if "QUALIFIED" in text:
            return OUTCOME_QUALIFIED
        if "INTERESTED" in text or "SALES_INQUIRY" in text or "PRICING_INQUIRY" in text:
            return OUTCOME_INTERESTED

        return text

    @staticmethod
    def _parse_timestamp(val: Any) -> Optional[datetime]:
        if not val:
            return None
        if isinstance(val, (int, float)):
            # Retell sends epoch ms
            ts = val / 1000.0 if val > 1e11 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    # ── Deterministic Follow-Up Rules & Name Resolution ───────────────────────

    @staticmethod
    def is_reliable_name(name: Optional[str]) -> bool:
        """
        Check if a candidate name is reliable and not missing, empty, or a generic placeholder.
        """
        if not name or not isinstance(name, str):
            return False
        cleaned = name.strip()
        if not cleaned:
            return False
        unreliable_tokens = {
            "there",
            "unknown",
            "n/a",
            "na",
            "none",
            "null",
            "undefined",
            "prospect",
            "lead",
            "prospect lead",
            "customer",
            "caller",
        }
        if cleaned.lower() in unreliable_tokens:
            return False
        first_word = cleaned.split()[0].lower()
        if first_word in unreliable_tokens:
            return False
        return True

    @classmethod
    def resolve_reliable_recipient_name(
        cls,
        data: ExtractedCallData,
        contact: Optional[Contact] = None,
        lead: Optional[Lead] = None,
    ) -> Optional[str]:
        """
        Resolves the recipient name following strict precedence:
        1. Valid, reliable name provided by webhook (data.lead_full_name).
        2. First name from existing linked Contact within organization.
        3. First name from existing linked Lead within organization.
        4. None if no reliable name is available. Never guesses from email.
        """
        # 1. Preserve a valid name provided by the webhook when reliable
        if cls.is_reliable_name(data.lead_full_name):
            return data.lead_full_name.strip()

        # 2. Try Contact within the correct organization
        if contact and cls.is_reliable_name(contact.first_name):
            first_name = contact.first_name.strip().split()[0].capitalize()
            last_name = (
                contact.last_name.strip()
                if contact.last_name and cls.is_reliable_name(contact.last_name)
                else ""
            )
            return f"{first_name} {last_name}".strip()

        # 3. Try Lead within the same organization
        if lead and cls.is_reliable_name(lead.first_name):
            first_name = lead.first_name.strip().split()[0].capitalize()
            last_name = (
                lead.last_name.strip()
                if lead.last_name and cls.is_reliable_name(lead.last_name)
                else ""
            )
            return f"{first_name} {last_name}".strip()

        # 4. Do not guess from email or other fields
        return None

    def check_recipient_cooldown(
        self,
        org_id: uuid.UUID,
        recipient_email: Optional[str],
        cooldown_hours: Optional[int] = None,
        current_call_record_id: Optional[uuid.UUID] = None,
    ) -> Optional[Outreach]:
        """
        Checks if a successful voice follow-up outreach was sent to this recipient
        within the cooldown period in the same organization.

        Requirements:
        - Scoped strictly to the same organization and normalized recipient email.
        - Only checks successful voice follow-up outreach records (status='sent' and call_record_id is not None).
        - Does NOT treat unrelated campaign emails as voice follow-ups.
        - Fails safely on database errors to prevent uncontrolled duplicate sends.
        """
        if not recipient_email or not org_id:
            return None

        norm_email = normalize_email(recipient_email)
        if not norm_email:
            return None

        effective_hours = (
            cooldown_hours
            if cooldown_hours is not None
            else getattr(self, "cooldown_hours", 24)
        )
        if effective_hours is None or effective_hours <= 0:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(hours=effective_hours)

        try:
            stmt = (
                select(Outreach)
                .where(
                    Outreach.organization_id == org_id,
                    func.lower(Outreach.recipient) == norm_email,
                    Outreach.channel == "email",
                    Outreach.status == "sent",
                    Outreach.call_record_id.isnot(None),
                    func.coalesce(Outreach.sent_at, Outreach.created_at) >= cutoff,
                )
            )
            if current_call_record_id is not None:
                stmt = stmt.where(Outreach.call_record_id != current_call_record_id)

            stmt = stmt.order_by(
                func.coalesce(Outreach.sent_at, Outreach.created_at).desc()
            ).limit(1)

            recent_outreach = self.db.execute(stmt).scalar_one_or_none()
            return recent_outreach
        except Exception as exc:
            logger.error(
                "Database error while querying voice follow-up cooldown for recipient %s in org %s: %s",
                norm_email,
                org_id,
                exc,
                exc_info=True,
            )
            # Re-raise to ensure query failures do not silently allow duplicate email sends
            raise VoiceFollowUpError(
                f"Failed to check recipient cooldown safely: {exc}"
            ) from exc

    @classmethod
    def evaluate_followup_decision(
        cls,
        data: ExtractedCallData,
        resolved_email: Optional[str] = None,
        is_missing_email: bool = False,
        resolved_name: Optional[str] = None,
    ) -> FollowUpDecision:
        """
        Evaluate deterministic follow-up rules based on structured call analysis.
        Rules:
        1. DO_NOT_CONTACT / do_not_contact=True → no email
        2. WRONG_PERSON → no email
        3. NOT_INTERESTED → no email
        4. UNKNOWN / OTHER → no automated email
        5. Missing or invalid email (or is_missing_email=True) → no email
        6. MEETING_REQUESTED / meeting_requested=True → send meeting follow-up email
        7. CALLBACK_REQUESTED / callback_requested=True → send callback confirmation email
        8. INTERESTED → send follow-up email
        9. QUALIFIED → send follow-up email
        """
        effective_email = resolved_email if resolved_email is not None else data.email
        effective_name = resolved_name if resolved_name is not None else data.lead_full_name
        has_missing_email = is_missing_email or not effective_email

        # 1. Do Not Contact
        if data.do_not_contact or data.call_outcome == OUTCOME_DO_NOT_CONTACT:
            return FollowUpDecision(
                should_send_email=False,
                followup_type=FOLLOWUP_TYPE_NONE,
                reason="Do Not Contact requested or indicated",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # 2. Wrong Person
        if data.call_outcome == OUTCOME_WRONG_PERSON:
            return FollowUpDecision(
                should_send_email=False,
                followup_type=FOLLOWUP_TYPE_NONE,
                reason="Wrong person reached",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # 3. Not Interested
        if data.call_outcome == OUTCOME_NOT_INTERESTED:
            return FollowUpDecision(
                should_send_email=False,
                followup_type=FOLLOWUP_TYPE_NONE,
                reason="Prospect is not interested",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # 4. Unknown outcome
        if data.call_outcome in (OUTCOME_UNKNOWN, "OTHER", "UNAVAILABLE"):
            if not data.meeting_requested and not data.callback_requested:
                return FollowUpDecision(
                    should_send_email=False,
                    followup_type=FOLLOWUP_TYPE_NONE,
                    reason=f"Call outcome '{data.call_outcome}' does not trigger automated email",
                    recipient_email=effective_email,
                    recipient_name=effective_name,
                    is_missing_email=False,
                )

        # 5. Check Email Validity (Authoritative Check)
        if has_missing_email:
            return FollowUpDecision(
                should_send_email=False,
                followup_type=FOLLOWUP_TYPE_NONE,
                reason="missing_email: Missing or invalid recipient email",
                recipient_email=None,
                recipient_name=effective_name,
                is_missing_email=True,
            )

        # 6. Meeting Requested
        if data.meeting_requested or data.call_outcome == OUTCOME_MEETING_REQUESTED:
            return FollowUpDecision(
                should_send_email=True,
                followup_type=FOLLOWUP_TYPE_MEETING,
                reason="Prospect requested meeting/demo",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # 7. Callback Requested
        if data.callback_requested or data.call_outcome == OUTCOME_CALLBACK_REQUESTED:
            return FollowUpDecision(
                should_send_email=True,
                followup_type=FOLLOWUP_TYPE_CALLBACK,
                reason="Prospect requested callback",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # 8. Qualified
        if data.call_outcome == OUTCOME_QUALIFIED:
            return FollowUpDecision(
                should_send_email=True,
                followup_type=FOLLOWUP_TYPE_QUALIFIED,
                reason="Prospect qualified for sales outreach",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # 9. Interested
        if data.call_outcome == OUTCOME_INTERESTED or data.interest_level in ("high", "medium"):
            return FollowUpDecision(
                should_send_email=True,
                followup_type=FOLLOWUP_TYPE_INTERESTED,
                reason="Prospect showed interest during call",
                recipient_email=effective_email,
                recipient_name=effective_name,
                is_missing_email=False,
            )

        # Fallback default: Do not send
        return FollowUpDecision(
            should_send_email=False,
            followup_type=FOLLOWUP_TYPE_NONE,
            reason=f"No automated email rule configured for outcome: {data.call_outcome}",
            recipient_email=effective_email,
            recipient_name=effective_name,
            is_missing_email=False,
        )

    # ── Safe Email Content Generation ─────────────────────────────────────────

    @classmethod
    def render_email_content(
        cls,
        decision: FollowUpDecision,
        data: ExtractedCallData,
        organization: Optional[Organization] = None,
        contact: Optional[Contact] = None,
        lead: Optional[Lead] = None,
    ) -> Tuple[str, str]:
        """
        Renders safe, factual email subject and body for voice follow-up.
        Strict rule: Do not invent pricing, guarantees, fake meeting slots, or false commitments.
        If no reliable recipient name is available, falls back to:
        - Subject: "Great speaking with you earlier"
        - Greeting: "Hello,"
        Never produces: "Great speaking with you, there"
        """
        # Determine recipient first name
        first_name = None
        raw_name = (
            decision.recipient_name
            or (contact.first_name if contact else None)
            or (lead.first_name if lead else None)
        )
        if cls.is_reliable_name(raw_name):
            first_name = raw_name.strip().split()[0].capitalize()
            if not cls.is_reliable_name(first_name):
                first_name = None

        sender_name = settings.EMAIL_FROM_NAME or "Agile Sales & Marketing Team"
        sender_company = (
            organization.name
            if organization and organization.name
            else "Agile Sales & Marketing"
        )

        has_name = bool(first_name)

        if decision.followup_type in (FOLLOWUP_TYPE_INTERESTED, FOLLOWUP_TYPE_QUALIFIED):
            subject = f"Great speaking with you, {first_name}" if has_name else "Great speaking with you earlier"
            greeting = f"Hi {first_name}," if has_name else "Hello,"
            body = (
                f"{greeting}\n\n"
                f"Thanks for speaking with us today.\n\n"
                f"Based on our conversation, we'd be happy to continue the discussion and help with the next steps.\n\n"
                f"Best,\n"
                f"{sender_name}\n"
                f"{sender_company}"
            )
            return subject, body

        if decision.followup_type == FOLLOWUP_TYPE_MEETING:
            subject = f"Great speaking with you, {first_name}" if has_name else "Great speaking with you earlier"
            greeting = f"Hi {first_name}," if has_name else "Hello,"
            body = (
                f"{greeting}\n\n"
                f"Thanks for speaking with us today.\n\n"
                f"We look forward to connecting for our upcoming meeting. "
                f"Our team will follow up shortly with scheduling details and the next steps.\n\n"
                f"Best,\n"
                f"{sender_name}\n"
                f"{sender_company}"
            )
            return subject, body

        if decision.followup_type == FOLLOWUP_TYPE_CALLBACK:
            subject = f"Callback Request Confirmation, {first_name}" if has_name else "Great speaking with you earlier"
            greeting = f"Hi {first_name}," if has_name else "Hello,"
            body = (
                f"{greeting}\n\n"
                f"Thanks for speaking with us today.\n\n"
                f"We have noted your request for a callback and our team will reach back out to you shortly.\n\n"
                f"Best,\n"
                f"{sender_name}\n"
                f"{sender_company}"
            )
            return subject, body

        # Default fallback
        subject = f"Follow-up regarding our call, {first_name}" if has_name else "Great speaking with you earlier"
        greeting = f"Hi {first_name}," if has_name else "Hello,"
        body = (
            f"{greeting}\n\n"
            f"Thank you for your time on our call today.\n\n"
            f"Best,\n"
            f"{sender_name}\n"
            f"{sender_company}"
        )
        return subject, body

    # ── Database Resolution & Non-Destructive Ingestion ───────────────────────

    def resolve_organization(
        self,
        data: ExtractedCallData,
        org_id_override: Optional[uuid.UUID] = None,
    ) -> Optional[Organization]:
        """
        Resolve tenant Organization safely and deterministically.
        Strictly requires trusted metadata, explicit overrides, or unambiguous entity mappings.
        Never falls back to arbitrary organization selections (LIMIT 1).
        """
        if org_id_override:
            return self.db.get(Organization, org_id_override)

        # 1. Direct metadata / collected variables organization_id check
        meta_org_id = (
            data.metadata_json.get("organization_id")
            or data.collected_variables.get("organization_id")
        )
        if meta_org_id:
            try:
                parsed_id = uuid.UUID(str(meta_org_id))
                org = self.db.get(Organization, parsed_id)
                if org:
                    return org
            except (ValueError, TypeError):
                pass

        # 2. Existing CallRecord check (idempotent matching of prior call events)
        if data.call_id:
            existing_call = self.db.execute(
                select(CallRecord).where(CallRecord.call_id == data.call_id)
            ).scalar_one_or_none()
            if existing_call:
                org = self.db.get(Organization, existing_call.organization_id)
                if org:
                    return org

        # 3. Referenced Campaign lookup
        target_campaign_id = (
            data.campaign_id
            or data.metadata_json.get("campaign_id")
            or data.collected_variables.get("campaign_id")
        )
        if target_campaign_id:
            try:
                camp_uuid = uuid.UUID(str(target_campaign_id))
                from app.models.campaign import Campaign
                campaign = self.db.get(Campaign, camp_uuid)
                if campaign:
                    org = self.db.get(Organization, campaign.organization_id)
                    if org:
                        return org
            except (ValueError, TypeError):
                pass

        # 4. Referenced Lead lookup
        target_lead_id = (
            data.lead_id
            or data.metadata_json.get("lead_id")
            or data.collected_variables.get("lead_id")
        )
        if target_lead_id:
            try:
                lead_uuid = uuid.UUID(str(target_lead_id))
                lead = self.db.get(Lead, lead_uuid)
                if lead:
                    org = self.db.get(Organization, lead.organization_id)
                    if org:
                        return org
            except (ValueError, TypeError):
                pass

        # 5. Referenced Contact lookup
        target_contact_id = (
            data.contact_id
            or data.metadata_json.get("contact_id")
            or data.collected_variables.get("contact_id")
        )
        if target_contact_id:
            try:
                contact_uuid = uuid.UUID(str(target_contact_id))
                contact = self.db.get(Contact, contact_uuid)
                if contact:
                    org = self.db.get(Organization, contact.organization_id)
                    if org:
                        return org
            except (ValueError, TypeError):
                pass

        # If not deterministically resolvable, return None (NO LIMIT 1 FALLBACK!)
        return None

    def sync_lead_and_contact(
        self,
        org_id: uuid.UUID,
        data: ExtractedCallData,
    ) -> Tuple[Optional[Contact], Optional[Lead]]:
        """
        Synchronize caller information with Contact and Lead records.
        Strict rule: Do not overwrite existing valid data blindly.
        Uses normalized email addresses and organization scoping to prevent duplicates.
        """
        contact: Optional[Contact] = None
        lead: Optional[Lead] = None
        norm_email = normalize_email(data.email)

        # 1. Contact Lookup / Non-destructive update
        if norm_email:
            contact = self.db.execute(
                select(Contact)
                .where(
                    Contact.organization_id == org_id,
                    func.lower(Contact.email) == norm_email,
                )
                .limit(1)
            ).scalar_one_or_none()

        if not contact and data.phone_number:
            contact = self.db.execute(
                select(Contact)
                .where(Contact.organization_id == org_id, Contact.phone == data.phone_number)
                .limit(1)
            ).scalar_one_or_none()

        if contact:
            # Non-destructive update only
            if data.phone_number and not contact.phone:
                contact.phone = data.phone_number
            if data.job_title and not contact.job_title:
                contact.job_title = data.job_title
        elif norm_email:
            # Create minimal contact if email is present
            first_name = "Prospect"
            last_name = "Lead"
            if data.lead_full_name:
                parts = data.lead_full_name.strip().split(maxsplit=1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""

            contact = Contact(
                organization_id=org_id,
                email=norm_email,
                first_name=first_name,
                last_name=last_name,
                phone=data.phone_number,
                job_title=data.job_title,
                lead_status="qualified" if data.call_outcome == OUTCOME_QUALIFIED else "contacted",
            )
            self.db.add(contact)
            self.db.flush()

        # 2. Lead Lookup / Non-destructive update
        if norm_email:
            lead = self.db.execute(
                select(Lead)
                .where(
                    Lead.organization_id == org_id,
                    func.lower(Lead.email) == norm_email,
                )
                .limit(1)
            ).scalar_one_or_none()

        if lead:
            if data.company_name and not lead.company_name:
                lead.company_name = data.company_name
            if data.job_title and not lead.job_title:
                lead.job_title = data.job_title
            if data.phone_number and not lead.phone:
                lead.phone = data.phone_number
            if not lead.contact_id and contact:
                lead.contact_id = contact.id
                if contact.company_id and not lead.company_id:
                    lead.company_id = contact.company_id
        elif norm_email and data.company_name:
            # Create lead snapshot if company name is known
            first_name = None
            last_name = None
            if data.lead_full_name:
                parts = data.lead_full_name.strip().split(maxsplit=1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else None

            lead = Lead(
                organization_id=org_id,
                company_name=data.company_name,
                email=norm_email,
                phone=data.phone_number,
                first_name=first_name,
                last_name=last_name,
                job_title=data.job_title,
                source="retell_voice_call",
                qualification_status="qualified" if data.call_outcome in (OUTCOME_INTERESTED, OUTCOME_QUALIFIED) else "new",
                lead_temperature="hot" if data.meeting_requested else "warm",
                contact_id=contact.id if contact else None,
                company_id=contact.company_id if (contact and contact.company_id) else None,
            )
            self.db.add(lead)
            self.db.flush()

        return contact, lead

    def resolve_associated_lead_and_contact(
        self,
        org_id: uuid.UUID,
        data: ExtractedCallData,
        call_record: Optional[CallRecord] = None,
    ) -> Tuple[Optional[Lead], Optional[Contact]]:
        """
        Locates any existing Lead or Contact in the database associated with this call.
        Precedence:
        1. Explicit lead_id
        2. Explicit contact_id
        3. Telephony matching (caller_phone or to_phone)
        4. Cross-linking between contact and lead
        5. Existing database record with matching normalized email
        """
        lead: Optional[Lead] = None
        contact: Optional[Contact] = None

        # 1. By lead_id
        target_lead_id = data.lead_id or (str(call_record.lead_id) if call_record and call_record.lead_id else None)
        if target_lead_id:
            try:
                lid = uuid.UUID(str(target_lead_id))
                lead = self.db.execute(
                    select(Lead).where(Lead.organization_id == org_id, Lead.id == lid)
                ).scalar_one_or_none()
            except (ValueError, TypeError):
                pass

        # 2. By contact_id
        target_contact_id = data.contact_id or (str(call_record.contact_id) if call_record and call_record.contact_id else None)
        if target_contact_id:
            try:
                cid = uuid.UUID(str(target_contact_id))
                contact = self.db.execute(
                    select(Contact).where(Contact.organization_id == org_id, Contact.id == cid)
                ).scalar_one_or_none()
            except (ValueError, TypeError):
                pass

        # 3. By phone number lookup
        phones_to_check = [p for p in (data.caller_phone, data.to_phone, data.phone_number) if p]
        if not contact and phones_to_check:
            for p in phones_to_check:
                contact = self.db.execute(
                    select(Contact).where(Contact.organization_id == org_id, Contact.phone == p).limit(1)
                ).scalar_one_or_none()
                if contact:
                    break

        if not lead and phones_to_check:
            for p in phones_to_check:
                lead = self.db.execute(
                    select(Lead).where(Lead.organization_id == org_id, Lead.phone == p).limit(1)
                ).scalar_one_or_none()
                if lead:
                    break

        # 4. Cross-linking
        if contact and not lead and getattr(contact, "lead_id", None):
            lead = self.db.get(Lead, contact.lead_id)
        if lead and not contact and getattr(lead, "contact_id", None):
            contact = self.db.get(Contact, lead.contact_id)

        # 5. Check if normalized email belongs to a known Contact or Lead in DB
        norm_email = normalize_email(data.email)
        if not contact and norm_email:
            existing_c = self.db.execute(
                select(Contact).where(
                    Contact.organization_id == org_id,
                    func.lower(Contact.email) == norm_email,
                ).limit(1)
            ).scalar_one_or_none()
            if existing_c:
                contact = existing_c

        if not lead and norm_email:
            existing_l = self.db.execute(
                select(Lead).where(
                    Lead.organization_id == org_id,
                    func.lower(Lead.email) == norm_email,
                ).limit(1)
            ).scalar_one_or_none()
            if existing_l:
                lead = existing_l

        # Link unambiguous relationship if known
        if lead and contact and not lead.contact_id:
            lead.contact_id = contact.id
            if contact.company_id and not lead.company_id:
                lead.company_id = contact.company_id

        return lead, contact

    def resolve_authoritative_recipient_email(
        self,
        data: ExtractedCallData,
        lead: Optional[Lead],
        contact: Optional[Contact],
    ) -> Tuple[Optional[str], bool]:
        """
        Determines the authoritative recipient email address based on CRM precedence.
        
        Rules:
        1. If associated Lead or Contact exists (KNOWN caller):
           - Stored Lead.email (or Contact.email) is authoritative!
           - AI-extracted email must NOT override stored Lead/Contact email.
           - If stored email is valid -> return (stored_email, False).
           - If stored email is missing/empty -> return (None, True). (missing_email)
        2. If genuinely UNKNOWN caller (no associated Lead or Contact found):
           - If caller provided a valid email during call -> return (data.email, False).
           - If caller provided no valid email -> return (None, True). (missing_email)
        """
        is_known = (lead is not None) or (contact is not None)

        if is_known:
            stored_lead_email = self.validate_email(lead.email) if lead and lead.email else None
            stored_contact_email = self.validate_email(contact.email) if contact and contact.email else None
            authoritative_stored = stored_lead_email or stored_contact_email

            if authoritative_stored:
                return authoritative_stored, False
            else:
                # Known lead/contact has NO stored email in backend -> do NOT use AI hallucinated email
                return None, True

        # Genuinely unknown caller
        if data.email:
            return data.email, False

        return None, True

    # ── Call Event Lifecycle Handlers ─────────────────────────────────────────

    def handle_call_started(self, payload: Dict[str, Any]) -> CallRecord:
        """Process Retell call_started webhook event."""
        data = self.extract_call_data(payload)
        org = self.resolve_organization(data)
        if not org:
            logger.warning("Quarantined call_started event: cannot resolve organization unambiguously for call_id=%s", data.call_id)
            raise UnresolvedOrganizationError(f"Unable to resolve Organization unambiguously for call_id={data.call_id}. Event quarantined.")

        existing = self.db.execute(
            select(CallRecord)
            .where(CallRecord.organization_id == org.id, CallRecord.call_id == data.call_id)
        ).scalar_one_or_none()

        if existing:
            existing.call_status = "in_progress"
            existing.started_at = data.started_at or existing.started_at
            self.db.commit()
            return existing

        record = CallRecord(
            organization_id=org.id,
            call_id=data.call_id,
            agent_id=data.agent_id,
            direction=data.direction,
            call_status="in_progress",
            caller_phone=data.caller_phone,
            to_phone=data.to_phone,
            started_at=data.started_at or datetime.now(timezone.utc),
            followup_status="none",
        )
        self.db.add(record)
        self.db.commit()
        return record

    def handle_call_ended(self, payload: Dict[str, Any]) -> CallRecord:
        """Process Retell call_ended webhook event."""
        data = self.extract_call_data(payload)
        org = self.resolve_organization(data)
        if not org:
            logger.warning("Quarantined call_ended event: cannot resolve organization unambiguously for call_id=%s", data.call_id)
            raise UnresolvedOrganizationError(f"Unable to resolve Organization unambiguously for call_id={data.call_id}. Event quarantined.")

        record = self.db.execute(
            select(CallRecord)
            .where(CallRecord.organization_id == org.id, CallRecord.call_id == data.call_id)
        ).scalar_one_or_none()

        if not record:
            record = CallRecord(
                organization_id=org.id,
                call_id=data.call_id,
                agent_id=data.agent_id,
                direction=data.direction,
                call_status="ended",
                caller_phone=data.caller_phone,
                to_phone=data.to_phone,
                duration_ms=data.duration_ms,
                disconnection_reason=data.disconnection_reason,
                started_at=data.started_at,
                ended_at=data.ended_at or datetime.now(timezone.utc),
                followup_status="none",
            )
            self.db.add(record)
        else:
            record.call_status = "ended"
            record.duration_ms = data.duration_ms or record.duration_ms
            record.disconnection_reason = data.disconnection_reason or record.disconnection_reason
            record.ended_at = data.ended_at or datetime.now(timezone.utc)

        self.db.commit()
        return record

    # ── Post-Call Analysis & Automated Email Dispatch (Idempotent) ───────────

    def process_call_analyzed(
        self,
        payload: Dict[str, Any],
        org_id_override: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Process Retell call_analyzed webhook event:
        1. Extract call data & structured variables.
        2. Resolve Organization (cross-tenant protected).
        3. Persist/update CallRecord.
        4. Check idempotency: (call_id + followup_type).
        5. Evaluate deterministic email rules.
        6. If approved, render safe template and deliver via existing EmailProvider.
        7. Audit log Outreach & OutreachEvent.
        8. Return status payload.
        """
        data = self.extract_call_data(payload)
        if not data.call_id:
            raise ValueError("Payload missing valid 'call_id'")

        org = self.resolve_organization(data, org_id_override=org_id_override)
        if not org:
            logger.warning(
                "Quarantining call_analyzed event: cannot resolve organization unambiguously for call_id=%s. No email sent.",
                data.call_id,
            )
            return {
                "status": "quarantined",
                "call_id": data.call_id,
                "event": "call_analyzed",
                "duplicate": False,
                "email_sent": False,
                "followup_status": "quarantined",
                "followup_reason": "Quarantined: organization cannot be resolved unambiguously. No business actions taken.",
                "followup_email_id": None,
                "extracted_variables": {
                    "lead_full_name": data.lead_full_name,
                    "email": data.email,
                    "phone_number": data.phone_number,
                    "company_name": data.company_name,
                    "job_title": data.job_title,
                    "call_outcome": data.call_outcome,
                    "meeting_requested": data.meeting_requested,
                    "callback_requested": data.callback_requested,
                    "do_not_contact": data.do_not_contact,
                },
            }

        # Lookup or create CallRecord
        call_record = self.db.execute(
            select(CallRecord)
            .where(CallRecord.organization_id == org.id, CallRecord.call_id == data.call_id)
        ).scalar_one_or_none()

        if not call_record:
            call_record = CallRecord(
                organization_id=org.id,
                call_id=data.call_id,
                agent_id=data.agent_id,
                direction=data.direction,
                call_status="analyzed",
                call_outcome=data.call_outcome,
                caller_phone=data.caller_phone,
                to_phone=data.to_phone,
                duration_ms=data.duration_ms,
                disconnection_reason=data.disconnection_reason,
                summary=data.summary,
                transcript=data.transcript,
                collected_variables=data.collected_variables,
                call_analysis=data.call_analysis,
                metadata_json=data.metadata_json,
                started_at=data.started_at,
                ended_at=data.ended_at,
                analyzed_at=data.analyzed_at,
                followup_status="none",
            )
            self.db.add(call_record)
            self.db.flush()
        else:
            call_record.call_status = "analyzed"
            call_record.call_outcome = data.call_outcome or call_record.call_outcome
            call_record.summary = data.summary or call_record.summary
            call_record.transcript = data.transcript or call_record.transcript
            call_record.collected_variables = data.collected_variables or call_record.collected_variables
            call_record.call_analysis = data.call_analysis or call_record.call_analysis
            call_record.analyzed_at = data.analyzed_at or datetime.now(timezone.utc)
            if data.duration_ms:
                call_record.duration_ms = data.duration_ms

        # 1. Resolve associated Lead and Contact (Source of truth)
        lead, contact = self.resolve_associated_lead_and_contact(org.id, data, call_record=call_record)
        if lead:
            call_record.lead_id = lead.id
        if contact:
            call_record.contact_id = contact.id
        if data.campaign_id and not call_record.campaign_id:
            try:
                call_record.campaign_id = uuid.UUID(data.campaign_id)
            except (ValueError, TypeError):
                pass

        # 2. Resolve authoritative recipient email
        authoritative_email, is_missing_email = self.resolve_authoritative_recipient_email(data, lead, contact)

        # 3. For genuinely unknown callers who provided a valid email, sync to CRM without duplicate creation
        if not lead and not contact and authoritative_email:
            contact, lead = self.sync_lead_and_contact(org.id, data)
            if contact:
                call_record.contact_id = contact.id
            if lead:
                call_record.lead_id = lead.id

        # 3.5 Resolve reliable recipient name from webhook or database Contact/Lead
        resolved_name = self.resolve_reliable_recipient_name(data, contact=contact, lead=lead)

        # 4. Evaluate Deterministic Rules using authoritative email and resolved name
        decision = self.evaluate_followup_decision(
            data,
            resolved_email=authoritative_email,
            is_missing_email=is_missing_email,
            resolved_name=resolved_name,
        )

        # 4.5 CRM Suppression & Opt-Out Guard
        if decision.should_send_email:
            is_crm_opted_out = False
            crm_optout_reason = ""
            if contact and contact.lead_status in ("opted_out", "unsubscribed"):
                is_crm_opted_out = True
                crm_optout_reason = f"Contact lead_status is '{contact.lead_status}'"
            elif lead and lead.status in ("opted_out", "rejected"):
                is_crm_opted_out = True
                crm_optout_reason = f"Lead status is '{lead.status}'"

            if is_crm_opted_out:
                logger.info(
                    "Skipping voice follow-up email for call_id=%s: recipient opted out in CRM (%s)",
                    data.call_id,
                    crm_optout_reason,
                )
                decision.should_send_email = False
                decision.reason = f"Recipient is opted out in CRM ({crm_optout_reason})"

        # Build Idempotency Key: call_id + followup_type
        idempotency_key = f"{data.call_id}:{decision.followup_type}"

        # ── IDEMPOTENCY CHECK ─────────────────────────────────────────────────
        if call_record.followup_idempotency_key == idempotency_key and call_record.followup_status == "sent":
            return {
                "status": "success",
                "call_id": data.call_id,
                "event": "call_analyzed",
                "duplicate": True,
                "email_sent": False,
                "followup_status": "sent",
                "followup_reason": "Follow-up email already sent (idempotent duplicate skipped)",
                "followup_email_id": str(call_record.followup_email_id) if call_record.followup_email_id else None,
                "extracted_variables": {
                    "lead_full_name": decision.recipient_name or data.lead_full_name,
                    "email": authoritative_email,
                    "phone_number": data.phone_number,
                    "company_name": data.company_name,
                    "job_title": data.job_title,
                    "call_outcome": data.call_outcome,
                    "meeting_requested": data.meeting_requested,
                    "callback_requested": data.callback_requested,
                    "do_not_contact": data.do_not_contact,
                },
            }

        if not decision.should_send_email:
            call_record.followup_status = "skipped"
            call_record.followup_reason = decision.reason
            self.db.commit()

            return {
                "status": "success",
                "call_id": data.call_id,
                "event": "call_analyzed",
                "duplicate": False,
                "email_sent": False,
                "followup_status": "skipped",
                "followup_reason": decision.reason,
                "outcome_status": "missing_email" if decision.is_missing_email else "skipped",
                "followup_email_id": None,
                "extracted_variables": {
                    "lead_full_name": decision.recipient_name or data.lead_full_name,
                    "email": authoritative_email,
                    "phone_number": data.phone_number,
                    "company_name": data.company_name,
                    "job_title": data.job_title,
                    "call_outcome": data.call_outcome,
                    "meeting_requested": data.meeting_requested,
                    "callback_requested": data.callback_requested,
                    "do_not_contact": data.do_not_contact,
                },
            }

        # ── RECIPIENT COOLDOWN CHECK ──────────────────────────────────────────
        target_recipient_email = authoritative_email or decision.recipient_email
        recent_outreach = self.check_recipient_cooldown(
            org_id=org.id,
            recipient_email=target_recipient_email,
            cooldown_hours=self.cooldown_hours,
            current_call_record_id=call_record.id,
        )
        if recent_outreach:
            cooldown_reason = (
                f"skipped_cooldown: Voice follow-up to {target_recipient_email} "
                f"skipped due to active {self.cooldown_hours}h cooldown window "
                f"(previous outreach {recent_outreach.id} at {recent_outreach.sent_at or recent_outreach.created_at})"
            )
            logger.info(
                "Skipping voice follow-up for call_id=%s: recipient %s is within active cooldown window",
                data.call_id,
                target_recipient_email,
            )
            call_record.followup_status = "skipped"
            call_record.followup_reason = cooldown_reason
            self.db.commit()

            return {
                "status": "success",
                "call_id": data.call_id,
                "event": "call_analyzed",
                "duplicate": False,
                "email_sent": False,
                "followup_status": "skipped",
                "followup_reason": cooldown_reason,
                "outcome_status": "skipped_cooldown",
                "followup_email_id": None,
                "extracted_variables": {
                    "lead_full_name": decision.recipient_name or data.lead_full_name,
                    "email": authoritative_email,
                    "phone_number": data.phone_number,
                    "company_name": data.company_name,
                    "job_title": data.job_title,
                    "call_outcome": data.call_outcome,
                    "meeting_requested": data.meeting_requested,
                    "callback_requested": data.callback_requested,
                    "do_not_contact": data.do_not_contact,
                },
            }

        # Render Safe Email Content
        subject, body = self.render_email_content(
            decision,
            data,
            organization=org,
            contact=contact,
            lead=lead,
        )
        recipient_email = decision.recipient_email

        # Send via existing EmailProvider abstraction (Resend / SES / Mock)
        email_msg = EmailMessage(
            to_email=recipient_email,
            subject=subject,
            body=body,
            metadata={
                "source": "retell_voice_followup",
                "call_id": data.call_id,
                "agent_id": data.agent_id,
                "followup_type": decision.followup_type,
                "idempotency_key": idempotency_key,
                "organization_id": str(org.id),
            },
        )

        send_result = self.email_provider.send(email_msg)

        # Audit Log: Create Outreach Record
        outreach_status = "sent" if send_result.success else "failed"
        outreach_record = Outreach(
            organization_id=org.id,
            campaign_id=call_record.campaign_id,
            channel="email",
            status=outreach_status,
            subject=subject,
            body=body,
            recipient=recipient_email,
            provider=send_result.provider,
            provider_message_id=send_result.provider_message_id if send_result.success else None,
            sent_at=send_result.timestamp if send_result.success else None,
            contact_id=contact.id if contact else None,
            call_record_id=call_record.id,
        )
        self.db.add(outreach_record)
        self.db.flush()

        # Audit Log: Create OutreachEvent Record
        outreach_event = OutreachEvent(
            organization_id=org.id,
            outreach_id=outreach_record.id,
            event_type="sent" if send_result.success else "failed",
            event_metadata={
                "source": "retell_voice_followup",
                "call_id": data.call_id,
                "followup_type": decision.followup_type,
                "provider": send_result.provider,
                "provider_message_id": send_result.provider_message_id,
                "error": send_result.error_message,
            },
            occurred_at=send_result.timestamp,
        )
        self.db.add(outreach_event)

        # Update CallRecord
        if send_result.success:
            call_record.followup_status = "sent"
            call_record.followup_reason = f"Sent {decision.followup_type} to {recipient_email}"
            call_record.followup_email_id = outreach_record.id
            call_record.followup_idempotency_key = idempotency_key
        else:
            call_record.followup_status = "failed"
            call_record.followup_reason = f"Provider delivery failed: {send_result.error_message}"
            call_record.followup_email_id = outreach_record.id

        self.db.commit()

        return {
            "status": "success" if send_result.success else "failed",
            "call_id": data.call_id,
            "event": "call_analyzed",
            "duplicate": False,
            "email_sent": bool(send_result.success),
            "followup_status": call_record.followup_status,
            "followup_reason": call_record.followup_reason,
            "followup_email_id": str(outreach_record.id),
            "provider": send_result.provider,
            "provider_message_id": send_result.provider_message_id,
            "extracted_variables": {
                "lead_full_name": data.lead_full_name,
                "email": data.email,
                "phone_number": data.phone_number,
                "company_name": data.company_name,
                "job_title": data.job_title,
                "call_outcome": data.call_outcome,
                "meeting_requested": data.meeting_requested,
                "callback_requested": data.callback_requested,
                "do_not_contact": data.do_not_contact,
            },
        }
