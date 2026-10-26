"""Comprehensive unit and integration test suite for Twilio SMS integration.

CRITICAL SAFETY GUARANTEE:
Zero SMS messages sent during test execution.
Zero Twilio API credits consumed.
All SMS operations are verified via unit functions and MockSMSProvider.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from contextlib import asynccontextmanager
from typing import Generator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_organization
from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.tenant import Organization, User
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.services.sms.base import (
    SMSMessage,
    SMSSendResult,
    MockSMSProvider,
    normalize_phone_number,
    calculate_sms_segments,
)
from app.services.sms.twilio_provider import TwilioSMSProvider
from app.services.sms.service import (
    validate_recipient_phone,
    check_sms_consent,
    render_sms_message,
    preview_sms_step,
    send_sms_outreach,
    get_sms_provider,
)
from app.services.sms.webhook import (
    verify_twilio_signature,
    process_twilio_delivery_callback,
    WebhookSignatureVerificationError,
)


# ── SQLite In-Memory Test Fixture ─────────────────────────────────────────────

@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session for each test."""
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
async def make_test_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Helper for Creating Org & User ────────────────────────────────────────────

def create_test_tenant(db: Session, org_name: str = "Test Org", email: str = "user@test.org") -> tuple[Organization, User, str]:
    slug = f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(name=org_name, slug=slug)
    db.add(org)
    db.flush()

    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("SecurePassword123!"),
        full_name="Test Operator",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=user.role,
    )
    return org, user, token


# ── 1. Phone Number Normalization Tests ───────────────────────────────────────

def test_phone_normalization_valid_e164():
    """Valid international E.164 numbers are preserved."""
    is_valid, formatted, err = normalize_phone_number("+14155552671")
    assert is_valid is True
    assert formatted == "+14155552671"
    assert err is None

    is_valid, formatted, err = normalize_phone_number("+919876543210")
    assert is_valid is True
    assert formatted == "+919876543210"
    assert err is None

    is_valid, formatted, err = normalize_phone_number("+447911123456")
    assert is_valid is True
    assert formatted == "+447911123456"
    assert err is None


def test_phone_normalization_local_us_formats():
    """Common US formatted phone strings are normalized to +1 E.164."""
    for raw in ["(415) 555-2671", "415-555-2671", "415.555.2671", "4155552671", "1-415-555-2671"]:
        is_valid, formatted, err = normalize_phone_number(raw)
        assert is_valid is True, f"Failed on raw format: {raw}"
        assert formatted == "+14155552671", f"Incorrect normalization for: {raw}"
        assert err is None


def test_phone_normalization_invalid_and_empty():
    """Invalid, incomplete, and empty phone inputs are rejected."""
    for invalid in [None, "", "   ", "12345", "invalid-letters", "phone: 415-abc-2671"]:
        is_valid, formatted, err = normalize_phone_number(invalid)
        assert is_valid is False, f"Expected invalid for: {invalid}"
        assert err is not None


def test_validate_recipient_phone_helper():
    """validate_recipient_phone returns structured dictionary validation outcome."""
    valid_res = validate_recipient_phone("(415) 555-2671")
    assert valid_res["is_valid"] is True
    assert valid_res["formatted_phone"] == "+14155552671"
    assert valid_res["error_message"] is None

    invalid_res = validate_recipient_phone("too-short")
    assert invalid_res["is_valid"] is False
    assert invalid_res["formatted_phone"] == ""
    assert "Invalid phone number format" in invalid_res["error_message"]


# ── 2. Segment Math & Character Encoding Tests ────────────────────────────────

def test_sms_segment_math_gsm7_single_segment():
    """Standard ASCII under 160 chars fits in 1 GSM-7 segment."""
    body = "Hi Alex, this is John from Agile. Are you free for a brief call next week?"
    seg = calculate_sms_segments(body)
    assert seg["encoding"] == "GSM-7"
    assert seg["segment_count"] == 1
    assert seg["character_count"] == len(body)
    assert seg["max_per_segment"] == 160
    assert seg["remaining_in_segment"] == 160 - len(body)


