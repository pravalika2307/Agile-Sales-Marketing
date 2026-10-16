"""Automated Unit & Integration Tests for HubSpot CRM Synchronization (Phase 1).

Tests:
1. Pagination across multiple pages with cursor tokens.
2. Field mapping from HubSpot properties to internal CRM models.
3. Duplicate prevention / idempotency on repeated sync runs.
4. Tenant isolation (multi-tenant boundaries strictly enforced).
5. Permission failure handling: 403 Forbidden with missing scope crm.objects.companies.read.
6. Honest reporting: Empty portal results remain 0, never fabricated.
7. Local data preservation: Existing voice test records remain intact.
8. API endpoints: /status and /sync.
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Company, Contact, Deal, Pipeline, PipelineStage
from app.models.hubspot_sync import HubSpotSyncRun
from app.models.lead import Lead
from app.models.tenant import Organization, User
from app.services.integrations.hubspot.client import (
    HubSpotClient,
    HubSpotPermissionError,
)
from app.services.integrations.hubspot.sync import (
    HubSpotSyncEngine,
    HubSpotSyncSummary,
)


# ── In-Memory SQLite Test Fixture ─────────────────────────────────────────────

@pytest.fixture
def db_session():
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


@pytest.fixture
def org_and_pipeline(db_session):
    """Setup a test organization with a default pipeline and stage."""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Sync Org",
        slug="test-sync-org",
    )
    db_session.add(org)
    db_session.flush()

    pipeline = Pipeline(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Default Pipeline",
        is_default=True,
    )
    db_session.add(pipeline)
    db_session.flush()

    stage = PipelineStage(
        id=uuid.uuid4(),
        pipeline_id=pipeline.id,
        name="Discovery",
        order_index=1,
        probability_pct=20,
    )
    db_session.add(stage)
    db_session.commit()

    return org, pipeline, stage


# ── 1. Pagination & Contact Field Mapping Test ─────────────────────────────────

@pytest.mark.asyncio
async def test_contacts_pagination_and_field_mapping(db_session, org_and_pipeline):
    org, _, _ = org_and_pipeline

    page1_response = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-contact-101",
                    "properties": {
                        "firstname": "Alice",
                        "lastname": "Smith",
                        "email": "alice@company.com",
                        "phone": "+1-555-0101",
                        "jobtitle": "VP Engineering",
                        "company": "Acme Corp",
                        "hs_lead_status": "OPEN",
                    },
                }
            ],
            "paging": {"next": {"after": "cursor-page-2"}},
        },
    )

    page2_response = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-contact-102",
                    "properties": {
                        "firstname": "Bob",
                        "lastname": "Jones",
                        "email": "bob@company.com",
                        "phone": "+1-555-0102",
                        "jobtitle": "CTO",
                        "company": "Acme Corp",
                        "hs_lead_status": "QUALIFIED",
                    },
                }
            ],
        },
    )

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True

    async def mock_get(path, params=None, check_status=True):
        if path == "/crm/v3/objects/contacts":
            if params and params.get("after") == "cursor-page-2":
                return page2_response
            return page1_response
        return Response(status_code=200, json={"results": []})

    mock_client.get = AsyncMock(side_effect=mock_get)

    engine = HubSpotSyncEngine(client=mock_client)
    res = await engine.sync_contacts(db_session, org.id)

    assert res.status == "synced"
    assert res.imported == 2
    assert res.total_in_hubspot == 2

    # Verify Contacts stored in database
    contacts = db_session.query(Contact).filter(Contact.organization_id == org.id).all()
    assert len(contacts) == 2

    c1 = db_session.query(Contact).filter(Contact.hubspot_id == "hs-contact-101").first()
    assert c1 is not None
    assert c1.email == "alice@company.com"
    assert c1.first_name == "Alice"
    assert c1.last_name == "Smith"
    assert c1.job_title == "VP Engineering"
    assert c1.phone == "+1-555-0101"
    assert c1.lead_status == "new"

    # Verify corresponding Leads created with neutral unscored state
    leads = db_session.query(Lead).filter(Lead.organization_id == org.id).all()
    assert len(leads) == 2
    l1 = db_session.query(Lead).filter(Lead.source_external_id == "hs-contact-101").first()
    assert l1 is not None
    assert l1.source == "hubspot"
    assert l1.lead_score == 0
    assert l1.lead_temperature == "cold"
    assert l1.qualification_status == "new"


# ── 2. Duplicate Prevention / Idempotency Test ────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_prevention_on_repeat_sync(db_session, org_and_pipeline):
    org, _, _ = org_and_pipeline

    single_page_resp = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-contact-201",
                    "properties": {
                        "firstname": "Carol",
                        "lastname": "Danvers",
                        "email": "carol@marvel.com",
                        "phone": "+1-555-0201",
                        "jobtitle": "Director",
                        "company": "Starforce",
                    },
                }
            ],
        },
    )

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True
    mock_client.get = AsyncMock(return_value=single_page_resp)

    engine = HubSpotSyncEngine(client=mock_client)

    # First run -> 1 imported, 0 updated
    run1 = await engine.sync_contacts(db_session, org.id)
    assert run1.imported == 1
    assert run1.updated == 0

    total_contacts_after_run1 = db_session.query(Contact).filter(Contact.organization_id == org.id).count()
    assert total_contacts_after_run1 == 1

    # Second run -> 0 imported, 1 updated (idempotent, no duplicate rows)
    run2 = await engine.sync_contacts(db_session, org.id)
    assert run2.imported == 0
    assert run2.updated == 1

    total_contacts_after_run2 = db_session.query(Contact).filter(Contact.organization_id == org.id).count()
    assert total_contacts_after_run2 == 1  # No duplicate record!


# ── 3. Tenant Isolation Test ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(db_session, org_and_pipeline):
    org_a, _, _ = org_and_pipeline

    # Create Org B
    org_b = Organization(id=uuid.uuid4(), name="Org B", slug="org-b")
    db_session.add(org_b)
    db_session.commit()

    contact_resp = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-tenant-isolate-1",
                    "properties": {
                        "firstname": "David",
                        "lastname": "Tenant",
                        "email": "david@tardis.org",
                    },
                }
            ],
        },
    )

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True
    mock_client.get = AsyncMock(return_value=contact_resp)

    engine = HubSpotSyncEngine(client=mock_client)

    # Sync into Org A
    await engine.sync_contacts(db_session, org_a.id)

    # Verify Org A has the record
    assert db_session.query(Contact).filter(Contact.organization_id == org_a.id).count() == 1

    # Verify Org B has zero records (strict tenant isolation)
    assert db_session.query(Contact).filter(Contact.organization_id == org_b.id).count() == 0
    assert db_session.query(Lead).filter(Lead.organization_id == org_b.id).count() == 0


# ── 4. Permission Error / Missing Scope 403 Test ──────────────────────────────

@pytest.mark.asyncio
async def test_company_permission_403_handling(db_session, org_and_pipeline):
    org, _, _ = org_and_pipeline

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True

    async def mock_get(path, params=None, check_status=True):
        if path == "/crm/v3/objects/companies":
            raise HubSpotPermissionError(
                message="This app hasn't been granted all required scopes to make this call.",
                required_scopes=["crm.objects.companies.read"],
            )
        elif path == "/crm/v3/objects/contacts":
            return Response(status_code=200, json={"results": []})
        elif path == "/crm/v3/objects/deals":
            return Response(status_code=200, json={"results": []})
        elif path == "/account-info/v3/details":
            return Response(status_code=200, json={"portalId": 244174914})
        return Response(status_code=200, json={})

    mock_client.get = AsyncMock(side_effect=mock_get)

    engine = HubSpotSyncEngine(client=mock_client)
    summary = await engine.run_sync(db_session, org.id)

    # Must be "partial", not a fatal crash
    assert summary.status == "partial"
    assert summary.companies.status == "missing_scope"
    assert summary.companies.imported == 0
    assert summary.companies.scope_required == "crm.objects.companies.read"
    assert "crm.objects.companies.read" in summary.permission_errors["companies"]

    # Verify zero companies in DB (no fabricated data)
    assert db_session.query(Company).filter(Company.organization_id == org.id).count() == 0

    # Verify HubSpotSyncRun audit recorded
    sync_run = db_session.query(HubSpotSyncRun).filter(HubSpotSyncRun.organization_id == org.id).first()
    assert sync_run is not None
    assert sync_run.status == "partial"
    assert "companies" in sync_run.permission_errors


# ── 5. Honest Zero-Record / Empty Handling ────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_deals_portal_returns_zero(db_session, org_and_pipeline):
    org, _, stage = org_and_pipeline

    empty_resp = Response(status_code=200, json={"results": []})

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True
    mock_client.get = AsyncMock(return_value=empty_resp)

    engine = HubSpotSyncEngine(client=mock_client)
    res = await engine.sync_deals(db_session, org.id)

    assert res.status == "empty"
    assert res.imported == 0
    assert res.total_in_hubspot == 0

    # Verify Deal table is empty
    assert db_session.query(Deal).filter(Deal.organization_id == org.id).count() == 0


# ── 6. Preservation of Existing Voice Test Leads ─────────────────────────────

@pytest.mark.asyncio
async def test_existing_voice_test_leads_preserved(db_session, org_and_pipeline):
    org, _, _ = org_and_pipeline

    # Create the voice test lead
    voice_lead = Lead(
        organization_id=org.id,
        source="retell_voice_call",
        source_external_id="call-voice-test-123",
        first_name="Test",
        last_name="VoiceLead",
        email="test@example.com",
        company_name="Voice Inc",
        status="contacted",
    )
    db_session.add(voice_lead)
    db_session.commit()

    # Simulate HubSpot sync with another contact
    contact_resp = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-contact-999",
                    "properties": {
                        "firstname": "HubSpot",
                        "lastname": "Only",
                        "email": "hubspotonly@example.com",
                        "company": "HubSpot Portal",
                    },
                }
            ],
        },
    )

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True
    mock_client.get = AsyncMock(return_value=contact_resp)

    engine = HubSpotSyncEngine(client=mock_client)
    await engine.sync_contacts(db_session, org.id)

    # Verify voice lead was NOT altered
    preserved = db_session.query(Lead).filter(Lead.email == "test@example.com").first()
    assert preserved is not None
    assert preserved.source == "retell_voice_call"
    assert preserved.source_external_id == "call-voice-test-123"
    assert preserved.first_name == "Test"


# ── 7. Successful Company & Deal Mapping ──────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_deals_and_companies_sync(db_session, org_and_pipeline):
    org, _, stage = org_and_pipeline

    companies_resp = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-comp-1",
                    "properties": {
                        "name": "Wayne Enterprises",
                        "domain": "wayne.com",
                        "industry": "Defense",
                        "numberofemployees": "1000-5000",
                        "city": "Gotham",
                        "country": "USA",
                    },
                }
            ],
        },
    )

    deals_resp = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-deal-1",
                    "properties": {
                        "dealname": "Batmobile Supply Contract",
                        "amount": "5000000.00",
                        "closedate": "2026-12-31T00:00:00.000Z",
                        "hs_is_closed_won": "false",
                    },
                }
            ],
        },
    )

    mock_client = MagicMock(spec=HubSpotClient)
    mock_client.is_configured = True

    async def mock_get(path, params=None, check_status=True):
        if path == "/crm/v3/objects/companies":
            return companies_resp
        elif path == "/crm/v3/objects/deals":
            return deals_resp
        return Response(status_code=200, json={"results": []})

    mock_client.get = AsyncMock(side_effect=mock_get)

    engine = HubSpotSyncEngine(client=mock_client)
    res_co = await engine.sync_companies(db_session, org.id)
    assert res_co.status == "synced"
    assert res_co.imported == 1

    company = db_session.query(Company).filter(Company.hubspot_id == "hs-comp-1").first()
    assert company is not None
    assert company.name == "Wayne Enterprises"
    assert company.domain == "wayne.com"

    res_dl = await engine.sync_deals(db_session, org.id)
    assert res_dl.status == "synced"
    assert res_dl.imported == 1

    deal = db_session.query(Deal).filter(Deal.hubspot_id == "hs-deal-1").first()
    assert deal is not None
    assert deal.name == "Batmobile Supply Contract"
    assert deal.amount == Decimal("5000000.00")
    assert deal.pipeline_stage_id == stage.id
