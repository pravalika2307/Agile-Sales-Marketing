"""Integration tests for Outreach, provider abstraction, lifecycle transitions, and tenant isolation."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.outreach import MockEmailProvider, send_outreach


# ── SQLite Database Fixture ───────────────────────────────────────────────────

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
            "full_name": "Outreach Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def setup_enrolled_contact(client: AsyncClient, headers: dict) -> dict:
    """Helper to set up a campaign, contact, and enrollment."""
    # 1. Create campaign
    camp = (await client.post(
        "/api/v1/campaigns",
        json={"name": "Sales Sequence Q1", "type": "sales_outbound"},
        headers=headers,
    )).json()

    # 2. Create contact
    contact = (await client.post(
        "/api/v1/contacts",
        json={"email": "prospect@example.com", "first_name": "Alex", "last_name": "Rivera"},
        headers=headers,
    )).json()

    # 3. Enroll contact
    enrollment = (await client.post(
        f"/api/v1/campaigns/{camp['id']}/contacts/{contact['id']}",
        json={"enrollment_status": "queued"},
        headers=headers,
    )).json()

    return {
        "campaign_id": camp["id"],
        "contact_id": contact["id"],
        "campaign_contact_id": enrollment["id"],
    }


# ── Outreach Creation & Validation Tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_create_outreach_valid_defaults_to_draft(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin1@outreach.com", "Org Outreach 1")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        resp = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
                "subject": "Introductory Partnership",
                "body": "Hi Alex, wanted to follow up.",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "draft"
        assert data["channel"] == "email"
        assert data["subject"] == "Introductory Partnership"
        assert data["provider"] is None
        assert data["provider_message_id"] is None
        assert data["sent_at"] is None

        # Verify initial 'created' event exists
        events_resp = await client.get(f"/api/v1/outreach/{data['id']}/events", headers=headers)
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert len(events) == 1
        assert events[0]["event_type"] == "created"


@pytest.mark.asyncio
async def test_create_outreach_invalid_references_rejected(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin2@outreach.com", "Org Outreach 2")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)
        fake_uuid = str(uuid.uuid4())

        # Invalid campaign -> 404
        r1 = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": fake_uuid,
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers,
        )
        assert r1.status_code == 404

        # Invalid contact -> 404
        r2 = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": fake_uuid,
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers,
        )
        assert r2.status_code == 404

        # Invalid campaign contact -> 404
        r3 = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": fake_uuid,
                "channel": "email",
            },
            headers=headers,
        )
        assert r3.status_code == 404


@pytest.mark.asyncio
async def test_create_outreach_mismatched_enrollment_rejected(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin3@outreach.com", "Org Outreach 3")
        headers = {"Authorization": f"Bearer {token}"}
        setup1 = await setup_enrolled_contact(client, headers)

        # Create a second contact NOT enrolled in setup1 campaign
        c2 = (await client.post(
            "/api/v1/contacts",
            json={"email": "other@example.com", "first_name": "Other", "last_name": "Person"},
            headers=headers,
        )).json()

        # Attempt to create outreach with campaign_contact_id from setup1 but contact_id of c2 -> 404
        mismatch_resp = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup1["campaign_id"],
                "contact_id": c2["id"],
                "campaign_contact_id": setup1["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers,
        )
        assert mismatch_resp.status_code == 404


# ── Outreach Lifecycle & Transitions ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_outreach_full_lifecycle_draft_to_sent(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin4@outreach.com", "Org Outreach 4")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        # 1. Create draft
        outreach = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
                "subject": "Follow Up",
                "body": "Checking in.",
            },
            headers=headers,
        )).json()
        oid = outreach["id"]
        assert outreach["status"] == "draft"

        # 2. Schedule: draft -> scheduled
        sched_resp = await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)
        assert sched_resp.status_code == 200
        assert sched_resp.json()["status"] == "scheduled"

        # 3. Send: scheduled -> sending -> sent
        send_resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert send_resp.status_code == 200
        sent_data = send_resp.json()
        assert sent_data["status"] == "sent"
        assert sent_data["provider"] == "mock"
        assert sent_data["provider_message_id"].startswith("mock-msg-")
        assert sent_data["sent_at"] is not None

        # Verify event sequence: created, scheduled, sending, sent
        events_resp = await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)
        assert events_resp.status_code == 200
        types = [e["event_type"] for e in events_resp.json()]
        assert types == ["created", "scheduled", "sending", "sent"]

        # Sent is terminal: cannot reschedule or cancel
        re_sched = await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)
        assert re_sched.status_code == 400

        cancel_sent = await client.post(f"/api/v1/outreach/{oid}/cancel", headers=headers)
        assert cancel_sent.status_code == 400


@pytest.mark.asyncio
async def test_outreach_cancel_from_draft_and_scheduled(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin5@outreach.com", "Org Outreach 5")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        # Cancel from draft
        o1 = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers,
        )).json()
        c1_resp = await client.post(f"/api/v1/outreach/{o1['id']}/cancel", headers=headers)
        assert c1_resp.status_code == 200
        assert c1_resp.json()["status"] == "cancelled"

        # Cancelled is terminal: cannot send
        bad_send = await client.post(f"/api/v1/outreach/{o1['id']}/send", headers=headers)
        assert bad_send.status_code == 400

        # Cancel from scheduled
        o2 = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers,
        )).json()
        await client.post(f"/api/v1/outreach/{o2['id']}/schedule", headers=headers)
        c2_resp = await client.post(f"/api/v1/outreach/{o2['id']}/cancel", headers=headers)
        assert c2_resp.status_code == 200
        assert c2_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_outreach_failed_delivery_can_reschedule(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin6@outreach.com", "Org Outreach 6")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        # Create and schedule
        o = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
                "body": "Hi Alex, please review the proposal.",
            },
            headers=headers,
        )).json()
        oid = uuid.UUID(o["id"])
        await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)

        # Directly invoke service send with a failing MockEmailProvider
        org_id = uuid.UUID(o["organization_id"])
        failing_provider = MockEmailProvider(should_fail=True, failure_reason="Simulated network bounce")
        failed_outreach = send_outreach(test_db_session, org_id, oid, provider=failing_provider)
        assert failed_outreach.status == "failed"

        # Failed outreach can be rescheduled: failed -> scheduled
        resched_resp = await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)
        assert resched_resp.status_code == 200
        assert resched_resp.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_completed_campaign_cannot_execute_outreach(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin7@outreach.com", "Org Outreach 7")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        o = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers,
        )).json()
        oid = o["id"]
        await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)

        # Complete campaign: draft -> active -> completed
        cid = setup["campaign_id"]
        await client.post(f"/api/v1/campaigns/{cid}/activate", headers=headers)
        await client.post(f"/api/v1/campaigns/{cid}/complete", headers=headers)

        # Sending outreach for completed campaign must return 400
        send_resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert send_resp.status_code == 400


@pytest.mark.asyncio
async def test_campaign_contact_enrollment_status_untouched_after_send(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin8@outreach.com", "Org Outreach 8")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        o = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
                "body": "Hi Alex, please review the proposal.",
            },
            headers=headers,
        )).json()
        oid = o["id"]
        await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)

        # Verify CampaignContact enrollment_status is STILL 'queued'
        contacts_resp = await client.get(f"/api/v1/campaigns/{setup['campaign_id']}/contacts", headers=headers)
        assert contacts_resp.status_code == 200
        enrollments = contacts_resp.json()
        assert len(enrollments) == 1
        assert enrollments[0]["enrollment_status"] == "queued"


# ── Outreach Query & Update Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_update_and_list_outreach(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin9@outreach.com", "Org Outreach 9")
        headers = {"Authorization": f"Bearer {token}"}
        setup = await setup_enrolled_contact(client, headers)

        create_resp = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup["campaign_id"],
                "contact_id": setup["contact_id"],
                "campaign_contact_id": setup["campaign_contact_id"],
                "channel": "email",
                "subject": "Initial Note",
                "body": "Initial body text",
            },
            headers=headers,
        )
        oid = create_resp.json()["id"]

        # Get
        get_resp = await client.get(f"/api/v1/outreach/{oid}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["subject"] == "Initial Note"

        # Update
        patch_resp = await client.patch(
            f"/api/v1/outreach/{oid}",
            json={"subject": "Revised Subject", "body": "Revised body"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["subject"] == "Revised Subject"
        assert patch_resp.json()["body"] == "Revised body"

        # List with filter
        list_resp = await client.get(
            f"/api/v1/outreach?campaign_id={setup['campaign_id']}&channel=email",
            headers=headers,
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.headers.get("X-Total-Count") == "1"


# ── Multi-Tenant Isolation Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_outreach_isolation(test_db_session):
    async with make_client() as client:
        token_a = await register_tenant(client, "alpha@outreach.com", "Org Alpha")
        token_b = await register_tenant(client, "beta@outreach.com", "Org Beta")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        setup_a = await setup_enrolled_contact(client, headers_a)
        setup_b = await setup_enrolled_contact(client, headers_b)

        # Org B creates outreach
        o_b = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup_b["campaign_id"],
                "contact_id": setup_b["contact_id"],
                "campaign_contact_id": setup_b["campaign_contact_id"],
                "channel": "email",
                "subject": "Secret B Message",
            },
            headers=headers_b,
        )).json()
        oid_b = o_b["id"]

        # 1. Org A cannot get Org B's outreach (404)
        get_b = await client.get(f"/api/v1/outreach/{oid_b}", headers=headers_a)
        assert get_b.status_code == 404

        # 2. Org A cannot update Org B's outreach (404)
        patch_b = await client.patch(
            f"/api/v1/outreach/{oid_b}",
            json={"subject": "Hacked Subject"},
            headers=headers_a,
        )
        assert patch_b.status_code == 404

        # 3. Org A cannot schedule Org B's outreach (404)
        sched_b = await client.post(f"/api/v1/outreach/{oid_b}/schedule", headers=headers_a)
        assert sched_b.status_code == 404

        # 4. Org A cannot send Org B's outreach (404)
        send_b = await client.post(f"/api/v1/outreach/{oid_b}/send", headers=headers_a)
        assert send_b.status_code == 404

        # 5. Org A cannot cancel Org B's outreach (404)
        cancel_b = await client.post(f"/api/v1/outreach/{oid_b}/cancel", headers=headers_a)
        assert cancel_b.status_code == 404

        # 6. Org A cannot view Org B's outreach events (404)
        events_b = await client.get(f"/api/v1/outreach/{oid_b}/events", headers=headers_a)
        assert events_b.status_code == 404

        # 7. Org A cannot create outreach using Org B's campaign (404)
        bad_create1 = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup_b["campaign_id"],
                "contact_id": setup_a["contact_id"],
                "campaign_contact_id": setup_a["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers_a,
        )
        assert bad_create1.status_code == 404

        # 8. Org A cannot create outreach using Org B's contact (404)
        bad_create2 = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup_a["campaign_id"],
                "contact_id": setup_b["contact_id"],
                "campaign_contact_id": setup_a["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers_a,
        )
        assert bad_create2.status_code == 404

        # 9. Org A cannot create outreach using Org B's campaign contact (404)
        bad_create3 = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": setup_a["campaign_id"],
                "contact_id": setup_a["contact_id"],
                "campaign_contact_id": setup_b["campaign_contact_id"],
                "channel": "email",
            },
            headers=headers_a,
        )
        assert bad_create3.status_code == 404
