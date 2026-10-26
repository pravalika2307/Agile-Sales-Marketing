"""Phase 2 & Phase 3 End-to-End Verification Test Suite for Twilio SMS.

STRICT CONSTRAINTS & GUARANTEES:
- Uses MockSMSProvider and isolated in-memory test databases.
- ZERO live SMS messages sent.
- ZERO external HTTP requests to Twilio.
- Thoroughly validates outbound dispatch, suppression gates, retries, campaign execution,
  inbound webhooks, cryptographic HMAC-SHA1 signatures, idempotency, and audit trails.
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
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.sms import InboundSMSMessage, SMSSuppression
from app.models.tenant import Organization, User
from app.services.campaign_execution import execute_campaign
from app.services.outreach.service import retry_outreach
from app.services.sms.base import (
    MockSMSProvider,
    SMSMessage,
    calculate_sms_segments,
    normalize_phone_number,
)
from app.services.sms.service import (
    SMSConsentSuppressedError,
    SMSServiceError,
    get_sms_provider,
    is_sms_suppressed,
    preview_sms_step,
    render_sms_message,
    send_sms_outreach,
    validate_recipient_phone,
)
from app.services.sms.twilio_provider import TwilioSMSProvider
from app.services.sms.webhook import (
    is_inbound_sms,
    process_twilio_delivery_callback,
    process_twilio_inbound_message,
    verify_twilio_signature,
)


@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Isolated in-memory SQLite database session with complete schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)


def create_test_tenant(db: Session, name: str = "Test Org") -> tuple[Organization, Contact]:
    org = Organization(
        id=uuid.uuid4(),
        name=name,
        slug=f"org-{uuid.uuid4().hex[:8]}",
        billing_status="active",
    )
    db.add(org)
    db.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Alice",
        last_name="Smith",
        email=f"alice.{uuid.uuid4().hex[:6]}@example.com",
        phone="+14155552671",
        lead_status="new",
    )
    db.add(contact)
    db.commit()
    return org, contact


def generate_twilio_signature(url: str, params: Dict[str, Any], token: str) -> str:
    s = url
    for k in sorted(params.keys()):
        s += f"{k}{params[k]}"
    mac = hmac.new(token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: Outbound SMS Verification Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_p2_e164_phone_validation():
    """Verify standard E.164 international phone number normalization."""
    # Valid US numbers
    for raw in ["+14155552671", "(415) 555-2671", "415.555.2671", "1-415-555-2671"]:
        is_v, formatted, err = normalize_phone_number(raw)
        assert is_v is True, f"Failed for {raw}"
        assert formatted == "+14155552671"
        assert err is None

    # Valid international
    is_v, formatted, _ = normalize_phone_number("+447911123456")
    assert is_v is True and formatted == "+447911123456"

    # Invalid numbers
    for inv in ["", "  ", None, "123", "letters-only", "+000000"]:
        is_v, _, err = normalize_phone_number(inv)
        assert is_v is False
        assert err is not None


def test_p2_template_rendering_and_placeholder_resolution():
    """Verify SMS template placeholder rendering and unresolved placeholder detection."""
    template = "Hi {contact.first_name}, {sender.name} here. Book: {booking_link}"
    rendered = render_sms_message(
        template_body=template,
        contact_data={"first_name": "Bob", "contact.first_name": "Bob"},
        booking_url="https://cal.com/test/30min",
        sender_name="Agile Team",
    )
    assert rendered == "Hi Bob, Agile Team here. Book: https://cal.com/test/30min"

    # Preview with unresolved placeholder
    preview = preview_sms_step(
        template_body="Hi {contact.first_name}, see {missing_field}",
        contact_data={"first_name": "Bob", "phone": "+14155552671"},
    )
    assert "{missing_field}" in preview["unresolved_placeholders"]
    assert preview["phone_validation"]["is_valid"] is True


def test_p2_segment_calculation_gsm7_and_ucs2():
    """Verify segment math for GSM-7 (160/153) and UCS-2 Unicode (70/67)."""
    # GSM-7 single segment
    gsm_single = calculate_sms_segments("Hello world! Standard 7-bit GSM message.")
    assert gsm_single["encoding"] == "GSM-7"
    assert gsm_single["segment_count"] == 1
    assert gsm_single["max_per_segment"] == 160

    # GSM-7 multi-segment
    gsm_multi = calculate_sms_segments("A" * 165)
    assert gsm_multi["encoding"] == "GSM-7"
    assert gsm_multi["segment_count"] == 2
    assert gsm_multi["max_per_segment"] == 153

    # UCS-2 Unicode single segment
    ucs2_single = calculate_sms_segments("Hello 🚀")
    assert ucs2_single["encoding"] == "UCS-2"
    assert ucs2_single["segment_count"] == 1
    assert ucs2_single["max_per_segment"] == 70

    # UCS-2 Unicode multi-segment
    ucs2_multi = calculate_sms_segments("🚀" * 75)
    assert ucs2_multi["encoding"] == "UCS-2"
    assert ucs2_multi["segment_count"] == 2
    assert ucs2_multi["max_per_segment"] == 67


def test_p2_successful_mocked_dispatch(test_db_session: Session):
    """Verify successful dispatch using MockSMSProvider without real network requests."""
    org, contact = create_test_tenant(test_db_session, "Outbound Success Org")

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="draft",
        recipient=contact.phone,
        body="Hello Alice, this is a test dispatch.",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_prov = MockSMSProvider()
    result_outreach = send_sms_outreach(
        db=test_db_session,
        org_id=org.id,
        outreach_id=outreach.id,
        provider=mock_prov,
    )

    assert result_outreach.status == "sent"
    assert result_outreach.provider == "mock-twilio"
    assert result_outreach.provider_message_id.startswith("mock-sms-")
    assert result_outreach.sent_at is not None

    # Verify audit events persisted: 'sending' then 'sent'
    events = (
        test_db_session.query(OutreachEvent)
        .filter_by(outreach_id=outreach.id)
        .order_by(OutreachEvent.occurred_at.asc())
        .all()
    )
    assert len(events) == 2
    assert events[0].event_type == "sending"
    assert events[1].event_type == "sent"
    assert events[1].event_metadata["provider"] == "mock-twilio"


def test_p2_duplicate_send_prevention(test_db_session: Session):
    """Verify duplicate send prevention when status is already 'sent' or 'sending'."""
    org, contact = create_test_tenant(test_db_session, "Duplicate Guard Org")

    # Already sent outreach
    outreach_sent = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="sent",
        recipient=contact.phone,
        body="Already delivered.",
    )
    test_db_session.add(outreach_sent)

    # Currently sending outreach
    outreach_sending = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="sending",
        recipient=contact.phone,
        body="Currently delivering.",
    )
    test_db_session.add(outreach_sending)
    test_db_session.commit()

    mock_prov = MockSMSProvider()

    with pytest.raises(SMSServiceError) as exc_sent:
        send_sms_outreach(test_db_session, org.id, outreach_sent.id, provider=mock_prov)
    assert "already been sent" in str(exc_sent.value)

    with pytest.raises(SMSServiceError) as exc_sending:
        send_sms_outreach(test_db_session, org.id, outreach_sending.id, provider=mock_prov)
    assert "currently in the process of sending" in str(exc_sending.value)


def test_p2_suppression_blocking_direct_sends(test_db_session: Session):
    """Verify direct SMS dispatch is blocked when phone is recorded in SMSSuppression."""
    org, contact = create_test_tenant(test_db_session, "Suppression Direct Org")

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
        body="Hello Alice",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    with pytest.raises(SMSConsentSuppressedError) as exc:
        send_sms_outreach(test_db_session, org.id, outreach.id, provider=MockSMSProvider())

    assert "opted out of SMS" in str(exc.value)
    test_db_session.refresh(outreach)
    assert outreach.status == "draft"  # No state change


def test_p2_suppression_blocking_retries(test_db_session: Session):
    """Verify retrying a failed SMS outreach is blocked if recipient is suppressed."""
    org, contact = create_test_tenant(test_db_session, "Retry Suppression Org")

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Retry Test Campaign",
        status="active",
    )
    test_db_session.add(campaign)
    test_db_session.flush()

    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=campaign.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
    )
    test_db_session.add(cc)
    test_db_session.flush()

    # Failed outreach linked to campaign and campaign_contact
    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        campaign_contact_id=cc.id,
        contact_id=contact.id,
        channel="sms",
        status="failed",
        recipient=contact.phone,
        body="Hello Alice, please retry",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    # Now add suppression (e.g. user texted STOP after failure)
    suppression = SMSSuppression(
        organization_id=org.id,
        phone=contact.phone,
        contact_id=contact.id,
        keyword="STOP",
        reason="opt_out_keyword",
    )
    test_db_session.add(suppression)
    test_db_session.commit()

    # Attempting to retry must raise SMSConsentSuppressedError
    with pytest.raises(SMSConsentSuppressedError) as exc:
        retry_outreach(test_db_session, org.id, outreach.id, provider=MockSMSProvider())

    assert "opted out of SMS" in str(exc.value)


def test_p2_suppression_blocking_campaign_generated_sends(test_db_session: Session):
    """Verify campaign execution skips contacts whose phone is in SMSSuppression."""
    org, contact = create_test_tenant(test_db_session, "Campaign Suppression Org")

    # Add suppression
    suppression = SMSSuppression(
        organization_id=org.id,
        phone=contact.phone,
        contact_id=contact.id,
        keyword="STOP",
        reason="opt_out_keyword",
    )
    test_db_session.add(suppression)

    # Create active campaign with visual workflow config having Step 1 = SMS
    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="SMS Outreach Campaign",
        status="active",
        workflow_config={
            "nodes": [
                {"id": "start-node", "type": "start", "title": "Start", "config": {}},
                {
                    "id": "sms-node-1",
                    "type": "sms",
                    "title": "SMS Step 1",
                    "config": {
                        "body": "Hi {contact.first_name}, check this out!",
                        "is_active": True,
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "start-node", "target": "sms-node-1"},
            ],
        },
    )
    test_db_session.add(campaign)
    test_db_session.flush()

    cc = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=campaign.id,
        contact_id=contact.id,
        enrollment_status="queued",
    )
    test_db_session.add(cc)
    test_db_session.commit()

    # Execute campaign
    result = execute_campaign(test_db_session, org.id, campaign.id)

    # Contact was rejected due to suppression, zero outreaches created
    assert result.created_count == 0
    assert cc.id in result.rejected_campaign_contact_ids

    # No outreach records created
    outreach_count = (
        test_db_session.query(Outreach)
        .filter_by(organization_id=org.id, campaign_id=campaign.id)
        .count()
    )
    assert outreach_count == 0


def test_p2_cannot_fall_through_to_real_twilio():
    """Verify that get_sms_provider() strictly defaults to MockSMSProvider and TwilioSMSProvider fails closed."""
    from unittest.mock import patch
    with patch.object(settings, "TWILIO_ENABLED", False), patch.object(settings, "TWILIO_ALLOW_LIVE_SENDING", False):
        # 1. get_sms_provider returns MockSMSProvider
        prov = get_sms_provider()
        assert isinstance(prov, MockSMSProvider)

        # 2. TwilioSMSProvider fails closed when live sending is disabled
        twilio_prov = TwilioSMSProvider(
            account_sid="ACmocktest1234567890abcdef12345678",
            auth_token="mocktesttoken1234567890abcdef1234",
            from_number="+15005550006",
        )
        res = twilio_prov.send(SMSMessage(to_phone="+14155552671", body="Test message"))
        assert res.success is False
        assert res.provider == "twilio"
        assert "strictly disabled" in res.error_message


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3: Inbound SMS Verification Tests
# ══════════════════════════════════════════════════════════════════════════════

def test_p3_valid_signature_acceptance():
    """Verify inbound webhook accepts requests with valid Twilio HMAC-SHA1 signature."""
    token = "test_auth_token_secret_xyz"
    url = "https://example.com/api/v1/sms/webhook"
    params = {"Body": "STOP", "From": "+14155552671", "MessageSid": "SMtest123"}
    valid_sig = generate_twilio_signature(url, params, token)

    assert verify_twilio_signature(url, params, valid_sig, auth_token=token) is True


def test_p3_invalid_signature_rejection():
    """Verify inbound webhook rejects tampered signature, tampered body, and missing signature."""
    token = "test_auth_token_secret_xyz"
    url = "https://example.com/api/v1/sms/webhook"
    params = {"Body": "STOP", "From": "+14155552671", "MessageSid": "SMtest123"}
    valid_sig = generate_twilio_signature(url, params, token)

    # Tampered signature
    assert verify_twilio_signature(url, params, "tampered_sig_abc", auth_token=token) is False
    # Tampered payload body
    tampered_params = dict(params, Body="START")
    assert verify_twilio_signature(url, tampered_params, valid_sig, auth_token=token) is False
    # Missing / empty signature
    assert verify_twilio_signature(url, params, "", auth_token=token) is False
    assert verify_twilio_signature(url, params, None, auth_token=token) is False


def test_p3_inbound_stop_processing_and_durable_suppression(test_db_session: Session):
    """Verify inbound STOP creates durable SMSSuppression and records InboundSMSMessage."""
    org, contact = create_test_tenant(test_db_session, "Inbound Stop Org")

    payload = {
        "MessageSid": "SM_inbound_stop_verification_01",
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

    # Durable suppression persisted
    suppression = (
        test_db_session.query(SMSSuppression)
        .filter_by(organization_id=org.id, phone=contact.phone)
        .first()
    )
    assert suppression is not None
    assert suppression.keyword == "STOP"
    assert suppression.contact_id == contact.id

    # Inbound message log persisted
    inbound_log = (
        test_db_session.query(InboundSMSMessage)
        .filter_by(message_sid="SM_inbound_stop_verification_01")
        .first()
    )
    assert inbound_log is not None
    assert inbound_log.is_opt_out is True
    assert inbound_log.matched_contact_id == contact.id


def test_p3_duplicate_messagesid_handling(test_db_session: Session):
    """Verify idempotent processing: duplicate MessageSid returns already_processed without duplicate rows."""
    org, contact = create_test_tenant(test_db_session, "Idempotency Org")

    payload = {
        "MessageSid": "SM_duplicate_check_02",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "STOP",
    }
    url = "http://testserver/api/v1/sms/webhook"

    res1 = process_twilio_inbound_message(test_db_session, payload, url, enforce_signature=False)
    assert res1["status"] == "processed"

    res2 = process_twilio_inbound_message(test_db_session, payload, url, enforce_signature=False)
    assert res2["status"] == "already_processed"
    assert res2["is_opt_out"] is True

    # Count of inbound records is strictly 1
    inbound_count = (
        test_db_session.query(InboundSMSMessage)
        .filter_by(message_sid="SM_duplicate_check_02")
        .count()
    )
    assert inbound_count == 1


def test_p3_cancellation_of_pending_sms_outreach(test_db_session: Session):
    """Verify inbound STOP cancels pending scheduled SMS outreach and logs cancellation audit event."""
    org, contact = create_test_tenant(test_db_session, "Cancel Pending Org")

    scheduled = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="scheduled",
        recipient=contact.phone,
        body="Scheduled reminder message.",
    )
    test_db_session.add(scheduled)
    test_db_session.commit()

    payload = {
        "MessageSid": "SM_cancel_pending_03",
        "From": contact.phone,
        "To": "+17005550001",
        "Body": "CANCEL",
    }
    process_twilio_inbound_message(
        db=test_db_session,
        payload=payload,
        url="http://testserver/api/v1/sms/webhook",
        enforce_signature=False,
    )

    test_db_session.refresh(scheduled)
    assert scheduled.status == "cancelled"

    cancel_evt = (
        test_db_session.query(OutreachEvent)
        .filter_by(outreach_id=scheduled.id, event_type="cancelled")
        .first()
    )
    assert cancel_evt is not None
    assert cancel_evt.event_metadata["keyword"] == "CANCEL"


def test_p3_tenant_isolation(test_db_session: Session):
    """Verify tenant isolation: STOP in Tenant A does not suppress Tenant B."""
    shared_phone = "+14155557777"
    org_a, contact_a = create_test_tenant(test_db_session, "Tenant Alpha")
    org_b, contact_b = create_test_tenant(test_db_session, "Tenant Beta")
    contact_a.phone = shared_phone
    contact_b.phone = shared_phone

    outreach_a = Outreach(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        contact_id=contact_a.id,
        channel="sms",
        status="sent",
        recipient=shared_phone,
        body="Sent from Alpha",
    )
    test_db_session.add(outreach_a)
    test_db_session.commit()

    # User texts STOP in response to Org A's outreach
    payload = {
        "MessageSid": "SM_isolation_test_04",
        "From": shared_phone,
        "To": "+17005550001",
        "Body": "STOP",
    }
    process_twilio_inbound_message(
        db=test_db_session,
        payload=payload,
        url="http://testserver/api/v1/sms/webhook",
        enforce_signature=False,
    )

    # Org A: suppressed
    supp_a, _ = is_sms_suppressed(test_db_session, org_a.id, phone=shared_phone)
    assert supp_a is True

    # Org B: not suppressed
    supp_b, _ = is_sms_suppressed(test_db_session, org_b.id, phone=shared_phone)
    assert supp_b is False


def test_p3_delivery_status_callback_processing(test_db_session: Session):
    """Verify delivery status callbacks update outreach status and record delivery timestamp."""
    org, contact = create_test_tenant(test_db_session, "Delivery Callback Org")

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="sms",
        status="sent",
        recipient=contact.phone,
        provider="mock",
        provider_message_id="SM_delivery_status_check_05",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    payload = {
        "MessageSid": "SM_delivery_status_check_05",
        "MessageStatus": "delivered",
        "To": contact.phone,
        "From": "+17005550001",
    }
    res = process_twilio_delivery_callback(
        db=test_db_session,
        payload=payload,
        url="http://testserver/api/v1/sms/webhook",
        enforce_signature=False,
    )

    assert res["status"] == "processed"
    assert res["updated_status"] == "sent"

    test_db_session.refresh(outreach)
    assert outreach.first_delivered_at is not None
