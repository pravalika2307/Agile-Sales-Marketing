"""Mock lead generation provider delivering deterministic synthetic B2B prospects."""
from __future__ import annotations

import hashlib
from typing import List, Optional

from app.services.lead_generation.base import (
    GeneratedLead,
    LeadGenerationProvider,
    LeadGenerationResult,
    LeadSearchCriteria,
)

# Deterministic pools for synthetic generation
FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Pat", "Robin",
    "Casey", "Jamie", "Riley", "Cameron", "Avery", "Kendall", "Reese"
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
    "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin"
]
COMPANY_PREFIXES = [
    "Apex", "Beacon", "Crest", "Dynasty", "Elevate", "Frontier", "Genesis",
    "Horizon", "Infiniti", "Kinetics", "Luminary", "Matrix", "Nexus", "Omni",
    "Pinnacle", "Quantum", "Radiant", "Strata", "Titan", "Vertex"
]
COMPANY_SUFFIXES = [
    "Technologies", "Solutions", "Systems", "Software", "Dynamics", "Labs",
    "Partners", "Digital", "Cloud", "Analytics"
]
DEFAULT_INDUSTRIES = ["Software", "Financial Services", "Healthcare", "Manufacturing", "E-Commerce"]
DEFAULT_COUNTRIES = ["United States", "Canada", "United Kingdom", "Germany", "Australia"]
DEFAULT_CITIES = ["San Francisco", "New York", "Austin", "London", "Toronto", "Berlin"]
DEFAULT_TITLES = ["VP of Sales", "Director of Growth", "Chief Technology Officer", "Head of Marketing", "Sales Director"]


class MockLeadGenerationProvider(LeadGenerationProvider):
    """
    Offline deterministic lead generation provider for testing and local development.
    Guarantees reproducible synthetic prospects without any network or external service calls.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    def search(
        self,
        criteria: LeadSearchCriteria,
        limit: int = 10,
    ) -> LeadGenerationResult:
        leads: List[GeneratedLead] = []

        # Build seed from criteria to ensure deterministic generation
        seed_raw = (
            f"{criteria.industries}_{criteria.countries}_{criteria.cities}_"
            f"{criteria.job_titles}_{criteria.company_size_min}_{criteria.company_size_max}"
        )
        base_seed = int(hashlib.sha256(seed_raw.encode("utf-8")).hexdigest()[:8], 16)

        for i in range(limit):
            item_seed = (base_seed + i * 31) % 1000000

            # Industry
            if criteria.industries and len(criteria.industries) > 0:
                industry = criteria.industries[i % len(criteria.industries)]
            else:
                industry = DEFAULT_INDUSTRIES[i % len(DEFAULT_INDUSTRIES)]

            # Country
            if criteria.countries and len(criteria.countries) > 0:
                country = criteria.countries[i % len(criteria.countries)]
            else:
                country = DEFAULT_COUNTRIES[i % len(DEFAULT_COUNTRIES)]

            # City
            if criteria.cities and len(criteria.cities) > 0:
                city = criteria.cities[i % len(criteria.cities)]
            else:
                city = DEFAULT_CITIES[i % len(DEFAULT_CITIES)]

            # Job Title
            if criteria.job_titles and len(criteria.job_titles) > 0:
                job_title = criteria.job_titles[i % len(criteria.job_titles)]
            else:
                job_title = DEFAULT_TITLES[i % len(DEFAULT_TITLES)]

            # Company Size Range
            if criteria.company_size_min is not None and criteria.company_size_max is not None:
                size_range = f"{criteria.company_size_min}-{criteria.company_size_max}"
            elif criteria.company_size_min is not None:
                size_range = f"{criteria.company_size_min}+"
            elif criteria.company_size_max is not None:
                size_range = f"1-{criteria.company_size_max}"
            else:
                size_range = "50-200"

            # Deterministic company name & domain
            prefix = COMPANY_PREFIXES[(item_seed + i) % len(COMPANY_PREFIXES)]
            suffix = COMPANY_SUFFIXES[(item_seed // 7 + i) % len(COMPANY_SUFFIXES)]
            company_name = f"{prefix} {suffix}"
            domain_slug = f"{prefix.lower()}{suffix.lower()[:4]}"
            domain = f"{domain_slug}.com"

            # If specific domains were requested in criteria, prioritize them
            if criteria.company_domains and i < len(criteria.company_domains):
                domain = criteria.company_domains[i]
                company_name = domain.split(".")[0].capitalize() + " Corp"

            # Contact
            first_name = FIRST_NAMES[(item_seed // 3 + i) % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(item_seed // 5 + i) % len(LAST_NAMES)]
            email = f"{first_name.lower()}.{last_name.lower()}@{domain}"
            phone = f"+1-555-{100 + (item_seed % 800):03d}-{1000 + (i * 123) % 9000:04d}"

            # Deterministic external ID
            ext_hash = hashlib.sha256(f"{domain}_{email}_{i}".encode("utf-8")).hexdigest()[:12]
            source_external_id = f"mock-{ext_hash}"

            leads.append(
                GeneratedLead(
                    source=self.provider_name,
                    source_external_id=source_external_id,
                    company_name=company_name,
                    company_domain=domain,
                    industry=industry,
                    employee_count_range=size_range,
                    city=city,
                    country=country,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=phone,
                    job_title=job_title,
                    metadata={"synthetic": True, "seed_index": i},
                )
            )

        return LeadGenerationResult(
            leads=leads,
            total_found=len(leads),
            source_name=self.provider_name,
        )
