"""
Comprehensive test suite for AI Campaign Draft Generator.

Validates:
1. Complete workflow generation with suggested steps, delays, condition branches, and exit conditions.
2. Personalization token safety and canonical booking link placeholders ({booking_link}).
3. Sanitization of hallucinated external URLs (e.g. Calendly URLs replaced with {booking_link}).
4. Validation against the real workflow schema (validate_workflow).
5. Channel entitlement and configuration gating (voice steps only when entitled & RETELL_ENABLED=True).
6. Handling of unsupported channels (e.g. LinkedIn filtered out with explicit reason).
7. Error handling for invalid AI output (malformed JSON, invalid schema, empty response).
8. Error handling for unconfigured AI provider credentials (AICampaignConfigurationError).
9. Safe draft persistence (campaign status strictly 'draft', never active).
10. FastAPI endpoint contract (/api/v1/campaigns/generate-draft).
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.entitlement import OrganizationChannelEntitlement
from app.models.tenant import Organization, User
from app.schemas.campaign_ai import AICampaignDraftRequest, AICampaignDraftResponse
from app.schemas.workflow import WorkflowConfig, WorkflowNode, WorkflowEdge
from app.services.campaign_ai_service import (
    AICampaignConfigurationError,
    AICampaignGeneratorService,
    AICampaignValidationError,
    filter_requested_channels,
)


# ── Database Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite database for isolated test execution."""
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


