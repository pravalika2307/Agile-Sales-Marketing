"""Tests for campaign template rendering engine, syntax support, safe fallbacks, and validation guards."""
from __future__ import annotations

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
from app.models.outreach import Outreach
from app.services.campaign_steps.template_renderer import (
    find_unresolved_placeholders,
    render_template,
)
from app.services.outreach.base import MockEmailProvider
from app.services.outreach.service import (
    UnresolvedTemplatePlaceholderError,
    create_outreach,
    send_outreach,
)
from app.services.organization_config import register_organization_booking_url


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
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Campaign Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── 1. Unit Tests for Template Renderer ───────────────────────────────────────

def test_template_renderer_nested_contact_syntax():
    """Requirement 1: Support {contact.first_name}, {contact.last_name}, {contact.email}, {contact.company}, {contact.job_title}."""
    contact = Contact(
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@example.com",
        job_title="VP of Sales",
        phone="+1234567890",
    )
    company = Company(name="Acme Corporation")

    template = (
        "Hello {contact.first_name} {contact.last_name},\n"
        "We noticed your role as {contact.job_title} at {contact.company}.\n"
        "Reach us at {contact.email} or call {contact.phone}."
    )

    rendered = render_template(template, contact=contact, company=company)
    assert rendered == (
        "Hello Jane Doe,\n"
        "We noticed your role as VP of Sales at Acme Corporation.\n"
        "Reach us at jane.doe@example.com or call +1234567890."
    )


def test_template_renderer_flat_variables_and_single_braces():
    """Requirement 2: Preserve existing flat variables and support both single and double braces."""
    contact = Contact(
        first_name="Alice",
        last_name="Smith",
        email="alice@smith.org",
        job_title="Head of Ops",
    )
    company = Company(name="Smith Logistics")

    # Mix of flat variables and double braces
    template = "Hi {first_name} {{last_name}}, {{full_name}} at {company_name} (aka {company}) - sent by {sender_name}."
    rendered = render_template(
        template,
        contact=contact,
        company=company,
        sender_name="Outreach Bot",
    )
    assert rendered == "Hi Alice Smith, Alice Smith at Smith Logistics (aka Smith Logistics) - sent by Outreach Bot."


def test_template_renderer_whitespace_tolerance():
    """Variables with internal whitespace like { contact.company } or {{ contact.first_name }} resolve properly."""
    contact = Contact(first_name="Bob", email="bob@test.com")
    company = Company(name="Globex Corp")

    template = "Welcome { contact.first_name } from {{ contact.company }}!"
    rendered = render_template(template, contact=contact, company=company)
    assert rendered == "Welcome Bob from Globex Corp!"


def test_template_renderer_missing_company_safe_fallback():
    """Requirement 5: If company is missing, omit company-specific phrase gracefully."""
    contact = Contact(first_name="John", email="john@example.com")

    # Subject with trailing preposition "for {contact.company}"
    subject_tmpl = "Strategic briefing for {contact.company}"
    rendered_subject = render_template(subject_tmpl, contact=contact, company=None)
    assert rendered_subject == "Strategic briefing"

    # Body with preposition "at {contact.company}"
    body_tmpl = "I noticed your work at {contact.company} in sales."
    rendered_body = render_template(body_tmpl, contact=contact, company=None)
    assert rendered_body == "I noticed your work in sales."


def test_template_renderer_missing_first_name_safe_fallback():
    """Requirement 5: If first_name is missing, greetings like 'Hi {contact.first_name},' fall back to 'Hi there,'."""
    contact = Contact(first_name="", last_name="Johnson", email="johnson@example.com")

    template = "Hi {contact.first_name},\n\nWe have a special announcement."
    rendered = render_template(template, contact=contact)
    assert rendered == "Hi there,\n\nWe have a special announcement."


def test_template_renderer_unknown_variables_remain_for_guards():
    """Unknown variables remain unmodified so validation guards can catch them."""
    contact = Contact(first_name="Sara", email="sara@example.com")
    company = Company(name="Stark Industries")

    template = "Hello {contact.first_name}, your voucher code is {voucher_code} and promo {promo.id}."
    rendered = render_template(template, contact=contact, company=company)
    assert rendered == "Hello Sara, your voucher code is {voucher_code} and promo {promo.id}."

    unresolved = find_unresolved_placeholders(rendered)
    assert unresolved == ["{voucher_code}", "{promo.id}"]


