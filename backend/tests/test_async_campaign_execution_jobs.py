"""Comprehensive QA Verification Test Suite for Asynchronous Campaign Workflow Execution.

Verifies all 16 execution scenarios in the dedicated Agile QA Sandbox (c0aae7f1-95bb-485f-bb9b-e3ed95469912)
using strictly mocked communication providers (MockEmailProvider, MockVoiceClient, MockSMSProvider):

1. Three consecutive zero-delay email steps.
2. Ten-step zero-delay workflow.
3. Positive-delay workflow.
4. Mixed zero-delay and delayed steps.
5. Email -> Email progression.
6. Voice -> Email progression.
7. SMS -> Email progression where supported.
8. Worker restart with pending jobs.
9. Worker crash during processing (lease recovery).
10. Provider timeout and ambiguous response (dispatch_unknown).
11. Retry without duplicate communication (backoff & CAS).
12. Concurrent worker execution (SKIP LOCKED safety).
13. Multiple recipients with independent failures.
14. Stale job recovery (>24h overdue held).
15. Campaign completion and failure states.
16. Tenant isolation (Agile QA Sandbox vs Production org).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.core.qa_safeguard import QA_SANDBOX_ORG_ID, QA_SANDBOX_SLUG
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_execution_job import (
    AUTODISPATCH_ALLOWED_CHANNELS,
    CampaignExecutionJob,
)
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.outreach import Outreach
from app.models.tenant import Organization
from app.services.campaign_execution.job_service import (
    CampaignExecutionJobService,
    InvalidPayloadError,
    LeaseLostError,
)
from app.services.campaign_execution.worker import CampaignJobWorker
from app.services.outreach.base import (
    EmailMessage,
    EmailSendResult,
    MockEmailProvider,
)

PRODUCTION_ORG_ID = uuid.UUID("0d85dc9f-1520-4bcb-8af4-8aad025255cb")


# ── Mock Providers ────────────────────────────────────────────────────────────

class RecordingMockEmailProvider(MockEmailProvider):
    """Mock email provider tracking all calls and supporting conditional failure/timeouts."""

    def __init__(
        self,
        should_fail: bool = False,
        should_timeout: bool = False,
        failing_recipients: Optional[List[str]] = None,
    ) -> None:
        super().__init__(should_fail=should_fail)
        self.should_timeout = should_timeout
        self.failing_recipients = failing_recipients or []
        self.sent_messages: List[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        if self.should_timeout:
            import httpx
            raise httpx.ReadTimeout("Simulated AWS SES provider connection timeout")
        if self._should_fail or (message.to_email in self.failing_recipients):
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=f"Simulated provider delivery failure for {message.to_email}",
            )
        res = super().send(message)
        if res.success:
            self.sent_messages.append(message)
        return res


class MockRetellVoiceClient:
    """Mock Retell AI voice client."""

    def __init__(self, should_fail: bool = False, should_timeout: bool = False) -> None:
        self.should_fail = should_fail
        self.should_timeout = should_timeout
        self.calls_created: List[Dict[str, Any]] = []

    def create_phone_call(self, **kwargs: Any) -> Dict[str, Any]:
        if self.should_timeout:
            import httpx
            raise httpx.ReadTimeout("Simulated Retell AI gateway timeout")
        if self.should_fail:
            raise RuntimeError("Simulated Retell call initiation failure")
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        record = {"call_id": call_id, "status": "registered", **kwargs}
        self.calls_created.append(record)
        return record


# ── Pytest Fixture ────────────────────────────────────────────────────────────

@pytest.fixture
def qa_db():
    """In-memory SQLite database initialized with Agile QA Sandbox."""
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


# ── Test Helpers ──────────────────────────────────────────────────────────────

def create_test_campaign(
    db: Session,
    org_id: uuid.UUID,
    name: str,
    step_specs: List[Dict[str, Any]],
) -> Campaign:
    """Helper creating a visual workflow campaign with specified step configurations."""
    nodes = [{"id": "start-node", "type": "start", "title": "Start", "config": {}}]
    edges = []
    prev_id = "start-node"

    for idx, spec in enumerate(step_specs, start=1):
        stype = spec.get("channel", "email")
        node_id = f"step-{idx}"
        nodes.append({
            "id": node_id,
            "type": stype,
            "title": spec.get("subject", f"Step {idx}"),
            "config": {
                "step_number": idx,
                "subject": spec.get("subject", f"Subject {idx}"),
                "body": spec.get("body", f"Body for step {idx}"),
                "delay_days": spec.get("delay_days", 0),
                "delay_hours": spec.get("delay_hours", 0),
                "is_active": True,
            },
        })
        edges.append({"id": f"edge-{prev_id}-{node_id}", "source": prev_id, "target": node_id})
        prev_id = node_id

    camp = Campaign(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=name,
        type="sales_outbound",
        status="active",
        workflow_config={"nodes": nodes, "edges": edges},
    )
    db.add(camp)
    db.commit()
    return camp


def enroll_test_contact(
    db: Session,
    org_id: uuid.UUID,
    camp_id: uuid.UUID,
    email: str,
    first_name: str = "Test",
    phone: str = "+15551234567",
) -> tuple[Contact, CampaignContact]:
    """Helper enrolling a test contact into a campaign."""
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org_id,
        first_name=first_name,
        last_name="User",
        email=email,
        phone=phone,
        lead_status="new",
    )
    db.add(contact)
    db.flush()

    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp_id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=0,
    )
    db.add(cc)
    db.commit()
    return contact, cc


# ── QA Verification Scenarios (1 through 16) ──────────────────────────────────

def test_scenario_01_three_consecutive_zero_delay_email_steps(qa_db: Session):
    """Scenario 1: Three consecutive zero-delay email steps execute through asynchronous jobs."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "Three-Step Zero Delay",
        [
            {"channel": "email", "subject": "Intro", "body": "Welcome", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Follow-up", "body": "Checking in", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Final", "body": "Last note", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "user1@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    # Enqueue Step 1
    job1 = job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "Intro", "rendered_body": "Welcome"},
    )
    assert job1.status == "pending"

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    # Tick 1: Step 1 dispatches and enqueues Step 2
    res1 = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert res1["processed_count"] == 1
    assert len(mock_email.sent_messages) == 1

    # Tick 2: Step 2 dispatches and enqueues Step 3
    res2 = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert res2["processed_count"] == 1
    assert len(mock_email.sent_messages) == 2

    # Tick 3: Step 3 dispatches and completes campaign cadence
    res3 = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert res3["processed_count"] == 1
    assert len(mock_email.sent_messages) == 3

    qa_db.refresh(cc)
    assert cc.enrollment_status == "completed"
    assert cc.current_step == 3


