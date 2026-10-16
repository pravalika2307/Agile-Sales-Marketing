"""Automated test suite verifying the three deletion and removal features:
1. Delete individual leads (preserves shared CRM contacts, other campaign memberships, rejects cross-tenant).
2. Remove individual contacts from a specific campaign (preserves global contact, other campaign memberships, cancels pending steps, preserves historical outreaches).
3. Delete individual campaigns (preserves contacts, leads, historical outreaches, rejects cross-tenant).
"""
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
from app.models.campaign_step import CampaignStep
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
    assert resp.status_code == 201, f"Tenant registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ==============================================================================
# FEATURE 1: DELETE INDIVIDUAL LEADS
# ==============================================================================

@pytest.mark.asyncio
async def test_delete_individual_lead_workflow(test_db_session):
    """
    Verifies that:
    - A specific lead can be deleted.
    - The lead no longer appears in the Leads list.
    - Unrelated leads remain intact.
    - Shared CRM Contact is NOT deleted.
    - Other campaign memberships remain intact.
    - Cross-tenant deletion is rejected (404).
    - Deleting a missing lead returns 404.
    """
    async with make_client() as client:
        # 1. Register Tenant A and Tenant B
        token_a = await register_tenant(client, "org_a_user@example.com", "Tenant A Org")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = await register_tenant(client, "org_b_user@example.com", "Tenant B Org")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. Create Lead 1 in Tenant A
        create_lead_1 = await client.post(
            "/api/v1/leads",
            headers=headers_a,
            json={
                "first_name": "Marcus",
                "last_name": "Aurelius",
                "email": "marcus.aurelius@rome-growth.org",
                "company_name": "Roman Empire Corp",
                "jobTitle": "Head of Philosophy",
            },
        )
        assert create_lead_1.status_code == 201
        lead_1_data = create_lead_1.json()
        lead_1_id = lead_1_data["id"]
        contact_1_id = lead_1_data["contact_id"]
        assert contact_1_id is not None

        # 3. Create Lead 2 (unrelated lead) in Tenant A
        create_lead_2 = await client.post(
            "/api/v1/leads",
            headers=headers_a,
            json={
                "first_name": "Seneca",
                "last_name": "Younger",
                "email": "seneca@stoic-advisory.org",
                "company_name": "Stoic Advisory",
            },
        )
        assert create_lead_2.status_code == 201
        lead_2_id = create_lead_2.json()["id"]

        # 4. Enroll Contact 1 into a Campaign in Tenant A
        create_camp = await client.post(
            "/api/v1/campaigns",
            headers=headers_a,
            json={"name": "Executive Outreach", "type": "sales_outbound"},
        )
        assert create_camp.status_code == 201
        camp_id = create_camp.json()["id"]

        enroll_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/contacts/{contact_1_id}",
            headers=headers_a,
        )
        assert enroll_resp.status_code == 201

        # 5. Verify Cross-Tenant deletion is rejected
        cross_tenant_delete = await client.delete(
            f"/api/v1/leads/{lead_1_id}",
            headers=headers_b,
        )
        assert cross_tenant_delete.status_code == 404

        # 6. Delete Lead 1 as Tenant A
        delete_resp = await client.delete(
            f"/api/v1/leads/{lead_1_id}",
            headers=headers_a,
        )
        assert delete_resp.status_code == 204

        # 7. Verify Lead 1 no longer appears in Leads list
        leads_list_resp = await client.get("/api/v1/leads", headers=headers_a)
        assert leads_list_resp.status_code == 200
        items = leads_list_resp.json()["items"]
        lead_ids = [item["id"] for item in items]
        assert lead_1_id not in lead_ids

        # 8. Verify unrelated Lead 2 remains intact in the list
        assert lead_2_id in lead_ids

        # 9. Verify shared CRM Contact was NOT deleted
        contact_in_db = test_db_session.query(Contact).filter(Contact.id == uuid.UUID(contact_1_id)).first()
        assert contact_in_db is not None
        assert contact_in_db.email == "marcus.aurelius@rome-growth.org"

        # 10. Verify campaign membership was NOT deleted
        camp_enrollment = (
            test_db_session.query(CampaignContact)
            .filter(
                CampaignContact.campaign_id == uuid.UUID(camp_id),
                CampaignContact.contact_id == uuid.UUID(contact_1_id),
            )
            .first()
        )
        assert camp_enrollment is not None
        assert camp_enrollment.enrollment_status == "queued"

        # 11. Verify deleting a non-existent or already deleted lead returns 404
        delete_missing = await client.delete(
            f"/api/v1/leads/{lead_1_id}",
            headers=headers_a,
        )
        assert delete_missing.status_code == 404


