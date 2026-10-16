"""
Unit and integration tests for Pre-Call Lead Intelligence & Web Research layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.lead import Lead
from app.models.lead_research import LeadResearch
from app.models.tenant import Organization
from app.schemas.lead_research import StructuredLeadIntelligence
from app.services.outreach.voice_agent import build_voice_dynamic_variables
from app.services.research.base import RawResearchResult, RawSource
from app.services.research.providers.mock import (
    MockLLMStructuringProvider,
    MockWebResearchProvider,
)
from app.services.research.service import LeadNotFoundError, LeadResearchService


# ── In-Memory SQLite Fixture ───────────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Isolated in-memory SQLite database session."""
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


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> tuple[str, str]:
    """Helper to register tenant and return (token, org_id)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Research Tester",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["tokens"]["access_token"], data["organization"]["id"]


def create_test_lead(
    session,
    org_id: uuid.UUID,
    company_name: str = "Acme Health",
    domain: str = "acmehealth.com",
    industry: str = "Healthcare",
) -> Lead:
    """Helper to insert test lead."""
    lead = Lead(
        organization_id=org_id,
        company_name=company_name,
        company_domain=domain,
        industry=industry,
        employee_count_range="100-250",
        city="Chicago",
        country="USA",
        first_name="Alice",
        last_name="Johnson",
        email="alice@acmehealth.com",
        job_title="Director of Operations",
        qualification_status="new",
        status="new",
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


# ── 1. Model Persistence & Freshness Logic ────────────────────────────────────

def test_lead_research_model_persistence_and_freshness(test_db_session):
    org_id = uuid.uuid4()
    lead = create_test_lead(test_db_session, org_id)

    now = datetime.now(timezone.utc)
    research = LeadResearch(
        organization_id=org_id,
        lead_id=lead.id,
        company_summary="Acme Health is a regional healthcare provider.",
        industry="Healthcare",
        company_size="100-250",
        location="Chicago, USA",
        business_signals=["Expanding outpatient facilities"],
        potential_pain_points=["Scheduling overhead"],
        personalization_points=["Congratulate on Chicago clinic opening"],
        research_summary="Acme Health focuses on outpatient care.",
        source_urls=["https://acmehealth.com"],
        researched_at=now,
        research_status="completed",
    )
    test_db_session.add(research)
    test_db_session.commit()
    test_db_session.refresh(research)

    assert research.id is not None
    assert research.check_freshness(max_age_days=7) is True
    assert research.is_fresh is True

    # Test stale threshold
    research.researched_at = now - timedelta(days=10)
    test_db_session.commit()
    assert research.check_freshness(max_age_days=7) is False
    assert research.is_fresh is False


# ── 2. Service Workflow & Freshness Reuse ─────────────────────────────────────

@pytest.mark.asyncio
async def test_lead_research_service_workflow_and_freshness_reuse(test_db_session):
    org_id = uuid.uuid4()
    lead = create_test_lead(test_db_session, org_id)

    web_mock = MockWebResearchProvider()
    llm_mock = MockLLMStructuringProvider()
    service = LeadResearchService(web_provider=web_mock, llm_provider=llm_mock)

    # Initial research execution
    res1 = await service.get_or_research_lead(
        db=test_db_session,
        org_id=org_id,
        lead_id=lead.id,
        max_age_days=7,
        force_refresh=False,
    )
    assert res1.research_status == "completed"
    assert res1.company_summary is not None
    assert "Acme Health" in res1.company_summary
    assert len(res1.source_urls) > 0
    assert "https://acmehealth.com" in res1.source_urls[0]

    # Verify relationship on lead
    test_db_session.refresh(lead)
    assert lead.research is not None
    assert lead.research.id == res1.id

    # Secondary call: should reuse fresh research without calling provider again
    with patch.object(web_mock, "search_and_fetch", wraps=web_mock.search_and_fetch) as spy_search:
        res2 = await service.get_or_research_lead(
            db=test_db_session,
            org_id=org_id,
            lead_id=lead.id,
            max_age_days=7,
            force_refresh=False,
        )
        assert res2.id == res1.id
        spy_search.assert_not_called()

    # Force refresh: should re-run search
    with patch.object(web_mock, "search_and_fetch", wraps=web_mock.search_and_fetch) as spy_search:
        res3 = await service.get_or_research_lead(
            db=test_db_session,
            org_id=org_id,
            lead_id=lead.id,
            max_age_days=7,
            force_refresh=True,
        )
        assert res3.id == res1.id
        spy_search.assert_called_once()


# ── 3. Tenant Isolation & Security ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lead_research_tenant_isolation(test_db_session):
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    lead_org1 = create_test_lead(test_db_session, org1_id)

    service = LeadResearchService(
        web_provider=MockWebResearchProvider(),
        llm_provider=MockLLMStructuringProvider(),
    )

    # Attempt to access Org1's lead from Org2
    with pytest.raises(LeadNotFoundError):
        await service.get_or_research_lead(
            db=test_db_session,
            org_id=org2_id,
            lead_id=lead_org1.id,
        )


# ── 4. Error Handling During Web/LLM Failures ──────────────────────────────────

@pytest.mark.asyncio
async def test_lead_research_provider_failure_handling(test_db_session):
    org_id = uuid.uuid4()
    lead = create_test_lead(test_db_session, org_id)

    failing_web = MockWebResearchProvider(should_fail=True)
    service = LeadResearchService(
        web_provider=failing_web,
        llm_provider=MockLLMStructuringProvider(),
    )

    record = await service.get_or_research_lead(
        db=test_db_session,
        org_id=org_id,
        lead_id=lead.id,
    )

    assert record.research_status == "failed"
    assert record.error_message is not None
    assert "Mock research provider connection failure" in record.error_message


# ── 5. Voice Dynamic Context Formatting ───────────────────────────────────────

def test_voice_dynamic_context_formatting_and_injection(test_db_session):
    org_id = uuid.uuid4()
    lead = create_test_lead(test_db_session, org_id)

    research = LeadResearch(
        organization_id=org_id,
        lead_id=lead.id,
        company_summary="Acme Health manages modern outpatient centers in Illinois.",
        industry="Healthcare",
        potential_pain_points=["Manual scheduling backlogs", "Patient intake delays"],
        personalization_points=["Noticed their recent expansion in outpatient care"],
        business_signals=["Added 3 new clinic locations"],
        research_summary="Regional healthcare provider experiencing patient intake growth.",
        research_status="completed",
        researched_at=datetime.now(timezone.utc),
    )

    voice_context = LeadResearchService.format_voice_dynamic_context(research)
    assert "Acme Health manages modern outpatient centers" in voice_context["research_company_summary"]
    assert "Manual scheduling backlogs; Patient intake delays" == voice_context["research_pain_points"]
    assert "Noticed their recent expansion in outpatient care" == voice_context["research_personalization_point"]
    assert "Added 3 new clinic locations" == voice_context["research_business_signals"]

    # Test integration with build_voice_dynamic_variables
    all_vars = build_voice_dynamic_variables(
        contact=lead,
        company=None,
        campaign=None,
        organization=None,
        lead_research=research,
    )

    assert all_vars["lead_first_name"] == "Alice"
    assert all_vars["lead_last_name"] == "Johnson"
    assert all_vars["research_company_summary"] == voice_context["research_company_summary"]
    assert all_vars["research_pain_points"] == voice_context["research_pain_points"]
    assert all_vars["research_personalization_point"] == voice_context["research_personalization_point"]


# ── 6. REST API Endpoints ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lead_research_api_endpoints(test_db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token, org_id_str = await register_tenant(client, "research_api@example.com", "Research Org")
        headers = {"Authorization": f"Bearer {token}"}
        org_id = uuid.UUID(org_id_str)

        lead = create_test_lead(test_db_session, org_id, company_name="TechWave Solutions")

        # A. Trigger research via POST
        post_resp = await client.post(
            f"/api/v1/leads/{lead.id}/research",
            json={"force_refresh": False, "max_age_days": 7},
            headers=headers,
        )
        assert post_resp.status_code == 200, post_resp.text
        data = post_resp.json()
        assert data["lead_id"] == str(lead.id)
        assert data["research_status"] == "completed"
        assert "TechWave Solutions" in data["company_summary"]
        assert data["is_fresh"] is True

        # B. Query cached research via GET
        get_resp = await client.get(
            f"/api/v1/leads/{lead.id}/research",
            headers=headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == data["id"]

        # C. Query formatted voice context
        vc_resp = await client.get(
            f"/api/v1/leads/{lead.id}/research/voice-context",
            headers=headers,
        )
        assert vc_resp.status_code == 200
        vc_data = vc_resp.json()
        assert "voice_dynamic_variables" in vc_data
        v_vars = vc_data["voice_dynamic_variables"]
        assert "research_company_summary" in v_vars
        assert "TechWave Solutions" in v_vars["research_company_summary"]
        assert "research_pain_points" in v_vars
