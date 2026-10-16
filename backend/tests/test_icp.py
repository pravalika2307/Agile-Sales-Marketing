"""Integration and unit tests for Step 11: Ideal Customer Profile (ICP)."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.icp import IdealCustomerProfile


@pytest.fixture
def test_db_session():
    """Create isolated in-memory SQLite DB session for each test."""
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
            "password": "SecurePassword123!",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_create_icp_success(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "icp_owner@test.com", "ICP Org 1")
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "B2B Mid-Market SaaS ICP",
            "description": "Targeting sales leadership at mid-market tech companies",
            "industries": ["Software", "Technology"],
            "company_size_min": 50,
            "company_size_max": 500,
            "countries": ["United States", "Canada"],
            "cities": ["Austin", "San Francisco"],
            "company_domains": ["example.com"],
            "job_titles": ["VP of Sales", "Head of Growth"],
            "seniority_levels": ["VP", "Director"],
            "departments": ["Sales", "Revenue"],
            "technologies": ["Salesforce", "HubSpot"],
            "keywords": ["B2B", "Outbound"],
            "is_active": True,
        }

        resp = await client.post("/api/v1/icps", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()

        assert data["name"] == "B2B Mid-Market SaaS ICP"
        assert data["company_size_min"] == 50
        assert data["company_size_max"] == 500
        assert data["industries"] == ["Software", "Technology"]
        assert data["job_titles"] == ["VP of Sales", "Head of Growth"]
        assert data["is_active"] is True
        assert "id" in data
        assert "organization_id" in data


@pytest.mark.asyncio
async def test_icp_validation_company_size(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "val_owner@test.com", "Validation Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Negative min size
        resp = await client.post(
            "/api/v1/icps",
            json={"name": "Invalid Min", "company_size_min": -5},
            headers=headers,
        )
        assert resp.status_code == 422

        # Max smaller than min
        resp = await client.post(
            "/api/v1/icps",
            json={"name": "Invalid Range", "company_size_min": 100, "company_size_max": 50},
            headers=headers,
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_and_get_icps(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "list_owner@test.com", "List Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two ICPs (one active, one inactive)
        r1 = await client.post(
            "/api/v1/icps",
            json={"name": "Active ICP", "is_active": True},
            headers=headers,
        )
        assert r1.status_code == 201
        icp1_id = r1.json()["id"]

        r2 = await client.post(
            "/api/v1/icps",
            json={"name": "Inactive ICP", "is_active": False},
            headers=headers,
        )
        assert r2.status_code == 201
        icp2_id = r2.json()["id"]

        # List all
        resp = await client.get("/api/v1/icps", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        assert resp.headers["X-Total-Count"] == "2"

        # List filtered by is_active=true
        resp_active = await client.get("/api/v1/icps?is_active=true", headers=headers)
        assert resp_active.status_code == 200
        items = resp_active.json()
        assert len(items) == 1
        assert items[0]["name"] == "Active ICP"

        # Get single ICP
        resp_single = await client.get(f"/api/v1/icps/{icp1_id}", headers=headers)
        assert resp_single.status_code == 200
        assert resp_single.json()["id"] == icp1_id


@pytest.mark.asyncio
async def test_update_and_delete_icp(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "patch_owner@test.com", "Patch Org")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/icps",
            json={"name": "Original Name", "company_size_min": 10},
            headers=headers,
        )
        icp_id = create_resp.json()["id"]

        # Update
        patch_resp = await client.patch(
            f"/api/v1/icps/{icp_id}",
            json={"name": "Updated Name", "company_size_max": 200, "is_active": False},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["name"] == "Updated Name"
        assert data["company_size_min"] == 10
        assert data["company_size_max"] == 200
        assert data["is_active"] is False

        # Delete
        del_resp = await client.delete(f"/api/v1/icps/{icp_id}", headers=headers)
        assert del_resp.status_code == 204

        # Confirm 404
        get_resp = await client.get(f"/api/v1/icps/{icp_id}", headers=headers)
        assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_icp_tenant_isolation(test_db_session):
    async with make_client() as client:
        token_a = await register_tenant(client, "tenant_a@test.com", "Org A")
        token_b = await register_tenant(client, "tenant_b@test.com", "Org B")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A creates an ICP
        res = await client.post("/api/v1/icps", json={"name": "Org A Secret ICP"}, headers=headers_a)
        assert res.status_code == 201
        icp_id = res.json()["id"]

        # Tenant B tries to get Org A's ICP -> 404
        get_b = await client.get(f"/api/v1/icps/{icp_id}", headers=headers_b)
        assert get_b.status_code == 404

        # Tenant B tries to update Org A's ICP -> 404
        patch_b = await client.patch(
            f"/api/v1/icps/{icp_id}",
            json={"name": "Hacked Name"},
            headers=headers_b,
        )
        assert patch_b.status_code == 404

        # Tenant B tries to delete Org A's ICP -> 404
        del_b = await client.delete(f"/api/v1/icps/{icp_id}", headers=headers_b)
        assert del_b.status_code == 404

        # Org A's ICP still intact
        get_a = await client.get(f"/api/v1/icps/{icp_id}", headers=headers_a)
        assert get_a.status_code == 200
        assert get_a.json()["name"] == "Org A Secret ICP"
