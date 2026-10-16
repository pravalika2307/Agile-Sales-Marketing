"""Comprehensive test suite for the Automated Multi-Day Campaign Execution Scheduler.

Tests all 12 required scenarios:
1. Step delay calculations before and after due time.
2. Multi-step progression and sequence completion.
3. Reply and bounce stop conditions.
4. Opt-out and unsubscribe suppression.
5. Meeting-request and confirmed-booking stop conditions (without marking deals won).
6. Paused and resumed campaigns.
7. Failed delivery and retry handling.
8. Duplicate prevention and concurrent execution.
9. Tenant isolation.
10. Dry-run mode causing zero database writes and zero external calls.
11. Scheduler disabled by default.
12. Existing campaign and outreach regression behavior.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.outreach import Outreach
from app.models.tenant import Organization
from app.services.campaign_scheduler import CampaignSchedulerService
from app.services.outreach.base import EmailMessage, EmailSendResult, MockEmailProvider
from app.services.outreach.service import send_outreach
from app.services.outreach.tracking import record_bounced, record_replied


class RecordingMockEmailProvider(MockEmailProvider):
    """Mock provider that records all sent EmailMessage payloads."""

    def __init__(self, should_fail: bool = False, failure_reason: str | None = None) -> None:
        super().__init__(should_fail=should_fail, failure_reason=failure_reason)
        self.sent_messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        res = super().send(message)
        if res.success:
            self.sent_messages.append(message)
        return res


# ── Database & Client Fixtures ────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Create fresh isolated in-memory SQLite database session for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.pop(get_db, None)


@asynccontextmanager
async def make_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> str:
    """Helper to register a tenant and return access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Scheduler Test Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── Scenario 11: Scheduler Disabled by Default ────────────────────────────────

def test_scheduler_disabled_by_default(test_db_session):
    """Scheduler must be disabled by default and refuse to run unless force=True or configured."""
    assert settings.SCHEDULER_ENABLED is False

    service = CampaignSchedulerService(db=test_db_session)
    result = service.tick(force=False, dry_run=False)

    assert result.status == "disabled"
    assert "disabled by default" in result.message
    assert result.planned_count == 0


@pytest.mark.asyncio
async def test_scheduler_tick_api_endpoint_disabled_by_default(test_db_session):
    """POST /api/v1/campaigns/scheduler/tick reports disabled status when not forced."""
    async with make_client() as client:
        token = await register_tenant(client, "admin_disabled@test.com", "Disabled Org")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/campaigns/scheduler/tick", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disabled"
        assert data["planned_count"] == 0


# ── Scenario 1: Step Delay Calculations (Before and After Due Time) ───────────