def test_find_unresolved_placeholders_clean_text():
    """Clean text has zero unresolved placeholders."""
    assert find_unresolved_placeholders("Just a normal subject line") == []
    assert find_unresolved_placeholders("Hi Jane, thanks for speaking today.") == []
    assert find_unresolved_placeholders(None) == []
    assert find_unresolved_placeholders("") == []


# ── 2. Integration Tests: Subject & Body Rendering in Previews & Execution ────

@pytest.mark.asyncio
async def test_campaign_execution_renders_subject_and_body_properly(test_db_session):
    """Verify execute_campaign renders both subject and body without literal placeholders."""
    async with make_client() as client:
        token = await register_tenant(client, "campaign_exec@test.com", "Exec Org")
        register_organization_booking_url("exec-org", "https://cal.com/test-org/30min")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create company
        comp_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Acme Ventures", "domain": "acme.com"},
            headers=headers,
        )
        company_id = comp_resp.json()["id"]

        # 2. Create contact linked to company
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Pravalika",
                "last_name": "Palle",
                "email": "pravalika@example.com",
                "company_id": company_id,
            },
            headers=headers,
        )
        contact_id = cont_resp.json()["id"]

        # 3. Create campaign
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Alpha Sequence", "type": "sales_outbound"},
            headers=headers,
        )
        campaign_id = camp_resp.json()["id"]

        # 4. Configure Step 1 with template syntax
        steps_resp = await client.get(f"/api/v1/campaigns/{campaign_id}/steps", headers=headers)
        step_id = steps_resp.json()[0]["id"]

        await client.patch(
            f"/api/v1/campaigns/{campaign_id}/steps/{step_id}",
            json={
                "subject_template": "Strategic briefing for {contact.company}",
                "body_template": "Hi {contact.first_name},\n\nNoticed your work at {contact.company} in sales.",
            },
            headers=headers,
        )

        # 5. Enroll contact
        await client.post(
            f"/api/v1/campaigns/{campaign_id}/contacts/{contact_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )

        # 6. Activate campaign
        activate_resp = await client.post(f"/api/v1/campaigns/{campaign_id}/activate", headers=headers)
        assert activate_resp.status_code == 200

        # 7. Test Preview endpoint
        preview_resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/execute/preview",
            headers=headers,
        )
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()
        assert preview_data["eligible_count"] == 1
        assert preview_data["preview_items"][0]["subject"] == "Strategic briefing for Acme Ventures"
        assert "Hi Pravalika,\n\nNoticed your work at Acme Ventures in sales." in preview_data["preview_items"][0]["body"]
        # Ensure no placeholders remain in preview
        assert find_unresolved_placeholders(preview_data["preview_items"][0]["subject"]) == []
        assert find_unresolved_placeholders(preview_data["preview_items"][0]["body"]) == []

        # 8. Execute campaign planning
        exec_resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/execute",
            headers=headers,
        )
        assert exec_resp.status_code == 200

        # 9. Verify created Outreach record in DB
        outreach_resp = await client.get(
            f"/api/v1/outreach?campaign_id={campaign_id}",
            headers=headers,
        )
        assert outreach_resp.status_code == 200
        outreaches = outreach_resp.json()
        assert len(outreaches) == 1
        o = outreaches[0]
        assert o["subject"] == "Strategic briefing for Acme Ventures"
        assert "Hi Pravalika," in o["body"]
        assert "Acme Ventures" in o["body"]
        assert find_unresolved_placeholders(o["subject"]) == []
        assert find_unresolved_placeholders(o["body"]) == []


# ── 3. Integration Tests: Send Validation Guard & Blocking ────────────────────

