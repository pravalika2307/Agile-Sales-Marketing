"""Test suite for campaign scheduler staleness gates, tenant scoping, and manual review safeguards.

Verifies:
1. Maximum Overdue Staleness Gate (SCHEDULER_MAX_OVERDUE_HOURS = 24):
   - Steps overdue < 24h auto-dispatch normally.
   - Steps overdue = 24h boundary behavior verified.
   - Steps overdue > 24h are held for manual review; never auto-dispatched.
   - Original scheduled_at preserved; hold event with reason and overdue hours recorded.
   - Subsequent scheduler ticks skip held steps without dispatching.
   - Manual review resolution: approve dispatches and advances; dismiss cancels cleanly.
2. Tenant Scoping and Multi-Tenant Isolation:
   - plan_due_steps(org_id=None) and dispatch_scheduled_outreach(org_id=None) raise ValueError.
   - Scheduler tick(org_id=unauthorized) fails closed.
   - Scheduler tick(org_id=None) sweeps only authorized orgs from SCHEDULER_AUTHORIZED_ORGS.
   - Cross-tenant contact relationships are rejected.
3. Safe mock execution in Agile QA Sandbox (c0aae7f1-95bb-485f-bb9b-e3ed95469912).
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
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization
from app.services.campaign_scheduler import (
    CampaignSchedulerService,
    _ensure_utc,
    advance_campaign_contact_sequence,
    list_held_outreaches,
    resolve_held_outreach,
)
from app.services.outreach.base import (
    EmailMessage,
    EmailSendResult,
    MockEmailProvider,
)
from app.services.outreach.service import create_outreach, send_outreach
from app.schemas.outreach import OutreachCreate


class RecordingMockEmailProvider(MockEmailProvider):
    """Mock email provider that records all sent messages for verification."""

    def __init__(self) -> None:
        super().__init__()
        self.sent_messages: List[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        res = super().send(message)
        if res.success:
            self.sent_messages.append(message)
        return res


@pytest.fixture
def qa_db():
    """Isolated in-memory database initialized with the official Agile QA Sandbox and a second tenant."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # 1. Official QA Sandbox Org
    qa_org = Organization(
        id=QA_SANDBOX_ORG_ID,
        name="Agile QA Sandbox",
        slug=QA_SANDBOX_SLUG,
    )
    session.add(qa_org)

    # 2. Production Org (unauthorized in test scheduler configuration)
    prod_org = Organization(
        id=uuid.UUID("0d85dc9f-1520-4bcb-8af4-8aad025255cb"),
        name="Agile Production Org",
        slug="agile-production-org",
    )
    session.add(prod_org)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_test_campaign(
    db: Session,
    org_id: uuid.UUID,
    name: str = "Test Cadence",
    step_configs: Optional[List[dict]] = None,
) -> Campaign:
    """Helper to create campaign with steps."""
    camp = Campaign(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=name,
        type="sales_outbound",
        status="active",
        workflow_config={"nodes": [], "edges": []},
    )
    db.add(camp)
    db.flush()

    if step_configs:
        for cfg in step_configs:
            step = CampaignStep(
                organization_id=org_id,
                campaign_id=camp.id,
                step_number=cfg.get("step_number", 1),
                step_type=cfg.get("step_type", "email"),
                subject_template=cfg.get("subject_template", "Subject {{contact.first_name}}"),
                body_template=cfg.get("body_template", "Body {{contact.first_name}}"),
                delay_days=cfg.get("delay_days", 0),
                delay_hours=cfg.get("delay_hours", 0),
                is_active=True,
            )
            db.add(step)
        db.flush()

    db.commit()
    return camp


def create_test_contact(
    db: Session,
    org_id: uuid.UUID,
    first_name: str = "Jane",
    last_name: str = "Doe",
    email: str = "jane.doe@example.com",
) -> Contact:
    """Helper to create contact."""
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        lead_status="new",
    )
    db.add(contact)
    db.commit()
    return contact


# ==============================================================================
# TEST SUITE 1: Maximum Overdue Staleness Gate (SCHEDULER_MAX_OVERDUE_HOURS = 24)
# ==============================================================================

