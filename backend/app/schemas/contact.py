"""Contact Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.crm import ALLOWED_LEAD_STATUSES
from app.schemas.company import CompanyResponse


class ContactCreate(BaseModel):
    """Payload to create a new Contact prospect."""
    email: EmailStr = Field(..., description="Prospect email address")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Last name")
    company_id: Optional[uuid.UUID] = Field(None, description="Optional associated Company ID")
    phone: Optional[str] = Field(None, max_length=50, description="Phone number")
    job_title: Optional[str] = Field(None, max_length=150, description="Job title")
    lead_status: Optional[str] = Field("new", description="Lead status (default: 'new')")

    @field_validator("lead_status")
    @classmethod
    def validate_lead_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_LEAD_STATUSES:
                raise ValueError(
                    f"Invalid lead_status '{v}'. Allowed values: {sorted(list(ALLOWED_LEAD_STATUSES))}"
                )
            return clean
        return "new"


class ContactUpdate(BaseModel):
    """Payload to partially update an existing Contact."""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    company_id: Optional[uuid.UUID] = None
    phone: Optional[str] = Field(None, max_length=50)
    job_title: Optional[str] = Field(None, max_length=150)
    lead_status: Optional[str] = None

    @field_validator("lead_status")
    @classmethod
    def validate_lead_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_LEAD_STATUSES:
                raise ValueError(
                    f"Invalid lead_status '{v}'. Allowed values: {sorted(list(ALLOWED_LEAD_STATUSES))}"
                )
            return clean
        return v


class ContactResponse(BaseModel):
    """Contact public representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    company_id: Optional[uuid.UUID]
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    job_title: Optional[str]
    lead_status: str
    created_at: datetime
    updated_at: datetime
    company: Optional[CompanyResponse] = None