@pytest.mark.asyncio
async def test_send_outreach_blocks_unresolved_placeholders(test_db_session):
    """Requirement 6: Validation guard blocks send if placeholders remain unresolved."""
    async with make_client() as client:
        token = await register_tenant(client, "guard_tester@test.com", "Guard Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create contact
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={"first_name": "Test", "last_name": "User", "email": "test.guard@example.com"},
            headers=headers,
        )
        contact_id = cont_resp.json()["id"]

        # 2. Create campaign
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Guard Campaign", "type": "sales_outbound"},
            headers=headers,
        )
        campaign_id = camp_resp.json()["id"]

        # 3. Enroll contact
        cc_resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/contacts/{contact_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )
        cc_id = cc_resp.json()["id"]

        # 4. Create outreach with an unresolved/unknown placeholder
        outreach_resp = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": campaign_id,
                "contact_id": contact_id,
                "campaign_contact_id": cc_id,
                "channel": "email",
                "subject": "Notice regarding {unresolved_variable}",
                "body": "Hello, please view your {security_token}.",
            },
            headers=headers,
        )
        outreach_id = outreach_resp.json()["id"]

        # 5. Attempt to send -> MUST be blocked with HTTP 400
        send_resp = await client.post(f"/api/v1/outreach/{outreach_id}/send", headers=headers)
        assert send_resp.status_code == 400
        error_detail = send_resp.json()["detail"]
        assert "unresolved template placeholder" in error_detail.lower()
        assert "{unresolved_variable}" in error_detail
        assert "{security_token}" in error_detail

        # 6. Verify outreach status remains draft and was NOT marked sent
        fresh_outreach = await client.get(f"/api/v1/outreach/{outreach_id}", headers=headers)
        assert fresh_outreach.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_send_outreach_succeeds_with_resolved_templates_via_mock_provider(test_db_session):
    """Verify send_outreach succeeds and uses MockEmailProvider cleanly when templates resolve."""
    async with make_client() as client:
        token = await register_tenant(client, "success_tester@test.com", "Success Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create company and contact
        comp_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Tech Corp"},
            headers=headers,
        )
        comp_id = comp_resp.json()["id"]

        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Maya",
                "last_name": "Lin",
                "email": "maya@example.com",
                "company_id": comp_id,
            },
            headers=headers,
        )
        cont_id = cont_resp.json()["id"]

        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Success Campaign", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        cc_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/contacts/{cont_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )
        cc_id = cc_resp.json()["id"]

        # 2. Create outreach with valid template syntax
        outreach_resp = await client.post(
            "/api/v1/outreach",
            json={
                "campaign_id": camp_id,
                "contact_id": cont_id,
                "campaign_contact_id": cc_id,
                "channel": "email",
                "subject": "Greetings for {contact.company}",
                "body": "Hi {contact.first_name}, connecting from {sender_name}.",
            },
            headers=headers,
        )
        outreach_id = outreach_resp.json()["id"]

        # 3. Send outreach -> must succeed and render completely before dispatch
        send_resp = await client.post(f"/api/v1/outreach/{outreach_id}/send", headers=headers)
        assert send_resp.status_code == 200
        sent_data = send_resp.json()
        assert sent_data["status"] == "sent"
        assert sent_data["subject"] == "Greetings for Tech Corp"
        assert sent_data["body"] == "Hi Maya, connecting from Agile Sales & Marketing."
        assert sent_data["provider"] == "mock"
        assert find_unresolved_placeholders(sent_data["subject"]) == []
        assert find_unresolved_placeholders(sent_data["body"]) == []


# ── 4. Regression Test: Exact Production Failure Scenario ────────────────────