def test_overdue_step_within_threshold_auto_dispatches(qa_db: Session):
    """Scenario 1: Steps overdue by < 24 hours auto-dispatch normally when scheduler runs."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Normal Cadence",
        step_configs=[
            {"step_number": 1, "delay_days": 0, "delay_hours": 0},
            {"step_number": 2, "delay_days": 1, "delay_hours": 0},
        ],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="within_threshold@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    qa_db.add(cc)
    qa_db.flush()

    # Step 1 was sent 1 day and 12 hours ago
    t0 = datetime.now(timezone.utc) - timedelta(days=1, hours=12)
    step1_outreach = Outreach(
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        recipient=contact.email,
        sent_at=t0,
    )
    qa_db.add(step1_outreach)
    qa_db.commit()

    # Step 2 due time is t0 + 1 day = 12 hours ago (overdue by 12 hours < 24 hours)
    current_time = datetime.now(timezone.utc)
    service = CampaignSchedulerService(db=qa_db)
    result = service.tick(
        now=current_time,
        org_id=QA_SANDBOX_ORG_ID,
        auto_dispatch=True,
        provider=provider,
        force=True,
    )

    assert result.status == "completed"
    assert result.dispatched_count == 1
    assert result.held_count == 0
    assert len(provider.sent_messages) == 1

    # Verify Step 2 outreach record is sent
    step2 = qa_db.query(Outreach).filter(Outreach.campaign_contact_id == cc.id, Outreach.status == "sent").all()
    assert len(step2) == 2


def test_step_at_exact_threshold_boundary(qa_db: Session):
    """Scenario 1b: Boundary behavior at exactly 24 hours and 24h + 1s."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Boundary Cadence",
        step_configs=[
            {"step_number": 1, "delay_days": 0, "delay_hours": 0},
            {"step_number": 2, "delay_days": 1, "delay_hours": 0},
        ],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="boundary@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    qa_db.add(cc)
    qa_db.flush()

    # Step 1 was sent 2 days and 1 second ago
    # Step 2 delay is 1 day. Due time = 1 day and 1 second ago = 24 hours + 1 second overdue (> 24h)
    t0 = datetime.now(timezone.utc) - timedelta(days=2, seconds=1)
    step1_outreach = Outreach(
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        recipient=contact.email,
        sent_at=t0,
    )
    qa_db.add(step1_outreach)
    qa_db.commit()

    service = CampaignSchedulerService(db=qa_db)
    result = service.tick(
        now=datetime.now(timezone.utc),
        org_id=QA_SANDBOX_ORG_ID,
        auto_dispatch=True,
        provider=provider,
        force=True,
    )
    assert result.held_count == 1
    assert result.dispatched_count == 0


