"""Integration tests for Deals API, stage movements, status transitions, and multi-tenant isolation."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


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
            "full_name": "Deals Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def get_default_stage_ids(client: AsyncClient, headers: dict) -> list[str]:
    """Helper to fetch stage IDs for default sales pipeline."""
    resp = await client.get("/api/v1/pipelines", headers=headers)
    assert resp.status_code == 200
    return [stage["id"] for stage in resp.json()[0]["stages"]]


# ── Deal CRUD & Association Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_deal_without_optional_associations(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals1@test.com", "Deals Org 1")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        resp = await client.post(
            "/api/v1/deals",
            json={
                "name": "Standalone Deal",
                "amount": "15000.00",
                "pipeline_stage_id": stage_ids[0],
                "expected_close_date": "2026-12-31",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Standalone Deal"
        assert float(data["amount"]) == 15000.00
        assert data["contact_id"] is None
        assert data["company_id"] is None
        assert data["status"] == "open"
        assert data["pipeline_stage_id"] == stage_ids[0]


@pytest.mark.asyncio
async def test_create_deal_with_contact_and_company(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals2@test.com", "Deals Org 2")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        # Create Company
        comp_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Acme Industrial", "domain": "acme.com"},
            headers=headers,
        )
        company_id = comp_resp.json()["id"]

        # Create Contact linked to Company
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "email": "wile@acme.com",
                "first_name": "Wile",
                "last_name": "Coyote",
                "company_id": company_id,
            },
            headers=headers,
        )
        contact_id = cont_resp.json()["id"]

        # Create Deal with only contact
        deal_contact_resp = await client.post(
            "/api/v1/deals",
            json={
                "name": "Contact-Only Deal",
                "amount": "5000.00",
                "pipeline_stage_id": stage_ids[0],
                "contact_id": contact_id,
            },
            headers=headers,
        )
        assert deal_contact_resp.status_code == 201
        assert deal_contact_resp.json()["contact_id"] == contact_id
        assert deal_contact_resp.json()["company_id"] is None

        # Create Deal with only company
        deal_company_resp = await client.post(
            "/api/v1/deals",
            json={
                "name": "Company-Only Deal",
                "amount": "25000.00",
                "pipeline_stage_id": stage_ids[0],
                "company_id": company_id,
            },
            headers=headers,
        )
        assert deal_company_resp.status_code == 201
        assert deal_company_resp.json()["company_id"] == company_id
        assert deal_company_resp.json()["contact_id"] is None

        # Create Deal with both
        deal_both_resp = await client.post(
            "/api/v1/deals",
            json={
                "name": "Full Acme Deal",
                "amount": "75000.00",
                "pipeline_stage_id": stage_ids[1],
                "contact_id": contact_id,
                "company_id": company_id,
            },
            headers=headers,
        )
        assert deal_both_resp.status_code == 201
        deal_both = deal_both_resp.json()
        assert deal_both["contact_id"] == contact_id
        assert deal_both["company_id"] == company_id


@pytest.mark.asyncio
async def test_get_update_and_delete_deal(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals3@test.com", "Deals Org 3")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        create_resp = await client.post(
            "/api/v1/deals",
            json={"name": "Deal to Update", "amount": "10000.00", "pipeline_stage_id": stage_ids[0]},
            headers=headers,
        )
        deal_id = create_resp.json()["id"]

        # Get deal
        get_resp = await client.get(f"/api/v1/deals/{deal_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Deal to Update"

        # Update deal
        patch_resp = await client.patch(
            f"/api/v1/deals/{deal_id}",
            json={"name": "Updated Deal Name", "amount": "12500.50"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Updated Deal Name"
        assert float(patch_resp.json()["amount"]) == 12500.50

        # Delete deal
        del_resp = await client.delete(f"/api/v1/deals/{deal_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify 404
        get_again = await client.get(f"/api/v1/deals/{deal_id}", headers=headers)
        assert get_again.status_code == 404


# ── Stage Movement Tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_move_deal_between_stages_in_same_pipeline(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals4@test.com", "Deals Org 4")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        create_resp = await client.post(
            "/api/v1/deals",
            json={"name": "Moving Deal", "amount": "20000.00", "pipeline_stage_id": stage_ids[0]},
            headers=headers,
        )
        deal_id = create_resp.json()["id"]

        # Move to Qualified (stage_ids[1])
        move_resp = await client.patch(
            f"/api/v1/deals/{deal_id}/stage",
            json={"pipeline_stage_id": stage_ids[1]},
            headers=headers,
        )
        assert move_resp.status_code == 200
        assert move_resp.json()["pipeline_stage_id"] == stage_ids[1]
        # Status should remain open
        assert move_resp.json()["status"] == "open"

        # Move to Proposal (stage_ids[3])
        move_resp2 = await client.patch(
            f"/api/v1/deals/{deal_id}/stage",
            json={"pipeline_stage_id": stage_ids[3]},
            headers=headers,
        )
        assert move_resp2.status_code == 200
        assert move_resp2.json()["pipeline_stage_id"] == stage_ids[3]


@pytest.mark.asyncio
async def test_cross_pipeline_stage_movement_rejected(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals5@test.com", "Deals Org 5")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        # Create deal in default pipeline
        deal_resp = await client.post(
            "/api/v1/deals",
            json={"name": "Pipeline 1 Deal", "amount": "5000.00", "pipeline_stage_id": stage_ids[0]},
            headers=headers,
        )
        deal_id = deal_resp.json()["id"]

        # Create a second pipeline with a stage
        pipe2_resp = await client.post(
            "/api/v1/pipelines",
            json={"name": "Secondary Pipeline"},
            headers=headers,
        )
        pipe2_id = pipe2_resp.json()["id"]

        pipe2_stage_resp = await client.post(
            f"/api/v1/pipelines/{pipe2_id}/stages",
            json={"name": "Other Pipeline Stage", "order_index": 1, "probability_pct": 50},
            headers=headers,
        )
        pipe2_stage_id = pipe2_stage_resp.json()["id"]

        # Moving deal from Pipeline 1 to Pipeline 2 stage should return 400
        move_resp = await client.patch(
            f"/api/v1/deals/{deal_id}/stage",
            json={"pipeline_stage_id": pipe2_stage_id},
            headers=headers,
        )
        assert move_resp.status_code == 400


# ── Deal Status Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_deal_won_and_lost(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals6@test.com", "Deals Org 6")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        deal_resp = await client.post(
            "/api/v1/deals",
            json={"name": "Status Deal", "amount": "30000.00", "pipeline_stage_id": stage_ids[0]},
            headers=headers,
        )
        deal_id = deal_resp.json()["id"]
        assert deal_resp.json()["status"] == "open"

        # Mark Won
        won_resp = await client.patch(
            f"/api/v1/deals/{deal_id}/status",
            json={"status": "won"},
            headers=headers,
        )
        assert won_resp.status_code == 200
        assert won_resp.json()["status"] == "won"

        # Mark Lost
        lost_resp = await client.patch(
            f"/api/v1/deals/{deal_id}/status",
            json={"status": "lost"},
            headers=headers,
        )
        assert lost_resp.status_code == 200
        assert lost_resp.json()["status"] == "lost"

        # Reopen
        open_resp = await client.patch(
            f"/api/v1/deals/{deal_id}/status",
            json={"status": "open"},
            headers=headers,
        )
        assert open_resp.status_code == 200
        assert open_resp.json()["status"] == "open"


# ── Deal Validation Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_validation_rules(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals7@test.com", "Deals Org 7")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        # Negative amount rejected
        neg_resp = await client.post(
            "/api/v1/deals",
            json={"name": "Negative Deal", "amount": "-100.00", "pipeline_stage_id": stage_ids[0]},
            headers=headers,
        )
        assert neg_resp.status_code == 422

        # Invalid status rejected
        bad_status_resp = await client.post(
            "/api/v1/deals",
            json={"name": "Bad Status Deal", "amount": "100.00", "pipeline_stage_id": stage_ids[0], "status": "pending"},
            headers=headers,
        )
        assert bad_status_resp.status_code == 422

        # Empty name rejected
        empty_name_resp = await client.post(
            "/api/v1/deals",
            json={"name": "   ", "amount": "100.00", "pipeline_stage_id": stage_ids[0]},
            headers=headers,
        )
        assert empty_name_resp.status_code == 422


# ── Deal Filtering Tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_filtering_and_search(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "deals8@test.com", "Deals Org 8")
        headers = {"Authorization": f"Bearer {token}"}
        stage_ids = await get_default_stage_ids(client, headers)

        # Create two deals
        await client.post(
            "/api/v1/deals",
            json={"name": "Alpha Cloud Contract", "amount": "50000.00", "pipeline_stage_id": stage_ids[0], "status": "open"},
            headers=headers,
        )
        deal_won = await client.post(
            "/api/v1/deals",
            json={"name": "Beta Security Audit", "amount": "20000.00", "pipeline_stage_id": stage_ids[1], "status": "won"},
            headers=headers,
        )

        # Filter by status: won
        won_list = await client.get("/api/v1/deals?status=won", headers=headers)
        assert won_list.status_code == 200
        assert len(won_list.json()) == 1
        assert won_list.json()[0]["name"] == "Beta Security Audit"
        assert won_list.headers.get("X-Total-Count") == "1"

        # Search by term: "cloud"
        cloud_list = await client.get("/api/v1/deals?search=cloud", headers=headers)
        assert cloud_list.status_code == 200
        assert len(cloud_list.json()) == 1
        assert cloud_list.json()[0]["name"] == "Alpha Cloud Contract"

        # Filter by stage_id
        stage0_list = await client.get(f"/api/v1/deals?pipeline_stage_id={stage_ids[0]}", headers=headers)
        assert stage0_list.status_code == 200
        assert len(stage0_list.json()) == 1
        assert stage0_list.json()[0]["name"] == "Alpha Cloud Contract"


# ── Critical Multi-Tenant Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_deal_isolation(test_db_session):
    async with make_client() as client:
        # Register Org A and Org B
        token_a = await register_tenant(client, "tenant_a@org.com", "Tenant Alpha")
        token_b = await register_tenant(client, "tenant_b@org.com", "Tenant Beta")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        stages_a = await get_default_stage_ids(client, headers_a)
        stages_b = await get_default_stage_ids(client, headers_b)

        # Org B creates a company and contact
        comp_b = (await client.post("/api/v1/companies", json={"name": "Beta Corp"}, headers=headers_b)).json()
        cont_b = (await client.post("/api/v1/contacts", json={"email": "b@beta.com", "first_name": "Bob", "last_name": "Beta"}, headers=headers_b)).json()

        # 1. Org A CANNOT use Org B's pipeline stage (must return 404)
        use_bad_stage = await client.post(
            "/api/v1/deals",
            json={"name": "Unauthorized Stage Deal", "amount": "1000.00", "pipeline_stage_id": stages_b[0]},
            headers=headers_a,
        )
        assert use_bad_stage.status_code == 404

        # 2. Org A CANNOT use Org B's contact (must return 404)
        use_bad_contact = await client.post(
            "/api/v1/deals",
            json={"name": "Unauthorized Contact Deal", "amount": "1000.00", "pipeline_stage_id": stages_a[0], "contact_id": cont_b["id"]},
            headers=headers_a,
        )
        assert use_bad_contact.status_code == 404

        # 3. Org A CANNOT use Org B's company (must return 404)
        use_bad_company = await client.post(
            "/api/v1/deals",
            json={"name": "Unauthorized Company Deal", "amount": "1000.00", "pipeline_stage_id": stages_a[0], "company_id": comp_b["id"]},
            headers=headers_a,
        )
        assert use_bad_company.status_code == 404

        # Create a legitimate deal for Org B
        deal_b = (await client.post(
            "/api/v1/deals",
            json={"name": "Org B Secret Deal", "amount": "99999.00", "pipeline_stage_id": stages_b[0]},
            headers=headers_b,
        )).json()
        deal_b_id = deal_b["id"]

        # 4. Org A CANNOT retrieve Org B's deal (must return 404)
        get_deal_b = await client.get(f"/api/v1/deals/{deal_b_id}", headers=headers_a)
        assert get_deal_b.status_code == 404

        # 5. Org A CANNOT update Org B's deal (must return 404)
        update_deal_b = await client.patch(
            f"/api/v1/deals/{deal_b_id}",
            json={"name": "Hacked Name"},
            headers=headers_a,
        )
        assert update_deal_b.status_code == 404

        # 6. Org A CANNOT move Org B's deal (must return 404)
        move_deal_b = await client.patch(
            f"/api/v1/deals/{deal_b_id}/stage",
            json={"pipeline_stage_id": stages_a[1]},
            headers=headers_a,
        )
        assert move_deal_b.status_code == 404

        # 7. Org A CANNOT delete Org B's deal (must return 404)
        del_deal_b = await client.delete(f"/api/v1/deals/{deal_b_id}", headers=headers_a)
        assert del_deal_b.status_code == 404
