"""Integration and unit tests for Step 11: Leads, Qualification, Selection, and CRM Conversion."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Company, Contact
from app.models.lead import Lead


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
            "password": "SecurePassword123!",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_lead_generation_and_listing(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "lead_owner@test.com", "Prospects Inc")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create ICP
        icp_resp = await client.post(
            "/api/v1/icps",
            json={
                "name": "Tech Exec ICP",
                "industries": ["Software"],
                "company_size_min": 10,
                "company_size_max": 200,
                "countries": ["United States"],
                "job_titles": ["VP of Sales"],
            },
            headers=headers,
        )
        assert icp_resp.status_code == 201
        icp_id = icp_resp.json()["id"]

        # 2. Generate leads
        gen_resp = await client.post(
            f"/api/v1/icps/{icp_id}/generate",
            json={"limit": 5},
            headers=headers,
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["created_count"] == 5
        assert len(gen_data["leads"]) == 5

        # 3. List leads
        list_resp = await client.get("/api/v1/leads", headers=headers)
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] == 5
        assert len(list_data["items"]) == 5

        first_lead = list_data["items"][0]
        assert first_lead["qualification_status"] == "new"
        assert first_lead["status"] == "new"
        assert first_lead["lead_score"] > 0
        assert first_lead["lead_temperature"] in ["cold", "warm", "hot"]
        assert first_lead["qualification_reason"] is not None


@pytest.mark.asyncio
async def test_lead_filtering_and_pagination(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "filter_owner@test.com", "Filter Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create ICP and generate 10 leads
        icp_resp = await client.post(
            "/api/v1/icps",
            json={
                "name": "Global Tech ICP",
                "industries": ["Software", "Healthcare"],
                "countries": ["United States", "Canada"],
            },
            headers=headers,
        )
        icp_id = icp_resp.json()["id"]

        await client.post(f"/api/v1/icps/{icp_id}/generate", json={"limit": 10}, headers=headers)

        # Pagination test: page 1, page_size 4
        p1_resp = await client.get("/api/v1/leads?page=1&page_size=4", headers=headers)
        assert p1_resp.status_code == 200
        p1_data = p1_resp.json()
        assert len(p1_data["items"]) == 4
        assert p1_data["total"] == 10
        assert p1_data["page"] == 1

        # Pagination test: page 3, page_size 4
        p3_resp = await client.get("/api/v1/leads?page=3&page_size=4", headers=headers)
        assert p3_resp.status_code == 200
        p3_data = p3_resp.json()
        assert len(p3_data["items"]) == 2

        # Filter by ICP ID
        icp_filter = await client.get(f"/api/v1/leads?icp_id={icp_id}", headers=headers)
        assert icp_filter.status_code == 200
        assert icp_filter.json()["total"] == 10

        # Filter by non-existent ICP ID
        random_uuid = str(uuid.uuid4())
        empty_filter = await client.get(f"/api/v1/leads?icp_id={random_uuid}", headers=headers)
        assert empty_filter.status_code == 200
        assert empty_filter.json()["total"] == 0


@pytest.mark.asyncio
async def test_lead_qualification_update(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "qual_owner@test.com", "Qual Org")
        headers = {"Authorization": f"Bearer {token}"}

        icp = await client.post("/api/v1/icps", json={"name": "ICP"}, headers=headers)
        gen = await client.post(f"/api/v1/icps/{icp.json()['id']}/generate", json={"limit": 1}, headers=headers)
        lead_id = gen.json()["leads"][0]["id"]

        # Update qualification to 'qualified' and temperature to 'hot'
        patch_resp = await client.patch(
            f"/api/v1/leads/{lead_id}/qualification",
            json={
                "qualification_status": "qualified",
                "lead_temperature": "hot",
                "qualification_reason": "Manually reviewed by SDR; great product fit",
            },
            headers=headers,
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["qualification_status"] == "qualified"
        assert data["lead_temperature"] == "hot"
        assert data["qualification_reason"] == "Manually reviewed by SDR; great product fit"


@pytest.mark.asyncio
async def test_lead_selection_workflow(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "sel_owner@test.com", "Selection Org")
        headers = {"Authorization": f"Bearer {token}"}

        icp = await client.post("/api/v1/icps", json={"name": "ICP"}, headers=headers)
        gen = await client.post(f"/api/v1/icps/{icp.json()['id']}/generate", json={"limit": 4}, headers=headers)
        leads = gen.json()["leads"]

        lead1_id = leads[0]["id"]
        lead2_id = leads[1]["id"]
        lead3_id = leads[2]["id"]  # will be disqualified
        lead4_id = leads[3]["id"]

        # Disqualify lead3
        await client.patch(
            f"/api/v1/leads/{lead3_id}/qualification",
            json={"qualification_status": "disqualified"},
            headers=headers,
        )

        # 1. Select lead1 and lead2
        sel_resp1 = await client.post(
            "/api/v1/leads/select",
            json={"lead_ids": [lead1_id, lead2_id]},
            headers=headers,
        )
        assert sel_resp1.status_code == 200
        data1 = sel_resp1.json()
        assert data1["selected_count"] == 2
        assert data1["already_selected_count"] == 0
        assert data1["rejected_count"] == 0

        # 2. Select again: lead1 (already selected) and lead3 (disqualified) and lead4 (new)
        sel_resp2 = await client.post(
            "/api/v1/leads/select",
            json={"lead_ids": [lead1_id, lead3_id, lead4_id]},
            headers=headers,
        )
        assert sel_resp2.status_code == 200
        data2 = sel_resp2.json()
        assert data2["selected_count"] == 1  # lead4
        assert data2["already_selected_count"] == 1  # lead1
        assert data2["rejected_count"] == 1  # lead3


@pytest.mark.asyncio
async def test_convert_lead_to_crm(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "crm_owner@test.com", "CRM Org")
        headers = {"Authorization": f"Bearer {token}"}

        icp = await client.post("/api/v1/icps", json={"name": "CRM ICP"}, headers=headers)
        gen = await client.post(f"/api/v1/icps/{icp.json()['id']}/generate", json={"limit": 2}, headers=headers)
        leads = gen.json()["leads"]
        lead1_id = leads[0]["id"]
        lead2_id = leads[1]["id"]

        # 1. Convert lead1 -> new company and new contact created
        conv_resp1 = await client.post(f"/api/v1/leads/{lead1_id}/convert", headers=headers)
        assert conv_resp1.status_code == 200
        cdata1 = conv_resp1.json()
        assert cdata1["company_created"] is True
        assert cdata1["contact_created"] is True
        assert cdata1["status"] == "converted"
        company1_id = cdata1["company_id"]
        contact1_id = cdata1["contact_id"]

        # Verify lead record updated
        lead1_get = await client.get(f"/api/v1/leads/{lead1_id}", headers=headers)
        assert lead1_get.json()["company_id"] == company1_id
        assert lead1_get.json()["contact_id"] == contact1_id
        assert lead1_get.json()["status"] == "converted"

        # 2. Convert lead1 again (idempotent CRM reuse)
        conv_resp1_repeat = await client.post(f"/api/v1/leads/{lead1_id}/convert", headers=headers)
        assert conv_resp1_repeat.status_code == 200
        cdata_repeat = conv_resp1_repeat.json()
        assert cdata_repeat["company_created"] is False
        assert cdata_repeat["contact_created"] is False
        assert cdata_repeat["company_id"] == company1_id
        assert cdata_repeat["contact_id"] == contact1_id


@pytest.mark.asyncio
async def test_cross_tenant_lead_isolation(test_db_session):
    async with make_client() as client:
        token_a = await register_tenant(client, "tenant_a_leads@test.com", "Org Alpha")
        token_b = await register_tenant(client, "tenant_b_leads@test.com", "Org Beta")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Org Alpha creates an ICP and generates a lead
        icp = await client.post("/api/v1/icps", json={"name": "Alpha ICP"}, headers=headers_a)
        gen = await client.post(f"/api/v1/icps/{icp.json()['id']}/generate", json={"limit": 1}, headers=headers_a)
        lead_id = gen.json()["leads"][0]["id"]

        # Org Beta cannot get Alpha's lead -> 404
        get_b = await client.get(f"/api/v1/leads/{lead_id}", headers=headers_b)
        assert get_b.status_code == 404

        # Org Beta cannot update qualification of Alpha's lead -> 404
        patch_b = await client.patch(
            f"/api/v1/leads/{lead_id}/qualification",
            json={"qualification_status": "qualified"},
            headers=headers_b,
        )
        assert patch_b.status_code == 404

        # Org Beta selecting Alpha's lead ignores it safely without cross-tenant leakage
        sel_b = await client.post(
            "/api/v1/leads/select",
            json={"lead_ids": [lead_id]},
            headers=headers_b,
        )
        assert sel_b.status_code == 200
        assert sel_b.json()["selected_count"] == 0

        # Org Beta cannot convert Alpha's lead -> 404
        conv_b = await client.post(f"/api/v1/leads/{lead_id}/convert", headers=headers_b)
        assert conv_b.status_code == 404


@pytest.mark.asyncio
async def test_unscored_and_manual_leads_data_integrity(test_db_session):
    """Test data integrity: manual/unscored leads must have is_scored=False and lead_score=None."""
    async with make_client() as client:
        token = await register_tenant(client, "unscored_owner@test.com", "Integrity Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a manual lead
        create_resp = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Sarah",
                "last_name": "Connor",
                "email": "sarah.connor@cyberdyne.io",
                "company_name": "Cyberdyne Systems",
                "job_title": "Security Lead",
                "source": "manual",
            },
            headers=headers,
        )
        assert create_resp.status_code == 201
        created_lead = create_resp.json()
        assert created_lead["is_scored"] is False
        assert created_lead["lead_score"] is None
        assert created_lead["qualification_reason"] is None

        # 2. Verify listing also returns is_scored=False and lead_score=None
        list_resp = await client.get("/api/v1/leads?exclude_test=false", headers=headers)
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["is_scored"] is False
        assert items[0]["lead_score"] is None

        # 3. Create ICP-evaluated lead and verify is_scored=True and evaluated score is preserved
        icp = await client.post("/api/v1/icps", json={"name": "Cyber ICP"}, headers=headers)
        gen = await client.post(f"/api/v1/icps/{icp.json()['id']}/generate", json={"limit": 1}, headers=headers)
        assert gen.status_code == 200
        gen_lead = gen.json()["leads"][0]
        assert gen_lead["is_scored"] is True
        assert gen_lead["lead_score"] is not None
        assert gen_lead["lead_score"] > 0


@pytest.mark.asyncio
async def test_bulk_status_update_and_tenant_isolation(test_db_session):
    """Test bulk status update endpoint and enforce strict tenant scoping."""
    async with make_client() as client:
        token_a = await register_tenant(client, "bulk_a@test.com", "Bulk Org A")
        token_b = await register_tenant(client, "bulk_b@test.com", "Bulk Org B")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Create two leads in Org A
        lead_a1 = (await client.post(
            "/api/v1/leads",
            json={"first_name": "A1", "company_name": "Company A1", "source": "manual"},
            headers=headers_a,
        )).json()
        lead_a2 = (await client.post(
            "/api/v1/leads",
            json={"first_name": "A2", "company_name": "Company A2", "source": "manual"},
            headers=headers_a,
        )).json()

        # Update lifecycle status in bulk for Org A
        bulk_resp1 = await client.patch(
            "/api/v1/leads/bulk-status",
            json={
                "lead_ids": [lead_a1["id"], lead_a2["id"]],
                "status": "contacted",
            },
            headers=headers_a,
        )
        assert bulk_resp1.status_code == 200
        res1 = bulk_resp1.json()
        assert res1["updated_count"] == 2
        assert len(res1["updated_ids"]) == 2

        # Verify leads updated in Org A
        get_a1 = await client.get(f"/api/v1/leads/{lead_a1['id']}", headers=headers_a)
        assert get_a1.json()["status"] == "contacted"

        # Update qualification status in bulk
        bulk_resp2 = await client.patch(
            "/api/v1/leads/bulk-status",
            json={
                "lead_ids": [lead_a1["id"]],
                "qualification_status": "qualified",
            },
            headers=headers_a,
        )
        assert bulk_resp2.status_code == 200
        assert bulk_resp2.json()["updated_count"] == 1
        get_a1_updated = await client.get(f"/api/v1/leads/{lead_a1['id']}", headers=headers_a)
        assert get_a1_updated.json()["qualification_status"] == "qualified"
        # Lifecycle status remains contacted
        assert get_a1_updated.json()["status"] == "contacted"

        # Cross-tenant attempt: Org B attempts to update Org A's leads in bulk
        bulk_cross = await client.patch(
            "/api/v1/leads/bulk-status",
            json={
                "lead_ids": [lead_a1["id"], lead_a2["id"]],
                "status": "converted",
            },
            headers=headers_b,
        )
        assert bulk_cross.status_code == 200
        # Org B should update 0 records because the leads belong to Org A
        assert bulk_cross.json()["updated_count"] == 0
        assert len(bulk_cross.json()["updated_ids"]) == 0

        # Verify Org A's lead is unmodified
        check_a1 = await client.get(f"/api/v1/leads/{lead_a1['id']}", headers=headers_a)
        assert check_a1.json()["status"] == "contacted"


@pytest.mark.asyncio
async def test_lead_qualification_and_lifecycle_filters_independent(test_db_session):
    """Test that qualification_status and lifecycle status filters operate independently."""
    async with make_client() as client:
        token = await register_tenant(client, "indep_filter@test.com", "Filter Independent Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create lead 1: new lifecycle, qualified qualification
        l1 = (await client.post(
            "/api/v1/leads",
            json={
                "first_name": "L1",
                "company_name": "C1",
                "qualification_status": "qualified",
            },
            headers=headers,
        )).json()

        # Create lead 2: contacted lifecycle, new qualification
        l2 = (await client.post(
            "/api/v1/leads",
            json={
                "first_name": "L2",
                "company_name": "C2",
                "status": "contacted",
                "qualification_status": "new",
            },
            headers=headers,
        )).json()

        # Filter by qualification_status=qualified only
        q_filter = await client.get("/api/v1/leads?qualification_status=qualified&exclude_test=false", headers=headers)
        assert q_filter.status_code == 200
        q_data = q_filter.json()
        assert q_data["total"] == 1
        assert q_data["items"][0]["id"] == l1["id"]

        # Filter by status=contacted only
        s_filter = await client.get("/api/v1/leads?status=contacted&exclude_test=false", headers=headers)
        assert s_filter.status_code == 200
        s_data = s_filter.json()
        assert s_data["total"] == 1
        assert s_data["items"][0]["id"] == l2["id"]


@pytest.mark.asyncio
async def test_batch_lead_import(test_db_session):
    """Test batch lead import with duplicate skipping, row errors, and tenant isolation."""
    async with make_client() as client:
        token_a = await register_tenant(client, "import_a@test.com", "Import Org A")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = await register_tenant(client, "import_b@test.com", "Import Org B")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 1. Pre-create a lead in Org A
        await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Existing",
                "email": "existing@alpha.com",
                "company_name": "Alpha Corp",
            },
            headers=headers_a,
        )

        # 2. Batch import into Org A:
        # Row 1: Valid new lead
        # Row 2: In-batch duplicate of Row 1
        # Row 3: Pre-existing duplicate in Org A
        # Row 4: Missing company/identifying info -> should fail
        # Row 5: Invalid email -> should fail
        # Row 6: Valid new lead with person name deriving company
        import_payload = {
            "rows": [
                {
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john.doe@acme.com",
                    "company_name": "Acme Inc",
                    "phone": "+15551234567",
                    "job_title": "VP Sales",
                },
                {
                    "first_name": "John Duplicate",
                    "email": "john.doe@acme.com",
                    "company_name": "Acme Inc",
                },
                {
                    "first_name": "Existing Duplicate",
                    "email": "existing@alpha.com",
                    "company_name": "Alpha Corp",
                },
                {
                    "first_name": "",
                    "last_name": "",
                    "email": "",
                    "company_name": "",
                },
                {
                    "first_name": "Bad",
                    "email": "not-an-email",
                    "company_name": "Bad Corp",
                },
                {
                    "first_name": "Alice",
                    "last_name": "Smith",
                    "email": "alice@innovate.io",
                    "company_name": "",
                },
            ]
        }

        resp_a = await client.post("/api/v1/leads/import", json=import_payload, headers=headers_a)
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert data_a["imported_count"] == 2  # Row 1 and Row 6
        assert data_a["skipped_duplicate_count"] == 2  # Row 2 (in-batch) and Row 3 (DB duplicate)
        assert data_a["failed_count"] == 2  # Row 4 (empty) and Row 5 (bad email)
        assert len(data_a["imported_ids"]) == 2
        assert len(data_a["errors"]) == 2

        # 3. Tenant Isolation: Org B imports the same email that was already in Org A
        resp_b = await client.post(
            "/api/v1/leads/import",
            json={
                "rows": [
                    {
                        "first_name": "Org B John",
                        "email": "john.doe@acme.com",
                        "company_name": "Acme Org B",
                    }
                ]
            },
            headers=headers_b,
        )
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        assert data_b["imported_count"] == 1
        assert data_b["skipped_duplicate_count"] == 0

@pytest.mark.asyncio
async def test_create_lead_with_minimal_fields_and_edit_later(test_db_session):
    """Test creating a lead with only name, phone, and company (no email), and later adding email and LinkedIn."""
    async with make_client() as client:
        token = await register_tenant(client, "edit_lead_test@test.com", "Edit Lead Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create with minimal fields (no email, no linkedin, no job title)
        create_payload = {
            "first_name": "Hank",
            "last_name": "Schrader",
            "company_name": "Schrader Enterprises",
            "phone": "+1 555-0199",
            "source": "manual",
        }
        res_create = await client.post("/api/v1/leads", json=create_payload, headers=headers)
        assert res_create.status_code == 201
        lead = res_create.json()
        lead_id = lead["id"]
        assert lead["first_name"] == "Hank"
        assert lead["last_name"] == "Schrader"
        assert lead["phone"] == "+1 555-0199"
        assert lead["email"] is None
        assert lead["job_title"] is None
        assert lead["linkedin_profile_url"] is None

        # 2. Update lead with added details: email, job_title, linkedin_profile_url, location
        update_payload = {
            "email": "hank.schrader@dea.gov",
            "job_title": "Special Agent in Charge",
            "linkedin_profile_url": "https://www.linkedin.com/in/hank-schrader-asac/?trk=feed",
            "city": "Albuquerque",
            "state": "NM",
        }
        res_patch = await client.patch(f"/api/v1/leads/{lead_id}", json=update_payload, headers=headers)
        assert res_patch.status_code == 200
        updated = res_patch.json()

        # 3. Verify untouched fields are preserved, and new fields are populated and normalized
        assert updated["first_name"] == "Hank"
        assert updated["last_name"] == "Schrader"
        assert updated["phone"] == "+1 555-0199"
        assert updated["company_name"] == "Schrader Enterprises"
        assert updated["email"] == "hank.schrader@dea.gov"
        assert updated["job_title"] == "Special Agent in Charge"
        assert updated["linkedin_profile_url"] == "https://www.linkedin.com/in/hank-schrader-asac"
        assert updated["city"] == "Albuquerque"
        assert updated["state"] == "NM"

        # 4. Verify linked Contact exists and is synchronized
        assert updated["contact_id"] is not None
        contact_id = updated["contact_id"]
        res_contact = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
        assert res_contact.status_code == 200
        contact = res_contact.json()
        assert contact["first_name"] == "Hank"
        assert contact["email"] == "hank.schrader@dea.gov"
        assert contact["phone"] == "+1 555-0199"
        assert contact["job_title"] == "Special Agent in Charge"
        assert contact["linkedin_profile_url"] == "https://www.linkedin.com/in/hank-schrader-asac"
