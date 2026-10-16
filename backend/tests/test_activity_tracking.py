"""Tests for Channel-Specific Activity Tracking & Unified Activities (Stage B)."""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from contextlib import asynccontextmanager
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, get_db
from app.main import app
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.contact_list import ContactList, ContactListMember
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.services.analytics_service import get_unified_activities
from app.services.outreach import service as outreach_service


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session."""
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
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201
    return resp.json()["tokens"]["access_token"]


def test_outreach_filtering_by_lead_and_list(db_session):
    """Verify Outreach can be filtered by lead_id and list_id with tenant scoping."""
    org1 = Organization(name="Org 1", slug="org-1")
    org2 = Organization(name="Org 2", slug="org-2")
    db_session.add_all([org1, org2])
    db_session.commit()

    # Create Lead and Contact in Org 1
    contact1 = Contact(
        organization_id=org1.id,
        email="lead1@example.com",
        first_name="Alice",
        last_name="Smith",
    )
    db_session.add(contact1)
    db_session.flush()

    lead1 = Lead(
        organization_id=org1.id,
        email="lead1@example.com",
        first_name="Alice",
        last_name="Smith",
        company_name="Acme Corp",
        contact_id=contact1.id,
    )
    lead2 = Lead(
        organization_id=org1.id,
        email="lead2@example.com",
        first_name="Bob",
        last_name="Jones",
        company_name="Beta LLC",
    )
    # Lead in Org 2 (cross-tenant test)
    lead_org2 = Lead(
        organization_id=org2.id,
        email="lead_org2@example.com",
        first_name="Eve",
        last_name="Cross",
        company_name="Cross Org",
    )
    db_session.add_all([lead1, lead2, lead_org2])
    db_session.commit()

    # Create Contact List in Org 1 containing lead1
    cl = ContactList(organization_id=org1.id, name="Target Leads", type="static")
    db_session.add(cl)
    db_session.flush()

    m1 = ContactListMember(contact_list_id=cl.id, lead_id=lead1.id, contact_id=contact1.id)
    db_session.add(m1)
    db_session.commit()

    # Create Outreach for lead1 and lead2
    outreach1 = Outreach(
        organization_id=org1.id,
        contact_id=contact1.id,
        recipient="lead1@example.com",
        channel="email",
        status="sent",
        subject="Intro email",
        sent_at=datetime.now(timezone.utc),
    )
    outreach2 = Outreach(
        organization_id=org1.id,
        recipient="lead2@example.com",
        channel="email",
        status="draft",
        subject="Draft email",
    )
    # Outreach in Org 2
    outreach_org2 = Outreach(
        organization_id=org2.id,
        recipient="lead_org2@example.com",
        channel="email",
        status="sent",
        subject="Cross tenant email",
    )
    db_session.add_all([outreach1, outreach2, outreach_org2])
    db_session.commit()

    # 1. Filter by lead1
    res_lead1, total_lead1 = outreach_service.list_outreach(db_session, org1.id, lead_id=lead1.id)
    assert total_lead1 == 1
    assert res_lead1[0].id == outreach1.id

    # 2. Filter by lead2
    res_lead2, total_lead2 = outreach_service.list_outreach(db_session, org1.id, lead_id=lead2.id)
    assert total_lead2 == 1
    assert res_lead2[0].id == outreach2.id

    # 3. Filter by list
    res_list, total_list = outreach_service.list_outreach(db_session, org1.id, list_id=cl.id)
    assert total_list == 1
    assert res_list[0].id == outreach1.id

    # 4. Cross-tenant isolation: querying lead_org2 from org1 returns 0
    res_cross, total_cross = outreach_service.list_outreach(db_session, org1.id, lead_id=lead_org2.id)
    assert total_cross == 0


def test_voice_call_records_filtering(db_session):
    """Verify call records can be safely filtered by lead_id, contact_id, and campaign_id."""
    org = Organization(name="Voice Org", slug="voice-org")
    db_session.add(org)
    db_session.commit()

    camp = Campaign(organization_id=org.id, name="Q4 Voice Outbound", type="sales_outbound", status="active")
    db_session.add(camp)
    db_session.flush()

    contact = Contact(organization_id=org.id, email="contact@example.com", first_name="Jane", last_name="Doe")
    db_session.add(contact)
    db_session.flush()

    lead = Lead(organization_id=org.id, company_name="Doe Industries", contact_id=contact.id)
    db_session.add(lead)
    db_session.flush()

    cr1 = CallRecord(
        organization_id=org.id,
        call_id="call_001",
        agent_id="agent_alpha",
        direction="outbound",
        call_status="ended",
        call_outcome="QUALIFIED",
        duration_ms=45000,
        lead_id=lead.id,
        contact_id=contact.id,
        campaign_id=camp.id,
    )
    cr2 = CallRecord(
        organization_id=org.id,
        call_id="call_002",
        agent_id="agent_alpha",
        direction="inbound",
        call_status="ended",
        call_outcome="INTERESTED",
        duration_ms=30000,
    )
    db_session.add_all([cr1, cr2])
    db_session.commit()

    # Query unified activities for this lead
    acts = get_unified_activities(db_session, org.id, lead_id=lead.id, channel="voice")
    assert acts.total == 1
    assert acts.items[0].id == str(cr1.id)
    assert acts.items[0].voice_details.is_connected is True
    assert acts.items[0].voice_details.duration_seconds == 45
    assert acts.items[0].voice_details.call_outcome == "QUALIFIED"


def test_sent_vs_delivered_and_chronological_ordering(db_session):
    """
    STRICT DATA INTEGRITY:
    - sent_at with no first_delivered_at must NOT be reported as delivered.
    - first_delivered_at must report is_delivered=True with accurate timestamp.
    - stream must sort chronologically descending (newest first).
    """
    org = Organization(name="Integrity Org", slug="integrity-org")
    db_session.add(org)
    db_session.commit()

    lead = Lead(organization_id=org.id, company_name="Sample Co", email="prospect@sample.com")
    db_session.add(lead)
    db_session.commit()

    t_now = datetime.now(timezone.utc)
    t_older = t_now - timedelta(hours=2)
    t_oldest = t_now - timedelta(hours=5)

    # 1. Oldest email: sent but NOT delivered
    email_submitted_only = Outreach(
        organization_id=org.id,
        recipient="prospect@sample.com",
        channel="email",
        status="sent",
        subject="Initial outreach",
        sent_at=t_oldest,
        first_delivered_at=None,
    )
    # 2. Middle activity: Voice call connected
    call_connected = CallRecord(
        organization_id=org.id,
        call_id="call_mid",
        agent_id="agent_retell",
        direction="outbound",
        call_status="ended",
        call_outcome="MEETING_REQUESTED",
        duration_ms=62000,
        started_at=t_older,
        lead_id=lead.id,
    )
    # 3. Newest activity: Email delivered and replied
    email_delivered = Outreach(
        organization_id=org.id,
        recipient="prospect@sample.com",
        channel="email",
        status="sent",
        subject="Meeting confirmation",
        sent_at=t_now - timedelta(minutes=30),
        first_delivered_at=t_now - timedelta(minutes=25),
        first_replied_at=t_now - timedelta(minutes=5),
    )

    db_session.add_all([email_submitted_only, call_connected, email_delivered])
    db_session.commit()

    activities = get_unified_activities(db_session, org.id, lead_id=lead.id)
    assert activities.total == 3

    # Check Chronological Ordering (newest first)
    items = activities.items
    assert items[0].id == str(email_delivered.id)
    assert items[1].id == str(call_connected.id)
    assert items[2].id == str(email_submitted_only.id)

    # Check Sent vs. Delivered Invariants
    # 1. Delivered email has is_delivered=True and is_replied=True
    assert items[0].email_details.is_delivered is True
    assert items[0].email_details.is_replied is True
    assert items[0].activity_type == "email_replied"

    # 2. Voice call has verified outcome and is_connected=True
    assert items[1].voice_details.is_connected is True
    assert items[1].voice_details.call_outcome == "MEETING_REQUESTED"
    assert items[1].activity_type == "voice_call_meeting_requested"
    assert items[1].voice_details.duration_seconds == 62

    # 3. Submitted-only email is NEVER inferred as delivered
    assert items[2].email_details.status == "sent"
    assert items[2].email_details.is_delivered is False
    assert items[2].email_details.delivered_at is None
    assert items[2].activity_type == "email_sent"


def test_empty_state_uncontacted_lead(db_session):
    """Verify clean neutral empty state when a lead has no outreach or voice activities."""
    org = Organization(name="Empty State Org", slug="empty-state-org")
    db_session.add(org)
    db_session.commit()

    fresh_lead = Lead(organization_id=org.id, company_name="Brand New Inc", email="fresh@example.com")
    db_session.add(fresh_lead)
    db_session.commit()

    acts = get_unified_activities(db_session, org.id, lead_id=fresh_lead.id)
    assert acts.total == 0
    assert len(acts.items) == 0


@pytest.mark.anyio
async def test_api_analytics_activities_endpoint(db_session):
    """Test GET /api/v1/analytics/activities via HTTP client."""
    async with make_client() as client:
        token = await register_tenant(client, "admin@activitycorp.com", "Activity Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Initial query: zero activities
        res = await client.get("/api/v1/analytics/activities", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["items"] == []
