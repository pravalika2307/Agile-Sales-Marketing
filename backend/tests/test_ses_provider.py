"""Unit and integration tests for AWS SES Email Provider and Outreach integration."""
import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.outreach import Outreach, OutreachEvent
from app.services.outreach.base import EmailMessage
from app.services.outreach.providers import (
    SesEmailProvider,
    get_email_provider,
)
from app.services.outreach.service import (
    AlreadySentError,
    CurrentlySendingError,
    OutreachNotFoundError,
    send_outreach,
)


# ── In-Memory SQLite Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Create fresh isolated in-memory SQLite database session."""
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
            "full_name": "SES Outreach Tester",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def setup_test_outreach(
    client: AsyncClient,
    headers: dict,
    email: str = "lead@example.com",
    body: str = "Hello from Agile Sales & Marketing SES!",
    subject: str = "Enterprise Outreach",
    channel: str = "email",
) -> dict:
    """Helper to create campaign, contact, enrollment, and draft outreach."""
    camp = (await client.post(
        "/api/v1/campaigns",
        json={"name": "Outbound SES Sequence", "type": "sales_outbound"},
        headers=headers,
    )).json()

    cont = (await client.post(
        "/api/v1/contacts",
        json={"email": email, "first_name": "Alice", "last_name": "Smith"},
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


# ── Unit Tests: SesEmailProvider ──────────────────────────────────────────────

def test_ses_provider_initialization_and_properties():
    """Verify provider naming, configuration check, and credential safety."""
    provider = SesEmailProvider(
        region_name="us-east-2",
        from_email="outreach@agile.com",
        from_name="Agile Sales",
        configuration_set="agile-config-set",
    )
    assert provider.provider_name == "aws_ses"
    assert provider.is_configured is True

    # Ensure repr or string does not expose AWS credentials
    repr_str = repr(provider)
    assert "secret" not in repr_str.lower()


def test_ses_provider_unconfigured_safeguard():
    """Verify provider safely returns failure when unconfigured without raising."""
    provider = SesEmailProvider(
        region_name="",
        from_email="",
    )
    assert provider.is_configured is False
    msg = EmailMessage(to_email="test@example.com", subject="Test", body="Body")
    result = provider.send(msg)
    assert result.success is False
    assert result.provider == "aws_ses"
    assert "not configured" in result.error_message


def test_ses_provider_send_simple_success():
    """Verify successful delivery via mocked boto3 sesv2 client."""
    mock_boto_client = MagicMock()
    mock_boto_client.send_email.return_value = {
        "MessageId": "ses-msg-12345-abcdef",
        "ResponseMetadata": {"HTTPStatusCode": 200},
    }

    provider = SesEmailProvider(
        region_name="us-east-2",
        from_email="sales@company.com",
        from_name="Sales Team",
        configuration_set="main-config-set",
        client=mock_boto_client,
    )

    msg = EmailMessage(
        to_email="recipient@example.com",
        subject="Product Demo",
        body="Let's schedule a 15-minute call.",
        metadata={
            "outreach_id": "outreach-uuid-1",
            "campaign_id": "campaign-uuid-2",
            "organization_id": "org-uuid-3",
        },
    )

    result = provider.send(msg)

    assert result.success is True
    assert result.provider == "aws_ses"
    assert result.provider_message_id == "ses-msg-12345-abcdef"
    assert result.error_message is None

    mock_boto_client.send_email.assert_called_once()
    call_kwargs = mock_boto_client.send_email.call_args[1]

    assert call_kwargs["FromEmailAddress"] == "sales@company.com"
    assert call_kwargs["Destination"]["ToAddresses"] == ["recipient@example.com"]
    assert call_kwargs["ConfigurationSetName"] == "main-config-set"
    assert call_kwargs["Content"]["Simple"]["Subject"]["Data"] == "Product Demo"
    assert call_kwargs["Content"]["Simple"]["Body"]["Text"]["Data"] == "Let's schedule a 15-minute call."

    # Check tags passed correctly
    tag_names = [t["Name"] for t in call_kwargs["EmailTags"]]
    assert "outreach_id" in tag_names
    assert "campaign_id" in tag_names
    assert "organization_id" in tag_names


def test_ses_provider_send_html_and_attachments():
    """Verify raw MIME construction when HTML, attachments, or inline images are provided."""
    mock_boto_client = MagicMock()
    mock_boto_client.send_email.return_value = {"MessageId": "ses-mime-9988"}

    provider = SesEmailProvider(
        region_name="us-east-2",
        from_email="sales@company.com",
        client=mock_boto_client,
    )

    msg = EmailMessage(
        to_email="client@example.com",
        subject="Quarterly Overview",
        body="Please see attached overview.",
        metadata={
            "html_body": "<h1>Quarterly Overview</h1><p>Details below.</p>",
            "reply_to": "replies@company.com",
            "cc_emails": ["cc@company.com"],
            "attachments": [
                {
                    "filename": "overview.pdf",
                    "content": b"%PDF-1.4 mock pdf content",
                    "mime_type": "application/pdf",
                }
            ],
        },
    )

    result = provider.send(msg)

    assert result.success is True
    assert result.provider_message_id == "ses-mime-9988"

    call_kwargs = mock_boto_client.send_email.call_args[1]
    assert "Raw" in call_kwargs["Content"]
    assert b"Quarterly Overview" in call_kwargs["Content"]["Raw"]["Data"]
    assert call_kwargs["ReplyToAddresses"] == ["replies@company.com"]


def test_ses_provider_client_error_handling():
    """Verify ClientError from AWS SES is captured and cleanly returned."""
    mock_boto_client = MagicMock()
    error_response = {
        "Error": {
            "Code": "MessageRejected",
            "Message": "Email address is not verified in sandbox.",
        }
    }
    mock_boto_client.send_email.side_effect = ClientError(error_response, "SendEmail")

    provider = SesEmailProvider(
        region_name="us-east-2",
        from_email="sales@company.com",
        client=mock_boto_client,
    )

    msg = EmailMessage(to_email="unverified@example.com", subject="Test", body="Hello")
    result = provider.send(msg)

    assert result.success is False
    assert result.provider == "aws_ses"
    assert result.provider_message_id == ""
    assert "MessageRejected" in result.error_message
    assert "Email address is not verified in sandbox" in result.error_message


def test_ses_provider_unexpected_exception_handling():
    """Verify unexpected connection exceptions do not crash and are safely reported."""
    mock_boto_client = MagicMock()
    mock_boto_client.send_email.side_effect = ConnectionResetError("Connection lost to AWS")

    provider = SesEmailProvider(
        region_name="us-east-2",
        from_email="sales@company.com",
        client=mock_boto_client,
    )

    msg = EmailMessage(to_email="user@example.com", subject="Test", body="Hello")
    result = provider.send(msg)

    assert result.success is False
    assert result.provider == "aws_ses"
    assert "ConnectionResetError" in result.error_message


# ── Provider Factory Resolution Tests ─────────────────────────────────────────

def test_get_email_provider_ses_resolution():
    """Verify get_email_provider resolves SesEmailProvider correctly."""
    # Explicit request
    provider = get_email_provider("ses")
    assert isinstance(provider, SesEmailProvider)
    assert provider.provider_name == "aws_ses"

    provider_aws = get_email_provider("aws_ses")
    assert isinstance(provider_aws, SesEmailProvider)

    # Resolution via settings
    with patch.object(settings, "EMAIL_PROVIDER_TYPE", "ses"):
        prov = get_email_provider()
        assert isinstance(prov, SesEmailProvider)


# ── Integration Tests: send_outreach Lifecycle with SES ───────────────────────

@pytest.mark.asyncio
async def test_send_outreach_success_with_ses(test_db_session):
    """Verify end-to-end outreach send with SesEmailProvider records sent status and message ID."""
    async with make_client() as client:
        token = await register_tenant(client, "org_ses@example.com", "SES Enterprise Org")
        headers = {"Authorization": f"Bearer {token}"}

        setup = await setup_test_outreach(client, headers)
        outreach_id = uuid.UUID(setup["outreach_id"])

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "ses-outreach-msg-777"}

        ses_provider = SesEmailProvider(
            region_name="us-east-2",
            from_email="outreach@ses-org.com",
            client=mock_client,
        )

        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == outreach_id).first()
        org_id = db_outreach.organization_id

        sent_outreach = send_outreach(
            test_db_session,
            org_id,
            outreach_id,
            provider=ses_provider,
        )

        assert sent_outreach.status == "sent"
        assert sent_outreach.provider == "aws_ses"
        assert sent_outreach.provider_message_id == "ses-outreach-msg-777"
        assert sent_outreach.sent_at is not None

        # Verify audit events: 'created', 'sending', 'sent'
        events = test_db_session.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach_id).all()
        event_types = [e.event_type for e in events]
        assert "created" in event_types
        assert "sending" in event_types
        assert "sent" in event_types


