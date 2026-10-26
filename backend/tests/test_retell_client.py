"""Unit & Integration tests for Retell API client, Agent Discovery, and Connection Health."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest
import httpx

from app.core.config import settings
from app.services.voice.retell_client import (
    RetellAPIError,
    RetellAgentDetail,
    RetellAgentSummary,
    RetellAuthenticationError,
    RetellClient,
    RetellConfigurationError,
    RetellConnectionStatus,
    RetellError,
    RetellNotFoundError,
    RetellPermissionError,
    RetellRateLimitError,
    RetellTimeoutError,
    get_retell_client,
)


# ── Sample Fixtures ───────────────────────────────────────────────────────────

SAMPLE_AGENTS_V2 = {
    "items": [
        {
            "agent_id": "agent_3d80320b8eb60bcc212da34856",
            "agent_name": "Outbound B2B SDR Agent",
            "channel": "voice",
            "voice_id": "11labs-Ryan",
            "user_modified_timestamp": 1729000000000,
            "response_engine": {
                "type": "retell-llm",
                "llm_id": "llm_cd09d862e48d07e25f1700334031",
            },
        },
        {
            "agent_id": "agent_46fb4b1901d63d803e5ef3030e",
            "agent_name": "Inbound Sales Receptionist",
            "channel": "voice",
            "voice_id": "11labs-Rachel",
            "user_modified_timestamp": 1729100000000,
            "response_engine": {
                "type": "conversation-flow",
                "conversation_flow_id": "conversation_flow_efec35923e7c",
            },
        },
    ],
    "has_more": False,
    "pagination_key": None,
}

SAMPLE_AGENT_DETAIL = {
    "agent_id": "agent_3d80320b8eb60bcc212da34856",
    "agent_name": "Outbound B2B SDR Agent",
    "channel": "voice",
    "voice_id": "11labs-Ryan",
    "voice_model": "eleven_flash_v2",
    "fallback_voice_ids": ["11labs-Adam"],
    "voice_temperature": 0.7,
    "voice_speed": 1.05,
    "responsiveness": 1.0,
    "interruption_sensitivity": 0.8,
    "enable_backchannel": True,
    "ambient_sound": "coffee-shop",
    "language": "en-US",
    "is_published": True,
    "response_engine": {
        "type": "retell-llm",
        "llm_id": "llm_cd09d862e48d07e25f1700334031",
    },
    "post_call_analysis_data": [
        {"name": "qualification_outcome", "type": "enum"},
        {"name": "lead_interest_summary", "type": "string"},
    ],
    "last_modification_timestamp": 1729000000000,
}


# ── Client Core Tests ─────────────────────────────────────────────────────────

def test_retell_client_initialization_and_repr():
    """Verify client initialization, config check, and secret masking in repr."""
    secret_key = "key_super_secret_retell_12345"
    client = RetellClient(api_key=secret_key, base_url="https://api.retellai.com")

    assert client.is_configured is True
    assert client.base_url == "https://api.retellai.com"
    assert secret_key not in repr(client)
    assert "configured=True" in repr(client)

    unconfigured_client = RetellClient(api_key="")
    assert unconfigured_client.is_configured is False
    assert "configured=False" in repr(unconfigured_client)


def test_retell_client_missing_key_raises_config_error():
    """Verify attempting to make requests without an API key fails closed."""
    client = RetellClient(api_key="")
    with pytest.raises(RetellConfigurationError, match="not configured"):
        client.list_agents()


def test_retell_client_list_agents_success():
    """Test successful agent discovery parsing Retell v2 paginated response."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v2/list-agents"
        assert request.headers["Authorization"] == "Bearer mock_key_123"
        return httpx.Response(200, json=SAMPLE_AGENTS_V2)

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key_123", http_client=mock_http)

    agents = client.list_agents()
    assert len(agents) == 2
    assert agents[0].agent_id == "agent_3d80320b8eb60bcc212da34856"
    assert agents[0].agent_name == "Outbound B2B SDR Agent"
    assert agents[0].voice_id == "11labs-Ryan"
    assert agents[0].llm_id == "llm_cd09d862e48d07e25f1700334031"
    assert agents[1].agent_id == "agent_46fb4b1901d63d803e5ef3030e"
    assert agents[1].response_engine_type == "conversation-flow"


