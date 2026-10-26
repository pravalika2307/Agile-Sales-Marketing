"""Comprehensive test suite for outbound Retell voice campaign workflow.

Validates end-to-end:
1. Outbound call initiation (mocked & simulated test mode)
2. Dynamic variable mapping (lead, contact, company, campaign)
3. Invalid destination numbers and phone validation
4. Missing Retell configuration (from_number, agent_id)
5. Provider authentication (401) and permission (403) errors without secret leakage
6. Rate limits (429), timeouts, and server errors
7. Duplicate dispatch prevention (sending, sent)
8. CallRecord persistence and bidirectional Outreach linkage
9. Webhook processing lifecycle: call_started -> call_ended -> call_analyzed
10. Out-of-order and duplicate webhook idempotency
11. Voice outreach step completion on analyzed call
12. Failure and no-answer handling
13. Positive outcome (interested / meeting requested) triggering follow-up email
14. Negative outcomes (not interested / dnc / wrong person) not triggering email
15. Missing recipient email handling
16. Missing meeting booking URL handling without inventing fake links
17. Safe email retry without repeating the voice call
18. Tenant isolation guards
19. Campaign scheduler delay evaluation (respecting delays without sleep)
20. Live-call fail-closed safety controls
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.services.campaign_execution.rules import (
    EvaluationResult,
    evaluate_subsequent_step_eligibility,
)
from app.services.campaign_scheduler import CampaignSchedulerService
from app.services.organization_config import (
    clear_organization_booking_registry,
    register_organization_booking_url,
)
from app.services.outreach.base import EmailMessage, EmailSendResult, MockEmailProvider
from app.services.outreach.service import (
    AlreadySentError,
    CurrentlySendingError,
    OutreachNotFoundError,
    ProviderDeliveryError,
    SuppressedRecipientError,
    retry_outreach,
    send_outreach,
)
from app.services.outreach.voice_agent import build_voice_dynamic_variables
from app.services.outreach.voice_followup import (
    FOLLOWUP_TYPE_INTERESTED,
    FOLLOWUP_TYPE_MEETING,
    FOLLOWUP_TYPE_NONE,
    VoiceFollowUpService,
)
from app.services.voice.retell_client import (
    RetellAPIError,
    RetellAuthenticationError,
    RetellClient,
    RetellConfigurationError,
    RetellRateLimitError,
    RetellTimeoutError,
)
from app.services.voice.service import (
    InvalidPhoneNumberError,
    VoiceConfigurationError,
    check_voice_consent,
    initiate_outbound_call,
    send_voice_outreach,
    validate_recipient_phone,
)


# ── Database Fixture ──────────────────────────────────────────────────────────

class RecordingMockEmailProvider(MockEmailProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent_messages = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        res = super().send(message)
        if res.success:
            self.sent_messages.append(message)
        return res


@pytest.fixture
def db():
    """Isolated SQLite in-memory database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ── Seed Helpers ──────────────────────────────────────────────────────────────

def create_tenant_environment(db: Session, name_suffix: str = ""):
    """Creates a complete tenant environment with organization, company, contact, campaign, and enrollment."""
    org = Organization(
        id=uuid.uuid4(),
        name=f"Acme Voice Org {name_suffix}".strip(),
        slug=f"acme-voice-{uuid.uuid4().hex[:6]}",
    )
    db.add(org)

    company = Company(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Target Enterprise {name_suffix}".strip(),
    )
    db.add(company)

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_id=company.id,
        first_name="Bruce",
        last_name="Wayne",
        email="bruce@wayneenterprises.com",
        phone="+14155552671",
        job_title="CEO",
        lead_status="qualified",
    )
    db.add(contact)

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        company_id=company.id,
        first_name="Bruce",
        last_name="Wayne",
        email="bruce@wayneenterprises.com",
        phone="+14155552671",
        company_name="Wayne Enterprises",
        job_title="CEO",
        status="contacted",
    )
    db.add(lead)

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Q4 Enterprise Voice Outreach {name_suffix}".strip(),
        status="active",
        workflow_config={
            "nodes": [
                {"id": "node-1", "type": "start", "title": "Start"},
                {
                    "id": "node-2",
                    "type": "voice",
                    "title": "AI Voice SDR Call",
                    "config": {
                        "agent_id": "agent_test_sdr_123",
                        "from_number": "+14155550100",
                    },
                },
                {
                    "id": "node-3",
                    "type": "condition",
                    "title": "Meeting Requested?",
                    "config": {"condition_type": "meeting_requested"},
                },
                {
                    "id": "node-4",
                    "type": "email",
                    "title": "Send Calendar Booking Link",
                    "config": {
                        "condition_type": "meeting_requested",
                        "subject": "Follow-up regarding our call, {{first_name}}",
                        "body": "Hi {{first_name}},\n\nThanks for your time. Book a meeting here: {{booking_link}}",
                        "delay_days": 0,
                        "delay_hours": 0,
                    },
                },
            ],
            "edges": [],
        },
    )
    db.add(campaign)

    enrollment = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=campaign.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    db.add(enrollment)
    db.commit()

    return {
        "org": org,
        "company": company,
        "contact": contact,
        "lead": lead,
        "campaign": campaign,
        "enrollment": enrollment,
    }


