"""Pydantic schemas for B2B Lead / Prospect records and workflows."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


QualificationStatusType = Literal["new", "qualified", "disqualified", "reviewed"]
LeadTemperatureType = Literal["cold", "warm", "hot"]
LeadStatusType = Literal["new", "selected", "enrolled", "contacted", "replied", "converted", "rejected"]


class LeadCreate(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    job_title: Optional[str] = Field(None, max_length=255)
    company_name: str = Field(..., min_length=1, max_length=255)
    company_domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    employee_count_range: Optional[str] = Field(None, max_length=50)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    postal_code: Optional[str] = Field(None, max_length=20)
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=100)
    icp_id: Optional[uuid.UUID] = None
    lead_temperature: Optional[LeadTemperatureType] = None
    lead_score: Optional[int] = Field(None, ge=0, le=100)
    source: Optional[str] = Field("manual", max_length=100)
    qualification_status: Optional[QualificationStatusType] = None
    status: Optional[LeadStatusType] = None


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    icp_id: Optional[uuid.UUID] = None
    company_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None

    source: str
    source_external_id: Optional[str] = None

    # Company snapshot
    company_name: str
    company_domain: Optional[str] = None
    industry: Optional[str] = None
    employee_count_range: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    country: Optional[str] = None

    # Contact snapshot
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None

    # Qualification & Scoring
    qualification_status: str
    lead_temperature: Optional[str] = None
    lead_score: Optional[int] = None
    is_scored: bool = False
    qualification_reason: Optional[str] = None

    # Routing & Assignment
    assigned_to_user_id: Optional[uuid.UUID] = None
    assignee_name: Optional[str] = None
    routing_rule_id: Optional[uuid.UUID] = None
    routed_at: Optional[datetime] = None
    routing_notes: Optional[str] = None

    # Status & Timestamps
    status: str
    created_at: datetime
    updated_at: datetime

    def model_post_init(self, __context: object) -> None:
        if not self.is_scored:
            self.lead_score = None


class LeadListResponse(BaseModel):
    items: List[LeadResponse]
    total: int
    page: int
    page_size: int


class LeadBulkStatusUpdate(BaseModel):
    lead_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100, description="List of lead UUIDs to update")
    status: Optional[LeadStatusType] = None
    qualification_status: Optional[QualificationStatusType] = None


class LeadBulkStatusResponse(BaseModel):
    updated_count: int
    updated_ids: List[uuid.UUID]


class LeadQualificationUpdate(BaseModel):
    qualification_status: Optional[QualificationStatusType] = None
    lead_temperature: Optional[LeadTemperatureType] = None
    qualification_reason: Optional[str] = Field(None, max_length=1000)


class LeadSelectionRequest(BaseModel):
    lead_ids: List[uuid.UUID] = Field(..., min_length=1, description="List of lead UUIDs to select")


class LeadSelectionResponse(BaseModel):
    selected_count: int
    already_selected_count: int
    rejected_count: int
    selected_ids: List[uuid.UUID]


class LeadConversionResponse(BaseModel):
    lead_id: uuid.UUID
    company_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    company_created: bool
    contact_created: bool
    status: str


class LeadGenerationRequest(BaseModel):
    limit: int = Field(10, ge=1, le=100, description="Number of prospect leads to generate")


class LeadImportRow(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    job_title: Optional[str] = Field(None, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    postal_code: Optional[str] = Field(None, max_length=20)
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=100)


class LeadImportRequest(BaseModel):
    rows: List[LeadImportRow] = Field(..., max_length=500, description="List of rows to import")


class LeadImportResponse(BaseModel):
    imported_count: int
    skipped_duplicate_count: int
    failed_count: int
    imported_ids: List[uuid.UUID]
    errors: List[str]
