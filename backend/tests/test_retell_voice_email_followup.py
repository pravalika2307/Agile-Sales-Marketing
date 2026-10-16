"""Comprehensive test suite for Retell AI Voice Call to Automated Email Follow-Up.

Covers all 15 required scenarios:
1. Retell call_analyzed webhook
2. Extracting customer email
3. Extracting customer name
4. Extracting customer company
5. Interested -> email sent
6. Meeting requested -> email sent
7. Callback requested -> appropriate email
8. Not interested -> no email
9. Do-not-contact -> no email
10. Missing email -> no email
11. Invalid email -> no email
12. Duplicate webhook -> only one email (strict idempotency)
13. Cross-tenant protection
14. Resend / provider failure handled gracefully
15. Retell webhook signature failure
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.call_record import CallRecord
from app.models.crm import Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.services.outreach.base import EmailMessage, EmailSendResult, MockEmailProvider
from app.services.outreach.voice_followup import (
    OUTCOME_CALLBACK_REQUESTED,
    OUTCOME_DO_NOT_CONTACT,
    OUTCOME_INTERESTED,
    OUTCOME_MEETING_REQUESTED,
    OUTCOME_NOT_INTERESTED,
    OUTCOME_QUALIFIED,
    OUTCOME_UNKNOWN,
    OUTCOME_WRONG_PERSON,
    VoiceFollowUpService,
)


TEST_SECRET = "retell_test_secret_key_12345"


def generate_retell_signature(raw_body: bytes, secret: str = TEST_SECRET) -> str:
    """Generate a valid Retell HMAC-SHA256 signature in v=<timestamp>,d=<digest> format."""
    timestamp = "1728400000"
    content_to_sign = f"{timestamp}.{raw_body.decode('utf-8')}"
    digest = hmac.new(
        secret.encode("utf-8"),
        content_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"v={timestamp},d={digest}"


def create_test_org(session, name: str = "Test Org") -> Organization:
    """Helper to create an organization with required non-null fields."""
    org = Organization(
        id=uuid.uuid4(),
        name=name,
        slug=f"org-{uuid.uuid4().hex[:8]}",
        billing_status="active",
    )
    session.add(org)
    session.commit()
    return org


# ── In-Memory SQLite Test Fixture ─────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Isolated in-memory SQLite database session for each test."""
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
        app.dependency_overrides.pop(get_db, None)


