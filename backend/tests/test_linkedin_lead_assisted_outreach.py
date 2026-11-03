"""Comprehensive regression tests for LinkedIn Assisted-Outreach integration and Lead profile handling."""
import uuid
from typing import Generator
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.normalization import normalize_linkedin_profile_url
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.schemas.lead import LeadCreate, LeadImportRow, LeadUpdate
from app.schemas.linkedin import LinkedInConfirmActionRequest, LinkedInUpdateProspectProfileRequest
from app.services.integrations.linkedin.service import LinkedInIntegrationService
from app.services.lead_generation.service import (
    DuplicateLeadError,
    convert_lead_to_crm,
    create_lead,
    import_leads,
    update_lead,
)
from app.services.lead_qualification.campaign_eligibility import (
    check_lead_campaign_eligibility,
    enroll_qualified_lead_in_campaign,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTesting()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_org(db_session: Session) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name="Agile Receivables Inc",
        slug="agile-receivables",
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def test_user(db_session: Session, test_org: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        email="kunal@agilereceivables.com",
        full_name="Kunal Sadhre",
        hashed_password="mock_hashed_password",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ==============================================================================
# Phase 2: URL Normalization and Validation Tests
# ==============================================================================

def test_normalize_linkedin_profile_url_valid():
    """Test valid LinkedIn profile URLs in various formats are normalized consistently."""
    assert (
        normalize_linkedin_profile_url("https://www.linkedin.com/in/kunal-sadhre")
        == "https://www.linkedin.com/in/kunal-sadhre"
    )
    assert (
        normalize_linkedin_profile_url("http://linkedin.com/in/kunal-sadhre/")
        == "https://www.linkedin.com/in/kunal-sadhre"
    )
    assert (
        normalize_linkedin_profile_url("linkedin.com/in/kunal-sadhre")
        == "https://www.linkedin.com/in/kunal-sadhre"
    )
    assert (
        normalize_linkedin_profile_url("www.linkedin.com/in/kunal-sadhre-123/")
        == "https://www.linkedin.com/in/kunal-sadhre-123"
    )
    assert (
        normalize_linkedin_profile_url("https://in.linkedin.com/in/kunal-sadhre?miniProfileUrn=urn%3Ali")
        == "https://www.linkedin.com/in/kunal-sadhre"
    )
    assert normalize_linkedin_profile_url(None) is None
    assert normalize_linkedin_profile_url("") is None
    assert normalize_linkedin_profile_url("   ") is None


def test_normalize_linkedin_profile_url_invalid():
    """Test invalid or non-profile URLs raise clear, descriptive ValueErrors."""
    with pytest.raises(ValueError, match="Domain must be linkedin.com"):
        normalize_linkedin_profile_url("https://twitter.com/in/kunalsadhre")

    with pytest.raises(ValueError, match="Expected an individual member profile"):
        normalize_linkedin_profile_url("https://www.linkedin.com/company/agile-receivables")

    with pytest.raises(ValueError, match="Must be a personal profile URL"):
        normalize_linkedin_profile_url("https://www.linkedin.com/feed")


# ==============================================================================
# Lead Creation and Editing with LinkedIn Profile URLs
# ==============================================================================

def test_create_lead_with_linkedin_profile_url(db_session: Session, test_org: Organization):
    """Test creating a lead with a valid LinkedIn profile URL."""
    payload = LeadCreate(
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@acmecorp.com",
        company_name="Acme Corp",
        linkedin_profile_url="linkedin.com/in/janedoe",
    )
    lead = create_lead(db_session, test_org, payload)
    assert lead.linkedin_profile_url == "https://www.linkedin.com/in/janedoe"
    assert lead.first_name == "Jane"

    # Verify CRM Contact was automatically linked and has the profile URL
    assert lead.contact_id is not None
    contact = db_session.query(Contact).filter(Contact.id == lead.contact_id).first()
    assert contact is not None
    assert contact.linkedin_profile_url == "https://www.linkedin.com/in/janedoe"
    assert contact.linkedin_url == "https://www.linkedin.com/in/janedoe"


def test_create_lead_without_linkedin_profile_url_optional(db_session: Session, test_org: Organization):
    """Test that LinkedIn profile URL remains completely optional for non-LinkedIn leads."""
    payload = LeadCreate(
        first_name="Bob",
        last_name="Smith",
        email="bob.smith@techflow.com",
        company_name="Techflow Inc",
    )
    lead = create_lead(db_session, test_org, payload)
    assert lead.linkedin_profile_url is None
    assert lead.email == "bob.smith@techflow.com"


def test_update_lead_linkedin_profile_url(db_session: Session, test_org: Organization):
    """Test updating a lead with a LinkedIn profile URL syncs to linked Contact."""
    create_payload = LeadCreate(
        first_name="Alice",
        last_name="Johnson",
        email="alice.j@innovate.com",
        company_name="Innovate Ltd",
    )
    lead = create_lead(db_session, test_org, create_payload)
    assert lead.linkedin_profile_url is None

    update_payload = LeadUpdate(
        linkedin_profile_url="https://www.linkedin.com/in/alice-johnson-innovate",
    )
    updated = update_lead(db_session, test_org, lead.id, update_payload)
    assert updated.linkedin_profile_url == "https://www.linkedin.com/in/alice-johnson-innovate"

    # Verify linked Contact also updated
    contact = db_session.query(Contact).filter(Contact.id == lead.contact_id).first()
    assert contact.linkedin_profile_url == "https://www.linkedin.com/in/alice-johnson-innovate"


# ==============================================================================
# CSV Lead Import with LinkedIn Profile URL
# ==============================================================================

def test_import_leads_with_linkedin_profile_url(db_session: Session, test_org: Organization):
    """Test CSV batch import properly maps and stores LinkedIn profile URLs."""
    rows = [
        LeadImportRow(
            first_name="David",
            last_name="Miller",
            email="david.miller@megacorp.com",
            company_name="MegaCorp",
            linkedin_profile_url="https://www.linkedin.com/in/davidmiller",
        ),
        LeadImportRow(
            first_name="Sarah",
            last_name="Connor",
            email="sarah.c@cyberdyne.com",
            company_name="Cyberdyne",
            linkedin_profile_url=None,
        ),
    ]
    res = import_leads(db_session, test_org, rows)
    assert res.imported_count == 2
    assert res.failed_count == 0

    david = db_session.query(Lead).filter(Lead.email == "david.miller@megacorp.com").first()
    assert david is not None
    assert david.linkedin_profile_url == "https://www.linkedin.com/in/davidmiller"

    sarah = db_session.query(Lead).filter(Lead.email == "sarah.c@cyberdyne.com").first()
    assert sarah is not None
    assert sarah.linkedin_profile_url is None


# ==============================================================================
# Phase 3 & 4: Campaign Enrollment and Assisted Outreach Workspace
# ==============================================================================

def test_campaign_eligibility_and_enrollment_with_linkedin(db_session: Session, test_org: Organization):
    """Test campaign eligibility checks and enrollment for LinkedIn campaigns."""
    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        name="Q4 LinkedIn Assisted Campaign",
        type="sales_outbound",
        status="active",
        workflow_config={
            "nodes": [
                {"id": "node-1", "type": "startNode"},
                {"id": "node-2", "type": "linkedinNode"},
            ]
        },
    )
    db_session.add(campaign)
    db_session.commit()

    # Lead with LinkedIn URL
    lead1 = create_lead(
        db_session,
        test_org,
        LeadCreate(
            first_name="Rachel",
            last_name="Green",
            email="rachel@ralphlauren.com",
            company_name="Ralph Lauren",
            qualification_status="qualified",
            linkedin_profile_url="https://www.linkedin.com/in/rachel-green",
        ),
    )

    # Lead without LinkedIn URL
    lead2 = create_lead(
        db_session,
        test_org,
        LeadCreate(
            first_name="Chandler",
            last_name="Bing",
            email="chandler@transponster.com",
            company_name="Data Analysis Inc",
            qualification_status="qualified",
        ),
    )

    # Check eligibility for lead1 (has LinkedIn URL)
    el1 = check_lead_campaign_eligibility(db_session, test_org, lead1.id, campaign.id)
    assert el1.is_eligible is True
    assert any("LinkedIn profile URL is available" in r for r in el1.reasons)

    # Check eligibility for lead2 (missing LinkedIn URL -> warning notice, but eligible for assisted queue)
    el2 = check_lead_campaign_eligibility(db_session, test_org, lead2.id, campaign.id)
    assert el2.is_eligible is True
    assert any("Notice: Lead is missing a LinkedIn profile URL" in r for r in el2.reasons)

    # Enroll lead1
    enroll1 = enroll_qualified_lead_in_campaign(db_session, test_org, lead1.id, campaign.id)
    assert enroll1.status == "enrolled"    # Prevent accidental duplicate enrollment (raises 400)
    with pytest.raises(HTTPException) as exc_info:
        enroll_qualified_lead_in_campaign(db_session, test_org, lead1.id, campaign.id)
    assert exc_info.value.status_code == 400
    assert "already enrolled" in exc_info.value.detail
def test_linkedin_assisted_queue_and_workspace(
    db_session: Session, test_org: Organization, test_user: User
):
    """Test LinkedIn assisted queue generates personalized notes and provides profile links."""
    service = LinkedInIntegrationService(db=db_session, client=None)

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        name="Strategic Accounts LinkedIn Outreach",
        type="sales_outbound",
        status="active",
    )
    db_session.add(campaign)
    db_session.commit()

    lead = create_lead(
        db_session,
        test_org,
        LeadCreate(
            first_name="Monica",
            last_name="Geller",
            email="monica@alessandros.com",
            company_name="Alessandros Bistro",
            job_title="Head Chef & Owner",
            qualification_status="qualified",
            linkedin_profile_url="https://www.linkedin.com/in/monica-geller",
        ),
    )

    enroll = enroll_qualified_lead_in_campaign(db_session, test_org, lead.id, campaign.id)
    cc_id = enroll.campaign_contact_id
    assert cc_id is not None

    queue_data = service.get_campaign_assisted_queue(test_org, campaign.id)
    assert queue_data["total"] == 1
    assert queue_data["pending_count"] == 1
    item = queue_data["items"][0]

    assert item["full_name"] == "Monica Geller"
    assert item["company_name"] == "Alessandros Bistro"
    assert item["has_linkedin_profile_url"] is True
    assert item["linkedin_url"] == "https://www.linkedin.com/in/monica-geller"
    assert item["linkedin_profile_url"] == "https://www.linkedin.com/in/monica-geller"
    assert "Monica" in item["connection_note"]
    assert len(item["connection_note"]) <= 300
    assert item["outreach_status"] == "pending"


