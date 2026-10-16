"""Pydantic schemas for Ideal Customer Profile (ICP) management."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _clean_string_list(v: Optional[List[str]]) -> Optional[List[str]]:
    """Clean string list by trimming and removing empty strings."""
    if v is None:
        return None
    cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
    return cleaned if cleaned else None


class IdealCustomerProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Descriptive name of the ICP")
    description: Optional[str] = Field(None, description="Optional notes and persona context")

    # Firmographic criteria
    industries: Optional[List[str]] = Field(None, description="Target industry names")
    company_size_min: Optional[int] = Field(None, ge=0, description="Minimum employee headcount")
    company_size_max: Optional[int] = Field(None, ge=0, description="Maximum employee headcount")
    countries: Optional[List[str]] = Field(None, description="Target countries")
    cities: Optional[List[str]] = Field(None, description="Target cities")
    company_domains: Optional[List[str]] = Field(None, description="Target domains or competitor domains")

    # Persona criteria
    job_titles: Optional[List[str]] = Field(None, description="Target job titles or role keywords")
    seniority_levels: Optional[List[str]] = Field(None, description="Seniority levels (e.g. C-Level, VP, Director)")
    departments: Optional[List[str]] = Field(None, description="Target departments (e.g. Sales, Engineering)")

    # Additional criteria
    technologies: Optional[List[str]] = Field(None, description="Target tech stack keywords")
    keywords: Optional[List[str]] = Field(None, description="General qualification keywords")

    is_active: bool = Field(True, description="Whether this ICP is actively used for generation")

    @model_validator(mode="after")
    def validate_sizes_and_lists(self) -> IdealCustomerProfileBase:
        # Validate company sizes
        if self.company_size_min is not None and self.company_size_max is not None:
            if self.company_size_max < self.company_size_min:
                raise ValueError("company_size_max must be greater than or equal to company_size_min")

        # Clean string lists
        self.industries = _clean_string_list(self.industries)
        self.countries = _clean_string_list(self.countries)
        self.cities = _clean_string_list(self.cities)
        self.company_domains = _clean_string_list(self.company_domains)
        self.job_titles = _clean_string_list(self.job_titles)
        self.seniority_levels = _clean_string_list(self.seniority_levels)
        self.departments = _clean_string_list(self.departments)
        self.technologies = _clean_string_list(self.technologies)
        self.keywords = _clean_string_list(self.keywords)

        return self


class IdealCustomerProfileCreate(IdealCustomerProfileBase):
    pass


class IdealCustomerProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

    industries: Optional[List[str]] = None
    company_size_min: Optional[int] = Field(None, ge=0)
    company_size_max: Optional[int] = Field(None, ge=0)
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    company_domains: Optional[List[str]] = None

    job_titles: Optional[List[str]] = None
    seniority_levels: Optional[List[str]] = None
    departments: Optional[List[str]] = None

    technologies: Optional[List[str]] = None
    keywords: Optional[List[str]] = None

    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_sizes_and_lists(self) -> IdealCustomerProfileUpdate:
        if self.company_size_min is not None and self.company_size_max is not None:
            if self.company_size_max < self.company_size_min:
                raise ValueError("company_size_max must be greater than or equal to company_size_min")

        if self.industries is not None:
            self.industries = _clean_string_list(self.industries)
        if self.countries is not None:
            self.countries = _clean_string_list(self.countries)
        if self.cities is not None:
            self.cities = _clean_string_list(self.cities)
        if self.company_domains is not None:
            self.company_domains = _clean_string_list(self.company_domains)
        if self.job_titles is not None:
            self.job_titles = _clean_string_list(self.job_titles)
        if self.seniority_levels is not None:
            self.seniority_levels = _clean_string_list(self.seniority_levels)
        if self.departments is not None:
            self.departments = _clean_string_list(self.departments)
        if self.technologies is not None:
            self.technologies = _clean_string_list(self.technologies)
        if self.keywords is not None:
            self.keywords = _clean_string_list(self.keywords)

        return self


class IdealCustomerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: Optional[str] = None

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

    is_active: bool
    created_at: datetime
    updated_at: datetime


class IdealCustomerProfileListResponse(BaseModel):
    items: List[IdealCustomerProfileResponse]
    total: int
    page: int
    page_size: int