@asynccontextmanager
async def make_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> Dict[str, Any]:
    """Helper to register an organization and user, returning tokens and org info."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    data = resp.json()
    return {
        "access_token": data["tokens"]["access_token"],
        "organization_id": data["user"]["organization_id"],
        "headers": {"Authorization": f"Bearer {data['tokens']['access_token']}"},
    }


def build_sample_retell_payload(
    call_id: str = "call_test_123",
    agent_id: str = "agent_retell_test",
    event: str = "call_analyzed",
    outcome: str = "INTERESTED",
    lead_name: str = "Jane Smith",
    email: str = "jane.smith@acmecorp.com",
    company: str = "Acme Corp",
    job_title: str = "VP of Sales",
    meeting_requested: bool = False,
    callback_requested: bool = False,
    do_not_contact: bool = False,
    org_id: Optional[str] = None,
    phone_number: str = "+15551234567",
) -> Dict[str, Any]:
    """Build a realistic Retell voice call webhook payload."""
    return {
        "event": event,
        "call": {
            "call_id": call_id,
            "agent_id": agent_id,
            "call_status": "analyzed",
            "direction": "inbound",
            "from_number": phone_number,
            "to_number": "+15559876543",
            "duration_ms": 75000,
            "start_timestamp": 1728400000000,
            "end_timestamp": 1728400075000,
            "disconnection_reason": "agent_hangup",
            "transcript": "Hello, thank you for calling. I am interested in your software.",
            "collected_dynamic_variables": {
                "lead_full_name": lead_name,
                "email": email,
                "phone_number": phone_number,
                "company_name": company,
            },
            "call_analysis": {
                "call_summary": "Prospect called asking about pricing and requested follow-up.",
                "user_sentiment": "Positive",
                "call_successful": True,
                "custom_analysis_data": {
                    "lead_full_name": lead_name,
                    "email": email,
                    "phone_number": phone_number,
                    "company_name": company,
                    "job_title": job_title,
                    "interest_level": "high",
                    "call_outcome": outcome,
                    "meeting_requested": meeting_requested,
                    "callback_requested": callback_requested,
                    "do_not_contact": do_not_contact,
                },
            },
            "metadata": {
                "organization_id": org_id or "",
            },
        },
    }


# ── Scenario Tests ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_retell_call_analyzed_webhook_processing(test_db_session):
    """1. Retell call_analyzed webhook processes successfully and creates records."""
    async with make_client() as client:
        tenant = await register_tenant(client, "admin1@test.com", "Acme Tenant 1")
        payload = build_sample_retell_payload(
            call_id="call_001",
            outcome="INTERESTED",
            org_id=tenant["organization_id"],
        )
        raw_body = json.dumps(payload).encode("utf-8")
        sig = generate_retell_signature(raw_body, TEST_SECRET)

        with patch.object(settings, "RETELL_API_KEY", TEST_SECRET), \
             patch.object(settings, "RETELL_VERIFY_WEBHOOK_SIGNATURE", True), \
             patch("app.services.outreach.voice_followup.get_email_provider", return_value=MockEmailProvider()):

            resp = await client.post(
                "/api/v1/voice/retell-webhook",
                content=raw_body,
                headers={"Content-Type": "application/json", "x-retell-signature": sig},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["call_id"] == "call_001"
            assert data["event"] == "call_analyzed"
            assert data["followup_status"] == "sent"
            assert data["followup_email_id"] is not None

        # Verify DB records
        call_rec = test_db_session.execute(
            select(CallRecord).where(CallRecord.call_id == "call_001")
        ).scalar_one()
        assert call_rec.call_outcome == "INTERESTED"
        assert call_rec.followup_status == "sent"
        assert call_rec.followup_idempotency_key == "call_001:interested_followup"


def test_extract_customer_email(test_db_session):
    """2. Safely extract and validate customer email from diverse Retell payload variations."""
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    # Valid email in custom_analysis_data
    p1 = build_sample_retell_payload(email="Lead.Person@corp.co.uk")
    data1 = service.extract_call_data(p1)
    assert data1.email == "lead.person@corp.co.uk"

    # Valid email in flat format
    p2 = {
        "call_id": "flat_123",
        "agent_id": "agent_1",
        "collected_dynamic_variables": {"email": "hello@world.com"},
    }
    data2 = service.extract_call_data(p2)
    assert data2.email == "hello@world.com"

    # Invalid email rejected safely
    p3 = build_sample_retell_payload(email="not-an-email")
    data3 = service.extract_call_data(p3)
    assert data3.email is None


def test_extract_customer_name(test_db_session):
    """3. Safely extract customer name (full name, or split first/last)."""
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    # Full name in custom_analysis_data
    p1 = build_sample_retell_payload(lead_name="Eleanor Vance")
    data1 = service.extract_call_data(p1)
    assert data1.lead_full_name == "Eleanor Vance"

    # Fallback to first_name + last_name
    p2 = {
        "call": {
            "call_id": "call_name_test",
            "collected_dynamic_variables": {
                "first_name": "Thomas",
                "last_name": "Anderson",
            },
        }
    }
    data2 = service.extract_call_data(p2)
    assert data2.lead_full_name == "Thomas Anderson"


def test_extract_customer_company(test_db_session):
    """4. Safely extract company name and job title."""
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    p1 = build_sample_retell_payload(
        company="Stark Industries",
        job_title="Chief Technology Officer",
    )
    data1 = service.extract_call_data(p1)
    assert data1.company_name == "Stark Industries"
    assert data1.job_title == "Chief Technology Officer"


def test_interested_outcome_sends_email(test_db_session):
    """5. INTERESTED outcome triggers automated follow-up email and records outreach."""
    org = create_test_org(test_db_session, "Interested Org")

    mock_provider = MockEmailProvider()
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_interested_1",
        outcome="INTERESTED",
        lead_name="Sarah Connor",
        email="sarah@cyberdyne.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["followup_status"] == "sent"

    # Verify Outreach row
    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "sarah@cyberdyne.com")
    ).scalar_one()
    assert outreach.status == "sent"
    assert outreach.channel == "email"
    assert "Great speaking with you, Sarah" in outreach.subject
    assert "Thanks for speaking with us today." in outreach.body

    # Verify OutreachEvent
    event = test_db_session.execute(
        select(OutreachEvent).where(OutreachEvent.outreach_id == outreach.id)
    ).scalar_one()
    assert event.event_type == "sent"


def test_meeting_requested_outcome_sends_email(test_db_session):
    """6. MEETING_REQUESTED outcome sends meeting confirmation follow-up."""
    org = create_test_org(test_db_session, "Meeting Org")

    mock_provider = MockEmailProvider()
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_meeting_1",
        outcome="MEETING_REQUESTED",
        meeting_requested=True,
        lead_name="Bruce Wayne",
        email="bruce@wayneenterprises.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["followup_status"] == "sent"

    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "bruce@wayneenterprises.com")
    ).scalar_one()
    assert "upcoming meeting" in outreach.body
    assert "$" not in outreach.body
    assert "guarantee" not in outreach.body.lower()


def test_callback_requested_outcome_sends_email(test_db_session):
    """7. CALLBACK_REQUESTED outcome sends callback confirmation email."""
    org = create_test_org(test_db_session, "Callback Org")

    mock_provider = MockEmailProvider()
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_callback_1",
        outcome="CALLBACK_REQUESTED",
        callback_requested=True,
        lead_name="Peter Parker",
        email="peter@dailybugle.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["followup_status"] == "sent"

    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "peter@dailybugle.com")
    ).scalar_one()
    assert "Callback Request Confirmation" in outreach.subject
    assert "request for a callback" in outreach.body


def test_not_interested_outcome_no_email(test_db_session):
    """8. NOT_INTERESTED outcome does not send email."""
    org = create_test_org(test_db_session, "Not Interested Org")

    mock_provider = MagicMock(spec=MockEmailProvider)
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_ni_1",
        outcome="NOT_INTERESTED",
        lead_name="Diana Prince",
        email="diana@themiscira.gov",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "skipped"
    assert "not interested" in result["followup_reason"].lower()
    mock_provider.send.assert_not_called()

    # Verify no Outreach record created
    outreaches = test_db_session.execute(select(Outreach)).scalars().all()
    assert len(outreaches) == 0


def test_do_not_contact_outcome_no_email(test_db_session):
    """9. DO_NOT_CONTACT outcome strictly prohibits sending any email."""
    org = create_test_org(test_db_session, "DNC Org")

    mock_provider = MagicMock(spec=MockEmailProvider)
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_dnc_1",
        outcome="DO_NOT_CONTACT",
        do_not_contact=True,
        lead_name="Clark Kent",
        email="clark@dailyplanet.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "skipped"
    assert "do not contact" in result["followup_reason"].lower()
    mock_provider.send.assert_not_called()


def test_missing_email_no_email(test_db_session):
    """10. Missing email skips follow-up without errors."""
    org = create_test_org(test_db_session, "No Email Org")

    mock_provider = MagicMock(spec=MockEmailProvider)
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_no_email",
        outcome="INTERESTED",
        email="",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "skipped"
    assert "Missing or invalid recipient email" in result["followup_reason"]
    mock_provider.send.assert_not_called()


def test_invalid_email_no_email(test_db_session):
    """11. Invalid/malformed email skips follow-up without crashing."""
    org = create_test_org(test_db_session, "Bad Email Org")

    mock_provider = MagicMock(spec=MockEmailProvider)
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_bad_email",
        outcome="INTERESTED",
        email="invalid-email-format-without-at",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "skipped"
    assert "Missing or invalid recipient email" in result["followup_reason"]
    mock_provider.send.assert_not_called()


def test_duplicate_webhook_only_one_email_idempotent(test_db_session):
    """12. Duplicate webhook calls send only one email (strict idempotency)."""
    org = create_test_org(test_db_session, "Idempotent Org")

    send_call_count = 0

    class CountingMockProvider(MockEmailProvider):
        def send(self, message: EmailMessage) -> EmailSendResult:
            nonlocal send_call_count
            send_call_count += 1
            return super().send(message)

    provider = CountingMockProvider()
    service = VoiceFollowUpService(db=test_db_session, email_provider=provider)

    payload = build_sample_retell_payload(
        call_id="call_idempotent_999",
        outcome="INTERESTED",
        lead_name="Tony Stark",
        email="tony@starkindustries.com",
        org_id=str(org.id),
    )

    # First webhook execution
    r1 = service.process_call_analyzed(payload)
    assert r1["status"] == "success"
    assert r1["duplicate"] is False
    assert r1["followup_status"] == "sent"
    assert send_call_count == 1

    # Second webhook execution with the identical call_id
    r2 = service.process_call_analyzed(payload)
    assert r2["status"] == "success"
    assert r2["duplicate"] is True
    assert r2["followup_status"] == "sent"
    assert "already sent" in r2["followup_reason"].lower()
    # Provider must NOT have been called a second time
    assert send_call_count == 1

    # Verify only ONE outreach record exists in database
    outreaches = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "tony@starkindustries.com")
    ).scalars().all()
    assert len(outreaches) == 1


@pytest.mark.anyio
async def test_cross_tenant_protection(test_db_session):
    """13. Cross-tenant isolation prevents tenant B from seeing or mutating tenant A's records."""
    async with make_client() as client:
        t1 = await register_tenant(client, "tenant1@test.com", "Tenant 1 Corp")
        t2 = await register_tenant(client, "tenant2@test.com", "Tenant 2 Corp")

        # Process call for Tenant 1
        service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())
        payload1 = build_sample_retell_payload(
            call_id="call_t1_private",
            outcome="INTERESTED",
            email="lead@t1.com",
            org_id=t1["organization_id"],
        )
        service.process_call_analyzed(payload1)

        # Tenant 1 should see the record
        resp1 = await client.get("/api/v1/voice/call-records", headers=t1["headers"])
        assert resp1.status_code == 200
        records1 = resp1.json()
        assert len(records1) == 1
        assert records1[0]["call_id"] == "call_t1_private"

        # Tenant 2 must NOT see Tenant 1's call record
        resp2 = await client.get("/api/v1/voice/call-records", headers=t2["headers"])
        assert resp2.status_code == 200
        records2 = resp2.json()
        assert len(records2) == 0

        # Tenant 2 cannot access call by ID
        resp2_detail = await client.get("/api/v1/voice/call-records/call_t1_private", headers=t2["headers"])
        assert resp2_detail.status_code == 404