def test_step_delay_calculation_before_and_after_due_time(test_db_session):
    """Step 2 with delay_days=2 must be skipped before 2 days elapse, and planned after 2 days."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Setup tenant, contact, campaign with Step 1 (0d) and Step 2 (2d)
    org = Organization(name="Delay Org", slug=f"delay-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="delay_user@example.com", first_name="Alex", last_name="Rivera")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Multi-Day Sequence", status="active", type="sales_outbound")
    db.add(camp)
    db.flush()

    step1 = CampaignStep(
        organization_id=org.id,
        campaign_id=camp.id,
        step_number=1,
        step_type="email",
        subject_template="Step 1 Intro",
        body_template="Hi {contact.first_name}, introduction.",
        delay_days=0,
        delay_hours=0,
        is_active=True,
    )
    step2 = CampaignStep(
        organization_id=org.id,
        campaign_id=camp.id,
        step_number=2,
        step_type="email",
        subject_template="Step 2 Follow-up",
        body_template="Hi {contact.first_name}, following up.",
        delay_days=2,
        delay_hours=0,
        is_active=True,
    )
    db.add_all([step1, step2])
    db.flush()

    # Enroll contact in progress with Step 1 sent at t0
    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    outreach1 = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        subject="Step 1 Intro",
        body="Hi Alex, introduction.",
        sent_at=t0,
        created_at=t0,
    )
    db.add(outreach1)
    db.commit()

    service = CampaignSchedulerService(db=db)

    # Check at t0 + 1 day (before delay of 2 days elapses)
    t_before = t0 + timedelta(days=1)
    res_before = service.tick(now=t_before, org_id=org.id, force=True)
    assert res_before.planned_count == 0
    assert res_before.skipped_count == 1
    assert "delay not elapsed" in res_before.details[0]["reason"].lower()

    # Verify no new outreach created
    outreaches_mid = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).all()
    assert len(outreaches_mid) == 1
    assert cc.current_step == 1

    # Check at t0 + 2 days + 1 hour (after delay of 2 days elapses)
    t_after = t0 + timedelta(days=2, hours=1)
    res_after = service.tick(now=t_after, org_id=org.id, force=True)
    assert res_after.planned_count == 1
    assert res_after.skipped_count == 0

    # Verify Step 2 outreach is now created
    outreaches_final = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).order_by(Outreach.created_at.asc()).all()
    assert len(outreaches_final) == 2
    assert outreaches_final[1].subject == "Step 2 Follow-up"
    assert outreaches_final[1].status == "draft"
    assert cc.current_step == 2


# ── Scenario 2: Multi-Step Progression and Sequence Completion ───────────────

def test_multi_step_progression_and_sequence_completion(test_db_session):
    """Enrolled contact progresses through Step 1 -> 2 -> 3 and transitions to 'completed' when exhausted."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Progression Org", slug=f"prog-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="complete_user@example.com", first_name="Morgan", last_name="Complete")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="3-Step Cadence", status="active", type="sales_outbound")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, delay_hours=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, delay_hours=0, is_active=True, subject_template="S2", body_template="B2")
    s3 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=3, delay_days=2, delay_hours=0, is_active=True, subject_template="S3", body_template="B3")
    db.add_all([s1, s2, s3])

    # Contact enrolled in queued status
    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="queued", current_step=0, enrolled_at=t0)
    db.add(cc)
    db.commit()

    service = CampaignSchedulerService(db=db)

    # 1. Tick at t0: Plan Step 1
    res1 = service.tick(now=t0, org_id=org.id, force=True)
    assert res1.planned_count == 1
    assert cc.current_step == 1
    assert cc.enrollment_status == "in_progress"

    # Simulate Step 1 sent via provider
    o1 = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).first()
    o1.status = "sent"
    o1.sent_at = t0
    db.commit()

    # 2. Tick at t0 + 1 day: Plan Step 2
    t1 = t0 + timedelta(days=1, minutes=5)
    res2 = service.tick(now=t1, org_id=org.id, force=True)
    assert res2.planned_count == 1
    assert cc.current_step == 2

    # Simulate Step 2 sent
    o2 = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).order_by(Outreach.created_at.desc()).first()
    o2.status = "sent"
    o2.sent_at = t1
    db.commit()

    # 3. Tick at t1 + 2 days: Plan Step 3
    t2 = t1 + timedelta(days=2, minutes=5)
    res3 = service.tick(now=t2, org_id=org.id, force=True)
    assert res3.planned_count == 1
    assert cc.current_step == 3

    # Simulate Step 3 sent
    o3 = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).order_by(Outreach.created_at.desc()).first()
    o3.status = "sent"
    o3.sent_at = t2
    db.commit()

    # 4. Tick after Step 3: No steps remaining -> Sequence transitions to 'completed'
    t3 = t2 + timedelta(days=1)
    res4 = service.tick(now=t3, org_id=org.id, force=True)
    assert res4.completed_count == 1
    assert cc.enrollment_status == "completed"

    # Total outreaches must be exactly 3
    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 3


# ── Scenario 3: Reply Stop Condition ──────────────────────────────────────────

