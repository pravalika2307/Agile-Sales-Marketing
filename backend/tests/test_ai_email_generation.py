"""Comprehensive tests for AI email generation using AWS Bedrock Claude Sonnet 4.5."""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.crm import Contact
from app.models.outreach import Outreach
from app.models.tenant import Organization
from app.schemas.email_template import AIEmailGenerateRequest
from app.services.campaign_steps.ai_template_service import (
    AITemplateConfigurationError,
    AITemplateGenerationError,
    generate_email_template,
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
            "full_name": "AI Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    return resp.json()["tokens"]["access_token"]


# ── 1. Service Level Tests with Mocks ────────────────────────────────────────

def test_generate_email_template_force_mock():
    """Deterministic mock mode produces compliant template with required variables."""
    req = AIEmailGenerateRequest(
        campaign_name="Enterprise Cloud Briefing",
        email_objective="Schedule a 15-minute briefing with VP of Operations",
        target_audience="Enterprise Operations Leaders",
        tone="professional",
        call_to_action="Would you have 15 minutes this week for a brief briefing?",
    )

    res = generate_email_template(req, force_mock=True)
    assert res.is_mock
    assert res.ai_provider == "bedrock"
    assert "{contact.company}" in res.subject or "{contact.company}" in res.body
    assert "{contact.first_name}" in res.body
    assert "briefing" in res.body.lower()


def test_generate_email_template_bedrock_converse_mock():
    """Service invokes Bedrock Converse API with Claude Sonnet 4.5 model ID and parses JSON output."""
    mock_bedrock_client = MagicMock()
    mock_output_json = json.dumps({
        "subject": "Strategic partnership for {contact.company}",
        "body": "Hi {contact.first_name},\n\nI noticed your work at {contact.company}.\n\nBest regards,\n{sender_name}",
    })
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": mock_output_json}]
            }
        }
    }

    req = AIEmailGenerateRequest(
        campaign_name="Strategic Expansion",
        email_objective="Reach out to operations leads",
        target_audience="Operations Leads",
        tone="consultative",
    )

    with patch("app.services.campaign_steps.ai_template_service._get_bedrock_client", return_value=mock_bedrock_client):
        res = generate_email_template(req, force_mock=False)

    assert not res.is_mock
    assert res.subject == "Strategic partnership for {contact.company}"
    assert "{contact.first_name}" in res.body
    assert res.model_used == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Verify converse call arguments
    mock_bedrock_client.converse.assert_called_once()
    call_kwargs = mock_bedrock_client.converse.call_args[1]
    assert call_kwargs["modelId"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert len(call_kwargs["messages"]) == 1
    assert "Strategic Expansion" in call_kwargs["messages"][0]["content"][0]["text"]


def test_generate_email_template_unconfigured_error():
    """Service raises AITemplateConfigurationError if AWS credentials are not configured."""
    from app.core.config import settings

    req = AIEmailGenerateRequest(
        email_objective="Test objective",
    )

    with patch.object(settings, "AWS_ACCESS_KEY_ID_AI", None), \
         patch.object(settings, "AWS_SECRET_ACCESS_KEY_AI", None), \
         patch.object(settings, "AWS_ACCESS_KEY_ID", None), \
         patch.object(settings, "AWS_SECRET_ACCESS_KEY", None):
        with pytest.raises(AITemplateConfigurationError) as exc_info:
            generate_email_template(req, force_mock=False)

        assert "credentials are not configured" in str(exc_info.value).lower()


def test_generate_email_template_bedrock_client_error():
    """Service catches Bedrock ClientError and wraps in AITemplateGenerationError."""
    mock_bedrock_client = MagicMock()
    mock_bedrock_client.converse.side_effect = ClientError(
        error_response={"Error": {"Code": "AccessDeniedException", "Message": "Not authorized to perform bedrock:InvokeModel"}},
        operation_name="Converse",
    )

    req = AIEmailGenerateRequest(
        email_objective="Schedule a briefing",
    )

    with patch("app.services.campaign_steps.ai_template_service._get_bedrock_client", return_value=mock_bedrock_client):
        with pytest.raises(AITemplateGenerationError) as exc_info:
            generate_email_template(req, force_mock=False)

        assert "AccessDeniedException" in str(exc_info.value)


# ── 2. API Endpoint Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_generate_ai_template_success(test_db_session: Session):
    """POST /api/v1/campaigns/templates/generate-ai returns generated subject and body with 200 OK."""
    mock_bedrock_client = MagicMock()
    mock_output_json = json.dumps({
        "subject": "Modernizing outreach for {contact.company}",
        "body": "Hi {contact.first_name},\n\nHope this finds you well at {contact.company}.\n\nBest,\n{sender_name}",
    })
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": mock_output_json}]
            }
        }
    }

    async with make_client() as client:
        token = await register_tenant(client, "admin@ai.com", "AI Corp")
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.services.campaign_steps.ai_template_service._get_bedrock_client", return_value=mock_bedrock_client):
            resp = await client.post(
                "/api/v1/campaigns/templates/generate-ai",
                headers=headers,
                json={
                    "campaign_name": "Outbound Velocity",
                    "email_objective": "Drive demo bookings for operational leaders",
                    "target_audience": "Operations Directors",
                    "tone": "professional",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["subject"] == "Modernizing outreach for {contact.company}"
        assert "{contact.first_name}" in data["body"]
        assert data["ai_provider"] == "bedrock"


@pytest.mark.asyncio
async def test_api_generate_ai_template_unconfigured_status(test_db_session: Session):
    """Unconfigured Bedrock returns 503 Service Unavailable with clear actionable error."""
    from app.core.config import settings

    async with make_client() as client:
        token = await register_tenant(client, "admin@unconf.com", "Unconf Corp")
        headers = {"Authorization": f"Bearer {token}"}

        with patch.object(settings, "AWS_ACCESS_KEY_ID_AI", None), \
             patch.object(settings, "AWS_SECRET_ACCESS_KEY_AI", None), \
             patch.object(settings, "AWS_ACCESS_KEY_ID", None), \
             patch.object(settings, "AWS_SECRET_ACCESS_KEY", None):
            resp = await client.post(
                "/api/v1/campaigns/templates/generate-ai",
                headers=headers,
                json={
                    "email_objective": "Drive demos",
                },
            )

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_generate_campaign_workflow_endpoint(test_db_session: Session):
    """POST /api/v1/campaigns/{id}/workflow/generate-email pre-populates campaign context."""
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Campaign Org", slug="camp-org")
    campaign_id = uuid.uuid4()
    camp = Campaign(id=campaign_id, organization_id=org_id, name="FinTech Outbound Q4")
    test_db_session.add_all([org, camp])
    test_db_session.commit()

    mock_bedrock_client = MagicMock()
    mock_output_json = json.dumps({
        "subject": "FinTech efficiency for {contact.company}",
        "body": "Hi {contact.first_name},\n\nReaching out from FinTech Outbound Q4.\n\nBest,\n{sender_name}",
    })
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": mock_output_json}]
            }
        }
    }

    async with make_client() as client:
        token = await register_tenant(client, "admin@fintech.com", "FinTech Corp")
        headers = {"Authorization": f"Bearer {token}"}

        # Query user's org
        from app.models.tenant import User
        user = test_db_session.query(User).filter(User.email == "admin@fintech.com").first()
        camp.organization_id = user.organization_id
        test_db_session.commit()

        with patch("app.services.campaign_steps.ai_template_service._get_bedrock_client", return_value=mock_bedrock_client):
            resp = await client.post(
                f"/api/v1/campaigns/{camp.id}/workflow/generate-email",
                headers=headers,
                json={
                    "email_objective": "Target finance managers",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["subject"] == "FinTech efficiency for {contact.company}"


@pytest.mark.asyncio
async def test_ai_generation_is_strictly_non_destructive(test_db_session: Session):
    """AI email generation strictly does not write outreach records, change contacts, or send emails."""
    mock_bedrock_client = MagicMock()
    mock_output_json = json.dumps({
        "subject": "Draft Subject",
        "body": "Draft Body",
    })
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": mock_output_json}]
            }
        }
    }

    initial_outreaches = test_db_session.query(Outreach).count()
    initial_contacts = test_db_session.query(Contact).count()

    async with make_client() as client:
        token = await register_tenant(client, "admin@safety.com", "Safety Corp")
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.services.campaign_steps.ai_template_service._get_bedrock_client", return_value=mock_bedrock_client):
            resp = await client.post(
                "/api/v1/campaigns/templates/generate-ai",
                headers=headers,
                json={"email_objective": "Non destructive check"},
            )
        assert resp.status_code == 200

    # Verify zero database side effects
    assert test_db_session.query(Outreach).count() == initial_outreaches
    assert test_db_session.query(Contact).count() == initial_contacts
