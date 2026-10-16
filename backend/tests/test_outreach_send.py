"""Integration & unit tests for Step 10: Real Email Provider & Safe Send Execution."""
import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient, Response as HttpxResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.services.outreach.base import EmailMessage, MockEmailProvider
from app.services.outreach.providers import ResendEmailProvider, get_email_provider
from app.services.outreach.service import (
    AlreadySentError,
    CancelledOutreachError,
    CurrentlySendingError,
    EmptyOutreachBodyError,
    InvalidRecipientEmailError,
    SuppressedRecipientError,
    UnsupportedChannelError,
    retry_outreach,
    send_outreach,
)


# ── SQLite In-Memory Database Fixture ──────────────────────────────────────────

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


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> str:
    """Helper to register a tenant and return access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Step 10 Tester",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def setup_test_outreach(
    client: AsyncClient,
    headers: dict,
    email: str = "recipient@example.com",
    body: str = "Hello from Agile Sales & Marketing!",
    subject: str = "Partnership Proposal",
    channel: str = "email",
) -> dict:
    """Helper to create campaign, contact, enrollment, and draft outreach."""
    camp = (await client.post(
        "/api/v1/campaigns",
        json={"name": "Step 10 Sequence", "type": "sales_outbound"},
        headers=headers,
    )).json()

    cont = (await client.post(
        "/api/v1/contacts",
        json={"email": email, "first_name": "Test", "last_name": "User"},
        headers=headers,
    )).json()

    enr = (await client.post(
        f"/api/v1/campaigns/{camp['id']}/contacts/{cont['id']}",
        json={"enrollment_status": "queued"},
        headers=headers,
    )).json()

    outreach = (await client.post(
        "/api/v1/outreach",
        json={
            "campaign_id": camp["id"],
            "contact_id": cont["id"],
            "campaign_contact_id": enr["id"],
            "channel": channel,
            "subject": subject,
            "body": body,
        },
        headers=headers,
    )).json()

    return {
        "campaign_id": camp["id"],
        "contact_id": cont["id"],
        "campaign_contact_id": enr["id"],
        "outreach_id": outreach["id"],
        "outreach": outreach,
    }


# ── 1. Successful Send Lifecycle (Draft -> Sending -> Sent) ───────────────────

@pytest.mark.asyncio
async def test_send_draft_outreach_full_lifecycle_success(test_db_session):
    """Verify sending a draft outreach transitions draft -> sending -> sent with all metadata."""
    async with make_client() as client:
        token = await register_tenant(client, "send1@example.com", "Send Org 1")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = setup["outreach_id"]

        # Initial status is draft
        assert setup["outreach"]["status"] == "draft"

        # Explicit send call
        resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Metadata verification
        assert data["status"] == "sent"
        assert data["channel"] == "email"
        assert data["provider"] == "mock"
        assert data["provider_message_id"].startswith("mock-msg-")
        assert data["sent_at"] is not None
        assert data["recipient_email"] == "recipient@example.com"
        assert data["outreach_id"] == oid

        # Audit events verification
        events_resp = await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)
        assert events_resp.status_code == 200
        events = events_resp.json()
        event_types = [e["event_type"] for e in events]
        assert event_types == ["created", "sending", "sent"]


# ── 2. Provider Failure Lifecycle (Draft -> Sending -> Failed) ────────────────

@pytest.mark.asyncio
async def test_send_outreach_provider_failure_handling(test_db_session):
    """Verify provider failure transitions outreach to failed and creates failed event without provider_message_id."""
    org_id = uuid.uuid4()
    oid = uuid.uuid4()

    # Direct service test with failing MockEmailProvider
    async with make_client() as client:
        token = await register_tenant(client, "send_fail@example.com", "Fail Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = uuid.UUID(setup["outreach_id"])

        # Fetch org_id from database
        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == oid).first()
        org_id = db_outreach.organization_id

        failing_provider = MockEmailProvider(should_fail=True, failure_reason="Simulated provider outage")
        failed = send_outreach(test_db_session, org_id, oid, provider=failing_provider, raise_on_failure=False)

        assert failed.status == "failed"
        assert failed.provider == "mock"
        assert failed.provider_message_id is None
        assert failed.sent_at is None

        # Verify failed event created
        events = test_db_session.query(OutreachEvent).filter(OutreachEvent.outreach_id == oid).all()
        event_types = [e.event_type for e in events]
        assert event_types == ["created", "sending", "failed"]

        # Verify API returns 502 when executed with real failure via API
        setup2 = await setup_test_outreach(client, headers, email="fail2@example.com")
        oid2 = setup2["outreach_id"]

        with patch("app.services.outreach.service.get_email_provider", return_value=failing_provider):
            api_resp = await client.post(f"/api/v1/outreach/{oid2}/send", headers=headers)
            assert api_resp.status_code == 502
            assert "Email delivery failed" in api_resp.json()["detail"]

            # DB record is nevertheless persisted as failed
            get_resp = await client.get(f"/api/v1/outreach/{oid2}", headers=headers)
            assert get_resp.status_code == 200
            assert get_resp.json()["status"] == "failed"
            assert get_resp.json()["provider_message_id"] is None


# ── 3. Content and Validation Rules ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_rejected_for_empty_body(test_db_session):
    """Empty or whitespace-only email body must be rejected before calling provider."""
    async with make_client() as client:
        token = await register_tenant(client, "empty_body@example.com", "Empty Body Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create outreach with None/empty body
        setup = await setup_test_outreach(client, headers, body="")
        oid = setup["outreach_id"]

        resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert resp.status_code == 400
        assert "body must be present" in resp.json()["detail"].lower()

        # Outreach remains in draft status
        get_resp = await client.get(f"/api/v1/outreach/{oid}", headers=headers)
        assert get_resp.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_send_rejected_for_invalid_recipient_email(test_db_session):
    """Missing or invalid recipient contact email must be rejected."""
    async with make_client() as client:
        token = await register_tenant(client, "inv_email@example.com", "Invalid Email Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = setup["outreach_id"]

        # Directly update contact email to invalid in DB
        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == uuid.UUID(oid)).first()
        db_outreach.contact.email = "not-an-email"
        test_db_session.commit()

        resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert resp.status_code == 400
        assert "no valid non-empty email" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_rejected_for_non_email_channel(test_db_session):
    """Non-email outreach channel must be rejected."""
    async with make_client() as client:
        token = await register_tenant(client, "non_email@example.com", "Non Email Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = uuid.UUID(setup["outreach_id"])

        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == oid).first()
        db_outreach.channel = "sms"
        test_db_session.commit()

        resp = await client.post(f"/api/v1/outreach/{str(oid)}/send", headers=headers)
        assert resp.status_code == 400
        assert "Only 'email' is supported" in resp.json()["detail"]


# ── 4. Idempotency & Duplicate Send Protection ────────────────────────────────

@pytest.mark.asyncio
async def test_already_sent_outreach_cannot_be_resent(test_db_session):
    """An outreach that has already been sent must be rejected on repeated send calls."""
    async with make_client() as client:
        token = await register_tenant(client, "dup_send@example.com", "Duplicate Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = setup["outreach_id"]

        # First send succeeds
        r1 = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["status"] == "sent"

        # Second send must be rejected (409 Conflict)
        r2 = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert r2.status_code == 409
        assert "already been sent" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_sending_outreach_cannot_be_concurrently_sent(test_db_session):
    """An outreach currently in 'sending' state cannot accept another send request."""
    async with make_client() as client:
        token = await register_tenant(client, "concurr@example.com", "Concurrent Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = uuid.UUID(setup["outreach_id"])

        # Manually set to sending
        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == oid).first()
        db_outreach.status = "sending"
        test_db_session.commit()

        resp = await client.post(f"/api/v1/outreach/{str(oid)}/send", headers=headers)
        assert resp.status_code == 409
        assert "currently in the process of sending" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cancelled_outreach_cannot_be_sent(test_db_session):
    """A cancelled outreach cannot be sent."""
    async with make_client() as client:
        token = await register_tenant(client, "cancel_send@example.com", "Cancel Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers)
        oid = setup["outreach_id"]

        # Cancel outreach
        cancel_resp = await client.post(f"/api/v1/outreach/{oid}/cancel", headers=headers)
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # Try to send
        send_resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert send_resp.status_code == 400
        assert "Cannot send a cancelled outreach" in send_resp.json()["detail"]


# ── 5. Multi-Tenant Isolation ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_outreach_send_isolation(test_db_session):
    """Tenant B cannot send Tenant A's outreach message."""
    async with make_client() as client:
        token_a = await register_tenant(client, "tenant_a_sender@example.com", "Tenant A Send")
        token_b = await register_tenant(client, "tenant_b_sender@example.com", "Tenant B Send")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        setup_a = await setup_test_outreach(client, headers_a)
        oid_a = setup_a["outreach_id"]

        # Tenant B tries to send Tenant A's outreach -> 404
        cross_resp = await client.post(f"/api/v1/outreach/{oid_a}/send", headers=headers_b)
        assert cross_resp.status_code == 404
        assert "not found" in cross_resp.json()["detail"].lower()

        # Outreach A remains draft
        get_a = await client.get(f"/api/v1/outreach/{oid_a}", headers=headers_a)
        assert get_a.json()["status"] == "draft"