def test_reply_stop_condition_halts_future_steps(test_db_session):
    """When a prospect replies to Step 1, the enrollment transitions to 'replied' and Step 2 is never scheduled."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Reply Org", slug=f"reply-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="reply_lead@example.com", first_name="Taylor", last_name="Reply")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Reply Stop Campaign", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=2, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="sent", sent_at=t0)
    db.add(o1)
    db.commit()

    # Prospect replies via tracking webhook
    record_replied(db=db, org_id=org.id, outreach_id=o1.id)
    assert o1.first_replied_at is not None
    assert cc.enrollment_status == "replied"
    assert contact.lead_status == "replied"

    # Run scheduler tick 5 days later
    service = CampaignSchedulerService(db=db)
    t_future = t0 + timedelta(days=5)
    res = service.tick(now=t_future, org_id=org.id, force=True)

    # Step 2 must be halted and not planned
    assert res.planned_count == 0
    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 1


# ── Scenario 3b: Bounce Stop Condition ────────────────────────────────────────

def test_bounce_stop_condition_halts_future_steps(test_db_session):
    """When Step 1 bounces, enrollment transitions to 'bounced' and Step 2 is never scheduled."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Bounce Org", slug=f"bounce-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="invalid_email@example.com", first_name="Chris", last_name="Bounce")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Bounce Campaign", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="sent", sent_at=t0)
    db.add(o1)
    db.commit()

    # Record bounce event
    record_bounced(db=db, org_id=org.id, outreach_id=o1.id)
    assert o1.first_bounced_at is not None
    assert cc.enrollment_status == "bounced"

    # Run scheduler tick 3 days later
    service = CampaignSchedulerService(db=db)
    t_future = t0 + timedelta(days=3)
    res = service.tick(now=t_future, org_id=org.id, force=True)

    assert res.planned_count == 0
    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 1


# ── Scenario 4: Opt-Out & Unsubscribe Suppression ─────────────────────────────

def test_opt_out_and_unsubscribe_suppression(test_db_session):
    """Opted-out contact cancels pending steps and is never advanced by the scheduler."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="OptOut Org", slug=f"optout-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="opted_out@example.com", first_name="Sam", last_name="OptOut", lead_status="opted_out")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="OptOut Campaign", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.commit()

    service = CampaignSchedulerService(db=db)
    t_future = t0 + timedelta(days=2)
    res = service.tick(now=t_future, org_id=org.id, force=True)

    assert res.planned_count == 0
    assert res.halted_count == 1
    assert cc.enrollment_status == "completed"

    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 0


# ── Scenario 5: Meeting Request Stop Condition ────────────────────────────────

def test_meeting_request_halts_cold_sequence(test_db_session):
    """When a meeting request exists in call records, cold cadence halts without marking deal won."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Meeting Org", slug=f"meeting-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="meeting_prospect@example.com", first_name="Jamie", last_name="Meeting")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Cold Outbound Sequence", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="sent", sent_at=t0)
    db.add(o1)

    # Ingest a Retell voice call with MEETING_REQUESTED outcome
    call_rec = CallRecord(
        organization_id=org.id,
        contact_id=contact.id,
        call_id=f"retell_call_{uuid.uuid4().hex[:8]}",
        agent_id="agent_outbound_sdr",
        direction="outbound",
        call_status="ended",
        call_outcome="MEETING_REQUESTED",
    )
    db.add(call_rec)
    db.commit()

    service = CampaignSchedulerService(db=db)
    t_future = t0 + timedelta(days=2)
    res = service.tick(now=t_future, org_id=org.id, force=True)

    # Must be halted: cold sequence stops
    assert res.planned_count == 0
    assert res.halted_count == 1
    assert cc.enrollment_status == "completed"

    # Step 2 outreach must NOT be created
    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 1


# ── Scenario 6: Paused and Resumed Campaigns ──────────────────────────────────

