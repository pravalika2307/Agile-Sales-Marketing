"""Unit & Integration tests for FastAPI HubSpot endpoints and Tenant Security."""
import uuid
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_organization
from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Contact, Deal, Pipeline, PipelineStage
from app.models.tenant import Organization
from app.services.integrations.hubspot.client import HubSpotClient
from app.services.integrations.hubspot.contacts import HubSpotContactService
from app.services.integrations.hubspot.deals import HubSpotDealService


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
        app.dependency_overrides.pop(get_current_organization, None)


@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "hubspot_configured" in data


# ── SEC-01: Unauthenticated Requests Must Return 401 Unauthorized ──────────────

@pytest.mark.asyncio
async def test_api_hubspot_test_unauthenticated(test_db_session):
    """Unauthenticated calls to /test must be rejected with 401."""
    app.dependency_overrides.pop(get_current_organization, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/integrations/hubspot/test")
        assert resp.status_code == 401
        assert "credentials were not provided" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_hubspot_get_contact_unauthenticated(test_db_session):
    """Unauthenticated calls to /contacts/{id} must be rejected with 401."""
    app.dependency_overrides.pop(get_current_organization, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/integrations/hubspot/contacts/c101")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_hubspot_get_deal_unauthenticated(test_db_session):
    """Unauthenticated calls to /deals/{id} must be rejected with 401."""
    app.dependency_overrides.pop(get_current_organization, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/integrations/hubspot/deals/d202")
        assert resp.status_code == 401


# ── SEC-01: Authenticated Requests & Tenant Isolation ──────────────────────────

@pytest.mark.asyncio
async def test_api_hubspot_test_authenticated_unconfigured(test_db_session):
    """Authenticated request returns configured=False when token is missing."""
    org = Organization(id=uuid.uuid4(), name="Acme Corp", slug="acme")
    test_db_session.add(org)
    test_db_session.commit()

    app.dependency_overrides[get_current_organization] = lambda: org
    transport = ASGITransport(app=app)

    with patch.object(HubSpotClient, "is_configured", False):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/api/v1/integrations/hubspot/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is False
            assert data["success"] is False
            assert "not configured" in data["message"].lower()


@pytest.mark.asyncio
async def test_api_hubspot_test_authenticated_success(test_db_session):
    """Authenticated request returns connection verification result."""
    org = Organization(id=uuid.uuid4(), name="Acme Corp", slug="acme")
    test_db_session.add(org)
    test_db_session.commit()

    app.dependency_overrides[get_current_organization] = lambda: org
    transport = ASGITransport(app=app)

    mock_validate = {
        "success": True,
        "status_code": 200,
        "message": "HubSpot connection verified successfully.",
        "details": {"owners_sampled": 2},
    }

    with patch.object(HubSpotClient, "is_configured", True):
        with patch.object(HubSpotClient, "validate_credentials", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = mock_validate
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/api/v1/integrations/hubspot/test")
                assert resp.status_code == 200
                data = resp.json()
                assert data["configured"] is True
                assert data["success"] is True
                assert data["details"]["owners_sampled"] == 2


@pytest.mark.asyncio
async def test_api_hubspot_get_contact_cross_tenant_forbidden(test_db_session):
    """SEC-01: Accessing contact belonging to another organization returns 403 Forbidden."""
    org_a = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    org_b = Organization(id=uuid.uuid4(), name="Org B", slug="org-b")
    test_db_session.add_all([org_a, org_b])
    test_db_session.commit()

    # Local record belongs to Org B
    foreign_contact = Contact(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        hubspot_id="c_foreign_101",
        first_name="Alice",
        last_name="Smith",
        email="alice@foreign.com",
    )
    test_db_session.add(foreign_contact)
    test_db_session.commit()

    # Request made by Org A
    app.dependency_overrides[get_current_organization] = lambda: org_a
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/integrations/hubspot/contacts/c_foreign_101")
        assert resp.status_code == 403
        assert "belongs to another organization" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_hubspot_get_contact_same_tenant_success(test_db_session):
    """SEC-01: Accessing contact belonging to same organization returns 200 OK."""
    org_a = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    test_db_session.add(org_a)
    test_db_session.commit()

    local_contact = Contact(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        hubspot_id="c_local_101",
        first_name="Bob",
        last_name="Jones",
        email="bob@local.com",
    )
    test_db_session.add(local_contact)
    test_db_session.commit()

    mock_contact = {
        "id": "c_local_101",
        "properties": {"firstname": "Bob", "email": "bob@local.com"},
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-02T00:00:00Z",
    }

    app.dependency_overrides[get_current_organization] = lambda: org_a
    transport = ASGITransport(app=app)

    with patch.object(HubSpotContactService, "is_configured", True):
        with patch.object(HubSpotContactService, "get_contact", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_contact
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/api/v1/integrations/hubspot/contacts/c_local_101")
                assert resp.status_code == 200
                data = resp.json()
                assert data["id"] == "c_local_101"
                assert data["properties"]["email"] == "bob@local.com"


@pytest.mark.asyncio
async def test_api_hubspot_get_contact_not_found(test_db_session):
    """Authenticated request returns 404 when contact does not exist in HubSpot."""
    org_a = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    test_db_session.add(org_a)
    test_db_session.commit()

    app.dependency_overrides[get_current_organization] = lambda: org_a
    transport = ASGITransport(app=app)

    with patch.object(HubSpotContactService, "is_configured", True):
        with patch.object(HubSpotContactService, "get_contact", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/api/v1/integrations/hubspot/contacts/c_missing")
                assert resp.status_code == 404
                assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_hubspot_get_deal_cross_tenant_forbidden(test_db_session):
    """SEC-01: Accessing deal belonging to another organization returns 403 Forbidden."""
    org_a = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    org_b = Organization(id=uuid.uuid4(), name="Org B", slug="org-b")
    test_db_session.add_all([org_a, org_b])
    test_db_session.commit()

    # Create pipeline and stage for Org B
    pipeline_b = Pipeline(id=uuid.uuid4(), organization_id=org_b.id, name="Pipeline B")
    test_db_session.add(pipeline_b)
    test_db_session.flush()
    stage_b = PipelineStage(id=uuid.uuid4(), pipeline_id=pipeline_b.id, name="Stage B", order_index=0)
    test_db_session.add(stage_b)
    test_db_session.flush()

    foreign_deal = Deal(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        pipeline_stage_id=stage_b.id,
        hubspot_id="d_foreign_202",
        name="Enterprise Plan",
        amount=50000.0,
    )
    test_db_session.add(foreign_deal)
    test_db_session.commit()

    app.dependency_overrides[get_current_organization] = lambda: org_a
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/integrations/hubspot/deals/d_foreign_202")
        assert resp.status_code == 403
        assert "belongs to another organization" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_hubspot_get_deal_same_tenant_success(test_db_session):
    """SEC-01: Accessing deal belonging to same organization returns 200 OK."""
    org_a = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    test_db_session.add(org_a)
    test_db_session.commit()

    pipeline_a = Pipeline(id=uuid.uuid4(), organization_id=org_a.id, name="Pipeline A")
    test_db_session.add(pipeline_a)
    test_db_session.flush()
    stage_a = PipelineStage(id=uuid.uuid4(), pipeline_id=pipeline_a.id, name="Stage A", order_index=0)
    test_db_session.add(stage_a)
    test_db_session.flush()

    local_deal = Deal(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        pipeline_stage_id=stage_a.id,
        hubspot_id="d_local_202",
        name="Growth Plan",
        amount=12000.0,
    )
    test_db_session.add(local_deal)
    test_db_session.commit()

    mock_deal = {
        "id": "d_local_202",
        "properties": {"dealname": "Growth Plan", "amount": "12000.0"},
        "createdAt": "2026-02-01T00:00:00Z",
        "updatedAt": "2026-02-02T00:00:00Z",
    }

    app.dependency_overrides[get_current_organization] = lambda: org_a
    transport = ASGITransport(app=app)

    with patch.object(HubSpotDealService, "is_configured", True):
        with patch.object(HubSpotDealService, "get_deal", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_deal
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/api/v1/integrations/hubspot/deals/d_local_202")
                assert resp.status_code == 200
                data = resp.json()
                assert data["id"] == "d_local_202"
                assert data["properties"]["dealname"] == "Growth Plan"


@pytest.mark.asyncio
async def test_api_hubspot_get_deal_not_found(test_db_session):
    """Authenticated request returns 404 when deal does not exist in HubSpot."""
    org_a = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    test_db_session.add(org_a)
    test_db_session.commit()

    app.dependency_overrides[get_current_organization] = lambda: org_a
    transport = ASGITransport(app=app)

    with patch.object(HubSpotDealService, "is_configured", True):
        with patch.object(HubSpotDealService, "get_deal", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/api/v1/integrations/hubspot/deals/d_missing")
                assert resp.status_code == 404
                assert "not found" in resp.json()["detail"].lower()
