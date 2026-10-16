"""HubSpot CRM Integration Package.

Exports clean, modular clients, services, and domain exceptions.
"""
from .client import (
    HubSpotClient,
    HubSpotError,
    HubSpotConfigurationError,
    HubSpotAuthenticationError,
    HubSpotPermissionError,
    HubSpotNotFoundError,
    HubSpotConflictError,
    HubSpotRateLimitError,
    HubSpotTimeoutError,
    HubSpotAPIError,
)
from .contacts import HubSpotContactService, STANDARD_CONTACT_PROPERTIES
from .deals import HubSpotDealService, STANDARD_DEAL_PROPERTIES, DEFAULT_PIPELINE
from .associations import HubSpotAssociationService, DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID
from .sync import HubSpotSyncEngine, HubSpotSyncSummary, ObjectSyncResult

__all__ = [
    "HubSpotClient",
    "HubSpotContactService",
    "HubSpotDealService",
    "HubSpotAssociationService",
    "HubSpotSyncEngine",
    "HubSpotSyncSummary",
    "ObjectSyncResult",
    "HubSpotError",
    "HubSpotConfigurationError",
    "HubSpotAuthenticationError",
    "HubSpotPermissionError",
    "HubSpotNotFoundError",
    "HubSpotConflictError",
    "HubSpotRateLimitError",
    "HubSpotTimeoutError",
    "HubSpotAPIError",
    "STANDARD_CONTACT_PROPERTIES",
    "STANDARD_DEAL_PROPERTIES",
    "DEFAULT_PIPELINE",
    "DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID",
]
