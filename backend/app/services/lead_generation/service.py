"""Lead generation and prospect management orchestration service (Step 11)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.normalization import normalize_domain, normalize_email
from app.models.crm import Company, Contact
from app.models.icp import IdealCustomerProfile
from app.models.lead import Lead
from app.models.tenant import Organization
from app.schemas.lead import (
    LeadConversionResponse,
    LeadCreate,
    LeadImportResponse,
    LeadImportRow,
    LeadQualificationUpdate,
    LeadSelectionResponse,
    LeadUpdate,
)
from app.services.lead_generation.base import (
    LeadGenerationProvider,
    LeadSearchCriteria,
)
from app.services.lead_generation.mock_provider import MockLeadGenerationProvider
from app.services.lead_generation.scoring import calculate_lead_score


class LeadGenerationError(Exception):
    """Base exception for lead generation operations."""
    pass


class DuplicateLeadError(LeadGenerationError):
    """Raised when a lead with the same email already exists in the organization."""
    pass


def generate_leads(
    db: Session,
    current_org: Organization,
    icp_id: uuid.UUID,
    provider: Optional[LeadGenerationProvider] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Generate and persist prospect leads matching the specified ICP.
    Deduplicates prospects against existing leads and contacts in the organization.
    Assigns initial score, temperature, and explainable qualification reason.
    Does NOT enroll leads into campaigns and does NOT send emails.
    """
    icp = db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.id == icp_id,
            IdealCustomerProfile.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not icp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ideal Customer Profile not found",
        )

    # Convert ICP into provider criteria
    criteria = LeadSearchCriteria(
        industries=icp.industries,
        company_size_min=icp.company_size_min,
        company_size_max=icp.company_size_max,
        countries=icp.countries,
        cities=icp.cities,
        company_domains=icp.company_domains,
        job_titles=icp.job_titles,
        seniority_levels=icp.seniority_levels,
        departments=icp.departments,
        technologies=icp.technologies,
        keywords=icp.keywords,
    )

    if provider is None:
        provider = MockLeadGenerationProvider()

    search_result = provider.search(criteria=criteria, limit=limit)

    created_leads: List[Lead] = []
    skipped_count = 0

    for gen in search_result.leads:
        norm_email = normalize_email(gen.email)
        norm_domain = normalize_domain(gen.company_domain)

        # 1. Deduplicate by email within organization
        if norm_email:
            existing_by_email = db.execute(
                select(Lead).where(
                    Lead.organization_id == current_org.id,
                    func.lower(Lead.email) == norm_email,
                )
            ).scalar_one_or_none()
            if existing_by_email:
                skipped_count += 1
                continue

        # 2. Tenant-scoped deduplication on organization_id + source + source_external_id
        if gen.source_external_id:
            existing = db.execute(
                select(Lead).where(
                    Lead.organization_id == current_org.id,
                    Lead.source == gen.source,
                    Lead.source_external_id == gen.source_external_id,
                )
            ).scalar_one_or_none()
            if existing:
                skipped_count += 1
                continue

        # 3. Check whether an existing CRM contact represents the same person
        linked_contact_id = None
        linked_company_id = None
        if norm_email:
            existing_contact = db.execute(
                select(Contact).where(
                    Contact.organization_id == current_org.id,
                    func.lower(Contact.email) == norm_email,
                )
            ).scalar_one_or_none()
            if existing_contact:
                linked_contact_id = existing_contact.id
                linked_company_id = existing_contact.company_id

        score, temp, reason = calculate_lead_score(gen, icp)

        new_lead = Lead(
            organization_id=current_org.id,
            icp_id=icp.id,
            contact_id=linked_contact_id,
            company_id=linked_company_id,
            source=gen.source,
            source_external_id=gen.source_external_id,
            company_name=gen.company_name,
            company_domain=norm_domain,
            industry=gen.industry,
            employee_count_range=gen.employee_count_range,
            city=gen.city,
            country=gen.country,
            first_name=gen.first_name,
            last_name=gen.last_name,
            email=norm_email or gen.email,
            phone=gen.phone,
            job_title=gen.job_title,
            qualification_status="new",
            lead_temperature=temp,
            lead_score=score,
            qualification_reason=reason,
            status="new",
        )
        db.add(new_lead)
        created_leads.append(new_lead)

    db.commit()
    for l in created_leads:
        db.refresh(l)

    return {
        "created_count": len(created_leads),
        "skipped_count": skipped_count,
        "leads": created_leads,
    }


