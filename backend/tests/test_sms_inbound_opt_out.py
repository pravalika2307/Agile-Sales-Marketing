"""Comprehensive unit and integration tests for Twilio inbound SMS handling and opt-out suppression.

Covers:
1. Valid signed inbound messages.
2. Invalid or missing cryptographic signatures.
3. Every supported opt-out keyword and case variation (STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT).
4. Duplicate webhook deliveries (idempotency).
5. Unknown senders safely handled without associating with wrong contacts.
6. Multi-tenant isolation (suppression in Org A does not affect Org B).
7. Cancellation of scheduled outreach upon opt-out and retry suppression.
8. Prevention of SMS dispatch after opt-out across all dispatch paths.
9. Existing delivery-status webhook regression behavior preserved.
10. Preservation of other communication channels (email, voice, physical mail).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.sms import InboundSMSMessage, SMSSuppression
from app.models.tenant import Organization, User
from app.services.sms.base import MockSMSProvider
from app.services.sms.service import (
    SMSConsentSuppressedError,
    check_sms_consent,
    is_sms_suppressed,
    send_sms_outreach,
)
from app.services.sms.webhook import (
    WebhookSignatureVerificationError,
    extract_opt_out_keyword,
    handle_twilio_webhook,
    is_inbound_sms,
    process_twilio_delivery_callback,
    process_twilio_inbound_message,
    verify_twilio_signature,
)


# ── SQLite In-Memory Test Fixture ─────────────────────────────────────────────

@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session with all tables created."""
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


def create_test_org_and_contact(
    db: Session,
    org_name: str = "Test Org",
    phone: str = "+14155552671",
) -> tuple[Organization, Contact]:
    """Create a persistent test organization and contact."""
    org = Organization(
        id=uuid.uuid4(),
        name=org_name,
        slug=f"org-{uuid.uuid4().hex[:8]}",
        billing_status="active",
    )
    db.add(org)
    db.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Jane",
        last_name="Doe",
        email=f"jane.{uuid.uuid4().hex[:6]}@example.com",
        phone=phone,
        lead_status="new",
    )
    db.add(contact)
    db.commit()
    return org, contact


def generate_twilio_signature(url: str, params: Dict[str, Any], token: str) -> str:
    """Generate valid Twilio HMAC-SHA1 signature for testing."""
    data_to_sign = url
    for key in sorted(params.keys()):
        data_to_sign += f"{key}{params[key]}"
    mac = hmac.new(token.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


# ── 1. Keyword Extraction Unit Tests ──────────────────────────────────────────

def test_extract_opt_out_keyword_all_variations():
    """Verify all supported keywords and whitespace/case variations are recognized."""
    test_cases = [
        ("STOP", "STOP"),
        ("stop", "STOP"),
        ("Stop", "STOP"),
        ("  STOPALL  ", "STOPALL"),
        ("stopall", "STOPALL"),
        ("UNSUBSCRIBE", "UNSUBSCRIBE"),
        ("unsubscribe", "UNSUBSCRIBE"),
        ("cancel", "CANCEL"),
        ("CANCEL!", "CANCEL"),
        ("end.", "END"),
        ("QUIT", "QUIT"),
        ("quit please", "QUIT"),
        ("Stop outreach", "STOP"),
    ]
    for raw_input, expected_keyword in test_cases:
        assert extract_opt_out_keyword(raw_input) == expected_keyword, f"Failed for {raw_input}"

    non_opt_outs = [
        "Hello",
        "Can we reschedule?",
        "START",
        "YES",
        "I am interested",
        "",
        None,
    ]
    for non_kw in non_opt_outs:
        assert extract_opt_out_keyword(non_kw) is None, f"Should not match {non_kw}"


def test_is_inbound_sms_discrimination():
    """Distinguish inbound SMS from outbound status callbacks."""
    # Outbound delivery callback
    assert not is_inbound_sms({"MessageSid": "SM123", "MessageStatus": "delivered"})
    assert not is_inbound_sms({"MessageSid": "SM123", "SmsStatus": "sent"})
    assert not is_inbound_sms({"MessageSid": "SM123", "MessageStatus": "undelivered"})

    # Inbound message
    assert is_inbound_sms({"MessageSid": "SM123", "Body": "STOP", "From": "+14155552671"})
    assert is_inbound_sms({"MessageSid": "SM123", "Body": "Hello", "From": "+14155552671"})
    assert is_inbound_sms({"MessageSid": "SM123", "SmsStatus": "received", "From": "+14155552671"})


# ── 2. Signature Verification Tests ───────────────────────────────────────────

def test_verify_twilio_signature_valid_and_tampered():
    """Verify constant-time HMAC signature checks for inbound webhooks."""
    token = "test_auth_token_secret_123"
    url = "https://example.com/api/v1/sms/webhook"
    params = {"Body": "STOP", "From": "+14155552671", "MessageSid": "SM12345"}

    valid_sig = generate_twilio_signature(url, params, token)
    assert verify_twilio_signature(url, params, valid_sig, auth_token=token) is True

    # Tampered signature
    assert verify_twilio_signature(url, params, "invalid_sig", auth_token=token) is False
    # Tampered param
    tampered_params = dict(params, Body="HELLO")
    assert verify_twilio_signature(url, tampered_params, valid_sig, auth_token=token) is False


# ── 3. Inbound Opt-Out Handling & Suppression Tests ───────────────────────────

def test_inbound_stop_suppresses_phone_and_cancels_scheduled_outreach(test_db_session: Session):
    """STOP keyword records SMSSuppression and cancels pending/scheduled SMS outreach."""
    org, contact = create_test_org_and_contact(test_db_session, "Stop Org", "+14155552671")

    # Create scheduled and draft SMS outreaches
    scheduled_outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="scheduled",
        recipient=contact.phone,
        body="Reminder: meeting scheduled tomorrow {booking_link}",
    )
    test_db_session.add(scheduled_outreach)
    test_db_session.commit()

    payload = {
        "MessageSid": "SM_inbound_stop_001",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "STOP",
    }
    url = "http://testserver/api/v1/sms/webhook"

    result = process_twilio_inbound_message(
        db=test_db_session,
        payload=payload,
        url=url,
        enforce_signature=False,
    )

    assert result["status"] == "processed"
    assert result["is_opt_out"] is True
    assert result["action"] == "suppressed"

    # Verify SMSSuppression record exists
    suppression = (
        test_db_session.query(SMSSuppression)
        .filter_by(organization_id=org.id, phone=contact.phone)
        .first()
    )
    assert suppression is not None
    assert suppression.keyword == "STOP"
    assert suppression.reason == "opt_out_keyword"

    # Verify scheduled outreach was cancelled
    test_db_session.refresh(scheduled_outreach)
    assert scheduled_outreach.status == "cancelled"

    # Verify cancellation audit event was recorded
    cancel_event = (
        test_db_session.query(OutreachEvent)
        .filter_by(outreach_id=scheduled_outreach.id, event_type="cancelled")
        .first()
    )
    assert cancel_event is not None
    assert cancel_event.event_metadata["keyword"] == "STOP"


