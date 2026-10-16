"""Pydantic schemas for reusable email templates and AI generation."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class EmailTemplateBase(BaseModel):
    """Base fields for an email template."""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: Optional[str] = Field(None, max_length=1000, description="Usage guidelines or notes")
    category: str = Field(default="outbound", max_length=50, description="Category (outbound, follow_up, nurture, referral, announcement)")
    subject_template: str = Field(..., min_length=1, description="Email subject template with optional {contact.*} variables")
    body_template: str = Field(..., min_length=1, description="Email body template with optional {contact.*} variables")
    is_active: bool = Field(default=True, description="Whether template is active for selection")


class EmailTemplateCreate(EmailTemplateBase):
    """Request payload to create a reusable email template."""
    pass


class EmailTemplateUpdate(BaseModel):
    """Request payload to update an existing email template."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    subject_template: Optional[str] = Field(None, min_length=1)
    body_template: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


class EmailTemplateResponse(EmailTemplateBase):
    """Full representation of a persisted email template."""
    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIEmailGenerateRequest(BaseModel):
    """Parameters for AI-assisted email generation."""
    campaign_name: Optional[str] = Field(None, description="Current campaign name for context")
    email_objective: str = Field(..., min_length=1, description="Purpose or goal of the email")
    target_audience: Optional[str] = Field(None, description="Target persona or industry")
    tone: Optional[str] = Field(default="professional", description="Desired tone: professional, consultative, casual, direct, urgent")
    call_to_action: Optional[str] = Field(None, description="Desired next step or CTA")


class AIEmailGenerateResponse(BaseModel):
    """AI-generated email subject and body result."""
    subject: str = Field(..., description="Generated email subject line")
    body: str = Field(..., description="Generated email body text")
    model_used: str = Field(..., description="Model identifier used for generation")
    ai_provider: str = Field(default="bedrock", description="AI provider used")
    is_mock: bool = Field(default=False, description="Whether generated via mock test mode")