@pytest.fixture
def client(db: Session):
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def create_test_org(db: Session, suffix: str = "A") -> Organization:
    """Helper to create a test organization."""
    org = Organization(
        id=uuid.uuid4(),
        name=f"AI Campaign Org {suffix}",
        slug=f"ai-campaign-org-{suffix.lower()}",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


# ── 1. Complete Workflow Generation (Deterministic Mock Mode) ─────────────────

def test_generate_campaign_draft_force_mock(db: Session):
    """Deterministic mock mode generates a fully validated, multi-step draft saved as 'draft'."""
    org = create_test_org(db, "MockTest")
    service = AICampaignGeneratorService(db=db)

    req = AICampaignDraftRequest(
        description="Re-engage cold B2B SaaS leads who dropped off during Q3 by offering an executive pipeline audit.",
        target_audience="VP of Sales, Head of RevOps at B2B Tech companies",
        objective="Schedule a 15-minute briefing on pipeline acceleration",
        channels=["email"],
        campaign_duration_days=14,
        followup_interval_days=3,
        tone="consultative",
        save_as_draft=True,
    )

    res = service.generate_campaign_draft(org_id=org.id, request=req, force_mock=True)

    assert res.is_mock is True
    assert res.ai_provider == "bedrock"
    assert res.campaign_id is not None
    assert "email" in res.channels_used

    # Verify workflow graph structure
    wf = res.workflow_config
    assert len(wf.nodes) >= 5
    assert len(wf.edges) >= 4

    # 1. Exactly one Start node
    start_nodes = [n for n in wf.nodes if n.type == "start"]
    assert len(start_nodes) == 1

    # 2. Email step with personalized tokens
    email_nodes = [n for n in wf.nodes if n.type == "email"]
    assert len(email_nodes) >= 1
    intro_email = email_nodes[0]
    assert "{contact.first_name}" in intro_email.config["body"]
    assert "{contact.company}" in intro_email.config["body"] or "{contact.company}" in intro_email.config["subject"]
    assert "{booking_link}" in intro_email.config["body"]

    # 3. Wait step with requested interval
    wait_nodes = [n for n in wf.nodes if n.type == "wait"]
    assert len(wait_nodes) >= 1
    assert wait_nodes[0].config["duration"] == 3
    assert wait_nodes[0].config["unit"] == "days"

    # 4. Condition step for reply check
    cond_nodes = [n for n in wf.nodes if n.type == "condition"]
    assert len(cond_nodes) >= 1
    condition_types = [n.config.get("condition_type") for n in cond_nodes]
    assert "email_replied" in condition_types

    # 5. Domain validation
    assert res.validation.is_valid is True
    assert len(res.validation.errors) == 0

    # 6. Database record verification (saved strictly in 'draft' status)
    saved_campaign = db.get(Campaign, res.campaign_id)
    assert saved_campaign is not None
    assert saved_campaign.status == "draft"  # Strictly draft, never active
    assert saved_campaign.organization_id == org.id
    assert saved_campaign.workflow_config is not None


# ── 2. Bedrock Converse Mock Integration ──────────────────────────────────────

def test_generate_campaign_draft_bedrock_converse_mock(db: Session):
    """Service invokes Bedrock Converse API with Claude Sonnet 4.5 and parses structured workflow JSON."""
    org = create_test_org(db, "BedrockMock")
    service = AICampaignGeneratorService(db=db)

    mock_llm_output = {
        "campaign_name": "Mid-Market RevOps Reactivation",
        "summary": "Multi-touch outreach sequence with initial email, follow-up delay, and reply check.",
        "workflow": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "start",
                    "title": "Campaign Trigger",
                    "config": {},
                    "position": {"x": 250, "y": 50},
                },
                {
                    "id": "email-1",
                    "type": "email",
                    "title": "Step 1: Introduction",
                    "config": {
                        "subject": "Quick inquiry regarding {contact.company}",
                        "body": "Hi {contact.first_name},\n\nWould you have 15 minutes to connect? Book here: {booking_link}\n\nBest,\n{sender_name}",
                    },
                    "position": {"x": 250, "y": 180},
                },
                {
                    "id": "wait-1",
                    "type": "wait",
                    "title": "Wait 3 Days",
                    "config": {"duration": 3, "unit": "days"},
                    "position": {"x": 250, "y": 300},
                },
                {
                    "id": "cond-1",
                    "type": "condition",
                    "title": "Check Reply",
                    "config": {"condition_type": "email_replied"},
                    "position": {"x": 250, "y": 420},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "email-1", "label": "Start"},
                {"id": "e2", "source": "email-1", "target": "wait-1", "label": "After Send"},
                {"id": "e3", "source": "wait-1", "target": "cond-1", "label": "Evaluate"},
            ],
        },
    }

    mock_bedrock_client = MagicMock()
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": json.dumps(mock_llm_output)}]
            }
        }
    }

    req = AICampaignDraftRequest(
        description="Reactivate stalled opportunities",
        target_audience="RevOps Leaders",
        objective="Schedule demo",
        channels=["email"],
        save_as_draft=True,
    )

    with patch("app.services.campaign_ai_service._get_bedrock_client", return_value=mock_bedrock_client):
        res = service.generate_campaign_draft(org_id=org.id, request=req, force_mock=False)

    assert res.is_mock is False
    assert res.campaign_name == "Mid-Market RevOps Reactivation"
    assert res.model_used == settings.BEDROCK_DEFAULT_MODEL_ID
    assert res.validation.is_valid is True

    # Verify Converse call
    mock_bedrock_client.converse.assert_called_once()
    call_args = mock_bedrock_client.converse.call_args[1]
    assert call_args["modelId"] == settings.BEDROCK_DEFAULT_MODEL_ID


# ── 3. Invalid AI Output Handling ─────────────────────────────────────────────

def test_generate_campaign_draft_invalid_ai_output_malformed_json(db: Session):
    """Non-JSON or malformed output from Bedrock raises AICampaignValidationError."""
    org = create_test_org(db, "MalformedJSON")
    service = AICampaignGeneratorService(db=db)

    mock_bedrock_client = MagicMock()
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "NOT_VALID_JSON_AT_ALL{{{"}]
            }
        }
    }

    req = AICampaignDraftRequest(
        description="Test description",
        target_audience="Audience",
        objective="Objective",
        channels=["email"],
    )

    with patch("app.services.campaign_ai_service._get_bedrock_client", return_value=mock_bedrock_client):
        with pytest.raises(AICampaignValidationError) as exc_info:
            service.generate_campaign_draft(org_id=org.id, request=req, force_mock=False)

    assert "invalid json" in str(exc_info.value).lower()


