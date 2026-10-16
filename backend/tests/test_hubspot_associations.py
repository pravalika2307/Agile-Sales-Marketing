"""Unit tests for HubSpotAssociationService."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.integrations.hubspot.associations import (
    DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID,
    HubSpotAssociationService,
)


def test_build_deal_contact_association_payload(association_service):
    payload = association_service.build_deal_contact_association_payload("contact_777")
    assert payload["to"]["id"] == "contact_777"
    assert payload["types"][0]["associationTypeId"] == DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID
    assert payload["types"][0]["associationCategory"] == "HUBSPOT_DEFINED"


@pytest.mark.asyncio
async def test_associate_deal_to_contact_success(association_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch.object(hubspot_client, "put", new_callable=AsyncMock) as mock_put:
        mock_put.return_value = mock_resp
        success = await association_service.associate_deal_to_contact("deal_100", "contact_200")
        assert success is True
        mock_put.assert_called_once_with(
            "/crm/v3/objects/deals/deal_100/associations/contacts/contact_200/deal_to_contact",
            check_status=False,
        )


@pytest.mark.asyncio
async def test_associate_deal_to_contact_failure(association_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    with patch.object(hubspot_client, "put", new_callable=AsyncMock) as mock_put:
        mock_put.return_value = mock_resp
        success = await association_service.associate_deal_to_contact("deal_100", "contact_200")
        assert success is False


@pytest.mark.asyncio
async def test_remove_association(association_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch.object(hubspot_client, "delete", new_callable=AsyncMock) as mock_del:
        mock_del.return_value = mock_resp
        success = await association_service.remove_deal_to_contact_association("deal_100", "contact_200")
        assert success is True
