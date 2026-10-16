"""Automated tests for List-Driven Lead Management (Stage C)."""
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from contextlib import asynccontextmanager
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.contact_list import CampaignList, ContactList, ContactListMember
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.tenant import Organization, User
from app.schemas.contact_list import ContactListCreate, ContactListUpdate
from app.services import contact_list_service


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
        Base.metadata.drop_all(bind=engine)
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
            "password": "Password123!",
            "full_name": "List Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


@pytest.fixture
def org_one(db_session):
    org = Organization(name="Acme Corp", slug="acme-corp")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_two(db_session):
    org = Organization(name="Beta Industries", slug="beta-industries")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


# ── Test Suite ────────────────────────────────────────────────────────────────

def test_create_list_and_unique_name_per_org(db_session, org_one, org_two):
    # 1. Create list in Org 1
    l1 = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Q4 SaaS Prospects", description="High value SaaS")
    )
    assert l1.id is not None
    assert l1.name == "Q4 SaaS Prospects"
    assert l1.organization_id == org_one.id

    # 2. Reject duplicate list name within Org 1 (case-insensitive)
    with pytest.raises(contact_list_service.DuplicateContactListNameError):
        contact_list_service.create_contact_list(
            db_session, org_one.id, ContactListCreate(name="q4 saas prospects")
        )

    # 3. Allow same list name in Org 2
    l2 = contact_list_service.create_contact_list(
        db_session, org_two.id, ContactListCreate(name="Q4 SaaS Prospects")
    )
    assert l2.id is not None
    assert l2.organization_id == org_two.id
    assert l2.id != l1.id


def test_list_crud_operations(db_session, org_one):
    l1 = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="FinTech Founders")
    )

    # Retrieve
    retrieved = contact_list_service.get_contact_list(db_session, org_one.id, l1.id)
    assert retrieved is not None
    assert retrieved.name == "FinTech Founders"

    # Update
    updated = contact_list_service.update_contact_list(
        db_session, org_one.id, l1.id, ContactListUpdate(name="FinTech CEOs", description="Updated desc")
    )
    assert updated.name == "FinTech CEOs"
    assert updated.description == "Updated desc"

    # List
    items, total = contact_list_service.list_contact_lists(db_session, org_one.id)
    assert total == 1
    assert items[0].name == "FinTech CEOs"

    # Delete
    deleted = contact_list_service.delete_contact_list(db_session, org_one.id, l1.id)
    assert deleted is True
    assert contact_list_service.get_contact_list(db_session, org_one.id, l1.id) is None


def test_add_contact_and_lead_members(db_session, org_one):
    cl = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Retail Leaders")
    )

    # Create CRM Contact
    contact = Contact(
        organization_id=org_one.id,
        first_name="Alice",
        last_name="Smith",
        email="alice@retailcorp.com",
    )
    db_session.add(contact)
    db_session.commit()
    db_session.refresh(contact)

    # Create Lead with linked contact
    lead1 = Lead(
        organization_id=org_one.id,
        first_name="Bob",
        last_name="Jones",
        email="bob@retailcorp.com",
        company_name="Retail Corp",
        contact_id=contact.id,
    )
    db_session.add(lead1)
    db_session.commit()

    # Add both to list
    res = contact_list_service.add_members_to_list(
        db_session, org_one.id, cl.id, contact_ids=[contact.id], lead_ids=[lead1.id]
    )
    # Since lead1.contact_id == contact.id, contact is added once and lead is linked!
    assert res.added_count == 1
    assert res.already_members_count == 1

    members, count = contact_list_service.list_members(db_session, org_one.id, cl.id)
    assert count == 1
    assert members[0].email == "alice@retailcorp.com"
    assert members[0].has_valid_email is True
    assert members[0].is_unresolved_email is False


