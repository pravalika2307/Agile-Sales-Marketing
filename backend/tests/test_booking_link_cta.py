"""Tests for client-configurable meeting-booking CTA implementation ({booking_link})."""
from __future__ import annotations

import html
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.email_template import EmailTemplate
from app.models.outreach import Outreach
from app.models.tenant import Organization
from app.schemas.email_template import AIEmailGenerateRequest
from app.schemas.outreach import OutreachCreate
from app.schemas.workflow import TemplatePreviewRequest, WorkflowConfig, WorkflowNode
from app.services.campaign_execution.service import execute_campaign
from app.services.campaign_steps.ai_template_service import (
    _build_system_prompt,
    generate_email_template,
)
from app.services.campaign_steps.template_renderer import (
    ensure_booking_cta,
    find_unresolved_placeholders,
    render_email_html,
    render_template,
)
from app.services.organization_config import (
    AGILE_RECEIVABLES_BOOKING_URL,
    MissingBookingUrlError,
    clear_organization_booking_registry,
    get_organization_booking_url,
    register_organization_booking_url,
    require_organization_booking_url,
)
from app.services.outreach.base import MockEmailProvider
from app.services.outreach.service import create_outreach, send_outreach
from app.services.workflow_service import preview_template_content, validate_workflow


# ── Database Fixtures ─────────────────────────────────────────────────────────

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
        clear_organization_booking_registry()


# ── 1. Organization Booking URL Resolution & Tenant Isolation ─────────────────

def test_agile_receivables_resolves_confirmed_cal_com_url(test_db_session: Session):
    """Agile Receivables organization resolves strictly to confirmed https://cal.com/agilereceivables/30min."""
    db = test_db_session
    agile_org = Organization(
        id=uuid.UUID("3de43e6b-6cc0-4391-a061-2faba481bcb8"),
        name="Agile Receivables Org",
        slug="agile-receivables-org",
        billing_status="active",
    )
    db.add(agile_org)
    db.commit()

    # Resolution by instance
    resolved_by_instance = get_organization_booking_url(db, agile_org)
    assert resolved_by_instance == "https://cal.com/agilereceivables/30min"

    # Resolution by UUID
    resolved_by_id = get_organization_booking_url(db, agile_org.id)
    assert resolved_by_id == "https://cal.com/agilereceivables/30min"

    # Resolution by slug
    resolved_by_slug = get_organization_booking_url(db, "agile-receivables-org")
    assert resolved_by_slug == "https://cal.com/agilereceivables/30min"


def test_different_organization_resolves_own_configured_url(test_db_session: Session):
    """Other organizations resolve their own configured booking URL."""
    db = test_db_session
    other_org = Organization(
        id=uuid.uuid4(),
        name="Acme Corporation",
        slug="acme-corp",
        billing_status="active",
    )
    db.add(other_org)
    db.commit()

    custom_url = "https://cal.com/acme-corp/sales-briefing"
    register_organization_booking_url(other_org.id, custom_url)

    resolved = get_organization_booking_url(db, other_org)
    assert resolved == custom_url
    assert resolved != AGILE_RECEIVABLES_BOOKING_URL


def test_strict_tenant_isolation_never_falls_back_to_agile_receivables(test_db_session: Session):
    """An unconfigured organization strictly returns None and never leaks Agile Receivables' URL."""
    db = test_db_session
    unconfigured_org = Organization(
        id=uuid.uuid4(),
        name="Unconfigured Tenant Inc",
        slug="unconfigured-tenant",
        billing_status="active",
    )
    db.add(unconfigured_org)
    db.commit()

    resolved = get_organization_booking_url(db, unconfigured_org)
    assert resolved is None

    # require_organization_booking_url raises MissingBookingUrlError
    with pytest.raises(MissingBookingUrlError) as exc_info:
        require_organization_booking_url(db, unconfigured_org)
    assert "Unconfigured Tenant Inc" in str(exc_info.value)
    assert "{booking_link}" in str(exc_info.value)


# ── 2. CTA Insertion and Duplicate Prevention ────────────────────────────────

def test_automatic_cta_insertion_when_absent():
    """Emails missing a booking link automatically have 'Book a Meeting: {booking_link}' appended."""
    plain_body = "Hi {contact.first_name},\n\nWould you like to connect about our solution?\n\nBest regards,\n{sender_name}"
    rendered = render_template(
        plain_body,
        contact=None,
        booking_link="https://cal.com/agilereceivables/30min",
        enforce_booking_cta=True,
    )
    assert "Book a Meeting: https://cal.com/agilereceivables/30min" in rendered
    assert "Best regards," in rendered
    # Appended before sign-off
    cta_pos = rendered.find("Book a Meeting:")
    signoff_pos = rendered.find("Best regards,")
    assert cta_pos < signoff_pos


