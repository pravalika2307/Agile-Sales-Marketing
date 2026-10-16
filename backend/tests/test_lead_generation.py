"""Unit and integration tests for Lead Generation Provider, Scoring, and Deduplication."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import CampaignContact
from app.models.icp import IdealCustomerProfile
from app.models.lead import Lead
from app.models.outreach import Outreach
from app.services.lead_generation.base import LeadSearchCriteria
from app.services.lead_generation.mock_provider import MockLeadGenerationProvider
from app.services.lead_generation.scoring import (
    calculate_lead_score,
    calculate_lead_temperature,
)


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


def test_mock_provider_offline_and_deterministic():
    """Mock provider must generate deterministic fake prospects offline without network."""
    provider = MockLeadGenerationProvider()
    criteria = LeadSearchCriteria(
        industries=["Fintech"],
        countries=["Germany"],
        cities=["Berlin"],
        job_titles=["Chief Technology Officer"],
        company_size_min=50,
        company_size_max=250,
    )

    res1 = provider.search(criteria, limit=5)
    res2 = provider.search(criteria, limit=5)

    assert res1.total_found == 5
    assert res2.total_found == 5

    # Check identical synthetic data
    for l1, l2 in zip(res1.leads, res2.leads):
        assert l1.company_name == l2.company_name
        assert l1.company_domain == l2.company_domain
        assert l1.email == l2.email
        assert l1.industry == "Fintech"
        assert l1.country == "Germany"
        assert l1.city == "Berlin"
        assert l1.job_title == "Chief Technology Officer"
        assert l1.employee_count_range == "50-250"
        assert l1.source_external_id == l2.source_external_id


def test_deterministic_scoring_and_temperature_thresholds():
    """Verify deterministic scoring calculations and temperature classifications."""
    assert calculate_lead_temperature(0) == "cold"
    assert calculate_lead_temperature(39) == "cold"
    assert calculate_lead_temperature(40) == "warm"
    assert calculate_lead_temperature(69) == "warm"
    assert calculate_lead_temperature(70) == "hot"
    assert calculate_lead_temperature(100) == "hot"

    provider = MockLeadGenerationProvider()
    criteria = LeadSearchCriteria(
        industries=["Software"],
        countries=["United States"],
        cities=["Austin"],
        job_titles=["VP of Sales"],
    )
    result = provider.search(criteria, limit=1)
    lead = result.leads[0]

    # Create dummy ICP matching lead
    dummy_icp = IdealCustomerProfile(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Target ICP",
        industries=["Software"],
        countries=["United States"],
        cities=["Austin"],
        job_titles=["VP of Sales"],
    )

    score, temp, reason = calculate_lead_score(lead, dummy_icp)
    assert score >= 60  # +20 (industry) + 15 (country) + 10 (city) + 15 (job title) + 5 (domain) = 65
    assert temp in ["warm", "hot"]
    assert "Industry matched ICP" in reason
    assert "Country matched ICP" in reason
    assert "Job title matched ICP" in reason


@pytest.mark.asyncio
async def test_duplicate_lead_prevention(test_db_session):
    """Running generate twice against same ICP skips existing external leads."""
    async with make_client() as client:
        token = await register_tenant(client, "dedup_owner@test.com", "Dedup Org")
        headers = {"Authorization": f"Bearer {token}"}

        icp = await client.post("/api/v1/icps", json={"name": "Dedup ICP"}, headers=headers)
        icp_id = icp.json()["id"]

        # Run 1: generate 5
        r1 = await client.post(f"/api/v1/icps/{icp_id}/generate", json={"limit": 5}, headers=headers)
        assert r1.status_code == 200
        assert r1.json()["created_count"] == 5
        assert r1.json()["skipped_count"] == 0

        # Run 2: generate same 5 leads -> all 5 skipped
        r2 = await client.post(f"/api/v1/icps/{icp_id}/generate", json={"limit": 5}, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["created_count"] == 0
        assert r2.json()["skipped_count"] == 5


@pytest.mark.asyncio
async def test_no_campaign_enrollment_or_outreach_execution(test_db_session):
    """Lead generation must NEVER auto-enroll into campaigns or send outreach emails."""
    async with make_client() as client:
        token = await register_tenant(client, "safety_owner@test.com", "Safety Org")
        headers = {"Authorization": f"Bearer {token}"}

        icp = await client.post("/api/v1/icps", json={"name": "Safety ICP"}, headers=headers)
        icp_id = icp.json()["id"]

        # Generate leads
        await client.post(f"/api/v1/icps/{icp_id}/generate", json={"limit": 5}, headers=headers)

        # Verify no CampaignContact rows exist
        enrollments = list(test_db_session.execute(select(CampaignContact)).scalars().all())
        assert len(enrollments) == 0

        # Verify no Outreach rows exist
        outreaches = list(test_db_session.execute(select(Outreach)).scalars().all())
        assert len(outreaches) == 0