def test_add_lead_without_email_preserves_lead_without_contact(db_session, org_one):
    cl = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Research Prospects")
    )

    # Create lead without email
    lead_no_email = Lead(
        organization_id=org_one.id,
        first_name="Ghost",
        last_name="Prospect",
        email=None,
        phone="+1234567890",
        company_name="Stealth Co",
    )
    db_session.add(lead_no_email)
    db_session.commit()

    # Add to list
    res = contact_list_service.add_members_to_list(
        db_session, org_one.id, cl.id, lead_ids=[lead_no_email.id]
    )
    assert res.added_count == 1
    assert res.already_members_count == 0

    # Verify membership row points to lead_id only, with contact_id=None
    membership = (
        db_session.query(ContactListMember)
        .filter(ContactListMember.contact_list_id == cl.id)
        .first()
    )
    assert membership.lead_id == lead_no_email.id
    assert membership.contact_id is None

    # Verify listing shows unresolved email badge
    members, count = contact_list_service.list_members(db_session, org_one.id, cl.id)
    assert count == 1
    assert members[0].has_valid_email is False
    assert members[0].is_unresolved_email is True
    assert members[0].company_name == "Stealth Co"

    # Verify no spurious Contact row was created in contacts table
    total_contacts = db_session.query(Contact).count()
    assert total_contacts == 0


def test_remove_member_preserves_underlying_entities(db_session, org_one):
    cl = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Temp List")
    )

    contact = Contact(
        organization_id=org_one.id,
        first_name="Dan",
        last_name="Miller",
        email="dan@miller.com",
    )
    db_session.add(contact)
    db_session.commit()

    contact_list_service.add_members_to_list(
        db_session, org_one.id, cl.id, contact_ids=[contact.id]
    )
    _, count = contact_list_service.list_members(db_session, org_one.id, cl.id)
    assert count == 1

    # Remove member
    removed = contact_list_service.remove_member_from_list(
        db_session, org_one.id, cl.id, contact.id
    )
    assert removed is True

    _, count = contact_list_service.list_members(db_session, org_one.id, cl.id)
    assert count == 0

    # Invariant: Contact still exists in CRM!
    still_exists = db_session.query(Contact).filter(Contact.id == contact.id).first()
    assert still_exists is not None


def test_cross_tenant_isolation(db_session, org_one, org_two):
    l1 = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Org1 Private List")
    )
    contact_org2 = Contact(
        organization_id=org_two.id,
        first_name="Spy",
        last_name="Agent",
        email="spy@org2.com",
    )
    db_session.add(contact_org2)
    db_session.commit()

    # Tenant 2 cannot access Org 1's list
    assert contact_list_service.get_contact_list(db_session, org_two.id, l1.id) is None

    # Tenant 1 cannot add Tenant 2's contact
    res = contact_list_service.add_members_to_list(
        db_session, org_one.id, l1.id, contact_ids=[contact_org2.id]
    )
    assert res.added_count == 0
    assert res.failed_count == 1

    members, count = contact_list_service.list_members(db_session, org_one.id, l1.id)
    assert count == 0


def test_campaign_attachment_and_sync_eligibility(db_session, org_one):
    cl = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Campaign Audience List")
    )

    # 1. Eligible Contact
    c_valid = Contact(
        organization_id=org_one.id,
        first_name="Valid",
        last_name="User",
        email="valid@target.com",
        lead_status="new",
    )
    # 2. Suppressed Contact
    c_suppressed = Contact(
        organization_id=org_one.id,
        first_name="Opted",
        last_name="Out",
        email="optout@target.com",
        lead_status="opted_out",
    )
    # 3. Lead without email
    lead_no_email = Lead(
        organization_id=org_one.id,
        first_name="No",
        last_name="Email",
        email=None,
        company_name="Missing Email Inc",
    )
    db_session.add_all([c_valid, c_suppressed, lead_no_email])
    db_session.commit()

    # Add all 3 to list
    contact_list_service.add_members_to_list(
        db_session, org_one.id, cl.id, contact_ids=[c_valid.id, c_suppressed.id], lead_ids=[lead_no_email.id]
    )

    # Create Campaign
    campaign = Campaign(
        organization_id=org_one.id,
        name="Q4 Enterprise Outreach",
        type="sales_outbound",
        status="draft",
    )
    db_session.add(campaign)
    db_session.commit()

    # Attach list to campaign
    attach_res = contact_list_service.attach_list_to_campaign(
        db_session, org_one.id, campaign.id, cl.id
    )

    assert attach_res.newly_enrolled_count == 1  # Only c_valid
    assert attach_res.suppressed_opt_out_count == 1  # c_suppressed skipped
    assert attach_res.unresolved_email_count == 1  # lead_no_email skipped
    assert len(attach_res.unresolved_members) == 1

    # Verify CampaignContact has only 1 enrollment in queued status
    enrollments = (
        db_session.query(CampaignContact)
        .filter(CampaignContact.campaign_id == campaign.id)
        .all()
    )
    assert len(enrollments) == 1
    assert enrollments[0].contact_id == c_valid.id
    assert enrollments[0].enrollment_status == "queued"
    assert enrollments[0].current_step == 0


