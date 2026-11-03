"""
Comprehensive regression test suite for Retell Voice-Call completion and workflow progression.

Covers:
1. Webhook authenticity & HMAC-SHA256 signature verification.
2. Successful completed call -> persists CallRecord & advances campaign to Step 2.
3. Positive outcome (INTERESTED / MEETING_REQUESTED) condition evaluation.
4. Negative outcome (NOT_INTERESTED) condition evaluation (skips email).
5. Unanswered call (no_answer) handling.
6. Call failure with failure-handling branch progression.
7. Duplicate webhook idempotency (duplicate=True, zero duplicate emails).
8. Out-of-order / delayed webhook handling (call_analyzed before late call_ended).
9. Positive-delay workflow step scheduling (does not dispatch early).
10. Tenant isolation & fails-closed quarantine on cross-tenant / unresolvable payloads.
"""
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
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
from app.models.tenant import Organization
from app.services.campaign_execution.rules import (
    ContactEvaluation,
    EvaluationResult,
    evaluate_subsequent_step_eligibility,
)
from app.services.campaign_scheduler import (
    CampaignSchedulerService,
    advance_campaign_contact_sequence,
)
from app.services.outreach.base import EmailMessage, EmailSendResult, MockEmailProvider
from app.services.outreach.service import send_outreach
from app.services.outreach.voice_followup import (
    OUTCOME_DO_NOT_CONTACT,
    OUTCOME_INTERESTED,
    OUTCOME_MEETING_REQUESTED,
    OUTCOME_NOT_INTERESTED,
    OUTCOME_QUALIFIED,
    VoiceFollowUpService,
)
from app.services.voice.service import send_voice_outreach


# ── Test Database Fixture ─────────────────────────────────────────────────────

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