def test_no_duplicate_cta_when_token_or_url_already_present():
    """Emails that already incorporate {booking_link} or the booking URL do NOT receive a duplicate CTA."""
    # Case A: Body already has {booking_link}
    body_with_token = (
        "Hi there,\n\nPlease choose a slot on our calendar: {booking_link}\n\n"
        "Best regards,\nSales Team"
    )
    rendered_a = render_template(
        body_with_token,
        contact=None,
        booking_link="https://cal.com/agilereceivables/30min",
        enforce_booking_cta=True,
    )
    assert rendered_a.count("https://cal.com/agilereceivables/30min") == 1
    assert "Book a Meeting:" not in rendered_a  # Preserves author's exact phrase

    # Case B: Body already contains the concrete URL
    body_with_url = (
        "Hi there,\n\nBook a meeting directly: https://cal.com/agilereceivables/30min\n\n"
        "Best regards,\nSales Team"
    )
    rendered_b = render_template(
        body_with_url,
        contact=None,
        booking_link="https://cal.com/agilereceivables/30min",
        enforce_booking_cta=True,
    )
    assert rendered_b.count("https://cal.com/agilereceivables/30min") == 1
    assert rendered_b.count("Book a") == 1


# ── 3. HTML and Plain-Text Rendering ─────────────────────────────────────────

def test_html_and_plain_text_rendering():
    """Plain-text preserves the raw URL; HTML renders a styled, clickable anchor tag with safe escaping."""
    raw_body = (
        "Hi John & Jane,\n\n"
        "We noticed <Acme Corp> has high potential.\n\n"
        "Book a Meeting: https://cal.com/agilereceivables/30min\n\n"
        "Best regards,\nSales Team"
    )
    html_output = render_email_html(raw_body, booking_url="https://cal.com/agilereceivables/30min")

    # Plain text remains intact
    assert "Book a Meeting: https://cal.com/agilereceivables/30min" in raw_body

    # HTML contains clickable <a> tag
    assert 'href="https://cal.com/agilereceivables/30min"' in html_output
    assert "Book a Meeting" in html_output

    # HTML contains safe escaping: <Acme Corp> is escaped to &lt;Acme Corp&gt;
    assert "&lt;Acme Corp&gt;" in html_output
    assert "<Acme Corp>" not in html_output

    # & is escaped
    assert "John &amp; Jane" in html_output


# ── 4. Missing Booking Configuration Prevents Dispatch ───────────────────────

def test_missing_booking_configuration_blocks_send_outreach(test_db_session: Session):
    """Outreach delivery fails closed with MissingBookingUrlError if the tenant has no booking URL."""
    db = test_db_session
    org = Organization(id=uuid.uuid4(), name="No Booking Org", slug="no-booking-org")
    contact = Contact(organization_id=org.id, first_name="Alice", last_name="Smith", email="alice@example.com")
    campaign = Campaign(organization_id=org.id, name="Test Campaign", status="active")
    db.add_all([org, contact, campaign])
    db.flush()

    cc = CampaignContact(campaign_id=campaign.id, contact_id=contact.id)
    db.add(cc)
    db.flush()

    outreach = Outreach(
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        subject="Intro",
        body="Hello Alice, let's talk about our product. Book a meeting: {booking_link}",
        status="draft",
    )
    db.add(outreach)
    db.commit()

    provider = MockEmailProvider()

    # Sending must be blocked with clear MissingBookingUrlError
    with pytest.raises(MissingBookingUrlError) as exc_info:
        send_outreach(db, org.id, outreach.id, provider=provider)

    assert "No Booking Org" in str(exc_info.value)
    assert "{booking_link}" in str(exc_info.value)

    # Verify outreach was NOT marked sent
    db.refresh(outreach)
    assert outreach.status != "sent"