def test_resend_or_provider_failure_handled_gracefully(test_db_session):
    """14. Provider delivery failure records failed status without crashing or data loss."""
    org = create_test_org(test_db_session, "Provider Failure Org")

    # Mock provider configured to fail
    failing_provider = MockEmailProvider(should_fail=True, failure_reason="Resend API rate limit exceeded")
    service = VoiceFollowUpService(db=test_db_session, email_provider=failing_provider)

    payload = build_sample_retell_payload(
        call_id="call_fail_1",
        outcome="INTERESTED",
        email="lead@failtest.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["status"] == "failed"
    assert result["followup_status"] == "failed"
    assert "Resend API rate limit exceeded" in result["followup_reason"]

    # Verify CallRecord stored as failed
    call_rec = test_db_session.execute(
        select(CallRecord).where(CallRecord.call_id == "call_fail_1")
    ).scalar_one()
    assert call_rec.followup_status == "failed"

    # Verify Outreach stored with status=failed
    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "lead@failtest.com")
    ).scalar_one()
    assert outreach.status == "failed"


@pytest.mark.anyio
async def test_retell_webhook_signature_failure(test_db_session):
    """15. Invalid or missing Retell webhook signature returns 401 Unauthorized."""
    async with make_client() as client:
        tenant = await register_tenant(client, "sig_admin@test.com", "Sig Org")
        payload = build_sample_retell_payload(
            call_id="call_sig_test",
            org_id=tenant["organization_id"],
        )
        raw_body = json.dumps(payload).encode("utf-8")

        with patch.object(settings, "RETELL_API_KEY", TEST_SECRET), \
             patch.object(settings, "RETELL_VERIFY_WEBHOOK_SIGNATURE", True), \
             patch("app.services.outreach.voice_followup.get_email_provider", return_value=MockEmailProvider()):

            # Case A: Missing signature header
            resp_no_sig = await client.post(
                "/api/v1/voice/retell-webhook",
                content=raw_body,
                headers={"Content-Type": "application/json"},
            )
            assert resp_no_sig.status_code == 401
            assert "Invalid or missing Retell webhook signature" in resp_no_sig.json()["detail"]

            # Case B: Tampered / bad signature header
            resp_bad_sig = await client.post(
                "/api/v1/voice/retell-webhook",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "x-retell-signature": "v=1728400000,d=bad_tampered_digest_abc123",
                },
            )
            assert resp_bad_sig.status_code == 401
            assert "Invalid or missing Retell webhook signature" in resp_bad_sig.json()["detail"]

            # Case C: Valid signature header passes
            valid_sig = generate_retell_signature(raw_body, TEST_SECRET)
            resp_valid = await client.post(
                "/api/v1/voice/retell-webhook",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "x-retell-signature": valid_sig,
                },
            )
            assert resp_valid.status_code == 200


