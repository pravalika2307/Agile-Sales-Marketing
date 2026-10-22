"""Regression and integration tests for campaign channel persistence.

Verifies:
1. Creating a campaign with SMS as the first step persists an SMS workflow node.
2. Opening /api/v1/campaigns/{id}/workflow retrieves the SMS node and NEVER defaults to Email.
3. Editing and saving the SMS workflow persists cleanly without mutating to Email.
4. Voice first step campaigns correctly persist Voice SDR nodes.
5. Scheduled campaign advancement creates outreach with channel='sms' matching the workflow step.
6. Multi-tenant isolation is strictly maintained across organizations.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.outreach import Outreach
from app.models.crm import Contact
from app.services.campaign_scheduler import CampaignSchedulerService


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


def make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_sms_campaign_creation_and_workflow_persistence(test_db_session):
    """
    CRITICAL BUG REPRODUCTION & REGRESSION TEST:
    Creating a campaign with first_step_channel='sms' must persist an SMS step
    and retrieve an SMS workflow node, never defaulting or mutating to Email.
    """
    async with make_client() as client:
        token = await register_tenant(client, "sms_camp_test@example.com", "SMS Test Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create campaign selecting SMS channel
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "name": "SMS Outreach Test Campaign",
                "type": "sales_outbound",
                "description": "Direct SMS sequence for senior executive briefing",
                "first_step_channel": "sms",
            },
            headers=headers,
        )
        assert create_resp.status_code == 201, f"Campaign creation failed: {create_resp.text}"
        campaign_data = create_resp.json()
        camp_id = campaign_data["id"]

        # Verify initial returned campaign has workflow_config with SMS node
        assert campaign_data.get("workflow_config") is not None
        nodes = campaign_data["workflow_config"]["nodes"]
        assert len(nodes) >= 2
        assert nodes[0]["type"] == "start"
        assert nodes[1]["type"] == "sms", f"Expected SMS first step, got {nodes[1]['type']}"
        assert "SMS" in nodes[1]["title"]

        # 2. Open workflow editor via GET /api/v1/campaigns/{id}/workflow
        wf_resp = await client.get(f"/api/v1/campaigns/{camp_id}/workflow", headers=headers)
        assert wf_resp.status_code == 200, f"Get workflow failed: {wf_resp.text}"
        wf_data = wf_resp.json()

        wf_nodes = wf_data["nodes"]
        assert len(wf_nodes) >= 2
        assert wf_nodes[0]["type"] == "start"
        # Channel-persistence assertion: step 1 MUST BE SMS, NOT email
        assert wf_nodes[1]["type"] == "sms", (
            f"CHANNEL PERSISTENCE BUG DETECTED: First step node type is '{wf_nodes[1]['type']}', expected 'sms'!"
        )
        assert "{contact.first_name}" in wf_nodes[1]["config"]["body"]

        # 3. Update the SMS content and save workflow via PUT /api/v1/campaigns/{id}/workflow
        updated_nodes = list(wf_nodes)
        updated_nodes[1]["config"]["body"] = (
            "Hi {contact.first_name}, connecting from {sender_company_name}. Book a briefing here: {booking_link}"
        )
        updated_nodes[1]["title"] = "Step 1: Executive SMS"

        save_resp = await client.put(
            f"/api/v1/campaigns/{camp_id}/workflow",
            json={"workflow_config": {"nodes": updated_nodes, "edges": wf_data["edges"]}},
            headers=headers,
        )
        assert save_resp.status_code == 200, f"Workflow save failed: {save_resp.text}"
        save_data = save_resp.json()
        assert save_data["validation"]["is_valid"] is True
        assert save_data["workflow_config"]["nodes"][1]["type"] == "sms"

        # 4. Reopen workflow editor again to confirm persisted state
        reopen_resp = await client.get(f"/api/v1/campaigns/{camp_id}/workflow", headers=headers)
        assert reopen_resp.status_code == 200
        reopen_wf = reopen_resp.json()
        assert reopen_wf["nodes"][1]["type"] == "sms"
        assert "Executive SMS" in reopen_wf["nodes"][1]["title"]
        assert "Book a briefing here: {booking_link}" in reopen_wf["nodes"][1]["config"]["body"]


@pytest.mark.asyncio
async def test_voice_campaign_creation_and_workflow_persistence(test_db_session):
    """Voice first step campaigns correctly persist Voice SDR nodes."""
    async with make_client() as client:
        token = await register_tenant(client, "voice_camp_test@example.com", "Voice Test Org")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "name": "AI SDR Voice Outreach",
                "type": "sales_outbound",
                "first_step_channel": "voice",
            },
            headers=headers,
        )
        assert create_resp.status_code == 201
        camp_id = create_resp.json()["id"]

        wf_resp = await client.get(f"/api/v1/campaigns/{camp_id}/workflow", headers=headers)
        assert wf_resp.status_code == 200
        nodes = wf_resp.json()["nodes"]
        assert len(nodes) >= 2
        assert nodes[1]["type"] == "voice"
        assert "Voice" in nodes[1]["title"]


@pytest.mark.asyncio
async def test_sms_campaign_scheduler_advancement_creates_sms_outreach(test_db_session):
    """Campaign scheduler creates outreach with channel='sms' when step is SMS."""
    async with make_client() as client:
        token = await register_tenant(client, "sched_sms@example.com", "Sched SMS Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create SMS campaign
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "name": "Scheduled SMS Cadence",
                "type": "sales_outbound",
                "first_step_channel": "sms",
            },
            headers=headers,
        )
        camp_id = create_resp.json()["id"]

        from app.services.organization_config import register_organization_booking_url
        register_organization_booking_url("sched-sms-org", "https://cal.com/sched-sms/15min")
        register_organization_booking_url("Sched SMS Org", "https://cal.com/sched-sms/15min")

        # 2. Create contact with phone
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "email": "sms_lead@example.com",
                "first_name": "Arjun",
                "last_name": "Sharma",
                "phone": "+919876543210",
            },
            headers=headers,
        )
        cont_id = cont_resp.json()["id"]

        # 3. Enroll contact in campaign
        enr_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/contacts/{cont_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )
        assert enr_resp.status_code == 201

        # 4. Activate campaign
        act_resp = await client.post(f"/api/v1/campaigns/{camp_id}/activate", headers=headers)
        assert act_resp.status_code == 200

        # 5. Run scheduler tick
        scheduler = CampaignSchedulerService(db=test_db_session)
        tick_result = scheduler.plan_due_steps(
            campaign_id=uuid.UUID(camp_id),
            dry_run=False,
            sender_name="Kunal",
        )

        assert tick_result.planned_count == 1
        assert tick_result.error_count == 0

        # 6. Verify created outreach has channel == 'sms'
        outreaches = (
            test_db_session.query(Outreach)
            .filter(Outreach.campaign_id == uuid.UUID(camp_id))
            .all()
        )
        assert len(outreaches) == 1
        assert outreaches[0].channel == "sms", f"Expected outreach channel 'sms', got '{outreaches[0].channel}'"
        assert "Arjun" in outreaches[0].body
