"""Integration tests for Contacts API and Multi-Tenant Isolation."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Contact


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
    """Helper to register a tenant and return their access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Tenant Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201
    return resp.json()["tokens"]["access_token"]


# ── Contact CRUD Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_contact_without_company(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@contactco.com", "Contact Co")
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "email": "alex.smith@prospect.com",
            "first_name": "Alex",
            "last_name": "Smith",
            "phone": "+1-555-0100",
            "job_title": "VP of Engineering",
            "lead_status": "new",
        }
        resp = await client.post("/api/v1/contacts", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alex.smith@prospect.com"
        assert data["first_name"] == "Alex"
        assert data["last_name"] == "Smith"
        assert data["lead_status"] == "new"
        assert data["company_id"] is None
        assert "id" in data
        assert "organization_id" in data

        # Check DB
        contact_id = uuid.UUID(data["id"])
        db_contact = test_db_session.query(Contact).filter(Contact.id == contact_id).first()
        assert db_contact is not None
        assert db_contact.email == "alex.smith@prospect.com"


@pytest.mark.asyncio
async def test_create_contact_linked_to_company(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@linkedco.com", "Linked Co")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create Company
        comp_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Pied Piper", "domain": "piedpiper.com"},
            headers=headers,
        )
        assert comp_resp.status_code == 201
        company_id = comp_resp.json()["id"]

        # 2. Create Contact linked to that Company
        payload = {
            "email": "richard@piedpiper.com",
            "first_name": "Richard",
            "last_name": "Hendricks",
            "company_id": company_id,
            "job_title": "CEO",
            "lead_status": "qualified",
        }
        resp = await client.post("/api/v1/contacts", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["company_id"] == company_id
        assert data["lead_status"] == "qualified"


@pytest.mark.asyncio
async def test_get_contact(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@getcontact.com", "Get Contact Co")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/contacts",
            json={"email": "dinesh@silicon.com", "first_name": "Dinesh", "last_name": "Chugtai"},
            headers=headers,
        )
        contact_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == contact_id
        assert resp.json()["first_name"] == "Dinesh"

        # Non-existent contact
        fake_id = uuid.uuid4()
        not_found = await client.get(f"/api/v1/contacts/{fake_id}", headers=headers)
        assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_list_contacts_and_filtering(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@filtercontacts.com", "Filter Co")
        headers = {"Authorization": f"Bearer {token}"}

        # Create Company
        comp_resp = await client.post("/api/v1/companies", json={"name": "Hooli"}, headers=headers)
        company_id = comp_resp.json()["id"]

        # Create multiple contacts
        await client.post(
            "/api/v1/contacts",
            json={"email": "gavin@hooli.com", "first_name": "Gavin", "last_name": "Belson", "company_id": company_id, "lead_status": "contacted"},
            headers=headers,
        )
        await client.post(
            "/api/v1/contacts",
            json={"email": "monica@raviga.com", "first_name": "Monica", "last_name": "Hall", "lead_status": "replied"},
            headers=headers,
        )
        await client.post(
            "/api/v1/contacts",
            json={"email": "jared@piedpiper.com", "first_name": "Jared", "last_name": "Dunn", "lead_status": "qualified"},
            headers=headers,
        )

        # List all
        resp_all = await client.get("/api/v1/contacts", headers=headers)
        assert resp_all.status_code == 200
        assert len(resp_all.json()) == 3
        assert resp_all.headers["X-Total-Count"] == "3"

        # Search by email/name
        resp_search = await client.get("/api/v1/contacts?search=Gavin", headers=headers)
        assert len(resp_search.json()) == 1
        assert resp_search.json()[0]["email"] == "gavin@hooli.com"

        # Filter by lead_status
        resp_status = await client.get("/api/v1/contacts?lead_status=qualified", headers=headers)
        assert len(resp_status.json()) == 1
        assert resp_status.json()[0]["first_name"] == "Jared"

        # Filter by company_id
        resp_comp = await client.get(f"/api/v1/contacts?company_id={company_id}", headers=headers)
        assert len(resp_comp.json()) == 1
        assert resp_comp.json()[0]["first_name"] == "Gavin"


@pytest.mark.asyncio
async def test_update_contact_and_assign_company_later(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@updatecontact.com", "Update Contact Co")
        headers = {"Authorization": f"Bearer {token}"}

        # Create contact without company
        c_resp = await client.post(
            "/api/v1/contacts",
            json={"email": "gilfoyle@test.com", "first_name": "Bertram", "last_name": "Gilfoyle"},
            headers=headers,
        )
        contact_id = c_resp.json()["id"]
        assert c_resp.json()["company_id"] is None

        # Create company
        comp_resp = await client.post("/api/v1/companies", json={"name": "Security Labs"}, headers=headers)
        company_id = comp_resp.json()["id"]

        # Update contact: assign company and change lead_status
        patch_resp = await client.patch(
            f"/api/v1/contacts/{contact_id}",
            json={"company_id": company_id, "lead_status": "replied", "job_title": "Chief Architect"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["company_id"] == company_id
        assert data["lead_status"] == "replied"
        assert data["job_title"] == "Chief Architect"


@pytest.mark.asyncio
async def test_delete_contact(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@delcontact.com", "Delete Contact Co")
        headers = {"Authorization": f"Bearer {token}"}

        c_resp = await client.post(
            "/api/v1/contacts",
            json={"email": "delete.me@test.com", "first_name": "Temp", "last_name": "User"},
            headers=headers,
        )
        contact_id = c_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/contacts/{contact_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify not found
        get_resp = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
        assert get_resp.status_code == 404


# ── Validation Tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_validation_rules(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@val.com", "Validation Co")
        headers = {"Authorization": f"Bearer {token}"}

        # Invalid email format (must return 422)
        resp_email = await client.post(
            "/api/v1/contacts",
            json={"email": "not-an-email", "first_name": "John", "last_name": "Doe"},
            headers=headers,
        )
        assert resp_email.status_code == 422

        # Invalid lead status (must return 422)
        resp_status = await client.post(
            "/api/v1/contacts",
            json={"email": "valid@email.com", "first_name": "John", "last_name": "Doe", "lead_status": "SUPER_HOT_LEAD"},
            headers=headers,
        )
        assert resp_status.status_code == 422


# ── CRITICAL MULTI-TENANT ISOLATION TESTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_multi_tenant_isolation(test_db_session: Session):
    """
    Organization A must NOT be able to:
    - retrieve Organization B's contact
    - update Organization B's contact
    - delete Organization B's contact
    - link a contact to Organization B's company
    """
    async with make_client() as client:
        token_a = await register_tenant(client, "org_a@contact.com", "Tenant A")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = await register_tenant(client, "org_b@contact.com", "Tenant B")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Org A creates a Company and a Contact
        comp_a = await client.post("/api/v1/companies", json={"name": "Org A Co"}, headers=headers_a)
        comp_a_id = comp_a.json()["id"]

        contact_a = await client.post(
            "/api/v1/contacts",
            json={"email": "target@org-a.com", "first_name": "Target", "last_name": "Alpha", "company_id": comp_a_id},
            headers=headers_a,
        )
        contact_a_id = contact_a.json()["id"]

        # 1. Org B cannot GET Org A's contact (404)
        get_b = await client.get(f"/api/v1/contacts/{contact_a_id}", headers=headers_b)
        assert get_b.status_code == 404

        # 2. Org B cannot PATCH Org A's contact (404)
        patch_b = await client.patch(
            f"/api/v1/contacts/{contact_a_id}",
            json={"first_name": "Hacked"},
            headers=headers_b,
        )
        assert patch_b.status_code == 404

        # 3. Org B cannot DELETE Org A's contact (404)
        del_b = await client.delete(f"/api/v1/contacts/{contact_a_id}", headers=headers_b)
        assert del_b.status_code == 404

        # 4. Org B CANNOT link its contact to Org A's Company (Cross-tenant reference rejected with 404)
        cross_create = await client.post(
            "/api/v1/contacts",
            json={"email": "rogue@org-b.com", "first_name": "Rogue", "last_name": "Agent", "company_id": comp_a_id},
            headers=headers_b,
        )
        assert cross_create.status_code == 404
        assert "not found in the current organization" in cross_create.json()["detail"]

        # 5. Same email in different organizations is allowed (tenant-scoped)
        dup_email_in_b = await client.post(
            "/api/v1/contacts",
            json={"email": "target@org-a.com", "first_name": "Legit", "last_name": "Tenant B Copy"},
            headers=headers_b,
        )
        assert dup_email_in_b.status_code == 201
