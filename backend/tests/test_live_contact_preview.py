"""
Focused tests for Live Contact Preview in Campaign Workflow Builder.
Covers:
- Default preview uses campaign-enrolled contact over generic tenant contacts
- Selecting a specific CRM contact renders their genuine data
- Switching between contacts dynamically updates preview
- Full variable resolution: {contact.first_name}, {contact.last_name}, {contact.company}, {sender.company_name}
- Missing company association handled safely with fallback
- Cross-tenant contact access rejection (strict multi-tenant isolation)
- Read-only preview behavior: zero outreaches created, zero enrollments modified
- Explicit synthetic sample contact option
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Company, Contact
from app.models.outreach import Outreach


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
            "full_name": "Preview Tester",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_default_preview_prioritizes_campaign_enrolled_contact(test_db_session):
    """
    When no contact_id is specified, preview must prioritize contacts enrolled in the campaign,
    rather than simply returning the newest contact in the entire organization.
    """
    async with make_client() as client:
        token = await register_tenant(client, "org_preview@test.com", "Preview Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create Company
        comp_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Agile Receivables", "domain": "agilereceivables.com"},
            headers=headers,
        )
        comp_id = comp_resp.json()["id"]

        # Create Contact 1 (Enrolled Contact, e.g. Pravalika Palle)
        cont1_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Pravalika",
                "last_name": "Palle",
                "email": "pravalika@agilereceivables.com",
                "company_id": comp_id,
            },
            headers=headers,
        )
        cont1_id = cont1_resp.json()["id"]

        # Create Contact 2 (Newer contact, NOT enrolled in campaign, e.g. Kunal Sadhre)
        cont2_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Kunal",
                "last_name": "Sadhre",
                "email": "kunal@example.com",
                "company_id": None,
            },
            headers=headers,
        )
        cont2_id = cont2_resp.json()["id"]

        # Create Campaign "Test Sales"
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Test Sales", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        # Enroll only Contact 1 (Pravalika Palle)
        enroll_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/contacts/bulk",
            json={"contact_ids": [cont1_id]},
            headers=headers,
        )
        assert enroll_resp.status_code == 200

        # Request Live Contact Preview without passing contact_id (default behavior)
        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/workflow/preview-template",
            json={
                "subject_template": "Quick intro for {contact.first_name}",
                "body_template": "Hi {contact.first_name} {contact.last_name} from {contact.company}.",
                "sender_company_name": "Agile Sales & Marketing",
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()

        # The default preview MUST be Pravalika Palle (the enrolled contact), NOT Kunal Sadhre
        assert preview["contact_used"]["id"] == cont1_id
        assert preview["contact_used"]["first_name"] == "Pravalika"
        assert preview["contact_used"]["last_name"] == "Palle"
        assert preview["contact_used"]["company_name"] == "Agile Receivables"
        assert preview["is_sample"] is False
        assert "Hi Pravalika Palle from Agile Receivables." in preview["rendered_body"]


@pytest.mark.asyncio
async def test_selecting_different_crm_contact_and_switching(test_db_session):
    """
    Selecting different contacts via contact_id updates the preview dynamically.
    """
    async with make_client() as client:
        token = await register_tenant(client, "switching@test.com", "Switching Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Company 1 and Contact 1
        c1 = (await client.post("/api/v1/companies", json={"name": "Alpha Corp"}, headers=headers)).json()
        cont1 = (await client.post("/api/v1/contacts", json={
            "first_name": "Alice", "last_name": "Adams", "email": "alice@alpha.com", "company_id": c1["id"]
        }, headers=headers)).json()

        # Company 2 and Contact 2
        c2 = (await client.post("/api/v1/companies", json={"name": "Beta LLC"}, headers=headers)).json()
        cont2 = (await client.post("/api/v1/contacts", json={
            "first_name": "Bob", "last_name": "Baker", "email": "bob@beta.com", "company_id": c2["id"]
        }, headers=headers)).json()

        camp = (await client.post("/api/v1/campaigns", json={"name": "Outreach", "type": "sales_outbound"}, headers=headers)).json()

        # 1. Preview for Alice
        prev_a = await client.post(
            f"/api/v1/campaigns/{camp['id']}/workflow/preview-template",
            json={
                "subject_template": "For {contact.first_name}",
                "body_template": "Meeting with {contact.company}",
                "contact_id": cont1["id"],
            },
            headers=headers,
        )
        assert prev_a.status_code == 200
        data_a = prev_a.json()
        assert data_a["contact_used"]["first_name"] == "Alice"
        assert data_a["rendered_body"] == "Meeting with Alpha Corp"

        # 2. Switch to Bob
        prev_b = await client.post(
            f"/api/v1/campaigns/{camp['id']}/workflow/preview-template",
            json={
                "subject_template": "For {contact.first_name}",
                "body_template": "Meeting with {contact.company}",
                "contact_id": cont2["id"],
            },
            headers=headers,
        )
        assert prev_b.status_code == 200
        data_b = prev_b.json()
        assert data_b["contact_used"]["first_name"] == "Bob"
        assert data_b["rendered_body"] == "Meeting with Beta LLC"


@pytest.mark.asyncio
async def test_full_variable_rendering_including_sender_company_name(test_db_session):
    """
    Renders {contact.first_name}, {contact.last_name}, {contact.company},
    and {sender.company_name} (dot notation).
    """
    async with make_client() as client:
        token = await register_tenant(client, "vars@test.com", "Vars Org")
        headers = {"Authorization": f"Bearer {token}"}

        comp = (await client.post("/api/v1/companies", json={"name": "Starlight Industries"}, headers=headers)).json()
        cont = (await client.post("/api/v1/contacts", json={
            "first_name": "David", "last_name": "Miller", "email": "david@starlight.com", "company_id": comp["id"]
        }, headers=headers)).json()
        camp = (await client.post("/api/v1/campaigns", json={"name": "Vars Camp", "type": "sales_outbound"}, headers=headers)).json()

        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp['id']}/workflow/preview-template",
            json={
                "subject_template": "Intro for {contact.company}",
                "body_template": "Dear {contact.first_name} {contact.last_name},\n\nWe would love to partner with {contact.company}.\nBest regards,\n{sender.company_name}",
                "contact_id": cont["id"],
                "sender_company_name": "Agile Sales & Marketing",
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()
        assert preview["rendered_subject"] == "Intro for Starlight Industries"
        assert "Dear David Miller," in preview["rendered_body"]
        assert "partner with Starlight Industries." in preview["rendered_body"]
        assert "Best regards,\nAgile Sales & Marketing" in preview["rendered_body"]
        assert len(preview["unresolved_placeholders"]) == 0


@pytest.mark.asyncio
async def test_missing_company_association_handled_safely(test_db_session):
    """
    When a contact has no company associated (company_id is None):
    - Template renders safe fallback for company.
    - preview.contact_used.company_name is None.
    - Safe fallback warning is listed.
    - No 500 error is thrown.
    """
    async with make_client() as client:
        token = await register_tenant(client, "nocomp@test.com", "NoComp Org")
        headers = {"Authorization": f"Bearer {token}"}

        cont = (await client.post("/api/v1/contacts", json={
            "first_name": "Independent", "last_name": "Consultant", "email": "indie@freelance.org", "company_id": None
        }, headers=headers)).json()
        camp = (await client.post("/api/v1/campaigns", json={"name": "Freelance Camp", "type": "sales_outbound"}, headers=headers)).json()

        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp['id']}/workflow/preview-template",
            json={
                "subject_template": "Hello {contact.first_name}",
                "body_template": "Hope things are well at {contact.company}.",
                "contact_id": cont["id"],
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()
        assert preview["contact_used"]["company_name"] is None
        # Contextual fallback cleanly omits " at {contact.company}" to avoid awkward phrasing
        assert preview["rendered_body"] == "Hope things are well."
        assert any("company" in f.lower() for f in preview["safe_fallbacks_applied"])


@pytest.mark.asyncio
async def test_cross_tenant_contact_access_rejected(test_db_session):
    """
    Attempting to preview with a contact ID from a different tenant:
    - Does NOT return the foreign tenant's contact data.
    - Reports a validation error and falls back to sample data (is_sample=True).
    - Preserves multi-tenant isolation.
    """
    async with make_client() as client:
        # Tenant 1
        t1_token = await register_tenant(client, "tenant1@test.com", "Tenant One")
        t1_headers = {"Authorization": f"Bearer {t1_token}"}
        t1_contact = (await client.post("/api/v1/contacts", json={
            "first_name": "Secret", "last_name": "Agent", "email": "secret@t1.com"
        }, headers=t1_headers)).json()

        # Tenant 2
        t2_token = await register_tenant(client, "tenant2@test.com", "Tenant Two")
        t2_headers = {"Authorization": f"Bearer {t2_token}"}
        t2_camp = (await client.post("/api/v1/campaigns", json={
            "name": "Tenant 2 Camp", "type": "sales_outbound"
        }, headers=t2_headers)).json()

        # Tenant 2 tries to use Tenant 1's contact ID
        prev_resp = await client.post(
            f"/api/v1/campaigns/{t2_camp['id']}/workflow/preview-template",
            json={
                "subject_template": "Hello {contact.first_name}",
                "body_template": "Body {contact.first_name}",
                "contact_id": t1_contact["id"],
            },
            headers=t2_headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()

        # Tenant 1's secret contact data must NEVER be leaked
        assert preview["contact_used"]["first_name"] != "Secret"
        assert preview["contact_used"]["email"] != "secret@t1.com"
        # Must report validation error and flag sample
        assert any("not found in authenticated organization" in err for err in preview["validation_errors"])
        assert preview["is_sample"] is True


@pytest.mark.asyncio
async def test_previewing_never_sends_email_or_modifies_enrollment(test_db_session):
    """
    Preview is strictly a read-only operation:
    - Never inserts an Outreach record.
    - Never creates or changes CampaignContact enrollment records.
    """
    async with make_client() as client:
        token = await register_tenant(client, "readonly@test.com", "ReadOnly Org")
        headers = {"Authorization": f"Bearer {token}"}

        cont = (await client.post("/api/v1/contacts", json={
            "first_name": "Sam", "last_name": "Sample", "email": "sam@test.com"
        }, headers=headers)).json()
        camp = (await client.post("/api/v1/campaigns", json={"name": "Safe Camp", "type": "sales_outbound"}, headers=headers)).json()

        initial_outreaches = test_db_session.query(Outreach).count()
        initial_enrollments = test_db_session.query(CampaignContact).count()

        # Perform 5 preview requests
        for _ in range(5):
            res = await client.post(
                f"/api/v1/campaigns/{camp['id']}/workflow/preview-template",
                json={
                    "subject_template": "Subject {contact.first_name}",
                    "body_template": "Body {contact.last_name}",
                    "contact_id": cont["id"],
                },
                headers=headers,
            )
            assert res.status_code == 200

        final_outreaches = test_db_session.query(Outreach).count()
        final_enrollments = test_db_session.query(CampaignContact).count()

        assert final_outreaches == initial_outreaches == 0
        assert final_enrollments == initial_enrollments == 0


@pytest.mark.asyncio
async def test_explicit_sample_contact_selection(test_db_session):
    """
    When use_sample is True, preview explicitly returns the synthetic sample contact
    and sets is_sample to True.
    """
    async with make_client() as client:
        token = await register_tenant(client, "sample_user@test.com", "Sample Org")
        headers = {"Authorization": f"Bearer {token}"}

        camp = (await client.post("/api/v1/campaigns", json={"name": "Sample Camp", "type": "sales_outbound"}, headers=headers)).json()

        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp['id']}/workflow/preview-template",
            json={
                "subject_template": "For {contact.first_name}",
                "body_template": "Hi {contact.first_name} at {contact.company}.",
                "use_sample": True,
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()
        assert preview["is_sample"] is True
        assert preview["contact_used"]["first_name"] == "Jordan"
        assert preview["contact_used"]["last_name"] == "Taylor"
        assert preview["contact_used"]["company_name"] == "Acme Global Solutions"
        assert "Hi Jordan at Acme Global Solutions." in preview["rendered_body"]