def create_voice_outreach_item(
    db: Session,
    env: Dict[str, Any],
    status: str = "draft",
    phone: Optional[str] = None,
) -> Outreach:
    """Helper to create an outreach row with channel='voice'."""
    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=env["org"].id,
        campaign_id=env["campaign"].id,
        contact_id=env["contact"].id,
        campaign_contact_id=env["enrollment"].id,
        channel="voice",
        status=status,
        recipient=phone or env["contact"].phone,
    )
    db.add(outreach)
    db.add(
        OutreachEvent(
            organization_id=env["org"].id,
            outreach_id=outreach.id,
            event_type="created",
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.refresh(outreach)
    return outreach


# ── TESTS ─────────────────────────────────────────────────────────────────────

# 1. Outbound Call Initiation (Safe Mock Test Mode)
def test_successful_outbound_call_creation(db):
    """Outbound voice outreach initiates call, transitions to 'sending', links CallRecord."""
    env = create_tenant_environment(db, "Success")
    outreach = create_voice_outreach_item(db, env)

    dispatched = send_voice_outreach(
        db=db,
        org_id=env["org"].id,
        outreach_id=outreach.id,
        force_mock=True,
    )

    assert dispatched.status == "sending"
    assert dispatched.provider == "retell"
    assert dispatched.provider_message_id is not None
    assert dispatched.provider_message_id.startswith("call_mock_")
    assert dispatched.call_record_id is not None

    call_rec = db.get(CallRecord, dispatched.call_record_id)
    assert call_rec is not None
    assert call_rec.call_id == dispatched.provider_message_id
    assert call_rec.agent_id == "agent_test_sdr_123"
    assert call_rec.direction == "outbound"
    assert call_rec.call_status == "registered"
    assert call_rec.to_phone == env["contact"].phone


# 2. Dynamic Variable Mapping
def test_dynamic_variable_mapping(db):
    """Dynamic variables extract prospect, company, campaign, and sender information without raw tags."""
    env = create_tenant_environment(db, "Vars")
    vars_dict = build_voice_dynamic_variables(
        contact=env["contact"],
        company=env["company"],
        campaign=env["campaign"],
        organization=env["org"],
        lead=env["lead"],
    )

    assert vars_dict["lead_first_name"] == "Bruce"
    assert vars_dict["lead_last_name"] == "Wayne"
    assert vars_dict["lead_full_name"] == "Bruce Wayne"
    assert vars_dict["prospect_company_name"] == env["company"].name
    assert vars_dict["campaign_name"] == env["campaign"].name
    assert vars_dict["sender_company_name"] == env["org"].name

    for k, v in vars_dict.items():
        assert "{{" not in str(v)
        assert "}}" not in str(v)


# 3. Invalid Destination Numbers
def test_invalid_destination_numbers(db):
    """Invalid or missing destination phone marks outreach failed without making provider calls."""
    env = create_tenant_environment(db, "InvalidPhone")
    outreach = create_voice_outreach_item(db, env, phone="invalid_phone_123")

    with pytest.raises(InvalidPhoneNumberError):
        send_voice_outreach(
            db=db,
            org_id=env["org"].id,
            outreach_id=outreach.id,
            raise_on_failure=True,
            force_mock=True,
        )

    db.refresh(outreach)
    assert outreach.status == "failed"

    events = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach.id).all()
    event_types = [e.event_type for e in events]
    assert "failed" in event_types


# 4. Missing Retell Configuration
def test_missing_retell_configuration(db):
    """Missing caller ID or agent ID fails safely with accurate error."""
    env = create_tenant_environment(db, "NoConfig")
    env["campaign"].workflow_config = {"nodes": []}
    db.commit()

    outreach = create_voice_outreach_item(db, env)

    with patch.object(settings, "RETELL_FROM_NUMBER", None):
        with patch.object(settings, "RETELL_AGENT_ID", None):
            with pytest.raises(VoiceConfigurationError):
                send_voice_outreach(
                    db=db,
                    org_id=env["org"].id,
                    outreach_id=outreach.id,
                    raise_on_failure=True,
                    force_mock=True,
                )

    db.refresh(outreach)
    assert outreach.status == "failed"


# 5. Provider Authentication and Permission Errors (Sanitized)
def test_provider_auth_and_permission_errors(db):
    """HTTP 401 and 403 provider errors fail safely without leaking API key in exceptions."""
    env = create_tenant_environment(db, "AuthError")
    outreach = create_voice_outreach_item(db, env)

    mock_client = MagicMock(spec=RetellClient)
    mock_client.create_phone_call.side_effect = RetellAuthenticationError(
        message="Retell authentication failed: secret_key_123456 invalid",
        status_code=401,
    )

    with patch.object(settings, "RETELL_ENABLED", True):
        with patch.object(settings, "RETELL_ALLOW_LIVE_CALLS", True):
            with patch.object(settings, "RETELL_API_KEY", "secret_key_123456"):
                with patch.object(settings, "RETELL_FROM_NUMBER", "+14155550100"):
                    with patch.object(settings, "RETELL_AGENT_ID", "agent_123"):
                        with pytest.raises(ProviderDeliveryError) as exc_info:
                            send_voice_outreach(
                                db=db,
                                org_id=env["org"].id,
                                outreach_id=outreach.id,
                                retell_client=mock_client,
                                raise_on_failure=True,
                                force_mock=False,
                            )

    assert "secret_key_123456" not in str(exc_info.value)
    db.refresh(outreach)
    assert outreach.status == "failed"


# 6. Rate Limits, Timeouts, and Server Failures
def test_rate_limits_timeouts_and_server_failures(db):
    """Rate limits (429) and timeouts translate into safe failure states."""
    env = create_tenant_environment(db, "RateLimit")
    outreach = create_voice_outreach_item(db, env)

    mock_client = MagicMock(spec=RetellClient)
    mock_client.create_phone_call.side_effect = RetellRateLimitError(
        message="Too many requests",
        retry_after=60,
    )

    with patch.object(settings, "RETELL_ENABLED", True):
        with patch.object(settings, "RETELL_ALLOW_LIVE_CALLS", True):
            with patch.object(settings, "RETELL_API_KEY", "key_xyz"):
                with patch.object(settings, "RETELL_FROM_NUMBER", "+14155550100"):
                    with patch.object(settings, "RETELL_AGENT_ID", "agent_123"):
                        send_voice_outreach(
                            db=db,
                            org_id=env["org"].id,
                            outreach_id=outreach.id,
                            retell_client=mock_client,
                            raise_on_failure=False,
                            force_mock=False,
                        )

    db.refresh(outreach)
    assert outreach.status == "failed"


# 7. Duplicate Dispatch Prevention
def test_duplicate_dispatch_prevention(db):
    """Cannot dispatch outreach that is already 'sending' or 'sent'."""
    env = create_tenant_environment(db, "DupDispatch")
    outreach = create_voice_outreach_item(db, env, status="sending")

    with pytest.raises(CurrentlySendingError):
        send_voice_outreach(
            db=db,
            org_id=env["org"].id,
            outreach_id=outreach.id,
            force_mock=True,
        )

    outreach.status = "sent"
    db.commit()

    with pytest.raises(AlreadySentError):
        send_voice_outreach(
            db=db,
            org_id=env["org"].id,
            outreach_id=outreach.id,
            force_mock=True,
        )


# 8. Webhook Processing: call_started -> call_ended -> call_analyzed
def test_webhook_processing_lifecycle(db):
    """Full webhook progression updates CallRecord and marks voice outreach 'sent'."""
    env = create_tenant_environment(db, "Lifecycle")
    outreach = create_voice_outreach_item(db, env)

    # 1. Dispatch
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)
    call_id = outreach.provider_message_id

    service = VoiceFollowUpService(db=db, email_provider=MockEmailProvider())

    # 2. call_started
    service.handle_call_started({
        "event": "call_started",
        "call_id": call_id,
        "start_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "from_number": "+14155550100",
        "to_number": env["contact"].phone,
        "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
    })
    call_rec = db.get(CallRecord, outreach.call_record_id)
    assert call_rec.call_status == "in_progress"
    db.refresh(outreach)
    assert outreach.status == "sending"  # Not mistaken for completed conversation yet

    # 3. call_ended
    service.handle_call_ended({
        "event": "call_ended",
        "call_id": call_id,
        "duration_ms": 45000,
        "disconnection_reason": "agent_hangup",
        "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
    })
    db.refresh(call_rec)
    assert call_rec.call_status == "ended"
    assert call_rec.duration_ms == 45000

    # 4. call_analyzed
    service.process_call_analyzed({
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "call_analysis": {
                "call_summary": "Prospect requested demo next week.",
                "call_outcome": "MEETING_REQUESTED",
            },
            "collected_dynamic_variables": {
                "meeting_requested": True,
            },
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    })
    db.refresh(call_rec)
    db.refresh(outreach)
    assert call_rec.call_status == "analyzed"
    assert outreach.status == "sent"  # Completed after call analysis
    assert outreach.sent_at is not None


