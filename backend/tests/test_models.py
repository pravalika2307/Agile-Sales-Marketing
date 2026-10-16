"""Unit tests for Organization, User, and BusinessProfile domain models."""
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import (
    BusinessProfile,
    Campaign,
    CampaignContact,
    Company,
    Contact,
    Deal,
    Organization,
    Outreach,
    OutreachEvent,
    Pipeline,
    PipelineStage,
    User,
)


@pytest.fixture
def db_session():
    """In-memory SQLite session with table creation for isolated model testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_organization_instantiation(db_session: Session):
    org = Organization(
        name="Acme Growth Inc",
        slug="acme-growth",
        billing_status="trial",
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    assert isinstance(org.id, uuid.UUID)
    assert org.name == "Acme Growth Inc"
    assert org.slug == "acme-growth"
    assert org.billing_status == "trial"
    assert org.created_at is not None
    assert org.updated_at is not None


def test_user_references_organization(db_session: Session):
    org = Organization(name="SaaS Labs", slug="saas-labs")
    db_session.add(org)
    db_session.commit()

    user = User(
        organization_id=org.id,
        email="founder@saaslabs.com",
        hashed_password="hashed_pw_test",
        full_name="Jane Doe",
        role="owner",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.organization_id == org.id
    assert user.organization.name == "SaaS Labs"
    assert user.is_active is True
    assert user in org.users


def test_business_profile_references_organization(db_session: Session):
    org = Organization(name="Alpha Agency", slug="alpha-agency")
    db_session.add(org)
    db_session.commit()

    profile = BusinessProfile(
        organization_id=org.id,
        company_name="Alpha Agency",
        industry="Marketing & Advertising",
        target_icp_description="B2B tech companies with >50 employees",
        value_proposition="We scale outbound revenue pipelines predictably",
        website_url="https://alphaagency.example.com",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    assert profile.organization_id == org.id
    assert profile.company_name == "Alpha Agency"
    assert org.business_profile.id == profile.id


def test_business_profile_one_to_one_constraint(db_session: Session):
    org = Organization(name="Beta Ventures", slug="beta-ventures")
    db_session.add(org)
    db_session.commit()

    profile1 = BusinessProfile(
        organization_id=org.id,
        company_name="Beta Ventures",
    )
    db_session.add(profile1)
    db_session.commit()

    # Second profile with the same organization_id must violate unique constraint
    profile2 = BusinessProfile(
        organization_id=org.id,
        company_name="Beta Ventures Duplicate",
    )
    db_session.add(profile2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_organization_unique_slug_constraint(db_session: Session):
    org1 = Organization(name="Org One", slug="shared-slug")
    db_session.add(org1)
    db_session.commit()

    org2 = Organization(name="Org Two", slug="shared-slug")
    db_session.add(org2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_user_unique_email_constraint(db_session: Session):
    org = Organization(name="Gamma Tech", slug="gamma-tech")
    db_session.add(org)
    db_session.commit()

    user1 = User(
        organization_id=org.id,
        email="duplicate@gamma.com",
        hashed_password="pw1",
        full_name="User One",
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        organization_id=org.id,
        email="duplicate@gamma.com",
        hashed_password="pw2",
        full_name="User Two",
    )
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_pipeline_and_stage_models(db_session: Session):
    org = Organization(name="Delta Tech", slug="delta-tech")
    db_session.add(org)
    db_session.commit()

    pipeline = Pipeline(
        organization_id=org.id,
        name="Sales Pipeline",
        is_default=True,
    )
    db_session.add(pipeline)
    db_session.commit()
    db_session.refresh(pipeline)

    assert pipeline.organization_id == org.id
    assert pipeline.name == "Sales Pipeline"
    assert pipeline.is_default is True

    stage = PipelineStage(
        pipeline_id=pipeline.id,
        name="Discovery",
        order_index=1,
        probability_pct=20,
    )
    db_session.add(stage)
    db_session.commit()
    db_session.refresh(pipeline)

    assert len(pipeline.stages) == 1
    assert pipeline.stages[0].name == "Discovery"


def test_deal_model_relationships(db_session: Session):
    org = Organization(name="Epsilon Inc", slug="epsilon-inc")
    db_session.add(org)
    db_session.commit()

    pipeline = Pipeline(organization_id=org.id, name="Main Flow")
    db_session.add(pipeline)
    db_session.commit()

    stage = PipelineStage(pipeline_id=pipeline.id, name="Qualified", order_index=1, probability_pct=50)
    db_session.add(stage)
    db_session.commit()

    company = Company(organization_id=org.id, name="Test Client")
    db_session.add(company)
    db_session.commit()

    contact = Contact(
        organization_id=org.id,
        company_id=company.id,
        email="client@example.com",
        first_name="Jane",
        last_name="Client",
    )
    db_session.add(contact)
    db_session.commit()

    deal = Deal(
        organization_id=org.id,
        pipeline_stage_id=stage.id,
        company_id=company.id,
        contact_id=contact.id,
        name="Enterprise Subscription",
        amount=12000.00,
        status="open",
    )
    db_session.add(deal)
    db_session.commit()
    db_session.refresh(deal)

    assert deal.organization_id == org.id
    assert deal.pipeline_stage_id == stage.id
    assert deal.company.name == "Test Client"
    assert deal.contact.email == "client@example.com"
    assert deal in org.deals
    assert deal in stage.deals


def test_campaign_and_campaign_contact_models(db_session: Session):
    org = Organization(name="Zeta Agency", slug="zeta-agency")
    db_session.add(org)
    db_session.commit()

    campaign = Campaign(
        organization_id=org.id,
        name="Outbound Lead Gen",
        type="sales_outbound",
        status="draft",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    assert campaign.organization_id == org.id
    assert campaign.status == "draft"
    assert campaign in org.campaigns

    contact = Contact(
        organization_id=org.id,
        email="lead@example.com",
        first_name="Sam",
        last_name="Lead",
    )
    db_session.add(contact)
    db_session.commit()

    enrollment = CampaignContact(
        campaign_id=campaign.id,
        contact_id=contact.id,
        enrollment_status="queued",
    )
    db_session.add(enrollment)
    db_session.commit()
    db_session.refresh(campaign)

    assert len(campaign.campaign_contacts) == 1
    assert campaign.campaign_contacts[0].contact.email == "lead@example.com"
    assert enrollment in contact.campaign_contacts

    # Duplicate enrollment violation
    dup = CampaignContact(
        campaign_id=campaign.id,
        contact_id=contact.id,
        enrollment_status="queued",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_outreach_and_outreach_event_models(db_session: Session):
    org = Organization(name="Theta Corp", slug="theta-corp")
    db_session.add(org)
    db_session.commit()

    campaign = Campaign(organization_id=org.id, name="Cold Outbound", type="sales_outbound")
    contact = Contact(organization_id=org.id, email="prospect@theta.com", first_name="Pat", last_name="Prospect")
    db_session.add_all([campaign, contact])
    db_session.commit()

    enrollment = CampaignContact(campaign_id=campaign.id, contact_id=contact.id)
    db_session.add(enrollment)
    db_session.commit()

    outreach = Outreach(
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=enrollment.id,
        channel="email",
        status="draft",
        subject="Quick question",
        body="Hello Pat",
    )
    db_session.add(outreach)
    db_session.commit()
    db_session.refresh(outreach)

    assert outreach.organization_id == org.id
    assert outreach.status == "draft"
    assert outreach in org.outreaches
    assert outreach in campaign.outreaches
    assert outreach in contact.outreaches
    assert outreach in enrollment.outreaches

    event = OutreachEvent(
        organization_id=org.id,
        outreach_id=outreach.id,
        event_type="created",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(outreach)

    assert len(outreach.events) == 1
    assert outreach.events[0].event_type == "created"
    assert outreach.first_delivered_at is None
    assert outreach.first_opened_at is None
    assert outreach.first_clicked_at is None
    assert outreach.first_replied_at is None
    assert outreach.first_bounced_at is None

    # Verify extended event types are accepted
    for evt_type in ("delivered", "opened", "clicked", "replied", "bounced"):
        evt = OutreachEvent(organization_id=org.id, outreach_id=outreach.id, event_type=evt_type)
        db_session.add(evt)
    db_session.commit()
    db_session.refresh(outreach)
    assert len(outreach.events) == 6
