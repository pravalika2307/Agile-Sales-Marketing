"""Regression tests for Lead <-> CRM Contact association, search, and campaign enrollment consistency."""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.lead import Lead
from app.models.crm import Contact, Company
from app.models.campaign import Campaign, CampaignContact
from app.models.outreach import Outreach
from app.models.call_record import CallRecord


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


def make_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_manual_lead_creation_creates_and_associates_crm_contact(test_db_session):
    """
    Creating a lead manually via POST /api/v1/leads must automatically create and associate
    a CRM Contact and Company record within the authenticated organization.
    """
    async with make_client() as client:
        token = await register_tenant(client, "lead_crm_assoc@example.com", "Assoc Org")
        headers = {"Authorization": f"Bearer {token}"}

        lead_payload = {
            "first_name": "Devika",
            "last_name": "Sharma",
            "email": "devika.sharma@example-fin.com",
            "company_name": "Fintech Global",
            "company_domain": "example-fin.com",
            "job_title": "VP Engineering",
            "source": "manual",
        }

        resp = await client.post("/api/v1/leads", json=lead_payload, headers=headers)
        assert resp.status_code == 201, resp.text
        lead_data = resp.json()

        assert lead_data["contact_id"] is not None
        assert lead_data["company_id"] is not None

        # Verify the created CRM contact is accessible via contacts API
        contacts_resp = await client.get("/api/v1/contacts", headers=headers)
        assert contacts_resp.status_code == 200
        contacts = contacts_resp.json()
        matching = [c for c in contacts if c["email"] == "devika.sharma@example-fin.com"]
        assert len(matching) == 1
        assert matching[0]["id"] == lead_data["contact_id"]
        assert matching[0]["first_name"] == "Devika"
        assert matching[0]["last_name"] == "Sharma"


@pytest.mark.asyncio
async def test_manual_lead_creation_reuses_existing_crm_contact_without_duplication(test_db_session):
    """
    If a CRM Contact already exists with the given email, manual lead creation must link to it
    and NOT create duplicate contact records.
    """
    async with make_client() as client:
        token = await register_tenant(client, "reuse_contact@example.com", "Reuse Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Directly create a CRM Contact first
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Arjun",
                "last_name": "Mehta",
                "email": "arjun.mehta@corp.com",
                "job_title": "Director",
            },
            headers=headers,
        )
        assert cont_resp.status_code == 201
        existing_contact_id = cont_resp.json()["id"]

        # 2. Create a lead with the same email
        lead_resp = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Arjun",
                "last_name": "Mehta",
                "email": "arjun.mehta@corp.com",
                "company_name": "Corp Inc",
            },
            headers=headers,
        )
        assert lead_resp.status_code == 201
        assert lead_resp.json()["contact_id"] == existing_contact_id

        # 3. Ensure no duplicate contact was added
        contacts_list = await client.get("/api/v1/contacts", headers=headers)
        matching = [c for c in contacts_list.json() if c["email"] == "arjun.mehta@corp.com"]
        assert len(matching) == 1


@pytest.mark.asyncio
async def test_search_by_email_and_name_surfaces_all_matching_leads_without_hardcoded_exclusion(test_db_session):
    """
    Searching leads by name or email must surface all matching records, even with exclude_test=true,
    without arbitrary hardcoded email suppression.
    """
    async with make_client() as client:
        token = await register_tenant(client, "search_leads@example.com", "Search Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two distinct leads with the same first name but different email domains
        await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Kavita",
                "last_name": "Reddy",
                "email": "kavita.work@acme.com",
                "company_name": "Acme",
            },
            headers=headers,
        )
        await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Kavita",
                "last_name": "Reddy",
                "email": "kavitareddy@personal.com",
                "company_name": "Personal Co",
            },
            headers=headers,
        )

        # Search by name with exclude_test=true
        search_resp = await client.get("/api/v1/leads?search=kavita&exclude_test=true", headers=headers)
        assert search_resp.status_code == 200
        items = search_resp.json()["items"]
        emails = {item["email"] for item in items}
        assert "kavita.work@acme.com" in emails
        assert "kavitareddy@personal.com" in emails