@pytest.mark.asyncio
async def test_send_outreach_duplicate_protection(test_db_session):
    """Verify duplicate send protection prevents double-sending an outreach with SES."""
    async with make_client() as client:
        token = await register_tenant(client, "org_dup@example.com", "Dup Protection Org")
        headers = {"Authorization": f"Bearer {token}"}

        setup = await setup_test_outreach(client, headers)
        outreach_id = uuid.UUID(setup["outreach_id"])

        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "ses-msg-first"}

        ses_provider = SesEmailProvider(
            region_name="us-east-2",
            from_email="outreach@dup-org.com",
            client=mock_client,
        )

        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == outreach_id).first()
        org_id = db_outreach.organization_id

        # First send succeeds
        send_outreach(test_db_session, org_id, outreach_id, provider=ses_provider)

        # Second send attempt raises AlreadySentError
        with pytest.raises(AlreadySentError):
            send_outreach(test_db_session, org_id, outreach_id, provider=ses_provider)


@pytest.mark.asyncio
async def test_send_outreach_tenant_isolation(test_db_session):
    """Verify cross-tenant outreach send is rejected."""
    async with make_client() as client:
        token_a = await register_tenant(client, "org_a@example.com", "Tenant A")
        token_b = await register_tenant(client, "org_b@example.com", "Tenant B")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        setup_a = await setup_test_outreach(client, headers_a)
        outreach_a_id = uuid.UUID(setup_a["outreach_id"])

        # Try to send Tenant A's outreach using Tenant B's credentials via API
        resp = await client.post(
            f"/api/v1/outreach/{outreach_a_id}/send",
            headers=headers_b,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_send_outreach_provider_failure_handling(test_db_session):
    """Verify provider delivery failure transitions outreach to 'failed' with audit trail."""
    async with make_client() as client:
        token = await register_tenant(client, "org_fail@example.com", "Fail Org")
        headers = {"Authorization": f"Bearer {token}"}

        setup = await setup_test_outreach(client, headers)
        outreach_id = uuid.UUID(setup["outreach_id"])

        mock_client = MagicMock()
        mock_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "AccountSendingPausedException", "Message": "Account sending paused"}},
            "SendEmail"
        )

        ses_provider = SesEmailProvider(
            region_name="us-east-2",
            from_email="outreach@fail.com",
            client=mock_client,
        )

        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == outreach_id).first()
        org_id = db_outreach.organization_id

        failed_outreach = send_outreach(
            test_db_session,
            org_id,
            outreach_id,
            provider=ses_provider,
            raise_on_failure=False,
        )

        assert failed_outreach.status == "failed"
        assert failed_outreach.provider == "aws_ses"
        assert failed_outreach.provider_message_id is None

        # Verify 'failed' event recorded
        events = test_db_session.query(OutreachEvent).filter(OutreachEvent.outreach_id == outreach_id).all()
        event_types = [e.event_type for e in events]
        assert "failed" in event_types