def test_scenario_02_ten_step_zero_delay_workflow(qa_db: Session):
    """Scenario 2: Ten-step zero-delay workflow executes reliably across ticks without stack overflow."""
    step_specs = [{"channel": "email", "subject": f"Step {i}", "body": f"Content {i}", "delay_days": 0, "delay_hours": 0} for i in range(1, 11)]
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Ten-Step Cadence", step_specs)
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "user10@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "Step 1", "rendered_body": "Content 1"},
    )

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    for i in range(1, 11):
        tick_res = worker.run_single_tick(QA_SANDBOX_ORG_ID)
        assert tick_res["processed_count"] == 1, f"Failed at step {i}"

    assert len(mock_email.sent_messages) == 10
    qa_db.refresh(cc)
    assert cc.enrollment_status == "completed"
    assert cc.current_step == 10


def test_scenario_03_positive_delay_workflow(qa_db: Session):
    """Scenario 3: Positive-delay steps are scheduled for future and execute only when due time arrives."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "Delayed Campaign",
        [
            {"channel": "email", "subject": "Step 1", "body": "Now", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Step 2", "body": "Later", "delay_days": 1, "delay_hours": 2},
        ],
    )
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "delayed@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    start_time = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        scheduled_at=start_time,
        execution_payload={"rendered_subject": "Step 1", "rendered_body": "Now"},
    )

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    # Dispatch step 1 at start_time
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=start_time)
    assert len(mock_email.sent_messages) == 1

    # Check Step 2 is scheduled for start_time + 1 day 2 hours
    step2_job = qa_db.query(CampaignExecutionJob).filter(
        CampaignExecutionJob.campaign_contact_id == cc.id,
        CampaignExecutionJob.step_number == 2,
    ).first()
    assert step2_job is not None
    assert step2_job.status == "pending"
    scheduled_utc = step2_job.scheduled_at if step2_job.scheduled_at.tzinfo else step2_job.scheduled_at.replace(tzinfo=timezone.utc)
    assert scheduled_utc == start_time + timedelta(days=1, hours=2)

    # 1 hour later: Step 2 must NOT be eligible yet
    tick_early = worker.run_single_tick(QA_SANDBOX_ORG_ID, now=start_time + timedelta(hours=1))
    assert tick_early["processed_count"] == 0
    assert len(mock_email.sent_messages) == 1

    # When due time arrives: Step 2 executes
    tick_due = worker.run_single_tick(QA_SANDBOX_ORG_ID, now=start_time + timedelta(days=1, hours=2, minutes=1))
    assert tick_due["processed_count"] == 1
    assert len(mock_email.sent_messages) == 2


def test_scenario_04_mixed_zero_and_delayed_steps(qa_db: Session):
    """Scenario 4: Mixed workflow with immediate Step 1, delayed Step 2, and zero-delay Step 3."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "Mixed Cadence",
        [
            {"channel": "email", "subject": "Intro", "body": "Immediate", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Follow-up", "body": "Wait 3h", "delay_days": 0, "delay_hours": 3},
            {"channel": "email", "subject": "Survey", "body": "Immediate after follow-up", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "mixed@example.com")
    job_svc = CampaignExecutionJobService(qa_db)
    t0 = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        scheduled_at=t0,
        execution_payload={"rendered_subject": "Intro", "rendered_body": "Immediate"},
    )

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    # Dispatch step 1 immediately
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=t0)
    assert len(mock_email.sent_messages) == 1

    # At t0 + 2h: Step 2 is not due yet
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=t0 + timedelta(hours=2))
    assert len(mock_email.sent_messages) == 1

    # At t0 + 3h: Step 2 becomes due and executes
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=t0 + timedelta(hours=3))
    assert len(mock_email.sent_messages) == 2

    # Step 3 (zero delay after step 2) is immediately ready in the next tick
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=t0 + timedelta(hours=3, seconds=5))
    assert len(mock_email.sent_messages) == 3


