"""Comprehensive test suite for the Campaign Workflow Execution Engine (Scenarios A through J).

Verifies shared workflow execution infrastructure across Email, Voice, SMS, and multi-step cadences.
Targets the official Agile QA Sandbox organization (c0aae7f1-95bb-485f-bb9b-e3ed95469912).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.core.qa_safeguard import QA_SANDBOX_ORG_ID, QA_SANDBOX_SLUG
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization
from app.services.campaign_scheduler import (
    CampaignSchedulerService,
    _ensure_utc,
    advance_campaign_contact_sequence,
    check_and_update_campaign_completion,
)
from app.services.outreach.base import (
    EmailMessage,
    EmailSendResult,
    MockEmailProvider,
)
from app.services.outreach.service import send_outreach
from app.services.voice.service import (
    complete_simulated_voice_call,
    send_voice_outreach,
)


class RecordingMockEmailProvider(MockEmailProvider):
    """Mock email provider that records sent messages and supports selective per-recipient failure."""

    def __init__(
        self,
        should_fail: bool = False,
        failure_reason: Optional[str] = None,
        failing_recipients: Optional[List[str]] = None,
    ) -> None:
        super().__init__(should_fail=should_fail, failure_reason=failure_reason)
        self.sent_messages: List[EmailMessage] = []
        self.failing_recipients: List[str] = failing_recipients or []

    def send(self, message: EmailMessage) -> EmailSendResult:
        if self._should_fail or (message.to_email in self.failing_recipients):
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=self._failure_reason or f"Simulated delivery failure for {message.to_email}",
            )
        res = super().send(message)
        if res.success:
            self.sent_messages.append(message)
        return res


@pytest.fixture
def qa_db():
    """Isolated in-memory database initialized with the official QA Sandbox Organization."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    qa_org = Organization(
        id=QA_SANDBOX_ORG_ID,
        name="Agile QA Sandbox",
        slug=QA_SANDBOX_SLUG,
    )
    session.add(qa_org)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ── Helper Setup ─────────────────────────────────────────────────────────────

def setup_campaign_with_steps(
    db: Session,
    org_id: uuid.UUID,
    campaign_name: str,
    step_configs: List[dict],
) -> Campaign:
    """Creates a campaign and associates specified steps."""
    nodes = [{"id": "start-node", "type": "start", "title": "Start", "config": {}, "position": {"x": 250, "y": 50}}]
    edges = []
    prev_id = "start-node"
    has_non_email = any(cfg.get("step_type", "email") != "email" for cfg in step_configs)

    for idx, cfg in enumerate(step_configs, start=1):
        stype = cfg.get("step_type", "email")
        node_id = f"step-{idx}"
        nodes.append({
            "id": node_id,
            "type": stype,
            "title": cfg.get("subject", f"Step {idx}"),
            "config": {
                "step_number": idx,
                "subject": cfg.get("subject", f"Subject Step {idx}"),
                "body": cfg.get("body", f"Body Step {idx} for {{contact.first_name}}"),
                "delay_days": cfg.get("delay_days", 0),
                "delay_hours": cfg.get("delay_hours", 0),
                "is_active": True,
            },
            "position": {"x": 250, "y": 50 + idx * 100},
        })
        edges.append({
            "id": f"edge-{prev_id}-{node_id}",
            "source": prev_id,
            "target": node_id,
        })
        prev_id = node_id

    camp = Campaign(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=campaign_name,
        status="active",
        type="sales_outbound",
        workflow_config={"nodes": nodes, "edges": edges},
    )
    db.add(camp)
    db.flush()

    if not has_non_email:
        steps = []
        for idx, cfg in enumerate(step_configs, start=1):
            step = CampaignStep(
                id=uuid.uuid4(),
                organization_id=org_id,
                campaign_id=camp.id,
                step_number=idx,
                step_type=cfg.get("step_type", "email"),
                subject_template=cfg.get("subject", f"Subject Step {idx}"),
                body_template=cfg.get("body", f"Body Step {idx} for {{contact.first_name}}"),
                delay_days=cfg.get("delay_days", 0),
                delay_hours=cfg.get("delay_hours", 0),
                is_active=True,
            )
            steps.append(step)
        db.add_all(steps)
        db.flush()

    return camp