@pytest.mark.anyio
async def test_dev_replay_endpoint(test_db_session):
    """Replay endpoint works in development mode and executes follow-up flow."""
    async with make_client() as client:
        tenant = await register_tenant(client, "replay_admin@test.com", "Replay Org")
        payload = build_sample_retell_payload(
            call_id="call_replay_test_100",
            outcome="QUALIFIED",
            lead_name="Wanda Maximoff",
            email="wanda@avengers.org",
            org_id=tenant["organization_id"],
        )

        with patch.object(settings, "DEBUG", True), \
             patch("app.services.outreach.voice_followup.get_email_provider", return_value=MockEmailProvider()):
            resp = await client.post(
                "/api/v1/voice/replay-analyzed-call",
                json=payload,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["followup_status"] == "sent"
            assert data["call_id"] == "call_replay_test_100"


def test_call_started_and_ended_handlers(test_db_session):
    """Test call_started and call_ended lifecycle event persistence."""
    org = create_test_org(test_db_session, "Lifecycle Org")

    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    # 1. call_started
    start_payload = {
        "event": "call_started",
        "call": {
            "call_id": "call_lifecycle_1",
            "agent_id": "agent_test",
            "direction": "inbound",
            "start_timestamp": 1728400000000,
            "metadata": {"organization_id": str(org.id)},
        },
    }
    rec_start = service.handle_call_started(start_payload)
    assert rec_start.call_status == "in_progress"

    # 2. call_ended
    end_payload = {
        "event": "call_ended",
        "call": {
            "call_id": "call_lifecycle_1",
            "agent_id": "agent_test",
            "duration_ms": 45000,
            "disconnection_reason": "user_hangup",
            "end_timestamp": 1728400045000,
            "metadata": {"organization_id": str(org.id)},
        },
    }
    rec_end = service.handle_call_ended(end_payload)
    assert rec_end.call_status == "ended"
    assert rec_end.duration_ms == 45000


def test_retell_qualification_outcome_and_next_step_mapping(test_db_session):
    """Test exact Retell test values: qualification_outcome='interested' & next_step_action='send_info_email'."""
    org = create_test_org(test_db_session, "SDR Outcome Org")

    mock_provider = MockEmailProvider()
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_sdr_qual_01",
            "agent_id": "agent_sdr_01",
            "direction": "outbound",
            "call_status": "analyzed",
            "call_analysis": {
                "call_summary": "Prospect is interested in receiving an info email.",
                "custom_analysis_data": {
                    "qualification_outcome": "interested",
                    "next_step_action": "send_info_email",
                    "lead_interest_summary": "Interested in sales automation",
                    "email": "prospect@acmecorp.com",
                    "lead_full_name": "Jordan Belfort",
                },
            },
            "metadata": {"organization_id": str(org.id)},
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["followup_status"] == "sent"
    assert "interested_followup" in result["followup_reason"]

    # Verify Outreach created
    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "prospect@acmecorp.com")
    ).scalar_one()
    assert outreach.status == "sent"
    assert "Great speaking with you, Jordan" in outreach.subject


def test_retell_qualification_outcome_ineligible_skips_email(test_db_session):
    """Test qualification_outcome ineligibility: not_interested and do_not_call skip email."""
    org = create_test_org(test_db_session, "SDR Ineligible Org")

    mock_provider = MagicMock(spec=MockEmailProvider)
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    # 1. Not interested
    p_ni = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_sdr_ni",
            "agent_id": "agent_sdr_01",
            "call_status": "analyzed",
            "call_analysis": {
                "custom_analysis_data": {
                    "qualification_outcome": "not_interested",
                    "next_step_action": "close",
                    "email": "not_interested@example.com",
                },
            },
            "metadata": {"organization_id": str(org.id)},
        },
    }
    r_ni = service.process_call_analyzed(p_ni)
    assert r_ni["followup_status"] == "skipped"
    mock_provider.send.assert_not_called()

    # 2. Do not call / mark DNC
    p_dnc = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_sdr_dnc",
            "agent_id": "agent_sdr_01",
            "call_status": "analyzed",
            "call_analysis": {
                "custom_analysis_data": {
                    "qualification_outcome": "do_not_call",
                    "next_step_action": "mark_dnc",
                    "email": "dnc@example.com",
                },
            },
            "metadata": {"organization_id": str(org.id)},
        },
    }
    r_dnc = service.process_call_analyzed(p_dnc)
    assert r_dnc["followup_status"] == "skipped"
    mock_provider.send.assert_not_called()


def test_caller_email_and_custom_field_aliases_extracted(test_db_session):
    """Test that caller_email and alternative field names are extracted properly."""
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    p = {
        "call": {
            "call_id": "call_alias_test",
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_email": "inbound_caller@domain.org",
                    "caller_name": "Marcus Aurelius",
                    "caller_company": "Roman Empire LLC",
                },
            },
        },
    }
    data = service.extract_call_data(p)
    assert data.email == "inbound_caller@domain.org"
    assert data.lead_full_name == "Marcus Aurelius"
    assert data.company_name == "Roman Empire LLC"


# ==============================================================================
# SECTION 5 SPECIFIC TESTS: OUTBOUND (A - F) & INBOUND (G - L)
# ==============================================================================

OUTBOUND_AGENT_ID = "agent_3d80320b8eb60bcc212da34856"
INBOUND_AGENT_ID = "agent_46fb4b1901d63d803e5ef3030e"


