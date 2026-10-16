"""Unit tests for HubSpotContactService."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.integrations.hubspot.client import (
    HubSpotConflictError,
    HubSpotNotFoundError,
)
from app.services.integrations.hubspot.contacts import HubSpotContactService


@pytest.mark.asyncio
async def test_search_contact_found(contact_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"id": "1001", "properties": {"email": "lead@example.com", "firstname": "Alex"}}
        ]
    }
    with patch.object(hubspot_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        contact = await contact_service.search_contact_by_email("lead@example.com")
        assert contact is not None
        assert contact["id"] == "1001"
        assert contact["properties"]["firstname"] == "Alex"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_search_contact_not_found(contact_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    with patch.object(hubspot_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        contact = await contact_service.search_contact_by_email("unknown@example.com")
        assert contact is None


@pytest.mark.asyncio
async def test_get_contact_found(contact_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "1001", "properties": {"firstname": "Alex"}}
    with patch.object(hubspot_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        contact = await contact_service.get_contact("1001")
        assert contact["id"] == "1001"


@pytest.mark.asyncio
async def test_get_contact_404_recovery(contact_service, hubspot_client):
    with patch.object(hubspot_client, "get", side_effect=HubSpotNotFoundError("Not found")):
        contact = await contact_service.get_contact("9999")
        assert contact is None


@pytest.mark.asyncio
async def test_update_contact_success(contact_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "1001", "properties": {"phone": "+15559999"}}
    with patch.object(hubspot_client, "patch", new_callable=AsyncMock) as mock_patch:
        mock_patch.return_value = mock_resp
        result = await contact_service.update_contact("1001", {"phone": "+15559999"})
        assert result["id"] == "1001"


@pytest.mark.asyncio
async def test_update_contact_404(contact_service, hubspot_client):
    with patch.object(hubspot_client, "patch", side_effect=HubSpotNotFoundError("Not found")):
        result = await contact_service.update_contact("9999", {"phone": "+15559999"})
        assert result is None


@pytest.mark.asyncio
async def test_create_contact_success(contact_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "2002", "properties": {"email": "new@example.com"}}
    with patch.object(hubspot_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await contact_service.create_contact({"email": "new@example.com", "firstname": "Sam"})
        assert result["id"] == "2002"


@pytest.mark.asyncio
async def test_create_contact_409_conflict_with_id_in_message(contact_service, hubspot_client):
    conflict_err = HubSpotConflictError(
        message="Contact already exists",
        response_text="Contact already exists. Existing ID: 8888",
    )
    mock_update_resp = MagicMock()
    mock_update_resp.json.return_value = {"id": "8888", "properties": {"email": "dup@example.com"}}

    with patch.object(hubspot_client, "post", side_effect=conflict_err):
        with patch.object(hubspot_client, "patch", new_callable=AsyncMock) as mock_patch:
            mock_patch.return_value = mock_update_resp
            result = await contact_service.create_contact({"email": "dup@example.com", "lastname": "Jones"})
            assert result["id"] == "8888"
            mock_patch.assert_called_once()


@pytest.mark.asyncio
async def test_sync_contact_flow(contact_service):
    with patch.object(contact_service, "search_contact_by_email", new_callable=AsyncMock) as mock_search:
        with patch.object(contact_service, "update_contact", new_callable=AsyncMock) as mock_update:
            mock_search.return_value = {"id": "3003"}
            mock_update.return_value = {"id": "3003", "properties": {"email": "sync@example.com"}}

            result = await contact_service.sync_contact("sync@example.com", {"firstname": "Taylor"})
            assert result["id"] == "3003"
            mock_search.assert_called_once_with("sync@example.com")
            mock_update.assert_called_once()