def test_sms_segment_math_gsm7_multi_segment():
    """ASCII text over 160 characters splits into 153-character concatenated segments."""
    body = "A" * 165
    seg = calculate_sms_segments(body)
    assert seg["encoding"] == "GSM-7"
    assert seg["segment_count"] == 2
    assert seg["character_count"] == 165
    assert seg["max_per_segment"] == 153
    # 165 - 153 = 12 characters in segment 2; remaining = 153 - 12 = 141
    assert seg["remaining_in_segment"] == 141


def test_sms_segment_math_gsm7_extended_characters():
    """Extended GSM-7 characters ({, }, [, ], ^, |, ~, €) consume 2 septets."""
    body = "Price: €100 {special}"
    seg = calculate_sms_segments(body)
    assert seg["encoding"] == "GSM-7"
    # Basic len = 21, but € { } each add 1 extra -> character_count = 24
    assert seg["character_count"] == 24
    assert seg["segment_count"] == 1


def test_sms_segment_math_ucs2_unicode():
    """Messages with Unicode/emojis use UCS-2 (70 chars per single, 67 multi)."""
    body = "Meeting confirmed! 🚀 See you next Monday."
    seg = calculate_sms_segments(body)
    assert seg["encoding"] == "UCS-2"
    assert seg["segment_count"] == 1
    assert seg["max_per_segment"] == 70

    multi_body = "🔥" * 75
    multi_seg = calculate_sms_segments(multi_body)
    assert multi_seg["encoding"] == "UCS-2"
    assert multi_seg["segment_count"] == 2
    assert multi_seg["max_per_segment"] == 67


# ── 3. Mock Provider Behavior & Zero Live Send Guarantee ──────────────────────

def test_mock_provider_deterministic_send():
    """MockSMSProvider returns mock-sms ID without initiating any network traffic."""
    provider = MockSMSProvider()
    msg = SMSMessage(
        to_phone="+14155552671",
        body="Mock test message",
        from_phone="+15005550006",
    )
    result = provider.send(msg)

    assert result.success is True
    assert result.provider == "mock-twilio"
    assert result.provider_message_id.startswith("mock-sms-")
    assert result.error_message is None
    assert result.status == "sent"


# ── 4. Fail-Closed Safety Verification ────────────────────────────────────────

def test_twilio_provider_fails_closed_when_live_sending_disabled():
    """TwilioSMSProvider aborts before calling Twilio API if live sending is disabled."""
    from unittest.mock import patch
    with patch.object(settings, "TWILIO_ENABLED", False), patch.object(settings, "TWILIO_ALLOW_LIVE_SENDING", False):
        provider = TwilioSMSProvider(
            account_sid="ACmockaccountsid1234567890abcdef",
            auth_token="mockauthtoken1234567890abcdef",
            from_number="+15005550006",
        )
        msg = SMSMessage(
            to_phone="+14155552671",
            body="Test safety lock",
            from_phone="+15005550006",
        )
        result = provider.send(msg)

        # Must fail closed with explicit security error, without making an external request
        assert result.success is False
        assert result.provider == "twilio"
        assert "Real SMS sending is strictly disabled" in result.error_message
        assert result.provider_message_id == ""


def test_get_sms_provider_defaults_to_mock():
    """When TWILIO_ENABLED=False or TWILIO_ALLOW_LIVE_SENDING=False, get_sms_provider returns MockSMSProvider."""
    from unittest.mock import patch
    with patch.object(settings, "TWILIO_ENABLED", False):
        provider = get_sms_provider()
        assert isinstance(provider, MockSMSProvider)


# ── 5. Message Personalization & Booking Link Resolution ──────────────────────

def test_render_sms_message_with_personalization():
    """SMS templates resolve contact, sender, and booking link variables."""
    template = "Hi {contact.first_name}, {sender.name} here. Book here: {booking_link}"
    contact_data = {
        "first_name": "Priya",
        "contact.first_name": "Priya",
    }
    rendered = render_sms_message(
        template_body=template,
        contact_data=contact_data,
        booking_url="https://cal.com/agilereceivables/30min",
        sender_name="Agile Team",
    )

    assert "Hi Priya" in rendered
    assert "Agile Team" in rendered
    assert "https://cal.com/agilereceivables/30min" in rendered


