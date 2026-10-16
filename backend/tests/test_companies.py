"""Integration tests for Companies API and Multi-Tenant Isolation."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Company


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


# ── Company CRUD Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_company(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@acme.com", "Acme Corp")
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "Stark Industries",
            "domain": "stark.com",
            "industry": "Aerospace & Defense",
            "employee_count_range": "1000-5000",
            "city": "New York",
            "country": "USA",
        }
        resp = await client.post("/api/v1/companies", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Stark Industries"
        assert data["domain"] == "stark.com"
        assert data["industry"] == "Aerospace & Defense"
        assert "id" in data
        assert "organization_id" in data

        # Check DB persistence
        company_id = uuid.UUID(data["id"])
        db_company = test_db_session.query(Company).filter(Company.id == company_id).first()
        assert db_company is not None
        assert db_company.name == "Stark Industries"


@pytest.mark.asyncio
async def test_get_company(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@wayne.com", "Wayne Enterprises")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Gotham Steel", "city": "Gotham"},
            headers=headers,
        )
        company_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/companies/{company_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == company_id
        assert resp.json()["name"] == "Gotham Steel"

        # Non-existent ID returns 404
        fake_id = uuid.uuid4()
        not_found_resp = await client.get(f"/api/v1/companies/{fake_id}", headers=headers)
        assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_companies_and_filtering(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@listco.com", "List Co")
        headers = {"Authorization": f"Bearer {token}"}

        # Create multiple companies
        await client.post("/api/v1/companies", json={"name": "Alpha Tech", "industry": "Software"}, headers=headers)
        await client.post("/api/v1/companies", json={"name": "Beta Health", "industry": "Healthcare"}, headers=headers)
        await client.post("/api/v1/companies", json={"name": "Alpha Finance", "industry": "Banking"}, headers=headers)

        # List all
        resp_all = await client.get("/api/v1/companies", headers=headers)
        assert resp_all.status_code == 200
        assert len(resp_all.json()) == 3
        assert resp_all.headers["X-Total-Count"] == "3"

        # Search by name
        resp_search = await client.get("/api/v1/companies?search=Alpha", headers=headers)
        assert len(resp_search.json()) == 2
        for c in resp_search.json():
            assert "Alpha" in c["name"]

        # Filter by industry
        resp_ind = await client.get("/api/v1/companies?industry=Health", headers=headers)
        assert len(resp_ind.json()) == 1
        assert resp_ind.json()[0]["name"] == "Beta Health"

        # Pagination: skip=1, limit=1
        resp_paged = await client.get("/api/v1/companies?skip=1&limit=1", headers=headers)
        assert len(resp_paged.json()) == 1


@pytest.mark.asyncio
async def test_update_company(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@updateco.com", "Update Co")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Old Name", "industry": "Old Industry"},
            headers=headers,
        )
        company_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/companies/{company_id}",
            json={"name": "New Name", "city": "San Francisco"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["name"] == "New Name"
        assert data["industry"] == "Old Industry"
        assert data["city"] == "San Francisco"


@pytest.mark.asyncio
async def test_delete_company(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin@deleteco.com", "Delete Co")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/companies",
            json={"name": "To Be Deleted"},
            headers=headers,
        )
        company_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/companies/{company_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify not found after deletion
        get_resp = await client.get(f"/api/v1/companies/{company_id}", headers=headers)
        assert get_resp.status_code == 404


# ── CRITICAL MULTI-TENANT ISOLATION TESTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_company_multi_tenant_isolation(test_db_session: Session):
    """
    Organization A must NOT be able to:
    - retrieve Organization B's company
    - update Organization B's company
    - delete Organization B's company
    - see Organization B's company in list queries
    """
    async with make_client() as client:
        # Register Organization A
        token_a = await register_tenant(client, "org_a@test.com", "Tenant A")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Register Organization B
        token_b = await register_tenant(client, "org_b@test.com", "Tenant B")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Org A creates Company A
        create_a_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Org A Secret Corp", "domain": "sec-a.com"},
            headers=headers_a,
        )
        company_a_id = create_a_resp.json()["id"]

        # 1. Org B cannot GET Org A's company (must return 404)
        get_b_resp = await client.get(f"/api/v1/companies/{company_a_id}", headers=headers_b)
        assert get_b_resp.status_code == 404

        # 2. Org B cannot PATCH Org A's company (must return 404)
        patch_b_resp = await client.patch(
            f"/api/v1/companies/{company_a_id}",
            json={"name": "Hacked Name"},
            headers=headers_b,
        )
        assert patch_b_resp.status_code == 404

        # 3. Org B cannot DELETE Org A's company (must return 404)
        del_b_resp = await client.delete(f"/api/v1/companies/{company_a_id}", headers=headers_b)
        assert del_b_resp.status_code == 404

        # 4. Org B does NOT see Org A's company in list
        list_b_resp = await client.get("/api/v1/companies", headers=headers_b)
        assert list_b_resp.status_code == 200
        assert len(list_b_resp.json()) == 0

        # Verify Org A's company remains intact and uncompromised
        check_a_resp = await client.get(f"/api/v1/companies/{company_a_id}", headers=headers_a)
        assert check_a_resp.status_code == 200
        assert check_a_resp.json()["name"] == "Org A Secret Corp"