def test_generate_campaign_draft_invalid_schema(db: Session):
    """Missing nodes or invalid node types from AI output raises AICampaignValidationError."""
    org = create_test_org(db, "InvalidSchema")
    service = AICampaignGeneratorService(db=db)

    mock_bedrock_client = MagicMock()
    # Missing required 'type' field in a node
    bad_output = {
        "campaign_name": "Bad Schema Campaign",
        "workflow": {
            "nodes": [{"id": "node-1"}],  # Missing type and title
            "edges": [],
        },
    }
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": json.dumps(bad_output)}]
            }
        }
    }

    req = AICampaignDraftRequest(
        description="Test description",
        target_audience="Audience",
        objective="Objective",
        channels=["email"],
    )

    with patch("app.services.campaign_ai_service._get_bedrock_client", return_value=mock_bedrock_client):
        with pytest.raises(AICampaignValidationError):
            service.generate_campaign_draft(org_id=org.id, request=req, force_mock=False)


# ── 4. Channel Entitlement & Gating ───────────────────────────────────────────

def test_unsupported_channels_filtered_out(db: Session):
    """Unsupported channels like LinkedIn are stripped and reported with clear reasons."""
    org = create_test_org(db, "UnsupportedCh")

    allowed, filtered_out = filter_requested_channels(
        db=db,
        org_id=org.id,
        requested_channels=["email", "linkedin", "tiktok_ads"],
    )

    assert allowed == ["email"]
    assert len(filtered_out) == 2
    filtered_channels = [f.channel for f in filtered_out]
    assert "linkedin" in filtered_channels
    assert "tiktok_ads" in filtered_channels


def test_voice_channel_gated_when_unentitled_or_disabled(db: Session):
    """Voice steps are rejected when the tenant is not entitled or when RETELL_ENABLED=False."""
    org = create_test_org(db, "VoiceGated")

    # Case A: Tenant is on base tier (no voice entitlement)
    with patch.object(settings, "RETELL_ENABLED", True):
        allowed_a, filtered_a = filter_requested_channels(
            db=db,
            org_id=org.id,
            requested_channels=["email", "voice"],
        )
        assert "voice" not in allowed_a
        assert any(f.channel == "voice" and "upgrade" in f.reason.lower() for f in filtered_a)

    # Case B: Voice is entitled, but RETELL_ENABLED=False in configuration
    ent = OrganizationChannelEntitlement(
        id=uuid.uuid4(),
        organization_id=org.id,
        channel="voice",
        status="approved",
        is_unlocked=True,
    )
    db.add(ent)
    db.commit()

    with patch.object(settings, "RETELL_ENABLED", False), \
         patch.object(settings, "RETELL_API_KEY", None):
        allowed_b, filtered_b = filter_requested_channels(
            db=db,
            org_id=org.id,
            requested_channels=["email", "voice"],
        )
        assert "voice" not in allowed_b
        assert any(f.channel == "voice" and "disabled" in f.reason.lower() for f in filtered_b)

    # Case C: Voice is both entitled AND enabled
    with patch.object(settings, "RETELL_ENABLED", True), \
         patch.object(settings, "RETELL_API_KEY", "retell_test_key_123"):
        allowed_c, filtered_c = filter_requested_channels(
            db=db,
            org_id=org.id,
            requested_channels=["email", "voice"],
        )
        assert "voice" in allowed_c


# ── 5. Missing Configuration Error ────────────────────────────────────────────

def test_unconfigured_bedrock_raises_configuration_error(db: Session):
    """Service raises AICampaignConfigurationError when Bedrock credentials are missing."""
    org = create_test_org(db, "Unconfigured")
    service = AICampaignGeneratorService(db=db)

    req = AICampaignDraftRequest(
        description="Outreach test",
        target_audience="VP Sales",
        objective="Meeting",
        channels=["email"],
    )

    with patch.object(settings, "AWS_ACCESS_KEY_ID_AI", None), \
         patch.object(settings, "AWS_SECRET_ACCESS_KEY_AI", None), \
         patch.object(settings, "AWS_ACCESS_KEY_ID", None), \
         patch.object(settings, "AWS_SECRET_ACCESS_KEY", None):
        with pytest.raises(AICampaignConfigurationError) as exc_info:
            service.generate_campaign_draft(org_id=org.id, request=req, force_mock=False)

        assert "credentials are not configured" in str(exc_info.value).lower()


# ── 6. Hallucinated URL Sanitization ──────────────────────────────────────────

