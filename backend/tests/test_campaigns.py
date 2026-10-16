"""Integration tests for Campaigns API, lifecycle state transitions, enrollment, and tenant isolation."""
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
            "full_name": "Campaign Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def create_test_contact(client: AsyncClient, headers: dict, email: str = "prospect@example.com") -> str:
    """Helper to create a contact and return contact ID."""
    resp = await client.post(
        "/api/v1/contacts",
        json={
            "email": email,
            "first_name": "Test",
            "last_name": "Prospect",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Campaign CRUD & Validation Tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_campaign_starts_as_draft(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp1@test.com", "Camp Org 1")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/campaigns",
            json={
                "name": "Q4 Outbound Outreach",
                "type": "sales_outbound",
                "schedule_settings": {"timezone": "UTC", "days": ["mon", "tue", "wed"]},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Q4 Outbound Outreach"
        assert data["type"] == "sales_outbound"
        assert data["status"] == "draft"  # Must always start as draft
        assert data["schedule_settings"]["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_campaign_types_validation(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp2@test.com", "Camp Org 2")
        headers = {"Authorization": f"Bearer {token}"}

        # Valid types: marketing_social, hybrid
        c1 = await client.post(
            "/api/v1/campaigns",
            json={"name": "Social Promo", "type": "marketing_social"},
            headers=headers,
        )
        assert c1.status_code == 201
        assert c1.json()["type"] == "marketing_social"

        c2 = await client.post(
            "/api/v1/campaigns",
            json={"name": "Multi-Channel Push", "type": "hybrid"},
            headers=headers,
        )
        assert c2.status_code == 201
        assert c2.json()["type"] == "hybrid"

        # Invalid type rejected
        bad = await client.post(
            "/api/v1/campaigns",
            json={"name": "Invalid Campaign", "type": "radio_broadcast"},
            headers=headers,
        )
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_get_update_and_delete_campaign(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp3@test.com", "Camp Org 3")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Original Name", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = create_resp.json()["id"]

        # Get
        get_resp = await client.get(f"/api/v1/campaigns/{camp_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Original Name"

        # Update
        patch_resp = await client.patch(
            f"/api/v1/campaigns/{camp_id}",
            json={"name": "Renamed Campaign"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Renamed Campaign"

        # Delete
        del_resp = await client.delete(f"/api/v1/campaigns/{camp_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify 404
        get_again = await client.get(f"/api/v1/campaigns/{camp_id}", headers=headers)
        assert get_again.status_code == 404


@pytest.mark.asyncio
async def test_list_campaigns_and_filtering(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp4@test.com", "Camp Org 4")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two campaigns
        c1 = (await client.post(
            "/api/v1/campaigns",
            json={"name": "SaaS Leaders Email", "type": "sales_outbound"},
            headers=headers,
        )).json()

        c2 = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Brand Awareness Push", "type": "marketing_social"},
            headers=headers,
        )).json()

        # Activate c1
        await client.post(f"/api/v1/campaigns/{c1['id']}/activate", headers=headers)

        # Filter by status=active
        active_resp = await client.get("/api/v1/campaigns?status=active", headers=headers)
        assert active_resp.status_code == 200
        assert len(active_resp.json()) == 1
        assert active_resp.json()[0]["name"] == "SaaS Leaders Email"
        assert active_resp.headers.get("X-Total-Count") == "1"

        # Filter by type=marketing_social
        type_resp = await client.get("/api/v1/campaigns?type=marketing_social", headers=headers)
        assert type_resp.status_code == 200
        assert len(type_resp.json()) == 1
        assert type_resp.json()[0]["name"] == "Brand Awareness Push"

        # Search by name term
        search_resp = await client.get("/api/v1/campaigns?search=leaders", headers=headers)
        assert search_resp.status_code == 200
        assert len(search_resp.json()) == 1
        assert search_resp.json()[0]["id"] == c1["id"]


# ── Campaign Lifecycle Transitions ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_lifecycle_state_machine(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp5@test.com", "Camp Org 5")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Start as draft
        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Lifecycle Campaign", "type": "sales_outbound"},
            headers=headers,
        )).json()
        cid = camp["id"]
        assert camp["status"] == "draft"

        # Illegal: cannot pause a draft
        bad_pause = await client.post(f"/api/v1/campaigns/{cid}/pause", headers=headers)
        assert bad_pause.status_code == 400

        # Illegal: cannot complete a draft
        bad_complete = await client.post(f"/api/v1/campaigns/{cid}/complete", headers=headers)
        assert bad_complete.status_code == 400

        # 2. draft -> active
        act_resp = await client.post(f"/api/v1/campaigns/{cid}/activate", headers=headers)
        assert act_resp.status_code == 200
        assert act_resp.json()["status"] == "active"

        # 3. active -> paused
        pause_resp = await client.post(f"/api/v1/campaigns/{cid}/pause", headers=headers)
        assert pause_resp.status_code == 200
        assert pause_resp.json()["status"] == "paused"

        # 4. paused -> active
        resume_resp = await client.post(f"/api/v1/campaigns/{cid}/activate", headers=headers)
        assert resume_resp.status_code == 200
        assert resume_resp.json()["status"] == "active"

        # 5. active -> completed
        comp_resp = await client.post(f"/api/v1/campaigns/{cid}/complete", headers=headers)
        assert comp_resp.status_code == 200
        assert comp_resp.json()["status"] == "completed"

        # 6. completed cannot transition anymore
        reactivate = await client.post(f"/api/v1/campaigns/{cid}/activate", headers=headers)
        assert reactivate.status_code == 400

        repause = await client.post(f"/api/v1/campaigns/{cid}/pause", headers=headers)
        assert repause.status_code == 400


@pytest.mark.asyncio
async def test_campaign_pause_to_complete(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp5b@test.com", "Camp Org 5B")
        headers = {"Authorization": f"Bearer {token}"}

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Pause to Complete", "type": "sales_outbound"},
            headers=headers,
        )).json()
        cid = camp["id"]

        # draft -> active -> paused -> completed
        await client.post(f"/api/v1/campaigns/{cid}/activate", headers=headers)
        await client.post(f"/api/v1/campaigns/{cid}/pause", headers=headers)
        comp_resp = await client.post(f"/api/v1/campaigns/{cid}/complete", headers=headers)
        assert comp_resp.status_code == 200
        assert comp_resp.json()["status"] == "completed"


# ── Contact Enrollment Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enroll_and_remove_contact(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp6@test.com", "Camp Org 6")
        headers = {"Authorization": f"Bearer {token}"}

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Enrollment Flow", "type": "sales_outbound"},
            headers=headers,
        )).json()
        cid = camp["id"]

        contact_id = await create_test_contact(client, headers, "john@example.com")

        # Enroll contact
        enroll_resp = await client.post(
            f"/api/v1/campaigns/{cid}/contacts/{contact_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )
        assert enroll_resp.status_code == 201
        enroll_data = enroll_resp.json()
        assert enroll_data["campaign_id"] == cid
        assert enroll_data["contact_id"] == contact_id
        assert enroll_data["enrollment_status"] == "queued"
        assert enroll_data["current_step"] == 0

        # Duplicate enrollment should return 409
        dup_resp = await client.post(
            f"/api/v1/campaigns/{cid}/contacts/{contact_id}",
            headers=headers,
        )
        assert dup_resp.status_code == 409

        # List enrolled contacts
        list_resp = await client.get(f"/api/v1/campaigns/{cid}/contacts", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.headers.get("X-Total-Count") == "1"

        # Update enrollment status
        status_patch = await client.patch(
            f"/api/v1/campaigns/{cid}/contacts/{contact_id}/status",
            json={"enrollment_status": "in_progress"},
            headers=headers,
        )
        assert status_patch.status_code == 200
        assert status_patch.json()["enrollment_status"] == "in_progress"

        # Remove enrollment
        del_resp = await client.delete(f"/api/v1/campaigns/{cid}/contacts/{contact_id}", headers=headers)
        assert del_resp.status_code == 204

        # List should now be empty
        list_after = await client.get(f"/api/v1/campaigns/{cid}/contacts", headers=headers)
        assert len(list_after.json()) == 0


# ── Bulk Enrollment Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_enrollment(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "camp7@test.com", "Camp Org 7")
        headers = {"Authorization": f"Bearer {token}"}

        camp = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Bulk Campaign", "type": "sales_outbound"},
            headers=headers,
        )).json()
        cid = camp["id"]

        c1 = await create_test_contact(client, headers, "c1@test.com")
        c2 = await create_test_contact(client, headers, "c2@test.com")
        c3 = await create_test_contact(client, headers, "c3@test.com")
        fake_id = str(uuid.uuid4())

        # Pre-enroll c1
        await client.post(f"/api/v1/campaigns/{cid}/contacts/{c1}", headers=headers)

        # Bulk enroll c1 (already), c2 (valid), c3 (valid), fake_id (rejected)
        bulk_resp = await client.post(
            f"/api/v1/campaigns/{cid}/contacts/bulk",
            json={"contact_ids": [c1, c2, c3, fake_id]},
            headers=headers,
        )
        assert bulk_resp.status_code == 200
        res = bulk_resp.json()
        assert c2 in res["enrolled"]
        assert c3 in res["enrolled"]
        assert c1 in res["already_enrolled"]
        assert fake_id in res["rejected"]

        # Verify enrolled count
        list_resp = await client.get(f"/api/v1/campaigns/{cid}/contacts", headers=headers)
        assert len(list_resp.json()) == 3


# ── Multi-Tenant Isolation Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_campaign_isolation(test_db_session):
    async with make_client() as client:
        token_a = await register_tenant(client, "alpha@camp.com", "Camp Alpha")
        token_b = await register_tenant(client, "beta@camp.com", "Camp Beta")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant B creates campaign and contact
        camp_b = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Org B Secret Campaign", "type": "sales_outbound"},
            headers=headers_b,
        )).json()
        cid_b = camp_b["id"]
        cont_b = await create_test_contact(client, headers_b, "beta_contact@example.com")

        # Tenant A creates contact
        cont_a = await create_test_contact(client, headers_a, "alpha_contact@example.com")

        # 1. Org A cannot access Org B's campaign (404)
        get_b = await client.get(f"/api/v1/campaigns/{cid_b}", headers=headers_a)
        assert get_b.status_code == 404

        # 2. Org A cannot update Org B's campaign (404)
        patch_b = await client.patch(
            f"/api/v1/campaigns/{cid_b}",
            json={"name": "Hacked Campaign"},
            headers=headers_a,
        )
        assert patch_b.status_code == 404

        # 3. Org A cannot delete Org B's campaign (404)
        del_b = await client.delete(f"/api/v1/campaigns/{cid_b}", headers=headers_a)
        assert del_b.status_code == 404

        # 4. Org A cannot activate Org B's campaign (404)
        act_b = await client.post(f"/api/v1/campaigns/{cid_b}/activate", headers=headers_a)
        assert act_b.status_code == 404

        # 5. Org A cannot access Org B's campaign contacts (404)
        contacts_b = await client.get(f"/api/v1/campaigns/{cid_b}/contacts", headers=headers_a)
        assert contacts_b.status_code == 404

        # 6. CRITICAL: Org A cannot enroll Org B's contact into Org A's campaign (404)
        camp_a = (await client.post(
            "/api/v1/campaigns",
            json={"name": "Org A Campaign", "type": "sales_outbound"},
            headers=headers_a,
        )).json()
        cid_a = camp_a["id"]

        enroll_cross = await client.post(
            f"/api/v1/campaigns/{cid_a}/contacts/{cont_b}",
            headers=headers_a,
        )
        assert enroll_cross.status_code == 404

        # 7. Bulk enrollment with cross-tenant contact rejects cross-tenant contact safely
        bulk_cross = await client.post(
            f"/api/v1/campaigns/{cid_a}/contacts/bulk",
            json={"contact_ids": [cont_a, cont_b]},
            headers=headers_a,
        )
        assert bulk_cross.status_code == 200
        res = bulk_cross.json()
        assert cont_a in res["enrolled"]
        assert cont_b in res["rejected"]
