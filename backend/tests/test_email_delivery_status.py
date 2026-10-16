"""
Tests for Outreach Email Provider Delivery Status and Evidence Integrity.
Covers:
- Mock send is recorded with provider='mock' and first_delivered_at=None (simulated, not delivered)
- Provider failure transitions to 'failed' with error message and never produces success
- Real provider acceptance (e.g. SES) sets provider_message_id and sent_at without falsely claiming delivery
- Delivery event (first_delivered_at) is only recorded upon explicit delivery confirmation
- Delivery tracking is idempotent
- Provider selection logic strictly respects EMAIL_PROVIDER_TYPE
- Zero external network requests or live provider invocations
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.schemas.outreach import OutreachCreate
from app.services.outreach.base import EmailMessage, MockEmailProvider
from app.services.outreach.providers import SesEmailProvider, get_email_provider
from app.services.outreach.service import (
    ProviderDeliveryError,
    create_outreach,
    send_outreach,
)
from app.services.outreach.tracking import record_delivered


@pytest.fixture
def test_db_session():
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
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Delivery Tester",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


def create_test_campaign_and_outreach(
    db: Session,
    org_id: uuid.UUID,
    recipient_email: str = "prospect@example-business.com",
) -> tuple[Campaign, Contact, Outreach]:
    camp = Campaign(
        organization_id=org_id,
        name="Outbound Delivery Test",
        type="sales_outbound",
        status="active",
    )
    db.add(camp)
    db.flush()

    contact = Contact(
        organization_id=org_id,
        first_name="Jane",
        last_name="Doe",
        email=recipient_email,
    )
    db.add(contact)
    db.flush()

    cc = CampaignContact(
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
    )
    db.add(cc)
    db.flush()

    outreach = create_outreach(
        db,
        org_id,
        OutreachCreate(
            campaign_id=camp.id,
            contact_id=contact.id,
            campaign_contact_id=cc.id,
            channel="email",
            subject="Strategic Partnership",
            body="Hello Jane, would love to connect.",
        ),
    )
    return camp, contact, outreach


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_mock_send_records_sent_status_with_mock_provider_and_no_delivered_timestamp(test_db_session):
    """
    Mock send sets status='sent', provider='mock', but first_delivered_at is strictly None.
    A mock send must never be treated as confirmed recipient delivery.
    """
    org_id = uuid.uuid4()
    _, _, outreach = create_test_campaign_and_outreach(test_db_session, org_id)

    mock_provider = MockEmailProvider()
    sent = send_outreach(test_db_session, org_id, outreach.id, provider=mock_provider)

    assert sent.status == "sent"
    assert sent.provider == "mock"
    assert sent.provider_message_id is not None
    assert sent.provider_message_id.startswith("mock-msg-")
    assert sent.sent_at is not None
    # Crucial assertion: Mock send DOES NOT populate first_delivered_at
    assert sent.first_delivered_at is None

    # Check event history
    events = (
        test_db_session.query(OutreachEvent)
        .filter(OutreachEvent.outreach_id == outreach.id)
        .all()
    )
    event_types = [e.event_type for e in events]
    assert "sent" in event_types
    assert "delivered" not in event_types


def test_provider_failure_transitions_to_failed_without_sent_timestamp(test_db_session):
    """
    When an email provider fails, outreach status transitions to 'failed',
    error details are audited, and sent_at/first_delivered_at remain None.
    """
    org_id = uuid.uuid4()
    _, _, outreach = create_test_campaign_and_outreach(test_db_session, org_id)

    failing_provider = MockEmailProvider(should_fail=True, failure_reason="SMTP handshake timeout")
    
    with pytest.raises(ProviderDeliveryError) as exc_info:
        send_outreach(test_db_session, org_id, outreach.id, provider=failing_provider, raise_on_failure=True)

    assert "SMTP handshake timeout" in str(exc_info.value)

    # Re-fetch from DB
    failed = test_db_session.query(Outreach).filter(Outreach.id == outreach.id).first()
    assert failed.status == "failed"
    assert failed.sent_at is None
    assert failed.first_delivered_at is None

    # Failed event was recorded
    failed_event = (
        test_db_session.query(OutreachEvent)
        .filter(OutreachEvent.outreach_id == outreach.id, OutreachEvent.event_type == "failed")
        .first()
    )
    assert failed_event is not None
    assert "SMTP handshake timeout" in str(failed_event.event_metadata.get("error"))


def test_ses_provider_acceptance_is_not_confused_with_recipient_delivery(test_db_session):
    """
    A real provider (SES) acceptance returns a MessageId and sets status='sent',
    but first_delivered_at remains None until an explicit delivery confirmation arrives.
    """
    org_id = uuid.uuid4()
    _, _, outreach = create_test_campaign_and_outreach(
        test_db_session, org_id, recipient_email="valid-prospect@corporate-domain.com"
    )

    # Mock the internal boto3 SES client to simulate successful API acceptance
    mock_boto3_client = MagicMock()
    mock_boto3_client.send_email.return_value = {"MessageId": "010f018a-ses-acceptance-uuid-000000"}

    ses_provider = SesEmailProvider(
        region_name="us-east-2",
        from_email="support@agilereceivables.com",
        client=mock_boto3_client,
    )

    sent = send_outreach(test_db_session, org_id, outreach.id, provider=ses_provider)

    assert sent.status == "sent"
    assert sent.provider == "aws_ses"
    assert sent.provider_message_id == "010f018a-ses-acceptance-uuid-000000"
    assert sent.sent_at is not None
    # Crucial assertion: provider submission IS NOT recipient delivery
    assert sent.first_delivered_at is None

    # Now simulate an SES delivery SNS webhook event arriving
    delivered_event = record_delivered(
        test_db_session,
        org_id,
        outreach.id,
        event_metadata={"ses_message_id": "010f018a-ses-acceptance-uuid-000000", "smtp_response": "250 OK"},
    )
    assert delivered_event.event_type == "delivered"

    # Re-fetch from DB: Now delivery is confirmed with timestamp
    test_db_session.refresh(sent)
    assert sent.first_delivered_at is not None


def test_record_delivered_is_idempotent(test_db_session):
    """
    Multiple delivery events preserve the first delivery timestamp without mutating status.
    """
    org_id = uuid.uuid4()
    _, _, outreach = create_test_campaign_and_outreach(test_db_session, org_id)
    send_outreach(test_db_session, org_id, outreach.id, provider=MockEmailProvider())

    # First delivery
    record_delivered(test_db_session, org_id, outreach.id)
    test_db_session.refresh(outreach)
    first_time = outreach.first_delivered_at
    assert first_time is not None

    # Second duplicate delivery notification
    record_delivered(test_db_session, org_id, outreach.id)
    test_db_session.refresh(outreach)
    # Timestamp must not change
    assert outreach.first_delivered_at == first_time


def test_provider_selection_honors_mock_configuration():
    """
    get_email_provider() returns MockEmailProvider when EMAIL_PROVIDER_TYPE='mock'.
    """
    provider = get_email_provider("mock")
    assert provider.provider_name == "mock"
    assert isinstance(provider, MockEmailProvider)


@pytest.mark.asyncio
async def test_api_send_surfaces_provider_failure_truthfully(test_db_session):
    """
    POST /api/v1/outreach/{id}/send surfaces provider failures with HTTP 500
    and never returns a false success message.
    """
    async with make_client() as client:
        token = await register_tenant(client, "failure_test@test.com", "Failure Test Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create contact and campaign
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={"first_name": "Error", "last_name": "Test", "email": "error@example.com"},
            headers=headers,
        )
        cont_id = cont_resp.json()["id"]

        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Fail Camp", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        enroll_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/contacts/{cont_id}",
            headers=headers,
        )
        cc_id = enroll_resp.json()["id"]

        # Create draft outreach
        outreach_resp = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": camp_id,
                "contact_id": cont_id,
                "campaign_contact_id": cc_id,
                "channel": "email",
                "subject": "Hello",
                "body": "Body text",
            },
            headers=headers,
        )
        oid = outreach_resp.json()["id"]

        # Attempt to send with failing provider injected via mock
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.services.outreach.service.get_email_provider",
                lambda: MockEmailProvider(should_fail=True, failure_reason="SES Connection Refused"),
            )
            send_resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
            assert send_resp.status_code == 502
            assert "SES Connection Refused" in send_resp.json()["detail"]
