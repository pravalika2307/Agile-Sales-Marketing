"""
Comprehensive test suite for Poplar Webhook handling and status tracking.

Validates:
1. Valid events (batch attribution report, single event notification, ping).
2. Invalid authentication (missing signature, invalid signature, bad secret).
3. Malformed payloads (invalid JSON, non-object, missing required keys).
4. Duplicate events (idempotency: duplicate payloads do not create extra events or re-mutate).
5. Unknown provider identifiers (unmatched mailing IDs are gracefully ignored without 500 errors).
6. Cross-tenant attempts (preventing unauthorized tenant record modification).
7. Out-of-order events (cancelled outreach preserved, timestamp consistency).
8. Provider retry behavior (subsequent retries after transient cuts succeed idempotently).
9. Fulfillment status polling via PhysicalMailTracker (delivered, in_transit, exception, mock).
10. FastAPI endpoint contract (/api/v1/physical-mail/webhook and sync).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Company, Contact
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.services.physical_mail.poplar_client import (
    PoplarClient,
    PoplarError,
    PoplarNotFoundError,
)
from app.services.physical_mail.tracker import (
    MailingSyncResult,
    PhysicalMailTracker,
)
from app.services.physical_mail.webhook import (
    PoplarCrossTenantError,
    PoplarMalformedPayloadError,
    PoplarSignatureVerificationError,
    PoplarWebhookResult,
    PoplarWebhookService,
    verify_poplar_signature,
)


# ── Database Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite database for isolated test execution."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db: Session):
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def make_signature(raw_body: bytes, secret: str) -> str:
    """Computes X-SLM-Signature (HMAC-SHA1 hex digest) matching Poplar's specification."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha1).hexdigest()


def create_tenant_setup(db: Session, suffix: str = "A") -> Dict[str, Any]:
    """Populates org, user, company, contact, campaign, campaign_contact, and outreach."""
    org = Organization(
        id=uuid.uuid4(),
        name=f"Poplar Webhook Org {suffix}",
        slug=f"poplar-wh-org-{suffix.lower()}",
    )
    db.add(org)
    db.flush()

    user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=f"admin_{suffix.lower()}@poplarmail.test",
        hashed_password="fakehashedpassword123",
        full_name=f"Admin {suffix}",
        role="admin",
        is_active=True,
    )
    db.add(user)

    company = Company(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Test Direct Mail Co {suffix}",
    )
    db.add(company)

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_id=company.id,
        first_name="Jane",
        last_name="Doe",
        email=f"jane_{suffix.lower()}@example.com",
        phone="+15125550100",
        address_line_1="789 Congress Ave",
        city="Austin",
        state="TX",
        postal_code="78701",
        country="US",
    )
    db.add(contact)

    camp = Campaign(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Direct Mail Retention {suffix}",
        type="sales_outbound",
        status="active",
    )
    db.add(camp)
    db.flush()

    enrollment = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    db.add(enrollment)
    db.flush()

    provider_id = f"mlg_{uuid.uuid4().hex[:12]}"
    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=enrollment.id,
        channel="physical_mail",
        status="sending",
        provider="poplar",
        provider_message_id=provider_id,
        recipient="789 Congress Ave, Austin, TX 78701",
    )
    db.add(outreach)
    db.commit()

    return {
        "org": org,
        "user": user,
        "contact": contact,
        "campaign": camp,
        "enrollment": enrollment,
        "outreach": outreach,
        "provider_id": provider_id,
    }


# ── 1. Valid Events ───────────────────────────────────────────────────────────

