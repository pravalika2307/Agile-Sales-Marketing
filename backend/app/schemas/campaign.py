"""Campaign and CampaignContact Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.campaign import (
    ALLOWED_CAMPAIGN_STATUSES,
    ALLOWED_CAMPAIGN_TYPES,
    ALLOWED_ENROLLMENT_STATUSES,
)
from app.schemas.contact import ContactResponse


class CampaignCreate(BaseModel):
    """Payload to create a new Campaign (starts in draft status)."""
    name: str = Field(..., min_length=1, max_length=255, description="Campaign name")
    type: str = Field("sales_outbound", description="Campaign type: sales_outbound, marketing_social, or hybrid")
    description: Optional[str] = Field(None, description="Optional campaign description")
    first_step_channel: Optional[str] = Field("email", description="Initial channel type for workflow: email, sms, or voice")
    schedule_settings: Optional[Dict[str, Any]] = Field(None, description="Optional scheduling configuration")
    workflow_config: Optional[Dict[str, Any]] = Field(None, description="Visual workflow builder configuration")

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Campaign name cannot be empty or whitespace only.")
        return clean

    @field_validator("first_step_channel")
    @classmethod
    def validate_first_step_channel(cls, v: Optional[str]) -> str:
        if v is None:
            return "email"
        clean = v.strip().lower()
        allowed = {"email", "sms", "voice"}
        if clean not in allowed:
            raise ValueError(
                f"Invalid first_step_channel '{v}'. Allowed channels: {sorted(list(allowed))}"
            )
        return clean

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_CAMPAIGN_TYPES:
            raise ValueError(
                f"Invalid campaign type '{v}'. Allowed types: {sorted(list(ALLOWED_CAMPAIGN_TYPES))}"
            )
        return clean


class CampaignUpdate(BaseModel):
    """Payload to partially update a Campaign."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[str] = None
    description: Optional[str] = None
    schedule_settings: Optional[Dict[str, Any]] = None
    workflow_config: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Campaign name cannot be empty or whitespace only.")
            return clean
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_CAMPAIGN_TYPES:
                raise ValueError(
                    f"Invalid campaign type '{v}'. Allowed types: {sorted(list(ALLOWED_CAMPAIGN_TYPES))}"
                )
            return clean
        return v


class CampaignResponse(BaseModel):
    """Campaign public representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    type: str
    status: str
    description: Optional[str] = None
    schedule_settings: Optional[Dict[str, Any]] = None
    workflow_config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    contacts_count: int = 0
    steps_count: int = 0


class CampaignContactResponse(BaseModel):
    """Campaign enrollment public representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    contact_id: uuid.UUID
    enrollment_status: str
    current_step: int
    enrolled_at: datetime
    updated_at: datetime
    contact: Optional[ContactResponse] = None


class CampaignEnrollmentRequest(BaseModel):
    """Payload to enroll a contact with optional initial status."""
    enrollment_status: Optional[str] = Field("queued", description="Initial enrollment status")

    @field_validator("enrollment_status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> str:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_ENROLLMENT_STATUSES:
                raise ValueError(
                    f"Invalid enrollment status '{v}'. Allowed values: {sorted(list(ALLOWED_ENROLLMENT_STATUSES))}"
                )
            return clean
        return "queued"


class BulkEnrollmentRequest(BaseModel):
    """Payload for bulk contact enrollment into a campaign."""
    contact_ids: List[uuid.UUID] = Field(..., min_length=1, description="List of Contact IDs to enroll")


class BulkEnrollmentResponse(BaseModel):
    """Response detailing outcomes of bulk enrollment."""
    enrolled: List[uuid.UUID] = Field(default_factory=list)
    already_enrolled: List[uuid.UUID] = Field(default_factory=list)
    rejected: List[uuid.UUID] = Field(default_factory=list)


class CampaignContactStatusUpdate(BaseModel):
    """Payload to update the enrollment status of an enrolled contact."""
    enrollment_status: str = Field(..., description="New enrollment status")

    @field_validator("enrollment_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_ENROLLMENT_STATUSES:
            raise ValueError(
                f"Invalid enrollment status '{v}'. Allowed values: {sorted(list(ALLOWED_ENROLLMENT_STATUSES))}"
            )
        return clean