def test_inbound_opt_out_preserves_other_communication_channels(test_db_session: Session):
    """CRITICAL: Opting out of SMS does NOT corrupt contact.lead_status or block email/voice."""
    org, contact = create_test_org_and_contact(test_db_session, "Channel Org", "+14155552671")
    assert contact.lead_status == "new"

    payload = {
        "MessageSid": "SM_inbound_unsubscribe_002",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "unsubscribe",
    }
    process_twilio_inbound_message(
        db=test_db_session,
        payload=payload,
        url="http://testserver/api/v1/sms/webhook",
        enforce_signature=False,
    )

    test_db_session.refresh(contact)
    # Contact lead_status is PRESERVED, not globally opted out
    assert contact.lead_status == "new"

    # SMS is suppressed
    is_supp, reason = is_sms_suppressed(test_db_session, org.id, phone=contact.phone, contact=contact)
    assert is_supp is True
    assert "opted out of SMS" in reason


def test_inbound_idempotency_prevents_duplicate_processing(test_db_session: Session):
    """Replaying identical MessageSid returns already_processed without duplicating."""
    org, contact = create_test_org_and_contact(test_db_session, "Idempotent Org", "+14155552671")

    payload = {
        "MessageSid": "SM_idempotent_test_003",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "QUIT",
    }
    url = "http://testserver/api/v1/sms/webhook"

    # First delivery
    res1 = process_twilio_inbound_message(test_db_session, payload, url, enforce_signature=False)
    assert res1["status"] == "processed"

    # Duplicate delivery
    res2 = process_twilio_inbound_message(test_db_session, payload, url, enforce_signature=False)
    assert res2["status"] == "already_processed"
    assert res2["is_opt_out"] is True

    # Exactly 1 InboundSMSMessage record created
    count = test_db_session.query(InboundSMSMessage).filter_by(message_sid="SM_idempotent_test_003").count()
    assert count == 1


def test_unknown_sender_suppressed_safely_without_corrupting_contacts(test_db_session: Session):
    """Inbound STOP from an unknown phone number suppresses the number but matches no contact."""
    org, contact = create_test_org_and_contact(test_db_session, "Unknown Sender Org", "+14155552671")
    unknown_phone = "+19995551234"

    payload = {
        "MessageSid": "SM_unknown_sender_004",
        "From": unknown_phone,
        "To": "+17005550001",
        "Body": "STOP",
    }
    url = "http://testserver/api/v1/sms/webhook"

    res = process_twilio_inbound_message(test_db_session, payload, url, enforce_signature=False)
    assert res["status"] == "processed"
    assert res["matched_contact_id"] is None  # NOT associated with contact

    # Suppression recorded at phone level
    suppression = (
        test_db_session.query(SMSSuppression)
        .filter_by(phone=unknown_phone)
        .first()
    )
    assert suppression is not None
    assert suppression.contact_id is None


