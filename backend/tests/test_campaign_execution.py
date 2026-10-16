"""Integration tests for Campaign Execution & Outreach Orchestration Foundation (Step 8)."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Contact
from app.models.outreach import Outreach


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
            "full_name": "Orchestrator Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def setup_campaign_with_contacts(
    client: AsyncClient,
    headers: dict,
    num_contacts: int = 2,
    activate: bool = True,
) -> dict:
    """Helper to create a campaign and enroll multiple contacts."""
    # 1. Create campaign
    camp = (await client.post(
        "/api/v1/campaigns",
        json={"name": "Outreach Sequence", "type": "sales_outbound"},
        headers=headers,
    )).json()

    # 2. Activate if requested
    if activate:
        camp = (await client.post(f"/api/v1/campaigns/{camp['id']}/activate", headers=headers)).json()
        assert camp["status"] == "active"

    contact_ids = []
    enrollment_ids = []

    for i in range(num_contacts):
        c = (await client.post(
            "/api/v1/contacts",
            json={
                "email": f"lead{i}_{uuid.uuid4().hex[:6]}@example.com",
                "first_name": f"Lead{i}",
                "last_name": f"User{i}",
            },
            headers=headers,
        )).json()
        contact_ids.append(c["id"])

        enr = (await client.post(
            f"/api/v1/campaigns/{camp['id']}/contacts/{c['id']}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )).json()
        enrollment_ids.append(enr["id"])

    return {
        "campaign_id": camp["id"],
        "campaign": camp,
        "contact_ids": contact_ids,
        "enrollment_ids": enrollment_ids,
    }


# ── 1. Preview Tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_active_campaign_and_immutability(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_prev@test.com", "Org Preview")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=2, activate=True)
        camp_id = ctx["campaign_id"]

        # Call preview endpoint
        resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute/preview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["campaign_id"] == camp_id
        assert data["eligible_count"] == 2
        assert len(data["eligible_campaign_contact_ids"]) == 2
        assert set(data["eligible_campaign_contact_ids"]) == set(ctx["enrollment_ids"])
        assert data["skipped_count"] == 0
        assert data["skipped_campaign_contact_ids"] == []
        assert data["rejected_count"] == 0
        assert data["rejected_campaign_contact_ids"] == []

        # Immutability Check: verify zero database mutations occurred
        # 1. Zero outreaches created
        list_outreach = (await client.get(f"/api/v1/outreach?campaign_id={camp_id}", headers=headers)).json()
        assert len(list_outreach) == 0

        # 2. CampaignContacts must remain 'queued' and current_step == 0
        enrolled_resp = (await client.get(f"/api/v1/campaigns/{camp_id}/contacts", headers=headers)).json()
        for enr in enrolled_resp:
            assert enr["enrollment_status"] == "queued"
            assert enr["current_step"] == 0


@pytest.mark.asyncio
async def test_preview_excludes_opted_out_and_already_processed_contacts(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_excl@test.com", "Org Exclude")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=3, activate=True)
        camp_id = ctx["campaign_id"]
        c_ids = ctx["contact_ids"]
        enr_ids = ctx["enrollment_ids"]

        # Contact 0: remains queued and eligible
        # Contact 1: opt out
        await client.patch(
            f"/api/v1/contacts/{c_ids[1]}",
            json={"lead_status": "opted_out"},
            headers=headers,
        )

        # Contact 2: manually advance status to in_progress
        patch_resp = await client.patch(
            f"/api/v1/campaigns/{camp_id}/contacts/{c_ids[2]}/status",
            json={"enrollment_status": "in_progress"},
            headers=headers,
        )
        assert patch_resp.status_code == 200

        resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute/preview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["eligible_count"] == 1
        assert data["eligible_campaign_contact_ids"] == [enr_ids[0]]
        assert data["skipped_count"] == 2
        assert set(data["skipped_campaign_contact_ids"]) == {enr_ids[1], enr_ids[2]}
        assert data["rejected_count"] == 0


# ── 2. Execution Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execution_active_campaign_creates_draft_outreach_and_advances_status(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_exec@test.com", "Org Exec")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=2, activate=True)
        camp_id = ctx["campaign_id"]

        resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["campaign_id"] == camp_id
        assert data["eligible_count"] == 2
        assert data["created_count"] == 2
        assert len(data["created_outreach_ids"]) == 2
        assert data["skipped_count"] == 0
        assert data["rejected_count"] == 0

        # Verify created Outreach items
        for oid in data["created_outreach_ids"]:
            outreach = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
            assert outreach["status"] == "draft"
            assert outreach["channel"] == "email"
            assert outreach["subject"] is None
            assert outreach["body"] is None
            assert outreach["provider"] is None
            assert outreach["provider_message_id"] is None
            assert outreach["sent_at"] is None
            assert outreach["scheduled_at"] is None

            # Verify initial 'created' event exists
            events = (await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)).json()
            assert len(events) == 1
            assert events[0]["event_type"] == "created"

        # Verify CampaignContacts transitioned to 'in_progress' and current_step == 1
        enrolled_resp = (await client.get(f"/api/v1/campaigns/{camp_id}/contacts", headers=headers)).json()
        for enr in enrolled_resp:
            assert enr["enrollment_status"] == "in_progress"
            assert enr["current_step"] == 1


# ── 3. Duplicate Prevention Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_prevention_on_repeated_execution(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_dup@test.com", "Org Dup")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=2, activate=True)
        camp_id = ctx["campaign_id"]

        # First execution
        resp1 = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["created_count"] == 2

        # Second execution immediately afterwards
        resp2 = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data2["eligible_count"] == 0
        assert data2["created_count"] == 0
        assert data2["created_outreach_ids"] == []
        assert data2["skipped_count"] == 2
        assert set(data2["skipped_campaign_contact_ids"]) == set(ctx["enrollment_ids"])
        assert data2["rejected_count"] == 0

        # Total outreach records in database remains exactly 2
        all_outreaches = (await client.get(f"/api/v1/outreach?campaign_id={camp_id}", headers=headers)).json()
        assert len(all_outreaches) == 2


# ── 4. Campaign State Validation Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_execution_and_preview_respect_campaign_states(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_states@test.com", "Org States")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Draft Campaign
        ctx_draft = await setup_campaign_with_contacts(client, headers, num_contacts=1, activate=False)
        camp_draft_id = ctx_draft["campaign_id"]

        # Execution rejected with 400
        exec_draft = await client.post(f"/api/v1/campaigns/{camp_draft_id}/execute", headers=headers)
        assert exec_draft.status_code == 400
        assert "active" in exec_draft.json()["detail"]

        # Preview returns 200 with 0 eligible contacts
        prev_draft = await client.post(f"/api/v1/campaigns/{camp_draft_id}/execute/preview", headers=headers)
        assert prev_draft.status_code == 200
        assert prev_draft.json()["eligible_count"] == 0
        assert prev_draft.json()["skipped_count"] == 1

        # 2. Paused Campaign
        await client.post(f"/api/v1/campaigns/{camp_draft_id}/activate", headers=headers)
        await client.post(f"/api/v1/campaigns/{camp_draft_id}/pause", headers=headers)

        exec_paused = await client.post(f"/api/v1/campaigns/{camp_draft_id}/execute", headers=headers)
        assert exec_paused.status_code == 400

        prev_paused = await client.post(f"/api/v1/campaigns/{camp_draft_id}/execute/preview", headers=headers)
        assert prev_paused.status_code == 200
        assert prev_paused.json()["eligible_count"] == 0
        assert prev_paused.json()["skipped_count"] == 1

        # 3. Completed Campaign
        await client.post(f"/api/v1/campaigns/{camp_draft_id}/complete", headers=headers)

        exec_completed = await client.post(f"/api/v1/campaigns/{camp_draft_id}/execute", headers=headers)
        assert exec_completed.status_code == 400

        prev_completed = await client.post(f"/api/v1/campaigns/{camp_draft_id}/execute/preview", headers=headers)
        assert prev_completed.status_code == 200
        assert prev_completed.json()["eligible_count"] == 0
        assert prev_completed.json()["skipped_count"] == 1


# ── 5. Tenant Isolation Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_on_campaign_execution(test_db_session):
    async with make_client() as client:
        # Tenant A
        token_a = await register_tenant(client, "admin_ta@test.com", "Tenant A")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        ctx_a = await setup_campaign_with_contacts(client, headers_a, num_contacts=1, activate=True)
        camp_a_id = ctx_a["campaign_id"]

        # Tenant B
        token_b = await register_tenant(client, "admin_tb@test.com", "Tenant B")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant B cannot preview Tenant A's campaign -> 404
        r_prev = await client.post(f"/api/v1/campaigns/{camp_a_id}/execute/preview", headers=headers_b)
        assert r_prev.status_code == 404

        # Tenant B cannot execute Tenant A's campaign -> 404
        r_exec = await client.post(f"/api/v1/campaigns/{camp_a_id}/execute", headers=headers_b)
        assert r_exec.status_code == 404


# ── 6. Opt-Out Protection Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_opted_out_contact_is_never_executed(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_opt@test.com", "Org OptOut Guard")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=1, activate=True)
        camp_id = ctx["campaign_id"]
        cid = ctx["contact_ids"][0]

        # Explicitly opt-out contact
        await client.patch(f"/api/v1/contacts/{cid}", json={"lead_status": "opted_out"}, headers=headers)

        # Execute
        resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["eligible_count"] == 0
        assert data["created_count"] == 0
        assert data["skipped_count"] == 1
        assert data["created_outreach_ids"] == []

        # Zero outreaches in database
        outreaches = (await client.get(f"/api/v1/outreach?campaign_id={camp_id}", headers=headers)).json()
        assert len(outreaches) == 0


# ── 7. Relationship Inconsistency Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_inconsistent_enrollment_relationship_is_rejected(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_incons@test.com", "Org Inconsistent")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=1, activate=True)
        camp_id = ctx["campaign_id"]
        enr_id = uuid.UUID(ctx["enrollment_ids"][0])

        # Tamper enrollment in database to point to an invalid / nonexistent contact ID
        invalid_contact_id = uuid.uuid4()
        cc = test_db_session.query(CampaignContact).filter(CampaignContact.id == enr_id).first()
        cc.contact_id = invalid_contact_id
        test_db_session.commit()

        # Preview reports rejected
        prev = (await client.post(f"/api/v1/campaigns/{camp_id}/execute/preview", headers=headers)).json()
        assert prev["eligible_count"] == 0
        assert prev["rejected_count"] == 1
        assert prev["rejected_campaign_contact_ids"] == [str(enr_id)]

        # Execution reports rejected safely
        resp = (await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)).json()
        assert resp["eligible_count"] == 0
        assert resp["created_count"] == 0
        assert resp["rejected_count"] == 1
        assert resp["rejected_campaign_contact_ids"] == [str(enr_id)]


# ── 8. Transaction Safety Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transaction_safety_rolls_back_partial_state_on_failure(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_tx@test.com", "Org Tx Safety")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=1, activate=True)
        camp_id = ctx["campaign_id"]
        enr_id = ctx["enrollment_ids"][0]

        # Patch create_outreach to simulate an unexpected error during execution
        with patch("app.services.campaign_execution.service.create_outreach", side_effect=RuntimeError("Simulated DB failure")):
            resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["eligible_count"] == 1
            assert data["created_count"] == 0
            assert data["rejected_count"] == 1
            assert data["rejected_campaign_contact_ids"] == [enr_id]

        # Verify CampaignContact was NOT partially updated (remains queued, step 0)
        enr_check = (await client.get(f"/api/v1/campaigns/{camp_id}/contacts", headers=headers)).json()[0]
        assert enr_check["enrollment_status"] == "queued"
        assert enr_check["current_step"] == 0

        # Verify zero outreaches created
        outreaches = (await client.get(f"/api/v1/outreach?campaign_id={camp_id}", headers=headers)).json()
        assert len(outreaches) == 0


# ── 9. Integration with Step 6 Lifecycle & Step 7 Tracking ───────────────────

@pytest.mark.asyncio
async def test_executed_outreach_full_lifecycle_and_tracking(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_integ@test.com", "Org Integ Flow")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_campaign_with_contacts(client, headers, num_contacts=1, activate=True)
        camp_id = ctx["campaign_id"]
        cid = ctx["contact_ids"][0]

        # Configure Step 1 with email copy
        steps = (await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)).json()
        if steps:
            await client.patch(
                f"/api/v1/campaigns/{camp_id}/steps/{steps[0]['id']}",
                json={"subject_template": "Welcome {{first_name}}", "body_template": "Hello {{first_name}}, welcome to our platform!"},
                headers=headers,
            )

        # 1. Execute campaign
        exec_resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
        assert exec_resp.status_code == 200
        oid = exec_resp.json()["created_outreach_ids"][0]

        # 2. Schedule draft outreach (Step 6)
        sched_resp = await client.post(f"/api/v1/outreach/{oid}/schedule", headers=headers)
        assert sched_resp.status_code == 200
        assert sched_resp.json()["status"] == "scheduled"

        # 3. Send outreach with MockEmailProvider (Step 6)
        send_resp = await client.post(f"/api/v1/outreach/{oid}/send", headers=headers)
        assert send_resp.status_code == 200
        assert send_resp.json()["status"] == "sent"

        # 4. Record tracking events (Step 7)
        await client.post(f"/api/v1/outreach/{oid}/tracking/delivered", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/opened", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/clicked", headers=headers)
        await client.post(f"/api/v1/outreach/{oid}/tracking/replied", headers=headers)

        outreach = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach["status"] == "sent"
        assert outreach["first_delivered_at"] is not None
        assert outreach["first_opened_at"] is not None
        assert outreach["first_clicked_at"] is not None
        assert outreach["first_replied_at"] is not None

        # Contact lead_status updated to replied
        contact = (await client.get(f"/api/v1/contacts/{cid}", headers=headers)).json()
        assert contact["lead_status"] == "replied"