def test_sync_new_members_delta(db_session, org_one):
    cl = contact_list_service.create_contact_list(
        db_session, org_one.id, ContactListCreate(name="Dynamic Growth List")
    )
    c1 = Contact(organization_id=org_one.id, first_name="Early", last_name="Bird", email="early@co.com")
    db_session.add(c1)
    db_session.commit()

    contact_list_service.add_members_to_list(db_session, org_one.id, cl.id, contact_ids=[c1.id])

    campaign = Campaign(organization_id=org_one.id, name="Nurture Sequence", type="sales_outbound", status="draft")
    db_session.add(campaign)
    db_session.commit()

    # Attach list
    contact_list_service.attach_list_to_campaign(db_session, org_one.id, campaign.id, cl.id)

    # Advance c1 step manually to simulate progress
    cc1 = db_session.query(CampaignContact).filter(CampaignContact.contact_id == c1.id).first()
    cc1.current_step = 2
    cc1.enrollment_status = "in_progress"
    db_session.commit()

    # Now add c2 to the list
    c2 = Contact(organization_id=org_one.id, first_name="Late", last_name="Arrival", email="late@co.com")
    db_session.add(c2)
    db_session.commit()
    contact_list_service.add_members_to_list(db_session, org_one.id, cl.id, contact_ids=[c2.id])

    # Explicit Sync
    sync_res = contact_list_service.sync_list_to_campaign(db_session, org_one.id, campaign.id, cl.id)
    assert sync_res.newly_enrolled_count == 1
    assert sync_res.already_enrolled_count == 1

    # Invariant: c1 step progress was NOT reset!
    db_session.refresh(cc1)
    assert cc1.current_step == 2
    assert cc1.enrollment_status == "in_progress"

    # c2 is queued at step 0
    cc2 = db_session.query(CampaignContact).filter(CampaignContact.contact_id == c2.id).first()
    assert cc2.current_step == 0
    assert cc2.enrollment_status == "queued"


def test_detach_list_preserves_campaign_contacts(db_session, org_one):
    cl = contact_list_service.create_contact_list(db_session, org_one.id, ContactListCreate(name="To Detach"))
    c = Contact(organization_id=org_one.id, first_name="Stay", last_name="Enrolled", email="stay@co.com")
    db_session.add(c)
    db_session.commit()

    contact_list_service.add_members_to_list(db_session, org_one.id, cl.id, contact_ids=[c.id])

    campaign = Campaign(organization_id=org_one.id, name="Test Campaign", type="sales_outbound")
    db_session.add(campaign)
    db_session.commit()

    contact_list_service.attach_list_to_campaign(db_session, org_one.id, campaign.id, cl.id)
    assert db_session.query(CampaignList).count() == 1
    assert db_session.query(CampaignContact).count() == 1

    # Detach
    detached = contact_list_service.detach_list_from_campaign(db_session, org_one.id, campaign.id, cl.id)
    assert detached is True
    assert db_session.query(CampaignList).count() == 0

    # Invariant: CampaignContact remains enrolled!
    assert db_session.query(CampaignContact).count() == 1


def test_list_reuse_across_multiple_campaigns(db_session, org_one):
    cl = contact_list_service.create_contact_list(db_session, org_one.id, ContactListCreate(name="Multi Use List"))
    c = Contact(organization_id=org_one.id, first_name="Reusable", last_name="Contact", email="reusable@co.com")
    db_session.add(c)

    camp_a = Campaign(organization_id=org_one.id, name="Email Campaign A", type="sales_outbound")
    camp_b = Campaign(organization_id=org_one.id, name="Email Campaign B", type="sales_outbound")
    db_session.add_all([camp_a, camp_b])
    db_session.commit()

    contact_list_service.add_members_to_list(db_session, org_one.id, cl.id, contact_ids=[c.id])

    # Attach to both campaigns
    res_a = contact_list_service.attach_list_to_campaign(db_session, org_one.id, camp_a.id, cl.id)
    res_b = contact_list_service.attach_list_to_campaign(db_session, org_one.id, camp_b.id, cl.id)

    assert res_a.newly_enrolled_count == 1
    assert res_b.newly_enrolled_count == 1

    # Contact is enrolled in both campaigns independently
    total_enrollments = db_session.query(CampaignContact).filter(CampaignContact.contact_id == c.id).count()
    assert total_enrollments == 2


