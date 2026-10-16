"""Routing rules API endpoints (Phase 4)."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.routing_rule import (
    RoutingRuleCreate,
    RoutingRuleResponse,
    RoutingRuleUpdate,
)
from app.services.lead_qualification.routing_service import (
    create_routing_rule,
    delete_routing_rule,
    get_routing_rule,
    list_routing_rules,
    update_routing_rule,
)

router = APIRouter(prefix="/routing-rules", tags=["Lead Routing Rules"])


@router.get(
    "",
    response_model=List[RoutingRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="List routing rules",
    description="List all lead routing rules for the current organization ordered by priority.",
)
async def get_all_routing_rules(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[RoutingRuleResponse]:
    return list_routing_rules(db=db, organization_id=current_org.id)


@router.post(
    "",
    response_model=RoutingRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create routing rule",
    description="Create a new lead routing rule scoped to authenticated organization.",
)
async def create_new_routing_rule(
    payload: RoutingRuleCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> RoutingRuleResponse:
    return create_routing_rule(db=db, current_org=current_org, payload=payload)


@router.get(
    "/{rule_id}",
    response_model=RoutingRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single routing rule",
    description="Retrieve a single routing rule by ID scoped to current organization.",
)
async def get_single_routing_rule(
    rule_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> RoutingRuleResponse:
    return get_routing_rule(db=db, organization_id=current_org.id, rule_id=rule_id)


@router.patch(
    "/{rule_id}",
    response_model=RoutingRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update routing rule",
    description="Update an existing routing rule scoped to authenticated organization.",
)
async def update_existing_routing_rule(
    rule_id: uuid.UUID,
    payload: RoutingRuleUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> RoutingRuleResponse:
    return update_routing_rule(db=db, current_org=current_org, rule_id=rule_id, payload=payload)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete routing rule",
    description="Delete a routing rule scoped to authenticated organization.",
)
async def delete_existing_routing_rule(
    rule_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> dict:
    success = delete_routing_rule(db=db, current_org=current_org, rule_id=rule_id)
    return {"ok": success, "deleted_id": str(rule_id)}