def test_preview_sms_step_detects_unresolved_placeholders():
    """Unresolved variable tags are cleanly detected and reported in preview_sms_step."""
    template = "Hi {contact.first_name}, review {custom_offer} at {booking_link}"
    contact_data = {
        "first_name": "David",
        "phone": "+14155552671",
    }
    preview = preview_sms_step(
        template_body=template,
        contact_data=contact_data,
        booking_url="https://cal.com/agilereceivables/30min",
    )

    assert "{custom_offer}" in preview["unresolved_placeholders"]
    assert preview["character_count"] > 0
    assert preview["segment_count"] >= 1
    assert preview["phone_validation"]["is_valid"] is True


# ── 6. Consent & Opt-Out Suppression ──────────────────────────────────────────

def test_sms_consent_eligible_for_active_contact():
    """Active contact with phone number passes SMS consent check."""
    contact = Contact(
        organization_id=uuid.uuid4(),
        email="jane@example.com",
        first_name="Jane",
        last_name="Doe",
        phone="+14155552671",
        lead_status="new",
    )
    eligible, reason = check_sms_consent(contact)
    assert eligible is True
    assert reason is None


def test_sms_consent_rejected_when_phone_missing():
    """Contact without phone number fails consent check."""
    contact = Contact(
        organization_id=uuid.uuid4(),
        email="jane@example.com",
        first_name="Jane",
        last_name="Doe",
        phone=None,
        lead_status="new",
    )
    eligible, reason = check_sms_consent(contact)
    assert eligible is False
    assert "no phone number" in reason.lower()


def test_sms_consent_rejected_when_opted_out():
    """Contact with opted_out status fails consent check."""
    contact = Contact(
        organization_id=uuid.uuid4(),
        email="opted@example.com",
        first_name="Opted",
        last_name="User",
        phone="+14155552671",
        lead_status="opted_out",
    )
    eligible, reason = check_sms_consent(contact)
    assert eligible is False
    assert "opted out" in reason.lower()


# ── 7. Twilio Webhook Signature Verification & Idempotency ────────────────────

def test_verify_twilio_signature_valid():
    """Valid HMAC-SHA1 signature passes verification."""
    auth_token = "test_auth_token_secret_12345"
    url = "https://example.com/api/v1/sms/webhook"
    params = {
        "MessageSid": "SMmock12345",
        "MessageStatus": "delivered",
        "To": "+14155552671",
        "From": "+15005550006",
    }

    # Construct correct signature: URL + sorted key-values
    s = url
    for k in sorted(params.keys()):
        s += f"{k}{params[k]}"
    expected_mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    valid_signature = base64.b64encode(expected_mac).decode("utf-8")

    assert verify_twilio_signature(url, params, valid_signature, auth_token) is True


def test_verify_twilio_signature_tampered_or_missing():
    """Tampered parameters or invalid signatures are rejected."""
    auth_token = "test_auth_token_secret_12345"
    url = "https://example.com/api/v1/sms/webhook"
    params = {"MessageSid": "SMmock12345", "MessageStatus": "delivered"}

    assert verify_twilio_signature(url, params, "invalid_signature", auth_token) is False
    assert verify_twilio_signature(url, params, "", auth_token) is False
    assert verify_twilio_signature(url, params, None, auth_token) is False


