"""Integration & unit tests for Step 9: Campaign Steps, Email Content & Campaign Sequences."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact, Company
from app.models.outreach import Outreach, OutreachEvent
from app.services.campaign_steps.template_renderer import render_template


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
            "full_name": "Step 9 Tester",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── 1. Unit Tests for Deterministic Template Renderer ─────────────────────────

def test_template_renderer_all_variables():
    """Verify all supported variables are deterministically rendered."""
    contact = Contact(
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@example.com",
    )
    company = Company(name="Acme Corp")
    template = "Hi {{first_name}} {{last_name}}, {{full_name}} at {{company_name}} (<{{email}}>). Sent by {{sender_name}}."

    rendered = render_template(
        template,
        contact=contact,
        company=company,
        sender_name="Custom Sender",
    )
    assert rendered == "Hi Jane Doe, Jane Doe at Acme Corp (<jane.doe@example.com>). Sent by Custom Sender."


def test_template_renderer_default_sender_name():
    """Verify sender_name defaults to 'Agile Sales & Marketing' when omitted or None."""
    contact = Contact(first_name="John", last_name="Smith", email="john@example.com")
    template = "From: {{sender_name}}"
    assert render_template(template, contact=contact, sender_name=None) == "From: Agile Sales & Marketing"
    assert render_template(template, contact=contact) == "From: Agile Sales & Marketing"


def test_template_renderer_missing_company():
    """Verify missing company safely renders company_name as empty string."""
    contact = Contact(first_name="Alice", last_name="Wonder", email="alice@example.com")
    template = "Hello {{first_name}} from '{{company_name}}'!"
    rendered = render_template(template, contact=contact, company=None)
    assert rendered == "Hello Alice from ''!"


def test_template_renderer_unknown_variable_untouched():
    """Verify unknown variables remain unmodified in the template string."""
    contact = Contact(first_name="Bob", email="bob@example.com")
    template = "Hello {{first_name}}, check your {{bonus_code}} and {{unknown}}!"
    rendered = render_template(template, contact=contact)
    assert rendered == "Hello Bob, check your {{bonus_code}} and {{unknown}}!"


def test_template_renderer_no_eval_or_python_execution():
    """Verify Python code and expressions are not executed."""
    contact = Contact(first_name="Eve", email="eve@example.com")
    template = "Attack: {{1 + 1}} and {{__import__('os').system('dir')}}."
    rendered = render_template(template, contact=contact)
    assert rendered == "Attack: {{1 + 1}} and {{__import__('os').system('dir')}}."


def test_template_renderer_empty_and_plain_text():
    """Verify plain text and empty/None templates are handled properly."""
    contact = Contact(first_name="Sam", email="sam@example.com")
    assert render_template(None, contact=contact) is None
    assert render_template("", contact=contact) == ""
    assert render_template("Just plain text with no vars.", contact=contact) == "Just plain text with no vars."


# ── 2. Campaign Creation & Default Step 1 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_creation_creates_default_step_1(test_db_session):
    """When a campaign is created, Step 1 is automatically created transactionally."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_creator@example.com", "Step 9 Inc")
        headers = {"Authorization": f"Bearer {token}"}

        # Create campaign
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Outreach Alpha", "type": "sales_outbound"},
            headers=headers,
        )
        assert camp_resp.status_code == 201
        camp_id = camp_resp.json()["id"]

        # Fetch steps for this campaign
        steps_resp = await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)
        assert steps_resp.status_code == 200
        steps = steps_resp.json()
        assert len(steps) == 1

        step1 = steps[0]
        assert step1["step_number"] == 1
        assert step1["step_type"] == "email"
        assert step1["delay_days"] == 0
        assert step1["delay_hours"] == 0
        assert step1["is_active"] is True
        assert step1["subject_template"] is None
        assert step1["body_template"] is None
        assert step1["campaign_id"] == camp_id


# ── 3. Step Creation Validation & Uniqueness ─────────────────────────────────