def test_outbound_a_existing_lead_email_me(test_db_session):
    """A. Existing lead + 'email me' -> use stored Lead.email -> email follow-up sent."""
    org = create_test_org(test_db_session, "Outbound Org A")
    lead = Lead(
        organization_id=org.id,
        company_name="Apex Corp",
        first_name="Alice",
        last_name="Smith",
        email="stored_alice@apexcorp.com",
        phone="+15551010001",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_outbound_a_001",
            "agent_id": OUTBOUND_AGENT_ID,
            "direction": "outbound",
            "to_number": "+15551010001",
            "metadata": {
                "organization_id": str(org.id),
                "lead_id": str(lead.id),
                "campaign_id": str(uuid.uuid4()),
            },
            "call_analysis": {
                "custom_analysis_data": {
                    "next_step_action": "send_info_email",
                    "lead_interest_summary": "Prospect asked: 'Email me the details'",
                    "qualification_outcome": "qualified",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True
    assert mock_provider.send.call_count == 1
    sent_msg = mock_provider.send.call_args[0][0]
    assert sent_msg.to_email == "stored_alice@apexcorp.com"


def test_outbound_b_existing_lead_ai_extracts_different_email(test_db_session):
    """B. Existing lead + AI extracts a different email -> stored Lead.email remains authoritative -> send to stored email."""
    org = create_test_org(test_db_session, "Outbound Org B")
    lead = Lead(
        organization_id=org.id,
        company_name="Beta Dynamics",
        first_name="Bob",
        last_name="Johnson",
        email="authoritative_bob@betadynamics.com",
        phone="+15551010002",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_outbound_b_002",
            "agent_id": OUTBOUND_AGENT_ID,
            "direction": "outbound",
            "metadata": {
                "organization_id": str(org.id),
                "lead_id": str(lead.id),
            },
            "call_analysis": {
                "custom_analysis_data": {
                    "email": "hallucinated_ai_email@otherdomain.com",
                    "next_step_action": "send_info_email",
                    "qualification_outcome": "qualified",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True
    assert mock_provider.send.call_count == 1
    sent_msg = mock_provider.send.call_args[0][0]
    # Stored email MUST be used, NOT the AI extracted email
    assert sent_msg.to_email == "authoritative_bob@betadynamics.com"
    assert sent_msg.to_email != "hallucinated_ai_email@otherdomain.com"


def test_outbound_c_existing_lead_no_stored_email(test_db_session):
    """C. Existing lead + no stored email + 'email me' -> no email sent -> missing_email recorded."""
    org = create_test_org(test_db_session, "Outbound Org C")
    lead = Lead(
        organization_id=org.id,
        company_name="Gamma Labs",
        first_name="Charlie",
        last_name="Davis",
        email=None,  # No stored email
        phone="+15551010003",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_outbound_c_003",
            "agent_id": OUTBOUND_AGENT_ID,
            "direction": "outbound",
            "metadata": {
                "organization_id": str(org.id),
                "lead_id": str(lead.id),
            },
            "call_analysis": {
                "custom_analysis_data": {
                    "next_step_action": "send_info_email",
                    "lead_interest_summary": "Send me something",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    assert "missing_email" in result["followup_reason"]
    mock_provider.send.assert_not_called()


def test_outbound_d_existing_lead_not_interested(test_db_session):
    """D. Existing lead + NOT_INTERESTED -> no email."""
    org = create_test_org(test_db_session, "Outbound Org D")
    lead = Lead(
        organization_id=org.id,
        company_name="Delta Corp",
        email="delta_lead@example.com",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_outbound_d_004",
            "agent_id": OUTBOUND_AGENT_ID,
            "direction": "outbound",
            "metadata": {"organization_id": str(org.id), "lead_id": str(lead.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "qualification_outcome": "not_interested",
                    "next_step_action": "close",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    mock_provider.send.assert_not_called()


def test_outbound_e_existing_lead_do_not_contact(test_db_session):
    """E. Existing lead + DO_NOT_CONTACT -> no email."""
    org = create_test_org(test_db_session, "Outbound Org E")
    lead = Lead(
        organization_id=org.id,
        company_name="Epsilon Inc",
        email="epsilon_lead@example.com",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_outbound_e_005",
            "agent_id": OUTBOUND_AGENT_ID,
            "direction": "outbound",
            "metadata": {"organization_id": str(org.id), "lead_id": str(lead.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "qualification_outcome": "do_not_call",
                    "next_step_action": "mark_dnc",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    mock_provider.send.assert_not_called()


def test_outbound_f_duplicate_call_analyzed_webhook(test_db_session):
    """F. Duplicate call_analyzed webhook -> only one follow-up email."""
    org = create_test_org(test_db_session, "Outbound Org F")
    lead = Lead(
        organization_id=org.id,
        company_name="Foxtrot LLC",
        email="foxtrot_lead@example.com",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_outbound_f_006",
            "agent_id": OUTBOUND_AGENT_ID,
            "direction": "outbound",
            "metadata": {"organization_id": str(org.id), "lead_id": str(lead.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "next_step_action": "send_info_email",
                    "qualification_outcome": "qualified",
                },
            },
        },
    }

    res1 = service.process_call_analyzed(payload)
    assert res1["email_sent"] is True
    assert mock_provider.send.call_count == 1

    # Second identical webhook
    res2 = service.process_call_analyzed(payload)
    assert res2["duplicate"] is True
    assert res2["email_sent"] is False
    # Still only 1 email sent total
    assert mock_provider.send.call_count == 1


def test_inbound_g_known_caller_email_me(test_db_session):
    """G. Known caller/contact + 'email me' -> use stored Contact/Lead.email -> send email."""
    org = create_test_org(test_db_session, "Inbound Org G")
    contact = Contact(
        organization_id=org.id,
        first_name="Grace",
        last_name="Hopper",
        email="grace_stored@navy.mil",
        phone="+15552020001",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_inbound_g_007",
            "agent_id": INBOUND_AGENT_ID,
            "direction": "inbound",
            "from_number": "+15552020001",
            "metadata": {"organization_id": str(org.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_phone": "+15552020001",
                    "requested_followup": True,
                    "next_step_action": "send_info_email",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True
    assert mock_provider.send.call_count == 1
    sent_msg = mock_provider.send.call_args[0][0]
    assert sent_msg.to_email == "grace_stored@navy.mil"


def test_inbound_h_known_caller_ai_extracts_different_email(test_db_session):
    """H. Known caller + AI extracts a different email -> stored email remains authoritative."""
    org = create_test_org(test_db_session, "Inbound Org H")
    contact = Contact(
        organization_id=org.id,
        first_name="Henry",
        last_name="Ford",
        email="authoritative_henry@motors.com",
        phone="+15552020002",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_inbound_h_008",
            "agent_id": INBOUND_AGENT_ID,
            "direction": "inbound",
            "from_number": "+15552020002",
            "metadata": {"organization_id": str(org.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_phone": "+15552020002",
                    "caller_email": "ai_extracted_henry_different@other.com",
                    "requested_followup": True,
                    "next_step_action": "send_info_email",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True
    assert mock_provider.send.call_count == 1
    sent_msg = mock_provider.send.call_args[0][0]
    # Stored email must be used, not the AI extracted one
    assert sent_msg.to_email == "authoritative_henry@motors.com"
    assert sent_msg.to_email != "ai_extracted_henry_different@other.com"


def test_inbound_i_unknown_inbound_caller_provides_email(test_db_session):
    """I. Unknown inbound caller + provides email -> validate/capture email -> use for follow-up & sync CRM."""
    org = create_test_org(test_db_session, "Inbound Org I")

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    new_caller_phone = "+15552020099"
    new_caller_email = "new_prospect_inbound@startup.io"

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_inbound_i_009",
            "agent_id": INBOUND_AGENT_ID,
            "direction": "inbound",
            "from_number": new_caller_phone,
            "metadata": {"organization_id": str(org.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_name": "Isaac Newton",
                    "caller_company": "Gravity Research",
                    "caller_email": new_caller_email,
                    "caller_phone": new_caller_phone,
                    "requested_followup": True,
                    "next_step_action": "send_info_email",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True
    assert mock_provider.send.call_count == 1
    sent_msg = mock_provider.send.call_args[0][0]
    assert sent_msg.to_email == new_caller_email

    # Verify contact was created without duplicate
    saved_contact = test_db_session.execute(
        select(Contact).where(Contact.organization_id == org.id, Contact.email == new_caller_email)
    ).scalar_one_or_none()
    assert saved_contact is not None
    assert saved_contact.first_name == "Isaac"
    assert saved_contact.last_name == "Newton"


def test_inbound_j_unknown_inbound_caller_asks_email_provides_no_email(test_db_session):
    """J. Unknown inbound caller + asks for email but provides no email -> no email -> missing_email."""
    org = create_test_org(test_db_session, "Inbound Org J")

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_inbound_j_010",
            "agent_id": INBOUND_AGENT_ID,
            "direction": "inbound",
            "from_number": "+15552020055",
            "metadata": {"organization_id": str(org.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_phone": "+15552020055",
                    "caller_email": None,
                    "requested_followup": True,
                    "next_step_action": "send_info_email",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    assert "missing_email" in result["followup_reason"]
    mock_provider.send.assert_not_called()


def test_inbound_k_inbound_caller_says_do_not_contact(test_db_session):
    """K. Inbound caller says do not contact -> no email."""
    org = create_test_org(test_db_session, "Inbound Org K")

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_inbound_k_011",
            "agent_id": INBOUND_AGENT_ID,
            "direction": "inbound",
            "from_number": "+15552020066",
            "metadata": {"organization_id": str(org.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_email": "caller_dnc@example.com",
                    "call_outcome": "DO_NOT_CONTACT",
                    "qualification_outcome": "do_not_call",
                },
            },
        },
    }

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    mock_provider.send.assert_not_called()


def test_inbound_l_duplicate_inbound_webhook(test_db_session):
    """L. Duplicate inbound webhook -> no duplicate email."""
    org = create_test_org(test_db_session, "Inbound Org L")
    contact = Contact(
        organization_id=org.id,
        first_name="Leo",
        last_name="Tolstoy",
        email="leo_inbound@literature.org",
        phone="+15552020077",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_inbound_l_012",
            "agent_id": INBOUND_AGENT_ID,
            "direction": "inbound",
            "from_number": "+15552020077",
            "metadata": {"organization_id": str(org.id)},
            "call_analysis": {
                "custom_analysis_data": {
                    "caller_phone": "+15552020077",
                    "requested_followup": True,
                    "next_step_action": "send_info_email",
                },
            },
        },
    }

    res1 = service.process_call_analyzed(payload)
    assert res1["email_sent"] is True
    assert mock_provider.send.call_count == 1

    # Second delivery
    res2 = service.process_call_analyzed(payload)
    assert res2["duplicate"] is True
    assert res2["email_sent"] is False
    assert mock_provider.send.call_count == 1


# ── SEC-02: Organization Resolution & Quarantine Tests ─────────────────────────

def test_voice_webhook_unknown_org_quarantined_safely(test_db_session):
    """SEC-02: Webhooks with untagged/unknown organization are quarantined without arbitrary fallback."""
    # Ensure there is an organization in DB that previously would have been picked by LIMIT 1
    org_fallback_trap = create_test_org(test_db_session, "Arbitrary Org Trap")

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    # Webhook payload has NO organization_id in metadata or collected variables
    payload = build_sample_retell_payload(
        call_id="call_unresolved_001",
        email="unresolved@example.com",
        outcome="INTERESTED",
        org_id=None,
    )

    result = service.process_call_analyzed(payload)
    assert result["status"] == "quarantined"
    assert result["followup_status"] == "quarantined"
    assert result["email_sent"] is False
    mock_provider.send.assert_not_called()

    # Verify NO call record was created for the trap organization
    records = test_db_session.query(CallRecord).filter(CallRecord.organization_id == org_fallback_trap.id).all()
    assert len(records) == 0


@pytest.mark.anyio
async def test_voice_webhook_api_endpoint_unknown_org_quarantined(test_db_session):
    """SEC-02: Retell webhook endpoint safely quarantines events when organization cannot be resolved."""
    create_test_org(test_db_session, "Existing Org")

    async with make_client() as client:
        payload = build_sample_retell_payload(
            call_id="call_webhook_quarantine_002",
            org_id=None,
        )
        raw_body = json.dumps(payload).encode("utf-8")
        valid_sig = generate_retell_signature(raw_body, TEST_SECRET)

        with patch.object(settings, "RETELL_API_KEY", TEST_SECRET), \
             patch.object(settings, "RETELL_VERIFY_WEBHOOK_SIGNATURE", True), \
             patch("app.services.outreach.voice_followup.get_email_provider", return_value=MockEmailProvider()):

            resp = await client.post(
                "/api/v1/voice/retell-webhook",
                content=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "x-retell-signature": valid_sig,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "quarantined"
            assert data["followup_status"] == "quarantined"


def test_voice_webhook_opted_out_contact_skips_email(test_db_session):
    """SAF-01: Voice follow-up skips email dispatch if CRM contact is opted out."""
    org = create_test_org(test_db_session, "Safety FollowUp Org")
    contact = Contact(
        organization_id=org.id,
        first_name="Opted",
        last_name="OutUser",
        email="optedout_voice@example.com",
        lead_status="opted_out",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    service = VoiceFollowUpService(db=test_db_session, email_provider=mock_provider)

    payload = build_sample_retell_payload(
        call_id="call_optout_voice_003",
        email="optedout_voice@example.com",
        outcome="INTERESTED",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["email_sent"] is False
    assert result["followup_status"] == "skipped"
    assert "opted out" in (result.get("followup_reason") or "").lower()
    mock_provider.send.assert_not_called()


# ── Cooldown & Personalization Regression Tests ───────────────────────────────

def test_first_followup_for_recipient_sends_successfully(test_db_session):
    """REG-01: First follow-up for a recipient sends successfully."""
    org = create_test_org(test_db_session, "Cooldown Org 1")
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    payload = build_sample_retell_payload(
        call_id="call_cooldown_first_001",
        outcome="INTERESTED",
        lead_name="Alice Smith",
        email="alice@cooldowntest.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["status"] == "success"
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True

    outreaches = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "alice@cooldowntest.com")
    ).scalars().all()
    assert len(outreaches) == 1
    assert outreaches[0].status == "sent"
    assert outreaches[0].call_record_id is not None


def test_second_distinct_call_within_cooldown_is_skipped(test_db_session):
    """REG-02: A second distinct call to the same recipient within 24 hours is skipped."""
    org = create_test_org(test_db_session, "Cooldown Org 2")
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    # Call 1: Successful send
    p1 = build_sample_retell_payload(
        call_id="call_cooldown_c1",
        outcome="INTERESTED",
        lead_name="Bob Jones",
        email="bob@cooldowntest.com",
        org_id=str(org.id),
    )
    r1 = service.process_call_analyzed(p1)
    assert r1["followup_status"] == "sent"
    assert r1["email_sent"] is True

    # Call 2: Distinct call_id 3 hours later
    p2 = build_sample_retell_payload(
        call_id="call_cooldown_c2",
        outcome="INTERESTED",
        lead_name="Bob Jones",
        email="bob@cooldowntest.com",
        org_id=str(org.id),
    )
    r2 = service.process_call_analyzed(p2)
    assert r2["status"] == "success"
    assert r2["duplicate"] is False
    assert r2["followup_status"] == "skipped"
    assert r2["outcome_status"] == "skipped_cooldown"
    assert r2["email_sent"] is False
    assert "skipped_cooldown" in r2["followup_reason"]

    # Verify only ONE outreach record was created in the database
    outreaches = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "bob@cooldowntest.com")
    ).scalars().all()
    assert len(outreaches) == 1

    # Verify CallRecord 2 is marked skipped
    c2_rec = test_db_session.execute(
        select(CallRecord).where(CallRecord.call_id == "call_cooldown_c2")
    ).scalar_one()
    assert c2_rec.followup_status == "skipped"
    assert "skipped_cooldown" in c2_rec.followup_reason


def test_same_recipient_can_receive_followup_after_cooldown_expires(test_db_session):
    """REG-03: The same recipient can receive a follow-up after the 24-hour cooldown expires."""
    org = create_test_org(test_db_session, "Cooldown Expire Org")

    # Seed an old call and outreach record from 25 hours ago
    past_time = datetime.now(timezone.utc) - timedelta(hours=25)
    old_call = CallRecord(
        organization_id=org.id,
        call_id="call_past_001",
        agent_id="agent_1",
        direction="inbound",
        call_status="ended",
        call_outcome="INTERESTED",
        followup_status="sent",
        started_at=past_time,
        ended_at=past_time,
    )
    test_db_session.add(old_call)
    test_db_session.flush()

    old_outreach = Outreach(
        organization_id=org.id,
        channel="email",
        status="sent",
        recipient="charlie@cooldowntest.com",
        subject="Great speaking with you, Charlie",
        body="Hi Charlie,\n\nThanks for speaking with us today.",
        provider="mock",
        call_record_id=old_call.id,
        sent_at=past_time,
        created_at=past_time,
    )
    test_db_session.add(old_outreach)
    test_db_session.commit()

    # Now a new call arrives after cooldown expired
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())
    p = build_sample_retell_payload(
        call_id="call_now_002",
        outcome="INTERESTED",
        lead_name="Charlie",
        email="charlie@cooldowntest.com",
        org_id=str(org.id),
    )
    res = service.process_call_analyzed(p)
    assert res["followup_status"] == "sent"
    assert res["email_sent"] is True

    # Total outreaches is now 2
    outreaches = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "charlie@cooldowntest.com")
    ).scalars().all()
    assert len(outreaches) == 2


def test_different_organizations_do_not_block_each_other(test_db_session):
    """REG-04: Different organizations do not block one another for the same recipient email."""
    org1 = create_test_org(test_db_session, "Tenant 1 Org")
    org2 = create_test_org(test_db_session, "Tenant 2 Org")

    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    # Call in Org 1
    p1 = build_sample_retell_payload(
        call_id="call_org1_001",
        outcome="INTERESTED",
        lead_name="Shared Prospect",
        email="shared@enterprise.com",
        org_id=str(org1.id),
    )
    r1 = service.process_call_analyzed(p1)
    assert r1["followup_status"] == "sent"

    # Call in Org 2 for the same email
    p2 = build_sample_retell_payload(
        call_id="call_org2_001",
        outcome="INTERESTED",
        lead_name="Shared Prospect",
        email="shared@enterprise.com",
        org_id=str(org2.id),
    )
    r2 = service.process_call_analyzed(p2)
    assert r2["followup_status"] == "sent"
    assert r2["email_sent"] is True


def test_different_recipients_do_not_block_each_other(test_db_session):
    """REG-05: Different recipients in the same organization do not block one another."""
    org = create_test_org(test_db_session, "Multi-Recipient Org")
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    p1 = build_sample_retell_payload(
        call_id="call_recip_001",
        outcome="INTERESTED",
        lead_name="User A",
        email="usera@testcorp.com",
        org_id=str(org.id),
    )
    r1 = service.process_call_analyzed(p1)
    assert r1["followup_status"] == "sent"

    p2 = build_sample_retell_payload(
        call_id="call_recip_002",
        outcome="INTERESTED",
        lead_name="User B",
        email="userb@testcorp.com",
        phone_number="+15559998888",
        org_id=str(org.id),
    )
    r2 = service.process_call_analyzed(p2)
    assert r2["followup_status"] == "sent"
    assert r2["email_sent"] is True


def test_existing_per_call_idempotency_still_works(test_db_session):
    """REG-06: Existing per-call idempotency still returns duplicate=True on replay."""
    org = create_test_org(test_db_session, "Idempotency Org")
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    payload = build_sample_retell_payload(
        call_id="call_per_call_idem_001",
        outcome="INTERESTED",
        lead_name="Tony Stark",
        email="tony@avengers.org",
        org_id=str(org.id),
    )

    r1 = service.process_call_analyzed(payload)
    assert r1["followup_status"] == "sent"
    assert r1["duplicate"] is False

    r2 = service.process_call_analyzed(payload)
    assert r2["followup_status"] == "sent"
    assert r2["duplicate"] is True
    assert "already sent" in r2["followup_reason"].lower()


def test_campaign_outreach_does_not_trigger_voice_followup_cooldown(test_db_session):
    """REG-07: Campaign outreach does not incorrectly trigger voice follow-up cooldown."""
    org = create_test_org(test_db_session, "Campaign Cooldown Org")

    # Seed an unrelated campaign outreach (call_record_id is None) sent 1 hour ago
    recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
    campaign_outreach = Outreach(
        organization_id=org.id,
        channel="email",
        status="sent",
        recipient="campaign_prospect@test.com",
        subject="Strategic Briefing",
        body="Hello,\n\nPlease review this campaign briefing.",
        provider="mock",
        call_record_id=None,
        sent_at=recent_time,
        created_at=recent_time,
    )
    test_db_session.add(campaign_outreach)
    test_db_session.commit()

    # Incoming voice call for the same prospect
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())
    payload = build_sample_retell_payload(
        call_id="call_voice_after_campaign_001",
        outcome="INTERESTED",
        lead_name="Campaign Prospect",
        email="campaign_prospect@test.com",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"
    assert result["email_sent"] is True


def test_missing_webhook_name_resolves_from_scoped_contact(test_db_session):
    """REG-08: Missing webhook name resolves from an organization-scoped Contact."""
    org = create_test_org(test_db_session, "Contact Resolution Org")
    contact = Contact(
        organization_id=org.id,
        first_name="Diana",
        last_name="Prince",
        email="diana@amazon.net",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())
    # Webhook contains email, but lead_name is None
    payload = build_sample_retell_payload(
        call_id="call_name_contact_001",
        outcome="INTERESTED",
        lead_name=None,
        email="diana@amazon.net",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"

    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "diana@amazon.net")
    ).scalar_one()
    assert outreach.subject == "Great speaking with you, Diana"
    assert "Hi Diana," in outreach.body
    assert ", there" not in outreach.subject


def test_missing_webhook_name_resolves_from_scoped_lead_when_contact_unavailable(test_db_session):
    """REG-09: If Contact is unavailable, a suitable organization-scoped Lead supplies the name."""
    org = create_test_org(test_db_session, "Lead Resolution Org")
    lead = Lead(
        organization_id=org.id,
        first_name="Clark",
        last_name="Kent",
        email="clark@dailyplanet.net",
        company_name="Daily Planet",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())
    # Webhook has no name
    payload = build_sample_retell_payload(
        call_id="call_name_lead_001",
        outcome="INTERESTED",
        lead_name=None,
        email="clark@dailyplanet.net",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"

    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "clark@dailyplanet.net")
    ).scalar_one()
    assert outreach.subject == "Great speaking with you, Clark"
    assert "Hi Clark," in outreach.body
    assert ", there" not in outreach.subject


def test_no_name_in_webhook_or_database_produces_natural_fallback(test_db_session):
    """REG-10: No name in webhook or database produces the natural fallback without 'there'."""
    org = create_test_org(test_db_session, "Natural Fallback Org")
    service = VoiceFollowUpService(db=test_db_session, email_provider=MockEmailProvider())

    # Webhook has no name, and no contact or lead exists in DB
    payload = build_sample_retell_payload(
        call_id="call_fallback_001",
        outcome="INTERESTED",
        lead_name=None,
        email="anonymous@mystery.org",
        org_id=str(org.id),
    )

    result = service.process_call_analyzed(payload)
    assert result["followup_status"] == "sent"

    outreach = test_db_session.execute(
        select(Outreach).where(Outreach.recipient == "anonymous@mystery.org")
    ).scalar_one()
    # Subject must be the natural fallback: "Great speaking with you earlier"
    assert outreach.subject == "Great speaking with you earlier"
    # Greeting must be "Hello,"
    assert outreach.body.startswith("Hello,")
    # Must NEVER produce "Great speaking with you, there" or ", there"
    assert ", there" not in outreach.subject
    assert "there" not in outreach.subject.lower()


def test_failed_or_skipped_followups_do_not_block_future_cooldown(test_db_session):
    """REG-11: Failed or skipped follow-ups do not incorrectly count as successful sends for cooldown."""
    org = create_test_org(test_db_session, "Failed FollowUp Cooldown Org")

    # Call 1 fails delivery
    failing_provider = MockEmailProvider(should_fail=True, failure_reason="SMTP Network Timeout")
    service1 = VoiceFollowUpService(db=test_db_session, email_provider=failing_provider)

    p1 = build_sample_retell_payload(
        call_id="call_fail_001",
        outcome="INTERESTED",
        lead_name="Retry User",
        email="retry@example.com",
        org_id=str(org.id),
    )
    r1 = service1.process_call_analyzed(p1)
    assert r1["followup_status"] == "failed"

    # Call 2 arrives with working provider
    working_provider = MockEmailProvider()
    service2 = VoiceFollowUpService(db=test_db_session, email_provider=working_provider)

    p2 = build_sample_retell_payload(
        call_id="call_retry_002",
        outcome="INTERESTED",
        lead_name="Retry User",
        email="retry@example.com",
        org_id=str(org.id),
    )
    r2 = service2.process_call_analyzed(p2)
    # Must NOT be blocked by cooldown because previous outreach failed
    assert r2["followup_status"] == "sent"
    assert r2["email_sent"] is True