@pytest.mark.asyncio
async def test_enrollment_modal_contacts_visibility_and_enrollment_distinction(test_db_session):
    """
    Contacts associated with distinct leads (e.g. work vs gmail) must both be visible in the
    contacts endpoint, and existing campaign enrollment of one must NOT mark the other as enrolled.
    """
    async with make_client() as client:
        token = await register_tenant(client, "enroll_distinction@example.com", "Enroll Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create lead 1 (work) and lead 2 (personal)
        lead1 = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Same",
                "last_name": "Person",
                "email": "same.work@enterprise.com",
                "company_name": "Enterprise",
            },
            headers=headers,
        )
        lead2 = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Same",
                "last_name": "Person",
                "email": "same.personal@gmail.com",
                "company_name": "Personal",
            },
            headers=headers,
        )
        cid1 = lead1.json()["contact_id"]
        cid2 = lead2.json()["contact_id"]
        assert cid1 != cid2

        # Create a campaign and enroll ONLY contact 1
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Outbound Alpha", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        enroll_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/contacts/{cid1}",
            headers=headers,
        )
        assert enroll_resp.status_code == 201

        # Fetch enrolled contacts for the campaign
        camp_contacts_resp = await client.get(
            f"/api/v1/campaigns/{camp_id}/contacts",
            headers=headers,
        )
        assert camp_contacts_resp.status_code == 200
        enrolled_ids = {cc["contact_id"] for cc in camp_contacts_resp.json()}

        assert cid1 in enrolled_ids
        assert cid2 not in enrolled_ids  # Contact 2 remains un-enrolled and available


@pytest.mark.asyncio
async def test_duplicate_lead_email_rejected_within_same_org_allowed_across_tenants(test_db_session):
    """Duplicate email within same organization is rejected (409), but allowed across tenants."""
    async with make_client() as client:
        token_a = await register_tenant(client, "tenant_a_dup@example.com", "Tenant A")
        token_b = await register_tenant(client, "tenant_b_dup@example.com", "Tenant B")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        payload = {
            "first_name": "Iso",
            "last_name": "Late",
            "email": "iso.late@example-corp.com",
            "company_name": "Corp",
        }

        # Tenant A creates lead
        resp1 = await client.post("/api/v1/leads", json=payload, headers=headers_a)
        assert resp1.status_code == 201

        # Tenant A duplicates same email -> 409
        resp2 = await client.post("/api/v1/leads", json=payload, headers=headers_a)
        assert resp2.status_code == 409

        # Tenant B creates same email -> 201 (tenant isolation)
        resp3 = await client.post("/api/v1/leads", json=payload, headers=headers_b)
        assert resp3.status_code == 201


@pytest.mark.asyncio
async def test_distinction_between_lead_record_and_outreach_record(test_db_session):
    """Creating a lead does NOT create an outreach record; outreaches are created upon sequence planning/send."""
    async with make_client() as client:
        token = await register_tenant(client, "outreach_dist@example.com", "Outreach Org")
        headers = {"Authorization": f"Bearer {token}"}

        lead_resp = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "LeadOnly",
                "last_name": "User",
                "email": "leadonly@example.com",
                "company_name": "Example Corp",
            },
            headers=headers,
        )
        assert lead_resp.status_code == 201

        # Check outreaches for this organization - must be 0
        outreach_resp = await client.get("/api/v1/outreach", headers=headers)
        assert outreach_resp.status_code == 200
        assert len(outreach_resp.json()) == 0


