"""Consistent normalization utilities for duplicate prevention across CRM, leads, and integrations."""
from __future__ import annotations

import re
from typing import Optional


def normalize_email(email: Optional[str]) -> Optional[str]:
    """
    Safely normalize an email address:
    - Strip leading and trailing whitespace
    - Case-fold to lowercase
    - Returns None if input is empty or None
    """
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned if cleaned else None


def normalize_domain(domain: Optional[str]) -> Optional[str]:
    """
    Safely normalize a company domain / URL:
    - Strip leading and trailing whitespace
    - Case-fold to lowercase
    - Safely remove scheme (http://, https://)
    - Safely remove leading www.
    - Remove URL paths, query parameters, and fragments
    - Remove trailing port if present
    - Returns None if input is empty or None
    """
    if not domain:
        return None
    d = domain.strip().lower()
    # Strip URL schemes
    d = re.sub(r"^https?://", "", d)
    # Strip www prefix
    d = re.sub(r"^www\.", "", d)
    # Strip path, query parameters, and fragments
    d = d.split("/")[0].split("?")[0].split("#")[0].strip()
    # Strip port if present
    d = d.split(":")[0].strip()
    return d if d else None