def test_missing_booking_configuration_blocks_campaign_execution(test_db_session: Session):
    """Campaign execution rejects contacts if organization lacks a configured booking URL."""
    db = test_db_session
    org = Organization(id=uuid.uuid4(), name="Unconfigured Org", slug="unconfigured-org")
    contact = Contact(organization_id=org.id, first_name="Bob", last_name="Jones", email="bob@example.com")
    campaign = Campaign(organization_id=org.id, name="Outreach Campaign", status="active")
    db.add_all([org, contact, campaign])
    db.flush()

    cc = CampaignContact(campaign_id=campaign.id, contact_id=contact.id)
    step = CampaignStep(
        organization_id=org.id,
        campaign_id=campaign.id,
        step_number=1,
        subject_template="Quick Question",
        body_template="Hi {contact.first_name}, check out our platform. Book a meeting: {booking_link}",
        is_active=True,
    )
    db.add_all([cc, step])
    db.commit()

    resp = execute_campaign(db, org.id, campaign.id)
    # Contact is rejected due to unresolved {booking_link}
    assert resp.created_count == 0
    assert resp.rejected_count == 1
    assert cc.id in resp.rejected_campaign_contact_ids


def test_configured_booking_url_succeeds_in_send_outreach(test_db_session: Session):
    """Configured Agile Receivables outreach delivers successfully with resolved booking URL and HTML body."""
    db = test_db_session
    org = Organization(
        id=uuid.UUID("3de43e6b-6cc0-4391-a061-2faba481bcb8"),
        name="Agile Receivables Org",
        slug="agile-receivables-org",
    )
    contact = Contact(organization_id=org.id, first_name="Carol", last_name="Taylor", email="carol@example.com")
    campaign = Campaign(organization_id=org.id, name="Briefing Campaign", status="active")
    db.add_all([org, contact, campaign])
    db.flush()

    cc = CampaignContact(campaign_id=campaign.id, contact_id=contact.id)
    db.add(cc)
    db.flush()

    outreach = Outreach(
        organization_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        channel="email",
        subject="Intro for {contact.first_name}",
        body="Hi {contact.first_name}, would love to brief you.",
        status="draft",
    )
    db.add(outreach)
    db.commit()

    provider = MockEmailProvider()
    sent_outreach = send_outreach(db, org.id, outreach.id, provider=provider)

    assert sent_outreach.status == "sent"
    assert "https://cal.com/agilereceivables/30min" in sent_outreach.body
    assert "Book a Meeting:" in sent_outreach.body


# ── 5. AI Generation & Reusable Templates Independence ────────────────────────

def test_ai_template_prompt_instructs_booking_link():
    """System prompt explicitly mandates {booking_link} token and forbids hardcoding external URLs."""
    prompt = _build_system_prompt()
    assert "{booking_link}" in prompt
    assert "CRITICAL CALL-TO-ACTION AND BOOKING LINK RULE" in prompt
    assert "NEVER invent, hallucinate, or hardcode external booking URLs" in prompt


def test_ai_generation_mock_includes_booking_link():
    """Mock AI generation incorporates {booking_link} into the email draft."""
    req = AIEmailGenerateRequest(
        campaign_name="Briefing",
        email_objective="Schedule a 15-minute meeting",
        tone="professional",
    )
    res = generate_email_template(req, force_mock=True)
    assert "{booking_link}" in res.body


def test_saved_template_organization_independence(test_db_session: Session):
    """Reusable template stores {booking_link} unrendered; different tenants resolve their own destinations."""
    db = test_db_session
    org_a = Organization(
        id=uuid.UUID("3de43e6b-6cc0-4391-a061-2faba481bcb8"),
        name="Agile Receivables Org",
        slug="agile-receivables-org",
    )
    org_b = Organization(
        id=uuid.uuid4(),
        name="Partner Org",
        slug="partner-org",
    )
    db.add_all([org_a, org_b])
    db.commit()

    register_organization_booking_url(org_b.id, "https://cal.com/partner/15min")

    # Master template stored in DB contains generic {booking_link}
    template = EmailTemplate(
        organization_id=org_a.id,
        name="Standard Outbound",
        subject_template="Quick Question",
        body_template="Hi {contact.first_name},\n\nBook a meeting: {booking_link}\n\nBest,\nSales",
    )
    db.add(template)
    db.commit()

    # The persisted template has not been mutated
    assert "{booking_link}" in template.body_template

    # Rendered for Org A
    url_a = get_organization_booking_url(db, org_a)
    rendered_a = render_template(template.body_template, contact=None, booking_link=url_a)
    assert "https://cal.com/agilereceivables/30min" in rendered_a

    # Rendered for Org B
    url_b = get_organization_booking_url(db, org_b)
    rendered_b = render_template(template.body_template, contact=None, booking_link=url_b)
    assert "https://cal.com/partner/15min" in rendered_b
    assert "https://cal.com/agilereceivables/30min" not in rendered_b