def test_scenario_05_email_to_email_progression(qa_db: Session):
    """Scenario 5: Email Step 1 delivery completes and advances to Email Step 2."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "Email to Email",
        [
            {"channel": "email", "subject": "Email 1", "body": "First", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Email 2", "body": "Second", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "e2e@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "Email 1", "rendered_body": "First"},
    )

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    worker.run_single_tick(QA_SANDBOX_ORG_ID)
    worker.run_single_tick(QA_SANDBOX_ORG_ID)

    assert len(mock_email.sent_messages) == 2
    assert [m.subject for m in mock_email.sent_messages] == ["Email 1", "Email 2"]


def test_scenario_06_voice_to_email_progression(qa_db: Session):
    """Scenario 6: Voice SDR call completion advances to follow-up email step."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "Voice to Email",
        [
            {"channel": "voice", "subject": "AI Voice Call", "body": "Voice Pitch", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Post-Call Summary", "body": "Thanks for speaking", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "voice@example.com", phone="+15559876543")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="voice",
        execution_payload={"retell_agent_id": "agent_123", "rendered_subject": "AI Voice Call", "script": "Voice Pitch"},
    )

    mock_email = RecordingMockEmailProvider()
    mock_voice = MockRetellVoiceClient()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, retell_client=mock_voice, force_mock=True)

    # Tick 1: Voice step executes
    res1 = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert res1["processed_count"] == 1
    assert len(mock_voice.calls_created) == 1

    # Tick 2: Step 2 email follow-up dispatches
    res2 = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert res2["processed_count"] == 1
    assert len(mock_email.sent_messages) == 1
    assert mock_email.sent_messages[0].subject == "Post-Call Summary"