@pytest.mark.asyncio
async def test_complete_end_to_end_lead_to_campaign_enrollment_and_preview_workflow(test_db_session):
    """
    Comprehensive test covering all 13 core requirements:
    1. Manually create a new lead with email
    2. Lead persists in database
    3. Associated CRM contact exists
    4. Contact appears in campaign enrollment search
    5. Searching by email works
    6. Searching by name (first, last, full, company) works
    7. Enroll contact into selected campaign
    8. Enrollment persists and campaign preview resolves variables accurately
    9. Enroll into a second campaign independently
    10. Reuse existing contact safely
    11. Cross-tenant isolation prevents exposure and enrollment
    12. Failed operations report errors (invalid UUID, duplicate enrollment)
    13. Zero automated emails or calls triggered
    """
    async with make_client() as client:
        # Register primary tenant
        token = await register_tenant(client, "e2e_owner@innovate-corp.com", "Innovate Corp Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Manually create a new lead with an email address
        create_lead_resp = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Priya",
                "last_name": "Nair",
                "email": "priya.nair@innovate-corp.com",
                "phone": "+1-555-0144",
                "company_name": "Innovate Technologies",
                "company_domain": "innovate-corp.com",
                "job_title": "Chief Technology Officer",
                "industry": "Technology",
                "source": "manual",
            },
            headers=headers,
        )
        assert create_lead_resp.status_code == 201, create_lead_resp.text
        lead_data = create_lead_resp.json()
        lead_id = lead_data["id"]

        # 2. Verify lead persists in database
        get_lead_resp = await client.get(f"/api/v1/leads/{lead_id}", headers=headers)
        assert get_lead_resp.status_code == 200
        persisted_lead = get_lead_resp.json()
        assert persisted_lead["email"] == "priya.nair@innovate-corp.com"
        assert persisted_lead["company_name"] == "Innovate Technologies"
        assert persisted_lead["first_name"] == "Priya"
        assert persisted_lead["last_name"] == "Nair"

        # 3. Verify appropriate CRM Contact exists and is associated
        contact_id = persisted_lead["contact_id"]
        assert contact_id is not None
        get_contact_resp = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
        assert get_contact_resp.status_code == 200
        crm_contact = get_contact_resp.json()
        assert crm_contact["email"] == "priya.nair@innovate-corp.com"
        assert crm_contact["first_name"] == "Priya"
        assert crm_contact["last_name"] == "Nair"
        assert crm_contact["company"]["name"] == "Innovate Technologies"

        # 4. Verify contact appears in campaign enrollment search (list contacts)
        list_contacts_resp = await client.get("/api/v1/contacts?limit=50", headers=headers)
        assert list_contacts_resp.status_code == 200
        contact_ids = [c["id"] for c in list_contacts_resp.json()]
        assert contact_id in contact_ids

        # 5. Verify searching by email works
        email_search_resp = await client.get(
            "/api/v1/contacts?search=priya.nair@innovate-corp.com",
            headers=headers,
        )
        assert email_search_resp.status_code == 200
        email_matches = email_search_resp.json()
        assert len(email_matches) == 1
        assert email_matches[0]["id"] == contact_id

        # 6. Verify searching by first name, last name, full name, and company works
        # Search by first name
        first_search = await client.get("/api/v1/contacts?search=Priya", headers=headers)
        assert any(c["id"] == contact_id for c in first_search.json())

        # Search by last name
        last_search = await client.get("/api/v1/contacts?search=Nair", headers=headers)
        assert any(c["id"] == contact_id for c in last_search.json())

        # Search by full name
        full_search = await client.get("/api/v1/contacts?search=Priya%20Nair", headers=headers)
        assert any(c["id"] == contact_id for c in full_search.json())

        # Search by company name
        company_search = await client.get("/api/v1/contacts?search=Innovate%20Technologies", headers=headers)
        assert any(c["id"] == contact_id for c in company_search.json())

        # 7. Create Campaign A and enroll the contact
        camp_a_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Q4 Enterprise Growth", "type": "sales_outbound"},
            headers=headers,
        )
        assert camp_a_resp.status_code == 201
        camp_a_id = camp_a_resp.json()["id"]

        enroll_a_resp = await client.post(
            f"/api/v1/campaigns/{camp_a_id}/contacts/bulk",
            json={"contact_ids": [contact_id]},
            headers=headers,
        )
        assert enroll_a_resp.status_code == 200
        enroll_a_data = enroll_a_resp.json()
        assert contact_id in enroll_a_data["enrolled"]
        assert enroll_a_data["already_enrolled"] == []
        assert enroll_a_data["rejected"] == []

        # 8. Verify enrollment persists and appears in campaign
        camp_a_contacts = await client.get(f"/api/v1/campaigns/{camp_a_id}/contacts", headers=headers)
        assert camp_a_contacts.status_code == 200
        enrolled_contacts_a = camp_a_contacts.json()
        assert len(enrolled_contacts_a) == 1
        assert enrolled_contacts_a[0]["contact_id"] == contact_id
        assert enrolled_contacts_a[0]["enrollment_status"] == "queued"
        assert enrolled_contacts_a[0]["contact"]["email"] == "priya.nair@innovate-corp.com"

        # Verify campaign preview resolves personalization variables using the selected contact's actual data
        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp_a_id}/workflow/preview-template",
            json={
                "contact_id": contact_id,
                "subject_template": "Executive Briefing for {contact.first_name}",
                "body_template": "Hello {contact.first_name} {contact.last_name}, I saw your leadership at {contact.company}. Contact email: {contact.email} from {sender.company_name}.",
                "sender_company_name": "Agile Sales & Marketing",
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview_data = prev_resp.json()
        assert preview_data["is_sample"] is False
        assert preview_data["rendered_subject"] == "Executive Briefing for Priya"
        assert preview_data["rendered_body"] == "Hello Priya Nair, I saw your leadership at Innovate Technologies. Contact email: priya.nair@innovate-corp.com from Agile Sales & Marketing."
        assert preview_data["unresolved_placeholders"] == []

        # 9. Verify the contact can be found and enrolled in a second eligible campaign independently
        camp_b_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Product Launch Outreach", "type": "hybrid"},
            headers=headers,
        )
        assert camp_b_resp.status_code == 201
        camp_b_id = camp_b_resp.json()["id"]

        enroll_b_resp = await client.post(
            f"/api/v1/campaigns/{camp_b_id}/contacts/bulk",
            json={"contact_ids": [contact_id]},
            headers=headers,
        )
        assert enroll_b_resp.status_code == 200
        assert contact_id in enroll_b_resp.json()["enrolled"]

        camp_b_contacts = await client.get(f"/api/v1/campaigns/{camp_b_id}/contacts", headers=headers)
        assert camp_b_contacts.status_code == 200
        assert any(c["contact_id"] == contact_id for c in camp_b_contacts.json())

        # 10. Verify that an existing contact with the same email is reused safely
        # Create an existing contact first
        pre_contact = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Rahul",
                "last_name": "Kapoor",
                "email": "rahul.kapoor@techcorp.io",
                "job_title": "VP Marketing",
            },
            headers=headers,
        )
        assert pre_contact.status_code == 201
        pre_contact_id = pre_contact.json()["id"]

        # Now create lead with same email
        lead_reused = await client.post(
            "/api/v1/leads",
            json={
                "first_name": "Rahul",
                "last_name": "Kapoor",
                "email": "rahul.kapoor@techcorp.io",
                "company_name": "TechCorp",
            },
            headers=headers,
        )
        assert lead_reused.status_code == 201
        assert lead_reused.json()["contact_id"] == pre_contact_id

        # Verify no duplicate contact was created
        all_contacts = await client.get("/api/v1/contacts?search=rahul.kapoor@techcorp.io", headers=headers)
        assert len(all_contacts.json()) == 1

        # 11. Verify contacts belonging to another organization cannot be exposed or enrolled
        token_b = await register_tenant(client, "competitor@competitor.com", "Competitor Corp")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant B searches for Priya Nair -> must be 0
        tenant_b_search = await client.get("/api/v1/contacts?search=Priya", headers=headers_b)
        assert len(tenant_b_search.json()) == 0

        # Tenant B creates campaign and tries to enroll Tenant A's contact
        camp_b_other = await client.post(
            "/api/v1/campaigns",
            json={"name": "Competitor Campaign", "type": "sales_outbound"},
            headers=headers_b,
        )
        camp_b_other_id = camp_b_other.json()["id"]

        cross_enroll = await client.post(
            f"/api/v1/campaigns/{camp_b_other_id}/contacts/bulk",
            json={"contact_ids": [contact_id]},
            headers=headers_b,
        )
        assert cross_enroll.status_code == 200
        assert contact_id in cross_enroll.json()["rejected"]
        assert cross_enroll.json()["enrolled"] == []

        # Single enroll endpoint rejects with 404
        cross_single = await client.post(
            f"/api/v1/campaigns/{camp_b_other_id}/contacts/{contact_id}",
            headers=headers_b,
        )
        assert cross_single.status_code == 404

        # 12. Verify failed operations report errors instead of false success
        # Duplicate enrollment in same campaign
        dup_enroll = await client.post(
            f"/api/v1/campaigns/{camp_a_id}/contacts/bulk",
            json={"contact_ids": [contact_id]},
            headers=headers,
        )
        assert dup_enroll.status_code == 200
        assert contact_id in dup_enroll.json()["already_enrolled"]
        assert dup_enroll.json()["enrolled"] == []

        # Single endpoint reports 409
        single_dup = await client.post(
            f"/api/v1/campaigns/{camp_a_id}/contacts/{contact_id}",
            headers=headers,
        )
        assert single_dup.status_code == 409

        # Enrolling to non-existent campaign reports 404
        fake_camp_id = str(uuid.uuid4())
        fake_enroll = await client.post(
            f"/api/v1/campaigns/{fake_camp_id}/contacts/bulk",
            json={"contact_ids": [contact_id]},
            headers=headers,
        )
        assert fake_enroll.status_code == 404

        # 13. Verify that no email or call is triggered by creating a lead or enrolling a contact
        outreach_check = await client.get("/api/v1/outreach", headers=headers)
        assert outreach_check.status_code == 200
        assert len(outreach_check.json()) == 0

        # Verify 0 call records in test DB session
        call_count = test_db_session.query(CallRecord).count()
        assert call_count == 0

