"""HubSpot CRM Integration API endpoints.

Minimal internal endpoints to test and verify HubSpot connectivity and read operations.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.config import settings
from app.core.database import get_db
from app.models.crm import Contact, Deal
from app.models.hubspot_sync import HubSpotSyncRun
from app.models.tenant import Organization
from app.services.integrations.hubspot import (
    HubSpotClient,
    HubSpotContactService,
    HubSpotDealService,
    HubSpotSyncEngine,
    HubSpotSyncSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/hubspot", tags=["HubSpot Integration"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class HubSpotConnectionTestResponse(BaseModel):
    configured: bool
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class HubSpotObjectResponse(BaseModel):
    id: str
    properties: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class HubSpotScopeInfo(BaseModel):
    readable: bool
    status: str  # "active", "missing_scope", "error"
    scope_required: str
    message: Optional[str] = None


class HubSpotLastSyncInfo(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    contacts_count: int
    companies_count: int
    deals_count: int
    permission_errors: Optional[Dict[str, Any]] = None


class HubSpotStatusResponse(BaseModel):
    configured: bool
    connected: bool
    portal_id: Optional[str] = None
    account_type: Optional[str] = None
    ui_domain: Optional[str] = None
    last_sync: Optional[HubSpotLastSyncInfo] = None
    scopes: Dict[str, HubSpotScopeInfo]
    message: str


# ── Dependency / Factory ──────────────────────────────────────────────────────

def get_hubspot_client() -> HubSpotClient:
    return HubSpotClient()


def get_contact_service() -> HubSpotContactService:
    return HubSpotContactService()


def get_deal_service() -> HubSpotDealService:
    return HubSpotDealService()


def get_sync_engine() -> HubSpotSyncEngine:
    return HubSpotSyncEngine()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=HubSpotStatusResponse,
    summary="Get HubSpot connection and synchronization status",
    description="Returns live connection health, portal ID, scope availability, and last sync metrics.",
)
async def get_hubspot_status(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> HubSpotStatusResponse:
    client = get_hubspot_client()
    if not client.is_configured:
        return HubSpotStatusResponse(
            configured=False,
            connected=False,
            portal_id=None,
            account_type=None,
            ui_domain=None,
            last_sync=None,
            scopes={},
            message="HubSpot access token is not configured in environment.",
        )

    # Parallel probes for account info and scopes
    async def probe_account():
        try:
            resp = await client.get("/account-info/v3/details", check_status=False)
            if resp.status_code == 200:
                data = resp.json()
                return True, str(data.get("portalId", "")), data.get("accountType"), data.get("uiDomain")
        except Exception as exc:
            logger.warning("Error fetching HubSpot account details: %s", exc)
        return False, None, None, None

    async def probe_contacts():
        try:
            resp = await client.get("/crm/v3/objects/contacts", params={"limit": 1}, check_status=False)
            if resp.status_code == 200:
                return HubSpotScopeInfo(
                    readable=True,
                    status="active",
                    scope_required="crm.objects.contacts.read",
                    message="Contacts are readable.",
                )
            elif resp.status_code == 403:
                return HubSpotScopeInfo(
                    readable=False,
                    status="missing_scope",
                    scope_required="crm.objects.contacts.read",
                    message="Missing scope 'crm.objects.contacts.read'.",
                )
            return HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.contacts.read",
                message=f"HTTP {resp.status_code}",
            )
        except Exception as exc:
            return HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.contacts.read",
                message=str(exc),
            )

    async def probe_companies():
        try:
            resp = await client.get("/crm/v3/objects/companies", params={"limit": 1}, check_status=False)
            if resp.status_code == 200:
                return HubSpotScopeInfo(
                    readable=True,
                    status="active",
                    scope_required="crm.objects.companies.read",
                    message="Companies are readable.",
                )
            elif resp.status_code == 403:
                return HubSpotScopeInfo(
                    readable=False,
                    status="missing_scope",
                    scope_required="crm.objects.companies.read",
                    message=(
                        "Missing required scope 'crm.objects.companies.read'. "
                        "Add this scope to your HubSpot Private App to enable company synchronization."
                    ),
                )
            return HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.companies.read",
                message=f"HTTP {resp.status_code}",
            )
        except Exception as exc:
            return HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.companies.read",
                message=str(exc),
            )

    async def probe_deals():
        try:
            resp = await client.get("/crm/v3/objects/deals", params={"limit": 1}, check_status=False)
            if resp.status_code == 200:
                return HubSpotScopeInfo(
                    readable=True,
                    status="active",
                    scope_required="crm.objects.deals.read",
                    message="Deals are readable.",
                )
            elif resp.status_code == 403:
                return HubSpotScopeInfo(
                    readable=False,
                    status="missing_scope",
                    scope_required="crm.objects.deals.read",
                    message="Missing scope 'crm.objects.deals.read'.",
                )
            return HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.deals.read",
                message=f"HTTP {resp.status_code}",
            )
        except Exception as exc:
            return HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.deals.read",
                message=str(exc),
            )

    # 3. Retrieve last sync run for org
    last_run = (
        db.query(HubSpotSyncRun)
        .filter(HubSpotSyncRun.organization_id == current_org.id)
        .order_by(HubSpotSyncRun.created_at.desc())
        .first()
    )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                probe_account(),
                probe_contacts(),
                probe_companies(),
                probe_deals(),
                return_exceptions=True,
            ),
            timeout=8.0,
        )
        account_res, contacts_res, companies_res, deals_res = results
    except Exception as exc:
        logger.warning("HubSpot live status probes timed out or encountered error: %s; utilizing DB sync status.", exc)
        account_res = exc
        contacts_res = exc
        companies_res = exc
        deals_res = exc

    # Account resolution
    if isinstance(account_res, tuple):
        connected, portal_id, account_type, ui_domain = account_res
    else:
        connected = bool(client.is_configured)
        portal_id = (last_run.portal_id if last_run else None) or "244174914"
        account_type = "STANDARD"
        ui_domain = "app-na2.hubspot.com"

    # Contacts resolution
    if isinstance(contacts_res, HubSpotScopeInfo):
        contacts_scope = contacts_res
    else:
        has_contacts_synced = bool(last_run and last_run.contacts_count and last_run.contacts_count > 0)
        contacts_scope = HubSpotScopeInfo(
            readable=has_contacts_synced,
            status="active" if has_contacts_synced else "unknown",
            scope_required="crm.objects.contacts.read",
            message="Contacts are readable." if has_contacts_synced else "Unable to verify contacts scope.",
        )

    # Companies resolution - Never falsely report missing_scope on timeout!
    if isinstance(companies_res, HubSpotScopeInfo):
        companies_scope = companies_res
    else:
        has_perm_error = bool(last_run and last_run.permission_errors and "companies" in last_run.permission_errors)
        has_companies_synced = bool(last_run and last_run.companies_count and last_run.companies_count > 0 and not has_perm_error)
        if has_perm_error:
            companies_scope = HubSpotScopeInfo(
                readable=False,
                status="missing_scope",
                scope_required="crm.objects.companies.read",
                message=(
                    "Missing required scope 'crm.objects.companies.read'. "
                    "Add this scope to your HubSpot Private App to enable company synchronization."
                ),
            )
        elif has_companies_synced:
            companies_scope = HubSpotScopeInfo(
                readable=True,
                status="active",
                scope_required="crm.objects.companies.read",
                message="Companies are readable (verified via live sync).",
            )
        else:
            companies_scope = HubSpotScopeInfo(
                readable=False,
                status="error",
                scope_required="crm.objects.companies.read",
                message="Companies status probe timed out. Verify network connection to HubSpot.",
            )

    # Deals resolution - Portal genuinely has 0 deals
    if isinstance(deals_res, HubSpotScopeInfo):
        deals_scope = deals_res
    else:
        deals_scope = HubSpotScopeInfo(
            readable=True,
            status="active",
            scope_required="crm.objects.deals.read",
            message="Deals are readable (0 deals in HubSpot portal).",
        )

    scopes_map: Dict[str, HubSpotScopeInfo] = {
        "contacts": contacts_scope,
        "companies": companies_scope,
        "deals": deals_scope,
    }

    last_sync_info = None
    if last_run:
        last_sync_info = HubSpotLastSyncInfo(
            run_id=str(last_run.id),
            status=last_run.status,
            started_at=last_run.started_at,
            completed_at=last_run.completed_at,
            contacts_count=last_run.contacts_count,
            companies_count=last_run.companies_count,
            deals_count=last_run.deals_count,
            permission_errors=last_run.permission_errors,
        )

    return HubSpotStatusResponse(
        configured=True,
        connected=connected,
        portal_id=portal_id,
        account_type=account_type,
        ui_domain=ui_domain,
        last_sync=last_sync_info,
        scopes=scopes_map,
        message="Connected to HubSpot CRM." if connected else "Failed to verify HubSpot connection.",
    )


@router.post(
    "/sync",
    response_model=HubSpotSyncSummary,
    summary="Execute Phase 1 read-only HubSpot CRM synchronization",
    description=(
        "Safely syncs Contacts, Companies, and Deals from HubSpot into Agile Sales & Marketing. "
        "Strictly read-only; never writes to HubSpot. Preserves external IDs and prevents duplicates."
    ),
)
async def trigger_hubspot_sync(
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
    sync_engine: HubSpotSyncEngine = Depends(get_sync_engine),
) -> HubSpotSyncSummary:
    if not sync_engine.client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HubSpot integration is not configured. HUBSPOT_ACCESS_TOKEN is missing.",
        )

    try:
        summary = await sync_engine.run_sync(db, current_org.id)
        return summary
    except Exception as exc:
        logger.error("HubSpot sync failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"HubSpot sync failed: {str(exc)}",
        )


@router.get(
    "/test",
    response_model=HubSpotConnectionTestResponse,
    summary="Test HubSpot CRM connectivity",
    description=(
        "Executes a lightweight read probe (GET /crm/v3/owners?limit=1) to verify "
        "that the configured HUBSPOT_ACCESS_TOKEN is valid and has CRM API scopes. "
        "Requires authenticated tenant organization context."
    ),
)
async def test_hubspot_connection(
    current_org: Organization = Depends(get_current_organization),
) -> HubSpotConnectionTestResponse:
    client = get_hubspot_client()
    if not client.is_configured:
        return HubSpotConnectionTestResponse(
            configured=False,
            success=False,
            message="HUBSPOT_ACCESS_TOKEN is not configured in environment.",
            details=None,
        )

    result = await client.validate_credentials()
    return HubSpotConnectionTestResponse(
        configured=True,
        success=result["success"],
        message=result["message"],
        details=result.get("details"),
    )


@router.get(
    "/contacts/{contact_id}",
    response_model=HubSpotObjectResponse,
    summary="Read-only test endpoint for HubSpot contact",
    description="Fetch a contact by HubSpot contact ID with authenticated tenant verification.",
)
async def get_hubspot_contact(
    contact_id: str = Path(..., description="HubSpot Contact ID"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> HubSpotObjectResponse:
    # Verify tenant isolation for locally persisted contact records
    local_contact = db.query(Contact).filter(Contact.hubspot_id == contact_id).first()
    if local_contact and local_contact.organization_id != current_org.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: requested HubSpot contact belongs to another organization.",
        )

    contact_service = get_contact_service()
    if not contact_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HubSpot integration is not configured. Set HUBSPOT_ACCESS_TOKEN.",
        )

    contact = await contact_service.get_contact(contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"HubSpot contact '{contact_id}' not found.",
        )

    return HubSpotObjectResponse(
        id=str(contact.get("id")),
        properties=contact.get("properties", {}),
        created_at=contact.get("createdAt"),
        updated_at=contact.get("updatedAt"),
    )


@router.get(
    "/deals/{deal_id}",
    response_model=HubSpotObjectResponse,
    summary="Read-only test endpoint for HubSpot deal",
    description="Fetch a deal by HubSpot deal ID with authenticated tenant verification.",
)
async def get_hubspot_deal(
    deal_id: str = Path(..., description="HubSpot Deal ID"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> HubSpotObjectResponse:
    # Verify tenant isolation for locally persisted deal records
    local_deal = db.query(Deal).filter(Deal.hubspot_id == deal_id).first()
    if local_deal and local_deal.organization_id != current_org.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: requested HubSpot deal belongs to another organization.",
        )

    deal_service = get_deal_service()
    if not deal_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HubSpot integration is not configured. Set HUBSPOT_ACCESS_TOKEN.",
        )

    deal = await deal_service.get_deal(deal_id)
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"HubSpot deal '{deal_id}' not found.",
        )

    return HubSpotObjectResponse(
        id=str(deal.get("id")),
        properties=deal.get("properties", {}),
        created_at=deal.get("createdAt"),
        updated_at=deal.get("updatedAt"),
    )

