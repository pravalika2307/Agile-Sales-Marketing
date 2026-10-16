"""CampaignStep Pydantic schemas for sequence step management."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.campaign_step import ALLOWED_STEP_TYPES


class CampaignStepCreate(BaseModel):
    """Payload to create a new step in a campaign sequence."""
    step_number: int = Field(..., ge=1, description="Sequence step order number (>= 1)")
    step_type: str = Field("email", description="Channel step type (only 'email' supported in Step 9)")
    subject_template: Optional[str] = Field(None, max_length=255, description="Email subject template")
    body_template: Optional[str] = Field(None, description="Email body content template")
    delay_days: int = Field(0, ge=0, description="Delay in days before step eligibility")
    delay_hours: int = Field(0, ge=0, lt=24, description="Delay in hours (0 to 23)")
    is_active: bool = Field(True, description="Whether this step is currently active")

    @field_validator("step_type")
    @classmethod
    def validate_step_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_STEP_TYPES:
            raise ValueError(
                f"Invalid step_type '{v}'. Allowed types: {sorted(list(ALLOWED_STEP_TYPES))}"
            )
        return clean


class CampaignStepUpdate(BaseModel):
    """Payload to partially update an existing campaign step."""
    subject_template: Optional[str] = Field(None, max_length=255)
    body_template: Optional[str] = None
    delay_days: Optional[int] = Field(None, ge=0)
    delay_hours: Optional[int] = Field(None, ge=0, lt=24)
    is_active: Optional[bool] = None


class CampaignStepResponse(BaseModel):
    """Safe public representation of a CampaignStep."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    campaign_id: uuid.UUID
    step_number: int
    step_type: str
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    delay_days: int
    delay_hours: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
