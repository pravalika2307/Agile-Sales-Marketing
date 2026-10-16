"""Comprehensive tests for reusable email templates, CRUD, search/filtering, and tenant isolation."""
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
from app.models.email_template import EmailTemplate
from app.models.tenant import Organization, User
from app.services import email_template_service
from app.schemas.email_template import EmailTemplateCreate, EmailTemplateUpdate


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
            "full_name": "Template Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── 1. Service Level Tests ───────────────────────────────────────────────────

def test_create_and_get_template(test_db_session: Session):
    """Template can be created and retrieved scoped to organization."""
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Acme Org", slug="acme-org")
    test_db_session.add(org)
    test_db_session.commit()

    created = email_template_service.create_template(
        test_db_session,
        org_id,
        EmailTemplateCreate(
            name="Executive Briefing",
            description="High-touch outreach for VP/C-suite",
            category="outbound",
            subject_template="Briefing for {contact.company}",
            body_template="Hi {contact.first_name},\n\nWould you have 10 minutes next week?\n\nBest,\n{sender_name}",
        ),
    )

    assert created.id is not None
    assert created.organization_id == org_id
    assert created.name == "Executive Briefing"
    assert created.category == "outbound"

    retrieved = email_template_service.get_template(test_db_session, org_id, created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.subject_template == "Briefing for {contact.company}"


def test_template_tenant_isolation(test_db_session: Session):
    """Organization B cannot retrieve, update, or delete Organization A's template."""
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    test_db_session.add_all([
        Organization(id=org_a, name="Org A", slug="org-a"),
        Organization(id=org_b, name="Org B", slug="org-b"),
    ])
    test_db_session.commit()

    tmpl_a = email_template_service.create_template(
        test_db_session,
        org_a,
        EmailTemplateCreate(
            name="Org A Secret Sequence",
            subject_template="Subject A",
            body_template="Body A",
        ),
    )

    # Org B attempts to get Org A's template
    assert email_template_service.get_template(test_db_session, org_b, tmpl_a.id) is None

    # Org B attempts to list templates
    b_list, b_total = email_template_service.list_templates(test_db_session, org_b)
    assert b_total == 0
    assert len(b_list) == 0

    # Org B attempts to update Org A's template
    with pytest.raises(email_template_service.EmailTemplateNotFoundError):
        email_template_service.update_template(
            test_db_session,
            org_b,
            tmpl_a.id,
            EmailTemplateUpdate(name="Hacked Name"),
        )

    # Org B attempts to delete Org A's template
    deleted = email_template_service.delete_template(test_db_session, org_b, tmpl_a.id)
    assert not deleted

    # Confirm Org A's template remains intact
    assert email_template_service.get_template(test_db_session, org_a, tmpl_a.id) is not None


def test_template_filtering_and_search(test_db_session: Session):
    """Templates can be searched by keyword and filtered by category."""
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Filter Org", slug="filter-org")
    test_db_session.add(org)
    test_db_session.commit()

    email_template_service.create_template(
        test_db_session,
        org_id,
        EmailTemplateCreate(
            name="Cold Outbound Sequence",
            category="outbound",
            subject_template="Intro to {contact.company}",
            body_template="Hello {contact.first_name}",
        ),
    )
    email_template_service.create_template(
        test_db_session,
        org_id,
        EmailTemplateCreate(
            name="Follow Up Touchpoint",
            category="follow_up",
            subject_template="Following up on our earlier note",
            body_template="Checking in {contact.first_name}",
        ),
    )
    email_template_service.create_template(
        test_db_session,
        org_id,
        EmailTemplateCreate(
            name="Nurture Newsletter",
            category="nurture",
            subject_template="Industry Insights for {contact.company}",
            body_template="Here is the report",
        ),
    )

    # Filter by category
    outbound_list, count = email_template_service.list_templates(test_db_session, org_id, category="outbound")
    assert count == 1
    assert outbound_list[0].name == "Cold Outbound Sequence"

    # Search by keyword in name
    search_list, count = email_template_service.list_templates(test_db_session, org_id, search="follow")
    assert count == 1
    assert search_list[0].name == "Follow Up Touchpoint"

    # Search by keyword in subject
    subject_search, count = email_template_service.list_templates(test_db_session, org_id, search="earlier note")
    assert count == 1
    assert subject_search[0].name == "Follow Up Touchpoint"


# ── 2. API Endpoint Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_template_crud_lifecycle(test_db_session: Session):
    """Full HTTP API lifecycle for templates: Create, List, Get, Update, Delete."""
    async with make_client() as client:
        token = await register_tenant(client, "admin@lifecycle.com", "Lifecycle Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create
        create_resp = await client.post(
            "/api/v1/templates",
            headers=headers,
            json={
                "name": "Q4 Enterprise Demo",
                "description": "Targeting large enterprises",
                "category": "outbound",
                "subject_template": "Executive briefing for {contact.company}",
                "body_template": "Hi {contact.first_name},\n\nBriefing request.\n\nBest,\n{sender_name}",
            },
        )
        assert create_resp.status_code == 201
        created_data = create_resp.json()
        tmpl_id = created_data["id"]
        assert created_data["name"] == "Q4 Enterprise Demo"

        # 2. List
        list_resp = await client.get("/api/v1/templates", headers=headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["id"] == tmpl_id

        # 3. Get
        get_resp = await client.get(f"/api/v1/templates/{tmpl_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["subject_template"] == "Executive briefing for {contact.company}"

        # 4. Update
        update_resp = await client.patch(
            f"/api/v1/templates/{tmpl_id}",
            headers=headers,
            json={
                "name": "Q4 Enterprise Demo (Updated)",
                "subject_template": "Updated subject line",
            },
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Q4 Enterprise Demo (Updated)"
        assert update_resp.json()["subject_template"] == "Updated subject line"

        # 5. Delete
        del_resp = await client.delete(f"/api/v1/templates/{tmpl_id}", headers=headers)
        assert del_resp.status_code == 204

        # 6. Verify 404 after delete
        get_again = await client.get(f"/api/v1/templates/{tmpl_id}", headers=headers)
        assert get_again.status_code == 404


@pytest.mark.asyncio
async def test_api_cross_tenant_template_security(test_db_session: Session):
    """API endpoints enforce strict 404 on cross-tenant template access."""
    async with make_client() as client:
        token_a = await register_tenant(client, "admin@orga.com", "Org Alpha")
        token_b = await register_tenant(client, "admin@orgb.com", "Org Beta")

        # Create in Org Alpha
        create_resp = await client.post(
            "/api/v1/templates",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "name": "Alpha Confidential",
                "subject_template": "Alpha Subject",
                "body_template": "Alpha Body",
            },
        )
        assert create_resp.status_code == 201
        alpha_id = create_resp.json()["id"]

        # Org Beta tries to GET
        b_get = await client.get(
            f"/api/v1/templates/{alpha_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert b_get.status_code == 404

        # Org Beta tries to UPDATE
        b_patch = await client.patch(
            f"/api/v1/templates/{alpha_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"name": "Hacked by Beta"},
        )
        assert b_patch.status_code == 404

        # Org Beta tries to DELETE
        b_del = await client.delete(
            f"/api/v1/templates/{alpha_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert b_del.status_code == 404
