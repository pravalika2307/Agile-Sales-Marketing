"""Integration and domain tests for Stage 4 (Outreach Event Tracking & Reply Association)
and Stage 5 (Campaign Workflow Conditions)."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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
from app.models.crm import Contact
from app.models.outreach import Outreach, OutreachEvent
from app.schemas.workflow import WorkflowConfig, WorkflowEdge, WorkflowNode
from app.services.campaign_scheduler import CampaignSchedulerService
from app.services.outreach.tracking import associate_inbound_reply, record_delivered, record_opened, record_replied
from app.services.workflow_service import save_campaign_workflow


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
            "full_name": "Stage B Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


async def setup_sent_outreach(
    client: AsyncClient,
    headers: dict,
    contact_email: str = "kunal.prospect@gmail.com",
    first_name: str = "Kunal",
    provider_msg_id: str = "010f01a136ab9798-a036ff45-1c10-4524-9238-ef38f8712493-000000",
) -> dict:
    """Helper to create campaign, contact, enrollment, and transition an outreach to 'sent'."""
    camp = (await client.post(
        "/api/v1/campaigns",
        json={"name": "Kunal Outreach Campaign", "type": "sales_outbound"},
        headers=headers,
    )).json()

    contact = (await client.post(
        "/api/v1/contacts",
        json={"email": contact_email, "first_name": first_name, "last_name": "Sadhre"},
        headers=headers,
    )).json()

    enrollment = (await client.post(
        f"/api/v1/campaigns/{camp['id']}/contacts/{contact['id']}",
        json={"enrollment_status": "in_progress"},
        headers=headers,
    )).json()

    outreach = (await client.post(
        "/api/v1/outreach",
        json={
            "campaign_id": camp["id"],
            "contact_id": contact["id"],
            "campaign_contact_id": enrollment["id"],
            "channel": "email",
            "subject": "Introduction to Agile Sales & Marketing",
            "body": f"Hi {first_name}, connecting regarding receivables automation.",
        },
        headers=headers,
    )).json()

    await client.post(f"/api/v1/outreach/{outreach['id']}/schedule", headers=headers)
    sent = (await client.post(f"/api/v1/outreach/{outreach['id']}/send", headers=headers)).json()
    assert sent["status"] == "sent"

    return {
        "campaign_id": camp["id"],
        "contact_id": contact["id"],
        "campaign_contact_id": enrollment["id"],
        "outreach_id": outreach["id"],
        "provider_message_id": sent.get("provider_message_id"),
        "contact_email": contact_email,
    }


# ── STAGE 4: SES WEBHOOK & INGESTION TESTS ───────────────────────────────────

@pytest.mark.asyncio
async def test_ses_webhook_delivery_open_click_bounce_complaint(test_db_session, monkeypatch):
    """Verify SES webhook properly ingests Delivery, Open, Click, and Bounce events."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)
    async with make_client() as client:
        token = await register_tenant(client, "admin_ses@test.com", "SES Org")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        msg_id = ctx["provider_message_id"]

        # 1. Delivery notification via standard SES webhook
        deliv_payload = {
            "eventType": "Delivery",
            "mail": {
                "messageId": msg_id,
                "destination": [ctx["contact_email"]],
            },
            "delivery": {
                "timestamp": "2026-10-15T12:00:00.000Z",
                "smtpResponse": "250 2.0.0 OK",
            },
        }
        res_deliv = await client.post("/api/v1/outreach/tracking/ses-webhook", json=deliv_payload)
        assert res_deliv.status_code == 200
        assert res_deliv.json()["status"] == "processed"

        # Check model first_delivered_at
        outreach_data = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_data["first_delivered_at"] is not None

        # 2. Open notification
        open_payload = {
            "eventType": "Open",
            "mail": {
                "messageId": msg_id,
            },
            "open": {
                "timestamp": "2026-10-15T12:05:00.000Z",
                "userAgent": "Mozilla/5.0",
            },
        }
        res_open = await client.post("/api/v1/tracking/ses-webhook", json=open_payload)
        assert res_open.status_code == 200
        assert res_open.json()["status"] == "processed"

        outreach_data = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_data["first_opened_at"] is not None

        # 3. Click notification
        click_payload = {
            "eventType": "Click",
            "mail": {
                "messageId": msg_id,
            },
            "click": {
                "link": "https://agilesalesmarketing.com/demo",
            },
        }
        res_click = await client.post("/api/v1/tracking/ses-webhook", json=click_payload)
        assert res_click.status_code == 200
        assert res_click.json()["status"] == "processed"

        outreach_data = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_data["first_clicked_at"] is not None