def test_retell_client_list_agents_array_fallback():
    """Test backward compatibility with array response format."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_AGENTS_V2["items"])

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key_123", http_client=mock_http)

    agents = client.list_agents()
    assert len(agents) == 2
    assert agents[0].agent_name == "Outbound B2B SDR Agent"


def test_retell_client_get_agent_success():
    """Test fetching individual agent details via GET /get-agent/{agent_id}."""
    target_id = "agent_3d80320b8eb60bcc212da34856"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/get-agent/{target_id}"
        return httpx.Response(200, json=SAMPLE_AGENT_DETAIL)

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key_123", http_client=mock_http)

    agent = client.get_agent(target_id)
    assert agent.agent_id == target_id
    assert agent.agent_name == "Outbound B2B SDR Agent"
    assert agent.voice_model == "eleven_flash_v2"
    assert agent.ambient_sound == "coffee-shop"
    assert agent.interruption_sensitivity == 0.8
    assert len(agent.post_call_analysis_data) == 2


def test_retell_client_get_agent_empty_id_raises():
    """Verify empty agent_id is rejected with ValueError before any network call."""
    client = RetellClient(api_key="mock_key_123")
    with pytest.raises(ValueError, match="agent_id must not be empty"):
        client.get_agent("   ")


def test_retell_client_authentication_failure():
    """Verify HTTP 401 raises RetellAuthenticationError with sanitized message."""
    secret = "secret_key_abc_999"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": f"Unauthorized key: {secret}"})

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key=secret, http_client=mock_http)

    with pytest.raises(RetellAuthenticationError) as exc_info:
        client.list_agents()

    assert exc_info.value.status_code == 401
    assert secret not in str(exc_info.value)
    assert "********" in str(exc_info.value)


def test_retell_client_permission_denied():
    """Verify HTTP 403 raises RetellPermissionError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Workspace access forbidden"})

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key", http_client=mock_http)

    with pytest.raises(RetellPermissionError) as exc_info:
        client.list_agents()
    assert exc_info.value.status_code == 403


def test_retell_client_not_found():
    """Verify HTTP 404 raises RetellNotFoundError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Agent agent_unknown not found"})

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key", http_client=mock_http)

    with pytest.raises(RetellNotFoundError):
        client.get_agent("agent_unknown")


def test_retell_client_rate_limiting():
    """Verify HTTP 429 raises RetellRateLimitError and parses Retry-After header."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "30"},
            json={"message": "Too Many Requests"},
        )

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key", http_client=mock_http)

    with pytest.raises(RetellRateLimitError) as exc_info:
        client.list_agents()
    assert exc_info.value.retry_after == 30


def test_retell_client_timeout():
    """Verify network timeouts raise RetellTimeoutError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out after 5.0 seconds")

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key", timeout=5.0, http_client=mock_http)

    with pytest.raises(RetellTimeoutError, match="timed out after 5.0s"):
        client.list_agents()


def test_retell_client_server_error():
    """Verify HTTP 500 raises RetellAPIError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "Internal telephony service error"})

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key", http_client=mock_http)

    with pytest.raises(RetellAPIError) as exc_info:
        client.list_agents()
    assert exc_info.value.status_code == 500


def test_retell_client_check_connection_success():
    """Verify check_connection probes agent availability and cross-checks configured IDs."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_AGENTS_V2)

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="mock_key", http_client=mock_http)

    with patch.object(settings, "RETELL_AGENT_ID", "agent_3d80320b8eb60bcc212da34856"), \
         patch.object(settings, "RETELL_INBOUND_AGENT_ID", "agent_46fb4b1901d63d803e5ef3030e"), \
         patch.object(settings, "RETELL_FROM_NUMBER", "+16416818482"):
        status = client.check_connection()

    assert status.configured is True
    assert status.connected is True
    assert status.agent_count == 2
    assert status.outbound_agent_valid is True
    assert status.inbound_agent_valid is True
    assert status.caller_id == "+16416818482"
    assert status.error is None
    assert "2 voice agent(s) discovered" in status.message


def test_retell_client_check_connection_unconfigured():
    """Verify check_connection returns graceful unconfigured status when key is absent."""
    client = RetellClient(api_key="")
    status = client.check_connection()

    assert status.configured is False
    assert status.connected is False
    assert status.agent_count == 0
    assert "unconfigured" in status.message


def test_retell_client_check_connection_auth_failure():
    """Verify check_connection catches authentication error without crashing."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad API key"})

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="bad_key", http_client=mock_http)

    status = client.check_connection()
    assert status.configured is True
    assert status.connected is False
    assert status.error == "Authentication failed"
    assert "authentication rejected" in status.message


def test_retell_client_list_phone_numbers():
    """Verify list_phone_numbers returns registered phone numbers safely."""
    sample_phones = {
        "items": [
            {
                "phone_number": "+16416818482",
                "nickname": "agile-dev",
                "phone_number_pretty": "+16416818482",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/v2/list-phone-numbers" in str(request.url)
        return httpx.Response(200, json=sample_phones)

    transport = httpx.MockTransport(handler)
    mock_http = httpx.Client(transport=transport)
    client = RetellClient(api_key="valid_key", http_client=mock_http)

    phones = client.list_phone_numbers()
    assert len(phones) == 1
    assert phones[0]["phone_number"] == "+16416818482"
    assert phones[0]["nickname"] == "agile-dev"