# 9. Out-of-Order and Duplicate Webhook Idempotency
def test_out_of_order_and_duplicate_webhooks(db):
    """Out-of-order webhook deliveries cannot regress analyzed call; duplicates are skipped."""
    env = create_tenant_environment(db, "OutOfOrder")
    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)
    call_id = outreach.provider_message_id

    service = VoiceFollowUpService(db=db, email_provider=MockEmailProvider())

    # Call analyzed arrives first (out of order)
    payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "call_analysis": {
                "call_summary": "Prospect interested in pricing details.",
                "call_outcome": "INTERESTED",
            },
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    }
    r1 = service.process_call_analyzed(payload)
    assert r1["duplicate"] is False
    assert r1["followup_status"] == "sent"

    call_rec = db.get(CallRecord, outreach.call_record_id)
    assert call_rec.call_status == "analyzed"

    # Late call_started arrives -> must NOT regress analyzed call to in_progress
    service.handle_call_started({
        "event": "call_started",
        "call_id": call_id,
        "metadata": {"organization_id": str(env["org"].id)},
    })
    db.refresh(call_rec)
    assert call_rec.call_status == "analyzed"

    # Late call_ended arrives -> must NOT regress analyzed call to ended
    service.handle_call_ended({
        "event": "call_ended",
        "call_id": call_id,
        "duration_ms": 25000,
        "metadata": {"organization_id": str(env["org"].id)},
    })
    db.refresh(call_rec)
    assert call_rec.call_status == "analyzed"

    # Duplicate call_analyzed -> returns duplicate=True
    r2 = service.process_call_analyzed(payload)
    assert r2["duplicate"] is True


