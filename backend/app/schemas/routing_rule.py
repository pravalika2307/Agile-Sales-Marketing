"""Pydantic schemas for Lead Routing Rules (Phase 4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RoutingRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=1000)
    is_active: bool = True

    # Conditions
    industries: Optional[List[str]] = None
    company_size_min: Optional[int] = Field(None, ge=0)
    company_size_max: Optional[int] = Field(None, ge=0)
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    min_score: Optional[int] = Field(None, ge=0, le=100)
    max_score: Optional[int] = Field(None, ge=0, le=100)
    qualification_statuses: Optional[List[str]] = None

    # Target
    assigned_to_user_id: Optional[uuid.UUID] = None
    assigned_team: Optional[str] = Field(None, max_length=100)


class RoutingRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=1000)
    is_active: Optional[bool] = None

    industries: Optional[List[str]] = None
    company_size_min: Optional[int] = Field(None, ge=0)
    company_size_max: Optional[int] = Field(None, ge=0)
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    min_score: Optional[int] = Field(None, ge=0, le=100)
    max_score: Optional[int] = Field(None, ge=0, le=100)
    qualification_statuses: Optional[List[str]] = None

    assigned_to_user_id: Optional[uuid.UUID] = None
    assigned_team: Optional[str] = Field(None, max_length=100)


class RoutingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: Optional[str] = None
    priority: int
    is_active: bool

    industries: Optional[List[str]] = None
    company_size_min: Optional[int] = None
    company_size_max: Optional[int] = None
    countries: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    qualification_statuses: Optional[List[str]] = None

    assigned_to_user_id: Optional[uuid.UUID] = None
    assigned_team: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_email: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class LeadRouteRequest(BaseModel):
    dry_run: bool = False
    rule_id: Optional[uuid.UUID] = None
    force_reroute: bool = False


class LeadRouteResult(BaseModel):
    lead_id: uuid.UUID
    is_routed: bool
    matched_rule_id: Optional[uuid.UUID] = None
    matched_rule_name: Optional[str] = None
    assigned_to_user_id: Optional[uuid.UUID] = None
    assignee_name: Optional[str] = None
    assigned_team: Optional[str] = None
    routed_at: Optional[datetime] = None
    explanation: str


class LeadBatchRouteRequest(BaseModel):
    lead_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)
    dry_run: bool = False
    force_reroute: bool = False


class LeadBatchRouteResult(BaseModel):
    total_evaluated: int
    routed_count: int
    unassigned_count: int
    already_assigned_count: int
    results: List[LeadRouteResult]