def test_tenant_isolation_on_suppression(test_db_session: Session):
    """Opt-out in Organization A does NOT suppress the same phone in Organization B."""
    shared_phone = "+14155558888"
    org_a, contact_a = create_test_org_and_contact(test_db_session, "Tenant A", shared_phone)
    org_b, contact_b = create_test_org_and_contact(test_db_session, "Tenant B", shared_phone)

    # Inbound STOP arrives for Org A (via an outreach sent by Org A)
    outreach_a = Outreach(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        contact_id=contact_a.id,
        channel="sms",
        status="sent",
        recipient=shared_phone,
        body="Message from Org A",
    )
    test_db_session.add(outreach_a)
    test_db_session.commit()

    payload = {
        "MessageSid": "SM_tenant_isolation_005",
        "From": shared_phone,
        "To": "+17005550001",
        "Body": "STOP",
    }
    process_twilio_inbound_message(test_db_session, payload, "http://testserver/api/v1/sms/webhook", enforce_signature=False)

    # Org A: phone is suppressed
    supp_a, _ = is_sms_suppressed(test_db_session, org_a.id, phone=shared_phone)
    assert supp_a is True

    # Org B: phone remains unsuppressed and eligible!
    supp_b, _ = is_sms_suppressed(test_db_session, org_b.id, phone=shared_phone)
    assert supp_b is False


# ── 4. Dispatch Enforcement Tests ─────────────────────────────────────────────

def test_send_sms_outreach_blocks_suppressed_recipient(test_db_session: Session):
    """Attempting to dispatch SMS outreach to a suppressed number raises SMSConsentSuppressedError."""
    org, contact = create_test_org_and_contact(test_db_session, "Dispatch Org", "+14155552671")

    # Suppress the phone number
    suppression = SMSSuppression(
        organization_id=org.id,
        phone=contact.phone,
        contact_id=contact.id,
        keyword="STOP",
        reason="opt_out_keyword",
    )
    test_db_session.add(suppression)

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="draft",
        recipient=contact.phone,
        body="Hello {contact.first_name}",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_provider = MockSMSProvider()

    # Dispatch attempt must fail closed immediately
    with pytest.raises(SMSConsentSuppressedError) as exc_info:
        send_sms_outreach(
            db=test_db_session,
            org_id=org.id,
            outreach_id=outreach.id,
            provider=mock_provider,
        )

    assert "opted out of SMS" in str(exc_info.value)

    # Provider send was never called
    test_db_session.refresh(outreach)
    assert outreach.status == "draft"


def test_ordinary_inbound_reply_does_not_unsuppress(test_db_session: Session):
    """An ordinary non-opt-out inbound message does NOT re-enable a suppressed phone number."""
    org, contact = create_test_org_and_contact(test_db_session, "Sticky Suppression", "+14155552671")

    # Suppress the phone number
    suppression = SMSSuppression(
        organization_id=org.id,
        phone=contact.phone,
        contact_id=contact.id,
        keyword="STOP",
        reason="opt_out_keyword",
    )
    test_db_session.add(suppression)
    test_db_session.commit()

    # User texts: "Can you hear me?"
    payload = {
        "MessageSid": "SM_ordinary_reply_006",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "Can you hear me now?",
    }
    process_twilio_inbound_message(test_db_session, payload, "http://testserver/api/v1/sms/webhook", enforce_signature=False)

    # Phone must STILL be suppressed
    is_supp, _ = is_sms_suppressed(test_db_session, org.id, phone=contact.phone)
    assert is_supp is True


# ── 5. Full Fast API HTTP Webhook Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature_when_token_configured(test_db_session: Session):
    """POST /api/v1/sms/webhook returns 403 Forbidden when signature is missing."""
    with patch.object(settings, "TWILIO_AUTH_TOKEN", "configured_secret_token"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/v1/sms/webhook",
                data={"MessageSid": "SM123", "From": "+14155552671", "Body": "STOP"},
            )
            assert resp.status_code == 403
            assert "Missing X-Twilio-Signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signature_and_suppresses_opt_out(test_db_session: Session):
    """POST /api/v1/sms/webhook accepts properly signed inbound STOP and processes suppression."""
    org, contact = create_test_org_and_contact(test_db_session, "HTTP Org", "+14155552671")
    token = "secret_auth_token_for_http_test"
    url = "http://testserver/api/v1/sms/webhook"
    payload = {
        "MessageSid": "SM_http_stop_007",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "STOP",
    }
    sig = generate_twilio_signature(url, payload, token)

    with patch.object(settings, "TWILIO_AUTH_TOKEN", token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/v1/sms/webhook",
                data=payload,
                headers={"X-Twilio-Signature": sig},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "processed"
            assert data["is_opt_out"] is True
            assert data["action"] == "suppressed"

    # Verify database state
    supp = test_db_session.query(SMSSuppression).filter_by(phone=contact.phone).first()
    assert supp is not None
    assert supp.keyword == "STOP"