def enroll_contact(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    email: str,
    first_name: str = "Test",
    last_name: str = "User",
    phone: Optional[str] = "+15551234567",
) -> tuple[Contact, CampaignContact]:
    """Creates a contact in QA Org and enrolls into target campaign."""
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        lead_status="new",
    )
    db.add(contact)
    db.flush()

    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
        enrolled_at=datetime.now(timezone.utc),
    )
    db.add(cc)
    db.flush()
    return contact, cc


# ── Scenario Tests ────────────────────────────────────────────────────────────

def test_scenario_a_three_email_steps_with_zero_delays(qa_db):
    """
    Scenario A: Three email steps with zero delays.
    Step 1 -> Zero delay -> Step 2 -> Zero delay -> Step 3.
    Verifies that all three steps execute sequentially without artificial delay,
    and transitions enrollment and campaign to 'completed'.
    """
    provider = RecordingMockEmailProvider()
    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario A Zero Delay Cadence",
        [
            {"step_type": "email", "subject": "Intro", "body": "Hello {contact.first_name}", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "Follow-up", "body": "Following up", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "Final", "body": "Final note", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "alice_zero@example.com", "Alice")

    # Create initial Step 1 Outreach
    o1 = Outreach(
        id=uuid.uuid4(),
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="draft",
        subject="Intro",
        body="Hello Alice",
        recipient="alice_zero@example.com",
    )
    qa_db.add(o1)
    qa_db.commit()

    # User or executor clicks Send on Step 1
    sent_o1 = send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=provider)
    assert sent_o1.status == "sent"

    # Refresh records
    qa_db.refresh(cc)
    qa_db.refresh(camp)

    # All 3 steps executed sequentially in this single execution
    assert len(provider.sent_messages) == 3
    assert provider.sent_messages[0].subject == "Intro"
    assert provider.sent_messages[1].subject == "Follow-up"
    assert provider.sent_messages[2].subject == "Final"

    outreaches = (
        qa_db.query(Outreach)
        .filter(Outreach.campaign_contact_id == cc.id)
        .order_by(Outreach.created_at.asc())
        .all()
    )
    assert len(outreaches) == 3
    for o in outreaches:
        assert o.status == "sent"
        assert o.sent_at is not None

    # Exhausted -> Enrollment and Campaign marked completed
    assert cc.enrollment_status == "completed"
    assert cc.current_step == 3
    assert camp.status == "completed"