# ==============================================================================
# FEATURE 2: REMOVE CONTACT FROM SPECIFIC CAMPAIGN
# ==============================================================================

@pytest.mark.asyncio
async def test_remove_contact_from_campaign_workflow(test_db_session):
    """
    Verifies that:
    - A contact enrolled in Campaign A and Campaign B can be removed from Campaign A only.
    - The contact remains in the CRM.
    - The lead remains in the Leads list.
    - Campaign A membership is removed.
    - Campaign B membership remains unchanged.
    - Other contacts in Campaign A remain enrolled.
    - Draft/pending outreach is cancelled and dissociated.
    - Historical sent outreach records are preserved.
    - The contact can be re-enrolled in Campaign A later if desired.
    - Cross-tenant removal attempts are rejected (404).
    """
    async with make_client() as client:
        # 1. Register Tenant A and Tenant B
        token_a = await register_tenant(client, "campaign_admin_a@example.com", "Tenant A Alpha")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = await register_tenant(client, "campaign_admin_b@example.com", "Tenant B Beta")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. Create Lead & Contact 1
        lead_resp = await client.post(
            "/api/v1/leads",
            headers=headers_a,
            json={
                "first_name": "Elena",
                "last_name": "Rostova",
                "email": "elena.rostova@alpha-defense.io",
                "company_name": "Alpha Defense",
            },
        )
        assert lead_resp.status_code == 201
        lead_id = lead_resp.json()["id"]
        contact_id = lead_resp.json()["contact_id"]

        # Create Contact 2
        contact_2_resp = await client.post(
            "/api/v1/contacts",
            headers=headers_a,
            json={
                "first_name": "Dmitri",
                "last_name": "Volkov",
                "email": "dmitri.volkov@alpha-defense.io",
            },
        )
        assert contact_2_resp.status_code == 201
        contact_2_id = contact_2_resp.json()["id"]

        # 3. Create Campaign A and Campaign B
        camp_a = (await client.post("/api/v1/campaigns", headers=headers_a, json={"name": "Campaign A"})).json()
        camp_b = (await client.post("/api/v1/campaigns", headers=headers_a, json={"name": "Campaign B"})).json()
        camp_a_id = camp_a["id"]
        camp_b_id = camp_b["id"]

        # 4. Enroll Contact 1 in Campaign A and Campaign B
        await client.post(f"/api/v1/campaigns/{camp_a_id}/contacts/{contact_id}", headers=headers_a)
        await client.post(f"/api/v1/campaigns/{camp_b_id}/contacts/{contact_id}", headers=headers_a)

        # Enroll Contact 2 in Campaign A
        await client.post(f"/api/v1/campaigns/{camp_a_id}/contacts/{contact_2_id}", headers=headers_a)

        # 5. Add a historical sent outreach and a draft outreach for Contact 1 in Campaign A
        enrollment_a = (
            test_db_session.query(CampaignContact)
            .filter(
                CampaignContact.campaign_id == uuid.UUID(camp_a_id),
                CampaignContact.contact_id == uuid.UUID(contact_id),
            )
            .first()
        )
        assert enrollment_a is not None

        org_a = enrollment_a.campaign.organization_id

        sent_outreach = Outreach(
            organization_id=org_a,
            campaign_id=uuid.UUID(camp_a_id),
            contact_id=uuid.UUID(contact_id),
            campaign_contact_id=enrollment_a.id,
            recipient="elena.rostova@alpha-defense.io",
            channel="email",
            status="sent",
            provider="ses",
            provider_message_id="msg-ses-audit-12345",
        )
        draft_outreach = Outreach(
            organization_id=org_a,
            campaign_id=uuid.UUID(camp_a_id),
            contact_id=uuid.UUID(contact_id),
            campaign_contact_id=enrollment_a.id,
            recipient="elena.rostova@alpha-defense.io",
            channel="email",
            status="draft",
        )
        test_db_session.add_all([sent_outreach, draft_outreach])
        test_db_session.commit()
        sent_outreach_id = sent_outreach.id
        draft_outreach_id = draft_outreach.id

        # 6. Verify cross-tenant removal attempt is rejected
        cross_tenant_remove = await client.delete(
            f"/api/v1/campaigns/{camp_a_id}/contacts/{contact_id}",
            headers=headers_b,
        )
        assert cross_tenant_remove.status_code == 404

        # 7. Remove Contact 1 from Campaign A as Tenant A
        remove_resp = await client.delete(
            f"/api/v1/campaigns/{camp_a_id}/contacts/{contact_id}",
            headers=headers_a,
        )
        assert remove_resp.status_code == 204

        # 8. Verify Contact 1 is no longer in Campaign A
        contacts_a_resp = await client.get(f"/api/v1/campaigns/{camp_a_id}/contacts", headers=headers_a)
        assert contacts_a_resp.status_code == 200
        enrolled_ids_a = [c["contact_id"] for c in contacts_a_resp.json()]
        assert contact_id not in enrolled_ids_a

        # 9. Verify Contact 2 remains enrolled in Campaign A
        assert contact_2_id in enrolled_ids_a

        # 10. Verify Contact 1 remains enrolled in Campaign B
        contacts_b_resp = await client.get(f"/api/v1/campaigns/{camp_b_id}/contacts", headers=headers_a)
        assert contacts_b_resp.status_code == 200
        enrolled_ids_b = [c["contact_id"] for c in contacts_b_resp.json()]
        assert contact_id in enrolled_ids_b

        # 11. Verify Contact remains in the CRM globally
        contact_record = test_db_session.query(Contact).filter(Contact.id == uuid.UUID(contact_id)).first()
        assert contact_record is not None

        # 12. Verify Lead remains in the Leads list
        leads_resp = await client.get("/api/v1/leads", headers=headers_a)
        assert any(l["id"] == lead_id for l in leads_resp.json()["items"])

        # 13. Verify draft outreach was cancelled and historical sent outreach was preserved
        test_db_session.expire_all()
        refreshed_sent = test_db_session.query(Outreach).filter(Outreach.id == sent_outreach_id).first()
        assert refreshed_sent is not None
        assert refreshed_sent.status == "sent"
        assert refreshed_sent.provider_message_id == "msg-ses-audit-12345"
        # campaign_contact_id was detached before deletion so the record was NOT cascade deleted
        assert refreshed_sent.campaign_contact_id is None

        refreshed_draft = test_db_session.query(Outreach).filter(Outreach.id == draft_outreach_id).first()
        assert refreshed_draft is not None
        assert refreshed_draft.status == "cancelled"

        # 14. Verify Contact 1 can be re-enrolled into Campaign A again
        re_enroll_resp = await client.post(
            f"/api/v1/campaigns/{camp_a_id}/contacts/{contact_id}",
            headers=headers_a,
        )
        assert re_enroll_resp.status_code == 201


