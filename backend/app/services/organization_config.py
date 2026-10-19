"""Organization configuration service managing tenant-specific settings and meeting booking destinations."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant import Organization

logger = logging.getLogger(__name__)

# Confirmed Agile Receivables Cal.com booking destination
AGILE_RECEIVABLES_BOOKING_URL = "https://cal.com/agilereceivables/30min"

# Known slugs, names, and IDs for Agile Receivables and Agile Sales & Marketing tenant
AGILE_RECEIVABLES_IDENTIFIERS = {
    # Agile Receivables identifiers
    "agile-receivables",
    "agile-receivables-org",
    "agile receivables",
    "agile receivables org",
    "3de43e6b-6cc0-4391-a061-2faba481bcb8",
    # Agile Sales & Marketing tenant identifiers
    "agile-sales-marketing",
    "agile-sales-marketing-org",
    "agile sales & marketing",
    "agile sales & marketing org",
    "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
}

# In-memory runtime override registry for dynamic tenant configurations and testing
_RUNTIME_BOOKING_URL_REGISTRY: Dict[str, str] = {}


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class OrganizationConfigError(Exception):
    """Base exception for organization configuration errors."""
    pass


class MissingBookingUrlError(OrganizationConfigError):
    """Raised when an organization has no configured meeting-booking URL."""
    pass


# ── Registry Management (for testing and runtime config) ───────────────────────

def register_organization_booking_url(identifier: Union[str, uuid.UUID], url: str) -> None:
    """Register or override a booking URL for an organization slug or ID."""
    key = str(identifier).strip().lower()
    _RUNTIME_BOOKING_URL_REGISTRY[key] = url.strip()


def clear_organization_booking_registry() -> None:
    """Clear all dynamic runtime booking URL overrides."""
    _RUNTIME_BOOKING_URL_REGISTRY.clear()


# ── Booking URL Resolution ────────────────────────────────────────────────────

def get_organization_booking_url(
    db: Optional[Session],
    org: Union[Organization, uuid.UUID, str],
) -> Optional[str]:
    """
    Resolves the meeting-booking URL strictly for the specified organization.

    Resolution hierarchy:
    1. Runtime in-memory registry overrides (keyed by ID or slug).
    2. Model attributes on Organization or BusinessProfile (if future schema adds it).
    3. Application settings `ORGANIZATION_BOOKING_URLS` mapping (by slug, ID, or name).
    4. Built-in mapping for Agile Receivables (by confirmed slug, ID, or name).

    TENANT ISOLATION GUARANTEE:
    - If the organization is NOT Agile Receivables and has no configured URL, this
      function strictly returns None.
    - It NEVER falls back to Agile Receivables' booking URL for other tenants.
    """
    org_instance: Optional[Organization] = None
    org_id_str: Optional[str] = None
    org_slug: Optional[str] = None
    org_name: Optional[str] = None

    if isinstance(org, Organization):
        org_instance = org
        org_id_str = str(org.id)
        org_slug = (org.slug or "").strip().lower()
        org_name = (org.name or "").strip().lower()
    elif isinstance(org, uuid.UUID):
        org_id_str = str(org)
        if db is not None:
            org_instance = db.query(Organization).filter(Organization.id == org).first()
            if org_instance:
                org_slug = (org_instance.slug or "").strip().lower()
                org_name = (org_instance.name or "").strip().lower()
    elif isinstance(org, str):
        # Could be UUID string or slug
        cleaned = org.strip().lower()
        try:
            parsed_uuid = uuid.UUID(cleaned)
            org_id_str = str(parsed_uuid)
            if db is not None:
                org_instance = db.query(Organization).filter(Organization.id == parsed_uuid).first()
                if org_instance:
                    org_slug = (org_instance.slug or "").strip().lower()
                    org_name = (org_instance.name or "").strip().lower()
        except ValueError:
            org_slug = cleaned
            if db is not None:
                org_instance = db.query(Organization).filter(Organization.slug == org_slug).first()
                if org_instance:
                    org_id_str = str(org_instance.id)
                    org_name = (org_instance.name or "").strip().lower()

    # 1. Check runtime registry
    for candidate in [org_id_str, org_slug, org_name]:
        if candidate and candidate in _RUNTIME_BOOKING_URL_REGISTRY:
            return _RUNTIME_BOOKING_URL_REGISTRY[candidate]

    # 2. Check future model column on Organization or BusinessProfile if present
    if org_instance is not None:
        if hasattr(org_instance, "booking_url") and getattr(org_instance, "booking_url"):
            return str(getattr(org_instance, "booking_url")).strip()
        bp = getattr(org_instance, "business_profile", None)
        if bp is not None and hasattr(bp, "booking_url") and getattr(bp, "booking_url"):
            return str(getattr(bp, "booking_url")).strip()

    # 3. Check Settings.ORGANIZATION_BOOKING_URLS dictionary
    configured_urls: Dict[str, str] = getattr(settings, "ORGANIZATION_BOOKING_URLS", {}) or {}
    for candidate in [org_id_str, org_slug, org_name]:
        if candidate and candidate in configured_urls:
            return configured_urls[candidate].strip()

    # 4. Check Agile Receivables built-in mapping
    is_agile_receivables = False
    for candidate in [org_id_str, org_slug, org_name]:
        if candidate and candidate in AGILE_RECEIVABLES_IDENTIFIERS:
            is_agile_receivables = True
            break

    if is_agile_receivables:
        return AGILE_RECEIVABLES_BOOKING_URL

    # Strict isolation: No fallback URL for other organizations
    return None


def require_organization_booking_url(
    db: Optional[Session],
    org: Union[Organization, uuid.UUID, str],
) -> str:
    """
    Returns the organization's meeting-booking URL, or raises MissingBookingUrlError.
    Used by campaign dispatch and outreach delivery guards to fail closed.
    """
    url = get_organization_booking_url(db, org)
    if not url:
        org_label = str(getattr(org, "name", None) or getattr(org, "slug", None) or org)
        raise MissingBookingUrlError(
            f"Organization '{org_label}' has no configured meeting-booking URL. "
            f"Every campaign email step requires a valid booking destination (canonical variable {{booking_link}})."
        )
    return url