def test_overdue_step_beyond_threshold_held_for_manual_review(qa_db: Session):
    """Scenario 2: Steps overdue by > 24 hours are HELD for manual review and never auto-dispatched."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Stale Cadence",
        step_configs=[
            {"step_number": 1, "delay_days": 0, "delay_hours": 0},
            {"step_number": 2, "delay_days": 1, "delay_hours": 0},
        ],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="stale_prospect@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    qa_db.add(cc)
    qa_db.flush()

    # Step 1 was sent 5 days ago (Step 2 was due 4 days ago -> 96 hours overdue >> 24 hours)
    t0 = datetime.now(timezone.utc) - timedelta(days=5)
    step1_outreach = Outreach(
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        recipient=contact.email,
        sent_at=t0,
    )
    qa_db.add(step1_outreach)
    qa_db.commit()

    current_time = datetime.now(timezone.utc)
    service = CampaignSchedulerService(db=qa_db)
    result = service.tick(
        now=current_time,
        org_id=QA_SANDBOX_ORG_ID,
        auto_dispatch=True,
        provider=provider,
        force=True,
    )

    # Must be held, not dispatched
    assert result.dispatched_count == 0
    assert result.held_count >= 1
    assert len(provider.sent_messages) == 0

    # Verify held outreach in database
    held_outreaches = list_held_outreaches(qa_db, QA_SANDBOX_ORG_ID)
    assert len(held_outreaches) == 1
    held_item = held_outreaches[0]
    assert held_item["recipient"] == "stale_prospect@example.com"
    assert held_item["status"] == "draft"
    assert "Held for manual review" in held_item["hold_reason"]
    assert held_item["overdue_hours"] > 24.0

    # Verify scheduled_at is preserved
    expected_due = t0 + timedelta(days=1)
    outreach_db = qa_db.query(Outreach).filter(Outreach.id == held_item["outreach_id"]).first()
    assert outreach_db is not None
    assert outreach_db.scheduled_at is not None
    assert abs((_ensure_utc(outreach_db.scheduled_at) - expected_due).total_seconds()) < 5

    # Verify OutreachEvent recorded with hold metadata
    hold_evt = qa_db.query(OutreachEvent).filter(
        OutreachEvent.outreach_id == outreach_db.id,
        OutreachEvent.event_type == "scheduled",
    ).first()
    assert hold_evt is not None
    assert hold_evt.event_metadata.get("held_for_manual_review") is True
    assert "overdue_hours" in hold_evt.event_metadata

    # Subsequent scheduler tick must skip held step without dispatching
    second_result = service.tick(
        now=current_time + timedelta(hours=1),
        org_id=QA_SANDBOX_ORG_ID,
        auto_dispatch=True,
        provider=provider,
        force=True,
    )
    assert second_result.dispatched_count == 0
    assert len(provider.sent_messages) == 0


def test_step1_overdue_staleness_held_for_manual_review(qa_db: Session):
    """Scenario 3: Contact queued days ago has Step 1 held if overdue by > 24 hours."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Stale Enrollment Cadence",
        step_configs=[{"step_number": 1, "delay_days": 0, "delay_hours": 0}],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="queued_stale@example.com")
    enrolled_at = datetime.now(timezone.utc) - timedelta(days=3)
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="queued",
        current_step=0,
        enrolled_at=enrolled_at,
    )
    qa_db.add(cc)
    qa_db.commit()

    current_time = datetime.now(timezone.utc)
    service = CampaignSchedulerService(db=qa_db)
    result = service.tick(
        now=current_time,
        org_id=QA_SANDBOX_ORG_ID,
        auto_dispatch=True,
        provider=provider,
        force=True,
    )

    # Step 1 was due 3 days ago -> must be held
    assert result.dispatched_count == 0
    assert result.held_count >= 1
    assert len(provider.sent_messages) == 0

    held_items = list_held_outreaches(qa_db, QA_SANDBOX_ORG_ID)
    assert len(held_items) == 1
    assert held_items[0]["recipient"] == "queued_stale@example.com"
    assert "Step 1 is overdue" in held_items[0]["hold_reason"]


# ==============================================================================
# TEST SUITE 2: Manual Review Resolution (Approve & Dismiss)
# ==============================================================================