@pytest.mark.asyncio
async def test_step_creation_and_validation(test_db_session):
    """Test step creation rules, delays, and validation."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_val@example.com", "Validation Org")
        headers = {"Authorization": f"Bearer {token}"}

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Step Testing", "type": "sales_outbound"},
            headers=headers,
        )).json()
        camp_id = camp["id"]

        # Step 2 valid creation
        s2_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={
                "step_number": 2,
                "step_type": "email",
                "subject_template": "Follow-up #1 for {{company_name}}",
                "body_template": "Hi {{first_name}}, following up...",
                "delay_days": 2,
                "delay_hours": 4,
                "is_active": True,
            },
            headers=headers,
        )
        assert s2_resp.status_code == 201
        s2 = s2_resp.json()
        assert s2["step_number"] == 2
        assert s2["delay_days"] == 2
        assert s2["delay_hours"] == 4

        # Reject duplicate step_number
        dup_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={"step_number": 2, "step_type": "email"},
            headers=headers,
        )
        assert dup_resp.status_code == 409

        # Reject step_number < 1
        inv_num_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={"step_number": 0, "step_type": "email"},
            headers=headers,
        )
        assert inv_num_resp.status_code == 422

        # Reject invalid delay_days < 0
        inv_days_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={"step_number": 3, "step_type": "email", "delay_days": -1},
            headers=headers,
        )
        assert inv_days_resp.status_code == 422

        # Reject invalid delay_hours >= 24
        inv_hours_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={"step_number": 3, "step_type": "email", "delay_hours": 24},
            headers=headers,
        )
        assert inv_hours_resp.status_code == 422

        # Reject unsupported step_type
        inv_type_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={"step_number": 3, "step_type": "linkedin"},
            headers=headers,
        )
        assert inv_type_resp.status_code == 422


# ── 4. Step CRUD Operations & Safety Rules ────────────────────────────────────

@pytest.mark.asyncio
async def test_step_crud_and_safety_rules(test_db_session):
    """Test get, update, delete step and immutability of step_number."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_crud@example.com", "CRUD Org")
        headers = {"Authorization": f"Bearer {token}"}

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "CRUD Campaign", "type": "sales_outbound"},
            headers=headers,
        )).json()
        camp_id = camp["id"]

        # Step 1 was created automatically
        steps = (await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)).json()
        step1_id = steps[0]["id"]

        # Cannot delete the only Step 1
        del_only = await client.delete(f"/api/v1/campaigns/{camp_id}/steps/{step1_id}", headers=headers)
        assert del_only.status_code == 400
        assert "Cannot delete the only Step 1" in del_only.json()["detail"]

        # Update Step 1 content
        patch_resp = await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step1_id}",
            json={
                "subject_template": "Quick question for {{first_name}}",
                "body_template": "Hi {{first_name}},\nI saw {{company_name}}.",
                "delay_days": 1,
                "delay_hours": 2,
            },
            headers=headers,
        )
        assert patch_resp.status_code == 200
        updated_step1 = patch_resp.json()
        assert updated_step1["subject_template"] == "Quick question for {{first_name}}"
        assert updated_step1["delay_days"] == 1
        assert updated_step1["step_number"] == 1  # step_number unchanged

        # Attempt to pass step_number in PATCH (should be ignored by update schema)
        patch_num = await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step1_id}",
            json={"step_number": 5},
            headers=headers,
        )
        assert patch_num.status_code == 200
        assert patch_num.json()["step_number"] == 1

        # Add Step 2
        s2 = (await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={"step_number": 2, "delay_days": 3},
            headers=headers,
        )).json()
        step2_id = s2["id"]

        # Now deleting Step 2 is allowed
        del_s2 = await client.delete(f"/api/v1/campaigns/{camp_id}/steps/{step2_id}", headers=headers)
        assert del_s2.status_code == 204

        # Verify Step 2 is gone
        get_s2 = await client.get(f"/api/v1/campaigns/{camp_id}/steps/{step2_id}", headers=headers)
        assert get_s2.status_code == 404


# ── 5. Campaign Execution Integration With Step 1 Templates ──────────────────

