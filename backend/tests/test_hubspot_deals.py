"""Unit tests for HubSpotDealService."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.integrations.hubspot.client import HubSpotNotFoundError
from app.services.integrations.hubspot.deals import HubSpotDealService


@pytest.mark.asyncio
async def test_create_deal_standard_properties(deal_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "deal_123", "properties": {"dealname": "Enterprise Deal"}}

    with patch.object(hubspot_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        props = {
            "dealname": "Enterprise Deal",
            "amount": "50000.0",
            "dealstage": "appointmentscheduled",
            "closedate": "2026-12-31T23:59:59+00:00",
            "description": "Annual SaaS subscription",
        }
        deal = await deal_service.create_deal(props)
        assert deal["id"] == "deal_123"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json_data"]
        assert payload["properties"]["pipeline"] == "default"
        assert payload["properties"]["dealname"] == "Enterprise Deal"
        assert payload["properties"]["amount"] == "50000.0"


@pytest.mark.asyncio
async def test_create_deal_duplicate_prevention(deal_service):
    with patch.object(deal_service, "update_deal", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"id": "deal_existing_555", "properties": {"amount": "7000.0"}}
        result = await deal_service.create_deal(
            properties={"amount": "7000.0"},
            existing_deal_id="deal_existing_555",
        )
        assert result["id"] == "deal_existing_555"
        mock_update.assert_called_once_with("deal_existing_555", {"amount": "7000.0"})


@pytest.mark.asyncio
async def test_get_deal_found(deal_service, hubspot_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "deal_123"}
    with patch.object(hubspot_client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        deal = await deal_service.get_deal("deal_123")
        assert deal["id"] == "deal_123"


@pytest.mark.asyncio
async def test_get_deal_404_recovery(deal_service, hubspot_client):
    with patch.object(hubspot_client, "get", side_effect=HubSpotNotFoundError("Deal not found")):
        deal = await deal_service.get_deal("deal_unknown")
        assert deal is None


@pytest.mark.asyncio
async def test_update_deal_stage(deal_service):
    with patch.object(deal_service, "update_deal", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"id": "deal_123", "properties": {"dealstage": "closedwon"}}
        close_dt = datetime(2026, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = await deal_service.update_deal_stage(
            deal_id="deal_123",
            stage="closedwon",
            amount=Decimal("15000.00"),
            close_date=close_dt,
        )
        assert result["id"] == "deal_123"
        mock_update.assert_called_once_with(
            "deal_123",
            {
                "dealstage": "closedwon",
                "amount": "15000.0",
                "closedate": "2026-12-01T10:00:00+00:00",
            },
        )
