"""HubSpot Deals Service.

Provides deal management operations against HubSpot CRM v3:
- create deal
- get deal by ID
- update deal
- update deal stage
- duplicate prevention (updates if existing ID supplied)
- verified standard HubSpot deal properties (dealname, amount, pipeline, dealstage, closedate, description)
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Union

from .client import (
    HubSpotClient,
    HubSpotNotFoundError,
)

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE = "default"

# Standard verified HubSpot deal property keys
STANDARD_DEAL_PROPERTIES = [
    "dealname",
    "amount",
    "pipeline",
    "dealstage",
    "closedate",
    "description",
    "createdate",
    "hs_lastmodifieddate",
    "hubspot_owner_id",
]


class HubSpotDealService:
    """Service for interacting with HubSpot Deals API."""

    def __init__(self, client: Optional[HubSpotClient] = None) -> None:
        self.client = client or HubSpotClient()

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    @staticmethod
    def format_amount(amount: Union[int, float, Decimal, str]) -> str:
        """Format monetary amount to standard HubSpot decimal string representation."""
        try:
            return str(float(amount))
        except (ValueError, TypeError):
            return "0"

    @staticmethod
    def format_close_date(close_date: Union[datetime, str]) -> str:
        """Format close date to ISO 8601 UTC string."""
        if isinstance(close_date, datetime):
            if close_date.tzinfo is None:
                close_date = close_date.replace(tzinfo=timezone.utc)
            return close_date.isoformat()
        return str(close_date)

    async def get_deal(
        self,
        deal_id: str,
        properties: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch deal by HubSpot deal ID.
        GET /crm/v3/objects/deals/{deal_id}
        Returns None on 404.
        """
        if not self.is_configured or not deal_id:
            return None

        clean_id = str(deal_id).strip()
        props = properties or STANDARD_DEAL_PROPERTIES
        params = {"properties": ",".join(props)}

        try:
            resp = await self.client.get(f"/crm/v3/objects/deals/{clean_id}", params=params)
            return resp.json()
        except HubSpotNotFoundError:
            logger.info("HubSpot deal %s not found (404)", clean_id)
            return None
        except Exception as exc:
            logger.warning("Error fetching HubSpot deal %s: %s", clean_id, exc)
            return None

    async def update_deal(
        self,
        deal_id: str,
        properties: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing HubSpot deal.
        PATCH /crm/v3/objects/deals/{deal_id}
        Returns None on 404.
        """
        if not self.is_configured or not deal_id:
            return None

        clean_id = str(deal_id).strip()
        payload = {"properties": properties}

        try:
            resp = await self.client.patch(f"/crm/v3/objects/deals/{clean_id}", json_data=payload)
            updated = resp.json()
            logger.info("Successfully updated HubSpot deal %s", clean_id)
            return updated
        except HubSpotNotFoundError:
            logger.warning("HubSpot deal %s not found for update (404)", clean_id)
            return None
        except Exception as exc:
            logger.warning("Error updating HubSpot deal %s: %s", clean_id, exc)
            return None

    async def create_deal(
        self,
        properties: Dict[str, Any],
        associations: Optional[List[Dict[str, Any]]] = None,
        existing_deal_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a HubSpot deal, or update if existing_deal_id is supplied to avoid duplicates.
        POST /crm/v3/objects/deals
        """
        if not self.is_configured:
            return None

        # Duplicate prevention: If existing deal ID is supplied, update instead
        if existing_deal_id:
            logger.info("Existing deal ID %s supplied; updating instead of creating duplicate", existing_deal_id)
            return await self.update_deal(existing_deal_id, properties)

        deal_props = dict(properties)
        if "pipeline" not in deal_props:
            deal_props["pipeline"] = DEFAULT_PIPELINE

        payload: Dict[str, Any] = {"properties": deal_props}
        if associations:
            payload["associations"] = associations

        try:
            resp = await self.client.post("/crm/v3/objects/deals", json_data=payload)
            created = resp.json()
            logger.info("Created new HubSpot deal %s", created.get("id"))
            return created
        except Exception as exc:
            logger.warning("Error creating HubSpot deal: %s", exc)
            return None

    async def update_deal_stage(
        self,
        deal_id: str,
        stage: str,
        amount: Optional[Union[int, float, Decimal, str]] = None,
        close_date: Optional[Union[datetime, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update dealstage and optional amount / closedate on an existing deal.
        """
        if not self.is_configured or not deal_id:
            return None

        props: Dict[str, Any] = {"dealstage": stage}
        if amount is not None:
            props["amount"] = self.format_amount(amount)
        if close_date is not None:
            props["closedate"] = self.format_close_date(close_date)

        return await self.update_deal(deal_id, props)