@pytest.mark.asyncio
async def test_campaign_execution_renders_step_1_templates(test_db_session):
    """Execution renders Step 1 templates into Outreach subject and body."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_exec@example.com", "Execution Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create company and contact
        comp = (await client.post("/api/v1/companies", json={"name": "Hooli Tech"}, headers=headers)).json()
        cont = (await client.post(
            "/api/v1/contacts",
            json={
                "email": "richard@hooli.com",
                "first_name": "Richard",
                "last_name": "Hendricks",
                "company_id": comp["id"],
            },
            headers=headers,
        )).json()

        # 2. Create campaign
        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Pied Piper Sequence", "type": "sales_outbound"},
            headers=headers,
        )).json()
        camp_id = camp["id"]

        # 3. Update Step 1 with template variables
        steps = (await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)).json()
        step1_id = steps[0]["id"]
        await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step1_id}",
            json={
                "subject_template": "Partnering with {{company_name}}",
                "body_template": "Hi {{first_name}},\nI would like to introduce {{sender_name}} to {{company_name}}.\nBest,\n{{sender_name}}",
            },
            headers=headers,
        )

        # 4. Enroll contact & activate campaign
        await client.post(f"/api/v1/campaigns/{camp_id}/contacts/{cont['id']}", json={"enrollment_status": "queued"}, headers=headers)
        await client.post(f"/api/v1/campaigns/{camp_id}/activate", headers=headers)

        # 5. Execute campaign with custom sender_name
        exec_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/execute",
            json={"sender_name": "Gavin Belson"},
            headers=headers,
        )
        assert exec_resp.status_code == 200
        exec_data = exec_resp.json()
        assert exec_data["eligible_count"] == 1
        assert exec_data["created_count"] == 1
        outreach_id = exec_data["created_outreach_ids"][0]

        # 6. Verify Outreach fields in database
        outreach = (await client.get(f"/api/v1/outreach/{outreach_id}", headers=headers)).json()
        assert outreach["status"] == "draft"
        assert outreach["channel"] == "email"
        assert outreach["subject"] == "Partnering with Hooli Tech"
        assert outreach["body"] == "Hi Richard,\nI would like to introduce Gavin Belson to Hooli Tech.\nBest,\nGavin Belson"

        # 7. Verify CampaignContact enrollment updated
        enrollments = (await client.get(f"/api/v1/campaigns/{camp_id}/contacts", headers=headers)).json()
        assert enrollments[0]["enrollment_status"] == "in_progress"
        assert enrollments[0]["current_step"] == 1


@pytest.mark.asyncio
async def test_campaign_execution_default_sender_name(test_db_session):
    """When sender_name is not provided, defaults to 'Agile Sales & Marketing'."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_default_sender@example.com", "Sender Org")
        headers = {"Authorization": f"Bearer {token}"}

        cont = (await client.post(
            "/api/v1/contacts",
            json={"email": "erlich@bachman.com", "first_name": "Erlich", "last_name": "Bachman"},
            headers=headers,
        )).json()

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Aviato Sequence", "type": "sales_outbound"},
            headers=headers,
        )).json()
        camp_id = camp["id"]

        steps = (await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)).json()
        step1_id = steps[0]["id"]
        await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step1_id}",
            json={
                "subject_template": "Greetings {{full_name}}",
                "body_template": "From {{sender_name}}",
            },
            headers=headers,
        )

        await client.post(f"/api/v1/campaigns/{camp_id}/contacts/{cont['id']}", json={"enrollment_status": "queued"}, headers=headers)
        await client.post(f"/api/v1/campaigns/{camp_id}/activate", headers=headers)

        # Call execute without body
        exec_resp = await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)
        assert exec_resp.status_code == 200
        outreach_id = exec_resp.json()["created_outreach_ids"][0]

        outreach = (await client.get(f"/api/v1/outreach/{outreach_id}", headers=headers)).json()
        assert outreach["subject"] == "Greetings Erlich Bachman"
        assert outreach["body"] == "From Agile Sales & Marketing"


# ── 6. Campaign Execution Preview With Step 1 Rendered Content ────────────────

