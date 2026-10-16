"""Company domain service managing tenant-scoped operations."""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.normalization import normalize_domain
from app.models.crm import Company
from app.schemas.company import CompanyCreate, CompanyUpdate

logger = logging.getLogger(__name__)


class CompanyServiceError(Exception):
    """Base exception for company service operations."""
    pass


class DuplicateCompanyError(CompanyServiceError):
    """Raised when a company with the same domain already exists in the organization."""
    pass


def create_company(
    db: Session,
    org_id: uuid.UUID,
    data: CompanyCreate,
) -> Company:
    """Create a new company belonging to the specified organization."""
    norm_domain = normalize_domain(data.domain)
    if norm_domain:
        query = db.query(Company).filter(
            Company.organization_id == org_id,
            func.lower(Company.domain) == norm_domain,
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        existing = query.first()
        if existing:
            raise DuplicateCompanyError(
                f"Company with domain '{norm_domain}' already exists in this organization."
            )

    company = Company(
        organization_id=org_id,
        name=data.name.strip(),
        domain=norm_domain,
        industry=data.industry.strip() if data.industry else None,
        employee_count_range=data.employee_count_range.strip() if data.employee_count_range else None,
        city=data.city.strip() if data.city else None,
        country=data.country.strip() if data.country else None,
    )
    db.add(company)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCompanyError(
            f"Company with domain '{norm_domain}' already exists in this organization."
        ) from exc
    db.refresh(company)
    return company


def get_company(
    db: Session,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
) -> Optional[Company]:
    """Retrieve a company by ID strictly scoped to the tenant organization."""
    return (
        db.query(Company)
        .filter(Company.id == company_id, Company.organization_id == org_id)
        .first()
    )


def list_companies(
    db: Session,
    org_id: uuid.UUID,
    search: Optional[str] = None,
    industry: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Company], int]:
    """
    List companies for a tenant with optional filtering by name search and industry.
    Returns (companies, total_count).
    """
    query = db.query(Company).filter(Company.organization_id == org_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(Company.name.ilike(term))

    if industry and industry.strip():
        query = query.filter(Company.industry.ilike(f"%{industry.strip()}%"))

    total = query.count()
    companies = (
        query.order_by(Company.created_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 500))
        .all()
    )
    return companies, total


def update_company(
    db: Session,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    data: CompanyUpdate,
) -> Optional[Company]:
    """Partially update a company strictly scoped to the tenant organization."""
    company = get_company(db, org_id, company_id)
    if not company:
        return None

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if val is not None and isinstance(val, str):
            val = val.strip()
        setattr(company, field, val)

    db.commit()
    db.refresh(company)
    return company


def delete_company(
    db: Session,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
) -> bool:
    """Delete a company strictly scoped to the tenant organization."""
    company = get_company(db, org_id, company_id)
    if not company:
        return False

    db.delete(company)
    db.commit()
    return True
