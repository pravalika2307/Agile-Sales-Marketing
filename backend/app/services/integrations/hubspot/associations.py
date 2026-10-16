"""HubSpot Associations Service.

Handles object associations in HubSpot CRM v3 (e.g. Contact <-> Deal),
completely separated from application business entities.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .client import HubSpotClient

logger = logging.getLogger(__name__)

# Standard HubSpot-defined association type ID for deal_to_contact
DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID = 3


class HubSpotAssociationService:
    """Service managing associations between HubSpot CRM objects."""

    def __init__(self, client: Optional[HubSpotClient] = None) -> None:
        self.client = client or HubSpotClient()

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    @staticmethod
    def build_deal_contact_association_payload(contact_id: str) -> Dict[str, Any]:
        """
        Build association schema snippet for embedding during Deal creation.
        """
        return {
            "to": {"id": str(contact_id).strip()},
            "types": [
                {
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": DEAL_TO_CONTACT_ASSOCIATION_TYPE_ID,
                }
            ],
        }

    async def associate_deal_to_contact(self, deal_id: str, contact_id: str) -> bool:
        """
        Associate an existing Deal with an existing Contact.
        PUT /crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact
        """
        if not self.is_configured or not deal_id or not contact_id:
            return False

        d_id = str(deal_id).strip()
        c_id = str(contact_id).strip()
        path = f"/crm/v3/objects/deals/{d_id}/associations/contacts/{c_id}/deal_to_contact"

        try:
            resp = await self.client.put(path, check_status=False)
            if resp.status_code in (200, 204):
                logger.info("Successfully associated Deal %s with Contact %s", d_id, c_id)
                return True
            else:
                logger.warning(
                    "Failed to associate Deal %s with Contact %s: HTTP %d - %s",
                    d_id,
                    c_id,
                    resp.status_code,
                    resp.text[:200],
                )
                return False
        except Exception as exc:
            logger.warning("Error associating Deal %s with Contact %s: %s", d_id, c_id, exc)
            return False

    async def remove_deal_to_contact_association(self, deal_id: str, contact_id: str) -> bool:
        """
        Remove association between a Deal and a Contact.
        DELETE /crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact
        """
        if not self.is_configured or not deal_id or not contact_id:
            return False

        d_id = str(deal_id).strip()
        c_id = str(contact_id).strip()
        path = f"/crm/v3/objects/deals/{d_id}/associations/contacts/{c_id}/deal_to_contact"

        try:
            resp = await self.client.delete(path, check_status=False)
            if resp.status_code in (200, 204):
                logger.info("Successfully removed association between Deal %s and Contact %s", d_id, c_id)
                return True
            else:
                logger.warning(
                    "Failed to remove association between Deal %s and Contact %s: HTTP %d",
                    d_id,
                    c_id,
                    resp.status_code,
                )
                return False
        except Exception as exc:
            logger.warning("Error removing association between Deal %s and Contact %s: %s", d_id, c_id, exc)
            return False
