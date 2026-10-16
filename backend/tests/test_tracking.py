"""Integration tests for Outreach email tracking and response events (Step 7)."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.services.outreach.base import EmailMessage, EmailProvider, EmailSendResult
from app.services.outreach.service import send_outreach


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
            "full_name": "Tracking Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def setup_sent_outreach(client: AsyncClient, headers: dict) -> dict:
    """Helper to create campaign, contact, enrollment, and transition an outreach to 'sent'."""
    # 1. Create campaign
    camp = (await client.post(
        "/api/v1/campaigns",
        json={"name": "Tracking Campaign", "type": "sales_outbound"},
        headers=headers,
    )).json()

    # 2. Create contact
    contact = (await client.post(
        "/api/v1/contacts",
        json={"email": "tracking.lead@example.com", "first_name": "Jordan", "last_name": "Lee"},
        headers=headers,
    )).json()

    # 3. Enroll contact
    enrollment = (await client.post(
        f"/api/v1/campaigns/{camp['id']}/contacts/{contact['id']}",
        json={"enrollment_status": "queued"},
        headers=headers,
    )).json()

    # 4. Create draft outreach
    outreach = (await client.post(
        "/api/v1/outreach",
        json={
            "campaign_id": camp["id"],
            "contact_id": contact["id"],
            "campaign_contact_id": enrollment["id"],
            "channel": "email",
            "subject": "Platform Demonstration",
            "body": "Hi Jordan, here is the demo link.",
        },
        headers=headers,
    )).json()

    # 5. Schedule
    sched = (await client.post(f"/api/v1/outreach/{outreach['id']}/schedule", headers=headers)).json()
    assert sched["status"] == "scheduled"

    # 6. Send
    sent = (await client.post(f"/api/v1/outreach/{outreach['id']}/send", headers=headers)).json()
    assert sent["status"] == "sent"

    return {
        "campaign_id": camp["id"],
        "contact_id": contact["id"],
        "campaign_contact_id": enrollment["id"],
        "outreach_id": outreach["id"],
    }


# ── 1. Delivered Event Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_delivered_lifecycle_and_idempotency(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_deliv@test.com", "Org Deliv")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]

        # Initial delivered
        resp1 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/delivered",
            json={"event_metadata": {"provider": "mock", "provider_message_id": "mock-123"}},
            headers=headers,
        )
        assert resp1.status_code == 200
        event1 = resp1.json()
        assert event1["event_type"] == "delivered"
        assert event1["event_metadata"]["provider"] == "mock"

        # Check Outreach model
        outreach_resp1 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_resp1["status"] == "sent"
        first_deliv = outreach_resp1["first_delivered_at"]
        assert first_deliv is not None

        # Repeated delivered
        resp2 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/delivered",
            json={"event_metadata": {"provider": "mock", "duplicate": True}},
            headers=headers,
        )
        assert resp2.status_code == 200

        # first_delivered_at must NOT be overwritten
        outreach_resp2 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_resp2["status"] == "sent"
        assert outreach_resp2["first_delivered_at"] == first_deliv

        # Verify audit history has both events
        events_resp = await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)
        events = events_resp.json()
        delivered_events = [e for e in events if e["event_type"] == "delivered"]
        assert len(delivered_events) == 2


# ── 2. Opened Event Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_opened_lifecycle_and_idempotency(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_open@test.com", "Org Open")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]

        # First open
        resp1 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/opened",
            json={"event_metadata": {"user_agent": "Mozilla/5.0", "ip_hash": "hash_1"}},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["event_type"] == "opened"

        outreach1 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach1["status"] == "sent"
        first_open = outreach1["first_opened_at"]
        assert first_open is not None

        # Repeated open
        resp2 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/opened",
            json={"event_metadata": {"user_agent": "Mozilla/5.0", "ip_hash": "hash_2"}},
            headers=headers,
        )
        assert resp2.status_code == 200

        outreach2 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach2["status"] == "sent"
        assert outreach2["first_opened_at"] == first_open


# ── 3. Clicked Event Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_clicked_lifecycle_and_idempotency(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_click@test.com", "Org Click")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]

        # First click
        resp1 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/clicked",
            json={"event_metadata": {"url": "https://example.com/demo"}},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["event_type"] == "clicked"

        outreach1 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach1["status"] == "sent"
        first_click = outreach1["first_clicked_at"]
        assert first_click is not None

        # Repeated click
        resp2 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/clicked",
            json={"event_metadata": {"url": "https://example.com/pricing"}},
            headers=headers,
        )
        assert resp2.status_code == 200

        outreach2 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach2["status"] == "sent"
        assert outreach2["first_clicked_at"] == first_click


# ── 4. Replied Event Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_replied_updates_contact_lead_status(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_reply@test.com", "Org Reply")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        cid = ctx["contact_id"]

        # Contact initially has default lead_status != "replied"
        contact_before = (await client.get(f"/api/v1/contacts/{cid}", headers=headers)).json()
        assert contact_before["lead_status"] != "replied"

        # First reply
        resp1 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/replied",
            json={"event_metadata": {"message_id": "msg-001", "thread_id": "thread-001"}},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["event_type"] == "replied"

        outreach1 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach1["status"] == "sent"
        first_reply = outreach1["first_replied_at"]
        assert first_reply is not None

        # Contact lead_status updated to "replied"
        contact_after = (await client.get(f"/api/v1/contacts/{cid}", headers=headers)).json()
        assert contact_after["lead_status"] == "replied"

        # Repeated reply
        resp2 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/replied",
            json={"event_metadata": {"message_id": "msg-002"}},
            headers=headers,
        )
        assert resp2.status_code == 200

        outreach2 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach2["first_replied_at"] == first_reply


@pytest.mark.asyncio
async def test_record_replied_does_not_override_opted_out_contact(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_optout@test.com", "Org OptOut")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        cid = ctx["contact_id"]

        # Explicitly opt-out contact
        opt_resp = await client.patch(
            f"/api/v1/contacts/{cid}",
            json={"lead_status": "opted_out"},
            headers=headers,
        )
        assert opt_resp.status_code == 200
        assert opt_resp.json()["lead_status"] == "opted_out"

        # Record reply
        resp = await client.post(
            f"/api/v1/outreach/{oid}/tracking/replied",
            headers=headers,
        )
        assert resp.status_code == 200

        # first_replied_at is recorded
        outreach = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach["first_replied_at"] is not None

        # Contact MUST remain "opted_out"
        contact = (await client.get(f"/api/v1/contacts/{cid}", headers=headers)).json()
        assert contact["lead_status"] == "opted_out"


# ── 5. Bounced Event Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_bounced_preserves_contact_and_campaign_enrollment(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_bounce@test.com", "Org Bounce")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        cid = ctx["contact_id"]
        camp_id = ctx["campaign_id"]

        # Record bounced
        resp1 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/bounced",
            json={"event_metadata": {"reason": "550 User unknown", "bounce_type": "hard"}},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["event_type"] == "bounced"

        outreach1 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach1["status"] == "sent"
        first_bounce = outreach1["first_bounced_at"]
        assert first_bounce is not None

        # Contact MUST remain intact
        c_resp = await client.get(f"/api/v1/contacts/{cid}", headers=headers)
        assert c_resp.status_code == 200
        assert c_resp.json()["id"] == cid

        # CampaignContact enrollment MUST remain intact
        enrollments_resp = await client.get(
            f"/api/v1/campaigns/{camp_id}/contacts",
            headers=headers,
        )
        assert enrollments_resp.status_code == 200
        assert any(e["contact_id"] == cid for e in enrollments_resp.json())

        # Repeated bounce does not overwrite first_bounced_at
        resp2 = await client.post(
            f"/api/v1/outreach/{oid}/tracking/bounced",
            json={"event_metadata": {"reason": "Repeated notice"}},
            headers=headers,
        )
        assert resp2.status_code == 200
        outreach2 = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach2["first_bounced_at"] == first_bounce


# ── 6. Invalid States Rejected ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tracking_rejected_for_draft_scheduled_cancelled_failed(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_invalid@test.com", "Org Invalid")
        headers = {"Authorization": f"Bearer {token}"}

        # Setup draft
        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Invalid State Test Camp", "type": "sales_outbound"},
            headers=headers,
        )).json()
        contact = (await client.post(
            "/api/v1/contacts",
            json={"email": "invalid.lead@example.com", "first_name": "Test", "last_name": "Invalid"},
            headers=headers,
        )).json()
        enrollment = (await client.post(
            f"/api/v1/campaigns/{camp['id']}/contacts/{contact['id']}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )).json()

        draft = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": camp["id"],
                "contact_id": contact["id"],
                "campaign_contact_id": enrollment["id"],
                "channel": "email",
                "subject": "Testing Invalid States",
            },
            headers=headers,
        )).json()
        draft_id = draft["id"]

        # 1. Draft outreach rejected
        for action in ("delivered", "opened", "clicked", "replied", "bounced"):
            r = await client.post(f"/api/v1/outreach/{draft_id}/tracking/{action}", headers=headers)
            assert r.status_code == 400, f"Expected 400 for {action} on draft, got {r.status_code}"

        # 2. Scheduled outreach rejected
        await client.post(f"/api/v1/outreach/{draft_id}/schedule", headers=headers)
        for action in ("delivered", "opened", "clicked", "replied", "bounced"):
            r = await client.post(f"/api/v1/outreach/{draft_id}/tracking/{action}", headers=headers)
            assert r.status_code == 400, f"Expected 400 for {action} on scheduled, got {r.status_code}"

        # 3. Cancelled outreach rejected
        await client.post(f"/api/v1/outreach/{draft_id}/cancel", headers=headers)
        for action in ("delivered", "opened", "clicked", "replied", "bounced"):
            r = await client.post(f"/api/v1/outreach/{draft_id}/tracking/{action}", headers=headers)
            assert r.status_code == 400, f"Expected 400 for {action} on cancelled, got {r.status_code}"

        # 4. Failed outreach rejected
        draft2 = (await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": camp["id"],
                "contact_id": contact["id"],
                "campaign_contact_id": enrollment["id"],
                "channel": "email",
                "subject": "Will Fail",
                "body": "Body content for failing outreach test.",
            },
            headers=headers,
        )).json()
        await client.post(f"/api/v1/outreach/{draft2['id']}/schedule", headers=headers)

        class FailingProvider(EmailProvider):
            @property
            def provider_name(self) -> str:
                return "failing_mock"

            def send(self, message: EmailMessage) -> EmailSendResult:
                return EmailSendResult(success=False, provider="failing_mock", provider_message_id="fail-1", error_message="Simulated connection error")

        # Execute send with failing provider directly via service
        org_resp = (await client.get("/api/v1/auth/me", headers=headers)).json()
        org_id = uuid.UUID(org_resp["organization_id"])
        send_outreach(test_db_session, org_id, uuid.UUID(draft2["id"]), provider=FailingProvider())

        failed_check = (await client.get(f"/api/v1/outreach/{draft2['id']}", headers=headers)).json()
        assert failed_check["status"] == "failed"

        for action in ("delivered", "opened", "clicked", "replied", "bounced"):
            r = await client.post(f"/api/v1/outreach/{draft2['id']}/tracking/{action}", headers=headers)
            assert r.status_code == 400, f"Expected 400 for {action} on failed, got {r.status_code}"


# ── 7. Tenant Isolation Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_on_tracking_and_events(test_db_session):
    async with make_client() as client:
        # Tenant A
        token_a = await register_tenant(client, "admin_a@test.com", "Tenant A")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        ctx_a = await setup_sent_outreach(client, headers_a)
        oid_a = ctx_a["outreach_id"]

        # Tenant B
        token_b = await register_tenant(client, "admin_b@test.com", "Tenant B")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant B cannot record tracking events for Tenant A's outreach
        for action in ("delivered", "opened", "clicked", "replied", "bounced"):
            r = await client.post(f"/api/v1/outreach/{oid_a}/tracking/{action}", headers=headers_b)
            assert r.status_code == 404, f"Expected 404 cross-tenant for {action}, got {r.status_code}"

        # Tenant B cannot retrieve Tenant A's event history
        r_events = await client.get(f"/api/v1/outreach/{oid_a}/events", headers=headers_b)
        assert r_events.status_code == 404

        # Verify Tenant A's tracking timestamps were untouched
        outreach_a = (await client.get(f"/api/v1/outreach/{oid_a}", headers=headers_a)).json()
        assert outreach_a["first_delivered_at"] is None
        assert outreach_a["first_opened_at"] is None
        assert outreach_a["first_clicked_at"] is None
        assert outreach_a["first_replied_at"] is None
        assert outreach_a["first_bounced_at"] is None


# ── 8. Event History Chronological Ordering ───────────────────────────────────

@pytest.mark.asyncio
async def test_event_history_chronological_ordering(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_order@test.com", "Org Order")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]

        # Record events sequentially
        await client.post(f"/api/v1/outreach/{oid}/tracking/delivered", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/opened", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/clicked", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/replied", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/bounced", headers=headers)

        events_resp = await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)
        assert events_resp.status_code == 200
        events = events_resp.json()

        event_types = [e["event_type"] for e in events]
        expected_types = [
            "created",
            "scheduled",
            "sending",
            "sent",
            "delivered",
            "opened",
            "clicked",
            "replied",
            "bounced",
        ]
        assert event_types == expected_types

        # Verify occurred_at ordering is non-decreasing
        timestamps = [e["occurred_at"] for e in events]
        assert timestamps == sorted(timestamps)


# ── 9. Safe Metadata Persisted ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safe_metadata_persisted_correctly(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_meta@test.com", "Org Meta")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]

        meta_open = {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "ip_hash": "a1b2c3d4"}
        resp_open = await client.post(
            f"/api/v1/outreach/{oid}/tracking/opened",
            json={"event_metadata": meta_open},
            headers=headers,
        )
        assert resp_open.status_code == 200
        assert resp_open.json()["event_metadata"] == meta_open

        meta_click = {"url": "https://example.com/pricing", "link_id": "cta_button"}
        resp_click = await client.post(
            f"/api/v1/outreach/{oid}/tracking/clicked",
            json={"event_metadata": meta_click},
            headers=headers,
        )
        assert resp_click.status_code == 200
        assert resp_click.json()["event_metadata"] == meta_click

        # Check persisted in events history
        events_resp = await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)
        events = events_resp.json()
        open_evt = next(e for e in events if e["event_type"] == "opened")
        click_evt = next(e for e in events if e["event_type"] == "clicked")
        assert open_evt["event_metadata"] == meta_open
        assert click_evt["event_metadata"] == meta_click