def test_manual_review_resolution_approve_dispatches_and_advances(qa_db: Session):
    """Scenario 4: Authorized user approves held step -> immediately dispatched and advances sequence."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Approval Cadence",
        step_configs=[
            {"step_number": 1, "delay_days": 0, "delay_hours": 0},
            {"step_number": 2, "delay_days": 1, "delay_hours": 0},
        ],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="approve_me@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    qa_db.add(cc)
    qa_db.flush()

    t0 = datetime.now(timezone.utc) - timedelta(days=4)
    step1_outreach = Outreach(
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        recipient=contact.email,
        sent_at=t0,
    )
    qa_db.add(step1_outreach)
    qa_db.commit()

    service = CampaignSchedulerService(db=qa_db)
    service.tick(now=datetime.now(timezone.utc), org_id=QA_SANDBOX_ORG_ID, auto_dispatch=True, force=True)

    # Retrieve held outreach
    held_items = list_held_outreaches(qa_db, QA_SANDBOX_ORG_ID)
    assert len(held_items) == 1
    target_id = held_items[0]["outreach_id"]

    # Approve resolution
    resolve_res = resolve_held_outreach(
        db=qa_db,
        org_id=QA_SANDBOX_ORG_ID,
        outreach_id=target_id,
        action="approve",
        provider=provider,
    )
    assert resolve_res["action"] == "approved"
    assert resolve_res["status"] == "sent"
    assert len(provider.sent_messages) == 1

    # Verify held list is now empty
    remaining_held = list_held_outreaches(qa_db, QA_SANDBOX_ORG_ID)
    assert len(remaining_held) == 0

    # Verify outreach in database is marked sent
    o = qa_db.query(Outreach).filter(Outreach.id == target_id).first()
    assert o.status == "sent"


def test_manual_review_resolution_dismiss_cancels_cleanly(qa_db: Session):
    """Scenario 5: Authorized user dismisses held step -> cancelled cleanly, zero external communication."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Dismiss Cadence",
        step_configs=[
            {"step_number": 1, "delay_days": 0, "delay_hours": 0},
            {"step_number": 2, "delay_days": 1, "delay_hours": 0},
        ],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="dismiss_me@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    qa_db.add(cc)
    qa_db.flush()

    t0 = datetime.now(timezone.utc) - timedelta(days=4)
    step1_outreach = Outreach(
        organization_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        status="sent",
        recipient=contact.email,
        sent_at=t0,
    )
    qa_db.add(step1_outreach)
    qa_db.commit()

    service = CampaignSchedulerService(db=qa_db)
    service.tick(now=datetime.now(timezone.utc), org_id=QA_SANDBOX_ORG_ID, auto_dispatch=True, force=True)

    held_items = list_held_outreaches(qa_db, QA_SANDBOX_ORG_ID)
    assert len(held_items) == 1
    target_id = held_items[0]["outreach_id"]

    # Dismiss resolution
    resolve_res = resolve_held_outreach(
        db=qa_db,
        org_id=QA_SANDBOX_ORG_ID,
        outreach_id=target_id,
        action="dismiss",
    )
    assert resolve_res["action"] == "dismissed"
    assert resolve_res["status"] == "cancelled"
    assert len(provider.sent_messages) == 0

    # Verify held list is empty
    remaining_held = list_held_outreaches(qa_db, QA_SANDBOX_ORG_ID)
    assert len(remaining_held) == 0

    # Verify outreach in database is cancelled
    o = qa_db.query(Outreach).filter(Outreach.id == target_id).first()
    assert o.status == "cancelled"


# ==============================================================================
# TEST SUITE 3: Tenant Scoping and Multi-Tenant Isolation
# ==============================================================================

def test_unrestricted_global_sweeps_prohibited(qa_db: Session):
    """Scenario 6: plan_due_steps and dispatch_scheduled_outreach raise ValueError if org_id is None."""
    service = CampaignSchedulerService(db=qa_db)

    with pytest.raises(ValueError, match="requires an explicit org_id"):
        service.plan_due_steps(org_id=None)

    with pytest.raises(ValueError, match="requires an explicit org_id"):
        service.dispatch_scheduled_outreach(org_id=None)


def test_scheduler_tick_unauthorized_org_fails_closed(qa_db: Session, monkeypatch):
    """Scenario 7: Scheduler tick for an unauthorized org fails closed without processing."""
    # Configure SCHEDULER_AUTHORIZED_ORGS to only allow QA Sandbox
    monkeypatch.setattr(
        settings,
        "SCHEDULER_AUTHORIZED_ORGS",
        str(QA_SANDBOX_ORG_ID),
    )

    unauthorized_prod_org_id = uuid.UUID("0d85dc9f-1520-4bcb-8af4-8aad025255cb")
    service = CampaignSchedulerService(db=qa_db)

    # Calling tick for unauthorized prod org must fail closed
    res = service.tick(
        org_id=unauthorized_prod_org_id,
        force=True,
    )
    assert res.status == "skipped"
    assert "not authorized" in res.message


