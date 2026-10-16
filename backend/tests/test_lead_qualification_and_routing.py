"""Tests for Lead Qualification, Explainable ICP Scoring, Routing Rules, and Campaign Eligibility."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.icp import IdealCustomerProfile
from app.models.lead import Lead
from app.models.routing_rule import LeadRoutingRule
from app.models.tenant import Organization, User


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


# ── Qualification & Scoring Evaluation Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_lead_qualification_evaluation(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "qualifier@example.com", "Qualify Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create ICP
        icp_resp = await client.post(
            "/api/v1/icps",
            headers=headers,
            json={
                "name": "B2B SaaS Mid-Market",
                "industries": ["Technology", "Software", "SaaS"],
                "company_size_min": 50,
                "company_size_max": 500,
                "countries": ["United States", "Canada"],
                "job_titles": ["VP of Sales", "Head of Growth", "CRO"],
                "seniority_levels": ["VP", "Director", "C-Level"],
                "technologies": ["python", "react", "hubspot"],
            },
        )
        assert icp_resp.status_code == 201
        icp_id = icp_resp.json()["id"]

        # 2. Create Lead that matches all criteria
        lead_resp = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "company_name": "Acme SaaS",
                "company_domain": "acmesaas.com",
                "industry": "Software",
                "employee_count_range": "100-250",
                "country": "United States",
                "city": "San Francisco",
                "first_name": "Sarah",
                "last_name": "Connor",
                "email": "sarah@acmesaas.com",
                "job_title": "VP of Sales",
                "icp_id": icp_id,
            },
        )
        assert lead_resp.status_code == 201
        lead_id = lead_resp.json()["id"]

        # 3. Dry run evaluation
        dry_eval = await client.post(
            f"/api/v1/leads/{lead_id}/evaluate-qualification",
            headers=headers,
            json={"dry_run": True, "qualification_threshold": 50},
        )
        assert dry_eval.status_code == 200
        res = dry_eval.json()
        assert res["is_qualified"] is True
        assert res["score"] >= 50
        assert res["qualification_status"] == "qualified"
        assert res["matched_criteria_count"] >= 3
        assert len(res["criteria"]) > 0

        # Check lead in DB is not updated after dry run
        get_lead_resp = await client.get(f"/api/v1/leads/{lead_id}", headers=headers)
        assert get_lead_resp.json()["lead_score"] is None

        # 4. Real evaluation
        eval_resp = await client.post(
            f"/api/v1/leads/{lead_id}/evaluate-qualification",
            headers=headers,
            json={"dry_run": False, "qualification_threshold": 50},
        )
        assert eval_resp.status_code == 200
        res = eval_resp.json()
        assert res["is_qualified"] is True

        # Verify DB updated
        get_lead_resp = await client.get(f"/api/v1/leads/{lead_id}", headers=headers)
        assert get_lead_resp.json()["lead_score"] == res["score"]
        assert get_lead_resp.json()["qualification_status"] == "qualified"


@pytest.mark.asyncio
async def test_lead_missing_data_criteria_breakdown(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "sparse@example.com", "Sparse Data Inc")
        headers = {"Authorization": f"Bearer {token}"}

        # Create ICP with multiple requirements
        icp_resp = await client.post(
            "/api/v1/icps",
            headers=headers,
            json={
                "name": "Strict ICP",
                "industries": ["Healthcare"],
                "company_size_min": 100,
                "company_size_max": 500,
            },
        )
        icp_id = icp_resp.json()["id"]

        # Lead with missing industry and missing employee count
        lead_resp = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "company_name": "Mysterious LLC",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@mystery.com",
                "icp_id": icp_id,
            },
        )
        lead_id = lead_resp.json()["id"]

        eval_resp = await client.post(
            f"/api/v1/leads/{lead_id}/evaluate-qualification",
            headers=headers,
            json={"dry_run": False, "qualification_threshold": 50},
        )
        assert eval_resp.status_code == 200
        res = eval_resp.json()
        assert res["is_qualified"] is False
        assert res["qualification_status"] == "new"
        assert res["is_assessed"] is False
        # Verify criteria has 'missing_data' statuses
        missing_crits = [c for c in res["criteria"] if c["status"] == "missing_data"]
        assert len(missing_crits) >= 2


@pytest.mark.asyncio
async def test_batch_qualification_evaluation(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "batch@example.com", "Batch Corp")
        headers = {"Authorization": f"Bearer {token}"}

        lead1 = (await client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": "L1", "first_name": "C1", "email": "c1@l1.com"},
        )).json()["id"]

        lead2 = (await client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": "L2", "first_name": "C2", "email": "c2@l2.com"},
        )).json()["id"]

        resp = await client.post(
            "/api/v1/leads/batch-evaluate-qualification",
            headers=headers,
            json={"lead_ids": [lead1, lead2], "dry_run": False},
        )
        assert resp.status_code == 200
        batch_res = resp.json()
        assert batch_res["total_evaluated"] == 2
        assert len(batch_res["results"]) == 2


# ── Routing Rules CRUD & Assignment Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_routing_rules_crud_and_assignment(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "router@example.com", "Routing Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a routing rule
        rule_resp = await client.post(
            "/api/v1/routing-rules",
            headers=headers,
            json={
                "name": "Enterprise Software Route",
                "description": "Route enterprise tech leads to specialized SDR",
                "priority": 1,
                "is_active": True,
                "industries": ["Software", "Technology"],
                "min_score": 20,
                "qualification_statuses": ["qualified"],
                "assigned_team": "Enterprise Sales",
            },
        )
        assert rule_resp.status_code == 201
        rule_data = rule_resp.json()
        rule_id = rule_data["id"]
        assert rule_data["name"] == "Enterprise Software Route"

        # 2. List routing rules
        list_resp = await client.get("/api/v1/routing-rules", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        # 3. Create qualifying lead
        lead_resp = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "company_name": "High Tech Inc",
                "industry": "Software",
                "first_name": "Jane",
                "last_name": "Sales",
                "email": "jane@hightech.com",
            },
        )
        lead_id = lead_resp.json()["id"]

        # Qualify the lead manually
        await client.patch(
            f"/api/v1/leads/{lead_id}/qualification",
            headers=headers,
            json={"qualification_status": "qualified"},
        )
        # Create an ICP and evaluate it
        icp = (await client.post(
            "/api/v1/icps",
            headers=headers,
            json={"name": "Tech ICP", "industries": ["Software"]},
        )).json()
        await client.post(
            f"/api/v1/leads/{lead_id}/evaluate-qualification",
            headers=headers,
            json={"icp_id": icp["id"], "dry_run": False, "qualification_threshold": 20},
        )

        # 4. Route the lead
        route_resp = await client.post(
            f"/api/v1/leads/{lead_id}/route",
            headers=headers,
            json={"dry_run": False},
        )
        assert route_resp.status_code == 200
        r_result = route_resp.json()
        assert r_result["is_routed"] is True
        assert r_result["matched_rule_id"] == rule_id

        # Verify lead record in DB
        lead_check = await client.get(f"/api/v1/leads/{lead_id}", headers=headers)
        assert lead_check.json()["routing_rule_id"] == rule_id

        # 5. Delete rule
        del_resp = await client.delete(f"/api/v1/routing-rules/{rule_id}", headers=headers)
        assert del_resp.status_code == 200
        list_after_del = await client.get("/api/v1/routing-rules", headers=headers)
        assert len(list_after_del.json()) == 0


# ── Campaign Eligibility & Safe Enrollment Tests ─────────────────────────────

@pytest.mark.asyncio
async def test_campaign_eligibility_and_enrollment(test_db_session):
    async with make_client() as client:
        token = await register_tenant(client, "campaigner@example.com", "Campaign Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a campaign
        camp_resp = await client.post(
            "/api/v1/campaigns",
            headers=headers,
            json={
                "name": "Q4 Outbound Push",
                "campaign_type": "email",
            },
        )
        assert camp_resp.status_code == 201
        camp_id = camp_resp.json()["id"]

        # 2. Create an unqualified lead
        unqual_lead = (await client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": "Lead Unqual", "first_name": "U", "email": "u@lead.com"},
        )).json()["id"]

        # Check eligibility - should fail because qualification_status is "new"
        elig1 = await client.get(
            f"/api/v1/leads/{unqual_lead}/campaign-eligibility/{camp_id}",
            headers=headers,
        )
        assert elig1.status_code == 200
        assert elig1.json()["is_eligible"] is False
        assert any("not qualified" in s.lower() for s in elig1.json()["suppression_reasons"])

        # 3. Qualify the lead
        await client.patch(
            f"/api/v1/leads/{unqual_lead}/qualification",
            headers=headers,
            json={"qualification_status": "qualified"},
        )

        # Check eligibility now - should succeed
        elig2 = await client.get(
            f"/api/v1/leads/{unqual_lead}/campaign-eligibility/{camp_id}",
            headers=headers,
        )
        assert elig2.status_code == 200
        assert elig2.json()["is_eligible"] is True

        # 4. Enroll the lead
        enroll_resp = await client.post(
            f"/api/v1/leads/{unqual_lead}/enroll-campaign",
            headers=headers,
            json={"campaign_id": camp_id},
        )
        assert enroll_resp.status_code == 200
        enroll_res = enroll_resp.json()
        assert enroll_res["status"] == "enrolled"

        # 5. Check duplicate enrollment prevention
        elig3 = await client.get(
            f"/api/v1/leads/{unqual_lead}/campaign-eligibility/{camp_id}",
            headers=headers,
        )
        assert elig3.status_code == 200
        assert elig3.json()["is_eligible"] is False
        assert elig3.json()["already_enrolled"] is True


# ── Tenant Isolation Verification ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qualification_and_routing_tenant_isolation(test_db_session):
    async with make_client() as client:
        # Tenant A
        token_a = await register_tenant(client, "tenant_a@example.com", "Org A")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Tenant B
        token_b = await register_tenant(client, "tenant_b@example.com", "Org B")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # A creates a routing rule
        rule_a = (await client.post(
            "/api/v1/routing-rules",
            headers=headers_a,
            json={"name": "Org A Rule", "priority": 1},
        )).json()["id"]

        # A creates a lead
        lead_a = (await client.post(
            "/api/v1/leads",
            headers=headers_a,
            json={"company_name": "Lead A", "first_name": "A", "email": "a@org.com"},
        )).json()["id"]

        # Tenant B cannot see Org A rule
        b_rules = (await client.get("/api/v1/routing-rules", headers=headers_b)).json()
        assert len(b_rules) == 0

        # Tenant B cannot route Tenant A lead
        route_b = await client.post(
            f"/api/v1/leads/{lead_a}/route",
            headers=headers_b,
            json={},
        )
        assert route_b.status_code == 404

        # Tenant B cannot evaluate Tenant A lead
        eval_b = await client.post(
            f"/api/v1/leads/{lead_a}/evaluate-qualification",
            headers=headers_b,
            json={},
        )
        assert eval_b.status_code == 404
