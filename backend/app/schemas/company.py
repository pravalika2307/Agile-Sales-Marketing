"""Company Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    """Payload to create a new Company account."""
    name: str = Field(..., min_length=1, max_length=255, description="Company name")
    domain: Optional[str] = Field(None, max_length=255, description="Company website domain (e.g. acme.com)")
    industry: Optional[str] = Field(None, max_length=255, description="Industry sector")
    employee_count_range: Optional[str] = Field(None, max_length=100, description="Headcount range (e.g. 50-200)")
    city: Optional[str] = Field(None, max_length=100, description="City location")
    country: Optional[str] = Field(None, max_length=100, description="Country location")


class CompanyUpdate(BaseModel):
    """Payload to partially update an existing Company."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=255)
    employee_count_range: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)


class CompanyResponse(BaseModel):
    """Company public representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    domain: Optional[str]
    industry: Optional[str]
    employee_count_range: Optional[str]
    city: Optional[str]
    country: Optional[str]
    created_at: datetime
    updated_at: datetime