def test_scenario_b_three_email_steps_with_configured_delays(qa_db):
    """
    Scenario B: Three email steps with configured delays.
    Step 1 (0 delay) -> Step 2 (1 day delay) -> Step 3 (2 days delay).
    Verifies that delayed steps respect wait periods and only advance when due.
    """
    provider = RecordingMockEmailProvider()
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)

    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario B Delayed Cadence",
        [
            {"step_type": "email", "subject": "Step 1", "body": "Body 1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "Step 2", "body": "Body 2", "delay_days": 1, "delay_hours": 0},
            {"step_type": "email", "subject": "Step 3", "body": "Body 3", "delay_days": 2, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "bob_delayed@example.com", "Bob")

    o1 = Outreach(
        id=uuid.uuid4(),
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="draft",
        subject="Step 1",
        body="Body 1",
        recipient="bob_delayed@example.com",
    )
    qa_db.add(o1)
    qa_db.commit()

    # Dispatch Step 1 at t0
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=provider, sent_at=t0)
    qa_db.refresh(cc)

    # Step 2 has 1-day delay: must be scheduled for t0 + 1 day, NOT sent immediately
    assert len(provider.sent_messages) == 1
    assert cc.current_step == 2
    assert cc.enrollment_status == "in_progress"

    outreaches = qa_db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).all()
    assert len(outreaches) == 2
    o2 = [o for o in outreaches if o.id != o1.id][0]
    assert o2.status == "scheduled"
    assert _ensure_utc(o2.scheduled_at) == t0 + timedelta(days=1)

    # Scheduler tick at t0 + 12 hours: Step 2 delay not elapsed -> remains scheduled
    service = CampaignSchedulerService(db=qa_db)
    t_half = t0 + timedelta(hours=12)
    res_half = service.tick(now=t_half, org_id=QA_SANDBOX_ORG_ID, force=True, auto_dispatch=True, provider=provider)
    assert res_half.dispatched_count == 0
    assert len(provider.sent_messages) == 1

    # Scheduler tick at t0 + 1 day + 5 mins: Step 2 is due -> dispatches Step 2, schedules Step 3
    t1 = t0 + timedelta(days=1, minutes=5)
    res1 = service.tick(now=t1, org_id=QA_SANDBOX_ORG_ID, force=True, auto_dispatch=True, provider=provider)
    assert res1.dispatched_count == 1
    assert len(provider.sent_messages) == 2

    qa_db.refresh(cc)
    assert cc.current_step == 3
    outreaches_3 = qa_db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).all()
    assert len(outreaches_3) == 3
    o3 = [o for o in outreaches_3 if o.id not in (o1.id, o2.id)][0]
    assert o3.status == "scheduled"

    # Scheduler tick at t1 + 2 days + 5 mins: Step 3 is due -> dispatches Step 3, sequence completes
    t2 = t1 + timedelta(days=2, minutes=5)
    res2 = service.tick(now=t2, org_id=QA_SANDBOX_ORG_ID, force=True, auto_dispatch=True, provider=provider)
    assert res2.dispatched_count == 1
    assert len(provider.sent_messages) == 3

    qa_db.refresh(cc)
    qa_db.refresh(camp)
    assert cc.enrollment_status == "completed"
    assert camp.status == "completed"


def test_scenario_c_mixed_zero_and_nonzero_delays(qa_db):
    """
    Scenario C: Mixed zero-delay and non-zero-delay steps.
    Step 1 (0 delay) -> Step 2 (2 days delay) -> Step 3 (0 delay).
    Verifies that Step 1 executes, Step 2 is scheduled, and when Step 2 dispatches,
    Step 3 (zero delay) follows immediately.
    """
    provider = RecordingMockEmailProvider()
    t0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)

    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario C Mixed Delays",
        [
            {"step_type": "email", "subject": "S1 Immediate", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S2 Wait 2 Days", "body": "B2", "delay_days": 2, "delay_hours": 0},
            {"step_type": "email", "subject": "S3 Immediate After S2", "body": "B3", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "charlie_mixed@example.com", "Charlie")

    o1 = Outreach(
        id=uuid.uuid4(),
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="draft",
        subject="S1 Immediate",
        body="B1",
        recipient="charlie_mixed@example.com",
    )
    qa_db.add(o1)
    qa_db.commit()

    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=provider, sent_at=t0)

    # Step 1 sent; Step 2 scheduled
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0].subject == "S1 Immediate"

    # Advance time to t0 + 2 days + 1 min and run scheduler tick
    t1 = t0 + timedelta(days=2, minutes=1)
    service = CampaignSchedulerService(db=qa_db)
    service.tick(now=t1, org_id=QA_SANDBOX_ORG_ID, force=True, auto_dispatch=True, provider=provider)

    # Step 2 dispatched AND Step 3 (0 delay) immediately chained!
    assert len(provider.sent_messages) == 3
    assert provider.sent_messages[1].subject == "S2 Wait 2 Days"
    assert provider.sent_messages[2].subject == "S3 Immediate After S2"

    qa_db.refresh(cc)
    assert cc.enrollment_status == "completed"