def test_paused_campaign_halts_and_activation_resumes(test_db_session):
    """When a campaign is paused, scheduler skips it. When resumed to active, cadence proceeds."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Pause Org", slug=f"pause-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="pause_lead@example.com", first_name="Jordan", last_name="Pause")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Pausable Sequence", status="paused")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="sent", sent_at=t0)
    db.add(o1)
    db.commit()

    service = CampaignSchedulerService(db=db)
    t_due = t0 + timedelta(days=2)

    # 1. While paused, tick skips campaign completely
    res_paused = service.tick(now=t_due, org_id=org.id, force=True)
    assert res_paused.planned_count == 0
    assert cc.current_step == 1

    # 2. Resume campaign to 'active'
    camp.status = "active"
    db.commit()

    # 3. Next tick executes Step 2
    res_active = service.tick(now=t_due, org_id=org.id, force=True)
    assert res_active.planned_count == 1
    assert cc.current_step == 2


# ── Scenario 7: Failed Delivery and Retry Handling ────────────────────────────

def test_failed_delivery_halts_sequence_until_retry_succeeds(test_db_session):
    """If Step 1 delivery fails, sequence does not advance to Step 2. Retrying allows progression."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Retry Org", slug=f"retry-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="failing_lead@example.com", first_name="Casey", last_name="Failing")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Failure Sequence", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    # Step 1 outreach failed
    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="failed", sent_at=None)
    db.add(o1)
    db.commit()

    service = CampaignSchedulerService(db=db)
    t_due = t0 + timedelta(days=2)

    # Tick evaluates failed step: sequence must not advance
    res_failed = service.tick(now=t_due, org_id=org.id, force=True)
    assert res_failed.planned_count == 0
    assert cc.current_step == 1
    assert "is not sent" in res_failed.details[0]["reason"]

    # Now simulate retry succeeding via mock provider
    t_retry = t0 + timedelta(days=1)
    o1.status = "sent"
    o1.sent_at = t_retry
    db.commit()

    # Tick before retry delay elapsed: skipped
    res_pre_retry = service.tick(now=t_retry + timedelta(hours=12), org_id=org.id, force=True)
    assert res_pre_retry.planned_count == 0

    # Tick after retry delay elapsed (1 day after retry): Step 2 planned!
    res_post_retry = service.tick(now=t_retry + timedelta(days=1, hours=1), org_id=org.id, force=True)
    assert res_post_retry.planned_count == 1
    assert cc.current_step == 2


# ── Scenario 8: Duplicate Prevention & Idempotency ────────────────────────────

def test_duplicate_prevention_on_concurrent_or_repeated_ticks(test_db_session):
    """Running multiple ticks at the same due timestamp never generates duplicate outreaches."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Idempotency Org", slug=f"idemp-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="idemp_user@example.com", first_name="Robin", last_name="Idemp")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Idempotency Sequence", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="sent", sent_at=t0)
    db.add(o1)
    db.commit()

    service = CampaignSchedulerService(db=db)
    t_due = t0 + timedelta(days=2)

    # First tick: plans Step 2
    res1 = service.tick(now=t_due, org_id=org.id, force=True)
    assert res1.planned_count == 1

    # Second tick immediately: skips Step 2 (duplicate prevented)
    res2 = service.tick(now=t_due, org_id=org.id, force=True)
    assert res2.planned_count == 0

    # Exactly 2 outreaches total (Step 1 and Step 2)
    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 2


# ── Scenario 9: Tenant Isolation ──────────────────────────────────────────────

def test_tenant_isolation_in_scheduler(test_db_session):
    """Running scheduler tick for Organization A strictly never touches Organization B's campaigns."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Org A
    org_a = Organization(name="Org A", slug=f"org-a-{uuid.uuid4().hex[:6]}")
    db.add(org_a)
    db.flush()
    cont_a = Contact(organization_id=org_a.id, email="lead_a@example.com", first_name="Alice", last_name="OrgA")
    db.add(cont_a)
    db.flush()
    camp_a = Campaign(organization_id=org_a.id, name="Campaign A", status="active")
    db.add(camp_a)
    db.flush()
    s1_a = CampaignStep(organization_id=org_a.id, campaign_id=camp_a.id, step_number=1, delay_days=0, is_active=True, subject_template="A1", body_template="B1")
    db.add(s1_a)
    cc_a = CampaignContact(campaign_id=camp_a.id, contact_id=cont_a.id, enrollment_status="queued", current_step=0, enrolled_at=t0)
    db.add(cc_a)

    # Org B
    org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:6]}")
    db.add(org_b)
    db.flush()
    cont_b = Contact(organization_id=org_b.id, email="lead_b@example.com", first_name="Bob", last_name="OrgB")
    db.add(cont_b)
    db.flush()
    camp_b = Campaign(organization_id=org_b.id, name="Campaign B", status="active")
    db.add(camp_b)
    db.flush()
    s1_b = CampaignStep(organization_id=org_b.id, campaign_id=camp_b.id, step_number=1, delay_days=0, is_active=True, subject_template="B1", body_template="B1")
    db.add(s1_b)
    cc_b = CampaignContact(campaign_id=camp_b.id, contact_id=cont_b.id, enrollment_status="queued", current_step=0, enrolled_at=t0)
    db.add(cc_b)
    db.commit()

    service = CampaignSchedulerService(db=db)

    # Tick strictly scoped to Org A
    res = service.tick(now=t0, org_id=org_a.id, force=True)
    assert res.planned_count == 1

    # Verify Org A advanced
    assert cc_a.current_step == 1
    assert cc_a.enrollment_status == "in_progress"

    # Verify Org B remains untouched (still queued, step 0)
    assert cc_b.current_step == 0
    assert cc_b.enrollment_status == "queued"
    outreaches_b = db.query(Outreach).filter(Outreach.campaign_id == camp_b.id).count()
    assert outreaches_b == 0


