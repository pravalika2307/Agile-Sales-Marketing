"""Security and reliability test suite for Phase B.1 (Outreach Tracking Remediation).

Validates:
1. Inbound webhook authentication (X-Webhook-Secret, Authorization: Bearer, fail-closed when unconfigured).
2. Multi-tenant isolation and ambiguous reply association guards (Tenant A vs Tenant B collision).
3. AWS SNS cryptographic signature verification, untrusted cert URL rejection, malformed envelope guards.
4. AWS SNS SubscriptionConfirmation safety (URL validation and safe confirmation).
5. Idempotent webhook processing and duplicate event suppression across Delivery, Open, Bounce, Reply.
"""
from __future__ import annotations

import base64
import datetime
import json
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Tuple

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
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
from app.models.tenant import Organization, User
from app.services.campaign_scheduler import CampaignSchedulerService
from app.services.outreach.sns_verifier import _CERT_CACHE, is_valid_sns_cert_url, is_valid_sns_subscribe_url


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


def generate_test_sns_key_and_cert(host: str = "sns.us-east-2.amazonaws.com") -> Tuple[rsa.RSAPrivateKey, bytes, str]:
    """Generate in-memory test RSA key, self-signed certificate, and trusted AWS cert URL."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_url = f"https://{host}/SimpleNotificationService-{uuid.uuid4().hex[:8]}.pem"
    # Pre-cache cert to avoid external network calls during tests
    _CERT_CACHE[cert_url] = (cert, datetime.datetime.now(datetime.timezone.utc).timestamp() + 3600)
    return key, cert_pem, cert_url


def create_signed_sns_notification(
    key: rsa.RSAPrivateKey,
    cert_url: str,
    message_dict: dict,
    subject: str = "Amazon SES Notification",
    topic_arn: str = "arn:aws:sns:us-east-2:123456789012:MyTopic",
    message_id: str = "sns-msg-12345",
    sig_version: str = "2",
) -> Dict[str, str]:
    """Build and cryptographically sign an AWS SNS Notification envelope."""
    msg_json = json.dumps(message_dict)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    keys = ["Message", "MessageId"]
    if subject is not None:
        keys.append("Subject")
    keys.extend(["Timestamp", "TopicArn", "Type"])

    raw_fields = {
        "Type": "Notification",
        "MessageId": message_id,
        "TopicArn": topic_arn,
        "Subject": subject,
        "Message": msg_json,
        "Timestamp": timestamp,
        "SignatureVersion": sig_version,
        "SigningCertURL": cert_url,
    }

    signable = "".join(f"{k}\n{raw_fields[k]}\n" for k in keys)
    hash_algo = hashes.SHA256() if sig_version == "2" else hashes.SHA1()
    raw_sig = key.sign(signable.encode("utf-8"), padding.PKCS1v15(), hash_algo)
    raw_fields["Signature"] = base64.b64encode(raw_sig).decode("ascii")

    return raw_fields


# ── SECTION 1: INBOUND WEBHOOK AUTHENTICATION ────────────────────────────────

@pytest.mark.asyncio
async def test_inbound_reply_webhook_rejects_when_secret_unconfigured(test_db_session, monkeypatch):
    """Fails closed: if INBOUND_REPLY_WEBHOOK_SECRET is None/empty, all requests are rejected with 401."""
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", None)
    async with make_client() as client:
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={"from_email": "prospect@example.com", "body": "Hello"},
            headers={"X-Webhook-Secret": "any-token"},
        )
        assert resp.status_code == 401
        assert "not configured" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_inbound_reply_webhook_rejects_missing_credentials(test_db_session, monkeypatch):
    """Rejects request with 401 when no auth headers are provided."""
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "super-secret-key-123")
    async with make_client() as client:
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={"from_email": "prospect@example.com", "body": "Hello"},
        )
        assert resp.status_code == 401
        assert "Invalid or missing webhook authentication credentials" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_inbound_reply_webhook_rejects_invalid_credentials(test_db_session, monkeypatch):
    """Rejects request with 401 when wrong secret is provided."""
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "super-secret-key-123")
    async with make_client() as client:
        # Invalid X-Webhook-Secret
        resp1 = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={"from_email": "prospect@example.com", "body": "Hello"},
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        assert resp1.status_code == 401

        # Invalid Authorization Bearer
        resp2 = await client.post(
            "/api/v1/outreach/tracking/inbound-reply",
            json={"from_email": "prospect@example.com", "body": "Hello"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_inbound_reply_webhook_accepts_valid_headers_on_both_aliases(test_db_session, monkeypatch):
    """Accepts valid credentials via X-Webhook-Secret and Authorization: Bearer on both route aliases."""
    db: Session = test_db_session
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "trusted-inbound-secret-789")

    # Seed Organization, Contact, Outreach
    org = Organization(name="Auth Test Org", slug="auth-test-org")
    db.add(org)
    db.commit()

    contact = Contact(organization_id=org.id, first_name="Alice", last_name="Prospect", email="alice@corp.com")
    db.add(contact)
    db.commit()

    outreach = Outreach(
        organization_id=org.id,
        contact_id=contact.id,
        recipient="alice@corp.com",
        status="sent",
        channel="email",
        provider_message_id="msg-alice-001",
        subject="Intro",
        body="Intro body",
    )
    db.add(outreach)
    db.commit()

    async with make_client() as client:
        # 1. Alias 1: /api/v1/tracking/inbound-reply with X-Webhook-Secret
        resp1 = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={"from_email": "alice@corp.com", "body": "Let's connect", "in_reply_to": "<msg-alice-001>"},
            headers={"X-Webhook-Secret": "trusted-inbound-secret-789"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "processed"

        # 2. Alias 2: /api/v1/outreach/tracking/inbound-reply with Authorization: Bearer
        resp2 = await client.post(
            "/api/v1/outreach/tracking/inbound-reply",
            json={"from_email": "alice@corp.com", "body": "Following up", "in_reply_to": "<msg-alice-001>"},
            headers={"Authorization": "Bearer trusted-inbound-secret-789"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "processed"


# ── SECTION 2: MULTI-TENANT ISOLATION & SENDER VERIFICATION ──────────────────

@pytest.mark.asyncio
async def test_tenant_collision_prevention_with_shared_prospect(test_db_session, monkeypatch):
    """
    Tenant A and Tenant B both have outreach sent to 'shared.prospect@example.com'.
    - Reply with Tenant A's In-Reply-To header must halt ONLY Tenant A's campaign.
    - Tenant B's outreach and enrollment must remain untouched.
    """
    db: Session = test_db_session
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "secret-test")

    # Tenant A
    org_a = Organization(name="Tenant A Corp", slug="tenant-a-corp")
    db.add(org_a)
    db.commit()
    camp_a = Campaign(organization_id=org_a.id, name="Campaign A", type="sales_outbound", status="active")
    db.add(camp_a)
    db.commit()
    contact_a = Contact(organization_id=org_a.id, first_name="Shared", last_name="Prospect", email="shared.prospect@example.com")
    db.add(contact_a)
    db.commit()
    cc_a = CampaignContact(campaign_id=camp_a.id, contact_id=contact_a.id, enrollment_status="in_progress", current_step=1)
    db.add(cc_a)
    db.commit()
    outreach_a = Outreach(
        organization_id=org_a.id,
        campaign_id=camp_a.id,
        contact_id=contact_a.id,
        campaign_contact_id=cc_a.id,
        recipient="shared.prospect@example.com",
        status="sent",
        channel="email",
        provider_message_id="msg-tenant-a-uuid",
        sent_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
    )
    db.add(outreach_a)
    db.commit()

    # Tenant B (Sent more recently than Tenant A!)
    org_b = Organization(name="Tenant B Corp", slug="tenant-b-corp")
    db.add(org_b)
    db.commit()
    camp_b = Campaign(organization_id=org_b.id, name="Campaign B", type="sales_outbound", status="active")
    db.add(camp_b)
    db.commit()
    contact_b = Contact(organization_id=org_b.id, first_name="Shared", last_name="Prospect", email="shared.prospect@example.com")
    db.add(contact_b)
    db.commit()
    cc_b = CampaignContact(campaign_id=camp_b.id, contact_id=contact_b.id, enrollment_status="in_progress", current_step=1)
    db.add(cc_b)
    db.commit()
    outreach_b = Outreach(
        organization_id=org_b.id,
        campaign_id=camp_b.id,
        contact_id=contact_b.id,
        campaign_contact_id=cc_b.id,
        recipient="shared.prospect@example.com",
        status="sent",
        channel="email",
        provider_message_id="msg-tenant-b-uuid",
        sent_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
    )
    db.add(outreach_b)
    db.commit()

    async with make_client() as client:
        # Prospect replies specifically with In-Reply-To referencing Tenant A's message ID
        reply_payload = {
            "from_email": "shared.prospect@example.com",
            "body": "Replying to Tenant A's email.",
            "in_reply_to": "<msg-tenant-a-uuid>",
        }
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json=reply_payload,
            headers={"X-Webhook-Secret": "secret-test"},
        )
        assert resp.status_code == 200
        assert resp.json()["outreach_id"] == str(outreach_a.id)

        # Verify Tenant A state: halted
        db.refresh(outreach_a)
        db.refresh(contact_a)
        db.refresh(cc_a)
        assert outreach_a.first_replied_at is not None
        assert contact_a.lead_status == "replied"
        assert cc_a.enrollment_status == "replied"

        # Verify Tenant B state: completely UNTOUCHED
        db.refresh(outreach_b)
        db.refresh(contact_b)
        db.refresh(cc_b)
        assert outreach_b.first_replied_at is None
        assert contact_b.lead_status != "replied"
        assert cc_b.enrollment_status == "in_progress"


@pytest.mark.asyncio
async def test_ambiguous_reply_without_headers_fails_closed(test_db_session, monkeypatch):
    """
    If multiple tenants have active outreach to a contact, and the reply lacks
    In-Reply-To headers and lacks a matching destination mailbox, the system must
    FAIL CLOSED (HTTP 422) rather than guessing the most recent global match.
    """
    db: Session = test_db_session
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "secret-test")

    # Tenant 1
    org1 = Organization(name="Tenant 1", slug="tenant-1")
    db.add(org1)
    db.commit()
    c1 = Contact(organization_id=org1.id, first_name="Tenant1", last_name="User", email="ambiguous.contact@target.com")
    db.add(c1)
    db.commit()
    o1 = Outreach(organization_id=org1.id, contact_id=c1.id, recipient="ambiguous.contact@target.com", status="sent", channel="email")
    db.add(o1)

    # Tenant 2
    org2 = Organization(name="Tenant 2", slug="tenant-2")
    db.add(org2)
    db.commit()
    c2 = Contact(organization_id=org2.id, first_name="Tenant2", last_name="User", email="ambiguous.contact@target.com")
    db.add(c2)
    db.commit()
    o2 = Outreach(organization_id=org2.id, contact_id=c2.id, recipient="ambiguous.contact@target.com", status="sent", channel="email")
    db.add(o2)
    db.commit()

    async with make_client() as client:
        # Reply without in_reply_to and without to_email
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={"from_email": "ambiguous.contact@target.com", "body": "Vague response with no headers"},
            headers={"X-Webhook-Secret": "secret-test"},
        )
        assert resp.status_code == 422
        assert "Ambiguous tenant resolution" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unthreaded_reply_routes_via_destination_mailbox(test_db_session, monkeypatch):
    """
    If multiple tenants sent to the contact, but 'to_email' matches Tenant 1's user mailbox,
    the reply routes unambiguously to Tenant 1.
    """
    db: Session = test_db_session
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "secret-test")

    # Tenant 1 with user mailbox
    org1 = Organization(name="Tenant 1 Mailbox", slug="tenant-1-box")
    db.add(org1)
    db.commit()
    user1 = User(
        organization_id=org1.id,
        email="kunal@tenant1.com",
        full_name="Kunal Shah",
        hashed_password="mock-hashed-password",
    )
    db.add(user1)
    c1 = Contact(organization_id=org1.id, first_name="Target", last_name="User", email="shared@target.com")
    db.add(c1)
    db.commit()
    o1 = Outreach(organization_id=org1.id, contact_id=c1.id, recipient="shared@target.com", status="sent", channel="email")
    db.add(o1)

    # Tenant 2
    org2 = Organization(name="Tenant 2 Mailbox", slug="tenant-2-box")
    db.add(org2)
    db.commit()
    c2 = Contact(organization_id=org2.id, first_name="Target", last_name="User", email="shared@target.com")
    db.add(c2)
    db.commit()
    o2 = Outreach(organization_id=org2.id, contact_id=c2.id, recipient="shared@target.com", status="sent", channel="email")
    db.add(o2)
    db.commit()

    async with make_client() as client:
        # Reply with to_email: kunal@tenant1.com
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={
                "from_email": "shared@target.com",
                "to_email": "kunal@tenant1.com",
                "body": "Hi Kunal, let's schedule a meeting.",
            },
            headers={"X-Webhook-Secret": "secret-test"},
        )
        assert resp.status_code == 200
        assert resp.json()["outreach_id"] == str(o1.id)

        db.refresh(o1)
        db.refresh(o2)
        assert o1.first_replied_at is not None
        assert o2.first_replied_at is None


@pytest.mark.asyncio
async def test_mismatched_sender_rejected(test_db_session, monkeypatch):
    """If in_reply_to references an outreach, but from_email does not match recipient, reject."""
    db: Session = test_db_session
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "secret-test")

    org = Organization(name="Sender Guard Org", slug="sender-guard-org")
    db.add(org)
    db.commit()
    c = Contact(organization_id=org.id, first_name="Real", last_name="Recipient", email="real.recipient@example.com")
    db.add(c)
    db.commit()
    o = Outreach(
        organization_id=org.id,
        contact_id=c.id,
        recipient="real.recipient@example.com",
        status="sent",
        channel="email",
        provider_message_id="msg-real-123",
    )
    db.add(o)
    db.commit()

    async with make_client() as client:
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json={
                "from_email": "impostor@attacker.com",
                "in_reply_to": "<msg-real-123>",
                "body": "Spoofed reply",
            },
            headers={"X-Webhook-Secret": "secret-test"},
        )
        assert resp.status_code == 400
        assert "does not match original outreach recipient" in resp.json()["detail"]


# ── SECTION 3: AWS SNS SIGNATURE VERIFICATION ────────────────────────────────

@pytest.mark.asyncio
async def test_untrusted_direct_json_rejected_when_signature_required(test_db_session, monkeypatch):
    """Raw unverified SES JSON without SNS envelope is rejected with 400 when signature verification is enabled."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", True)
    async with make_client() as client:
        raw_payload = {"eventType": "Delivery", "mail": {"messageId": "raw-123"}}
        resp = await client.post("/api/v1/outreach/tracking/ses-webhook", json=raw_payload)
        assert resp.status_code == 400
        assert "missing required AWS SNS envelope" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_untrusted_cert_url_rejected(test_db_session, monkeypatch):
    """SNS messages pointing to attacker cert URLs (non-AWS domain, non-HTTPS, or non-.pem) are rejected."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", True)
    async with make_client() as client:
        # 1. Attacker domain
        bad_envelope_1 = {
            "Type": "Notification",
            "MessageId": "msg-bad-1",
            "TopicArn": "arn:aws:sns:us-east-2:123456789012:Topic",
            "Message": "{}",
            "Timestamp": "2026-10-16T12:00:00Z",
            "SignatureVersion": "2",
            "Signature": "c2lnbmF0dXJl",
            "SigningCertURL": "https://evil-attacker.com/cert.pem",
        }
        resp1 = await client.post("/api/v1/tracking/ses-webhook", json=bad_envelope_1)
        assert resp1.status_code == 400
        assert "Untrusted certificate URL" in resp1.json()["detail"]

        # 2. HTTP (insecure)
        bad_envelope_2 = dict(bad_envelope_1)
        bad_envelope_2["SigningCertURL"] = "http://sns.us-east-2.amazonaws.com/cert.pem"
        resp2 = await client.post("/api/v1/tracking/ses-webhook", json=bad_envelope_2)
        assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_tampered_signature_rejected(test_db_session, monkeypatch):
    """SNS messages with tampered signatures or tampered body are rejected with 400."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", True)
    key, cert_pem, cert_url = generate_test_sns_key_and_cert()

    # Generate valid signature
    payload = create_signed_sns_notification(
        key=key,
        cert_url=cert_url,
        message_dict={"eventType": "Delivery", "mail": {"messageId": "msg-legit-1"}},
    )

    # Tamper with message after signing
    payload["Message"] = json.dumps({"eventType": "Bounce", "mail": {"messageId": "msg-legit-1"}})

    async with make_client() as client:
        resp = await client.post("/api/v1/tracking/ses-webhook", json=payload)
        assert resp.status_code == 400
        assert "Invalid SNS signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_valid_cryptographic_sns_signature_accepted(test_db_session, monkeypatch):
    """Cryptographically valid SNS notification (signed with SHA256withRSA) is verified and processed."""
    db: Session = test_db_session
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", True)
    key, cert_pem, cert_url = generate_test_sns_key_and_cert()

    # Seed outreach
    org = Organization(name="Crypto Org", slug="crypto-org")
    db.add(org)
    db.commit()
    contact = Contact(organization_id=org.id, first_name="Crypto", last_name="Lead", email="crypto.lead@test.com")
    db.add(contact)
    db.commit()
    outreach = Outreach(
        organization_id=org.id,
        contact_id=contact.id,
        recipient="crypto.lead@test.com",
        status="sent",
        channel="email",
        provider_message_id="ses-crypto-msg-999",
    )
    db.add(outreach)
    db.commit()

    # Sign Delivery notification
    sns_payload = create_signed_sns_notification(
        key=key,
        cert_url=cert_url,
        message_dict={
            "eventType": "Delivery",
            "mail": {
                "messageId": "ses-crypto-msg-999",
                "destination": ["crypto.lead@test.com"],
            },
            "delivery": {"timestamp": "2026-10-16T15:00:00Z"},
        },
    )

    async with make_client() as client:
        resp = await client.post("/api/v1/outreach/tracking/ses-webhook", json=sns_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"

        db.refresh(outreach)
        assert outreach.first_delivered_at is not None


@pytest.mark.asyncio
async def test_safe_subscription_confirmation_validation(test_db_session, monkeypatch):
    """
    SubscriptionConfirmation must be cryptographically signed, and SubscribeURL must point
    strictly to an official AWS SNS endpoint over HTTPS.
    """
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", True)
    key, cert_pem, cert_url = generate_test_sns_key_and_cert()

    # 1. Sign a valid SubscriptionConfirmation message
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    sub_payload = {
        "Type": "SubscriptionConfirmation",
        "MessageId": "sub-confirm-123",
        "TopicArn": "arn:aws:sns:us-east-2:123456789012:MyTopic",
        "Message": "You have chosen to subscribe to the topic.",
        "SubscribeURL": "https://sns.us-east-2.amazonaws.com/?Action=ConfirmSubscription&TopicArn=...&Token=...",
        "Token": "2336412f37fb687f5d51e6e241d09c805a394a34b6f1ae5",
        "Timestamp": timestamp,
        "SignatureVersion": "2",
        "SigningCertURL": cert_url,
    }

    # Reconstruct canonical string for SubscriptionConfirmation
    keys = ["Message", "MessageId", "SubscribeURL", "Timestamp", "TopicArn", "Token", "Type"]
    signable = "".join(f"{k}\n{sub_payload[k]}\n" for k in keys)
    sig = key.sign(signable.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    sub_payload["Signature"] = base64.b64encode(sig).decode("ascii")

    async with make_client() as client:
        resp = await client.post("/api/v1/tracking/ses-webhook", json=sub_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("subscription_confirmed", "subscription_confirmation_verified")


# ── SECTION 4: IDEMPOTENCY & EVENT DEDUPLICATION ─────────────────────────────

@pytest.mark.asyncio
async def test_idempotent_event_deduplication_on_repeated_webhooks(test_db_session, monkeypatch):
    """
    Repeated webhooks with the same message identifier must NOT insert duplicate OutreachEvent rows,
    and must NOT mutate or overwrite initial timestamps.
    """
    db: Session = test_db_session
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)

    org = Organization(name="Idempotency Org", slug="idempotency-org")
    db.add(org)
    db.commit()
    contact = Contact(organization_id=org.id, first_name="Dedup", last_name="Lead", email="dedup.lead@test.com")
    db.add(contact)
    db.commit()
    outreach = Outreach(
        organization_id=org.id,
        contact_id=contact.id,
        recipient="dedup.lead@test.com",
        status="sent",
        channel="email",
        provider_message_id="msg-dedup-100",
    )
    db.add(outreach)
    db.commit()

    async with make_client() as client:
        # Delivery payload
        deliv_payload = {
            "Type": "Notification",
            "MessageId": "sns-deliv-repeat-uuid",
            "Message": json.dumps({
                "eventType": "Delivery",
                "mail": {"messageId": "msg-dedup-100", "destination": ["dedup.lead@test.com"]},
                "delivery": {"timestamp": "2026-10-16T12:00:00Z"},
            }),
        }

        # 1. First invocation: records delivery
        resp1 = await client.post("/api/v1/tracking/ses-webhook", json=deliv_payload)
        assert resp1.status_code == 200

        db.refresh(outreach)
        initial_delivered_at = outreach.first_delivered_at
        assert initial_delivered_at is not None

        events_1 = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach.id).all()
        assert len(events_1) == 1
        assert events_1[0].event_type == "delivered"

        # 2. Second invocation: exact duplicate retry from AWS SNS
        resp2 = await client.post("/api/v1/tracking/ses-webhook", json=deliv_payload)
        assert resp2.status_code == 200

        db.refresh(outreach)
        # Timestamp must be identical
        assert outreach.first_delivered_at == initial_delivered_at

        # Event count must still be EXACTLY 1 (no duplicate row)
        events_2 = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach.id).all()
        assert len(events_2) == 1

        # 3. Third invocation: open notification
        open_payload = {
            "Type": "Notification",
            "MessageId": "sns-open-repeat-uuid",
            "Message": json.dumps({
                "eventType": "Open",
                "mail": {"messageId": "msg-dedup-100"},
                "open": {"timestamp": "2026-10-16T12:05:00Z"},
            }),
        }
        await client.post("/api/v1/tracking/ses-webhook", json=open_payload)
        db.refresh(outreach)
        assert outreach.first_opened_at is not None
        events_3 = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach.id).all()
        assert len(events_3) == 2  # 1 delivered + 1 opened

        # 4. Fourth invocation: duplicate open retry
        await client.post("/api/v1/tracking/ses-webhook", json=open_payload)
        events_4 = db.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach.id).all()
        assert len(events_4) == 2  # Still 2 events!