def test_quick_inline_update_prospect_linkedin_url(
    db_session: Session, test_org: Organization, test_user: User
):
    """Test updating a prospect's LinkedIn URL inline from the assisted queue."""
    service = LinkedInIntegrationService(db=db_session, client=None)

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        name="Outreach Campaign",
        type="sales_outbound",
        status="active",
    )
    db_session.add(campaign)
    db_session.commit()

    # Enrolled without profile URL
    lead = create_lead(
        db_session,
        test_org,
        LeadCreate(
            first_name="Ross",
            last_name="Geller",
            email="ross@museum.org",
            company_name="NY Museum of Prehistoric History",
            qualification_status="qualified",
        ),
    )
    enroll = enroll_qualified_lead_in_campaign(db_session, test_org, lead.id, campaign.id)
    cc_id = enroll.campaign_contact_id

    # Queue initially reflects search fallback
    q1 = service.get_campaign_assisted_queue(test_org, campaign.id)
    assert q1["items"][0]["has_linkedin_profile_url"] is False
    assert "search/results" in q1["items"][0]["linkedin_url"]

    # Inline update
    res = service.update_prospect_linkedin_url(
        org=test_org,
        campaign_id=campaign.id,
        campaign_contact_id=cc_id,
        profile_url="linkedin.com/in/dr-ross-geller",
    )
    assert res["success"] is True
    assert res["linkedin_profile_url"] == "https://www.linkedin.com/in/dr-ross-geller"

    # Queue now reflects the real profile URL
    q2 = service.get_campaign_assisted_queue(test_org, campaign.id)
    assert q2["items"][0]["has_linkedin_profile_url"] is True
    assert q2["items"][0]["linkedin_url"] == "https://www.linkedin.com/in/dr-ross-geller"