def test_workflow_validation_accepts_booking_link():
    """Workflow validation recognizes {booking_link} as a valid approved template variable."""
    workflow = WorkflowConfig(
        nodes=[
            WorkflowNode(id="start-1", type="start", title="Start", config={}),
            WorkflowNode(
                id="email-1",
                type="email",
                title="Intro Email",
                config={
                    "subject": "Intro regarding {contact.company}",
                    "body": "Hi {contact.first_name},\n\nPick a time: {booking_link}\n\nBest,\n{sender_name}",
                },
            ),
        ],
        edges=[],
    )
    result = validate_workflow(workflow)
    assert result.is_valid
    assert len(result.errors) == 0


# ── 7. Live Preview Template Booking CTA Resolution & Tenant Isolation ──────

def test_live_preview_resolves_booking_link_for_agile_receivables(test_db_session: Session):
    """Email Step Live Preview resolves {booking_link} dynamically to Cal.com URL for Agile Receivables tenants."""
    db = test_db_session
    for org_id_str in [
        "3de43e6b-6cc0-4391-a061-2faba481bcb8",
        "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
    ]:
        org_id = uuid.UUID(org_id_str)
        org = Organization(id=org_id, name="Agile Organization", slug=f"org-{org_id_str[:8]}")
        db.add(org)
        db.flush()

        req = TemplatePreviewRequest(
            subject_template="Quick Question for {contact.first_name}",
            body_template="Hi {contact.first_name},\n\nPlease book a time here: {booking_link}\n\nThanks,\n{sender_name}",
            sender_name="Alex Smith",
        )
        res = preview_template_content(db, org_id=org_id, campaign_id=uuid.uuid4(), request=req)

        assert res.booking_url == "https://cal.com/agilereceivables/30min"
        assert "https://cal.com/agilereceivables/30min" in res.rendered_body
        assert "{booking_link}" not in res.rendered_body
        assert "{booking_link}" not in res.unresolved_placeholders
        assert len(res.unresolved_placeholders) == 0
        assert res.rendered_html is not None
        assert 'href="https://cal.com/agilereceivables/30min"' in res.rendered_html
        assert "Book a Meeting" in res.rendered_html


def test_live_preview_unconfigured_org_reports_unresolved_placeholder(test_db_session: Session):
    """Email Step Live Preview reports {booking_link} as unresolved when organization has no booking URL configured."""
    db = test_db_session
    unconfigured_org_id = uuid.uuid4()
    org = Organization(id=unconfigured_org_id, name="Unconfigured Corp", slug="unconfigured-corp")
    db.add(org)
    db.flush()

    req = TemplatePreviewRequest(
        subject_template="Hello {contact.first_name}",
        body_template="Hi {contact.first_name},\n\nCheck our schedule: {booking_link}\n\nRegards,\nTeam",
    )
    res = preview_template_content(db, org_id=unconfigured_org_id, campaign_id=uuid.uuid4(), request=req)

    assert res.booking_url is None
    assert "{booking_link}" in res.unresolved_placeholders
    assert any("Organization has no configured meeting-booking URL" in err for err in res.validation_errors)


def test_live_preview_tenant_isolation(test_db_session: Session):
    """Ensure arbitrary tenants do not inherit Agile Receivables booking URL in preview."""
    db = test_db_session
    custom_org_id = uuid.uuid4()
    org = Organization(id=custom_org_id, name="Acme Health", slug="acme-health")
    db.add(org)
    db.flush()

    req = TemplatePreviewRequest(
        subject_template="Intro",
        body_template="Book here: {booking_link}",
    )

    # 1. Without configuration, cannot inherit Agile Receivables' URL
    res_unconf = preview_template_content(db, org_id=custom_org_id, campaign_id=uuid.uuid4(), request=req)
    assert res_unconf.booking_url is None
    assert "agilereceivables" not in res_unconf.rendered_body
    assert "{booking_link}" in res_unconf.unresolved_placeholders

    # 2. When configured with tenant's own URL, resolves to tenant's own URL
    register_organization_booking_url(custom_org_id, "https://cal.com/acme-health/demo")
    res_conf = preview_template_content(db, org_id=custom_org_id, campaign_id=uuid.uuid4(), request=req)
    assert res_conf.booking_url == "https://cal.com/acme-health/demo"
    assert "https://cal.com/acme-health/demo" in res_conf.rendered_body
    assert "agilereceivables" not in res_conf.rendered_body
    assert len(res_conf.unresolved_placeholders) == 0

