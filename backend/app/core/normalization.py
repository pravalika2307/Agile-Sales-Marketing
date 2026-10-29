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


def normalize_linkedin_profile_url(url: Optional[str]) -> Optional[str]:
    """
    Validate and normalize a LinkedIn personal profile URL.
    - Strips leading/trailing whitespace
    - Prepends https:// if scheme is missing
    - Validates host is linkedin.com or *.linkedin.com
    - Validates path matches /in/<username> or /[locale]/in/<username>
    - Strips query parameters, hashes, and trailing slashes
    - Returns normalized standard format: 'https://www.linkedin.com/in/<username>'
    - If url is empty or None, returns None.
    - Raises ValueError if URL is malformed, not LinkedIn, or not an individual personal profile.
    """
    if not url or not url.strip():
        return None
    raw = url.strip()
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = "https://" + raw

    from urllib.parse import urlparse
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower().split(":")[0]

    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        raise ValueError(
            f"Invalid LinkedIn profile URL '{url}'. Domain must be linkedin.com."
        )

    path = parsed.path.strip().rstrip("/")

    match = re.match(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?in/([a-zA-Z0-9_\-\.%]+)$", path, re.IGNORECASE)
    if not match:
        if "/company/" in path.lower() or "/school/" in path.lower():
            raise ValueError(
                f"Invalid LinkedIn profile URL '{url}'. Expected an individual member profile (/in/username), but received an organization or school page."
            )
        raise ValueError(
            f"Invalid LinkedIn profile URL '{url}'. Must be a personal profile URL in the format 'https://www.linkedin.com/in/<username>'."
        )

    vanity_slug = match.group(1)
    return f"https://www.linkedin.com/in/{vanity_slug}"

