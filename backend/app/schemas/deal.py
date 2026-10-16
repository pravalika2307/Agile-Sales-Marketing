"""Deal Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.crm import ALLOWED_DEAL_STATUSES
from app.schemas.company import CompanyResponse
from app.schemas.contact import ContactResponse
from app.schemas.pipeline import PipelineStageResponse


class DealCreate(BaseModel):
    """Payload to create a new Deal."""
    pipeline_stage_id: uuid.UUID = Field(..., description="Target pipeline stage ID")
    name: str = Field(..., min_length=1, max_length=255, description="Deal name")
    amount: Decimal = Field(default=Decimal("0.00"), ge=0, description="Deal monetary value (non-negative)")
    contact_id: Optional[uuid.UUID] = Field(None, description="Optional associated Contact ID")
    company_id: Optional[uuid.UUID] = Field(None, description="Optional associated Company ID")
    expected_close_date: Optional[date] = Field(None, description="Expected close date")
    status: Optional[str] = Field("open", description="Deal status: open, won, or lost")

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Deal name cannot be empty or whitespace only.")
        return clean

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> str:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_DEAL_STATUSES:
                raise ValueError(
                    f"Invalid status '{v}'. Allowed values: {sorted(list(ALLOWED_DEAL_STATUSES))}"
                )
            return clean
        return "open"


class DealUpdate(BaseModel):
    """Payload to partially update an existing Deal."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    amount: Optional[Decimal] = Field(None, ge=0)
    pipeline_stage_id: Optional[uuid.UUID] = None
    contact_id: Optional[uuid.UUID] = None
    company_id: Optional[uuid.UUID] = None
    expected_close_date: Optional[date] = None
    status: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Deal name cannot be empty or whitespace only.")
            return clean
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_DEAL_STATUSES:
                raise ValueError(
                    f"Invalid status '{v}'. Allowed values: {sorted(list(ALLOWED_DEAL_STATUSES))}"
                )
            return clean
        return v


class DealStageMove(BaseModel):
    """Payload to move a Deal to a new pipeline stage."""
    pipeline_stage_id: uuid.UUID = Field(..., description="Target pipeline stage ID")


class DealStatusUpdate(BaseModel):
    """Payload to update Deal status (open, won, lost)."""
    status: str = Field(..., description="New deal status: open, won, or lost")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_DEAL_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Allowed values: {sorted(list(ALLOWED_DEAL_STATUSES))}"
            )
        return clean


class DealResponse(BaseModel):
    """Deal public representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    pipeline_stage_id: uuid.UUID
    contact_id: Optional[uuid.UUID]
    company_id: Optional[uuid.UUID]
    name: str
    amount: Decimal
    expected_close_date: Optional[date]
    status: str
    created_at: datetime
    updated_at: datetime
    stage: Optional[PipelineStageResponse] = Field(None, validation_alias="pipeline_stage")
    contact: Optional[ContactResponse] = None
    company: Optional[CompanyResponse] = None