def test_process_twilio_delivery_callback_idempotency(test_db_session: Session):
    """Delivery callbacks update outreach records idempotently without duplicate errors."""
    org, user, _ = create_test_tenant(test_db_session, "Delivery Org")

    # Create an outreach record with SMS channel and mock provider ID
    outreach = Outreach(
        organization_id=org.id,
        channel="sms",
        recipient="+14155552671",
        provider="mock",
        provider_message_id="mock-sms-idempotent-test",
        status="sent",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    # Process first delivery callback
    payload = {
        "MessageSid": "mock-sms-idempotent-test",
        "MessageStatus": "delivered",
        "To": "+14155552671",
        "From": "+15005550006",
    }
    result1 = process_twilio_delivery_callback(
        db=test_db_session,
        payload=payload,
        url="http://testserver/api/v1/sms/webhook",
        enforce_signature=False,
    )
    assert result1["status"] == "processed"
    assert result1["updated_status"] == "sent"

    # Verify database was updated
    test_db_session.refresh(outreach)
    assert outreach.first_delivered_at is not None

    # Process identical callback a second time (idempotency)
    result2 = process_twilio_delivery_callback(
        db=test_db_session,
        payload=payload,
        url="http://testserver/api/v1/sms/webhook",
        enforce_signature=False,
    )
    assert result2["status"] == "processed"
    assert result2["updated_status"] == "sent"


# ── 8. API Endpoints & Multi-Tenant Authorization ─────────────────────────────

@pytest.mark.asyncio
async def test_sms_config_status_endpoint(test_db_session: Session):
    """GET /api/v1/sms/config-status returns safe simulation status."""
    org, user, token = create_test_tenant(test_db_session, "Config Org")

    async with make_test_client() as client:
        res = await client.get(
            "/api/v1/sms/config-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] in ("mock", "mock-twilio", "twilio")
        assert "mode" in data
        assert "live_sending_allowed" in data


@pytest.mark.asyncio
async def test_sms_validate_phone_endpoint(test_db_session: Session):
    """POST /api/v1/sms/validate-phone normalizes phone numbers securely."""
    org, user, token = create_test_tenant(test_db_session, "Phone Org")

    async with make_test_client() as client:
        res = await client.post(
            "/api/v1/sms/validate-phone",
            json={"phone": "(415) 555-2671"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["is_valid"] is True
        assert data["formatted_phone"] == "+14155552671"


@pytest.mark.asyncio
async def test_sms_preview_endpoint(test_db_session: Session):
    """POST /api/v1/sms/preview calculates segments and renders personalized message."""
    org, user, token = create_test_tenant(test_db_session, "Preview Org")

    contact = Contact(
        organization_id=org.id,
        first_name="Maya",
        last_name="Lin",
        email="maya@preview.com",
        phone="+14155552671",
        lead_status="new",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    async with make_test_client() as client:
        res = await client.post(
            "/api/v1/sms/preview",
            json={
                "body": "Hi {contact.first_name}, check {booking_link}",
                "contact_id": str(contact.id),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "Hi Maya" in data["rendered_body"]
        assert data["segment_count"] >= 1
        assert data["consent_eligible"] is True


@pytest.mark.asyncio
async def test_sms_preview_cross_tenant_isolation(test_db_session: Session):
    """User from Org A cannot preview contacts belonging to Org B."""
    org_a, user_a, token_a = create_test_tenant(test_db_session, "Org A", "user_a@test.org")
    org_b, user_b, token_b = create_test_tenant(test_db_session, "Org B", "user_b@test.org")

    contact_b = Contact(
        organization_id=org_b.id,
        first_name="Secret",
        last_name="Contact",
        email="secret@orgb.com",
        phone="+14155559999",
        lead_status="new",
    )
    test_db_session.add(contact_b)
    test_db_session.commit()

    # User A tries to preview Contact B
    async with make_test_client() as client:
        res = await client.post(
            "/api/v1/sms/preview",
            json={
                "body": "Hi {contact.first_name}",
                "contact_id": str(contact_b.id),
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res.status_code == 404
        assert "Contact not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_sms_endpoints_require_authentication():
    """SMS preview and validation endpoints reject unauthenticated requests."""
    async with make_test_client() as client:
        res_preview = await client.post(
            "/api/v1/sms/preview",
            json={"body": "Hello"},
        )
        assert res_preview.status_code in (401, 403)

        res_phone = await client.post(
            "/api/v1/sms/validate-phone",
            json={"phone": "4155552671"},
        )
        assert res_phone.status_code in (401, 403)
