"""Ideal Customer Profile (ICP) business logic service."""
from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.icp import IdealCustomerProfile
from app.schemas.icp import IdealCustomerProfileCreate, IdealCustomerProfileUpdate


def create_icp(
    db: Session,
    organization_id: uuid.UUID,
    data: IdealCustomerProfileCreate,
) -> IdealCustomerProfile:
    """Create a new ICP record under the specified tenant organization."""
    icp = IdealCustomerProfile(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        industries=data.industries,
        company_size_min=data.company_size_min,
        company_size_max=data.company_size_max,
        countries=data.countries,
        cities=data.cities,
        company_domains=data.company_domains,
        job_titles=data.job_titles,
        seniority_levels=data.seniority_levels,
        departments=data.departments,
        technologies=data.technologies,
        keywords=data.keywords,
        is_active=data.is_active,
    )
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return icp


def get_icp(
    db: Session,
    organization_id: uuid.UUID,
    icp_id: uuid.UUID,
) -> IdealCustomerProfile:
    """Retrieve single ICP with strict tenant isolation. Returns 404 if not found or cross-tenant."""
    icp = db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.id == icp_id,
            IdealCustomerProfile.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if not icp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ideal Customer Profile not found",
        )
    return icp


def list_icps(
    db: Session,
    organization_id: uuid.UUID,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[IdealCustomerProfile], int]:
    """List ICPs belonging to the authenticated tenant organization."""
    query = select(IdealCustomerProfile).where(
        IdealCustomerProfile.organization_id == organization_id
    )
    if is_active is not None:
        query = query.where(IdealCustomerProfile.is_active == is_active)

    count_stmt = select(func.count()).select_from(query.subquery())
    total = db.execute(count_stmt).scalar_one()

    items_stmt = query.order_by(IdealCustomerProfile.created_at.desc()).offset(skip).limit(limit)
    items = list(db.execute(items_stmt).scalars().all())

    return items, total


def update_icp(
    db: Session,
    organization_id: uuid.UUID,
    icp_id: uuid.UUID,
    data: IdealCustomerProfileUpdate,
) -> IdealCustomerProfile:
    """Update an ICP record ensuring tenant isolation."""
    icp = get_icp(db, organization_id, icp_id)

    update_fields = data.model_dump(exclude_unset=True)
    for field, val in update_fields.items():
        setattr(icp, field, val)

    db.commit()
    db.refresh(icp)
    return icp


def delete_icp(
    db: Session,
    organization_id: uuid.UUID,
    icp_id: uuid.UUID,
) -> None:
    """Delete an ICP record with tenant isolation."""
    icp = get_icp(db, organization_id, icp_id)
    db.delete(icp)
    db.commit()
