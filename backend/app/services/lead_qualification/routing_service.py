"""Lead routing rules management and automated lead assignment service (Phase 4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.routing_rule import LeadRoutingRule
from app.models.tenant import Organization, User
from app.schemas.routing_rule import (
    LeadBatchRouteResult,
    LeadRouteResult,
    RoutingRuleCreate,
    RoutingRuleResponse,
    RoutingRuleUpdate,
)
from app.services.lead_generation.scoring import _parse_size_range, _string_matches_list


# ── Routing Rule CRUD Operations ──────────────────────────────────────────────

def list_routing_rules(
    db: Session,
    organization_id: uuid.UUID,
) -> List[RoutingRuleResponse]:
    """Retrieve all routing rules for an organization ordered by priority."""
    rules = list(
        db.execute(
            select(LeadRoutingRule)
            .where(LeadRoutingRule.organization_id == organization_id)
            .order_by(LeadRoutingRule.priority.asc(), LeadRoutingRule.created_at.asc())
        ).scalars().all()
    )

    items: List[RoutingRuleResponse] = []
    for r in rules:
        user = None
        if r.assigned_to_user_id:
            user = db.execute(
                select(User).where(
                    User.id == r.assigned_to_user_id,
                    User.organization_id == organization_id,
                )
            ).scalar_one_or_none()

        resp = RoutingRuleResponse.model_validate(r)
        if user:
            resp.assignee_name = user.full_name
            resp.assignee_email = user.email
        items.append(resp)

    return items


def get_routing_rule(
    db: Session,
    organization_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> RoutingRuleResponse:
    """Retrieve a single routing rule by ID scoped to current organization."""
    rule = db.execute(
        select(LeadRoutingRule).where(
            LeadRoutingRule.id == rule_id,
            LeadRoutingRule.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )

    user = None
    if rule.assigned_to_user_id:
        user = db.execute(
            select(User).where(
                User.id == rule.assigned_to_user_id,
                User.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    resp = RoutingRuleResponse.model_validate(rule)
    if user:
        resp.assignee_name = user.full_name
        resp.assignee_email = user.email
    return resp


def create_routing_rule(
    db: Session,
    current_org: Organization,
    payload: RoutingRuleCreate,
) -> RoutingRuleResponse:
    """Create a new tenant-isolated routing rule."""
    # Verify assignee belongs to tenant if specified
    assignee_user: Optional[User] = None
    if payload.assigned_to_user_id:
        assignee_user = db.execute(
            select(User).where(
                User.id == payload.assigned_to_user_id,
                User.organization_id == current_org.id,
            )
        ).scalar_one_or_none()
        if not assignee_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignee user '{payload.assigned_to_user_id}' does not exist in this organization.",
            )

    rule = LeadRoutingRule(
        organization_id=current_org.id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        priority=payload.priority,
        is_active=payload.is_active,
        industries=payload.industries,
        company_size_min=payload.company_size_min,
        company_size_max=payload.company_size_max,
        countries=payload.countries,
        cities=payload.cities,
        min_score=payload.min_score,
        max_score=payload.max_score,
        qualification_statuses=payload.qualification_statuses,
        assigned_to_user_id=payload.assigned_to_user_id,
        assigned_team=payload.assigned_team.strip() if payload.assigned_team else None,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    resp = RoutingRuleResponse.model_validate(rule)
    if assignee_user:
        resp.assignee_name = assignee_user.full_name
        resp.assignee_email = assignee_user.email
    return resp


def update_routing_rule(
    db: Session,
    current_org: Organization,
    rule_id: uuid.UUID,
    payload: RoutingRuleUpdate,
) -> RoutingRuleResponse:
    """Update an existing routing rule."""
    rule = db.execute(
        select(LeadRoutingRule).where(
            LeadRoutingRule.id == rule_id,
            LeadRoutingRule.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )

    # Verify new assignee if updated
    if payload.assigned_to_user_id is not None:
        assignee = db.execute(
            select(User).where(
                User.id == payload.assigned_to_user_id,
                User.organization_id == current_org.id,
            )
        ).scalar_one_or_none()
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignee user '{payload.assigned_to_user_id}' not found in organization.",
            )

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(rule, k, v)

    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)

    assignee_user = None
    if rule.assigned_to_user_id:
        assignee_user = db.execute(
            select(User).where(User.id == rule.assigned_to_user_id)
        ).scalar_one_or_none()

    resp = RoutingRuleResponse.model_validate(rule)
    if assignee_user:
        resp.assignee_name = assignee_user.full_name
        resp.assignee_email = assignee_user.email
    return resp


def delete_routing_rule(
    db: Session,
    current_org: Organization,
    rule_id: uuid.UUID,
) -> bool:
    """Delete a routing rule with tenant isolation."""
    rule = db.execute(
        select(LeadRoutingRule).where(
            LeadRoutingRule.id == rule_id,
            LeadRoutingRule.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )

    db.delete(rule)
    db.commit()
    return True


# ── Rule Matching & Lead Routing Execution ────────────────────────────────────

def evaluate_rule_match(lead: Lead, rule: LeadRoutingRule) -> Tuple[bool, str]:
    """
    Evaluates whether a Lead satisfies all configured criteria of a routing rule.
    Returns (matched, explanation).
    """
    if not rule.is_active:
        return False, "Rule is inactive."

    # 1. Qualification Status Condition
    if rule.qualification_statuses:
        current_status = lead.qualification_status or "new"
        if current_status not in rule.qualification_statuses:
            return False, f"Qualification status '{current_status}' not in {rule.qualification_statuses}."

    # 2. Score Range Condition
    if rule.min_score is not None:
        if (lead.lead_score or 0) < rule.min_score:
            return False, f"Lead score {lead.lead_score or 0} < minimum required {rule.min_score}."

    if rule.max_score is not None:
        if (lead.lead_score or 0) > rule.max_score:
            return False, f"Lead score {lead.lead_score or 0} > maximum allowed {rule.max_score}."

    # 3. Industry Condition
    if rule.industries:
        if not lead.industry or not _string_matches_list(lead.industry, rule.industries):
            return False, f"Industry '{lead.industry}' does not match rule target industries."

    # 4. Geography Conditions
    if rule.countries:
        if not lead.country or not _string_matches_list(lead.country, rule.countries):
            return False, f"Country '{lead.country}' does not match rule target countries."

    if rule.cities:
        if not lead.city or not _string_matches_list(lead.city, rule.cities):
            return False, f"City '{lead.city}' does not match rule target cities."

    # 5. Company Size Condition
    if rule.company_size_min is not None or rule.company_size_max is not None:
        if not lead.employee_count_range:
            return False, "Lead has no employee count recorded to verify company size."

        size_bounds = _parse_size_range(lead.employee_count_range)
        if not size_bounds:
            return False, f"Unable to parse company size '{lead.employee_count_range}'."

        lead_min, lead_max = size_bounds
        if rule.company_size_min is not None and lead_max < rule.company_size_min:
            return False, f"Company size {lead_max} < minimum {rule.company_size_min}."
        if rule.company_size_max is not None and lead_min > rule.company_size_max:
            return False, f"Company size {lead_min} > maximum {rule.company_size_max}."

    return True, f"Matched rule '{rule.name}' (Priority {rule.priority})."


def route_single_lead(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
    dry_run: bool = False,
    rule_id: Optional[uuid.UUID] = None,
    force_reroute: bool = False,
) -> LeadRouteResult:
    """
    Evaluates active routing rules against a single lead and assigns to the designated user or team.
    Guarantees:
    - Never invents dummy assignees.
    - Preserves organization tenant isolation.
    - Records matched rule, assignee, and routing timestamp.
    """
    lead = db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )

    # Check existing assignment
    if (lead.assigned_to_user_id is not None or lead.routing_rule_id is not None) and not force_reroute:
        assignee_user = None
        if lead.assigned_to_user_id:
            assignee_user = db.execute(
                select(User).where(User.id == lead.assigned_to_user_id)
            ).scalar_one_or_none()

        return LeadRouteResult(
            lead_id=lead.id,
            is_routed=False,
            matched_rule_id=lead.routing_rule_id,
            matched_rule_name=(lead.routing_rule.name if lead.routing_rule else None),
            assigned_to_user_id=lead.assigned_to_user_id,
            assignee_name=(assignee_user.full_name if assignee_user else None),
            assigned_team=None,
            routed_at=lead.routed_at,
            explanation=f"Lead already assigned to {assignee_user.full_name if assignee_user else 'a team'}. Set force_reroute=True to override.",
        )

    # Fetch candidate rules
    if rule_id:
        rules = list(
            db.execute(
                select(LeadRoutingRule).where(
                    LeadRoutingRule.id == rule_id,
                    LeadRoutingRule.organization_id == current_org.id,
                    LeadRoutingRule.is_active == True,
                )
            ).scalars().all()
        )
    else:
        rules = list(
            db.execute(
                select(LeadRoutingRule)
                .where(
                    LeadRoutingRule.organization_id == current_org.id,
                    LeadRoutingRule.is_active == True,
                )
                .order_by(LeadRoutingRule.priority.asc(), LeadRoutingRule.created_at.asc())
            ).scalars().all()
        )

    if not rules:
        return LeadRouteResult(
            lead_id=lead.id,
            is_routed=False,
            matched_rule_id=None,
            matched_rule_name=None,
            assigned_to_user_id=None,
            assignee_name=None,
            assigned_team=None,
            routed_at=None,
            explanation="No active routing rules found for this organization. Lead remains unassigned.",
        )

    matched_rule: Optional[LeadRoutingRule] = None
    match_reason = ""

    for rule in rules:
        matched, reason = evaluate_rule_match(lead, rule)
        if matched:
            matched_rule = rule
            match_reason = reason
            break

    if not matched_rule:
        return LeadRouteResult(
            lead_id=lead.id,
            is_routed=False,
            matched_rule_id=None,
            matched_rule_name=None,
            assigned_to_user_id=None,
            assignee_name=None,
            assigned_team=None,
            routed_at=None,
            explanation="Lead did not match any active routing rule criteria. Lead remains unassigned.",
        )

    # Validate assignee user if rule targets a user
    assignee_user = None
    if matched_rule.assigned_to_user_id:
        assignee_user = db.execute(
            select(User).where(
                User.id == matched_rule.assigned_to_user_id,
                User.organization_id == current_org.id,
            )
        ).scalar_one_or_none()

        if not assignee_user or not assignee_user.is_active:
            # Rule matched but configured user is missing or inactive: keep unassigned honestly
            return LeadRouteResult(
                lead_id=lead.id,
                is_routed=False,
                matched_rule_id=matched_rule.id,
                matched_rule_name=matched_rule.name,
                assigned_to_user_id=None,
                assignee_name=None,
                assigned_team=matched_rule.assigned_team,
                routed_at=None,
                explanation=f"Matched rule '{matched_rule.name}' but assigned user is unconfigured or inactive. Lead remains unassigned per data integrity rules.",
            )

    now = datetime.now(timezone.utc)

    if not dry_run:
        lead.assigned_to_user_id = matched_rule.assigned_to_user_id
        lead.routing_rule_id = matched_rule.id
        lead.routed_at = now
        lead.routing_notes = (
            f"Routed via rule '{matched_rule.name}' to "
            + (f"user '{assignee_user.full_name}'" if assignee_user else f"team '{matched_rule.assigned_team}'")
        )
        db.commit()
        db.refresh(lead)

    return LeadRouteResult(
        lead_id=lead.id,
        is_routed=True,
        matched_rule_id=matched_rule.id,
        matched_rule_name=matched_rule.name,
        assigned_to_user_id=matched_rule.assigned_to_user_id,
        assignee_name=(assignee_user.full_name if assignee_user else None),
        assigned_team=matched_rule.assigned_team,
        routed_at=now,
        explanation=match_reason,
    )


def route_leads_batch(
    db: Session,
    current_org: Organization,
    lead_ids: List[uuid.UUID],
    dry_run: bool = False,
    force_reroute: bool = False,
) -> LeadBatchRouteResult:
    """
    Route multiple leads in a batch within current organization.
    Tenant-isolated.
    """
    results: List[LeadRouteResult] = []
    routed_count = 0
    unassigned_count = 0
    already_assigned_count = 0

    for lid in lead_ids:
        try:
            res = route_single_lead(
                db=db,
                current_org=current_org,
                lead_id=lid,
                dry_run=dry_run,
                force_reroute=force_reroute,
            )
            results.append(res)
            if res.is_routed:
                routed_count += 1
            elif "already assigned" in res.explanation.lower():
                already_assigned_count += 1
            else:
                unassigned_count += 1
        except HTTPException:
            # Skip non-existent or cross-tenant leads safely
            continue

    return LeadBatchRouteResult(
        total_evaluated=len(results),
        routed_count=routed_count,
        unassigned_count=unassigned_count,
        already_assigned_count=already_assigned_count,
        results=results,
    )