def test_scheduler_tick_delegates_only_to_authorized_orgs(qa_db: Session, monkeypatch):
    """Scenario 8: Background tick with org_id=None iterates strictly over configured authorized orgs."""
    monkeypatch.setattr(
        settings,
        "SCHEDULER_AUTHORIZED_ORGS",
        str(QA_SANDBOX_ORG_ID),
    )

    # Set up active campaign in authorized QA Sandbox
    camp_qa = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="QA Campaign",
        step_configs=[{"step_number": 1, "delay_days": 0, "delay_hours": 0}],
    )
    contact_qa = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="qa_tenant@example.com")
    cc_qa = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp_qa.id,
        contact_id=contact_qa.id,
        enrollment_status="queued",
        current_step=0,
    )
    qa_db.add(cc_qa)

    # Set up active campaign in unauthorized production org
    prod_org_id = uuid.UUID("0d85dc9f-1520-4bcb-8af4-8aad025255cb")
    camp_prod = create_test_campaign(
        qa_db,
        prod_org_id,
        name="Prod Campaign",
        step_configs=[{"step_number": 1, "delay_days": 0, "delay_hours": 0}],
    )
    contact_prod = create_test_contact(qa_db, prod_org_id, email="prod_prospect@example.com")
    cc_prod = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp_prod.id,
        contact_id=contact_prod.id,
        enrollment_status="queued",
        current_step=0,
    )
    qa_db.add(cc_prod)
    qa_db.commit()

    service = CampaignSchedulerService(db=qa_db)
    # Background tick with org_id=None
    res = service.tick(org_id=None, force=True, auto_dispatch=False)

    assert res.status == "completed"
    assert "1 authorized organization(s)" in res.message
    assert res.planned_count == 1

    # Verify QA Sandbox enrollment progressed to in_progress
    qa_db.refresh(cc_qa)
    assert cc_qa.enrollment_status == "in_progress"

    # Verify Production enrollment was completely untouched
    qa_db.refresh(cc_prod)
    assert cc_prod.enrollment_status == "queued"


def test_cross_tenant_contact_relationship_rejected(qa_db: Session):
    """Scenario 9: Cross-tenant enrollment (contact in Org B, campaign in Org A) is rejected."""
    prod_org_id = uuid.UUID("0d85dc9f-1520-4bcb-8af4-8aad025255cb")
    camp_qa = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="QA Cross Tenant Camp",
        step_configs=[{"step_number": 1, "delay_days": 0, "delay_hours": 0}],
    )
    # Contact belongs to Production org
    contact_prod = create_test_contact(qa_db, prod_org_id, email="cross_tenant@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp_qa.id,
        contact_id=contact_prod.id,
        enrollment_status="queued",
        current_step=0,
    )
    qa_db.add(cc)
    qa_db.commit()

    service = CampaignSchedulerService(db=qa_db)
    res = service.plan_due_steps(org_id=QA_SANDBOX_ORG_ID)

    assert res.error_count == 1
    assert any(d.get("action") == "rejected" for d in res.details)
    assert cc.enrollment_status == "queued"  # Did not advance


def test_duplicate_dispatch_prevention(qa_db: Session):
    """Scenario 10: Repeated triggers on the same enrollment never produce duplicate outreaches."""
    provider = RecordingMockEmailProvider()
    camp = create_test_campaign(
        qa_db,
        QA_SANDBOX_ORG_ID,
        name="Idempotency Cadence",
        step_configs=[{"step_number": 1, "delay_days": 0, "delay_hours": 0}],
    )
    contact = create_test_contact(qa_db, QA_SANDBOX_ORG_ID, email="idempotency@example.com")
    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="queued",
        current_step=0,
    )
    qa_db.add(cc)
    qa_db.commit()

    service = CampaignSchedulerService(db=qa_db)

    # First tick plans and dispatches Step 1
    res1 = service.tick(org_id=QA_SANDBOX_ORG_ID, auto_dispatch=True, provider=provider, force=True)
    assert res1.planned_count == 1
    assert res1.dispatched_count == 1
    assert len(provider.sent_messages) == 1

    # Second consecutive tick
    res2 = service.tick(org_id=QA_SANDBOX_ORG_ID, auto_dispatch=True, provider=provider, force=True)
    assert res2.planned_count == 0
    assert res2.dispatched_count == 0
    assert len(provider.sent_messages) == 1  # No duplicate send

    # Third consecutive tick
    res3 = service.tick(org_id=QA_SANDBOX_ORG_ID, auto_dispatch=True, provider=provider, force=True)
    assert res3.planned_count == 0
    assert res3.dispatched_count == 0
    assert len(provider.sent_messages) == 1
