"""Lead and prospect management API endpoints."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.icp import IdealCustomerProfile
from app.models.tenant import Organization
from app.schemas.lead import (
    LeadBulkStatusResponse,
    LeadBulkStatusUpdate,
    LeadConversionResponse,
    LeadCreate,
    LeadUpdate,
    LeadImportRequest,
    LeadImportResponse,
    LeadListResponse,
    LeadQualificationUpdate,
    LeadResponse,
    LeadSelectionRequest,
    LeadSelectionResponse,
)
from app.schemas.qualification import (
    CampaignEligibilityResult,
    LeadBatchEvaluateRequest,
    LeadBatchEvaluateResult,
    LeadCampaignEnrollRequest,
    LeadCampaignEnrollResult,
    LeadQualificationEvaluateRequest,
    LeadQualificationResult,
)
from app.schemas.routing_rule import (
    LeadBatchRouteRequest,
    LeadBatchRouteResult,
    LeadRouteRequest,
    LeadRouteResult,
)
from app.services.lead_generation import (
    DuplicateLeadError,
    bulk_update_lead_status,
    convert_lead_to_crm,
    create_lead,
    delete_lead,
    get_lead,
    import_leads,
    list_leads,
    select_leads,
    update_lead_qualification,
    update_lead,
)
from app.services.lead_qualification import (
    check_lead_campaign_eligibility,
    enroll_qualified_lead_in_campaign,
    evaluate_leads_batch,
    evaluate_single_lead_qualification,
    route_leads_batch,
    route_single_lead,
)

router = APIRouter(prefix="/leads", tags=["Leads & Prospects"])


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create lead manually",
    description="Manually create a new prospect lead scoped to authenticated tenant organization.",
)
async def create_new_lead(
    payload: LeadCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResponse:
    try:
        lead = create_lead(db, current_org, payload)
        return LeadResponse.model_validate(lead)
    except DuplicateLeadError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.post(
    "/import",
    response_model=LeadImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch import leads",
    description="Imports a batch of prospect lead records scoped to authenticated tenant, skipping duplicate emails without overwriting existing records.",
)
async def import_lead_batch(
    payload: LeadImportRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadImportResponse:
    return import_leads(db, current_org, payload.rows)


@router.get(
    "",
    response_model=LeadListResponse,
    status_code=status.HTTP_200_OK,
    summary="List leads with filtering and pagination",
    description="Query prospecting leads scoped to authenticated tenant organization.",
)
async def get_leads(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    icp_id: Optional[uuid.UUID] = Query(None, description="Filter by ICP"),
    qualification_status: Optional[str] = Query(None, description="Filter by qualification status"),
    lead_temperature: Optional[str] = Query(None, description="Filter by temperature (cold/warm/hot)"),
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum lead score"),
    max_score: Optional[int] = Query(None, ge=0, le=100, description="Maximum lead score"),
    industry: Optional[str] = Query(None, description="Filter by industry"),
    country: Optional[str] = Query(None, description="Filter by country"),
    city: Optional[str] = Query(None, description="Filter by city"),
    search: Optional[str] = Query(None, description="Search company name, domain, person name, or email"),
    exclude_test: bool = Query(True, description="Exclude Retell test artifacts"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadListResponse:
    leads, total = list_leads(
        db=db,
        current_org=current_org,
        page=page,
        page_size=page_size,
        icp_id=icp_id,
        qualification_status=qualification_status,
        lead_temperature=lead_temperature,
        status_filter=status,
        source=source,
        min_score=min_score,
        max_score=max_score,
        industry=industry,
        country=country,
        city=city,
        search=search,
        exclude_test=exclude_test,
    )
    return LeadListResponse(
        items=[LeadResponse.model_validate(l) for l in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/bulk-status",
    response_model=LeadBulkStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk update lifecycle or qualification status",
    description="Updates status or qualification_status for multiple leads scoped to current tenant.",
)
async def bulk_update_status(
    payload: LeadBulkStatusUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadBulkStatusResponse:
    if payload.status is None and payload.qualification_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either status or qualification_status",
        )
    count, ids = bulk_update_lead_status(
        db=db,
        current_org=current_org,
        lead_ids=payload.lead_ids,
        status=payload.status,
        qualification_status=payload.qualification_status,
    )
    return LeadBulkStatusResponse(updated_count=count, updated_ids=ids)


@router.post(
    "/select",
    response_model=LeadSelectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Select leads for future campaigns",
    description="Marks specified leads as selected while rejecting disqualified leads.",
)
async def select_lead_batch(
    payload: LeadSelectionRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadSelectionResponse:
    return select_leads(db, current_org, payload.lead_ids)


@router.post(
    "/batch-evaluate-qualification",
    response_model=LeadBatchEvaluateResult,
    status_code=status.HTTP_200_OK,
    summary="Batch evaluate lead qualification",
    description="Evaluates multiple leads against ICP criteria in a single request.",
)
async def batch_evaluate_leads_qualification(
    payload: LeadBatchEvaluateRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadBatchEvaluateResult:
    return evaluate_leads_batch(
        db=db,
        current_org=current_org,
        lead_ids=payload.lead_ids,
        icp_id=payload.icp_id,
        dry_run=payload.dry_run,
        qualification_threshold=payload.qualification_threshold,
    )


@router.post(
    "/batch-route",
    response_model=LeadBatchRouteResult,
    status_code=status.HTTP_200_OK,
    summary="Batch route multiple leads",
    description="Executes routing rule evaluation across multiple leads.",
)
async def batch_route_leads(
    payload: LeadBatchRouteRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadBatchRouteResult:
    return route_leads_batch(
        db=db,
        current_org=current_org,
        lead_ids=payload.lead_ids,
        dry_run=payload.dry_run,
        force_reroute=payload.force_reroute,
    )


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single lead details",
    description="Retrieve lead details with strict tenant isolation.",
)
async def get_lead_by_id(
    lead_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = get_lead(db, current_org, lead_id)
    return LeadResponse.model_validate(lead)


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
    status_code=status.HTTP_200_OK,
    summary="Update lead details",
    description="Partially update a prospect lead record including LinkedIn profile URL with tenant isolation.",
)
async def update_lead_by_id(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = update_lead(db, current_org, lead_id, payload)
    return LeadResponse.model_validate(lead)


@router.patch(
    "/{lead_id}/qualification",
    response_model=LeadResponse,
    status_code=status.HTTP_200_OK,
    summary="Update lead qualification status and temperature",
    description="Explicit tenant-scoped qualification review of a prospect lead.",
)
async def update_qualification(
    lead_id: uuid.UUID,
    payload: LeadQualificationUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = update_lead_qualification(db, current_org, lead_id, payload)
    return LeadResponse.model_validate(lead)


@router.post(
    "/{lead_id}/evaluate-qualification",
    response_model=LeadQualificationResult,
    status_code=status.HTTP_200_OK,
    summary="Evaluate single lead qualification",
    description="Deterministically evaluates lead against ICP criteria with explainable score breakdown.",
)
async def evaluate_lead_qualification(
    lead_id: uuid.UUID,
    payload: Optional[LeadQualificationEvaluateRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadQualificationResult:
    lead = get_lead(db, current_org, lead_id)
    icp = None
    dry_run = False
    threshold = 50
    if payload:
        dry_run = payload.dry_run
        threshold = payload.qualification_threshold
        if payload.icp_id:
            icp = db.execute(
                select(IdealCustomerProfile).where(
                    IdealCustomerProfile.id == payload.icp_id,
                    IdealCustomerProfile.organization_id == current_org.id,
                )
            ).scalar_one_or_none()
            if not icp:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ICP '{payload.icp_id}' not found.")
    return evaluate_single_lead_qualification(
        db=db,
        current_org=current_org,
        lead=lead,
        icp=icp,
        dry_run=dry_run,
        qualification_threshold=threshold,
    )


@router.post(
    "/{lead_id}/route",
    response_model=LeadRouteResult,
    status_code=status.HTTP_200_OK,
    summary="Route single lead to sales representative",
    description="Matches lead against active routing rules in priority order and assigns ownership.",
)
async def route_lead(
    lead_id: uuid.UUID,
    payload: Optional[LeadRouteRequest] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadRouteResult:
    dry_run = payload.dry_run if payload else False
    rule_id = payload.rule_id if payload else None
    force_reroute = payload.force_reroute if payload else False
    return route_single_lead(
        db=db,
        current_org=current_org,
        lead_id=lead_id,
        dry_run=dry_run,
        rule_id=rule_id,
        force_reroute=force_reroute,
    )


@router.get(
    "/{lead_id}/campaign-eligibility/{campaign_id}",
    response_model=CampaignEligibilityResult,
    status_code=status.HTTP_200_OK,
    summary="Check lead campaign eligibility",
    description="Validates whether lead is qualified, not opted out, and not duplicate in campaign.",
)
async def check_campaign_eligibility(
    lead_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> CampaignEligibilityResult:
    return check_lead_campaign_eligibility(
        db=db,
        current_org=current_org,
        lead_id=lead_id,
        campaign_id=campaign_id,
    )


@router.post(
    "/{lead_id}/enroll-campaign",
    response_model=LeadCampaignEnrollResult,
    status_code=status.HTTP_200_OK,
    summary="Safely enroll qualified lead into campaign",
    description="Enrolls qualified lead into target campaign without triggering automatic outreach dispatch.",
)
async def enroll_lead_campaign(
    lead_id: uuid.UUID,
    payload: LeadCampaignEnrollRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadCampaignEnrollResult:
    return enroll_qualified_lead_in_campaign(
        db=db,
        current_org=current_org,
        lead_id=lead_id,
        campaign_id=payload.campaign_id,
    )


@router.post(
    "/{lead_id}/convert",
    response_model=LeadConversionResponse,
    status_code=status.HTTP_200_OK,
    summary="Convert lead to CRM Company and Contact",
    description="Promotes a prospect Lead to formal CRM Company and Contact records without duplicates.",
)
async def convert_lead(
    lead_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> LeadConversionResponse:
    return convert_lead_to_crm(db, current_org, lead_id)


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete lead",
    description="Deletes an individual lead scoped to the authenticated tenant organization without deleting shared CRM contacts or other campaigns.",
)
async def delete_single_lead(
    lead_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    delete_lead(db, current_org, lead_id)