# ── 6. Resend Provider Unit Tests (Mocked HTTPX, Safe Credentials) ────────────

def test_resend_provider_unconfigured_fails_safely():
    """Unconfigured Resend provider returns failure result without raising or crashing."""
    provider = ResendEmailProvider(api_key=None, from_address=None)
    assert provider.is_configured is False
    assert provider.provider_name == "resend"

    msg = EmailMessage(to_email="lead@example.com", subject="Test", body="Hello")
    result = provider.send(msg)

    assert result.success is False
    assert result.provider == "resend"
    assert result.provider_message_id == ""
    assert "not configured" in (result.error_message or "")


def test_resend_provider_successful_delivery_mocked_httpx():
    """Verify Resend provider formats payload and parses message ID correctly."""
    provider = ResendEmailProvider(
        api_key="re_test_key_12345",
        from_address="sales@acme.com",
        from_name="Acme Sales",
        base_url="https://api.resend.com",
        timeout=5.0,
    )
    assert provider.is_configured is True

    msg = EmailMessage(to_email="lead@example.com", subject="Hello", body="Body content")

    fake_response = HttpxResponse(
        status_code=200,
        json={"id": "resend_msg_abc123"},
        request=MagicMock(),
    )

    with patch("httpx.Client.post", return_value=fake_response) as mock_post:
        result = provider.send(msg)

        assert result.success is True
        assert result.provider == "resend"
        assert result.provider_message_id == "resend_msg_abc123"
        assert result.error_message is None

        # Verify request parameters
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["from"] == "Acme Sales <sales@acme.com>"
        assert call_kwargs["json"]["to"] == ["lead@example.com"]
        assert call_kwargs["json"]["subject"] == "Hello"
        assert call_kwargs["json"]["text"] == "Body content"
        assert call_kwargs["headers"]["Authorization"] == "Bearer re_test_key_12345"