@pytest.mark.asyncio
async def test_regression_contact_no_company_execute_and_send(test_db_session):
    """
    Regression test reproducing the exact production failure observed at 2026-10-09 22:23 IST.

    Production scenario:
    - Campaign step template: subject='Strategic briefing for {contact.company}',
      body='Hi {contact.first_name},\\n\\nI noticed your recent work in accounts operations
           at {contact.company}. Agile Receivables...'
    - Contact (Pravalika Palle, pravalikapalle@agilereceivables.com) had company_id=None
    - Campaign execution created outreach records with LITERAL '{contact.company}' and
      '{contact.first_name}' because the OLD renderer did not support single-brace or
      dot-notation syntax.
    - The outreach was sent via aws_ses with unresolved placeholders in the subject and body.

    This test verifies that with the FIXED renderer:
    1. execute_campaign renders both templates before creating the Outreach record.
    2. With company_id=None, the company placeholder is cleaned via safe fallback.
    3. The stored Outreach record contains NO unresolved placeholders.
    4. send_outreach (with MockEmailProvider) delivers fully rendered content.
    5. No unresolved placeholder remains in the delivered subject or body.
    """
    async with make_client() as client:
        token = await register_tenant(client, "regression_no_company@test.com", "Regression Org")
        register_organization_booking_url("regression-org", "https://cal.com/test-org/30min")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create contact with NO company (mirrors production: company_id=None)
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Pravalika",
                "last_name": "Palle",
                "email": "pravalika_regression@agilereceivables.com",
                "job_title": "Operations Lead",
            },
            headers=headers,
        )
        assert cont_resp.status_code in (200, 201), f"Contact creation failed: {cont_resp.text}"
        contact_data = cont_resp.json()
        contact_id = contact_data["id"]
        assert contact_data.get("company_id") is None, "Contact must have no company for this regression test"

        # 2. Create campaign
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Production Regression Campaign", "type": "sales_outbound"},
            headers=headers,
        )
        campaign_id = camp_resp.json()["id"]

        # 3. Configure step 1 with EXACT production templates (single-brace dot-notation)
        steps_list = await client.get(f"/api/v1/campaigns/{campaign_id}/steps", headers=headers)
        step_id = steps_list.json()[0]["id"]
        await client.patch(
            f"/api/v1/campaigns/{campaign_id}/steps/{step_id}",
            json={
                "subject_template": "Strategic briefing for {contact.company}",
                "body_template": (
                    "Hi {contact.first_name},\n\n"
                    "I noticed your recent work at {contact.company}. "
                    "Agile Sales & Marketing provides an AI-powered sales platform "
                    "that automates prospect engagement.\n\nBest regards,\nAgile Team"
                ),
                "step_type": "email",
                "wait_days": 0,
            },
            headers=headers,
        )

        # 4. Activate campaign
        act = await client.post(f"/api/v1/campaigns/{campaign_id}/activate", headers=headers)
        assert act.status_code in (200, 201)

        # 5. Enroll contact
        enroll = await client.post(
            f"/api/v1/campaigns/{campaign_id}/contacts/{contact_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )
        assert enroll.status_code in (200, 201)

        # 6. Execute campaign
        exec_resp = await client.post(f"/api/v1/campaigns/{campaign_id}/execute", headers=headers)
        assert exec_resp.status_code in (200, 201), f"Execute failed: {exec_resp.text}"
        exec_data = exec_resp.json()
        assert exec_data["created_count"] == 1, f"Expected 1 outreach created, got: {exec_data}"
        outreach_id = exec_data["created_outreach_ids"][0]

        # 7. Fetch stored outreach record and verify NO unresolved placeholders
        out_resp = await client.get(f"/api/v1/outreach/{outreach_id}", headers=headers)
        assert out_resp.status_code == 200
        stored = out_resp.json()
        stored_subject = stored["subject"] or ""
        stored_body = stored["body"] or ""

        # Must not contain any unresolved {contact.xxx} or other placeholders
        assert find_unresolved_placeholders(stored_subject) == [], (
            f"REGRESSION: Stored subject contains unresolved placeholders: {stored_subject!r}"
        )
        assert find_unresolved_placeholders(stored_body) == [], (
            f"REGRESSION: Stored body contains unresolved placeholders: {stored_body!r}"
        )

        # With no company, "Strategic briefing for {contact.company}" -> "Strategic briefing"
        assert "Strategic briefing" in stored_subject
        assert "{contact.company}" not in stored_subject
        # first_name "Pravalika" should be rendered
        assert "Pravalika" in stored_body
        assert "{contact.first_name}" not in stored_body
        assert "{contact.company}" not in stored_body

        # 8. Send outreach with MockEmailProvider - must succeed with fully rendered content
        mock_provider = MockEmailProvider()
        from app.services.outreach.service import send_outreach

        db: Session = test_db_session
        org_resp = await client.get("/api/v1/auth/me", headers=headers)
        org_id = uuid.UUID(org_resp.json()["organization_id"])
        outreach_uuid = uuid.UUID(outreach_id)

        sent = send_outreach(db, org_id, outreach_uuid, provider=mock_provider)
        assert sent.status == "sent"
        assert sent.provider == "mock"
        # Verify final delivered subject and body have no placeholders
        assert find_unresolved_placeholders(sent.subject) == [], (
            f"REGRESSION: Delivered subject contains unresolved placeholders: {sent.subject!r}"
        )
        assert find_unresolved_placeholders(sent.body) == [], (
            f"REGRESSION: Delivered body contains unresolved placeholders: {sent.body!r}"
        )