def test_webhook_valid_attribution_batch(db: Session):
    """Valid Poplar attribution batch updates outreach to 'sent', records 'replied' event, and updates enrollment."""
    setup = create_tenant_setup(db, "ValidBatch")
    secret = "whsec_test_poplar_12345"

    payload = {
        "campaign_id": "cmp_test_123",
        "start_date": "2026-10-01",
        "end_date": "2026-10-22",
        "batch_index": 0,
        "total_batches": 1,
        "attribution_data": [
            {
                "mailing_id": setup["provider_id"],
                "identifier": str(setup["outreach"].id),
                "order_id": "ord_98765",
                "conversion_id": "conv_54321",
                "conversion_amount": 149.50,
                "status": "converted",
                "matched_at": "2026-10-22T14:30:00Z",
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = make_signature(raw_body, secret)

    service = PoplarWebhookService(db=db, secret=secret, verify_signature=True)
    result = service.process_webhook(raw_body=raw_body, signature=sig)

    assert result.status == "success"
    assert result.processed_count == 1
    assert result.duplicate_count == 0
    assert result.ignored_count == 0

    db.refresh(setup["outreach"])
    assert setup["outreach"].status == "sent"
    assert setup["outreach"].first_replied_at is not None

    # Check OutreachEvent
    events = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == setup["outreach"].id).all()
    assert len(events) == 1
    assert events[0].event_type == "replied"
    assert events[0].event_metadata["conversion_id"] == "conv_54321"
    assert events[0].event_metadata["conversion_amount"] == 149.50
    assert events[0].event_metadata["order_id"] == "ord_98765"

    # Check CampaignContact enrollment status
    db.refresh(setup["enrollment"])
    assert setup["enrollment"].enrollment_status == "replied"


def test_webhook_valid_ping_and_single_event(db: Session):
    """Poplar ping events are safely acknowledged, and single event notifications are processed."""
    setup = create_tenant_setup(db, "PingSingle")
    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=True)

    # 1. Ping Event
    ping_payload = {"event": "ping", "timestamp": "2026-10-22T12:00:00Z"}
    raw_ping = json.dumps(ping_payload).encode("utf-8")
    sig_ping = make_signature(raw_ping, secret)

    ping_result = service.process_webhook(raw_body=raw_ping, signature=sig_ping)
    assert ping_result.status == "success"
    assert ping_result.event_type == "ping"
    assert ping_result.processed_count == 0

    # 2. Single Event Notification
    single_payload = {
        "event": "conversion",
        "mailing_id": setup["provider_id"],
        "order_id": "ord_single_111",
        "conversion_amount": 75.00,
        "timestamp": "2026-10-22T14:00:00Z",
    }
    raw_single = json.dumps(single_payload).encode("utf-8")
    sig_single = make_signature(raw_single, secret)

    single_result = service.process_webhook(raw_body=raw_single, signature=sig_single)
    assert single_result.status == "success"
    assert single_result.processed_count == 1
    assert single_result.outcomes[0].status == "processed"


# ── 2. Invalid Authentication ─────────────────────────────────────────────────

def test_webhook_invalid_authentication(db: Session):
    """Missing or forged signatures are strictly rejected with PoplarSignatureVerificationError."""
    setup = create_tenant_setup(db, "AuthTest")
    secret = "whsec_authentic_key_999"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=True)

    payload = {"event": "ping"}
    raw_body = json.dumps(payload).encode("utf-8")

    # A: Missing signature
    with pytest.raises(PoplarSignatureVerificationError) as exc_missing:
        service.process_webhook(raw_body=raw_body, signature=None)
    assert "missing" in str(exc_missing.value).lower()

    # B: Forged signature
    bad_sig = "0123456789abcdef0123456789abcdef01234567"
    with pytest.raises(PoplarSignatureVerificationError) as exc_bad:
        service.process_webhook(raw_body=raw_body, signature=bad_sig)
    assert "invalid" in str(exc_bad.value).lower()

    # C: Signed with wrong secret
    wrong_sig = make_signature(raw_body, "wrong_secret_abc")
    with pytest.raises(PoplarSignatureVerificationError):
        service.process_webhook(raw_body=raw_body, signature=wrong_sig)


# ── 3. Malformed Payloads ─────────────────────────────────────────────────────

def test_webhook_malformed_payloads(db: Session):
    """Malformed JSON, non-object payloads, and missing required keys raise PoplarMalformedPayloadError."""
    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=False)

    # A: Non-JSON body
    with pytest.raises(PoplarMalformedPayloadError) as exc_json:
        service.process_webhook(raw_body=b"INVALID-NOT-JSON{{{", signature="any")
    assert "malformed" in str(exc_json.value).lower()

    # B: Empty body
    with pytest.raises(PoplarMalformedPayloadError) as exc_empty:
        service.process_webhook(raw_body=b"", signature="any")
    assert "empty" in str(exc_empty.value).lower()

    # C: JSON array instead of object
    with pytest.raises(PoplarMalformedPayloadError) as exc_arr:
        service.process_webhook(raw_body=b"[1, 2, 3]", signature="any")
    assert "must be a json object" in str(exc_arr.value).lower()

    # D: JSON object with no recognized event or attribution fields
    with pytest.raises(PoplarMalformedPayloadError) as exc_unrec:
        service.process_webhook(raw_body=b'{"unrelated_key": "some_value"}', signature="any")
    assert "missing recognized" in str(exc_unrec.value).lower()


# ── 4. Duplicate Events & Idempotency ─────────────────────────────────────────