def test_resend_provider_error_handling_mocked_httpx():
    """Verify Resend provider captures API error without exposing credentials."""
    provider = ResendEmailProvider(
        api_key="re_test_key_12345",
        from_address="sales@acme.com",
    )

    msg = EmailMessage(to_email="lead@example.com", subject="Hello", body="Body")

    error_response = HttpxResponse(
        status_code=422,
        json={"statusCode": 422, "message": "The domain is not verified"},
        request=MagicMock(),
    )

    with patch("httpx.Client.post", return_value=error_response):
        result = provider.send(msg)

        assert result.success is False
        assert result.provider == "resend"
        assert result.provider_message_id == ""
        assert "422" in (result.error_message or "")
        assert "domain is not verified" in (result.error_message or "")
        # Ensure API key is NEVER leaked in error message
        assert "re_test_key_12345" not in (result.error_message or "")


def test_get_email_provider_factory():
    """Verify factory returns appropriate provider according to configuration."""
    # When explicitly requested mock
    p_mock = get_email_provider(provider_type="mock")
    assert isinstance(p_mock, MockEmailProvider)

    # When unconfigured in test environment
    p_default = get_email_provider()
    assert isinstance(p_default, MockEmailProvider)


# ── SAF-01: Recipient Opt-Out Suppression & Retry Tests ────────────────────────

