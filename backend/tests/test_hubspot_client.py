"""Unit tests for HubSpotClient."""
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from app.services.integrations.hubspot.client import (
    HubSpotAuthenticationError,
    HubSpotClient,
    HubSpotConfigurationError,
    HubSpotConflictError,
    HubSpotNotFoundError,
    HubSpotRateLimitError,
    HubSpotTimeoutError,
)


def test_client_repr_does_not_leak_token():
    secret_token = "pat-na2-super-sensitive-12345678"
    client = HubSpotClient(access_token=secret_token)
    repr_str = repr(client)
    assert secret_token not in repr_str
    assert "configured=True" in repr_str


def test_unconfigured_client_raises_configuration_error():
    client = HubSpotClient(access_token="")
    assert not client.is_configured
    with pytest.raises(HubSpotConfigurationError):
        client._auth_headers()


@pytest.mark.asyncio
async def test_successful_request(hubspot_client):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {"results": []}

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        resp = await hubspot_client.get("/crm/v3/owners")
        assert resp.status_code == 200
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")
        assert "application/json" in kwargs["headers"]["Content-Type"]


@pytest.mark.asyncio
async def test_authentication_error(hubspot_client):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.is_success = False
    mock_resp.json.return_value = {"message": "Invalid token"}
    mock_resp.text = '{"message": "Invalid token"}'

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        with pytest.raises(HubSpotAuthenticationError) as exc_info:
            await hubspot_client.get("/crm/v3/owners")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_not_found_error(hubspot_client):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.is_success = False
    mock_resp.json.return_value = {"message": "Contact not found"}
    mock_resp.text = "Contact not found"

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        with pytest.raises(HubSpotNotFoundError):
            await hubspot_client.get("/crm/v3/objects/contacts/999999")


@pytest.mark.asyncio
async def test_conflict_error(hubspot_client):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 409
    mock_resp.is_success = False
    mock_resp.text = 'Contact already exists. Existing ID: 54321'
    mock_resp.json.return_value = {"message": "Contact already exists. Existing ID: 54321"}

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        with pytest.raises(HubSpotConflictError) as exc_info:
            await hubspot_client.post("/crm/v3/objects/contacts", json_data={"properties": {"email": "test@test.com"}})
        assert "54321" in exc_info.value.response_text


@pytest.mark.asyncio
async def test_rate_limit_error(hubspot_client):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.is_success = False
    mock_resp.json.return_value = {"message": "Rate limit exceeded"}
    mock_resp.text = "Rate limit exceeded"

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        with pytest.raises(HubSpotRateLimitError):
            await hubspot_client.get("/crm/v3/owners")


@pytest.mark.asyncio
async def test_timeout_resilience(hubspot_client):
    with patch("httpx.AsyncClient.request", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(HubSpotTimeoutError):
            await hubspot_client.get("/crm/v3/owners")


@pytest.mark.asyncio
async def test_validate_credentials_success(hubspot_client):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": [{"id": "owner_1"}, {"id": "owner_2"}]}

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        result = await hubspot_client.validate_credentials()
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["details"]["owners_sampled"] == 2


@pytest.mark.asyncio
async def test_validate_credentials_unconfigured(unconfigured_hubspot_client):
    result = await unconfigured_hubspot_client.validate_credentials()
    assert result["success"] is False
    assert "not configured" in result["message"]
