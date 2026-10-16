"""HubSpot Contacts Service.

Provides contact management operations against HubSpot CRM v3:
- search contact by email
- get contact by ID
- create contact
- update contact
- duplicate/conflict (409) resolution
- 404 recovery
- verified standard HubSpot properties
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .client import (
    HubSpotClient,
    HubSpotConflictError,
    HubSpotError,
    HubSpotNotFoundError,
)

logger = logging.getLogger(__name__)

# Standard verified HubSpot contact property keys
STANDARD_CONTACT_PROPERTIES = [
    "firstname",
    "lastname",
    "email",
    "phone",
    "company",
    "jobtitle",
    "hs_lead_status",
    "lifecyclestage",
    "city",
    "state",
    "country",
    "zip",
    "address",
    "message",
    "createdate",
    "lastmodifieddate",
]


class HubSpotContactService:
    """Service for interacting with HubSpot Contacts API."""

    def __init__(self, client: Optional[HubSpotClient] = None) -> None:
        self.client = client or HubSpotClient()

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    async def search_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Search HubSpot contacts by exact email match.
        POST /crm/v3/objects/contacts/search
        """
        if not self.is_configured or not email:
            return None

        clean_email = email.strip().lower()
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": clean_email,
                        }
                    ]
                }
            ],
            "properties": STANDARD_CONTACT_PROPERTIES,
            "limit": 1,
        }

        try:
            resp = await self.client.post("/crm/v3/objects/contacts/search", json_data=payload)
            data = resp.json()
            results = data.get("results", [])
            if results:
                contact = results[0]
                logger.info("Found existing HubSpot contact %s for email %s", contact.get("id"), clean_email)
                return contact
            return None
        except Exception as exc:
            logger.warning("Error searching HubSpot contact for email %s: %s", clean_email, exc)
            return None

    async def get_contact(
        self,
        contact_id: str,
        properties: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch contact by HubSpot contact ID.
        GET /crm/v3/objects/contacts/{contact_id}
        Returns None if contact does not exist (404).
        """
        if not self.is_configured or not contact_id:
            return None

        clean_id = str(contact_id).strip()
        props = properties or STANDARD_CONTACT_PROPERTIES
        params = {"properties": ",".join(props)}

        try:
            resp = await self.client.get(f"/crm/v3/objects/contacts/{clean_id}", params=params)
            return resp.json()
        except HubSpotNotFoundError:
            logger.info("HubSpot contact %s not found (404)", clean_id)
            return None
        except Exception as exc:
            logger.warning("Error fetching HubSpot contact %s: %s", clean_id, exc)
            return None

    async def update_contact(
        self,
        contact_id: str,
        properties: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing HubSpot contact.
        PATCH /crm/v3/objects/contacts/{contact_id}
        Returns None on 404 (allows caller to handle recovery).
        """
        if not self.is_configured or not contact_id:
            return None

        clean_id = str(contact_id).strip()
        payload = {"properties": properties}

        try:
            resp = await self.client.patch(f"/crm/v3/objects/contacts/{clean_id}", json_data=payload)
            updated = resp.json()
            logger.info("Successfully updated HubSpot contact %s", clean_id)
            return updated
        except HubSpotNotFoundError:
            logger.warning("HubSpot contact %s not found for update (404)", clean_id)
            return None
        except Exception as exc:
            logger.warning("Error updating HubSpot contact %s: %s", clean_id, exc)
            return None

    async def create_contact(
        self,
        properties: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new HubSpot contact.
        POST /crm/v3/objects/contacts

        Handles 409 Conflict gracefully:
        Extracts existing contact ID or performs email search fallback,
        then updates the existing contact with new properties.
        """
        if not self.is_configured:
            return None

        payload = {"properties": properties}
        email = properties.get("email")

        try:
            resp = await self.client.post("/crm/v3/objects/contacts", json_data=payload)
            created = resp.json()
            logger.info("Created new HubSpot contact %s", created.get("id"))
            return created

        except HubSpotConflictError as conflict:
            logger.info("HubSpot contact creation conflict (409) for email %s. Resolving duplicate...", email)
            # Try to extract existing contact ID from response body (standard HubSpot error string: "Existing ID: 12345")
            existing_id = None
            if conflict.response_text:
                match = re.search(r"Existing ID:\s*(\d+)", conflict.response_text)
                if match:
                    existing_id = match.group(1)

            # Fallback to email search if ID was not in error response
            if not existing_id and email:
                found = await self.search_contact_by_email(str(email))
                if found and "id" in found:
                    existing_id = str(found["id"])

            if existing_id:
                logger.info("Resolved conflicting contact ID %s. Updating record...", existing_id)
                return await self.update_contact(existing_id, properties)

            logger.warning("Could not extract existing contact ID from conflict response.")
            return None

        except Exception as exc:
            logger.warning("Error creating HubSpot contact: %s", exc)
            return None

    async def sync_contact(
        self,
        email: str,
        properties: Dict[str, Any],
        existing_contact_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        High-level sync flow with duplicate prevention and 404 recovery:
        1. If existing_contact_id is provided, try direct update.
        2. If that fails with 404 or no ID was provided, search by email.
        3. If found by email, update existing contact.
        4. If not found, create new contact (with automatic 409 conflict handling).
        """
        if not self.is_configured:
            return None

        clean_email = email.strip().lower() if email else ""
        props = dict(properties)
        if clean_email:
            props["email"] = clean_email

        # 1. Direct update if existing ID provided
        if existing_contact_id:
            updated = await self.update_contact(existing_contact_id, props)
            if updated:
                return updated
            logger.info("Contact %s not found on direct update (404); falling back to search", existing_contact_id)

        # 2. Search by email
        if clean_email:
            found = await self.search_contact_by_email(clean_email)
            if found and "id" in found:
                return await self.update_contact(str(found["id"]), props)

        # 3. Create new
        return await self.create_contact(props)