def test_send_outreach_contact_opted_out_blocked(test_db_session):
    """SAF-01: Outreach to opted_out contact must be blocked, marked cancelled, and record suppressed event."""
    from app.models.tenant import Organization
    from app.models.campaign import Campaign, CampaignContact

    org = Organization(id=uuid.uuid4(), name="Safety Org", slug="safety-org")
    test_db_session.add(org)
    test_db_session.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="optout@safety.com",
        first_name="Stop",
        last_name="Sending",
        lead_status="opted_out",
    )
    campaign = Campaign(id=uuid.uuid4(), organization_id=org.id, name="Safety Campaign", type="sales_outbound")
    test_db_session.add_all([contact, campaign])
    test_db_session.flush()

    camp_contact = CampaignContact(id=uuid.uuid4(), campaign_id=campaign.id, contact_id=contact.id)
    test_db_session.add(camp_contact)
    test_db_session.flush()

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=camp_contact.id,
        channel="email",
        status="draft",
        subject="Important Announcement",
        body="Body text",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())

    with pytest.raises(SuppressedRecipientError) as exc_info:
        send_outreach(test_db_session, org.id, outreach.id, provider=mock_provider)

    assert "opted out" in str(exc_info.value).lower()
    test_db_session.refresh(outreach)
    assert outreach.status == "cancelled"
    mock_provider.send.assert_not_called()

    # Check OutreachEvent recorded
    events = test_db_session.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach.id).all()
    assert len(events) == 1
    assert events[0].event_type == "cancelled"
    assert "suppressed" in events[0].event_metadata.get("reason", "").lower()


def test_send_outreach_contact_unsubscribed_blocked(test_db_session):
    """SAF-01: Outreach to unsubscribed contact must fail closed."""
    from app.models.tenant import Organization
    from app.models.campaign import Campaign, CampaignContact

    org = Organization(id=uuid.uuid4(), name="Safety Org 2", slug="safety-org-2")
    test_db_session.add(org)
    test_db_session.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="unsub@safety.com",
        first_name="Unsub",
        last_name="User",
        lead_status="unsubscribed",
    )
    campaign = Campaign(id=uuid.uuid4(), organization_id=org.id, name="Campaign 2", type="sales_outbound")
    test_db_session.add_all([contact, campaign])
    test_db_session.flush()

    camp_contact = CampaignContact(id=uuid.uuid4(), campaign_id=campaign.id, contact_id=contact.id)
    test_db_session.add(camp_contact)
    test_db_session.flush()

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=camp_contact.id,
        channel="email",
        status="draft",
        subject="Another Email",
        body="Body text",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())

    with pytest.raises(SuppressedRecipientError):
        send_outreach(test_db_session, org.id, outreach.id, provider=mock_provider)

    test_db_session.refresh(outreach)
    assert outreach.status == "cancelled"
    mock_provider.send.assert_not_called()


def test_send_outreach_associated_lead_opted_out_blocked(test_db_session):
    """SAF-01: If associated Lead is rejected/opted out, outreach must be suppressed."""
    from app.models.tenant import Organization
    from app.models.campaign import Campaign, CampaignContact

    org = Organization(id=uuid.uuid4(), name="Safety Org 3", slug="safety-org-3")
    test_db_session.add(org)
    test_db_session.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="leadoptout@safety.com",
        first_name="Lead",
        last_name="Optout",
        lead_status="contacted",  # contact is active
    )
    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_name="Safety Company",
        email="leadoptout@safety.com",
        first_name="Lead",
        last_name="Optout",
        status="rejected",  # lead record is rejected/suppressed!
    )
    campaign = Campaign(id=uuid.uuid4(), organization_id=org.id, name="Campaign 3", type="sales_outbound")
    test_db_session.add_all([contact, lead, campaign])
    test_db_session.flush()

    camp_contact = CampaignContact(id=uuid.uuid4(), campaign_id=campaign.id, contact_id=contact.id)
    test_db_session.add(camp_contact)
    test_db_session.flush()

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=camp_contact.id,
        channel="email",
        status="draft",
        subject="Lead Test",
        body="Body text",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())

    with pytest.raises(SuppressedRecipientError) as exc_info:
        send_outreach(test_db_session, org.id, outreach.id, provider=mock_provider)

    assert "rejected" in str(exc_info.value).lower()
    test_db_session.refresh(outreach)
    assert outreach.status == "cancelled"
    mock_provider.send.assert_not_called()