def test_confirm_assisted_action_persistence_and_distinction(
    db_session: Session, test_org: Organization, test_user: User
):
    """
    Test user confirmation creates an Outreach record with provider='linkedin_assisted'
    and status='sent' (NOT 'delivered' or 'accepted'), preserving compliance boundaries.
    """
    service = LinkedInIntegrationService(db=db_session, client=None)

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        name="Assisted Outreach",
        type="sales_outbound",
        status="active",
    )
    db_session.add(campaign)
    db_session.commit()

    lead = create_lead(
        db_session,
        test_org,
        LeadCreate(
            first_name="Joey",
            last_name="Tribbiani",
            email="joey@actorsguild.com",
            company_name="Days of Our Lives",
            qualification_status="qualified",
            linkedin_profile_url="https://www.linkedin.com/in/joey-tribbiani",
        ),
    )
    enroll = enroll_qualified_lead_in_campaign(db_session, test_org, lead.id, campaign.id)
    cc_id = enroll.campaign_contact_id

    # User confirms sending manual connection request
    confirm_res = service.confirm_assisted_action(
        user=test_user,
        org=test_org,
        campaign_id=campaign.id,
        campaign_contact_id=cc_id,
        action_type="connection_request",
        notes="Sent via personal Chrome tab",
    )
    assert confirm_res["success"] is True
    assert confirm_res["status"] == "sent"

    # Verify Outreach database record
    outreach = (
        db_session.query(Outreach)
        .filter(Outreach.campaign_contact_id == cc_id, Outreach.channel == "linkedin")
        .first()
    )
    assert outreach is not None
    assert outreach.status == "sent"
    assert outreach.provider == "linkedin_assisted"
    # STRICT COMPLIANCE: Must NOT fabricate provider delivery or acceptance
    assert outreach.first_delivered_at is None
    assert outreach.first_replied_at is None
    assert outreach.recipient == "https://www.linkedin.com/in/joey-tribbiani"

    # Verify OutreachEvent audit entry
    events = (
        db_session.query(OutreachEvent)
        .filter(OutreachEvent.outreach_id == outreach.id)
        .all()
    )
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "sent"
    assert ev.event_metadata["mode"] == "assisted_manual"
    assert ev.event_metadata["confirmed_by_user_id"] == str(test_user.id)
