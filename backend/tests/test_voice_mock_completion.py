"""Regression test suite for Retell Outbound Voice Mock Completion & Step 2 Email Advancement.

Verifies:
1. Deterministic mock completion mechanism transitions voice outreach from 'sending' to 'sent'.
2. Simulated call outcomes are explicitly marked as simulated (provider='mock', simulated=True).
3. Mock completion is strictly idempotent (duplicate completion events do not duplicate emails or regress state).
4. Positive interest outcome exercises Step 2 follow-up email with booking link (https://cal.com/agilereceivables/30min).
5. Disinterest outcome marks enrollment completed without generating email.
6. No-answer outcome marks outreach as failed without generating email.
7. Rejects non-mock / real provider calls if live calling is enabled.
8. API endpoint POST /api/v1/voice/simulate-mock-completion returns 200 OK with expected schema.
9. send_voice_outreach supports auto_complete_mock while preserving backward compatibility.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.services.organization_config import register_organization_booking_url
from app.services.outreach.base import MockEmailProvider
from app.services.voice.service import (
    VoiceServiceError,
    complete_simulated_voice_call,
    send_voice_outreach,
)


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def mock_voice_campaign_fixture(db_session: Session):
    """Sets up a complete voice campaign fixture with Step 1 (Voice) and Step 2 (Email)."""
    # 1. Organization
    org = Organization(
        name=f"Test Org Voice {uuid.uuid4().hex[:6]}",
        slug=f"test-org-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(org)
    db_session.flush()

    # Configure booking URL
    register_organization_booking_url(org.id, "https://cal.com/agilereceivables/30min")

    # 2. Company & Contact
    company = Company(
        organization_id=org.id,
        name="Acme Health Corp",
    )
    db_session.add(company)
    db_session.flush()

    contact = Contact(
        organization_id=org.id,
        company_id=company.id,
        first_name="Alexander",
        last_name="Wright",
        email="alexander.wright@acmehealth.com",
        phone="+14155552671",
        lead_status="open",
    )
    db_session.add(contact)
    db_session.flush()

    # 3. Campaign with Step 1 (voice) and Step 2 (email)
    campaign = Campaign(
        organization_id=org.id,
        name="Voice SDR Demo Campaign",
        status="active",
        workflow_config={
            "nodes": [
                {
                    "id": "node_1",
                    "type": "voice",
                    "step_order": 1,
                    "config": {
                        "agent_id": "agent_test_sdr_001",
                        "from_number": "+18005550199",
                    },
                },
                {
                    "id": "node_2",
                    "type": "email",
                    "step_order": 2,
                    "config": {
                        "template_subject": "Following up on our conversation, {contact.first_name}",
                        "template_body": "Hi {contact.first_name},\n\nGreat speaking with you regarding {contact.company}.\n\nPlease schedule a time here: {booking_link}\n\nBest,\n{sender_name}",
                    },
                },
            ]
        },
    )
    db_session.add(campaign)
    db_session.flush()

    step_2 = CampaignStep(
        organization_id=org.id,
        campaign_id=campaign.id,
        step_number=2,
        step_type="email",
        subject_template="Following up on our conversation, {contact.first_name}",
        body_template="Hi {contact.first_name},\n\nGreat speaking with you regarding {contact.company}.\n\nPlease schedule a time here: {booking_link}\n\nBest,\n{sender_name}",
        delay_days=0,
        delay_hours=0,
        is_active=True,
    )
    db_session.add(step_2)
    db_session.flush()

    # 4. Enrollment
    cc = CampaignContact(
        campaign_id=campaign.id,
        contact_id=contact.id,
        current_step=1,
        enrollment_status="in_progress",
    )
    db_session.add(cc)
    db_session.flush()

    # 5. In-flight Voice Outreach and CallRecord
    mock_call_id = f"call_mock_{uuid.uuid4().hex[:12]}"
    call_rec = CallRecord(
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        call_id=mock_call_id,
        agent_id="agent_test_sdr_001",
        direction="outbound",
        call_status="registered",
        caller_phone="+18005550199",
        to_phone="+14155552671",
        metadata_json={
            "organization_id": str(org.id),
            "campaign_id": str(campaign.id),
            "contact_id": str(contact.id),
            "campaign_contact_id": str(cc.id),
            "simulated": True,
        },
        followup_status="none",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call_rec)
    db_session.flush()

    outreach = Outreach(
        organization_id=org.id,
        campaign_id=campaign.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        call_record_id=call_rec.id,
        channel="voice",
        status="sending",
        provider="retell",
        provider_message_id=mock_call_id,
        recipient="+14155552671",
    )
    db_session.add(outreach)
    db_session.commit()

    return {
        "org": org,
        "campaign": campaign,
        "contact": contact,
        "company": company,
        "campaign_contact": cc,
        "outreach": outreach,
        "call_record": call_rec,
        "mock_call_id": mock_call_id,
    }


def test_simulate_mock_call_completion_positive_interest(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test deterministic mock completion with positive interest advances workflow to Step 2."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    outreach = env["outreach"]
    call_rec = env["call_record"]
    cc = env["campaign_contact"]

    # Initial state assertions
    assert outreach.status == "sending"
    assert call_rec.call_status == "registered"
    assert cc.current_step == 1
    assert cc.enrollment_status == "in_progress"

    # Complete simulated call
    response = complete_simulated_voice_call(
        db=db_session,
        org_id=org.id,
        outreach_id=outreach.id,
        outcome="INTERESTED",
        qualification_score=92,
        call_summary="Prospect expressed high interest in AI SDR automation.",
    )

    # Response assertions
    assert response.status == "success"
    assert response.simulated is True
    assert response.duplicate is False
    assert response.outreach_status == "sent"
    assert response.call_status == "analyzed"
    assert response.call_outcome == "INTERESTED"
    assert response.followup_email_created is True
    assert response.followup_email_id is not None

    # Database assertions
    db_session.refresh(outreach)
    db_session.refresh(call_rec)
    db_session.refresh(cc)

    assert outreach.status == "sent"
    assert outreach.provider == "mock"  # Explicitly marked as mock/simulated
    assert call_rec.call_status == "analyzed"
    assert call_rec.followup_status == "sent"

    # Verify Step 2 email outreach created
    followup_outreach = db_session.get(Outreach, uuid.UUID(response.followup_email_id))
    assert followup_outreach is not None
    assert followup_outreach.channel == "email"
    assert followup_outreach.status == "sent"
    assert followup_outreach.provider == "mock"
    assert followup_outreach.recipient == env["contact"].email
    assert "Alexander" in followup_outreach.body
    # Verify booking link merge variable resolved to organization booking url
    assert "https://cal.com/agilereceivables/30min" in followup_outreach.body

    # Campaign Contact must be advanced to Step 2
    assert cc.current_step == 2


def test_simulate_mock_call_completion_idempotency(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test duplicate completion triggers are idempotent and do not send duplicate emails."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    outreach = env["outreach"]
    cc = env["campaign_contact"]

    # First completion
    resp1 = complete_simulated_voice_call(
        db=db_session,
        org_id=org.id,
        outreach_id=outreach.id,
        outcome="INTERESTED",
    )
    assert resp1.duplicate is False
    assert resp1.followup_email_created is True
    first_email_id = resp1.followup_email_id

    # Second completion (duplicate event)
    resp2 = complete_simulated_voice_call(
        db=db_session,
        org_id=org.id,
        outreach_id=outreach.id,
        outcome="INTERESTED",
    )
    assert resp2.duplicate is True
    assert resp2.followup_email_id == first_email_id

    # Count email outreaches for this contact - must be exactly 1
    email_outreaches = (
        db_session.query(Outreach)
        .filter(
            Outreach.organization_id == org.id,
            Outreach.campaign_id == env["campaign"].id,
            Outreach.channel == "email",
        )
        .all()
    )
    assert len(email_outreaches) == 1

    db_session.refresh(cc)
    assert cc.current_step == 2


def test_simulate_mock_call_completion_negative_outcome(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test disinterest outcome completes call without sending follow-up email and halts campaign."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    outreach = env["outreach"]
    call_rec = env["call_record"]
    cc = env["campaign_contact"]

    response = complete_simulated_voice_call(
        db=db_session,
        org_id=org.id,
        outreach_id=outreach.id,
        outcome="NOT_INTERESTED",
        call_summary="Prospect not interested right now.",
    )

    assert response.status == "success"
    assert response.outreach_status == "sent"
    assert response.call_status == "analyzed"
    assert response.call_outcome == "NOT_INTERESTED"
    assert response.followup_email_created is False
    assert response.followup_status == "skipped"

    db_session.refresh(outreach)
    db_session.refresh(call_rec)
    db_session.refresh(cc)

    assert outreach.status == "sent"
    assert outreach.provider == "mock"
    assert call_rec.call_status == "analyzed"
    assert call_rec.followup_status == "skipped"

    # No email outreach created
    email_count = (
        db_session.query(Outreach)
        .filter(Outreach.organization_id == org.id, Outreach.channel == "email")
        .count()
    )
    assert email_count == 0

    # Contact enrollment marked completed (halt cold cadence)
    assert cc.enrollment_status == "completed"


def test_simulate_mock_call_completion_no_answer(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test no-answer outcome marks outreach failed without sending email."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    outreach = env["outreach"]
    call_rec = env["call_record"]

    response = complete_simulated_voice_call(
        db=db_session,
        org_id=org.id,
        outreach_id=outreach.id,
        outcome="NO_ANSWER",
        disconnection_reason="no_answer",
    )

    assert response.status == "success"
    assert response.outreach_status == "failed"
    assert response.call_outcome == "NO_ANSWER"
    assert response.followup_email_created is False

    db_session.refresh(outreach)
    db_session.refresh(call_rec)

    assert outreach.status == "failed"
    assert outreach.provider == "mock"
    assert call_rec.call_status == "analyzed"
    assert call_rec.followup_status == "skipped"


def test_simulate_mock_call_rejects_live_call(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test mock completion strictly rejects real provider calls when live calling is authorized."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    call_rec = env["call_record"]
    outreach = env["outreach"]

    # Assign a non-mock call ID and live provider
    real_call_id = f"call_real_provider_live_{uuid.uuid4().hex[:10]}"
    call_rec.call_id = real_call_id
    call_rec.metadata_json = {"simulated": False}
    outreach.provider = "retell"
    outreach.provider_message_id = real_call_id
    db_session.commit()

    from unittest.mock import PropertyMock
    with patch.object(type(settings), "is_retell_live_calling_allowed", new_callable=PropertyMock, return_value=True):
        with pytest.raises(VoiceServiceError, match="Cannot complete non-simulated call"):
            complete_simulated_voice_call(
                db=db_session,
                org_id=org.id,
                outreach_id=outreach.id,
                outcome="INTERESTED",
            )


def test_send_voice_outreach_auto_complete_mock(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test send_voice_outreach with auto_complete_mock=True deterministically executes full lifecycle."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    contact = env["contact"]
    campaign = env["campaign"]
    cc = env["campaign_contact"]

    # Create a new draft voice outreach
    draft_outreach = Outreach(
        organization_id=org.id,
        campaign_id=campaign.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        channel="voice",
        status="draft",
        recipient=contact.phone,
    )
    db_session.add(draft_outreach)
    db_session.commit()

    # Dispatch with auto_complete_mock=True
    completed_outreach = send_voice_outreach(
        db=db_session,
        org_id=org.id,
        outreach_id=draft_outreach.id,
        force_mock=True,
        auto_complete_mock=True,
        mock_outcome="INTERESTED",
    )

    db_session.refresh(completed_outreach)
    assert completed_outreach.status == "sent"
    assert completed_outreach.provider == "mock"
    assert completed_outreach.call_record_id is not None

    call_rec = db_session.get(CallRecord, completed_outreach.call_record_id)
    assert call_rec.call_status == "analyzed"
    assert call_rec.followup_status == "sent"


def test_send_voice_outreach_preserves_sending_default(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test default send_voice_outreach preserves in-flight status='sending' for backward compatibility."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    contact = env["contact"]
    campaign = env["campaign"]
    cc = env["campaign_contact"]

    draft_outreach = Outreach(
        organization_id=org.id,
        campaign_id=campaign.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        channel="voice",
        status="draft",
        recipient=contact.phone,
    )
    db_session.add(draft_outreach)
    db_session.commit()

    dispatched = send_voice_outreach(
        db=db_session,
        org_id=org.id,
        outreach_id=draft_outreach.id,
        force_mock=True,
        # Default auto_complete_mock is False
    )

    db_session.refresh(dispatched)
    assert dispatched.status == "sending"
    assert dispatched.provider_message_id.startswith("call_mock_")


def test_simulate_mock_completion_api_endpoint(db_session: Session, mock_voice_campaign_fixture: dict):
    """Test POST /api/v1/voice/simulate-mock-completion endpoint with tenant authentication."""
    env = mock_voice_campaign_fixture
    org = env["org"]
    outreach = env["outreach"]

    # Create user for authentication override
    user = User(
        organization_id=org.id,
        email=f"operator_{uuid.uuid4().hex[:8]}@acmehealth.com",
        hashed_password="test_hashed_password_123",
        full_name="Voice Campaign Operator",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    from app.api.deps import get_current_organization, get_current_user

    client = TestClient(app)
    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = client.post(
            "/api/v1/voice/simulate-mock-completion",
            json={
                "outreach_id": str(outreach.id),
                "outcome": "INTERESTED",
                "qualification_score": 88,
                "call_summary": "Test prospect answered and wants demo.",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "success"
        assert data["simulated"] is True
        assert data["outreach_status"] == "sent"
        assert data["call_status"] == "analyzed"
        assert data["call_outcome"] == "INTERESTED"
        assert data["followup_email_created"] is True
    finally:
        app.dependency_overrides.clear()