def test_scenario_d_multiple_recipients_acceptance_and_rejection(qa_db):
    """
    Scenario D: Multiple recipients, including simulated provider acceptance and rejection.
    Verifies that a provider error on Recipient 2 halts Recipient 2 without blocking Recipient 1.
    """
    provider = RecordingMockEmailProvider(failing_recipients=["bad_provider_fail@example.com"])
    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario D Multi Recipient",
        [
            {"step_type": "email", "subject": "S1", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S2", "body": "B2", "delay_days": 0, "delay_hours": 0},
        ],
    )
    c1, cc1 = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "good_recipient@example.com", "Good")
    c2, cc2 = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "bad_provider_fail@example.com", "Bad")

    o1 = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=c1.id, campaign_contact_id=cc1.id, channel="email", status="draft", subject="S1", body="B1", recipient="good_recipient@example.com")
    o2 = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=c2.id, campaign_contact_id=cc2.id, channel="email", status="draft", subject="S1", body="B1", recipient="bad_provider_fail@example.com")
    qa_db.add_all([o1, o2])
    qa_db.commit()

    # Send o1 -> succeeds and zero-delay executes Step 2
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=provider)
    qa_db.refresh(cc1)
    assert cc1.enrollment_status == "completed"

    # Send o2 -> provider rejects -> status becomes failed
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o2.id, provider=provider, raise_on_failure=False)
    qa_db.refresh(o2)
    qa_db.refresh(cc2)
    assert o2.status == "failed"
    assert cc2.enrollment_status == "in_progress"
    assert cc2.current_step == 1  # Did not advance


def test_scenario_e_failed_intermediate_step_and_subsequent_retry(qa_db):
    """
    Scenario E: Failed intermediate step and subsequent retry.
    Step 1 sent. Step 2 fails delivery.
    Outreach is in 'failed' status. Sequence stops.
    When Step 2 is retried with healthy provider, Step 2 succeeds and Step 3 immediately follows.
    """
    failing_provider = RecordingMockEmailProvider(should_fail=True)
    healthy_provider = RecordingMockEmailProvider()

    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario E Retry Cadence",
        [
            {"step_type": "email", "subject": "S1", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S2", "body": "B2", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S3", "body": "B3", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "retry_user@example.com", "RetryUser")

    o1 = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="draft", subject="S1", body="B1", recipient="retry_user@example.com")
    qa_db.add(o1)
    qa_db.commit()

    # Step 1 sent with healthy provider, but Step 2 auto-dispatch encounters failing provider
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=healthy_provider, auto_advance_sequence=False)
    
    # Trigger advance with failing provider on Step 2
    actions = advance_campaign_contact_sequence(qa_db, cc.id, org_id=QA_SANDBOX_ORG_ID, email_provider=failing_provider, auto_dispatch=True)
    assert any(a.get("action") == "failed" for a in actions)

    # Step 2 outreach is in failed state
    o2 = (
        qa_db.query(Outreach)
        .filter(Outreach.campaign_contact_id == cc.id)
        .order_by(Outreach.created_at.desc())
        .first()
    )
    assert o2.id != o1.id
    assert o2.status == "failed"

    qa_db.refresh(cc)
    assert cc.enrollment_status == "in_progress"
    assert cc.current_step == 2

    # Now simulate recovery/retry of Step 2 with healthy provider:
    # Reset status to draft for retry execution
    o2.status = "draft"
    qa_db.commit()

    # Retry Step 2: succeeds and immediately advances zero-delay Step 3!
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o2.id, provider=healthy_provider, auto_advance_sequence=True)

    qa_db.refresh(cc)
    qa_db.refresh(camp)
    assert cc.enrollment_status == "completed"
    assert camp.status == "completed"
    assert len(healthy_provider.sent_messages) == 3


