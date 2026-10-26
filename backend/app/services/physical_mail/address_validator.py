"""Postal address validation and normalization engine for physical mail dispatches."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Standard USPS 2-letter state abbreviations (50 states + DC + US territories)
USPS_VALID_STATES = {
    # 50 States
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    # Federal District & Territories
    "DC", "PR", "VI", "GU", "AS", "MP",
}

ZIP_REGEX = re.compile(r"^\d{5}(-\d{4})?$")


@dataclass
class AddressValidationResult:
    """Outcome of validating a single recipient's postal address."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    cleaned_address: Optional[Dict[str, str]] = None


def validate_usps_address(
    address_1: Optional[str],
    city: Optional[str],
    state: Optional[str],
    postal_code: Optional[str],
    address_2: Optional[str] = None,
    country: Optional[str] = "US",
    full_name: Optional[str] = None,
    company: Optional[str] = None,
) -> AddressValidationResult:
    """
    Validates domestic US address data against USPS and Poplar pre-flight constraints.
    Checks:
    - Addressee identity (full_name, company, or individual name must be present)
    - Primary street address non-empty
    - City non-empty
    - State is valid 2-letter USPS uppercase code
    - Postal code matches 5-digit or 9-digit ZIP+4 format
    - Country is US/USA
    """
    errors: List[str] = []

    # 1. Addressee identity check
    clean_name = (full_name or "").strip()
    clean_company = (company or "").strip()
    if not clean_name and not clean_company:
        errors.append("Recipient missing addressee name (full_name or company required).")

    # 2. Street address
    clean_addr1 = (address_1 or "").strip()
    if not clean_addr1:
        errors.append("Missing primary street address (address_1).")
    elif len(clean_addr1) < 3:
        errors.append(f"Street address '{clean_addr1}' is too short to be valid.")

    clean_addr2 = (address_2 or "").strip() or None

    # 3. City
    clean_city = (city or "").strip()
    if not clean_city:
        errors.append("Missing city.")

    # 4. State abbreviation
    clean_state = (state or "").strip().upper()
    if not clean_state:
        errors.append("Missing state abbreviation.")
    elif clean_state not in USPS_VALID_STATES:
        errors.append(f"Invalid state abbreviation '{clean_state}'. Must be standard 2-letter USPS code.")

    # 5. Postal code / ZIP
    raw_zip = (postal_code or "").strip()
    # Normalize common 9-digit unhyphenated ZIPs (123456789 -> 12345-6789)
    if len(raw_zip) == 9 and raw_zip.isdigit():
        raw_zip = f"{raw_zip[:5]}-{raw_zip[5:]}"

    if not raw_zip:
        errors.append("Missing postal code (ZIP).")
    elif not ZIP_REGEX.match(raw_zip):
        errors.append(f"Invalid postal code format '{raw_zip}'. Must be 5-digit (e.g. 78701) or 9-digit ZIP+4.")

    # 6. Country check
    clean_country = (country or "US").strip().upper()
    if clean_country not in ("US", "USA", "UNITED STATES"):
        errors.append(f"Unsupported country '{country}'. Poplar direct mail requires domestic US destinations.")

    if errors:
        return AddressValidationResult(is_valid=False, errors=errors)

    cleaned = {
        "address_1": clean_addr1,
        "address_2": clean_addr2 or "",
        "city": clean_city,
        "state": clean_state,
        "postal_code": raw_zip,
        "country": "US",
        "full_name": clean_name,
        "company": clean_company,
    }
    return AddressValidationResult(is_valid=True, cleaned_address=cleaned)