# ==============================================================================
# FEATURE 3: DELETE AN INDIVIDUAL CAMPAIGN
# ==============================================================================

@pytest.mark.asyncio
async def test_delete_individual_campaign_workflow(test_db_session):
    """
    Verifies that:
    - An isolated campaign can be deleted.
    - The campaign disappears from the active campaign list.
    - Unrelated campaigns remain unchanged.
    - Shared CRM Contacts and leads remain intact globally.
    - Campaign steps and enrollments are deleted (no orphaned executable work).
    - Historical outreach records are preserved in the DB (dissociated).
    - Cross-tenant campaign deletion is rejected (404).
    - Deleting a non-existent campaign returns 404.
    """
    async with make_client() as client:
        # 1. Register Tenant A and Tenant B
        token_a = await register_tenant(client, "org_a_camp@example.com", "Tenant A CampOrg")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = await register_tenant(client, "org_b_camp@example.com", "Tenant B CampOrg")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. Create Lead & Contact in Tenant A
        lead_resp = await client.post(
            "/api/v1/leads",
            headers=headers_a,
            json={
                "first_name": "Tariq",
                "last_name": "Al-Mansoor",
                "email": "tariq@gulf-invest.ae",
                "company_name": "Gulf Investment Partners",
            },
        )
        assert lead_resp.status_code == 201
        lead_id = lead_resp.json()["id"]
        contact_id = lead_resp.json()["contact_id"]

        # 3. Create Campaign 1 and Campaign 2 in Tenant A
        camp_1 = (await client.post("/api/v1/campaigns", headers=headers_a, json={"name": "Campaign One Target"})).json()
        camp_2 = (await client.post("/api/v1/campaigns", headers=headers_a, json={"name": "Campaign Two Keep"})).json()
        camp_1_id = camp_1["id"]
        camp_2_id = camp_2["id"]

        # 4. Enroll contact in both campaigns
        await client.post(f"/api/v1/campaigns/{camp_1_id}/contacts/{contact_id}", headers=headers_a)
        await client.post(f"/api/v1/campaigns/{camp_2_id}/contacts/{contact_id}", headers=headers_a)

        # 5. Add historical outreach in Campaign 1
        org_a = uuid.UUID(test_db_session.query(Campaign).filter_by(id=uuid.UUID(camp_1_id)).first().organization_id.hex)
        hist_outreach = Outreach(
            organization_id=org_a,
            campaign_id=uuid.UUID(camp_1_id),
            contact_id=uuid.UUID(contact_id),
            recipient="tariq@gulf-invest.ae",
            channel="email",
            status="sent",
            provider="ses",
            provider_message_id="ses-permanent-audit-999",
        )
        test_db_session.add(hist_outreach)
        test_db_session.commit()
        hist_outreach_id = hist_outreach.id

        # 6. Verify cross-tenant deletion attempt is rejected (404)
        cross_tenant_del = await client.delete(
            f"/api/v1/campaigns/{camp_1_id}",
            headers=headers_b,
        )
        assert cross_tenant_del.status_code == 404

        # 7. Delete Campaign 1 as Tenant A
        del_resp = await client.delete(
            f"/api/v1/campaigns/{camp_1_id}",
            headers=headers_a,
        )
        assert del_resp.status_code == 204

        # 8. Verify Campaign 1 disappears from active list
        list_resp = await client.get("/api/v1/campaigns", headers=headers_a)
        assert list_resp.status_code == 200
        visible_ids = [c["id"] for c in list_resp.json()]
        assert camp_1_id not in visible_ids

        # 9. Verify Campaign 2 remains in the active list
        assert camp_2_id in visible_ids

        # 10. Verify shared CRM Contact and Lead remain intact
        contact_record = test_db_session.query(Contact).filter_by(id=uuid.UUID(contact_id)).first()
        assert contact_record is not None
        assert contact_record.email == "tariq@gulf-invest.ae"

        lead_record = test_db_session.query(Lead).filter_by(id=uuid.UUID(lead_id)).first()
        assert lead_record is not None

        # 11. Verify Campaign 1 steps and enrollments are deleted (no orphaned steps or pending work)
        orphan_steps = test_db_session.query(CampaignStep).filter_by(campaign_id=uuid.UUID(camp_1_id)).all()
        assert len(orphan_steps) == 0

        orphan_enrollments = test_db_session.query(CampaignContact).filter_by(campaign_id=uuid.UUID(camp_1_id)).all()
        assert len(orphan_enrollments) == 0

        # 12. Verify historical audit outreach record is preserved (dissociated from deleted campaign)
        test_db_session.expire_all()
        persisted_outreach = test_db_session.query(Outreach).filter_by(id=hist_outreach_id).first()
        assert persisted_outreach is not None
        assert persisted_outreach.status == "sent"
        assert persisted_outreach.provider_message_id == "ses-permanent-audit-999"
        assert persisted_outreach.campaign_id is None

        # 13. Verify Campaign 2 still has its enrollment intact
        camp_2_enrollments = test_db_session.query(CampaignContact).filter_by(campaign_id=uuid.UUID(camp_2_id)).all()
        assert len(camp_2_enrollments) == 1
        assert camp_2_enrollments[0].contact_id == uuid.UUID(contact_id)

        # 14. Verify deleting a missing campaign returns 404
        missing_resp = await client.delete(
            f"/api/v1/campaigns/{camp_1_id}",
            headers=headers_a,
        )
        assert missing_resp.status_code == 404