# ── Integration Tests: SES / SNS Webhook Processing ───────────────────────────

@pytest.mark.asyncio
async def test_ses_webhook_delivery_event(test_db_session, monkeypatch):
    """Verify SES Delivery event webhook updates first_delivered_at and records event."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)
    async with make_client() as client:
        token = await register_tenant(client, "org_hook@example.com", "Webhook Org")
        headers = {"Authorization": f"Bearer {token}"}

        setup = await setup_test_outreach(client, headers)
        outreach_id = uuid.UUID(setup["outreach_id"])

        # Manually set provider_message_id and status to sent
        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == outreach_id).first()
        db_outreach.status = "sent"
        db_outreach.provider = "aws_ses"
        db_outreach.provider_message_id = "ses-hook-msg-999"
        test_db_session.commit()

        # Send direct SES event payload
        ses_payload = {
            "eventType": "Delivery",
            "mail": {
                "messageId": "ses-hook-msg-999",
                "timestamp": "2026-10-07T16:00:00Z",
            },
            "delivery": {
                "timestamp": "2026-10-07T16:00:02Z",
                "recipients": ["lead@example.com"],
            },
        }

        resp = await client.post("/api/v1/outreach/tracking/ses-webhook", json=ses_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"
        assert resp.json()["event_type"] == "Delivery"

        test_db_session.refresh(db_outreach)
        assert db_outreach.first_delivered_at is not None


@pytest.mark.asyncio
async def test_ses_webhook_sns_wrapped_open_and_click(test_db_session, monkeypatch):
    """Verify SNS envelope wrapped SES events update opened and clicked tracking."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)
    async with make_client() as client:
        token = await register_tenant(client, "org_sns@example.com", "SNS Wrapped Org")
        headers = {"Authorization": f"Bearer {token}"}

        setup = await setup_test_outreach(client, headers)
        outreach_id = uuid.UUID(setup["outreach_id"])

        db_outreach = test_db_session.query(Outreach).filter(Outreach.id == outreach_id).first()
        db_outreach.status = "sent"
        db_outreach.provider = "aws_ses"
        db_outreach.provider_message_id = "ses-sns-msg-888"
        test_db_session.commit()

        # 1. Test Open event wrapped in SNS envelope
        inner_open = {
            "eventType": "Open",
            "mail": {"messageId": "ses-sns-msg-888"},
            "open": {"timestamp": "2026-10-07T16:05:00Z", "ipAddress": "1.2.3.4"},
        }
        sns_envelope_open = {
            "Type": "Notification",
            "MessageId": "sns-notif-1",
            "Message": json.dumps(inner_open),
        }

        resp_open = await client.post("/api/v1/outreach/tracking/ses-webhook", json=sns_envelope_open)
        assert resp_open.status_code == 200
        assert resp_open.json()["status"] == "processed"

        test_db_session.refresh(db_outreach)
        assert db_outreach.first_opened_at is not None

        # 2. Test Click event wrapped in SNS envelope
        inner_click = {
            "eventType": "Click",
            "mail": {"messageId": "ses-sns-msg-888"},
            "click": {"timestamp": "2026-10-07T16:06:00Z", "link": "https://example.com/demo"},
        }
        sns_envelope_click = {
            "Type": "Notification",
            "MessageId": "sns-notif-2",
            "Message": json.dumps(inner_click),
        }

        resp_click = await client.post("/api/v1/outreach/tracking/ses-webhook", json=sns_envelope_click)
        assert resp_click.status_code == 200
        assert resp_click.json()["status"] == "processed"

        test_db_session.refresh(db_outreach)
        assert db_outreach.first_clicked_at is not None


@pytest.mark.asyncio
async def test_ses_webhook_unmatched_and_subscription_confirmation(test_db_session, monkeypatch):
    """Verify subscription confirmation and unknown message IDs are handled gracefully."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)
    async with make_client() as client:
        # Subscription confirmation
        resp_sub = await client.post(
            "/api/v1/outreach/tracking/ses-webhook",
            json={"Type": "SubscriptionConfirmation", "SubscribeURL": "https://sns.us-east-2.amazonaws.com"},
        )
        assert resp_sub.status_code == 200
        assert resp_sub.json()["status"] in ("subscription_confirmed", "subscription_confirmation_verified")

        # Unknown message ID
        resp_unknown = await client.post(
            "/api/v1/outreach/tracking/ses-webhook",
            json={"eventType": "Delivery", "mail": {"messageId": "unknown-message-id-999"}},
        )
        assert resp_unknown.status_code == 200
        assert resp_unknown.json()["status"] == "ignored"
        assert resp_unknown.json()["reason"] == "outreach_not_found"
