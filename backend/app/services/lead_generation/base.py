"""Base interfaces and data classes for lead generation providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LeadSearchCriteria:
    """Criteria passed to a lead generation provider derived from an ICP."""
    industries: Optional[List[str]] = None
    company_size_min: Optional[int] = None
    company_size_max: Optional[int] = None
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    company_domains: Optional[List[str]] = None
    job_titles: Optional[List[str]] = None
    seniority_levels: Optional[List[str]] = None
    departments: Optional[List[str]] = None
    technologies: Optional[List[str]] = None
    keywords: Optional[List[str]] = None


@dataclass
class GeneratedLead:
    """Standardized lead prospect payload produced by a lead provider."""
    source: str
    source_external_id: Optional[str]
    company_name: str
    company_domain: Optional[str] = None
    industry: Optional[str] = None
    employee_count_range: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class LeadGenerationResult:
    """Result of a lead generation search execution."""
    leads: List[GeneratedLead]
    total_found: int
    source_name: str


class LeadGenerationProvider(ABC):
    """Abstract interface for lead generation providers (mock, external DB, etc.)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the lead generation provider."""
        pass

    @abstractmethod
    def search(
        self,
        criteria: LeadSearchCriteria,
        limit: int = 10,
    ) -> LeadGenerationResult:
        """
        Execute a prospect search based on criteria.
        Must NOT perform external scraping or network calls when running mock implementations.
        """
        pass