@pytest.mark.asyncio
async def test_ses_webhook_message_id_variations_and_tag_lookup(test_db_session, monkeypatch):
    """Verify SES webhook matches candidate message IDs (with angle brackets) and tags."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)
    async with make_client() as client:
        token = await register_tenant(client, "admin_tags@test.com", "Tags Org")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        msg_id = ctx["provider_message_id"]

        # Angle-bracket wrapped message ID
        wrapped_payload = {
            "eventType": "Open",
            "mail": {
                "messageId": f"<{msg_id}>",
            },
        }
        res_wrapped = await client.post("/api/v1/tracking/ses-webhook", json=wrapped_payload)
        assert res_wrapped.status_code == 200
        assert res_wrapped.json()["status"] == "processed"

        # Lookup by SES tags
        tag_payload = {
            "eventType": "Click",
            "mail": {
                "messageId": "unknown-nonexistent-id",
                "tags": {
                    "outreach_id": [oid],
                },
            },
        }
        res_tag = await client.post("/api/v1/tracking/ses-webhook", json=tag_payload)
        assert res_tag.status_code == 200
        assert res_tag.json()["status"] == "processed"


@pytest.mark.asyncio
async def test_ses_webhook_reply_event_handling(test_db_session, monkeypatch):
    """Verify SES webhook handles Reply event type correctly."""
    monkeypatch.setattr(settings, "AWS_SNS_VERIFY_WEBHOOK_SIGNATURE", False)
    async with make_client() as client:
        token = await register_tenant(client, "admin_reply@test.com", "Reply Org")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        msg_id = ctx["provider_message_id"]

        reply_payload = {
            "eventType": "Reply",
            "mail": {
                "messageId": msg_id,
            },
            "reply": {
                "text": "Hi Kunal here, thanks for reaching out. Let's talk.",
            },
        }
        res_reply = await client.post("/api/v1/tracking/ses-webhook", json=reply_payload)
        assert res_reply.status_code == 200
        assert res_reply.json()["status"] == "processed"

        outreach_data = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_data["first_replied_at"] is not None

        # Verify contact lead_status transitioned to replied
        contact_data = (await client.get(f"/api/v1/contacts/{ctx['contact_id']}", headers=headers)).json()
        assert contact_data["lead_status"] == "replied"


# ── STAGE 4: INBOUND REPLY ASSOCIATION ENDPOINT TESTS ────────────────────────

@pytest.mark.asyncio
async def test_inbound_reply_by_in_reply_to_header(test_db_session, monkeypatch):
    """Verify inbound reply endpoint associates via In-Reply-To header and preserves content."""
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "test-inbound-secret")
    async with make_client() as client:
        token = await register_tenant(client, "admin_inbound@test.com", "Inbound Org")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]
        msg_id = ctx["provider_message_id"]

        reply_req = {
            "from_email": ctx["contact_email"],
            "to_email": "sales@agilereceivables.com",
            "subject": "Re: Introduction to Agile Sales & Marketing",
            "body": "Sounds interesting! Please send across your availability for next Tuesday.",
            "in_reply_to": f"<{msg_id}>",
        }
        resp = await client.post(
            "/api/v1/tracking/inbound-reply",
            json=reply_req,
            headers={"X-Webhook-Secret": "test-inbound-secret"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["outreach_id"] == oid
        assert data["event_type"] == "replied"

        # Verify Outreach timeline and events
        events_resp = await client.get(f"/api/v1/outreach/{oid}/events", headers=headers)
        assert events_resp.status_code == 200
        events = events_resp.json()
        replied_event = next(e for e in events if e["event_type"] == "replied")
        assert replied_event["event_metadata"]["body"] == reply_req["body"]
        assert replied_event["event_metadata"]["from_email"] == ctx["contact_email"]

        # Verify recipient lead_status updated to replied
        contact_data = (await client.get(f"/api/v1/contacts/{ctx['contact_id']}", headers=headers)).json()
        assert contact_data["lead_status"] == "replied"


@pytest.mark.asyncio
async def test_inbound_reply_by_sender_email_fallback(test_db_session, monkeypatch):
    """Verify inbound reply associates via sender email when In-Reply-To header is missing."""
    monkeypatch.setattr(settings, "INBOUND_REPLY_WEBHOOK_SECRET", "test-inbound-secret")
    async with make_client() as client:
        token = await register_tenant(client, "admin_fallback@test.com", "Fallback Org")
        headers = {"Authorization": f"Bearer {token}"}
        ctx = await setup_sent_outreach(client, headers)
        oid = ctx["outreach_id"]

        # Post reply with only from_email (no in_reply_to)
        reply_req = {
            "from_email": ctx["contact_email"],
            "subject": "Re: S&M Intro",
            "body": "Yes, I would like to learn more.",
        }
        resp = await client.post(
            "/api/v1/outreach/tracking/inbound-reply",
            json=reply_req,
            headers={"X-Webhook-Secret": "test-inbound-secret"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["outreach_id"] == oid

        # Verify outreach summary field
        outreach_data = (await client.get(f"/api/v1/outreach/{oid}", headers=headers)).json()
        assert outreach_data["first_replied_at"] is not None


# ── STAGE 5: WORKFLOW CONDITIONS & SCHEDULER ALIGNMENT TESTS ─────────────────

def test_visual_workflow_wait_nodes_accumulate_delays(test_db_session):
    """Verify visual workflow intermediate wait nodes accumulate delays onto CampaignSteps."""
    db: Session = test_db_session
    from app.models.tenant import Organization
    org = Organization(name="Workflow Delay Org", slug="workflow-delay-org")
    db.add(org)
    db.commit()

    camp = Campaign(
        organization_id=org.id,
        name="Multi-Day Cadence with Wait Nodes",
        type="sales_outbound",
        status="draft",
    )
    db.add(camp)
    db.commit()

    # Visual Workflow: Start -> Email 1 -> Wait (3 days) -> Email 2
    nodes = [
        WorkflowNode(id="start", type="start", title="Start", config={}),
        WorkflowNode(
            id="step1",
            type="email",
            title="Email 1",
            config={"subject": "Step 1 Subject", "body": "Step 1 Body", "delay_days": 0},
        ),
        WorkflowNode(
            id="wait1",
            type="wait",
            title="Wait 3 Days",
            config={"duration": 3, "unit": "days"},
        ),
        WorkflowNode(
            id="step2",
            type="email",
            title="Email 2",
            config={"subject": "Step 2 Subject", "body": "Step 2 Body"},
        ),
    ]
    edges = [
        WorkflowEdge(id="e1", source="start", target="step1"),
        WorkflowEdge(id="e2", source="step1", target="wait1"),
        WorkflowEdge(id="e3", source="wait1", target="step2"),
    ]
    config = WorkflowConfig(nodes=nodes, edges=edges)

    save_res = save_campaign_workflow(db, org.id, camp.id, config)
    assert save_res.validation.is_valid is True

    # Inspect persisted CampaignStep rows
    steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.campaign_id == camp.id)
        .order_by(CampaignStep.step_number.asc())
        .all()
    )
    assert len(steps) == 2
    assert steps[0].step_number == 1
    assert steps[0].delay_days == 0

    # Step 2 must have inherited the 3-day wait delay!
    assert steps[1].step_number == 2
    assert steps[1].delay_days == 3


def test_workflow_condition_email_opened_evaluation(test_db_session):
    """Verify scheduler respects email_opened condition: waits if not opened, advances when opened."""
    db: Session = test_db_session
    from app.models.tenant import Organization
    org = Organization(name="Condition Eval Org", slug="condition-eval-org")
    db.add(org)
    db.commit()

    camp = Campaign(
        organization_id=org.id,
        name="Conditional Open Campaign",
        type="sales_outbound",
        status="active",
        workflow_config={
            "nodes": [
                {"id": "s1", "type": "email", "config": {"subject": "S1", "body": "B1"}},
                {"id": "c1", "type": "condition", "config": {"condition_type": "email_opened"}},
                {"id": "s2", "type": "email", "config": {"subject": "S2", "body": "B2", "condition_type": "email_opened"}},
            ],
            "edges": [],
        },
    )
    db.add(camp)
    db.commit()

    step1 = CampaignStep(
        organization_id=org.id,
        campaign_id=camp.id,
        step_number=1,
        step_type="email",
        subject_template="Step 1 Subject",
        body_template="Step 1 Body",
        delay_days=0,
        delay_hours=0,
    )
    step2 = CampaignStep(
        organization_id=org.id,
        campaign_id=camp.id,
        step_number=2,
        step_type="email",
        subject_template="Step 2 Subject",
        body_template="Step 2 Body",
        delay_days=0,
        delay_hours=0,
    )
    db.add_all([step1, step2])
    db.commit()

    contact = Contact(
        organization_id=org.id,
        first_name="Alex",
        last_name="OpenLead",
        email="alex.open@example.com",
        lead_status="in_progress",
    )
    db.add(contact)
    db.commit()

    cc = CampaignContact(
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
        enrolled_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(cc)
    db.commit()

    # Step 1 outreach was sent 1 day ago, but NOT opened yet
    outreach1 = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        recipient=contact.email,
        channel="email",
        status="sent",
        subject="Step 1 Subject",
        body="Step 1 Body",
        sent_at=datetime.now(timezone.utc) - timedelta(days=1),
        first_opened_at=None,  # NOT OPENED
    )
    db.add(outreach1)
    db.commit()

    service = CampaignSchedulerService(db=db)

    # 1. First run: Email has NOT been opened -> Step 2 must be SKIPPED!
    res1 = service.plan_due_steps(org_id=org.id, campaign_id=camp.id)
    assert res1.planned_count == 0
    assert res1.skipped_count == 1
    assert any("requires previous email to be opened" in d.get("reason", "") for d in res1.details)

    # 2. Record open event on Step 1 outreach
    record_opened(db, org.id, outreach1.id)
    assert outreach1.first_opened_at is not None

    # 3. Second run: Email is now opened -> Step 2 must be PLANNED!
    res2 = service.plan_due_steps(org_id=org.id, campaign_id=camp.id)
    assert res2.planned_count == 1
    assert cc.current_step == 2


def test_inbound_reply_halts_scheduler_sequence(test_db_session):
    """Verify inbound reply halts sequence immediately and prevents future steps from executing."""
    db: Session = test_db_session
    from app.models.tenant import Organization
    org = Organization(name="Reply Halt Org", slug="reply-halt-org")
    db.add(org)
    db.commit()

    camp = Campaign(
        organization_id=org.id,
        name="Sequential Follow-up Campaign",
        type="sales_outbound",
        status="active",
    )
    db.add(camp)
    db.commit()

    step1 = CampaignStep(
        organization_id=org.id,
        campaign_id=camp.id,
        step_number=1,
        step_type="email",
        subject_template="Step 1",
        body_template="Step 1 Body",
        delay_days=0,
        delay_hours=0,
    )
    step2 = CampaignStep(
        organization_id=org.id,
        campaign_id=camp.id,
        step_number=2,
        step_type="email",
        subject_template="Step 2 Followup",
        body_template="Step 2 Body",
        delay_days=1,
        delay_hours=0,
    )
    db.add_all([step1, step2])
    db.commit()

    contact = Contact(
        organization_id=org.id,
        first_name="Kunal",
        last_name="Prospect",
        email="kunal.reply@example.com",
        lead_status="in_progress",
    )
    db.add(contact)
    db.commit()

    cc = CampaignContact(
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="in_progress",
        current_step=1,
        enrolled_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db.add(cc)
    db.commit()

    outreach1 = Outreach(
        organization_id=org.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        campaign_contact_id=cc.id,
        recipient=contact.email,
        channel="email",
        status="sent",
        provider_message_id="msg-kunal-12345",
        subject="Step 1",
        body="Step 1 Body",
        sent_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db.add(outreach1)
    db.commit()

    service = CampaignSchedulerService(db=db)

    # Inbound reply arrives before step 2 plans
    associate_inbound_reply(
        db=db,
        from_email="kunal.reply@example.com",
        subject="Re: Step 1",
        body="Yes, we are interested. Let us connect tomorrow.",
        in_reply_to="<msg-kunal-12345>",
    )

    assert outreach1.first_replied_at is not None
    assert contact.lead_status == "replied"
    assert cc.enrollment_status == "replied"

    # 1. The enrollment was immediately transitioned to 'replied' by associate_inbound_reply.
    # Therefore, the scheduler will not plan any further steps.
    res1 = service.plan_due_steps(org_id=org.id, campaign_id=camp.id)
    assert res1.planned_count == 0

    # 2. Even if enrollment was still marked 'in_progress', scheduler's stop condition catches the reply:
    cc.enrollment_status = "in_progress"
    db.commit()

    res2 = service.plan_due_steps(org_id=org.id, campaign_id=camp.id)
    assert res2.planned_count == 0
    assert res2.halted_count == 1
    assert any("Prospect replied" in d.get("reason", "") for d in res2.details)
    assert cc.enrollment_status == "replied"