def test_scenario_f_duplicate_scheduler_execution(qa_db):
    """
    Scenario F: Duplicate scheduler execution (Idempotency).
    Executing advance_campaign_contact_sequence multiple times on the same state
    produces zero duplicate outreaches or external messages.
    """
    provider = RecordingMockEmailProvider()
    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario F Idempotency",
        [
            {"step_type": "email", "subject": "S1", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S2", "body": "B2", "delay_days": 1, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "idemp@example.com", "Idemp")
    o1 = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="draft", subject="S1", body="B1", recipient="idemp@example.com")
    qa_db.add(o1)
    qa_db.commit()

    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=provider)
    assert len(provider.sent_messages) == 1

    # Call advance multiple times repeatedly
    for _ in range(5):
        advance_campaign_contact_sequence(qa_db, cc.id, org_id=QA_SANDBOX_ORG_ID, email_provider=provider, auto_dispatch=True)

    # Exactly 2 outreaches exist (1 sent, 1 scheduled)
    outreaches = qa_db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).all()
    assert len(outreaches) == 2
    assert len(provider.sent_messages) == 1


def test_scenario_g_worker_interruption_and_recovery(qa_db):
    """
    Scenario G: Worker interruption and recovery.
    Simulate worker crash after Step 1 is sent (o1 sent, Step 2 not yet planned).
    When the scheduler runs, it detects the eligible unexecuted Step 2 and advances.
    """
    provider = RecordingMockEmailProvider()
    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario G Recovery",
        [
            {"step_type": "email", "subject": "S1", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S2", "body": "B2", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "crashed_worker@example.com", "Crash")

    # Step 1 manually marked sent (as if worker sent it then crashed before scheduling step 2)
    o1 = Outreach(
        id=uuid.uuid4(),
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        subject="S1",
        body="B1",
        recipient="crashed_worker@example.com",
        sent_at=datetime.now(timezone.utc),
    )
    qa_db.add(o1)
    qa_db.commit()

    # Recovery: scheduler tick runs
    service = CampaignSchedulerService(db=qa_db)
    res = service.tick(org_id=QA_SANDBOX_ORG_ID, force=True, auto_dispatch=True, provider=provider)

    qa_db.refresh(cc)
    assert cc.enrollment_status == "completed"
    assert cc.current_step == 2
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0].subject == "S2"


def test_scenario_h_voice_call_campaign_progression(qa_db):
    """
    Scenario H: Voice-call campaign progression.
    Step 1 (Voice SDR Call) -> Step 2 (Follow-up Email, zero delay).
    Verifies that Step 2 advances only after the voice call completes with positive outcome.
    """
    mock_email = RecordingMockEmailProvider()
    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario H Voice to Email",
        [
            {"step_type": "voice", "subject": "Voice Call", "body": "Voice script", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "Email Follow-up", "body": "Thanks for speaking with us", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "voice_prospect@example.com", "VoiceUser", phone="+14155550199")

    # Create Step 1 Voice Outreach
    o_voice = Outreach(
        id=uuid.uuid4(),
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="voice",
        status="draft",
        subject="Voice Call",
        body="Voice script",
        recipient="+14155550199",
    )
    qa_db.add(o_voice)
    qa_db.commit()

    # 1. Initiate Voice call -> transitions to 'sending'
    send_voice_outreach(qa_db, QA_SANDBOX_ORG_ID, o_voice.id, force_mock=True)
    qa_db.refresh(o_voice)
    assert o_voice.status == "sending"

    # Step 2 has not executed because call is still in progress
    assert len(mock_email.sent_messages) == 0

    # 2. Simulate call completion with INTERESTED outcome
    comp_res = complete_simulated_voice_call(
        db=qa_db,
        org_id=QA_SANDBOX_ORG_ID,
        outreach_id=o_voice.id,
        outcome="INTERESTED",
        email_provider=mock_email,
    )
    assert comp_res.status == "success"

    qa_db.refresh(o_voice)
    qa_db.refresh(cc)
    assert o_voice.status == "sent"

    # Step 2 (Email) was executed upon voice call completion!
    qa_db.refresh(camp)
    assert cc.enrollment_status == "completed"
    assert camp.status == "completed"


def test_scenario_i_campaign_completion_after_final_step(qa_db):
    """
    Scenario I: Campaign completion after the final step.
    When the last enrolled contact finishes their sequence, campaign status transitions to 'completed'.
    """
    provider = RecordingMockEmailProvider()
    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario I Completion",
        [
            {"step_type": "email", "subject": "Single Step", "body": "B", "delay_days": 0, "delay_hours": 0},
        ],
    )
    c1, cc1 = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "user1@example.com", "U1")
    c2, cc2 = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "user2@example.com", "U2")

    o1 = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=c1.id, campaign_contact_id=cc1.id, channel="email", status="draft", subject="Single Step", body="B", recipient="user1@example.com")
    o2 = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=c2.id, campaign_contact_id=cc2.id, channel="email", status="draft", subject="Single Step", body="B", recipient="user2@example.com")
    qa_db.add_all([o1, o2])
    qa_db.commit()

    # User 1 finishes -> campaign remains active because User 2 is in_progress
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o1.id, provider=provider)
    qa_db.refresh(camp)
    assert camp.status == "active"

    # User 2 finishes -> all contacts terminal -> campaign transitions to completed!
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, o2.id, provider=provider)
    qa_db.refresh(camp)
    assert camp.status == "completed"


