"""HubSpot Production CRM Synchronization Service (Phase 1).

Executes safe, read-only synchronization of Contacts, Companies, and Deals
from HubSpot CRM v3 into Agile Sales & Marketing PostgreSQL database.

Guarantees:
1. Read-Only: Never writes, modifies, or deletes records in HubSpot CRM.
2. Tenant Isolation: Strictly scopes all records to current_org.id.
3. Idempotent: Prevents duplicates on repeated synchronizations using external hubspot_id.
4. Non-Destructive: Preserves existing database records (including voice test leads).
5. Transparent Permissions: Reports missing scopes (e.g., crm.objects.companies.read)
   without throwing fatal crashes or fabricating fake records.
6. Pagination: Fully supports HubSpot v3 cursor pagination (paging.next.after).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.crm import Company, Contact, Deal, Pipeline, PipelineStage
from app.models.hubspot_sync import HubSpotSyncRun
from app.models.lead import Lead
from app.services.integrations.hubspot.client import (
    HubSpotAuthenticationError,
    HubSpotClient,
    HubSpotConfigurationError,
    HubSpotPermissionError,
)

logger = logging.getLogger(__name__)

# Standard read properties
CONTACT_SYNC_PROPERTIES = [
    "firstname",
    "lastname",
    "email",
    "phone",
    "company",
    "associatedcompanyid",
    "jobtitle",
    "hs_lead_status",
    "createdate",
    "lastmodifieddate",
]

COMPANY_SYNC_PROPERTIES = [
    "name",
    "domain",
    "industry",
    "numberofemployees",
    "city",
    "country",
    "createdate",
    "lastmodifieddate",
]

DEAL_SYNC_PROPERTIES = [
    "dealname",
    "amount",
    "dealstage",
    "pipeline",
    "closedate",
    "hs_is_closed_won",
    "hs_is_closed",
    "createdate",
    "lastmodifieddate",
]

ALLOWED_LEAD_STATUS_MAP = {
    "new": "new",
    "open": "new",
    "in_progress": "contacted",
    "contacted": "contacted",
    "connected": "contacted",
    "replied": "replied",
    "open_deal": "qualified",
    "qualified": "qualified",
    "unqualified": "unresponsive",
    "bad_timing": "unresponsive",
    "unresponsive": "unresponsive",
    "opted_out": "opted_out",
}


# ── Response / Summary Schemas ────────────────────────────────────────────────

class ObjectSyncResult(BaseModel):
    status: str  # "synced", "empty", "missing_scope", "error", "skipped"
    imported: int = 0
    updated: int = 0
    total_in_hubspot: int = 0
    error: Optional[str] = None
    scope_required: Optional[str] = None


class HubSpotSyncSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    portal_id: Optional[str] = None
    status: str  # "completed", "partial", "failed"
    started_at: datetime
    completed_at: datetime
    contacts: ObjectSyncResult
    companies: ObjectSyncResult
    deals: ObjectSyncResult
    permission_errors: Dict[str, str] = {}
    message: str


class HubSpotSyncEngine:
    """Production HubSpot read-only synchronization engine."""

    def __init__(self, client: Optional[HubSpotClient] = None) -> None:
        self.client = client or HubSpotClient()

    async def get_portal_id(self) -> Optional[str]:
        """Fetch portal ID from HubSpot account info without modifying data."""
        if not self.client.is_configured:
            return None
        try:
            resp = await self.client.get("/account-info/v3/details", check_status=False)
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("portalId", ""))
        except Exception as exc:
            logger.warning("Failed to retrieve HubSpot portal ID: %s", exc)
        return None

    # ── Contacts Sync ─────────────────────────────────────────────────────────

    async def sync_contacts(
        self,
        db: Session,
        organization_id: uuid.UUID,
    ) -> ObjectSyncResult:
        """
        Safely fetch all HubSpot contacts with pagination and upsert locally.
        Tenant-isolated: All records stamped with organization_id.
        """
        imported_count = 0
        updated_count = 0
        total_fetched = 0
        after: Optional[str] = None

        logger.info("Starting HubSpot contacts sync for org=%s", organization_id)

        try:
            while True:
                params: Dict[str, Any] = {
                    "limit": 100,
                    "properties": ",".join(CONTACT_SYNC_PROPERTIES),
                    "associations": "companies",
                }
                if after:
                    params["after"] = after

                resp = await self.client.get("/crm/v3/objects/contacts", params=params)
                data = resp.json()
                results = data.get("results", [])
                total_fetched += len(results)

                for record in results:
                    hs_id = str(record.get("id"))
                    props = record.get("properties", {}) or {}

                    raw_email = (props.get("email") or "").strip().lower()
                    if not raw_email:
                        # Skip contacts without valid email since Contact.email is mandatory
                        logger.debug("Skipping HubSpot contact %s: missing email", hs_id)
                        continue

                    first_name = (props.get("firstname") or "").strip()
                    last_name = (props.get("lastname") or "").strip()
                    if not first_name and not last_name:
                        first_name = raw_email.split("@")[0].capitalize()
                        last_name = ""
                    elif not first_name:
                        first_name = last_name
                        last_name = ""
                    phone = (props.get("phone") or "").strip() or None
                    job_title = (props.get("jobtitle") or "").strip() or None
                    raw_company_prop = (props.get("company") or "").strip() or None

                    raw_lead_status = (props.get("hs_lead_status") or "").lower().replace(" ", "_")
                    lead_status = ALLOWED_LEAD_STATUS_MAP.get(raw_lead_status, "new")

                    # Resolve genuine HubSpot company association
                    assoc_company_id = props.get("associatedcompanyid")
                    if not assoc_company_id:
                        assoc_list = record.get("associations", {}).get("companies", {}).get("results", [])
                        if assoc_list:
                            assoc_company_id = str(assoc_list[0].get("id"))

                    resolved_company = None
                    if assoc_company_id:
                        resolved_company = db.query(Company).filter(
                            Company.organization_id == organization_id,
                            Company.hubspot_id == str(assoc_company_id),
                        ).first()

                    linked_company_id = resolved_company.id if resolved_company else None
                    resolved_company_name = (
                        resolved_company.name
                        if resolved_company
                        else (raw_company_prop if (raw_company_prop and raw_company_prop not in ("HubSpot Contact", "Unknown", "—")) else "—")
                    )
                    resolved_company_domain = resolved_company.domain if resolved_company else None

                    # 1. Upsert into CRM Contact table
                    existing_contact = db.query(Contact).filter(
                        Contact.organization_id == organization_id,
                        (Contact.hubspot_id == hs_id) | (Contact.email == raw_email),
                    ).first()

                    if existing_contact:
                        existing_contact.hubspot_id = hs_id
                        existing_contact.first_name = first_name
                        existing_contact.last_name = last_name
                        if linked_company_id:
                            existing_contact.company_id = linked_company_id
                        if phone and not existing_contact.phone:
                            existing_contact.phone = phone
                        if job_title and not existing_contact.job_title:
                            existing_contact.job_title = job_title
                        updated_count += 1
                        contact_id = existing_contact.id
                    else:
                        new_contact = Contact(
                            organization_id=organization_id,
                            hubspot_id=hs_id,
                            company_id=linked_company_id,
                            email=raw_email,
                            first_name=first_name,
                            last_name=last_name,
                            phone=phone,
                            job_title=job_title,
                            lead_status=lead_status,
                        )
                        db.add(new_contact)
                        db.flush()  # populate new_contact.id
                        imported_count += 1
                        contact_id = new_contact.id

                    # 2. Upsert into Prospecting Lead table (so it appears in Leads CRM)
                    existing_lead = db.query(Lead).filter(
                        Lead.organization_id == organization_id,
                        (Lead.source_external_id == hs_id) | (Lead.email == raw_email),
                    ).first()

                    if existing_lead:
                        # Safety: If existing lead was from voice call or other channel, preserve its source!
                        if existing_lead.source == "hubspot" or not existing_lead.source_external_id:
                            existing_lead.source_external_id = hs_id
                            existing_lead.contact_id = contact_id
                            if linked_company_id:
                                existing_lead.company_id = linked_company_id
                            if resolved_company_domain and not existing_lead.company_domain:
                                existing_lead.company_domain = resolved_company_domain
                            if not existing_lead.company_name or existing_lead.company_name in ("HubSpot Contact", "Unknown"):
                                existing_lead.company_name = resolved_company_name
                    else:
                        new_lead = Lead(
                            organization_id=organization_id,
                            contact_id=contact_id,
                            company_id=linked_company_id,
                            company_domain=resolved_company_domain,
                            source="hubspot",
                            source_external_id=hs_id,
                            first_name=first_name,
                            last_name=last_name,
                            email=raw_email,
                            phone=phone,
                            job_title=job_title,
                            company_name=resolved_company_name,
                            status="new",
                            # Clean neutral state for un-evaluated leads per data-integrity rules
                            lead_score=None,
                            lead_temperature=None,
                            qualification_status=None,
                        )
                        db.add(new_lead)

                paging = data.get("paging") or {}
                next_page = paging.get("next") or {}
                after = next_page.get("after")
                if not after:
                    break

            db.commit()

            status_str = "synced" if total_fetched > 0 else "empty"
            return ObjectSyncResult(
                status=status_str,
                imported=imported_count,
                updated=updated_count,
                total_in_hubspot=total_fetched,
            )

        except HubSpotPermissionError as exc:
            db.rollback()
            logger.warning("HubSpot contacts sync permission error: %s", exc)
            return ObjectSyncResult(
                status="missing_scope",
                error=str(exc),
                scope_required="crm.objects.contacts.read",
            )
        except Exception as exc:
            db.rollback()
            logger.error("HubSpot contacts sync failed: %s", exc, exc_info=True)
            return ObjectSyncResult(
                status="error",
                error=f"Contacts sync error: {str(exc)}",
            )

    # ── Companies Sync ────────────────────────────────────────────────────────

    async def sync_companies(
        self,
        db: Session,
        organization_id: uuid.UUID,
    ) -> ObjectSyncResult:
        """
        Safely fetch all HubSpot companies with pagination and upsert locally.
        Gracefully catches 403 / missing scope (crm.objects.companies.read)
        and returns actionable error without crashing or creating fake data.
        """
        imported_count = 0
        updated_count = 0
        total_fetched = 0
        after: Optional[str] = None

        logger.info("Starting HubSpot companies sync for org=%s", organization_id)

        try:
            while True:
                params: Dict[str, Any] = {
                    "limit": 100,
                    "properties": ",".join(COMPANY_SYNC_PROPERTIES),
                }
                if after:
                    params["after"] = after

                resp = await self.client.get("/crm/v3/objects/companies", params=params)
                data = resp.json()
                results = data.get("results", [])
                total_fetched += len(results)

                for record in results:
                    hs_id = str(record.get("id"))
                    props = record.get("properties", {}) or {}

                    domain = (props.get("domain") or "").strip().lower() or None
                    name = (props.get("name") or "").strip() or domain or f"HubSpot Company {hs_id}"
                    industry = (props.get("industry") or "").strip() or None
                    employees = str(props.get("numberofemployees") or "").strip() or None
                    city = (props.get("city") or "").strip() or None
                    country = (props.get("country") or "").strip() or None

                    existing_company = None
                    if domain:
                        existing_company = db.query(Company).filter(
                            Company.organization_id == organization_id,
                            (Company.hubspot_id == hs_id) | (Company.domain == domain),
                        ).first()
                    else:
                        existing_company = db.query(Company).filter(
                            Company.organization_id == organization_id,
                            Company.hubspot_id == hs_id,
                        ).first()

                    if existing_company:
                        existing_company.hubspot_id = hs_id
                        existing_company.name = name
                        if domain and not existing_company.domain:
                            existing_company.domain = domain
                        if industry and not existing_company.industry:
                            existing_company.industry = industry
                        if employees and not existing_company.employee_count_range:
                            existing_company.employee_count_range = employees
                        if city and not existing_company.city:
                            existing_company.city = city
                        if country and not existing_company.country:
                            existing_company.country = country
                        updated_count += 1
                    else:
                        new_company = Company(
                            organization_id=organization_id,
                            hubspot_id=hs_id,
                            name=name,
                            domain=domain,
                            industry=industry,
                            employee_count_range=employees,
                            city=city,
                            country=country,
                        )
                        db.add(new_company)
                        imported_count += 1

                paging = data.get("paging") or {}
                next_page = paging.get("next") or {}
                after = next_page.get("after")
                if not after:
                    break

            db.commit()

            status_str = "synced" if total_fetched > 0 else "empty"
            return ObjectSyncResult(
                status=status_str,
                imported=imported_count,
                updated=updated_count,
                total_in_hubspot=total_fetched,
            )

        except HubSpotPermissionError as exc:
            db.rollback()
            logger.warning("HubSpot companies sync missing scope: %s", exc)
            return ObjectSyncResult(
                status="missing_scope",
                imported=0,
                updated=0,
                total_in_hubspot=0,
                error=(
                    "Missing required scope 'crm.objects.companies.read'. "
                    "To synchronize company records, add this scope to your HubSpot Private App in HubSpot Settings > Integrations > Private Apps."
                ),
                scope_required="crm.objects.companies.read",
            )
        except Exception as exc:
            db.rollback()
            logger.error("HubSpot companies sync failed: %s", exc, exc_info=True)
            return ObjectSyncResult(
                status="error",
                error=f"Companies sync error: {str(exc)}",
            )

    # ── Deals Sync ────────────────────────────────────────────────────────────

    async def sync_deals(
        self,
        db: Session,
        organization_id: uuid.UUID,
    ) -> ObjectSyncResult:
        """
        Safely fetch all HubSpot deals with pagination and upsert locally.
        Links deals to organization's default sales pipeline stage.
        """
        imported_count = 0
        updated_count = 0
        total_fetched = 0
        after: Optional[str] = None

        logger.info("Starting HubSpot deals sync for org=%s", organization_id)

        # Retrieve default pipeline stage
        default_stage = (
            db.query(PipelineStage)
            .join(Pipeline, Pipeline.id == PipelineStage.pipeline_id)
            .filter(
                Pipeline.organization_id == organization_id,
                Pipeline.is_default == True,  # noqa: E712
            )
            .order_by(PipelineStage.order_index.asc())
            .first()
        )

        if not default_stage:
            # Fallback to any stage belonging to org
            default_stage = (
                db.query(PipelineStage)
                .join(Pipeline, Pipeline.id == PipelineStage.pipeline_id)
                .filter(Pipeline.organization_id == organization_id)
                .order_by(PipelineStage.order_index.asc())
                .first()
            )

        if not default_stage:
            # Create standard default pipeline and stages for the organization
            logger.info("Creating default pipeline for organization %s", organization_id)
            pipeline = Pipeline(
                organization_id=organization_id,
                name="Default Sales Pipeline",
                is_default=True,
            )
            db.add(pipeline)
            db.flush()

            stages = [
                PipelineStage(pipeline_id=pipeline.id, name="Discovery", order_index=1, probability_pct=10),
                PipelineStage(pipeline_id=pipeline.id, name="Qualified", order_index=2, probability_pct=30),
                PipelineStage(pipeline_id=pipeline.id, name="Demo", order_index=3, probability_pct=50),
                PipelineStage(pipeline_id=pipeline.id, name="Proposal", order_index=4, probability_pct=80),
                PipelineStage(pipeline_id=pipeline.id, name="Won", order_index=5, probability_pct=100),
            ]
            db.add_all(stages)
            db.flush()
            default_stage = stages[0]

        try:
            while True:
                params: Dict[str, Any] = {
                    "limit": 100,
                    "properties": ",".join(DEAL_SYNC_PROPERTIES),
                }
                if after:
                    params["after"] = after

                resp = await self.client.get("/crm/v3/objects/deals", params=params)
                data = resp.json()
                results = data.get("results", [])
                total_fetched += len(results)

                for record in results:
                    hs_id = str(record.get("id"))
                    props = record.get("properties", {}) or {}

                    name = (props.get("dealname") or "").strip() or f"HubSpot Deal {hs_id}"

                    # Safe amount parsing
                    raw_amount = props.get("amount")
                    amount = Decimal("0.00")
                    if raw_amount:
                        try:
                            amount = Decimal(str(raw_amount))
                            if amount < 0:
                                amount = Decimal("0.00")
                        except (InvalidOperation, ValueError):
                            amount = Decimal("0.00")

                    # Expected close date
                    close_date_str = props.get("closedate")
                    expected_close_date: Optional[date] = None
                    if close_date_str:
                        try:
                            # Handle ISO format strings like "2026-12-31T00:00:00.000Z"
                            expected_close_date = datetime.fromisoformat(
                                close_date_str.replace("Z", "+00:00")
                            ).date()
                        except Exception:
                            expected_close_date = None

                    # Deal status mapping
                    is_won = str(props.get("hs_is_closed_won", "")).lower() == "true"
                    is_closed = str(props.get("hs_is_closed", "")).lower() == "true"
                    if is_won:
                        status = "won"
                    elif is_closed:
                        status = "lost"
                    else:
                        status = "open"

                    existing_deal = db.query(Deal).filter(
                        Deal.organization_id == organization_id,
                        Deal.hubspot_id == hs_id,
                    ).first()

                    if existing_deal:
                        existing_deal.name = name
                        existing_deal.amount = amount
                        existing_deal.status = status
                        if expected_close_date:
                            existing_deal.expected_close_date = expected_close_date
                        updated_count += 1
                    else:
                        if not default_stage:
                            logger.error("Cannot create deal %s: missing pipeline stage", hs_id)
                            continue
                        new_deal = Deal(
                            organization_id=organization_id,
                            pipeline_stage_id=default_stage.id,
                            hubspot_id=hs_id,
                            name=name,
                            amount=amount,
                            status=status,
                            expected_close_date=expected_close_date,
                        )
                        db.add(new_deal)
                        imported_count += 1

                paging = data.get("paging") or {}
                next_page = paging.get("next") or {}
                after = next_page.get("after")
                if not after:
                    break

            db.commit()

            status_str = "synced" if total_fetched > 0 else "empty"
            return ObjectSyncResult(
                status=status_str,
                imported=imported_count,
                updated=updated_count,
                total_in_hubspot=total_fetched,
            )

        except HubSpotPermissionError as exc:
            db.rollback()
            logger.warning("HubSpot deals sync permission error: %s", exc)
            return ObjectSyncResult(
                status="missing_scope",
                error=str(exc),
                scope_required="crm.objects.deals.read",
            )
        except Exception as exc:
            db.rollback()
            logger.error("HubSpot deals sync failed: %s", exc, exc_info=True)
            return ObjectSyncResult(
                status="error",
                error=f"Deals sync error: {str(exc)}",
            )

    # ── Full Safe Read-Only Sync Orchestrator ─────────────────────────────────

    async def run_sync(
        self,
        db: Session,
        organization_id: uuid.UUID,
    ) -> HubSpotSyncSummary:
        """
        Execute full Phase 1 read-only synchronization.
        Saves an audit record in hubspot_sync_runs.
        """
        if not self.client.is_configured:
            raise HubSpotConfigurationError("HUBSPOT_ACCESS_TOKEN is not configured.")

        started_at = datetime.now(timezone.utc)
        portal_id = await self.get_portal_id()

        # Execute read-only syncs sequentially: companies first so contacts can link to existing companies!
        companies_res = await self.sync_companies(db, organization_id)
        contacts_res = await self.sync_contacts(db, organization_id)
        deals_res = await self.sync_deals(db, organization_id)

        # Post-sync backfill pass: ensure every Contact has company_id linked if available
        self._backfill_associations(db, organization_id)

        completed_at = datetime.now(timezone.utc)

        # Collect permission errors
        permission_errors: Dict[str, str] = {}
        if companies_res.status == "missing_scope" and companies_res.error:
            permission_errors["companies"] = companies_res.error
        if contacts_res.status == "missing_scope" and contacts_res.error:
            permission_errors["contacts"] = contacts_res.error
        if deals_res.status == "missing_scope" and deals_res.error:
            permission_errors["deals"] = deals_res.error

        # Determine overall run status
        has_errors = any(
            r.status == "error" for r in (contacts_res, companies_res, deals_res)
        )
        has_permission_gaps = bool(permission_errors)

        if has_errors and contacts_res.status == "error":
            run_status = "failed"
            message = "HubSpot synchronization failed."
        elif has_permission_gaps or has_errors:
            run_status = "partial"
            parts = []
            if contacts_res.status == "synced":
                parts.append(f"{contacts_res.imported + contacts_res.updated} contacts")
            if companies_res.status == "synced":
                parts.append(f"{companies_res.imported + companies_res.updated} companies")
            if deals_res.status == "synced":
                parts.append(f"{deals_res.imported + deals_res.updated} deals")
            synced_str = ", ".join(parts) if parts else "no records"
            message = f"Synchronized {synced_str}. Permission attention required for companies."
        else:
            run_status = "completed"
            message = "HubSpot synchronization completed successfully."

        # Audit run record in DB
        sync_run = HubSpotSyncRun(
            organization_id=organization_id,
            status=run_status,
            contacts_count=contacts_res.imported + contacts_res.updated,
            companies_count=companies_res.imported + companies_res.updated,
            deals_count=deals_res.imported + deals_res.updated,
            portal_id=portal_id,
            permission_errors=permission_errors or None,
            error_message=message if run_status != "completed" else None,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(sync_run)
        db.commit()
        db.refresh(sync_run)

        return HubSpotSyncSummary(
            run_id=str(sync_run.id),
            portal_id=portal_id,
            status=run_status,
            started_at=started_at,
            completed_at=completed_at,
            contacts=contacts_res,
            companies=companies_res,
            deals=deals_res,
            permission_errors=permission_errors,
            message=message,
        )

    @staticmethod
    def _backfill_associations(db: Session, organization_id: uuid.UUID) -> None:
        """
        Post-sync association backfill: links any contacts where company_id is NULL
        to the matching company resolved via leads or domain.
        """
        try:
            contacts_to_backfill = (
                db.query(Contact)
                .filter(Contact.organization_id == organization_id, Contact.company_id.is_(None))
                .all()
            )
            for contact in contacts_to_backfill:
                lead = (
                    db.query(Lead)
                    .filter(Lead.organization_id == organization_id, Lead.email == contact.email)
                    .first()
                )
                if lead and lead.company_id:
                    contact.company_id = lead.company_id
                    continue

                if contact.email and "@" in contact.email:
                    domain = contact.email.split("@")[1].lower()
                    company = (
                        db.query(Company)
                        .filter(Company.organization_id == organization_id, Company.domain == domain)
                        .first()
                    )
                    if company:
                        contact.company_id = company.id
                        if lead and not lead.company_id:
                            lead.company_id = company.id
                            lead.company_name = company.name

            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Error during post-sync association backfill: %s", exc)
