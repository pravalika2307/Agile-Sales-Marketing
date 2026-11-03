"""Comprehensive tests for Visual Campaign Workflow Builder, step types, persistence, and template preview."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.schemas.workflow import (
    TemplatePreviewRequest,
    WorkflowConfig,
    WorkflowEdge,
    WorkflowNode,
)
from app.services.workflow_service import (
    get_or_recover_campaign_workflow,
    preview_template_content,
    save_campaign_workflow,
    validate_workflow,
)


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
            "full_name": "Workflow Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── 1. Workflow Validation Tests ──────────────────────────────────────────────

def test_workflow_validation_requires_start_node():
    """Workflow validation fails when no Start node exists."""
    config = WorkflowConfig(
        nodes=[
            WorkflowNode(
                id="email-1",
                type="email",
                title="Intro Email",
                config={"subject": "Hi", "body": "Hello"},
            )
        ],
        edges=[],
    )
    result = validate_workflow(config)
    assert not result.is_valid
    assert any("Start node" in err for err in result.errors)


def test_workflow_validation_validates_email_placeholders():
    """Workflow validation blocks unknown placeholders in email nodes."""
    config = WorkflowConfig(
        nodes=[
            WorkflowNode(id="start", type="start", title="Start", config={}),
            WorkflowNode(
                id="email-1",
                type="email",
                title="Intro Email",
                config={
                    "subject": "Hello {contact.first_name}",
                    "body": "Your mystery code is {unknown_code_var}.",
                },
            ),
        ],
        edges=[WorkflowEdge(id="e1", source="start", target="email-1")],
    )
    result = validate_workflow(config)
    assert not result.is_valid
    assert any("unknown placeholder '{unknown_code_var}'" in err for err in result.errors)


def test_workflow_validation_reports_sms_as_unconfigured():
    """Workflow validation honestly warns that SMS gateway is unconfigured."""
    config = WorkflowConfig(
        nodes=[
            WorkflowNode(id="start", type="start", title="Start", config={}),
            WorkflowNode(
                id="sms-1",
                type="sms",
                title="SMS Follow-Up",
                config={"body": "Checking in via SMS"},
            ),
        ],
        edges=[],
    )
    with patch.object(settings, "TWILIO_ENABLED", False):
        result = validate_workflow(config)
        assert any("SMS gateway is currently unconfigured" in w for w in result.warnings)


def test_workflow_validation_physical_mail_and_linkedin():
    """Verify validation passes for valid physical mail and linkedin workflow nodes."""
    config = WorkflowConfig(
        nodes=[
            WorkflowNode(id="start", type="start", title="Start", config={}),
            WorkflowNode(
                id="mail-1",
                type="physical_mail",
                title="Poplar Direct Mail",
                config={"poplar_campaign_id": "cmp_123", "format": "postcard"},
            ),
            WorkflowNode(
                id="li-1",
                type="linkedin",
                title="LinkedIn Assisted",
                config={
                    "message_type": "connection_request",
                    "template": "Hi {contact.first_name}, connecting from Agile. Book: {booking_link}",
                    "booking_url": "https://cal.com/agilereceivables/30min",
                },
            ),
        ],
        edges=[
            WorkflowEdge(id="e1", source="start", target="mail-1"),
            WorkflowEdge(id="e2", source="mail-1", target="li-1"),
        ],
    )
    result = validate_workflow(config)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_workflow_validation_accepts_valid_multi_step_workflow():
    """Workflow validation passes for valid multi-step workflow with email, wait, voice, and conditions."""
    config = WorkflowConfig(
        nodes=[
            WorkflowNode(id="start", type="start", title="Start", config={}),
            WorkflowNode(
                id="email-1",
                type="email",
                title="Intro Email",
                config={
                    "subject": "Intro for {contact.company}",
                    "body": "Hi {contact.first_name}, from {sender_company_name}.",
                },
            ),
            WorkflowNode(
                id="wait-1",
                type="wait",
                title="Wait 2 Days",
                config={"duration": 2, "unit": "days"},
            ),
            WorkflowNode(
                id="voice-1",
                type="voice",
                title="AI SDR Outbound Call",
                config={"agent_type": "outbound_sdr"},
            ),
            WorkflowNode(
                id="cond-1",
                type="condition",
                title="Meeting Booked?",
                config={"condition_type": "meeting_requested"},
            ),
        ],
        edges=[
            WorkflowEdge(id="e1", source="start", target="email-1"),
            WorkflowEdge(id="e2", source="email-1", target="wait-1"),
            WorkflowEdge(id="e3", source="wait-1", target="voice-1"),
            WorkflowEdge(id="e4", source="voice-1", target="cond-1"),
        ],
    )
    result = validate_workflow(config)
    assert result.is_valid
    assert len(result.errors) == 0


# ── 2. Workflow Persistence & Recovery API Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_workflow_recovery_for_legacy_campaign(test_db_session):
    """A campaign created without workflow_config recovers its workflow from existing CampaignStep rows."""
    async with make_client() as client:
        token = await register_tenant(client, "legacy_wf@test.com", "Legacy Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create campaign (default Step 1 created)
        c_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Legacy Sequence", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = c_resp.json()["id"]

        # 2. Add Step 2
        await client.post(
            f"/api/v1/campaigns/{camp_id}/steps",
            json={
                "step_number": 2,
                "step_type": "email",
                "subject_template": "Follow-up",
                "body_template": "Just checking in.",
                "delay_days": 3,
            },
            headers=headers,
        )

        # 3. GET /workflow should recover Start node and two email steps
        wf_resp = await client.get(f"/api/v1/campaigns/{camp_id}/workflow", headers=headers)
        assert wf_resp.status_code == 200
        wf = wf_resp.json()
        assert len(wf["nodes"]) == 3  # Start + Step 1 + Step 2
        assert wf["nodes"][0]["type"] == "start"
        assert wf["nodes"][1]["type"] == "email"
        assert wf["nodes"][2]["type"] == "email"
        assert len(wf["edges"]) == 2


@pytest.mark.asyncio
async def test_save_and_reopen_workflow_persists_identically(test_db_session):
    """PUT /workflow persists the graph and reopening the campaign retrieves it identically."""
    async with make_client() as client:
        token = await register_tenant(client, "persist_wf@test.com", "Persist Org")
        headers = {"Authorization": f"Bearer {token}"}

        c_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Custom Workflow Sequence", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = c_resp.json()["id"]

        workflow_data = {
            "workflow_config": {
                "nodes": [
                    {"id": "node-start", "type": "start", "title": "Campaign Launch", "config": {}},
                    {
                        "id": "node-email-1",
                        "type": "email",
                        "title": "Welcome Briefing",
                        "config": {
                            "subject": "Exclusive Briefing for {contact.company}",
                            "body": "Hi {contact.first_name}, connecting from {sender_company_name}.",
                            "delay_days": 0,
                            "delay_hours": 0,
                        },
                    },
                    {
                        "id": "node-wait-1",
                        "type": "wait",
                        "title": "Delay 24 Hours",
                        "config": {"duration": 24, "unit": "hours"},
                    },
                    {
                        "id": "node-voice-1",
                        "type": "voice",
                        "title": "Retell SDR Connect",
                        "config": {"agent_type": "outbound_sdr"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "node-start", "target": "node-email-1", "label": "Next"},
                    {"id": "e2", "source": "node-email-1", "target": "node-wait-1", "label": "Next"},
                    {"id": "e3", "source": "node-wait-1", "target": "node-voice-1", "label": "Next"},
                ],
            },
            "description": "Enterprise outbound workflow designed in visual builder",
        }

        # Save workflow
        save_resp = await client.put(
            f"/api/v1/campaigns/{camp_id}/workflow",
            json=workflow_data,
            headers=headers,
        )
        assert save_resp.status_code == 200
        save_json = save_resp.json()
        assert save_json["validation"]["is_valid"] is True
        assert save_json["description"] == "Enterprise outbound workflow designed in visual builder"

        # Reopen workflow and verify exact persistence
        get_resp = await client.get(f"/api/v1/campaigns/{camp_id}/workflow", headers=headers)
        assert get_resp.status_code == 200
        reopened = get_resp.json()
        assert len(reopened["nodes"]) == 4
        assert [n["type"] for n in reopened["nodes"]] == ["start", "email", "wait", "voice"]

        # Verify underlying CampaignStep record was synchronized
        steps_resp = await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)
        assert steps_resp.status_code == 200
        steps = steps_resp.json()
        assert len(steps) == 1
        assert steps[0]["subject_template"] == "Exclusive Briefing for {contact.company}"


# ── 3. Template Preview with Genuine Contact Data ─────────────────────────────

@pytest.mark.asyncio
async def test_preview_step_template_with_persisted_contact(test_db_session):
    """POST /workflow/preview-template renders templates with persisted contact and company records."""
    async with make_client() as client:
        token = await register_tenant(client, "preview_wf@test.com", "Preview Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create company and contact
        comp_resp = await client.post(
            "/api/v1/companies",
            json={"name": "Vanguard Enterprises", "domain": "vanguard.com"},
            headers=headers,
        )
        comp_id = comp_resp.json()["id"]

        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Eleanor",
                "last_name": "Vance",
                "email": "eleanor@vanguard.com",
                "job_title": "Chief Technology Officer",
                "company_id": comp_id,
            },
            headers=headers,
        )
        cont_id = cont_resp.json()["id"]

        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Executive Outreach", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        # 2. Preview template
        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/workflow/preview-template",
            json={
                "subject_template": "AI Briefing for {contact.company}",
                "body_template": "Hi {contact.first_name},\n\nWe noted your leadership as {contact.job_title} at {contact.company}.\n\nFrom {sender_company_name}.",
                "contact_id": cont_id,
                "sender_company_name": "Agile S&M",
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()
        assert preview["rendered_subject"] == "AI Briefing for Vanguard Enterprises"
        assert "Hi Eleanor," in preview["rendered_body"]
        assert "Chief Technology Officer at Vanguard Enterprises." in preview["rendered_body"]
        assert "From Agile S&M." in preview["rendered_body"]
        assert len(preview["unresolved_placeholders"]) == 0
        assert preview["contact_used"]["first_name"] == "Eleanor"


@pytest.mark.asyncio
async def test_preview_reports_unresolved_placeholders(test_db_session):
    """Preview detects and flags unresolvable placeholders without sending."""
    async with make_client() as client:
        token = await register_tenant(client, "unres_prev@test.com", "Unresolved Org")
        headers = {"Authorization": f"Bearer {token}"}

        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Broken Template Campaign", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        prev_resp = await client.post(
            f"/api/v1/campaigns/{camp_id}/workflow/preview-template",
            json={
                "subject_template": "Subject with {unknown_var}",
                "body_template": "Body with {another_fake_variable}",
            },
            headers=headers,
        )
        assert prev_resp.status_code == 200
        preview = prev_resp.json()
        assert "{unknown_var}" in preview["unresolved_placeholders"]
        assert "{another_fake_variable}" in preview["unresolved_placeholders"]
        assert len(preview["validation_errors"]) > 0


# ── 4. Activation Guard Against Broken Templates ──────────────────────────────

@pytest.mark.asyncio
async def test_activation_blocked_if_workflow_step_has_unknown_placeholders(test_db_session):
    """Campaign activation is blocked with HTTP 400 if any step template has invalid placeholders."""
    async with make_client() as client:
        token = await register_tenant(client, "guard_act@test.com", "Guard Org")
        headers = {"Authorization": f"Bearer {token}"}

        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={"name": "Broken Step Campaign", "type": "sales_outbound"},
            headers=headers,
        )
        camp_id = camp_resp.json()["id"]

        steps_resp = await client.get(f"/api/v1/campaigns/{camp_id}/steps", headers=headers)
        step_id = steps_resp.json()[0]["id"]

        # Patch step with invalid placeholder
        await client.patch(
            f"/api/v1/campaigns/{camp_id}/steps/{step_id}",
            json={
                "subject_template": "Hello {broken_unknown_token}",
                "body_template": "Valid body content.",
            },
            headers=headers,
        )

        # Attempt activation
        act_resp = await client.post(f"/api/v1/campaigns/{camp_id}/activate", headers=headers)
        assert act_resp.status_code == 400
        detail = act_resp.json()["detail"].lower()
        assert "invalid placeholder" in detail
        assert "{broken_unknown_token}" in detail