def test_scenario_07_sms_to_email_progression(qa_db: Session):
    """Scenario 7: SMS message delivery advances to follow-up email step."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "SMS to Email",
        [
            {"channel": "sms", "subject": "SMS Intro", "body": "Quick SMS note", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Email Follow-up", "body": "Details via email", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "sms@example.com", phone="+15553334444")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="sms",
        execution_payload={"rendered_body": "Quick SMS note"},
    )

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    # Tick 1: SMS dispatches
    worker.run_single_tick(QA_SANDBOX_ORG_ID)

    # Tick 2: Email dispatches
    worker.run_single_tick(QA_SANDBOX_ORG_ID)

    assert len(mock_email.sent_messages) == 1
    assert mock_email.sent_messages[0].subject == "Email Follow-up"


def test_scenario_08_worker_restart_with_pending_jobs(qa_db: Session):
    """Scenario 8: Pending jobs persist across worker shutdown and resume cleanly on new worker instance."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Restart Campaign", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "restart@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )

    # Worker instance 1 starts and immediately terminates before processing
    worker1 = CampaignJobWorker(qa_db, worker_id="worker_instance_1")
    del worker1

    # Worker instance 2 starts and claims the pending job
    mock_email = RecordingMockEmailProvider()
    worker2 = CampaignJobWorker(qa_db, worker_id="worker_instance_2", email_provider=mock_email, force_mock=True)
    res = worker2.run_single_tick(QA_SANDBOX_ORG_ID)

    assert res["processed_count"] == 1
    assert len(mock_email.sent_messages) == 1


def test_scenario_09_worker_crash_during_processing_and_lease_recovery(qa_db: Session):
    """Scenario 9: Worker crash during execution leaves expired lease; recovery sweep reclaims job safely."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Crash Recovery", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "crash@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    t0 = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    job = job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        scheduled_at=t0,
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )

    # Simulate Worker 1 claiming the job with a 2-minute lease
    claimed = job_svc.claim_next_jobs(QA_SANDBOX_ORG_ID, worker_id="crashed_worker", now=t0)
    assert len(claimed) == 1
    assert claimed[0].status == "processing"

    # Worker 1 crashes (no heartbeat, no completion). 3 minutes later, lease has expired:
    t_after_crash = t0 + timedelta(minutes=3)

    mock_email = RecordingMockEmailProvider()
    worker2 = CampaignJobWorker(qa_db, worker_id="recovery_worker", email_provider=mock_email, force_mock=True)

    # Tick from Worker 2: reclaims expired lease and processes the pending job
    tick_res = worker2.run_single_tick(QA_SANDBOX_ORG_ID, now=t_after_crash)

    assert tick_res["reclaimed_count"] == 1
    assert tick_res["processed_count"] == 1
    assert len(mock_email.sent_messages) == 1

    qa_db.refresh(job)
    assert job.status == "completed"


def test_scenario_10_provider_timeout_and_dispatch_unknown(qa_db: Session):
    """Scenario 10: Provider network timeout transitions job to dispatch_unknown; blind retry is blocked."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Timeout Campaign", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "timeout@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job = job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )

    # Mock email provider configured to simulate a connection timeout
    timeout_provider = RecordingMockEmailProvider(should_timeout=True)
    worker = CampaignJobWorker(qa_db, email_provider=timeout_provider, force_mock=True)

    worker.run_single_tick(QA_SANDBOX_ORG_ID)

    qa_db.refresh(job)
    # Must enter dispatch_unknown, NOT retry_scheduled or completed
    assert job.status == "dispatch_unknown"
    assert "timeout" in job.last_error.lower()

    # Subsequent tick must NOT blindly retry dispatch_unknown job
    tick_next = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert tick_next["processed_count"] == 0

    # Reconciliation: Confirm provider never received message -> safely retry
    job_svc.reconcile_dispatch_unknown_job(job.id, confirmed_delivered=False)
    qa_db.refresh(job)
    assert job.status == "retry_scheduled"