def test_retry_outreach_respects_suppression(test_db_session):
    """SAF-01: Retrying a failed outreach must enforce suppression check and block delivery."""
    from app.models.tenant import Organization
    from app.models.campaign import Campaign, CampaignContact

    org = Organization(id=uuid.uuid4(), name="Safety Org Retry", slug="safety-org-retry")
    test_db_session.add(org)
    test_db_session.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="retryoptout@safety.com",
        first_name="Retry",
        last_name="User",
        lead_status="opted_out",  # recipient opted out after initial attempt
    )
    campaign = Campaign(id=uuid.uuid4(), organization_id=org.id, name="Retry Campaign", type="sales_outbound")
    test_db_session.add_all([contact, campaign])
    test_db_session.flush()

    camp_contact = CampaignContact(id=uuid.uuid4(), campaign_id=campaign.id, contact_id=contact.id)
    test_db_session.add(camp_contact)
    test_db_session.flush()

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=camp_contact.id,
        channel="email",
        status="failed",
        subject="Retry Test",
        body="Body text",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())

    with pytest.raises(SuppressedRecipientError):
        retry_outreach(test_db_session, org.id, outreach.id, provider=mock_provider)

    test_db_session.refresh(outreach)
    assert outreach.status == "cancelled"
    mock_provider.send.assert_not_called()


def test_retry_outreach_eligible_recipient_succeeds(test_db_session):
    """SAF-01: Retrying a failed outreach for an eligible recipient succeeds with mocked provider."""
    from app.models.tenant import Organization
    from app.models.campaign import Campaign, CampaignContact

    org = Organization(id=uuid.uuid4(), name="Safety Org Eligible", slug="safety-org-eligible")
    test_db_session.add(org)
    test_db_session.flush()

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="eligible@safety.com",
        first_name="Eligible",
        last_name="User",
        lead_status="active",
    )
    campaign = Campaign(id=uuid.uuid4(), organization_id=org.id, name="Eligible Campaign", type="sales_outbound")
    test_db_session.add_all([contact, campaign])
    test_db_session.flush()

    camp_contact = CampaignContact(id=uuid.uuid4(), campaign_id=campaign.id, contact_id=contact.id)
    test_db_session.add(camp_contact)
    test_db_session.flush()

    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=camp_contact.id,
        channel="email",
        status="failed",
        subject="Retry Test Success",
        body="Body text",
    )
    test_db_session.add(outreach)
    test_db_session.commit()

    mock_provider = MagicMock(wraps=MockEmailProvider())
    result = retry_outreach(test_db_session, org.id, outreach.id, provider=mock_provider)

    assert result.status == "sent"
    assert mock_provider.send.call_count == 1
    test_db_session.refresh(outreach)
    assert outreach.status == "sent"


@pytest.mark.asyncio
async def test_api_send_and_retry_opted_out_returns_400(test_db_session):
    """SAF-01: API endpoints for send and retry return HTTP 400 when recipient is suppressed."""
    async with make_client() as client:
        token = await register_tenant(client, "safetyapi@example.com", "Safety API Org")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_test_outreach(client, headers, email="apioptout@safety.com")
        oid = setup["outreach_id"]
        cid = setup["contact_id"]

        # Mark contact as opted_out via CRM update
        upd = await client.patch(
            f"/api/v1/contacts/{cid}",
            json={"lead_status": "opted_out"},
            headers=headers,
        )
        assert upd.status_code == 200

        # Attempt send -> HTTP 400 Suppressed
        send_resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert send_resp.status_code == 400
        assert "opted out" in send_resp.json()["detail"].lower()

        # Set outreach to failed to test retry endpoint
        outreach_rec = test_db_session.query(Outreach).filter(Outreach.id == uuid.UUID(oid)).first()
        outreach_rec.status = "failed"
        test_db_session.commit()

        # Attempt retry -> HTTP 400 Suppressed
        retry_resp = await client.post(f"/api/v1/outreach/{oid}/retry", headers=headers)
        assert retry_resp.status_code == 400
        assert "opted out" in retry_resp.json()["detail"].lower()