def test_scenario_j_recipient_level_failure_without_stopping_others(qa_db):
    """
    Scenario J: Recipient-level failure without incorrectly stopping other recipients.
    Contact A (success), Contact B (failure), Contact C (opt-out).
    Verifies that failures on B and opt-out on C never impede A's complete progression.
    """
    failing_list = ["recipient_b_fails@example.com"]
    provider = RecordingMockEmailProvider(failing_recipients=failing_list)

    camp = setup_campaign_with_steps(
        qa_db,
        QA_SANDBOX_ORG_ID,
        "Scenario J Multi Outcome",
        [
            {"step_type": "email", "subject": "S1", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"step_type": "email", "subject": "S2", "body": "B2", "delay_days": 0, "delay_hours": 0},
        ],
    )
    cA, ccA = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "recipient_a_good@example.com", "A")
    cB, ccB = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "recipient_b_fails@example.com", "B")
    cC, ccC = enroll_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "recipient_c_optout@example.com", "C")
    # Mark C opted out
    cC.lead_status = "opted_out"
    qa_db.commit()

    oA = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=cA.id, campaign_contact_id=ccA.id, channel="email", status="draft", subject="S1", body="B1", recipient="recipient_a_good@example.com")
    oB = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=cB.id, campaign_contact_id=ccB.id, channel="email", status="draft", subject="S1", body="B1", recipient="recipient_b_fails@example.com")
    oC = Outreach(id=uuid.uuid4(), organization_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, contact_id=cC.id, campaign_contact_id=ccC.id, channel="email", status="draft", subject="S1", body="B1", recipient="recipient_c_optout@example.com")
    qa_db.add_all([oA, oB, oC])
    qa_db.commit()

    # 1. Contact A executes Step 1 -> advances through Step 2 -> completes!
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, oA.id, provider=provider)
    qa_db.refresh(ccA)
    assert ccA.enrollment_status == "completed"

    # 2. Contact B executes Step 1 -> fails -> stops at Step 1
    send_outreach(qa_db, QA_SANDBOX_ORG_ID, oB.id, provider=provider, raise_on_failure=False)
    qa_db.refresh(oB)
    qa_db.refresh(ccB)
    assert oB.status == "failed"
    assert ccB.enrollment_status == "in_progress"
    assert ccB.current_step == 1

    # 3. Contact C attempts Step 1 -> suppressed due to opt-out
    with pytest.raises(Exception):
        send_outreach(qa_db, QA_SANDBOX_ORG_ID, oC.id, provider=provider, raise_on_failure=True)
    qa_db.refresh(oC)
    assert oC.status == "cancelled"

    # Contact A's 2 emails were delivered cleanly regardless of B's failure or C's opt-out
    sent_to_a = [m for m in provider.sent_messages if m.to_email == "recipient_a_good@example.com"]
    assert len(sent_to_a) == 2