def test_scenario_11_retry_without_duplicate_communication(qa_db: Session):
    """Scenario 11: Transient failure triggers retry with backoff; reuses original job ID without duplicates."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Retry Campaign", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "retry@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    t0 = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    job = job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        scheduled_at=t0,
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )
    original_job_id = job.id

    # Fail attempt 1
    failing_provider = RecordingMockEmailProvider(should_fail=True)
    worker = CampaignJobWorker(qa_db, email_provider=failing_provider, force_mock=True)
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=t0)

    qa_db.refresh(job)
    assert job.id == original_job_id
    assert job.status == "retry_scheduled"
    assert job.attempts == 1
    job_sched_utc = job.scheduled_at if job.scheduled_at.tzinfo else job.scheduled_at.replace(tzinfo=timezone.utc)
    assert job_sched_utc > t0

    # Ensure total job count in DB is strictly 1 (no duplicate rows created)
    job_count = qa_db.query(CampaignExecutionJob).filter(CampaignExecutionJob.campaign_contact_id == cc.id).count()
    assert job_count == 1

    # Attempt 2 after backoff elapsed: Succeeds
    succeeding_provider = RecordingMockEmailProvider(should_fail=False)
    worker.email_provider = succeeding_provider
    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=job_sched_utc + timedelta(seconds=1))

    qa_db.refresh(job)
    assert job.id == original_job_id
    assert job.status == "completed"
    assert len(succeeding_provider.sent_messages) == 1


def test_scenario_12_concurrent_worker_execution(qa_db: Session):
    """Scenario 12: Two concurrent workers do not double-claim or double-send the same job."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Concurrency", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "concurrent@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )

    # Worker A claims the job
    worker_a_jobs = job_svc.claim_next_jobs(QA_SANDBOX_ORG_ID, worker_id="worker_A", batch_size=5)
    assert len(worker_a_jobs) == 1

    # Worker B attempts to claim at the same time: returns empty list
    worker_b_jobs = job_svc.claim_next_jobs(QA_SANDBOX_ORG_ID, worker_id="worker_B", batch_size=5)
    assert len(worker_b_jobs) == 0


