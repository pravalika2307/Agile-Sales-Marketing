"""Comprehensive unit and integration tests for duplicate prevention across Agile Sales & Marketing.

Covers:
1. Contact duplicate prevention (same email -> 409 Conflict).
2. Case-insensitive and whitespace email normalization.
3. Organization isolation for contacts and companies.
4. Safe handling of missing email / missing domain.
5. Company duplicate prevention (normalized domain -> 409 Conflict).
6. Domain normalization (schemes, www prefixes, trailing slashes, uppercase).
7. Similar company names with distinct domains preserved.
8. Lead duplicate prevention (same email -> 409 Conflict).
9. Lead auto-linkage to existing CRM contact.
10. Lead discovery / generation deduplication against existing org leads.
11. Voice webhook repeated delivery idempotency & lead snapshot deduplication.
12. Voice webhook case-insensitive email matching.
13. Zero unintended campaign enrollment or outreach dispatch.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.normalization import normalize_domain, normalize_email
from app.main import app
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.tenant import Organization
from app.services.company_service import DuplicateCompanyError, create_company
from app.services.contact_service import DuplicateContactError, create_contact
from app.services.lead_generation.base import GeneratedLead, LeadGenerationResult
from app.services.lead_generation.service import (
    DuplicateLeadError,
    create_lead,
    generate_leads,
)
from app.services.outreach.voice_followup import (
    ExtractedCallData,
    VoiceFollowUpService,
)


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
            "full_name": "Tenant Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201
    return resp.json()["tokens"]["access_token"]


# ── 1. Normalization Utility Tests ────────────────────────────────────────────

def test_normalization_utils():
    # Email normalization
    assert normalize_email("  ALICE@Example.COM ") == "alice@example.com"
    assert normalize_email(None) is None
    assert normalize_email("") is None
    assert normalize_email("   ") is None

    # Domain normalization
    assert normalize_domain("https://www.AcmeCorp.com/path?foo=bar") == "acmecorp.com"
    assert normalize_domain("http://WWW.Sub.Domain.org/") == "sub.domain.org"
    assert normalize_domain("Example.COM:8080") == "example.com"
    assert normalize_domain("  simple-domain.co.uk  ") == "simple-domain.co.uk"
    assert normalize_domain(None) is None
    assert normalize_domain("") is None


# ── 2. Contact Duplicate Prevention ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_duplicate_prevention_same_email(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin1@org1.com", "Org 1")
        headers = {"Authorization": f"Bearer {token}"}

        # First contact succeeds
        resp1 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Alice", "last_name": "Smith", "email": "alice@company.com"},
        )
        assert resp1.status_code == 201
        data1 = resp1.json()
        assert data1["email"] == "alice@company.com"

        # Duplicate email rejected with 409 Conflict
        resp2 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Alice", "last_name": "Duplicate", "email": "alice@company.com"},
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_contact_case_insensitive_and_whitespace(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin2@org2.com", "Org 2")
        headers = {"Authorization": f"Bearer {token}"}

        resp1 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Bob", "last_name": "Jones", "email": "  Bob.Jones@Corp.IO  "},
        )
        assert resp1.status_code == 201
        assert resp1.json()["email"] == "bob.jones@corp.io"

        # Attempt to create with different case and whitespace
        resp2 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Robert", "last_name": "Jones", "email": "bob.jones@corp.io"},
        )
        assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_contact_organization_isolation(test_db_session: Session):
    async with make_client() as client:
        token1 = await register_tenant(client, "org1_admin@test.com", "Tenant Alpha")
        token2 = await register_tenant(client, "org2_admin@test.com", "Tenant Beta")

        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        # Both tenants create contact with identical email
        resp1 = await client.post(
            "/api/v1/contacts",
            headers=headers1,
            json={"first_name": "John", "last_name": "Doe", "email": "john.doe@sharedpartner.com"},
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/v1/contacts",
            headers=headers2,
            json={"first_name": "John", "last_name": "Doe", "email": "john.doe@sharedpartner.com"},
        )
        assert resp2.status_code == 201
        assert resp1.json()["id"] != resp2.json()["id"]


@pytest.mark.asyncio
async def test_lead_missing_email_safe(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin3@org3.com", "Org 3")
        headers = {"Authorization": f"Bearer {token}"}

        # Multiple leads without email are allowed safely
        resp1 = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": "Walkin Prospect 1", "first_name": "Anonymous", "last_name": "One", "email": None},
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": "Walkin Prospect 2", "first_name": "Anonymous", "last_name": "Two", "email": None},
        )
        assert resp2.status_code == 201


# ── 3. Company Duplicate Prevention ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_company_duplicate_prevention_same_domain(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin4@org4.com", "Org 4")
        headers = {"Authorization": f"Bearer {token}"}

        resp1 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Acme Inc", "domain": "acme.com"},
        )
        assert resp1.status_code == 201

        # Duplicate domain rejected with 409
        resp2 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Acme Alternative", "domain": "acme.com"},
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_company_normalized_domain_variations(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin5@org5.com", "Org 5")
        headers = {"Authorization": f"Bearer {token}"}

        resp1 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Globex", "domain": "https://www.GlobexCorp.com/about"},
        )
        assert resp1.status_code == 201
        assert resp1.json()["domain"] == "globexcorp.com"

        # Attempt duplicate with www prefix and uppercase
        resp2 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Globex 2", "domain": "WWW.GLOBEXCORP.COM"},
        )
        assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_company_similar_names_distinct_domains(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin6@org6.com", "Org 6")
        headers = {"Authorization": f"Bearer {token}"}

        # Similar names should NOT be treated as duplicates if domains differ
        resp1 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Apex Solutions", "domain": "apex-tech.com"},
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Apex Solutions", "domain": "apex-consulting.com"},
        )
        assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_company_missing_domain_safe(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin7@org7.com", "Org 7")
        headers = {"Authorization": f"Bearer {token}"}

        resp1 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Local Store 1", "domain": None},
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/v1/companies",
            headers=headers,
            json={"name": "Local Store 2", "domain": None},
        )
        assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_company_organization_isolation(test_db_session: Session):
    async with make_client() as client:
        token1 = await register_tenant(client, "t1_admin@org.com", "Tenant 1")
        token2 = await register_tenant(client, "t2_admin@org.com", "Tenant 2")

        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        resp1 = await client.post(
            "/api/v1/companies",
            headers=headers1,
            json={"name": "Cyberdyne", "domain": "cyberdyne.com"},
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/v1/companies",
            headers=headers2,
            json={"name": "Cyberdyne", "domain": "cyberdyne.com"},
        )
        assert resp2.status_code == 201
        assert resp1.json()["id"] != resp2.json()["id"]


# ── 4. Lead Duplicate Prevention & Contact Linkage ────────────────────────────

@pytest.mark.asyncio
async def test_lead_duplicate_prevention_same_email(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "lead_admin@org.com", "Lead Org")
        headers = {"Authorization": f"Bearer {token}"}

        resp1 = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "company_name": "Tech Corp",
                "first_name": "Sarah",
                "last_name": "Connor",
                "email": "sarah.connor@techcorp.com",
            },
        )
        assert resp1.status_code == 201

        # Duplicate lead with same email rejected
        resp2 = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "company_name": "Tech Corp 2",
                "first_name": "Sarah",
                "last_name": "Connor",
                "email": "  SARAH.CONNOR@techcorp.com  ",
            },
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_lead_links_to_existing_crm_contact(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "link_admin@org.com", "Link Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create CRM Contact first
        c_resp = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "first_name": "Dave",
                "last_name": "Bowman",
                "email": "dave@discovery.org",
            },
        )
        assert c_resp.status_code == 201
        contact_id = c_resp.json()["id"]

        # 2. Create Lead with same email
        l_resp = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={
                "company_name": "Discovery Inc",
                "first_name": "Dave",
                "last_name": "Bowman",
                "email": "DAVE@Discovery.org",
            },
        )
        assert l_resp.status_code == 201
        lead_data = l_resp.json()
        assert lead_data["contact_id"] == contact_id


def test_lead_generation_discovery_deduplication(test_db_session: Session):
    from app.models.icp import IdealCustomerProfile

    # Setup organization and existing lead in DB
    org = Organization(name="Discovery Dedupe Org", slug="discovery-dedupe-org")
    test_db_session.add(org)
    test_db_session.flush()

    icp = IdealCustomerProfile(
        organization_id=org.id,
        name="Target ICP",
    )
    test_db_session.add(icp)
    test_db_session.flush()

    existing_lead = Lead(
        organization_id=org.id,
        icp_id=icp.id,
        company_name="Alpha Co",
        email="existing@alphaco.com",
        status="new",
        source="manual",
    )
    test_db_session.add(existing_lead)
    test_db_session.commit()

    # Mock provider returning 2 leads: 1 duplicate, 1 new
    mock_provider = MagicMock()
    mock_provider.search.return_value = LeadGenerationResult(
        total_found=2,
        source_name="mock",
        leads=[
            GeneratedLead(
                source="mock",
                source_external_id="ext-1",
                company_name="Alpha Co",
                email="EXISTING@AlphaCo.com",  # Duplicate with different case
                first_name="Existing",
                last_name="Person",
            ),
            GeneratedLead(
                source="mock",
                source_external_id="ext-2",
                company_name="Beta Co",
                email="new@betaco.com",  # Genuinely new
                first_name="New",
                last_name="Person",
            ),
        ],
    )

    result = generate_leads(
        db=test_db_session,
        current_org=org,
        icp_id=icp.id,
        provider=mock_provider,
    )

    # Only 1 new lead should be created, duplicate skipped
    assert result["created_count"] == 1
    assert result["skipped_count"] == 1


# ── 5. Voice Webhook Processing & Idempotency ─────────────────────────────────

def test_voice_webhook_idempotency_and_case_insensitive_matching(test_db_session: Session):
    org = Organization(name="Voice Tenant", slug="voice-tenant")
    test_db_session.add(org)
    test_db_session.flush()

    # Pre-create contact with mixed case email
    contact = Contact(
        organization_id=org.id,
        email="caller@voicetest.com",
        first_name="Existing",
        last_name="Caller",
        lead_status="qualified",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    service = VoiceFollowUpService(db=test_db_session)

    call_payload = {
        "event": "call_analyzed",
        "call_id": "call-dedupe-test-001",
        "direction": "inbound",
        "metadata": {
            "organization_id": str(org.id),
        },
        "call_analysis": {
            "call_outcome": "QUALIFIED",
            "custom_analysis_data": {
                "email": "  CALLER@VoiceTest.COM  ",
                "lead_full_name": "Caller Person",
                "company_name": "Voice Test Corp",
            },
        },
    }

    # First delivery
    res1 = service.process_call_analyzed(call_payload)
    assert res1["status"] == "success"
    assert res1["duplicate"] is False

    # Second delivery with same call_id
    res2 = service.process_call_analyzed(call_payload)
    assert res2["status"] == "success"
    assert res2["duplicate"] is True

    # Verify no duplicate contacts were created
    contacts = test_db_session.execute(
        select(Contact).where(Contact.organization_id == org.id)
    ).scalars().all()
    assert len(contacts) == 1
    assert contacts[0].email == "caller@voicetest.com"


# ── 6. HubSpot Repeated Sync Idempotency ───────────────────────────────────────

@pytest.mark.asyncio
async def test_repeated_hubspot_sync_does_not_create_duplicate_contacts(test_db_session: Session):
    from httpx import Response
    from app.services.integrations.hubspot.sync import HubSpotSyncEngine

    org = Organization(name="HubSpot Sync Org", slug="hubspot-sync-org")
    test_db_session.add(org)
    test_db_session.commit()

    page_response = Response(
        status_code=200,
        json={
            "results": [
                {
                    "id": "hs-contact-999",
                    "properties": {
                        "email": "hubspot_prospect@partner.org",
                        "firstname": "Hub",
                        "lastname": "Spotter",
                    },
                }
            ],
            "paging": None,
        },
    )

    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.get = AsyncMock(return_value=page_response)

    sync_engine = HubSpotSyncEngine(client=mock_client)

    # First sync run
    sum1 = await sync_engine.sync_contacts(test_db_session, org.id)
    assert sum1.imported == 1

    # Second sync run with identical records
    sum2 = await sync_engine.sync_contacts(test_db_session, org.id)
    assert sum2.imported == 0
    assert sum2.updated == 1

    # Ensure only 1 contact exists in DB
    contacts = test_db_session.execute(
        select(Contact).where(Contact.organization_id == org.id)
    ).scalars().all()
    assert len(contacts) == 1
    assert contacts[0].hubspot_id == "hs-contact-999"


# ── 7. Lead Conversion CRM Entity Reuse ───────────────────────────────────────

def test_convert_lead_reuses_existing_company_and_contact(test_db_session: Session):
    from app.services.lead_generation.service import convert_lead_to_crm

    org = Organization(name="Convert Tenant", slug="convert-tenant")
    test_db_session.add(org)
    test_db_session.flush()

    # Pre-existing Company and Contact in CRM
    existing_comp = Company(
        organization_id=org.id,
        name="Wayne Enterprises",
        domain="waynecorp.com",
    )
    test_db_session.add(existing_comp)
    test_db_session.flush()

    existing_cont = Contact(
        organization_id=org.id,
        company_id=existing_comp.id,
        first_name="Bruce",
        last_name="Wayne",
        email="bruce@waynecorp.com",
        lead_status="qualified",
    )
    test_db_session.add(existing_cont)
    test_db_session.flush()

    # Lead with same domain and email
    lead = Lead(
        organization_id=org.id,
        company_name="Wayne Enterprises Inc",
        company_domain="https://www.waynecorp.com",
        first_name="Bruce",
        last_name="Wayne",
        email="BRUCE@WAYNECORP.COM",
        status="new",
        source="manual",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    # Convert lead
    resp = convert_lead_to_crm(db=test_db_session, current_org=org, lead_id=lead.id)

    assert resp.company_created is False
    assert resp.contact_created is False
    assert resp.company_id == existing_comp.id
    assert resp.contact_id == existing_cont.id
    assert resp.status == "converted"


# ── 8. No Unintended Campaign Enrollment or Outreach Dispatch ──────────────────

@pytest.mark.asyncio
async def test_no_unintended_campaign_enrollment_or_outreach(test_db_session: Session):
    from app.models.campaign import CampaignContact
    from app.models.outreach import Outreach

    async with make_client() as client:
        token = await register_tenant(client, "safety_admin@org.com", "Safety Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create contact
        c_resp = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Safe", "last_name": "Contact", "email": "safe@guard.com"},
        )
        assert c_resp.status_code == 201

        # Create lead
        l_resp = await client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": "Guard Co", "first_name": "Safe", "last_name": "Lead", "email": "safe_lead@guard.com"},
        )
        assert l_resp.status_code == 201

        # Verify 0 campaign enrollments and 0 outreach records
        enrollments = test_db_session.execute(select(CampaignContact)).scalars().all()
        assert len(enrollments) == 0

        outreach_records = test_db_session.execute(select(Outreach)).scalars().all()
        assert len(outreach_records) == 0