def list_leads(
    db: Session,
    current_org: Organization,
    page: int = 1,
    page_size: int = 50,
    icp_id: Optional[uuid.UUID] = None,
    qualification_status: Optional[str] = None,
    lead_temperature: Optional[str] = None,
    status_filter: Optional[str] = None,
    source: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    industry: Optional[str] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    search: Optional[str] = None,
    exclude_test: bool = True,
) -> Tuple[List[Lead], int]:
    """List and filter leads with strict tenant isolation."""
    query = select(Lead).where(Lead.organization_id == current_org.id)

    if exclude_test and not search:
        query = query.where(
            Lead.source != "retell_voice_call",
            or_(
                Lead.email.is_(None),
                ~Lead.email.in_(["test@example.com"]),
            ),
        )

    if icp_id is not None:
        query = query.where(Lead.icp_id == icp_id)
    if qualification_status:
        query = query.where(Lead.qualification_status == qualification_status)
    if lead_temperature:
        query = query.where(Lead.lead_temperature == lead_temperature)
    if status_filter:
        query = query.where(Lead.status == status_filter)
    if source:
        query = query.where(Lead.source == source)
    if min_score is not None:
        query = query.where(Lead.lead_score >= min_score)
    if max_score is not None:
        query = query.where(Lead.lead_score <= max_score)
    if industry:
        query = query.where(Lead.industry.ilike(f"%{industry}%"))
    if country:
        query = query.where(Lead.country.ilike(f"%{country}%"))
    if city:
        query = query.where(Lead.city.ilike(f"%{city}%"))
    if search:
        search_pattern = f"%{search}%"
        full_name_lead = func.concat(Lead.first_name, " ", Lead.last_name)
        query = query.where(
            or_(
                Lead.company_name.ilike(search_pattern),
                Lead.company_domain.ilike(search_pattern),
                Lead.first_name.ilike(search_pattern),
                Lead.last_name.ilike(search_pattern),
                full_name_lead.ilike(search_pattern),
                Lead.email.ilike(search_pattern),
                Lead.job_title.ilike(search_pattern),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(query.subquery())
    total = db.execute(count_stmt).scalar_one()

    # Pagination & ordering
    offset = (page - 1) * page_size
    items_stmt = query.order_by(Lead.created_at.desc()).offset(offset).limit(page_size)
    leads = list(db.execute(items_stmt).scalars().all())

    return leads, total


def create_lead(
    db: Session,
    current_org: Organization,
    data: LeadCreate,
) -> Lead:
    """Create a manual lead record scoped to the tenant organization with duplicate check and CRM linkage."""
    norm_email = normalize_email(data.email)
    norm_domain = normalize_domain(data.company_domain)
    if not norm_domain and norm_email and "@" in norm_email:
        norm_domain = normalize_domain(norm_email.split("@")[1])

    if norm_email:
        query = db.query(Lead).filter(
            Lead.organization_id == current_org.id,
            func.lower(Lead.email) == norm_email,
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        existing_lead = query.first()
        if existing_lead:
            raise DuplicateLeadError(
                f"Lead with email '{norm_email}' already exists in this organization."
            )

    # Parse first and last names cleanly
    raw_first = data.first_name.strip() if data.first_name else ""
    raw_last = data.last_name.strip() if data.last_name else ""
    if not raw_last and " " in raw_first:
        parsed_first, parsed_last = [p.strip() for p in raw_first.split(" ", 1)]
    else:
        parsed_first = raw_first or "Unknown"
        parsed_last = raw_last or ""

    # Check whether an existing CRM contact represents the same person; create or associate
    linked_contact_id = None
    linked_company_id = None
    existing_contact = None
    if norm_email:
        existing_contact = db.query(Contact).filter(
            Contact.organization_id == current_org.id,
            func.lower(Contact.email) == norm_email,
        ).first()
        if existing_contact:
            linked_contact_id = existing_contact.id
            linked_company_id = existing_contact.company_id

    if not existing_contact:
        # Resolve or create CRM Company
        company = None
        if norm_domain:
            company = db.query(Company).filter(
                Company.organization_id == current_org.id,
                func.lower(Company.domain) == norm_domain,
            ).first()
        if not company and data.company_name and data.company_name.strip():
            company = db.query(Company).filter(
                Company.organization_id == current_org.id,
                func.lower(Company.name) == data.company_name.strip().lower(),
            ).first()
        if not company and data.company_name and data.company_name.strip():
            company = Company(
                organization_id=current_org.id,
                name=data.company_name.strip(),
                domain=norm_domain,
                industry=data.industry.strip() if data.industry else None,
                employee_count_range=data.employee_count_range.strip() if data.employee_count_range else None,
                city=data.city.strip() if data.city else None,
                country=data.country.strip() if data.country else None,
            )
            db.add(company)
            db.flush()

        # Create CRM Contact even when email is initially omitted
        new_contact = Contact(
            id=uuid.uuid4(),
            organization_id=current_org.id,
            company_id=company.id if company else None,
            first_name=parsed_first,
            last_name=parsed_last,
            email=norm_email,
            phone=data.phone.strip() if data.phone else None,
            job_title=data.job_title.strip() if data.job_title else None,
            lead_status="new",
        )
        if hasattr(new_contact, "linkedin_profile_url") and data.linkedin_profile_url:
            new_contact.linkedin_profile_url = data.linkedin_profile_url
        db.add(new_contact)
        try:
            db.flush()
            linked_contact_id = new_contact.id
            linked_company_id = company.id if company else None
        except IntegrityError:
            # Concurrent transaction already created contact
            db.rollback()
            if norm_email:
                existing_contact = db.query(Contact).filter(
                    Contact.organization_id == current_org.id,
                    func.lower(Contact.email) == norm_email,
                ).first()
                if existing_contact:
                    linked_contact_id = existing_contact.id
                    linked_company_id = existing_contact.company_id

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=current_org.id,
        contact_id=linked_contact_id,
        company_id=linked_company_id,
        first_name=parsed_first if parsed_first != "Unknown" else (raw_first or None),
        last_name=parsed_last if parsed_last else None,
        email=norm_email or (data.email.strip().lower() if data.email else None),
        phone=data.phone.strip() if data.phone else None,
        job_title=data.job_title.strip() if data.job_title else None,
        company_name=data.company_name.strip(),
        company_domain=norm_domain,
        industry=data.industry.strip() if data.industry else None,
        employee_count_range=data.employee_count_range.strip() if data.employee_count_range else None,
        city=data.city.strip() if data.city else None,
        country=data.country.strip() if data.country else None,
        icp_id=data.icp_id,
        lead_temperature=data.lead_temperature or "cold",
        lead_score=data.lead_score or 0,
        source=data.source or "manual",
        qualification_status=data.qualification_status or "new",
        status=data.status or "new",
    )
    if hasattr(lead, "linkedin_profile_url") and data.linkedin_profile_url:
        lead.linkedin_profile_url = data.linkedin_profile_url
    db.add(lead)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateLeadError(
            f"Lead with email '{norm_email}' already exists in this organization."
        ) from exc
    db.refresh(lead)
    return lead



def get_lead(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
) -> Lead:
    """Retrieve single lead with tenant isolation."""
    lead = db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return lead


def delete_lead(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
) -> bool:
    """
    Safely delete a single lead record scoped to the tenant organization.
    Preserves shared CRM Contact, Company, Campaign enrollments, and audit records.
    """
    lead = get_lead(db, current_org, lead_id)
    db.delete(lead)
    db.commit()
    return True



def update_lead_qualification(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
    data: LeadQualificationUpdate,
) -> Lead:
    """Update qualification status, temperature, and notes for a lead."""
    lead = get_lead(db, current_org, lead_id)

    if data.qualification_status is not None:
        lead.qualification_status = data.qualification_status
    if data.lead_temperature is not None:
        lead.lead_temperature = data.lead_temperature
    if data.qualification_reason is not None:
        lead.qualification_reason = data.qualification_reason

    db.commit()
    db.refresh(lead)
    return lead


def bulk_update_lead_status(
    db: Session,
    current_org: Organization,
    lead_ids: List[uuid.UUID],
    status: Optional[str] = None,
    qualification_status: Optional[str] = None,
) -> Tuple[int, List[uuid.UUID]]:
    """
    Bulk update lifecycle status or qualification_status with strict tenant isolation.
    Only leads belonging to current_org are modified. Cross-tenant leads are ignored safely.
    """
    if not lead_ids:
        return 0, []

    leads = list(
        db.execute(
            select(Lead).where(
                Lead.id.in_(lead_ids),
                Lead.organization_id == current_org.id,
            )
        ).scalars().all()
    )

    updated_ids: List[uuid.UUID] = []
    for lead in leads:
        if status is not None:
            lead.status = status
        if qualification_status is not None:
            lead.qualification_status = qualification_status
        updated_ids.append(lead.id)

    db.commit()
    return len(updated_ids), updated_ids


def select_leads(
    db: Session,
    current_org: Organization,
    lead_ids: List[uuid.UUID],
) -> LeadSelectionResponse:
    """
    Select leads for future campaigns.
    Rejects disqualified/rejected leads.
    Idempotent for already-selected leads.
    """
    selected_count = 0
    already_selected_count = 0
    rejected_count = 0
    selected_ids: List[uuid.UUID] = []

    for lid in lead_ids:
        lead = db.execute(
            select(Lead).where(
                Lead.id == lid,
                Lead.organization_id == current_org.id,
            )
        ).scalar_one_or_none()

        if not lead:
            # Skip cross-tenant or missing leads safely
            continue

        if lead.status == "rejected" or lead.qualification_status == "disqualified":
            rejected_count += 1
        elif lead.status == "selected":
            already_selected_count += 1
            selected_ids.append(lead.id)
        else:
            lead.status = "selected"
            selected_count += 1
            selected_ids.append(lead.id)

    db.commit()

    return LeadSelectionResponse(
        selected_count=selected_count,
        already_selected_count=already_selected_count,
        rejected_count=rejected_count,
        selected_ids=selected_ids,
    )


def convert_lead_to_crm(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
) -> LeadConversionResponse:
    """
    Convert a Lead into CRM Company and Contact records.
    Deduplicates Company by domain / name and Contact by email within current organization.
    Tenant-isolated.
    """
    lead = get_lead(db, current_org, lead_id)

    # 1. Company resolution / reuse
    company: Optional[Company] = None
    company_created = False
    norm_lead_domain = normalize_domain(lead.company_domain)

    if norm_lead_domain:
        company = db.execute(
            select(Company).where(
                Company.organization_id == current_org.id,
                func.lower(Company.domain) == norm_lead_domain,
            )
        ).scalar_one_or_none()

    # Per requirement: Do not treat similar company names as conclusive proof of identity.
    # If no company with matching normalized domain exists, create a new company record.
    if not company:
        company = Company(
            organization_id=current_org.id,
            name=lead.company_name,
            domain=norm_lead_domain,
            industry=lead.industry,
            employee_count_range=lead.employee_count_range,
            city=lead.city,
            country=lead.country,
        )
        db.add(company)
        db.flush()
        company_created = True

    # 2. Contact resolution / reuse
    contact: Optional[Contact] = None
    contact_created = False
    norm_lead_email = normalize_email(lead.email)

    if norm_lead_email:
        contact = db.execute(
            select(Contact).where(
                Contact.organization_id == current_org.id,
                func.lower(Contact.email) == norm_lead_email,
            )
        ).scalar_one_or_none()

        if not contact:
            raw_first = lead.first_name or ""
            raw_last = lead.last_name or ""
            if not raw_last and " " in raw_first:
                first_name, last_name = [p.strip() for p in raw_first.split(" ", 1)]
            else:
                first_name = raw_first or "Unknown"
                last_name = raw_last or ""
            contact_kwargs = {
                "organization_id": current_org.id,
                "company_id": company.id if company else None,
                "first_name": first_name,
                "last_name": last_name,
                "email": norm_lead_email,
                "phone": lead.phone,
                "job_title": lead.job_title,
                "lead_status": "qualified" if lead.qualification_status == "qualified" else "new",
            }
            if hasattr(Contact, "address_line_1") and hasattr(lead, "address_line_1"):
                contact_kwargs["address_line_1"] = getattr(lead, "address_line_1", None)
            if hasattr(Contact, "address_line_2") and hasattr(lead, "address_line_2"):
                contact_kwargs["address_line_2"] = getattr(lead, "address_line_2", None)
            if hasattr(Contact, "city") and hasattr(lead, "city"):
                contact_kwargs["city"] = getattr(lead, "city", None)
            if hasattr(Contact, "state") and hasattr(lead, "state"):
                contact_kwargs["state"] = getattr(lead, "state", None)
            if hasattr(Contact, "postal_code") and hasattr(lead, "postal_code"):
                contact_kwargs["postal_code"] = getattr(lead, "postal_code", None)
            if hasattr(Contact, "country") and hasattr(lead, "country"):
                contact_kwargs["country"] = getattr(lead, "country", None) or "US"

            if hasattr(Contact, "linkedin_profile_url") and getattr(lead, "linkedin_profile_url", None):
                contact_kwargs["linkedin_profile_url"] = lead.linkedin_profile_url
            contact = Contact(**contact_kwargs)
            db.add(contact)
            db.flush()
            contact_created = True

    # 3. Associate CRM entities with Lead record and update status
    lead.company_id = company.id if company else None
    lead.contact_id = contact.id if contact else None
    lead.status = "converted"

    db.commit()
    db.refresh(lead)

    return LeadConversionResponse(
        lead_id=lead.id,
        company_id=company.id,
        contact_id=contact.id if contact else None,
        company_created=company_created,
        contact_created=contact_created,
        status=lead.status,
    )


def import_leads(
    db: Session,
    current_org: Organization,
    rows: List[LeadImportRow],
) -> LeadImportResponse:
    """
    Import a batch of lead rows scoped to the current tenant organization.
    Skips rows with duplicate emails (both in-batch and against existing DB leads).
    Preserves existing records without overwriting.
    """
    imported_ids: List[uuid.UUID] = []
    skipped_duplicate_count = 0
    failed_count = 0
    errors: List[str] = []

    seen_emails_in_batch: set[str] = set()

    for idx, row in enumerate(rows, start=1):
        company_name = (row.company_name or "").strip()
        first_name = (row.first_name or "").strip() or None
        last_name = (row.last_name or "").strip() or None
        raw_email = (row.email or "").strip().lower() or None

        if not company_name:
            if raw_email and "@" in raw_email:
                domain_part = raw_email.split("@")[1].split(".")[0].capitalize()
                company_name = domain_part or "Prospect Company"
            elif first_name:
                company_name = f"{first_name}'s Company"
            else:
                errors.append(f"Row {idx}: Missing company name or identifying details.")
                failed_count += 1
                continue

        norm_email = normalize_email(raw_email) if raw_email else None
        if raw_email:
            if not norm_email or "@" not in norm_email or "." not in norm_email.split("@")[-1] or not norm_email.split("@")[0]:
                errors.append(f"Row {idx}: Invalid email address '{raw_email}'.")
                failed_count += 1
                continue

        # In-batch duplicate check
        if norm_email:
            if norm_email in seen_emails_in_batch:
                skipped_duplicate_count += 1
                continue
            seen_emails_in_batch.add(norm_email)

            # DB duplicate check within tenant
            existing_lead = db.query(Lead).filter(
                Lead.organization_id == current_org.id,
                func.lower(Lead.email) == norm_email,
            ).first()
            if existing_lead:
                skipped_duplicate_count += 1
                continue

        # Check if a CRM Contact already exists for this email
        linked_contact_id = None
        linked_company_id = None
        if norm_email:
            existing_contact = db.query(Contact).filter(
                Contact.organization_id == current_org.id,
                func.lower(Contact.email) == norm_email,
            ).first()
            if existing_contact:
                linked_contact_id = existing_contact.id
                linked_company_id = existing_contact.company_id

        lead = Lead(
            id=uuid.uuid4(),
            organization_id=current_org.id,
            contact_id=linked_contact_id,
            company_id=linked_company_id,
            first_name=first_name,
            last_name=last_name,
            email=norm_email,
            phone=(row.phone or "").strip() or None,
            job_title=(row.job_title or "").strip() or None,
            company_name=company_name,
            company_domain=norm_email.split("@")[1] if norm_email and "@" in norm_email else None,
            industry=(row.industry or "").strip() or None,
            city=(row.city or "").strip() or None,
            country=(row.country or "").strip() or None,
            address_line_1=(row.address_line_1 or "").strip() or None if hasattr(Lead, "address_line_1") else None,
            address_line_2=(row.address_line_2 or "").strip() or None if hasattr(Lead, "address_line_2") else None,
            state=(row.state or "").strip() or None if hasattr(Lead, "state") else None,
            postal_code=(row.postal_code or "").strip() or None if hasattr(Lead, "postal_code") else None,
            source="csv_import",
            status="new",
            qualification_status="new",
            lead_temperature="cold",
            lead_score=0,
        )
        if hasattr(lead, "linkedin_profile_url") and getattr(row, "linkedin_profile_url", None):
            lead.linkedin_profile_url = row.linkedin_profile_url.strip() or None
            if linked_contact_id and existing_contact and not getattr(existing_contact, "linkedin_profile_url", None):
                existing_contact.linkedin_profile_url = lead.linkedin_profile_url
        db.add(lead)
        db.flush()
        imported_ids.append(lead.id)

    db.commit()

    return LeadImportResponse(
        imported_count=len(imported_ids),
        skipped_duplicate_count=skipped_duplicate_count,
        failed_count=failed_count,
        imported_ids=imported_ids,
        errors=errors,
    )

def update_lead(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
    data: LeadUpdate,
) -> Lead:
    """Update an existing Lead scoped to the tenant organization and sync Contact snapshot."""
    lead = get_lead(db, current_org, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )

    update_dict = data.model_dump(exclude_unset=True)
    if not update_dict:
        return lead

    # Update Lead fields
    for field, val in update_dict.items():
        if field == "email" and val:
            val = normalize_email(val)
        if field == "company_domain" and val:
            val = normalize_domain(val)
        if hasattr(lead, field):
            setattr(lead, field, val)

    # If lead doesn't have a linked company yet, resolve or create one
    if not lead.company_id and lead.company_name:
        company = (
            db.query(Company)
            .filter(
                Company.organization_id == current_org.id,
                func.lower(Company.name) == lead.company_name.strip().lower(),
            )
            .first()
        )
        if not company:
            company = Company(
                organization_id=current_org.id,
                name=lead.company_name.strip(),
                domain=lead.company_domain,
                industry=lead.industry,
                city=lead.city,
                country=lead.country,
            )
            db.add(company)
            db.flush()
        lead.company_id = company.id

    # If lead doesn't have a linked contact yet, create one if identifying details exist
    if not lead.contact_id and (lead.first_name or lead.last_name or lead.email or lead.phone):
        contact = Contact(
            id=uuid.uuid4(),
            organization_id=current_org.id,
            company_id=lead.company_id,
            first_name=lead.first_name or "",
            last_name=lead.last_name or "",
            email=lead.email,
            phone=lead.phone,
            job_title=lead.job_title,
            lead_status="new",
        )
        if hasattr(contact, "linkedin_profile_url") and getattr(lead, "linkedin_profile_url", None):
            contact.linkedin_profile_url = lead.linkedin_profile_url
        db.add(contact)
        db.flush()
        lead.contact_id = contact.id
    elif lead.contact_id:
        contact = (
            db.query(Contact)
            .filter(Contact.id == lead.contact_id, Contact.organization_id == current_org.id)
            .first()
        )
        if contact:
            if "linkedin_profile_url" in update_dict:
                contact.linkedin_profile_url = update_dict["linkedin_profile_url"]
            if "first_name" in update_dict:
                contact.first_name = update_dict["first_name"] or ""
            if "last_name" in update_dict:
                contact.last_name = update_dict["last_name"] or ""
            if "phone" in update_dict:
                contact.phone = update_dict["phone"]
            if "job_title" in update_dict:
                contact.job_title = update_dict["job_title"]
            if "email" in update_dict:
                contact.email = update_dict["email"]
            if lead.company_id and not contact.company_id:
                contact.company_id = lead.company_id

    db.commit()
    db.refresh(lead)
    return lead

