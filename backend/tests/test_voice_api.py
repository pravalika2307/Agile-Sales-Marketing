"""Integration and Security tests for FastAPI Voice endpoints (/api/v1/voice/status & /api/v1/voice/agents)."""
import uuid
from unittest.mock import MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_active_user, get_current_organization, get_db
from app.core.database import Base
from app.main import app
from app.models.tenant import Organization, User
from app.services.voice.retell_client import (
    RetellAgentDetail,
    RetellAgentSummary,
    RetellAuthenticationError,
    RetellClient,
    RetellConnectionStatus,
    RetellNotFoundError,
    RetellTimeoutError,
    get_retell_client,
)


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
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_organization, None)
        app.dependency_overrides.pop(get_retell_client, None)


@pytest.fixture
def auth_context(test_db_session):
    """Seed tenant organization and active user, configure dependency overrides."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="Agile Voice Test Org",
        slug="agile-voice-org",
    )
    test_db_session.add(org)

    user = User(
        id=uuid.uuid4(),
        organization_id=org_id,
        email="voiceadmin@agilevoice.com",
        full_name="Voice Admin",
        hashed_password="mock_hashed_pw",
        role="admin",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    def override_current_user():
        return user

    def override_current_org():
        return org

    app.dependency_overrides[get_current_active_user] = override_current_user
    app.dependency_overrides[get_current_organization] = override_current_org

    return {"org": org, "user": user}


# ── Status Endpoint Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_status_unauthenticated(test_db_session):
    """Verify GET /api/v1/voice/status requires authentication."""
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_organization, None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_voice_status_connected_success(auth_context):
    """Verify GET /api/v1/voice/status returns connection details when Retell is active."""
    mock_client = MagicMock(spec=RetellClient)
    mock_client.check_connection.return_value = RetellConnectionStatus(
        configured=True,
        connected=True,
        provider="retell",
        base_url="https://api.retellai.com",
        agent_count=2,
        configured_outbound_agent_id="agent_outbound_123",
        configured_inbound_agent_id="agent_inbound_456",
        outbound_agent_valid=True,
        inbound_agent_valid=True,
        caller_id="+16416818482",
        error=None,
        message="Retell AI connection active. 2 voice agent(s) discovered.",
    )
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["connected"] is True
    assert data["agent_count"] == 2
    assert data["outbound_agent_id"] == "agent_outbound_123"
    assert data["inbound_agent_id"] == "agent_inbound_456"
    assert data["outbound_from_number"] == "+16416818482"
    assert "api_key" not in data


@pytest.mark.asyncio
async def test_voice_status_unconfigured(auth_context):
    """Verify GET /api/v1/voice/status returns clean unconfigured state."""
    mock_client = MagicMock(spec=RetellClient)
    mock_client.check_connection.return_value = RetellConnectionStatus(
        configured=False,
        connected=False,
        provider="retell",
        base_url="https://api.retellai.com",
        agent_count=0,
        configured_outbound_agent_id=None,
        configured_inbound_agent_id=None,
        caller_id=None,
        error="RETELL_API_KEY is not configured",
        message="Retell AI voice provider is unconfigured.",
    )
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["connected"] is False
    assert data["agent_count"] == 0
    assert "unconfigured" in data["message"]


# ── Agent Listing & Detail Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_agents_list_success(auth_context):
    """Verify GET /api/v1/voice/agents lists discovered agents."""
    mock_client = MagicMock(spec=RetellClient)
    mock_client.is_configured = True
    mock_client.list_agents.return_value = [
        RetellAgentSummary(
            agent_id="agent_sdr_01",
            agent_name="Outbound SDR",
            channel="voice",
            voice_id="11labs-Ryan",
            user_modified_timestamp=1729000000000,
            response_engine_type="retell-llm",
            llm_id="llm_sdr_01",
        ),
        RetellAgentSummary(
            agent_id="agent_inbound_02",
            agent_name="Receptionist",
            channel="voice",
            voice_id="11labs-Rachel",
            user_modified_timestamp=1729100000000,
            response_engine_type="conversation-flow",
        ),
    ]
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    with patch("app.core.config.settings.RETELL_AGENT_ID", "agent_sdr_01"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/voice/agents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["connected"] is True
    assert data["count"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["agent_id"] == "agent_sdr_01"
    assert data["items"][0]["is_configured_sdr"] is True
    assert data["items"][1]["agent_id"] == "agent_inbound_02"
    assert data["items"][1]["is_configured_sdr"] is False


@pytest.mark.asyncio
async def test_voice_agents_unconfigured_returns_empty_list(auth_context):
    """Verify GET /api/v1/voice/agents returns clean response when provider unconfigured."""
    mock_client = MagicMock(spec=RetellClient)
    mock_client.is_configured = False
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice/agents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["count"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_voice_agents_auth_failure_handling(auth_context):
    """Verify provider 401 returns graceful error without server crash."""
    mock_client = MagicMock(spec=RetellClient)
    mock_client.is_configured = True
    mock_client.list_agents.side_effect = RetellAuthenticationError("Invalid API key")
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice/agents")

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["error"] == "Authentication failed"


@pytest.mark.asyncio
async def test_voice_agent_detail_success(auth_context):
    """Verify GET /api/v1/voice/agents/{agent_id} returns detailed configuration."""
    target_id = "agent_detailed_123"
    mock_client = MagicMock(spec=RetellClient)
    mock_client.is_configured = True
    mock_client.get_agent.return_value = RetellAgentDetail(
        agent_id=target_id,
        agent_name="Specialized B2B Agent",
        channel="voice",
        voice_id="11labs-Ryan",
        voice_model="eleven_flash_v2",
        language="en-US",
        responsiveness=1.0,
        interruption_sensitivity=0.8,
        enable_backchannel=True,
        ambient_sound="coffee-shop",
        response_engine={"type": "retell-llm", "llm_id": "llm_test_99"},
        post_call_analysis_data=[{"name": "qualification_outcome"}],
    )
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/v1/voice/agents/{target_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == target_id
    assert data["agent_name"] == "Specialized B2B Agent"
    assert data["voice_model"] == "eleven_flash_v2"
    assert data["enable_backchannel"] is True


@pytest.mark.asyncio
async def test_voice_agent_detail_not_found(auth_context):
    """Verify GET /api/v1/voice/agents/{agent_id} returns 404 for unknown agent."""
    mock_client = MagicMock(spec=RetellClient)
    mock_client.is_configured = True
    mock_client.get_agent.side_effect = RetellNotFoundError("Agent not found", "agent_missing")
    app.dependency_overrides[get_retell_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/voice/agents/agent_missing")

    assert resp.status_code == 404
    data = resp.json()
    assert "not found" in data["detail"].lower()