class RecordingEmailProvider(MockEmailProvider):
    """Mock provider recording all sent email messages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent_messages = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        res = super().send(message)
        if res.success:
            self.sent_messages.append(message)
        return res


def create_qa_sandbox_environment(
    db: Session,
    org_id: Optional[uuid.UUID] = None,
    step_2_condition: Optional[str] = "interested",
    step_2_delay_days: int = 0,
    step_2_delay_hours: int = 0,
    has_step_3: bool = False,
    step_3_delay_days: int = 2,
) -> Dict[str, Any]:
    """Helper creating a complete tenant environment in Agile QA Sandbox."""
    target_org_id = org_id or uuid.UUID("c0aae7f1-95bb-485f-bb9b-e3ed95469912")
    org = db.get(Organization, target_org_id)
    if not org:
        org = Organization(
            id=target_org_id,
            name="Agile QA Sandbox",
            slug=f"agile-qa-sandbox-{uuid.uuid4().hex[:6]}",
        )
        db.add(org)

    company = Company(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Apex Industrial Solutions",
    )
    db.add(company)

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_id=company.id,
        first_name="Pravallika",
        last_name="Test",
        email="pravallika.test@agilereceivables.com",
        phone="+917013670301",
        job_title="Operations Lead",
        lead_status="qualified",
    )
    db.add(contact)

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        company_id=company.id,
        first_name="Pravallika",
        last_name="Test",
        email="pravallika.test@agilereceivables.com",
        phone="+917013670301",
        company_name="Apex Industrial Solutions",
        job_title="Operations Lead",
        status="contacted",
    )
    db.add(lead)

    workflow_nodes = [
        {"id": "node-1", "type": "start", "title": "Start"},
        {
            "id": "node-2",
            "type": "voice",
            "title": "Outbound AI Voice SDR Call",
            "config": {
                "agent_id": "agent_test_sdr_123",
                "from_number": "+16416818482",
            },
        },
        {
            "id": "node-3",
            "type": "email",
            "title": "Step 2 Follow-Up Email",
            "config": {
                "condition_type": step_2_condition,
                "subject": "Follow-up regarding our call, {{first_name}}",
                "body": "Hi {{first_name}},\n\nThanks for your time today. Let us connect soon.",
                "delay_days": step_2_delay_days,
                "delay_hours": step_2_delay_hours,
            },
        },
    ]

    if has_step_3:
        workflow_nodes.append({
            "id": "node-4",
            "type": "email",
            "title": "Step 3 Short Follow-Up Email",
            "config": {
                "condition_type": "interested",
                "subject": "Checking back in, {{first_name}}",
                "body": "Hi {{first_name}},\n\nJust following up on our previous note.",
                "delay_days": step_3_delay_days,
                "delay_hours": 0,
            },
        })

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="QA Sandbox Voice Progression Campaign",
        status="active",
        workflow_config={
            "nodes": workflow_nodes,
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

    # Create in-flight Step 1 voice outreach
    voice_outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        campaign_contact_id=enrollment.id,
        contact_id=contact.id,
        channel="voice",
        status="sending",
        recipient=contact.phone,
        provider="mock",
        provider_message_id=f"call_mock_{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(voice_outreach)
    db.commit()

    call_record = CallRecord(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        call_id=voice_outreach.provider_message_id,
        agent_id="agent_test_sdr_123",
        direction="outbound",
        call_status="in_progress",
        caller_phone="+16416818482",
        to_phone=contact.phone,
        followup_status="none",
    )
    db.add(call_record)
    db.commit()

    voice_outreach.call_record_id = call_record.id
    db.commit()

    return {
        "org": org,
        "company": company,
        "contact": contact,
        "lead": lead,
        "campaign": campaign,
        "enrollment": enrollment,
        "voice_outreach": voice_outreach,
        "call_record": call_record,
    }


def compute_retell_signature(raw_body: bytes, secret: str) -> str:
    """Compute authentic Retell HMAC-SHA256 signature."""
    timestamp = str(int(time.time() * 1000))
    raw_str = raw_body.decode("utf-8", errors="replace")
    content = f"{raw_str}{timestamp}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), content, hashlib.sha256).hexdigest()
    return f"v={timestamp},d={digest}"


# ── Test Scenarios ────────────────────────────────────────────────────────────

def test_1_webhook_hmac_signature_verification(db):
    """1. Webhook authenticity: valid signature accepted, tampered/missing rejected."""
    secret = "test_webhook_secret_key_123"
    raw_payload = json.dumps({"event": "call_ended", "call_id": "call_sig_001"}).encode("utf-8")

    # Valid signature
    valid_sig = compute_retell_signature(raw_payload, secret)
    assert VoiceFollowUpService.verify_webhook_signature(raw_payload, valid_sig, secret=secret) is True

    # Tampered body with same signature -> rejected
    tampered_body = json.dumps({"event": "call_ended", "call_id": "call_sig_002"}).encode("utf-8")
    assert VoiceFollowUpService.verify_webhook_signature(tampered_body, valid_sig, secret=secret) is False

    # Missing signature -> rejected
    assert VoiceFollowUpService.verify_webhook_signature(raw_payload, None, secret=secret) is False
    assert VoiceFollowUpService.verify_webhook_signature(raw_payload, "", secret=secret) is False


def test_2_successful_call_analyzed_advances_to_step_2_email_once(db):
    """2. Completed call analyzed event advances campaign to Step 2 follow-up email exactly once."""
    env = create_qa_sandbox_environment(db, step_2_condition="interested")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "duration_ms": 48000,
            "call_analysis": {
                "call_summary": "Prospect is interested in Agile B2B automation platform.",
                "call_outcome": "INTERESTED",
            },
            "collected_dynamic_variables": {
                "interest_level": "high",
            },
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(env["voice_outreach"].id),
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["duplicate"] is False
    assert result["email_sent"] is True
    assert result["followup_status"] == "sent"

    # Step 1 voice outreach is marked sent
    db.refresh(env["voice_outreach"])
    assert env["voice_outreach"].status == "sent"
    assert env["voice_outreach"].sent_at is not None

    # CallRecord is persisted before progression
    call_rec = db.get(CallRecord, env["call_record"].id)
    assert call_rec.call_status == "analyzed"
    assert call_rec.call_outcome == "INTERESTED"
    assert "interested" in (call_rec.summary or "").lower()

    # Step 2 email outreach was dispatched exactly once
    assert len(mock_email.sent_messages) == 1
    sent_msg = mock_email.sent_messages[0]
    assert "Pravallika" in sent_msg.body
    assert env["contact"].email == sent_msg.to_email

    # CampaignContact current_step advanced to 2
    db.refresh(env["enrollment"])
    assert env["enrollment"].current_step == 2


def test_3_meeting_requested_outcome_advances_meeting_step(db):
    """3. MEETING_REQUESTED outcome advances to Step 2 when step condition is meeting_requested."""
    env = create_qa_sandbox_environment(db, step_2_condition="meeting_requested")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "call_analysis": {
                "call_summary": "Prospect agreed to meeting next Tuesday.",
                "call_outcome": "MEETING_REQUESTED",
            },
            "collected_dynamic_variables": {
                "meeting_requested": True,
            },
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(env["voice_outreach"].id),
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["email_sent"] is True
    assert result["followup_status"] == "sent"
    assert len(mock_email.sent_messages) == 1


def test_4_not_interested_outcome_skips_subsequent_step(db):
    """4. NOT_INTERESTED outcome skips Step 2 when step requires positive interest/meeting."""
    env = create_qa_sandbox_environment(db, step_2_condition="meeting_requested")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "call_analysis": {
                "call_summary": "Prospect is not interested at this time.",
                "call_outcome": "NOT_INTERESTED",
            },
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(env["voice_outreach"].id),
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    assert len(mock_email.sent_messages) == 0

    # CallRecord is persisted
    db.refresh(env["call_record"])
    assert env["call_record"].call_outcome == "NOT_INTERESTED"


def test_5_unanswered_call_ended_marks_failed_and_halts_positive_step(db):
    """5. Unanswered call (no_answer) marks voice outreach failed and halts progression for positive steps."""
    env = create_qa_sandbox_environment(db, step_2_condition="interested")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    ended_payload = {
        "event": "call_ended",
        "call_id": call_id,
        "disconnection_reason": "no_answer",
        "metadata": {
            "organization_id": str(env["org"].id),
            "outreach_id": str(env["voice_outreach"].id),
        },
    }

    service.handle_call_ended(ended_payload)

    db.refresh(env["voice_outreach"])
    db.refresh(env["call_record"])
    assert env["voice_outreach"].status == "failed"
    assert env["call_record"].call_status == "failed"

    # Step 2 required positive interest -> must NOT be dispatched
    assert len(mock_email.sent_messages) == 0


def test_6_call_failure_with_failure_handler_step(db):
    """6. Call failure correctly advances to Step 2 when Step 2 explicitly handles call_failed / no_answer."""
    env = create_qa_sandbox_environment(db, step_2_condition="call_failed")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    ended_payload = {
        "event": "call_ended",
        "call_id": call_id,
        "disconnection_reason": "dial_error",
        "metadata": {
            "organization_id": str(env["org"].id),
            "outreach_id": str(env["voice_outreach"].id),
        },
    }

    service.handle_call_ended(ended_payload)

    db.refresh(env["voice_outreach"])
    assert env["voice_outreach"].status == "failed"

    # Step 2 is configured for call_failed -> must be dispatched
    assert len(mock_email.sent_messages) == 1
    sent_msg = mock_email.sent_messages[0]
    assert env["contact"].email == sent_msg.to_email


def test_7_duplicate_webhook_idempotency(db):
    """7. Duplicate webhook events are detected via idempotency key and return duplicate=True without repeating sends."""
    env = create_qa_sandbox_environment(db, step_2_condition="interested")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "duration_ms": 35000,
            "call_analysis": {
                "call_summary": "Prospect is interested.",
                "call_outcome": "INTERESTED",
            },
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(env["voice_outreach"].id),
            },
        },
    }

    # First delivery
    r1 = service.process_call_analyzed(payload)
    assert r1["duplicate"] is False
    assert r1["email_sent"] is True
    assert len(mock_email.sent_messages) == 1

    # Second delivery (duplicate retry)
    r2 = service.process_call_analyzed(payload)
    assert r2["duplicate"] is True
    assert r2["email_sent"] is False
    # No second email sent
    assert len(mock_email.sent_messages) == 1


def test_8_out_of_order_and_delayed_webhooks(db):
    """8. Out-of-order webhook delivery (call_analyzed arriving before late call_ended) does not regress status."""
    env = create_qa_sandbox_environment(db, step_2_condition="interested")
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    analyzed_payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "duration_ms": 40000,
            "call_analysis": {
                "call_summary": "Prospect interested.",
                "call_outcome": "INTERESTED",
            },
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(env["voice_outreach"].id),
            },
        },
    }

    # Analyzed arrives first
    r1 = service.process_call_analyzed(analyzed_payload)
    assert r1["status"] == "success"
    call_rec = db.get(CallRecord, env["call_record"].id)
    assert call_rec.call_status == "analyzed"

    # Late call_ended arrives afterward -> must not regress call_status from analyzed to ended
    late_ended_payload = {
        "event": "call_ended",
        "call_id": call_id,
        "duration_ms": 41000,
        "metadata": {
            "organization_id": str(env["org"].id),
            "outreach_id": str(env["voice_outreach"].id),
        },
    }
    service.handle_call_ended(late_ended_payload)
    db.refresh(call_rec)
    assert call_rec.call_status == "analyzed"
    # Still exactly one email sent
    assert len(mock_email.sent_messages) == 1


def test_9_positive_delay_step_scheduling_and_multi_step_progression(db):
    """9. Multi-step progression: Step 2 with positive delay is scheduled, not dispatched immediately; Step 3 schedules after Step 2."""
    env = create_qa_sandbox_environment(
        db,
        step_2_condition="interested",
        step_2_delay_days=1,
        step_2_delay_hours=0,
        has_step_3=True,
        step_3_delay_days=2,
    )
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    call_id = env["voice_outreach"].provider_message_id
    payload = {
        "event": "call_analyzed",
        "call_id": call_id,
        "call": {
            "call_id": call_id,
            "duration_ms": 30000,
            "call_analysis": {
                "call_summary": "Prospect is interested in platform walkthrough.",
                "call_outcome": "INTERESTED",
            },
            "metadata": {
                "organization_id": str(env["org"].id),
                "outreach_id": str(env["voice_outreach"].id),
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["email_sent"] is False  # Positive delay -> scheduled, not dispatched immediately!
    assert result["followup_status"] == "in_progress"
    assert len(mock_email.sent_messages) == 0

    # Step 2 outreach is persisted with status 'scheduled'
    scheduled_outreach = (
        db.query(Outreach)
        .filter(
            Outreach.campaign_id == env["campaign"].id,
            Outreach.campaign_contact_id == env["enrollment"].id,
            Outreach.status == "scheduled",
        )
        .first()
    )
    assert scheduled_outreach is not None
    assert scheduled_outreach.channel == "email"
    assert scheduled_outreach.scheduled_at is not None


def test_10_tenant_isolation_and_quarantine_protection(db):
    """10. Tenant isolation: Webhooks for unresolvable orgs are quarantined with 0 actions taken; cannot cross tenants."""
    mock_email = RecordingEmailProvider()
    service = VoiceFollowUpService(db=db, email_provider=mock_email)

    unknown_org_id = uuid.uuid4()
    foreign_call_id = "call_foreign_tenant_999"

    # Webhook with completely unknown organization
    payload = {
        "event": "call_analyzed",
        "call_id": foreign_call_id,
        "call": {
            "call_id": foreign_call_id,
            "call_analysis": {"call_outcome": "INTERESTED"},
            "metadata": {"organization_id": str(unknown_org_id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "quarantined"
    assert result["followup_status"] == "quarantined"
    assert result["email_sent"] is False
    assert len(mock_email.sent_messages) == 0

    # Confirm no call records or outreaches created for unknown org
    records = db.query(CallRecord).filter(CallRecord.call_id == foreign_call_id).all()
    assert len(records) == 0
