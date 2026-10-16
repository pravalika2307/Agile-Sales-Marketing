"""Pytest fixtures and test environment setup."""
from __future__ import annotations

import os
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import app
from app.services.integrations.hubspot import (
    HubSpotAssociationService,
    HubSpotClient,
    HubSpotContactService,
    HubSpotDealService,
)

MOCK_TOKEN = "pat-na2-mock-token-sales-marketing-12345"


@pytest.fixture
def mock_token() -> str:
    return MOCK_TOKEN


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        HUBSPOT_ACCESS_TOKEN=MOCK_TOKEN,
        HUBSPOT_BASE_URL="https://api.hubapi.com",
        HUBSPOT_TIMEOUT_SECONDS=5.0,
    )


@pytest.fixture
def hubspot_client(mock_token) -> HubSpotClient:
    return HubSpotClient(access_token=mock_token, base_url="https://api.hubapi.com", timeout=5.0)


@pytest.fixture
def unconfigured_hubspot_client() -> HubSpotClient:
    return HubSpotClient(access_token="", base_url="https://api.hubapi.com", timeout=5.0)


@pytest.fixture
def contact_service(hubspot_client) -> HubSpotContactService:
    return HubSpotContactService(client=hubspot_client)


@pytest.fixture
def deal_service(hubspot_client) -> HubSpotDealService:
    return HubSpotDealService(client=hubspot_client)


@pytest.fixture
def association_service(hubspot_client) -> HubSpotAssociationService:
    return HubSpotAssociationService(client=hubspot_client)


@pytest.fixture
async def async_api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture(autouse=True)
def isolate_test_email_provider(monkeypatch):
    """Ensure automated tests use mock email provider by default so no real emails are sent."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "EMAIL_PROVIDER_TYPE", "mock")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")