def test_scenario_13_multiple_recipients_with_independent_failures(qa_db: Session):
    """Scenario 13: Recipient A fails transiently while Recipient B succeeds and progresses independently."""
    camp = create_test_campaign(
        qa_db, QA_SANDBOX_ORG_ID, "Independent Recipients",
        [
            {"channel": "email", "subject": "Step 1", "body": "B1", "delay_days": 0, "delay_hours": 0},
            {"channel": "email", "subject": "Step 2", "body": "B2", "delay_days": 0, "delay_hours": 0},
        ],
    )
    contact_a, cc_a = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "failing_user@example.com")
    contact_b, cc_b = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "success_user@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, campaign_contact_id=cc_a.id, contact_id=contact_a.id,
        step_number=1, channel="email", execution_payload={"rendered_subject": "Step 1", "rendered_body": "B1"},
    )
    job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID, campaign_id=camp.id, campaign_contact_id=cc_b.id, contact_id=contact_b.id,
        step_number=1, channel="email", execution_payload={"rendered_subject": "Step 1", "rendered_body": "B1"},
    )

    # Provider configured to fail ONLY failing_user@example.com
    selective_provider = RecordingMockEmailProvider(failing_recipients=["failing_user@example.com"])
    worker = CampaignJobWorker(qa_db, email_provider=selective_provider, force_mock=True)

    # Process batch
    worker.run_single_tick(QA_SANDBOX_ORG_ID)

    qa_db.refresh(cc_a)
    qa_db.refresh(cc_b)

    # Recipient A failed Step 1
    job_a = qa_db.query(CampaignExecutionJob).filter(CampaignExecutionJob.campaign_contact_id == cc_a.id).first()
    assert job_a.status == "retry_scheduled"
    assert cc_a.current_step == 0

    # Recipient B succeeded Step 1 and advanced to Step 2
    job_b = qa_db.query(CampaignExecutionJob).filter(CampaignExecutionJob.campaign_contact_id == cc_b.id, CampaignExecutionJob.step_number == 1).first()
    assert job_b.status == "completed"
    assert cc_b.current_step == 1


def test_scenario_14_stale_job_recovery_overdue_staleness_gate(qa_db: Session):
    """Scenario 14: Step overdue by >24h is held for manual review and never auto-dispatched."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Stale Campaign", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "stale@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    stale_scheduled_at = now - timedelta(hours=25)  # 25 hours overdue (> SCHEDULER_MAX_OVERDUE_HOURS=24)

    job = job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        scheduled_at=stale_scheduled_at,
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    worker.run_single_tick(QA_SANDBOX_ORG_ID, now=now)

    qa_db.refresh(job)
    # Must be held, and NO email sent
    assert job.status == "held"
    assert "overdue" in job.last_error.lower()
    assert len(mock_email.sent_messages) == 0


def test_scenario_15_campaign_completion_and_failure_states(qa_db: Session):
    """Scenario 15: Campaign transitions to completed; opt-outs safely cancel active jobs."""
    camp = create_test_campaign(qa_db, QA_SANDBOX_ORG_ID, "Completion Campaign", [{"channel": "email", "subject": "S1", "body": "B1"}])
    contact, cc = enroll_test_contact(qa_db, QA_SANDBOX_ORG_ID, camp.id, "optout@example.com")
    job_svc = CampaignExecutionJobService(qa_db)

    job = job_svc.enqueue_step_job(
        org_id=QA_SANDBOX_ORG_ID,
        campaign_id=camp.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        step_number=1,
        channel="email",
        execution_payload={"rendered_subject": "S1", "rendered_body": "B1"},
    )

    # Prospect opts out before send
    contact.lead_status = "opted_out"
    qa_db.commit()

    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    worker.run_single_tick(QA_SANDBOX_ORG_ID)

    qa_db.refresh(job)
    qa_db.refresh(cc)
    qa_db.refresh(camp)

    # Job held/cancelled, zero emails sent, enrollment completed
    assert job.status == "held"
    assert len(mock_email.sent_messages) == 0
    assert cc.enrollment_status == "completed"
    assert camp.status == "completed"


def test_scenario_16_strict_tenant_isolation(qa_db: Session):
    """Scenario 16: Worker processes Agile QA Sandbox, strictly rejecting unauthorized production org."""
    mock_email = RecordingMockEmailProvider()
    worker = CampaignJobWorker(qa_db, email_provider=mock_email, force_mock=True)

    # Attempt tick against production organization ID
    res_prod = worker.run_single_tick(PRODUCTION_ORG_ID)
    assert res_prod["status"] == "unauthorized"
    assert res_prod["processed_count"] == 0

    # Tick against QA sandbox organization ID succeeds
    res_qa = worker.run_single_tick(QA_SANDBOX_ORG_ID)
    assert res_qa["status"] == "success"