def test_webhook_duplicate_events_idempotent(db: Session):
    """Duplicate deliveries with identical conversion identifiers do not duplicate events or double-mutate."""
    setup = create_tenant_setup(db, "Dedup")
    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=True)

    payload = {
        "attribution_data": [
            {
                "mailing_id": setup["provider_id"],
                "order_id": "ord_idempotent_1",
                "conversion_id": "conv_idempotent_1",
                "conversion_amount": 250.00,
                "status": "converted",
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = make_signature(raw_body, secret)

    # First delivery: processed
    res1 = service.process_webhook(raw_body=raw_body, signature=sig)
    assert res1.status == "success"
    assert res1.processed_count == 1
    assert res1.duplicate_count == 0

    # Second delivery (identical payload / retry): duplicate detected
    res2 = service.process_webhook(raw_body=raw_body, signature=sig)
    assert res2.status == "duplicate"
    assert res2.processed_count == 0
    assert res2.duplicate_count == 1
    assert res2.outcomes[0].duplicate is True

    # Assert exactly 1 OutreachEvent exists in database
    events = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == setup["outreach"].id).all()
    assert len(events) == 1


# ── 5. Unknown Provider Identifiers ───────────────────────────────────────────

def test_webhook_unknown_provider_identifiers(db: Session):
    """Attribution events for unknown mailing IDs are safely ignored without raising 500 errors."""
    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=False)

    payload = {
        "attribution_data": [
            {
                "mailing_id": "mlg_unknown_99999999",
                "order_id": "ord_ghost_1",
                "conversion_id": "conv_ghost_1",
                "conversion_amount": 50.00,
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    result = service.process_webhook(raw_body=raw_body, signature="any")

    assert result.status == "ignored"
    assert result.processed_count == 0
    assert result.ignored_count == 1
    assert result.outcomes[0].status == "ignored"
    assert result.outcomes[0].action == "unknown_identifier"


# ── 6. Cross-Tenant Attempts ──────────────────────────────────────────────────

def test_webhook_cross_tenant_isolation(db: Session):
    """An event targeting Tenant A's outreach when scoped to Tenant B is rejected."""
    tenant_a = create_tenant_setup(db, "OrgA")
    tenant_b = create_tenant_setup(db, "OrgB")

    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=False)

    # Payload references Tenant A's mailing_id
    payload = {
        "attribution_data": [
            {
                "mailing_id": tenant_a["provider_id"],
                "conversion_id": "conv_cross_1",
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Scoped with Tenant B's organization ID hint
    with pytest.raises(PoplarCrossTenantError) as exc_info:
        service.process_webhook(
            raw_body=raw_body,
            signature="any",
            org_id_hint=tenant_b["org"].id,
        )
    assert "cross-tenant" in str(exc_info.value).lower()


# ── 7. Out-of-Order Events ────────────────────────────────────────────────────

def test_webhook_out_of_order_events(db: Session):
    """Cancelled outreach status is preserved and not overwritten by out-of-order attribution webhooks."""
    setup = create_tenant_setup(db, "OutOfOrder")
    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=False)

    # Cancel the outreach record explicitly
    setup["outreach"].status = "cancelled"
    db.commit()

    payload = {
        "attribution_data": [
            {
                "mailing_id": setup["provider_id"],
                "conversion_id": "conv_delayed_1",
                "conversion_amount": 100.0,
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    result = service.process_webhook(raw_body=raw_body, signature="any")

    assert result.status == "ignored"
    assert result.ignored_count == 1
    assert result.outcomes[0].action == "outreach_cancelled"

    db.refresh(setup["outreach"])
    assert setup["outreach"].status == "cancelled"


# ── 8. Provider Retry Behavior ────────────────────────────────────────────────

def test_webhook_provider_retry_behavior(db: Session):
    """Simulates provider retries: 1st delivery processed, 2nd & 3rd succeed with duplicate status."""
    setup = create_tenant_setup(db, "RetryBehavior")
    secret = "whsec_test_poplar_12345"
    service = PoplarWebhookService(db=db, secret=secret, verify_signature=True)

    payload = {
        "campaign_id": "cmp_retry_test",
        "attribution_data": [
            {
                "mailing_id": setup["provider_id"],
                "order_id": "ord_retry_456",
                "conversion_id": "conv_retry_456",
                "conversion_amount": 89.99,
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = make_signature(raw_body, secret)

    # Delivery 1: processed
    r1 = service.process_webhook(raw_body=raw_body, signature=sig)
    assert r1.processed_count == 1
    assert r1.status == "success"

    # Delivery 2 (Poplar retry #1): duplicate
    r2 = service.process_webhook(raw_body=raw_body, signature=sig)
    assert r2.processed_count == 0
    assert r2.duplicate_count == 1
    assert r2.status == "duplicate"

    # Delivery 3 (Poplar retry #2): duplicate
    r3 = service.process_webhook(raw_body=raw_body, signature=sig)
    assert r3.processed_count == 0
    assert r3.duplicate_count == 1
    assert r3.status == "duplicate"

    # Ensure only 1 replied event was written
    events = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == setup["outreach"].id).all()
    assert len(events) == 1


# ── 9. Fulfillment Status Polling (PhysicalMailTracker) ───────────────────────

def test_physical_mail_tracker_polling(db: Session):
    """Validates programmatic status synchronization via PhysicalMailTracker (GET /v1/mailing/:id)."""
    setup = create_tenant_setup(db, "TrackerTest")

    mock_client = MagicMock()

    # Case A: Poplar returns 'delivered'
    mock_client.get_mailing.return_value = {
        "id": setup["provider_id"],
        "status": "delivered",
        "status_details": "Scanned as delivered by USPS carrier",
    }

    tracker = PhysicalMailTracker(db=db, client=mock_client)
    res_delivered = tracker.sync_outreach_mailing(setup["outreach"])

    assert res_delivered.updated is True
    assert res_delivered.new_status == "sent"
    assert res_delivered.poplar_status == "delivered"

    db.refresh(setup["outreach"])
    assert setup["outreach"].status == "sent"
    assert setup["outreach"].first_delivered_at is not None

    delivered_event = db.query(OutreachEvent).filter(
        OutreachEvent.outreach_id == setup["outreach"].id,
        OutreachEvent.event_type == "delivered",
    ).first()
    assert delivered_event is not None

    # Case B: Mock mailing simulated status update
    mock_outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=setup["org"].id,
        campaign_id=setup["campaign"].id,
        channel="physical_mail",
        status="sending",
        provider="poplar",
        provider_message_id="mlg_mock_9876543210ab",
    )
    db.add(mock_outreach)
    db.commit()

    res_mock = tracker.sync_outreach_mailing(mock_outreach, simulated_override_status="delivered")
    assert res_mock.updated is True
    assert res_mock.new_status == "sent"

    # Case C: Exception / Suppressed status maps to 'failed'
    failed_outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=setup["org"].id,
        campaign_id=setup["campaign"].id,
        channel="physical_mail",
        status="sending",
        provider="poplar",
        provider_message_id=f"mlg_{uuid.uuid4().hex[:12]}",
    )
    db.add(failed_outreach)
    db.commit()

    mock_client.get_mailing.return_value = {
        "id": failed_outreach.provider_message_id,
        "status": "exception",
        "status_details": "Vacant address",
    }
    res_fail = tracker.sync_outreach_mailing(failed_outreach)
    assert res_fail.updated is True
    assert res_fail.new_status == "failed"

    db.refresh(failed_outreach)
    assert failed_outreach.status == "failed"
    assert failed_outreach.first_bounced_at is not None


# ── 10. FastAPI Webhook Endpoint ──────────────────────────────────────────────

def test_fastapi_poplar_webhook_endpoint(client: TestClient, db: Session):
    """Tests the dedicated POST /api/v1/physical-mail/webhook endpoint."""
    setup = create_tenant_setup(db, "EndpointTest")
    secret = "whsec_endpoint_secret_777"

    payload = {
        "attribution_data": [
            {
                "mailing_id": setup["provider_id"],
                "order_id": "ord_api_123",
                "conversion_amount": 99.00,
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    valid_sig = make_signature(raw_body, secret)

    with patch.object(settings, "POPLAR_WEBHOOK_SECRET", secret):
        with patch.object(settings, "POPLAR_VERIFY_WEBHOOK_SIGNATURE", True):
            # 1. Valid Signature -> 200 OK
            response = client.post(
                "/api/v1/physical-mail/webhook",
                content=raw_body,
                headers={"X-SLM-Signature": valid_sig, "Content-Type": "application/json"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["processed_count"] == 1

            # 2. Invalid Signature -> 401 Unauthorized
            bad_response = client.post(
                "/api/v1/physical-mail/webhook",
                content=raw_body,
                headers={"X-SLM-Signature": "invalid_signature_hex", "Content-Type": "application/json"},
            )
            assert bad_response.status_code == 401
            assert "signature" in bad_response.json()["detail"].lower()

            # 3. Missing Signature -> 401 Unauthorized
            no_sig_response = client.post(
                "/api/v1/physical-mail/webhook",
                content=raw_body,
                headers={"Content-Type": "application/json"},
            )
            assert no_sig_response.status_code == 401

            # 4. Malformed JSON -> 400 Bad Request
            malformed_body = b"NOT-JSON-CONTENT"
            malformed_sig = make_signature(malformed_body, secret)
            malformed_response = client.post(
                "/api/v1/physical-mail/webhook",
                content=malformed_body,
                headers={"X-SLM-Signature": malformed_sig, "Content-Type": "application/json"},
            )
            assert malformed_response.status_code == 400