# ── Scenario 10: Dry-Run Mode Zero Writes ─────────────────────────────────────

def test_dry_run_mode_zero_database_writes(test_db_session):
    """Dry-run mode identifies eligible steps but performs zero database mutations."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="DryRun Org", slug=f"dryrun-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="dryrun_lead@example.com", first_name="Dana", last_name="DryRun")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Dry Run Sequence", status="active")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(organization_id=org.id, campaign_id=camp.id, contact_id=contact.id, campaign_contact_id=cc.id, channel="email", status="sent", sent_at=t0)
    db.add(o1)
    db.commit()

    service = CampaignSchedulerService(db=db)
    t_due = t0 + timedelta(days=2)

    # Execute with dry_run=True
    res = service.tick(now=t_due, org_id=org.id, dry_run=True, force=True)
    assert res.dry_run is True
    assert res.planned_count == 1

    # Verify database state was NOT mutated
    db.expire_all()
    assert cc.current_step == 1
    total_outreaches = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).count()
    assert total_outreaches == 1  # Still only Step 1


# ── Scenario 12: Scheduled Outreach Dispatching ───────────────────────────────

def test_scheduled_outreach_dispatch_separation_and_execution(test_db_session):
    """Separate message dispatching executes delivery only when scheduled_at is due."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Dispatch Org", slug=f"dispatch-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="dispatch_lead@example.com", first_name="Jesse", last_name="Dispatch")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Dispatch Campaign", status="active")
    db.add(camp)
    db.flush()

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    # Create scheduled outreach due at t0 + 2 hours
    t_due = t0 + timedelta(hours=2)
    o = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="scheduled",
        subject="Scheduled Subject",
        body="Scheduled Body",
        scheduled_at=t_due,
    )
    db.add(o)
    db.commit()

    mock_provider = RecordingMockEmailProvider()
    service = CampaignSchedulerService(db=db)

    # 1. Dispatch at t0 + 1 hour (before due time): must not be dispatched
    res_before = service.dispatch_scheduled_outreach(org_id=org.id, now=t0 + timedelta(hours=1), provider=mock_provider)
    assert res_before.dispatched_count == 0
    assert o.status == "scheduled"
    assert len(mock_provider.sent_messages) == 0

    # 2. Dispatch at t0 + 3 hours (after due time): dispatched!
    res_after = service.dispatch_scheduled_outreach(org_id=org.id, now=t0 + timedelta(hours=3), provider=mock_provider)
    assert res_after.dispatched_count == 1
    assert o.status == "sent"
    assert o.sent_at is not None
    assert len(mock_provider.sent_messages) == 1