@pytest.mark.asyncio
async def test_api_contact_list_crud_and_members(db_session):
    async with make_client() as client:
        token = await register_tenant(client, "listmanager@example.com", "List Manager Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create list
        create_resp = await client.post(
            "/api/v1/lists",
            json={"name": "Enterprise FinTech Leads", "description": "High intent enterprise leads"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        list_id = data["id"]
        assert data["name"] == "Enterprise FinTech Leads"
        assert data["member_count"] == 0

        # 2. Duplicate name rejection (409)
        dup_resp = await client.post(
            "/api/v1/lists",
            json={"name": "Enterprise FinTech Leads"},
            headers=headers,
        )
        assert dup_resp.status_code == 409

        # 3. List lists (catalog)
        cat_resp = await client.get("/api/v1/lists", headers=headers)
        assert cat_resp.status_code == 200
        assert cat_resp.json()["total"] == 1

        # 4. Update list
        put_resp = await client.put(
            f"/api/v1/lists/{list_id}",
            json={"name": "Global FinTech Prospects", "description": "Updated description"},
            headers=headers,
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["name"] == "Global FinTech Prospects"

        # 5. Create a CRM Contact
        c_resp = await client.post(
            "/api/v1/contacts",
            json={"email": "sarah@fintech.com", "first_name": "Sarah", "last_name": "Connor"},
            headers=headers,
        )
        assert c_resp.status_code == 201
        contact_id = c_resp.json()["id"]

        # 6. Add Contact to List
        add_resp = await client.post(
            f"/api/v1/lists/{list_id}/members",
            json={"contact_ids": [contact_id], "lead_ids": []},
            headers=headers,
        )
        assert add_resp.status_code == 200
        assert add_resp.json()["added_count"] == 1

        # 7. List members
        mem_resp = await client.get(f"/api/v1/lists/{list_id}/members", headers=headers)
        assert mem_resp.status_code == 200
        members_data = mem_resp.json()
        assert members_data["total"] == 1
        member_id = members_data["items"][0]["id"]
        assert members_data["items"][0]["email"] == "sarah@fintech.com"
        assert members_data["items"][0]["has_valid_email"] is True

        # 8. Get List Detail with metrics
        detail_resp = await client.get(f"/api/v1/lists/{list_id}", headers=headers)
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["member_count"] == 1
        assert detail["valid_email_count"] == 1
        assert detail["unresolved_email_count"] == 0

        # 9. Remove Member
        del_mem = await client.delete(f"/api/v1/lists/{list_id}/members/{member_id}", headers=headers)
        assert del_mem.status_code == 204

        # Member count now 0
        mem_after = await client.get(f"/api/v1/lists/{list_id}/members", headers=headers)
        assert mem_after.json()["total"] == 0

        # Contact still exists in CRM!
        c_check = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
        assert c_check.status_code == 200

        # 10. Delete List
        del_list = await client.delete(f"/api/v1/lists/{list_id}", headers=headers)
        assert del_list.status_code == 204


@pytest.mark.asyncio
async def test_api_campaign_list_attachment_and_sync(db_session):
    async with make_client() as client:
        token = await register_tenant(client, "campaignlists@example.com", "Campaign Lists Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create list
        list_resp = await client.post(
            "/api/v1/lists",
            json={"name": "SaaS Execs"},
            headers=headers,
        )
        list_id = list_resp.json()["id"]

        # 2. Create contact & add to list
        c_resp = await client.post(
            "/api/v1/contacts",
            json={"email": "exec1@saas.com", "first_name": "Exec", "last_name": "One"},
            headers=headers,
        )
        cid1 = c_resp.json()["id"]
        await client.post(
            f"/api/v1/lists/{list_id}/members",
            json={"contact_ids": [cid1]},
            headers=headers,
        )

        # 3. Create Campaign
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Outbound Execs 2026", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        # 4. Attach list to campaign
        attach_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/lists",
            json={"contact_list_id": list_id},
            headers=headers,
        )
        assert attach_resp.status_code == 200
        attach_data = attach_resp.json()
        assert attach_data["newly_enrolled_count"] == 1
        assert attach_data["already_enrolled_count"] == 0

        # 5. List attached lists
        att_lists = await client.get(f"/api/v1/campaigns/{camp_id}/lists", headers=headers)
        assert att_lists.status_code == 200
        assert len(att_lists.json()) == 1

        # 6. Sync again without adding new members -> 0 newly enrolled
        sync1 = await client.post(f"/api/v1/campaigns/{camp_id}/lists/{list_id}/sync", headers=headers)
        assert sync1.status_code == 200
        assert sync1.json()["newly_enrolled_count"] == 0
        assert sync1.json()["already_enrolled_count"] == 1

        # 7. Add second contact to list
        c_resp2 = await client.post(
            "/api/v1/contacts",
            json={"email": "exec2@saas.com", "first_name": "Exec", "last_name": "Two"},
            headers=headers,
        )
        cid2 = c_resp2.json()["id"]
        await client.post(
            f"/api/v1/lists/{list_id}/members",
            json={"contact_ids": [cid2]},
            headers=headers,
        )

        # 8. Sync delta -> 1 newly enrolled
        sync2 = await client.post(f"/api/v1/campaigns/{camp_id}/lists/{list_id}/sync", headers=headers)
        assert sync2.status_code == 200
        assert sync2.json()["newly_enrolled_count"] == 1
        assert sync2.json()["already_enrolled_count"] == 1

        # 9. Detach list from campaign
        detach = await client.delete(f"/api/v1/campaigns/{camp_id}/lists/{list_id}", headers=headers)
        assert detach.status_code == 204

        # List is detached
        att_lists_after = await client.get(f"/api/v1/campaigns/{camp_id}/lists", headers=headers)
        assert len(att_lists_after.json()) == 0


def test_sync_source_and_category_lists(db_session, org_one, org_two):
    # Setup leads in Org 1 with various sources & industries
    l_hs = Lead(
        organization_id=org_one.id,
        first_name="Hub",
        last_name="Spot",
        email="hub@company.com",
        source="hubspot",
        company_name="Hub Company",
        industry="Financial Services",
    )
    l_csv = Lead(
        organization_id=org_one.id,
        first_name="Csv",
        last_name="Lead",
        email="csv@company.com",
        source="csv_import",
        company_name="CSV Company",
        industry="Financial Services",
    )
    l_manual = Lead(
        organization_id=org_one.id,
        first_name="Manual",
        last_name="Lead",
        email="manual@company.com",
        source="manual",
        company_name="Manual Co",
        industry=None,  # No industry -> left unassigned
    )
    l_voice = Lead(
        organization_id=org_one.id,
        first_name="Voice",
        last_name="Lead",
        email=None,
        source="retell_voice_call",
        company_name="Voice Co",
    )
    # Lead in Org 2 to check tenant isolation
    l_org2 = Lead(
        organization_id=org_two.id,
        first_name="Other",
        last_name="Org",
        email="other@org2.com",
        source="hubspot",
        company_name="Other Org Co",
    )
    db_session.add_all([l_hs, l_csv, l_manual, l_voice, l_org2])
    db_session.commit()

    # Sync sources for Org 1
    res = contact_list_service.sync_source_and_category_lists(db_session, org_one.id)
    assert res["total_lists_synced"] == 4  # HubSpot Contacts, CSV Imports, Manually Added Leads, Financial Services
    assert res["total_new_memberships"] == 5  # 3 sources (1 each) + Financial Services (2 leads)

    # Verify lists created
    lists, total = contact_list_service.list_contact_lists(db_session, org_one.id)
    assert total == 4
    list_names = {l.name: l for l in lists}

    assert "HubSpot Contacts" in list_names
    assert list_names["HubSpot Contacts"].member_count == 1
    assert list_names["HubSpot Contacts"].type == "source"

    assert "CSV Imports" in list_names
    assert list_names["CSV Imports"].member_count == 1
    assert list_names["CSV Imports"].type == "source"

    assert "Manually Added Leads" in list_names
    assert list_names["Manually Added Leads"].member_count == 1
    assert list_names["Manually Added Leads"].type == "source"

    assert "Financial Services" in list_names
    assert list_names["Financial Services"].member_count == 2
    assert list_names["Financial Services"].type == "industry"

    # Invariant: Idempotent re-sync does not create duplicate lists or duplicate memberships
    res_second = contact_list_service.sync_source_and_category_lists(db_session, org_one.id)
    assert res_second["total_new_memberships"] == 0

    # Invariant: Tenant 2 has no lists
    lists_org2, total_org2 = contact_list_service.list_contact_lists(db_session, org_two.id)
    assert total_org2 == 0


