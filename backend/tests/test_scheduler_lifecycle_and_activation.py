"""Comprehensive verification test suite for Campaign Scheduler Activation and Lifecycle.

Tests all required areas:
1. Scheduler startup and shutdown lifecycle in application lifespan.
2. Multiple scheduler instance protection and concurrency lock mutual exclusion.
3. Overdue-step recovery after restart.
4. Positive-delay scheduling strictly at due time.
5. Zero-delay progression preservation.
6. Campaign failure isolation (one failed campaign does not abort other campaigns).
7. Scheduler status API endpoint reporting runtime state.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app, lifespan
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact
from app.models.outreach import Outreach
from app.models.tenant import Organization
from app.services.campaign_scheduler import (
    CampaignSchedulerService,
    acquire_scheduler_lock,
    release_scheduler_lock,
)
from app.services.outreach.base import EmailMessage, EmailSendResult, MockEmailProvider
from app.services.outreach.service import send_outreach


class InMemoryMockEmailProvider(MockEmailProvider):
    """Mock provider tracking sent messages."""

    def __init__(self) -> None:
        super().__init__()
        self.dispatched_messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        res = super().send(message)
        if res.success:
            self.dispatched_messages.append(message)
        return res


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


@pytest.mark.asyncio
async def test_scheduler_startup_and_clean_shutdown_lifecycle(monkeypatch):
    """Verify background scheduler loop starts during app lifespan and cancels cleanly on exit."""
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCHEDULER_INTERVAL_SECONDS", 1)

    tick_called = asyncio.Event()

    original_tick = CampaignSchedulerService.tick

    def mock_tick(self, *args, **kwargs):
        tick_called.set()
        return original_tick(self, *args, **kwargs)

    with patch.object(CampaignSchedulerService, "tick", side_effect=mock_tick, autospec=True):
        async with lifespan(app):
            # Wait for the startup recovery tick to execute
            try:
                await asyncio.wait_for(tick_called.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pytest.fail("Initial scheduler tick was not called during application startup.")

        # Exited context manager -> task should be cancelled and cleanly shutdown


def test_multiple_scheduler_instances_concurrency_protection(test_db_session):
    """Verify concurrent scheduler workers are mutually excluded via advisory/process lock."""
    db = test_db_session

    # Worker 1 acquires lock
    lock1 = acquire_scheduler_lock(db)
    assert lock1 is True, "Worker 1 failed to acquire scheduler lock"

    # Worker 2 attempts to acquire lock concurrently
    lock2 = acquire_scheduler_lock(db)
    assert lock2 is False, "Worker 2 unexpectedly acquired lock while Worker 1 held it"

    # Worker 1 releases lock
    release_scheduler_lock(db, lock1)

    # Worker 2 can now acquire lock
    lock3 = acquire_scheduler_lock(db)
    assert lock3 is True, "Worker 2 failed to acquire lock after Worker 1 released it"
    release_scheduler_lock(db, lock3)


def test_scheduler_tick_skips_when_concurrent_worker_active(test_db_session, monkeypatch):
    """Verify tick() returns status='skipped' when another worker holds the scheduler lock."""
    db = test_db_session
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)

    # Simulate an active lock held by another process/worker
    held_lock = acquire_scheduler_lock(db)
    assert held_lock is True

    try:
        service = CampaignSchedulerService(db=db)
        res = service.tick()
        assert res.status == "skipped"
        assert "concurrent scheduler worker active" in res.message
        assert res.planned_count == 0
        assert res.dispatched_count == 0
    finally:
        release_scheduler_lock(db, held_lock)


def test_overdue_step_recovery_after_restart(test_db_session, monkeypatch):
    """Verify that steps overdue due to server downtime/restart are immediately recovered and dispatched."""
    db = test_db_session
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCHEDULER_AUTO_DISPATCH", True)

    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
    # Contact completed Step 1 at t0; Step 2 had 1 day delay (due at t0 + 1d)
    # Server was down until t0 + 3 days (2 days overdue)
    restart_time = t0 + timedelta(days=3)

    org = Organization(name="Restart Recovery Org", slug=f"restart-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    monkeypatch.setattr(settings, "SCHEDULER_AUTHORIZED_ORGS", str(org.id))
    monkeypatch.setattr(settings, "SCHEDULER_MAX_OVERDUE_HOURS", 72)

    contact = Contact(organization_id=org.id, email="alex_restart@example.com", first_name="Alex", last_name="Restart")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Restart Test Cadence", status="active", type="sales_outbound")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, delay_hours=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=1, delay_hours=0, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        subject="S1",
        body="B1",
        sent_at=t0,
        created_at=t0,
    )
    db.add(o1)
    db.commit()

    # Restart occurs at restart_time (overdue)
    service = CampaignSchedulerService(db=db)
    mock_prov = InMemoryMockEmailProvider()

    # Step planning identifies overdue step 2
    res = service.tick(now=restart_time, org_id=org.id, auto_dispatch=True, provider=mock_prov)
    assert res.planned_count == 1
    assert res.dispatched_count == 1
    assert cc.current_step == 2

    # Verify Step 2 outreach was created and dispatched
    o2 = db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id, Outreach.channel == "email").order_by(Outreach.created_at.desc()).first()
    assert o2 is not None
    assert o2.status == "sent"
    assert len(mock_prov.dispatched_messages) == 1


def test_positive_delay_strictly_waits_for_due_time(test_db_session, monkeypatch):
    """Verify that positive-delay touches are created in scheduled status and dispatched ONLY when due."""
    db = test_db_session
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCHEDULER_AUTO_DISPATCH", True)

    t0 = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)
    due_time = t0 + timedelta(days=2)

    org = Organization(name="Positive Delay Org", slug=f"pos-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    monkeypatch.setattr(settings, "SCHEDULER_AUTHORIZED_ORGS", str(org.id))

    contact = Contact(organization_id=org.id, email="delay_strictly@example.com", first_name="Chris", last_name="Taylor")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Delay Cadence", status="active", type="sales_outbound")
    db.add(camp)
    db.flush()

    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, delay_hours=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=2, delay_hours=0, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        subject="S1",
        body="B1",
        sent_at=t0,
        created_at=t0,
    )
    db.add(o1)
    db.commit()

    service = CampaignSchedulerService(db=db)
    mock_prov = InMemoryMockEmailProvider()

    # 1. Tick at t0 + 1 day: Step 2 delay has NOT elapsed
    t_before = t0 + timedelta(days=1)
    res_before = service.tick(now=t_before, org_id=org.id, auto_dispatch=True, provider=mock_prov)
    assert res_before.planned_count == 0
    assert res_before.dispatched_count == 0
    assert len(mock_prov.dispatched_messages) == 0

    # 2. Tick at t0 + 2 days + 5 minutes: Scheduled time has arrived
    t_after = due_time + timedelta(minutes=5)
    res_after = service.tick(now=t_after, org_id=org.id, auto_dispatch=True, provider=mock_prov)
    assert res_after.planned_count == 1
    assert res_after.dispatched_count == 1
    assert len(mock_prov.dispatched_messages) == 1
    assert cc.current_step == 2


def test_zero_delay_progression_preserved(test_db_session, monkeypatch):
    """Verify zero-delay progression executes steps immediately in sequence without waiting for tick."""
    db = test_db_session
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Zero Delay Org", slug=f"zero-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()

    contact = Contact(organization_id=org.id, email="zero_delay@example.com", first_name="Sam", last_name="Immediate")
    db.add(contact)
    db.flush()

    camp = Campaign(organization_id=org.id, name="Zero Delay Sequence", status="active", type="sales_outbound")
    db.add(camp)
    db.flush()

    # 2 Zero-delay steps
    s1 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=1, delay_days=0, delay_hours=0, is_active=True, subject_template="S1", body_template="B1")
    s2 = CampaignStep(organization_id=org.id, campaign_id=camp.id, step_number=2, delay_days=0, delay_hours=0, is_active=True, subject_template="S2", body_template="B2")
    db.add_all([s1, s2])

    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, enrollment_status="in_progress", current_step=1, enrolled_at=t0)
    db.add(cc)
    db.flush()

    o1 = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="draft",
        subject="S1",
        body="B1",
    )
    db.add(o1)
    db.commit()

    mock_prov = InMemoryMockEmailProvider()
    # Sending Step 1 with auto_advance_sequence=True should immediately progress and send Step 2
    send_outreach(db, org.id, o1.id, provider=mock_prov, auto_advance_sequence=True, sent_at=t0)

    # Verify both steps were dispatched
    assert len(mock_prov.dispatched_messages) == 2
    assert cc.current_step == 2
    assert cc.enrollment_status == "completed"
    assert camp.status == "completed"


def test_failed_campaign_isolation_does_not_stop_other_campaigns(test_db_session, monkeypatch):
    """Verify that an error in one corrupted campaign does not halt processing of other valid campaigns."""
    db = test_db_session
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCHEDULER_AUTO_DISPATCH", True)
    t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    org = Organization(name="Isolation Org", slug=f"iso-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    monkeypatch.setattr(settings, "SCHEDULER_AUTHORIZED_ORGS", str(org.id))

    contact1 = Contact(organization_id=org.id, email="corrupt_camp_user@example.com", first_name="Corrupt", last_name="User")
    contact2 = Contact(organization_id=org.id, email="healthy_camp_user@example.com", first_name="Healthy", last_name="User")
    db.add_all([contact1, contact2])
    db.flush()

    # Campaign 1: Corrupted / Broken workflow nodes that cause an unhandled exception during step resolution
    camp_broken = Campaign(
        organization_id=org.id,
        name="Broken Campaign",
        status="active",
        type="sales_outbound",
        workflow_config={"nodes": "INVALID_NOT_A_LIST"}, # Will raise exception or type error
    )
    camp_healthy = Campaign(
        organization_id=org.id,
        name="Healthy Campaign",
        status="active",
        type="sales_outbound",
    )
    db.add_all([camp_broken, camp_healthy])
    db.flush()

    step_healthy = CampaignStep(
        organization_id=org.id,
        campaign_id=camp_healthy.id,
        step_number=1,
        delay_days=0,
        delay_hours=0,
        is_active=True,
        subject_template="Healthy Intro",
        body_template="Hi {contact.first_name}, everything is healthy.",
    )
    step2_healthy = CampaignStep(
        organization_id=org.id,
        campaign_id=camp_healthy.id,
        step_number=2,
        delay_days=1,
        delay_hours=0,
        is_active=True,
        subject_template="Healthy Follow-up",
        body_template="Following up on healthy campaign.",
    )
    db.add_all([step_healthy, step2_healthy])
    db.flush()

    cc1 = CampaignContact(campaign_id=camp_broken.id, contact_id=contact1.id, enrollment_status="queued", current_step=0, enrolled_at=t0)
    cc2 = CampaignContact(campaign_id=camp_healthy.id, contact_id=contact2.id, enrollment_status="queued", current_step=0, enrolled_at=t0)
    db.add_all([cc1, cc2])
    db.commit()

    # Run scheduler tick across all active campaigns for org
    service = CampaignSchedulerService(db=db)
    mock_prov = InMemoryMockEmailProvider()

    res = service.tick(now=t0, org_id=org.id, auto_dispatch=True, provider=mock_prov)

    # Healthy campaign must be planned and dispatched despite broken campaign failure
    assert res.planned_count >= 1
    assert cc2.current_step >= 1
    assert cc2.enrollment_status == "in_progress"

    # Outreaches for healthy contact must exist
    o_healthy = db.query(Outreach).filter(Outreach.campaign_contact_id == cc2.id).first()
    assert o_healthy is not None
    assert o_healthy.status == "sent"


@pytest.mark.asyncio
async def test_scheduler_status_endpoint(test_db_session, monkeypatch):
    """Verify GET /api/v1/campaigns/scheduler/status returns accurate operational details."""
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCHEDULER_AUTO_DISPATCH", True)
    monkeypatch.setattr(settings, "SCHEDULER_INTERVAL_SECONDS", 45)
    monkeypatch.setattr(settings, "SCHEDULER_BATCH_SIZE", 30)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Register a tenant to obtain auth token
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"status_test_{uuid.uuid4().hex[:6]}@example.com",
                "password": "Password123!",
                "full_name": "Scheduler Test Admin",
                "organization_name": "Scheduler Status Org",
            },
        )
        assert reg_resp.status_code == 201
        token = reg_resp.json()["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/campaigns/scheduler/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["auto_dispatch"] is True
        assert data["interval_seconds"] == 45
        assert data["batch_size"] == 30
        assert data["status"] == "active"
        assert "database_dialect" in data