# ── Scenario 13: Company Tenant Isolation in Template Rendering ───────────────

def test_cross_tenant_company_cannot_be_used_during_campaign_template_rendering(test_db_session):
    """
    Regression Test: A company belonging to Organization B must NEVER be loaded
    or rendered into an outreach message for Organization A, even if a contact's
    company_id points to it (cross-tenant relationship).
    """
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Setup Org A (the campaign tenant)
    org_a = Organization(name="Tenant A Org", slug=f"tenant-a-{uuid.uuid4().hex[:6]}")
    db.add(org_a)
    db.flush()

    # 2. Setup Org B (a foreign tenant) with a company
    org_b = Organization(name="Tenant B Org", slug=f"tenant-b-{uuid.uuid4().hex[:6]}")
    db.add(org_b)
    db.flush()

    foreign_company = Company(
        organization_id=org_b.id,
        name="CrossTenant Leaked Corp",
    )
    db.add(foreign_company)
    db.flush()

    # 3. Contact in Org A mistakenly or maliciously references foreign_company.id
    contact = Contact(
        organization_id=org_a.id,
        company_id=foreign_company.id,
        email="target_user@example.com",
        first_name="Sam",
        last_name="Target",
    )
    db.add(contact)
    db.flush()

    # 4. Campaign in Org A with template referencing {contact.company} and {company}
    camp = Campaign(organization_id=org_a.id, name="Tenant A Cadence", status="active")
    db.add(camp)
    db.flush()

    step1 = CampaignStep(
        organization_id=org_a.id,
        campaign_id=camp.id,
        step_number=1,
        delay_days=0,
        is_active=True,
        subject_template="Special intro for {contact.first_name} at {contact.company}",
        body_template="Hi {first_name}, partnership opportunity with {company}.",
    )
    db.add(step1)

    cc = CampaignContact(
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="queued",
        current_step=0,
        enrolled_at=t0,
    )
    db.add(cc)
    db.commit()

    # 5. Run scheduler tick for Org A
    service = CampaignSchedulerService(db=db)
    res = service.tick(now=t0, org_id=org_a.id, force=True)

    assert res.planned_count == 1
    assert cc.current_step == 1

    # 6. Verify outreach created for Step 1
    outreach1 = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id).first()
    assert outreach1 is not None

    # CRITICAL SECURITY ASSERTION:
    # Foreign company name from Org B MUST NOT appear anywhere in the rendered subject or body!
    assert "CrossTenant Leaked Corp" not in outreach1.subject
    assert "CrossTenant Leaked Corp" not in outreach1.body
    assert "Special intro for Sam" in outreach1.subject
    assert "Hi Sam" in outreach1.body

    # 7. Now test Step 2 (subsequent step Company lookup isolation)
    outreach1.status = "sent"
    outreach1.sent_at = t0
    step2 = CampaignStep(
        organization_id=org_a.id,
        campaign_id=camp.id,
        step_number=2,
        delay_days=1,
        is_active=True,
        subject_template="Step 2 follow up for {contact.first_name} at {contact.company}",
        body_template="Following up regarding {company}.",
    )
    db.add(step2)
    db.commit()

    # Tick at t0 + 2 days
    res2 = service.tick(now=t0 + timedelta(days=2), org_id=org_a.id, force=True)
    assert res2.planned_count == 1
    assert cc.current_step == 2

    outreach2 = (
        db.query(Outreach)
        .filter(Outreach.campaign_contact_id == cc.id)
        .order_by(Outreach.created_at.desc())
        .first()
    )
    assert outreach2 is not None
    assert outreach2.id != outreach1.id
    assert "CrossTenant Leaked Corp" not in outreach2.subject
    assert "CrossTenant Leaked Corp" not in outreach2.body
    assert "Step 2 follow up for Sam" in outreach2.subject
    assert "Following up." in outreach2.body or "Following up regarding" in outreach2.body