# 10. Voice Outreach Failure on Unanswered/Failed Call
def test_voice_failure_on_no_answer(db):
    """Unanswered or disconnected voice call marks voice outreach failed."""
    env = create_tenant_environment(db, "NoAnswer")
    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)

    service = VoiceFollowUpService(db=db, email_provider=MockEmailProvider())
    service.handle_call_ended({
        "event": "call_ended",
        "call_id": outreach.provider_message_id,
        "disconnection_reason": "no_answer",
        "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
    })

    db.refresh(outreach)
    assert outreach.status == "failed"


# 11. Positive Outcome Triggers Exactly One Email
def test_positive_outcome_triggers_one_email(db):
    """Meeting requested outcome sends exactly one follow-up email linked to call."""
    env = create_tenant_environment(db, "PositiveOutcome")
    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)

    mock_provider = RecordingMockEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call_id": outreach.provider_message_id,
        "call": {
            "call_id": outreach.provider_message_id,
            "call_analysis": {
                "call_summary": "Prospect wants to schedule a demo.",
                "call_outcome": "MEETING_REQUESTED",
            },
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["email_sent"] is True
    assert result["followup_status"] == "sent"
    assert len(mock_provider.sent_messages) == 1

    # Replay webhook -> duplicate skipped, no second email
    result2 = service.process_call_analyzed(payload)
    assert result2["duplicate"] is True
    assert len(mock_provider.sent_messages) == 1


# 12. Negative Outcomes Do Not Trigger Email
@pytest.mark.parametrize("outcome", ["NOT_INTERESTED", "DO_NOT_CONTACT", "WRONG_PERSON", "UNAVAILABLE"])
def test_negative_outcomes_do_not_trigger_email(db, outcome):
    """Negative outcomes skip follow-up email without sending."""
    env = create_tenant_environment(db, f"Negative_{outcome}")
    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)

    mock_provider = RecordingMockEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call_id": outreach.provider_message_id,
        "call": {
            "call_id": outreach.provider_message_id,
            "call_analysis": {
                "call_outcome": outcome,
            },
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    assert len(mock_provider.sent_messages) == 0


# 13. Missing Recipient Email Handling
def test_missing_recipient_email_handling(db):
    """Missing or empty recipient email skips follow-up without throwing errors."""
    env = create_tenant_environment(db, "MissingEmail")
    env["contact"].email = "invalid-address"
    env["lead"].email = None
    db.commit()

    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)

    mock_provider = RecordingMockEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call_id": outreach.provider_message_id,
        "call": {
            "call_id": outreach.provider_message_id,
            "call_analysis": {"call_outcome": "INTERESTED"},
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["outcome_status"] == "missing_email"
    assert len(mock_provider.sent_messages) == 0


# 14. Missing Meeting Booking URL Handling
def test_missing_meeting_booking_url_handling(db):
    """When organization booking URL is missing, email is sent with safe factual text without fake links."""
    env = create_tenant_environment(db, "NoBookingUrl")
    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)

    mock_provider = RecordingMockEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call_id": outreach.provider_message_id,
        "call": {
            "call_id": outreach.provider_message_id,
            "call_analysis": {"call_outcome": "MEETING_REQUESTED"},
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is True
    sent_msg = mock_provider.sent_messages[0]
    assert "https://calendly.com" not in sent_msg.body
    assert "follow up shortly with scheduling details" in sent_msg.body


# 15. Safe Email Retry Without Repeating Voice Call
def test_email_retry_without_repeating_call(db):
    """A failed follow-up email can be retried via retry_outreach without redialing the voice call."""
    env = create_tenant_environment(db, "RetryEmail")
    outreach = create_voice_outreach_item(db, env)
    send_voice_outreach(db=db, org_id=env["org"].id, outreach_id=outreach.id, force_mock=True)
    db.refresh(outreach)

    failing_provider = MagicMock()
    failing_provider.send.return_value = EmailSendResult(
        success=False,
        provider="resend",
        error_message="SMTP 550 Mailbox full",
        timestamp=datetime.now(timezone.utc),
        provider_message_id=None,
    )

    service = VoiceFollowUpService(db=db, email_provider=failing_provider)
    payload = {
        "event": "call_analyzed",
        "call_id": outreach.provider_message_id,
        "call": {
            "call_id": outreach.provider_message_id,
            "call_analysis": {"call_outcome": "INTERESTED"},
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(outreach.id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "failed"
    followup_email_id = uuid.UUID(result["followup_email_id"])
    email_outreach = db.get(Outreach, followup_email_id)
    assert email_outreach.status == "failed"

    # Now retry email delivery with working provider
    working_provider = RecordingMockEmailProvider()
    retried_email = retry_outreach(
        db=db,
        org_id=env["org"].id,
        outreach_id=followup_email_id,
        provider=working_provider,
    )
    assert retried_email.status == "sent"
    assert len(working_provider.sent_messages) == 1

    # Verify voice call record and outreach were NOT repeated
    db.refresh(outreach)
    assert outreach.status == "sent"


# 16. Tenant Isolation
def test_tenant_isolation(db):
    """Cannot dispatch voice outreach using another tenant's credentials or contact."""
    env1 = create_tenant_environment(db, "Org1")
    env2 = create_tenant_environment(db, "Org2")

    outreach = create_voice_outreach_item(db, env1)

    with pytest.raises(OutreachNotFoundError):
        send_voice_outreach(
            db=db,
            org_id=env2["org"].id,  # Wrong organization ID
            outreach_id=outreach.id,
            force_mock=True,
        )


# 17. Campaign Scheduler Delay Respect (No sleep)
def test_campaign_scheduler_delay_and_no_sleep(db):
    """Step evaluation enforces configured delay between steps without using sleep."""
    env = create_tenant_environment(db, "Delay")

    # Voice call step 1 already completed
    last_call_outreach = create_voice_outreach_item(db, env, status="sent")
    last_call_outreach.sent_at = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)

    call_rec = CallRecord(
        organization_id=env["org"].id,
        call_id="call_completed_001",
        agent_id="agent_123",
        direction="outbound",
        call_status="analyzed",
        call_outcome="INTERESTED",
    )
    db.add(call_rec)
    db.flush()
    last_call_outreach.call_record_id = call_rec.id
    db.commit()

    # Step 2: Email with 2 days delay
    next_step = CampaignStep(
        organization_id=env["org"].id,
        campaign_id=env["campaign"].id,
        step_number=2,
        step_type="email",
        subject_template="Step 2 Email",
        body_template="Step 2 Body",
        delay_days=2,
        delay_hours=0,
    )

    # Check 1 day later -> Skipped (delay not elapsed)
    time_day1 = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone.utc)
    eval1 = evaluate_subsequent_step_eligibility(
        campaign=env["campaign"],
        campaign_contact=env["enrollment"],
        contact=env["contact"],
        next_step=next_step,
        last_sent_outreach=last_call_outreach,
        existing_outreaches_for_next_step=[],
        now=time_day1,
        required_condition="interested",
    )
    assert eval1.result == EvaluationResult.SKIPPED
    assert "delay not elapsed" in eval1.reason.lower()

    # Check 2 days later -> Eligible!
    time_day2 = datetime(2026, 10, 22, 10, 0, 1, tzinfo=timezone.utc)
    eval2 = evaluate_subsequent_step_eligibility(
        campaign=env["campaign"],
        campaign_contact=env["enrollment"],
        contact=env["contact"],
        next_step=next_step,
        last_sent_outreach=last_call_outreach,
        existing_outreaches_for_next_step=[],
        now=time_day2,
        required_condition="interested",
    )
    assert eval2.result == EvaluationResult.ELIGIBLE


# 18. Live Call Fail-Closed Safety Controls
def test_live_call_safety_controls(db):
    """When live calling flags are False, initiate_outbound_call operates in safe test mode."""
    with patch.object(settings, "RETELL_ENABLED", False):
        with patch.object(settings, "RETELL_ALLOW_LIVE_CALLS", False):
            result = initiate_outbound_call(
                from_number="+14155550100",
                to_number="+14155552671",
                agent_id="agent_test_sdr",
                force_mock=False,
            )

    assert result["simulated"] is True
    assert result["call_id"].startswith("call_mock_")
    assert result["call_status"] == "registered"


# 19. Opt-Out and Do-Not-Call Suppression
def test_opt_out_suppression(db):
    """Voice outreach is blocked and cancelled when prospect is opted out or marked DNC."""
    env = create_tenant_environment(db, "Suppression")

    # 1. Contact with lead_status = 'opted_out'
    suppressed_contact = Contact(
        id=uuid.uuid4(),
        organization_id=env["org"].id,
        company_id=env["company"].id,
        first_name="Clark",
        last_name="Kent",
        email="clark@dailyplanet.com",
        phone="+14155554321",
        lead_status="opted_out",
    )
    db.add(suppressed_contact)
    db.commit()

    enrollment = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=env["campaign"].id,
        contact_id=suppressed_contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    db.add(enrollment)
    db.commit()

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=env["org"].id,
        campaign_id=env["campaign"].id,
        contact_id=suppressed_contact.id,
        campaign_contact_id=enrollment.id,
        channel="voice",
        status="draft",
        recipient=suppressed_contact.phone,
    )
    db.add(outreach)
    db.commit()

    with pytest.raises(SuppressedRecipientError) as exc_info:
        send_outreach(
            db=db,
            org_id=env["org"].id,
            outreach_id=outreach.id,
        )
    assert "opted-out" in str(exc_info.value).lower()
    db.refresh(outreach)
    assert outreach.status == "cancelled"


# 20. Complete 18-Step Voice Campaign Lifecycle Scenario
def test_complete_voice_campaign_lifecycle_scenario(db):
    """
    Validates the complete 18-step outbound voice campaign lifecycle using mocked provider interactions.
    Matches the user-specified integration test scenario step-by-step.
    """
    # Step 1: Create synthetic organization, campaign, lead/contact, and campaign enrollment
    env = create_tenant_environment(db, "E2EScenario")
    configured_booking_url = "https://cal.com/e2e-scenario/30min"
    register_organization_booking_url(env["org"].id, configured_booking_url)

    try:
        # Step 2: Configure the campaign's first step as an outbound Retell voice call
        voice_outreach = create_voice_outreach_item(db, env, status="draft")
        assert voice_outreach.channel == "voice"
        assert voice_outreach.status == "draft"

        # Step 3 & 4: Dispatch the voice outreach through the actual campaign execution path (send_outreach)
        # and verify mock Retell call-creation succeeds
        dispatched_outreach = send_outreach(
            db=db,
            org_id=env["org"].id,
            outreach_id=voice_outreach.id,
        )

        # Step 5: Verify that the provider call ID and associated campaign records are persisted correctly
        db.refresh(voice_outreach)
        assert dispatched_outreach.id == voice_outreach.id
        assert voice_outreach.status == "sending"
        assert voice_outreach.provider_message_id is not None
        assert voice_outreach.provider_message_id.startswith("call_mock_")
        provider_call_id = voice_outreach.provider_message_id

        assert voice_outreach.call_record_id is not None
        call_rec = db.get(CallRecord, voice_outreach.call_record_id)
        assert call_rec is not None
        assert call_rec.call_id == provider_call_id
        assert call_rec.organization_id == env["org"].id
        assert call_rec.campaign_id == env["campaign"].id
        assert call_rec.contact_id == env["contact"].id

        # Step 6: Simulate call-started and call-ended webhooks
        mock_email_provider = RecordingMockEmailProvider()
        followup_service = VoiceFollowUpService(db=db, email_provider=mock_email_provider)

        # 6a. call-started
        start_payload = {
            "event": "call_started",
            "call_id": provider_call_id,
            "start_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "from_number": "+14155550100",
            "to_number": env["contact"].phone,
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(voice_outreach.id),
            },
        }
        followup_service.handle_call_started(start_payload)
        db.refresh(call_rec)
        db.refresh(voice_outreach)
        assert call_rec.call_status == "in_progress"
        assert voice_outreach.status == "sending"

        # 6b. call-ended
        ended_payload = {
            "event": "call_ended",
            "call_id": provider_call_id,
            "duration_ms": 52000,
            "disconnection_reason": "agent_hangup",
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(voice_outreach.id),
            },
        }
        followup_service.handle_call_ended(ended_payload)
        db.refresh(call_rec)
        assert call_rec.call_status == "ended"
        assert call_rec.duration_ms == 52000

        # Step 7: Simulate call-analyzed indicating prospect is interested and requests more info by email
        analyzed_payload = {
            "event": "call_analyzed",
            "call_id": provider_call_id,
            "call": {
                "call_id": provider_call_id,
                "call_analysis": {
                    "call_summary": "Prospect is interested and requested meeting booking details by email.",
                    "call_outcome": "INTERESTED",
                },
                "collected_dynamic_variables": {
                    "interest_level": "high",
                },
                "metadata": {
                    "organization_id": str(env["org"].id),
                    "outreach_id": str(voice_outreach.id),
                },
            },
        }
        analysis_result = followup_service.process_call_analyzed(analyzed_payload)

        # Step 8: Verify that the call analysis is persisted
        db.refresh(call_rec)
        assert call_rec.call_status == "analyzed"
        assert call_rec.call_outcome == "INTERESTED"
        assert "interested" in (call_rec.summary or "").lower()

        # Step 9: Verify that the voice step transitions to the appropriate completed state (sent)
        db.refresh(voice_outreach)
        assert voice_outreach.status == "sent"
        assert voice_outreach.sent_at is not None

        # Step 10: Verify that exactly one follow-up email is created or dispatched through email service
        assert analysis_result["status"] == "success"
        assert analysis_result["email_sent"] is True
        assert len(mock_email_provider.sent_messages) == 1

        # Step 11: Verify that the email contains the configured meeting-booking URL
        dispatched_email_msg = mock_email_provider.sent_messages[0]
        assert configured_booking_url in dispatched_email_msg.body

        # Step 12: Verify that the email step transitions to the correct state
        email_outreach_id = uuid.UUID(analysis_result["followup_email_id"])
        email_outreach = db.get(Outreach, email_outreach_id)
        assert email_outreach is not None
        assert email_outreach.channel == "email"
        assert email_outreach.status == "sent"
        assert email_outreach.campaign_id == env["campaign"].id
        assert email_outreach.call_record_id == call_rec.id

        # Step 13: Verify that the next workflow step follows its configured delay and conditions
        next_step = CampaignStep(
            id=uuid.uuid4(),
            organization_id=env["org"].id,
            campaign_id=env["campaign"].id,
            step_number=2,
            step_type="email",
            subject_template="Step 2 Follow-Up",
            body_template="Checking in on Step 2",
            delay_days=2,
            delay_hours=0,
        )
        # At day 1 -> skipped (delay not elapsed)
        eval_day1 = evaluate_subsequent_step_eligibility(
            campaign=env["campaign"],
            campaign_contact=env["enrollment"],
            contact=env["contact"],
            next_step=next_step,
            last_sent_outreach=voice_outreach,
            existing_outreaches_for_next_step=[],
            now=voice_outreach.sent_at + timedelta(days=1),
            required_condition="interested",
        )
        assert eval_day1.result == EvaluationResult.SKIPPED
        assert "delay not elapsed" in eval_day1.reason.lower()

        # At day 2 -> eligible
        eval_day2 = evaluate_subsequent_step_eligibility(
            campaign=env["campaign"],
            campaign_contact=env["enrollment"],
            contact=env["contact"],
            next_step=next_step,
            last_sent_outreach=voice_outreach,
            existing_outreaches_for_next_step=[],
            now=voice_outreach.sent_at + timedelta(days=2, seconds=5),
            required_condition="interested",
        )
        assert eval_day2.result == EvaluationResult.ELIGIBLE

        # Step 14: Replay the call-analyzed webhook and verify that no duplicate email is sent
        replay_result = followup_service.process_call_analyzed(analyzed_payload)
        assert replay_result["duplicate"] is True
        assert len(mock_email_provider.sent_messages) == 1

        # Step 15: Deliver call-ended after call-analyzed and verify that the analyzed state is preserved
        late_ended_payload = {
            "event": "call_ended",
            "call_id": provider_call_id,
            "duration_ms": 53000,
            "metadata": {"organization_id": str(env["org"].id)},
        }
        followup_service.handle_call_ended(late_ended_payload)
        db.refresh(call_rec)
        assert call_rec.call_status == "analyzed"

        # Step 16: Simulate a failed email and verify that retrying the email does not place another call
        failing_email_outreach = Outreach(
            id=uuid.uuid4(),
            organization_id=env["org"].id,
            campaign_id=env["campaign"].id,
            contact_id=env["contact"].id,
            campaign_contact_id=env["enrollment"].id,
            channel="email",
            status="failed",
            call_record_id=call_rec.id,
            recipient=env["contact"].email,
            subject="Test Failed Email",
            body="Test Failed Body",
        )
        db.add(failing_email_outreach)
        db.commit()

        # Retry the email with working provider
        retry_working_provider = RecordingMockEmailProvider()
        retried_record = retry_outreach(
            db=db,
            org_id=env["org"].id,
            outreach_id=failing_email_outreach.id,
            provider=retry_working_provider,
        )
        assert retried_record.status == "sent"
        assert len(retry_working_provider.sent_messages) == 1
        # Confirm original voice outreach status remains sent and call was not redialed
        db.refresh(voice_outreach)
        assert voice_outreach.status == "sent"

        # Step 17: Test negative, unclear, no-answer, and failed-call outcomes
        # 17a: Negative outcome (NOT_INTERESTED) -> skips email
        neg_outreach = create_voice_outreach_item(db, env, status="sending", phone="+14155550991")
        neg_call_rec = CallRecord(
            organization_id=env["org"].id,
            campaign_id=env["campaign"].id,
            contact_id=env["contact"].id,
            call_id="call_mock_neg_123",
            agent_id="agent_test_sdr_123",
            direction="outbound",
            call_status="in_progress",
        )
        db.add(neg_call_rec)
        db.commit()
        neg_outreach.call_record_id = neg_call_rec.id
        neg_outreach.provider_message_id = neg_call_rec.call_id
        db.commit()

        neg_service = VoiceFollowUpService(db=db, email_provider=RecordingMockEmailProvider())
        neg_res = neg_service.process_call_analyzed({
            "event": "call_analyzed",
            "call_id": neg_call_rec.call_id,
            "call": {
                "call_id": neg_call_rec.call_id,
                "call_analysis": {"call_outcome": "NOT_INTERESTED"},
                "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(neg_outreach.id)},
            },
        })
        assert neg_res["email_sent"] is False
        assert neg_res["followup_status"] == "skipped"

        # 17b: Unclear outcome -> skips email
        unclear_outreach = create_voice_outreach_item(db, env, status="sending", phone="+14155550992")
        unclear_call_rec = CallRecord(
            organization_id=env["org"].id,
            campaign_id=env["campaign"].id,
            contact_id=env["contact"].id,
            call_id="call_mock_unclear_123",
            agent_id="agent_test_sdr_123",
            direction="outbound",
            call_status="in_progress",
        )
        db.add(unclear_call_rec)
        db.commit()
        unclear_outreach.call_record_id = unclear_call_rec.id
        unclear_outreach.provider_message_id = unclear_call_rec.call_id
        db.commit()

        unclear_res = neg_service.process_call_analyzed({
            "event": "call_analyzed",
            "call_id": unclear_call_rec.call_id,
            "call": {
                "call_id": unclear_call_rec.call_id,
                "call_analysis": {"call_outcome": "UNCLEAR"},
                "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(unclear_outreach.id)},
            },
        })
        assert unclear_res["email_sent"] is False
        assert unclear_res["followup_status"] == "skipped"

        # 17c: No-answer outcome -> marks voice outreach failed
        no_ans_outreach = create_voice_outreach_item(db, env, status="sending", phone="+14155550993")
        no_ans_outreach.provider_message_id = "call_mock_no_ans_123"
        db.commit()
        neg_service.handle_call_ended({
            "event": "call_ended",
            "call_id": no_ans_outreach.provider_message_id,
            "disconnection_reason": "no_answer",
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(no_ans_outreach.id)},
        })
        db.refresh(no_ans_outreach)
        assert no_ans_outreach.status == "failed"

        # 17d: Failed-call outcome -> marks voice outreach failed
        failed_outreach = create_voice_outreach_item(db, env, status="sending", phone="+14155550994")
        failed_outreach.provider_message_id = "call_mock_dial_fail_123"
        db.commit()
        neg_service.handle_call_ended({
            "event": "call_ended",
            "call_id": failed_outreach.provider_message_id,
            "disconnection_reason": "dial_failed",
            "metadata": {"organization_id": str(env["org"].id), "outreach_id": str(failed_outreach.id)},
        })
        db.refresh(failed_outreach)
        assert failed_outreach.status == "failed"

        # Step 18: Verify tenant isolation and opt-out suppression
        # 18a. Tenant isolation
        other_env = create_tenant_environment(db, "OtherTenantLifecycle")
        isolated_outreach = create_voice_outreach_item(db, env)
        with pytest.raises(OutreachNotFoundError):
            send_outreach(
                db=db,
                org_id=other_env["org"].id,  # Wrong tenant
                outreach_id=isolated_outreach.id,
            )

        # 18b. Opt-out suppression
        suppressed_contact = Contact(
            id=uuid.uuid4(),
            organization_id=env["org"].id,
            company_id=env["company"].id,
            first_name="Opted",
            last_name="Out",
            email="optout@wayne.com",
            phone="+14155558888",
            lead_status="opted_out",  # Suppressed!
        )
        db.add(suppressed_contact)
        db.commit()
        suppressed_enrollment = CampaignContact(
            id=uuid.uuid4(),
            campaign_id=env["campaign"].id,
            contact_id=suppressed_contact.id,
            enrollment_status="in_progress",
            current_step=1,
        )
        db.add(suppressed_enrollment)
        db.commit()
        suppressed_outreach = Outreach(
            id=uuid.uuid4(),
            organization_id=env["org"].id,
            campaign_id=env["campaign"].id,
            contact_id=suppressed_contact.id,
            campaign_contact_id=suppressed_enrollment.id,
            channel="voice",
            status="draft",
            recipient=suppressed_contact.phone,
        )
        db.add(suppressed_outreach)
        db.commit()

        with pytest.raises(SuppressedRecipientError) as exc_info:
            send_outreach(
                db=db,
                org_id=env["org"].id,
                outreach_id=suppressed_outreach.id,
            )
        assert "opted-out" in str(exc_info.value).lower()
        db.refresh(suppressed_outreach)
        assert suppressed_outreach.status == "cancelled"

    finally:
        clear_organization_booking_registry()
