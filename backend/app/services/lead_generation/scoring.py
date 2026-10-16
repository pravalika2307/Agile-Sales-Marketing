"""Deterministic lead scoring and temperature classification (Step 11)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from app.models.icp import IdealCustomerProfile
from app.services.lead_generation.base import GeneratedLead

# Temperature Threshold Constants
TEMP_COLD_MAX = 39
TEMP_WARM_MAX = 69
TEMP_HOT_MIN = 70

# Scoring Weight Constants
SCORE_INDUSTRY_MATCH = 20
SCORE_COMPANY_SIZE_MATCH = 15
SCORE_COUNTRY_MATCH = 15
SCORE_CITY_MATCH = 10
SCORE_JOB_TITLE_MATCH = 15
SCORE_SENIORITY_MATCH = 10
SCORE_TECH_KEYWORD_MATCH = 10
SCORE_DOMAIN_EXISTS = 5
MAX_LEAD_SCORE = 100


def calculate_lead_temperature(score: int) -> str:
    """Categorize lead temperature deterministically based on score thresholds."""
    if score >= TEMP_HOT_MIN:
        return "hot"
    if score > TEMP_COLD_MAX:
        return "warm"
    return "cold"


def _string_matches_list(value: Optional[str], target_list: Optional[List[str]]) -> bool:
    """Case-insensitive containment check."""
    if not value or not target_list:
        return False
    val_norm = value.strip().lower()
    for item in target_list:
        if isinstance(item, str):
            item_norm = item.strip().lower()
            if item_norm == val_norm or item_norm in val_norm or val_norm in item_norm:
                return True
    return False


def _parse_size_range(size_range_str: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse string size range like '50-200' or '50+' into (min, max)."""
    if not size_range_str:
        return None
    cleaned = size_range_str.replace(",", "").strip()
    if "-" in cleaned:
        parts = cleaned.split("-")
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None
    elif "+" in cleaned:
        try:
            return int(cleaned.replace("+", "")), 1_000_000
        except ValueError:
            return None
    return None


def calculate_lead_score(
    lead: GeneratedLead,
    icp: Optional[IdealCustomerProfile],
) -> Tuple[int, str, str]:
    """
    Calculate deterministic score (0-100), temperature, and explanation.

    Returns:
        (lead_score, lead_temperature, qualification_reason)
    """
    score = 0
    reasons: List[str] = []

    if icp is None:
        # Default baseline if no ICP is attached
        if lead.company_domain:
            score += SCORE_DOMAIN_EXISTS
            reasons.append("Company domain provided")
        score = min(score, MAX_LEAD_SCORE)
        temp = calculate_lead_temperature(score)
        reason_str = "; ".join(reasons) if reasons else "No criteria matched"
        return score, temp, reason_str

    # 1. Industry match (+20)
    if icp.industries and _string_matches_list(lead.industry, icp.industries):
        score += SCORE_INDUSTRY_MATCH
        reasons.append(f"Industry matched ICP ({lead.industry})")

    # 2. Company size match (+15)
    if icp.company_size_min is not None or icp.company_size_max is not None:
        size_bounds = _parse_size_range(lead.employee_count_range)
        if size_bounds:
            lead_min, lead_max = size_bounds
            matches = True
            if icp.company_size_min is not None and lead_max < icp.company_size_min:
                matches = False
            if icp.company_size_max is not None and lead_min > icp.company_size_max:
                matches = False
            if matches:
                score += SCORE_COMPANY_SIZE_MATCH
                reasons.append("Company size within ICP range")
        else:
            # If no range on lead, neutral
            pass

    # 3. Country match (+15)
    if icp.countries and _string_matches_list(lead.country, icp.countries):
        score += SCORE_COUNTRY_MATCH
        reasons.append(f"Country matched ICP ({lead.country})")

    # 4. City match (+10)
    if icp.cities and _string_matches_list(lead.city, icp.cities):
        score += SCORE_CITY_MATCH
        reasons.append(f"City matched ICP ({lead.city})")

    # 5. Job title match (+15)
    if icp.job_titles and _string_matches_list(lead.job_title, icp.job_titles):
        score += SCORE_JOB_TITLE_MATCH
        reasons.append(f"Job title matched ICP persona ({lead.job_title})")

    # 6. Seniority match (+10)
    if icp.seniority_levels and _string_matches_list(lead.job_title, icp.seniority_levels):
        score += SCORE_SENIORITY_MATCH
        reasons.append("Seniority level matched ICP")

    # 7. Technology or Keyword match (+10)
    tech_matched = False
    if icp.technologies:
        # Check against metadata or industry
        for tech in icp.technologies:
            if tech.lower() in (lead.company_name.lower() + " " + (lead.industry or "").lower()):
                tech_matched = True
                break
    if not tech_matched and icp.keywords:
        for kw in icp.keywords:
            if kw.lower() in (lead.company_name.lower() + " " + (lead.job_title or "").lower()):
                tech_matched = True
                break
    if tech_matched:
        score += SCORE_TECH_KEYWORD_MATCH
        reasons.append("Technology/Keywords matched ICP")

    # 8. Domain provided (+5)
    if lead.company_domain:
        score += SCORE_DOMAIN_EXISTS
        reasons.append("Company domain verified")

    # Bound to [0, 100]
    final_score = min(max(score, 0), MAX_LEAD_SCORE)
    temperature = calculate_lead_temperature(final_score)
    reason_str = "; ".join(reasons) if reasons else "No criteria matched"

    return final_score, temperature, reason_str