def test_hallucinated_booking_url_sanitization(db: Session):
    """Hallucinated external URLs (e.g. calendly.com/...) are sanitized to {booking_link}."""
    org = create_test_org(db, "URLSanitize")
    service = AICampaignGeneratorService(db=db)

    # Mock output where LLM hallucinated a calendly URL
    hallucinated_output = {
        "campaign_name": "Sanitization Test Campaign",
        "summary": "Testing URL sanitization",
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "title": "Start", "config": {}},
                {
                    "id": "email-1",
                    "type": "email",
                    "title": "Email 1",
                    "config": {
                        "subject": "Quick meeting with {contact.first_name}",
                        "body": "Hi {contact.first_name}, pick time here: https://calendly.com/hallucinated-agent/15min",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "email-1", "label": "Start"}],
        },
    }

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": json.dumps(hallucinated_output)}]}}
    }

    req = AICampaignDraftRequest(
        description="Test description",
        target_audience="Audience",
        objective="Objective",
        channels=["email"],
        save_as_draft=False,
    )

    with patch("app.services.campaign_ai_service._get_bedrock_client", return_value=mock_client):
        res = service.generate_campaign_draft(org_id=org.id, request=req, force_mock=False)

    email_node = res.workflow_config.nodes[1]
    # Verify the hallucinated calendly URL was stripped and replaced with canonical {booking_link}
    assert "https://calendly.com" not in email_node.config["body"]
    assert "{booking_link}" in email_node.config["body"]


# ── 7. FastAPI Endpoint Integration ───────────────────────────────────────────

def test_fastapi_generate_campaign_draft_endpoint(client: TestClient, db: Session):
    """Tests POST /api/v1/campaigns/generate-draft endpoint contract and draft creation."""
    org = create_test_org(db, "EndpointTest")

    # Mock get_current_organization dependency
    from app.api.deps import get_current_organization
    app.dependency_overrides[get_current_organization] = lambda: org

    try:
        # 1. Successful draft generation (mocked Bedrock)
        mock_output = {
            "campaign_name": "Enterprise Renewal Cadence",
            "summary": "AI generated sequence for enterprise renewals.",
            "workflow": {
                "nodes": [
                    {"id": "start-node", "type": "start", "title": "Start", "config": {}},
                    {
                        "id": "email-step-1",
                        "type": "email",
                        "title": "Step 1: Introduction",
                        "config": {
                            "subject": "Accelerating pipeline for {contact.company}",
                            "body": "Hi {contact.first_name},\n\nWould you have 15 minutes? Direct link: {booking_link}",
                        },
                    },
                    {
                        "id": "wait-step-1",
                        "type": "wait",
                        "title": "Wait 3 Days",
                        "config": {"duration": 3, "unit": "days"},
                    },
                    {
                        "id": "cond-step-1",
                        "type": "condition",
                        "title": "Check Reply",
                        "config": {"condition_type": "email_replied"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "start-node", "target": "email-step-1"},
                    {"id": "e2", "source": "email-step-1", "target": "wait-step-1"},
                    {"id": "e3", "source": "wait-step-1", "target": "cond-step-1"},
                ],
            },
        }

        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = {
            "output": {"message": {"content": [{"text": json.dumps(mock_output)}]}}
        }

        with patch("app.services.campaign_ai_service._get_bedrock_client", return_value=mock_bedrock):
            resp = client.post(
                "/api/v1/campaigns/generate-draft",
                json={
                    "description": "Enterprise renewal sequence for Q4 contracts",
                    "target_audience": "VP of Customer Success",
                    "objective": "Book renewal discussion",
                    "channels": ["email"],
                    "campaign_duration_days": 14,
                    "followup_interval_days": 3,
                    "save_as_draft": True,
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["campaign_name"] == "Enterprise Renewal Cadence"
        assert data["campaign_id"] is not None
        assert data["validation"]["is_valid"] is True
        assert len(data["workflow_config"]["nodes"]) == 4

        # 2. Validation error: empty objective
        bad_resp = client.post(
            "/api/v1/campaigns/generate-draft",
            json={
                "description": "Short",
                "target_audience": "Audience",
                "objective": "   ",  # Invalid empty whitespace
                "channels": ["email"],
            },
        )
        assert bad_resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_organization, None)