@pytest.mark.asyncio
async def test_campaign_execution_preview_renders_step_1_without_mutations(test_db_session):
    """Preview renders templates into preview_items and creates zero records."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_prev@example.com", "Preview Org")
        headers = {"Authorization": f"Bearer {token}"}

        comp = (await client.post("/api/v1/companies", json={"name": "Initech"}, headers=headers)).json()
        cont = (await client.post(
            "/api/v1/contacts",
            json={"email": "peter@initech.com", "first_name": "Peter", "last_name": "Gibbons", "company_id": comp["id"]},
            headers=headers,
        )).json()

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "TPS Report Sequence", "type": "sales_outbound"},
            headers=headers,
        )).json()
        camp_id = camp["id"]

        steps = (await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)).json()
        step1_id = steps[0]["id"]
        await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step1_id}",
            json={
                "subject_template": "TPS update for {{company_name}}",
                "body_template": "Hi {{first_name}}, meet {{sender_name}}.",
            },
            headers=headers,
        )

        enr = (await client.post(f"/api/v1/campaigns/{camp_id}/contacts/{cont['id']}", json={"enrollment_status": "queued"}, headers=headers)).json()
        await client.post(f"/api/v1/campaigns/{camp_id}/activate", headers=headers)

        # Preview execution
        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/execute/preview",
            json={"sender_name": "Bill Lumbergh"},
            headers=headers,
        )
        assert prev_resp.status_code == 200
        prev_data = prev_resp.json()
        assert prev_data["eligible_count"] == 1
        assert len(prev_data["preview_items"]) == 1

        item = prev_data["preview_items"][0]
        assert item["campaign_contact_id"] == enr["id"]
        assert item["contact_id"] == cont["id"]
        assert item["step_number"] == 1
        assert item["subject"] == "TPS update for Initech"
        assert item["body"] == "Hi Peter, meet Bill Lumbergh."

        # Verify zero Outreach rows created
        outreaches = (await client.get("/api/v1/outreach", headers=headers)).json()
        assert len(outreaches) == 0

        # Verify CampaignContact was NOT mutated
        enr_after = (await client.get(f"/api/v1/campaigns/{camp_id}/contacts", headers=headers)).json()
        assert enr_after[0]["enrollment_status"] == "queued"
        assert enr_after[0]["current_step"] == 0


# ── 7. Missing Step 1 Handling ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_execution_handles_missing_or_inactive_step_1(test_db_session):
    """When Step 1 is inactive or missing, contacts are safely skipped without error."""
    async with make_client() as client:
        token = await register_tenant(client, "step9_missing@example.com", "Missing Step Org")
        headers = {"Authorization": f"Bearer {token}"}

        cont = (await client.post(
            "/api/v1/contacts",
            json={"email": "lead@example.com", "first_name": "Lead", "last_name": "User"},
            headers=headers,
        )).json()

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "No Step 1 Campaign", "type": "sales_outbound"},
            headers=headers,
        )).json()
        camp_id = camp["id"]

        steps = (await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)).json()
        step1_id = steps[0]["id"]

        # Deactivate Step 1
        await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step1_id}",
            json={"is_active": False},
            headers=headers,
        )

        await client.post(f"/api/v1/campaigns/{camp_id}/contacts/{cont['id']}", json={"enrollment_status": "queued"}, headers=headers)
        await client.post(f"/api/v1/campaigns/{camp_id}/activate", headers=headers)

        # Preview should have 0 eligible and 0 preview items
        prev = (await client.post(f"/api/v1/campaigns/{camp_id}/execute/preview", headers=headers)).json()
        assert prev["eligible_count"] == 0
        assert prev["skipped_count"] == 1
        assert len(prev["preview_items"]) == 0

        # Execute should create 0 outreaches and skip contact
        exec_data = (await client.post(f"/api/v1/campaigns/{camp_id}/execute", headers=headers)).json()
        assert exec_data["eligible_count"] == 0
        assert exec_data["created_count"] == 0
        assert exec_data["skipped_count"] == 1
        assert len(exec_data["created_outreach_ids"]) == 0


# ── 8. Tenant Isolation ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_steps_strict_tenant_isolation(test_db_session):
    """Tenant B cannot view, create, edit, or delete steps of Tenant A's campaign."""
    async with make_client() as client:
        token_a = await register_tenant(client, "tenant_a_step9@example.com", "Tenant A Org")
        token_b = await register_tenant(client, "tenant_b_step9@example.com", "Tenant B Org")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A creates campaign
        camp_a = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Tenant A Sequence", "type": "sales_outbound"},
            headers=headers_a,
        )).json()
        camp_a_id = camp_a["id"]

        steps_a = (await client.get(f"/api/v1/campaigns/{camp_a_id}/steps", headers=headers_a)).json()
        step_a1_id = steps_a[0]["id"]

        # Tenant B tries to list steps of Tenant A's campaign -> 404
        r_list = await client.get(f"/api/v1/campaigns/{camp_a_id}/steps", headers=headers_b)
        assert r_list.status_code == 404

        # Tenant B tries to get Tenant A's step -> 404
        r_get = await client.get(f"/api/v1/campaigns/{camp_a_id}/steps/{step_a1_id}", headers=headers_b)
        assert r_get.status_code == 404

        # Tenant B tries to create step on Tenant A's campaign -> 404
        r_create = await client.post(
            f"/api/v1/campaigns/{camp_a_id}/steps",
            json={"step_number": 2},
            headers=headers_b,
        )
        assert r_create.status_code == 404

        # Tenant B tries to patch Tenant A's step -> 404
        r_patch = await client.patch(
            f"/api/v1/campaigns/{camp_a_id}/steps/{step_a1_id}",
            json={"subject_template": "Hacked"},
            headers=headers_b,
        )
        assert r_patch.status_code == 404

        # Tenant B tries to delete Tenant A's step -> 404
        r_delete = await client.delete(
            f"/api/v1/campaigns/{camp_a_id}/steps/{step_a1_id}",
            headers=headers_b,
        )
        assert r_delete.status_code == 404
