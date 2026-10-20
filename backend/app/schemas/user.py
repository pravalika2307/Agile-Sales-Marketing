"""User and Organization Pydantic response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class OrganizationResponse(BaseModel):
    """Public organization details."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    billing_status: str
    created_at: datetime


class UserResponse(BaseModel):
    """Public user representation (never exposes password/hash)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    role: str
    access_level: str = "both"
    is_active: bool
    created_at: datetime
