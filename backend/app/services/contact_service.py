"""Contact domain service managing tenant-scoped operations and cross-tenant validation."""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.normalization import normalize_email
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.schemas.contact import ContactCreate, ContactUpdate

logger = logging.getLogger(__name__)


class ContactServiceError(Exception):
    """Base exception for contact service operations."""
    pass


class InvalidCompanyReferenceError(ContactServiceError):
    """Raised when an associated company is not found or belongs to another tenant."""
    pass


class DuplicateContactError(ContactServiceError):
    """Raised when a contact with the same email already exists in the organization."""
    pass


def _is_duplicate_email_error(exc: IntegrityError) -> bool:
    """Determine whether an IntegrityError was caused by the organization email unique constraint.

    Excludes foreign-key, not-null, check, and other unique constraint violations (e.g. hubspot_id).
    """
    err_str = str(exc).lower()

    # Explicit constraint name from PostgreSQL
    if "uq_contacts_org_lower_email" in err_str:
        return True

    # General unique constraint violation mentioning email across drivers (e.g., SQLite in tests)
    is_unique = (
        "unique constraint" in err_str
        or "unique violation" in err_str
        or "unique constraint failed" in err_str
        or "duplicate key" in err_str
    )
    if is_unique and "email" in err_str and "hubspot_id" not in err_str:
        return True

    return False


def _verify_tenant_company(db: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> Company:
    """Verify company exists and belongs strictly to the requesting organization."""
    company = (
        db.query(Company)
        .filter(Company.id == company_id, Company.organization_id == org_id)
        .first()
    )
    if not company:
        raise InvalidCompanyReferenceError(
            f"Company '{company_id}' not found in the current organization."
        )
    return company


def create_contact(
    db: Session,
    org_id: uuid.UUID,
    data: ContactCreate,
) -> Contact:
    """Create a new contact prospect strictly scoped to the tenant organization."""
    # Cross-tenant company validation
    if data.company_id:
        _verify_tenant_company(db, org_id, data.company_id)

    norm_email = normalize_email(data.email)
    if norm_email:
        query = db.query(Contact).filter(
            Contact.organization_id == org_id,
            func.lower(Contact.email) == norm_email,
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        existing = query.first()
        if existing:
            raise DuplicateContactError(
                f"Contact with email '{norm_email}' already exists in this organization."
            )

    contact = Contact(
        organization_id=org_id,
        company_id=data.company_id,
        email=norm_email or data.email.strip().lower(),
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        phone=data.phone.strip() if data.phone else None,
        job_title=data.job_title.strip() if data.job_title else None,
        lead_status=data.lead_status or "new",
    )
    db.add(contact)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_email_error(exc):
            raise DuplicateContactError(
                f"Contact with email '{norm_email}' already exists in this organization."
            ) from exc
        raise
    db.refresh(contact)
    return contact


def get_contact(
    db: Session,
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> Optional[Contact]:
    """Retrieve a contact by ID strictly scoped to the tenant organization."""
    return (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.organization_id == org_id)
        .first()
    )


def list_contacts(
    db: Session,
    org_id: uuid.UUID,
    search: Optional[str] = None,
    lead_status: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Contact], int]:
    """
    List contacts for a tenant with optional filtering by search (first_name/last_name/full_name/email/company),
    lead_status, and company_id. Returns (contacts, total_count).
    """
    query = db.query(Contact).filter(Contact.organization_id == org_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        full_name_expr = func.concat(Contact.first_name, " ", Contact.last_name)
        lead_contact_ids_subquery = (
            db.query(Lead.contact_id)
            .filter(
                Lead.organization_id == org_id,
                Lead.contact_id.isnot(None),
                Lead.company_name.ilike(term),
            )
        )
        query = query.outerjoin(Company, Contact.company_id == Company.id).filter(
            or_(
                Contact.first_name.ilike(term),
                Contact.last_name.ilike(term),
                full_name_expr.ilike(term),
                Contact.email.ilike(term),
                Company.name.ilike(term),
                Contact.id.in_(lead_contact_ids_subquery),
            )
        )

    if lead_status and lead_status.strip():
        query = query.filter(Contact.lead_status == lead_status.strip().lower())

    if company_id:
        query = query.filter(Contact.company_id == company_id)

    total = query.count()
    contacts = (
        query.options(joinedload(Contact.company))
        .order_by(Contact.created_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 500))
        .all()
    )
    return contacts, total


def update_contact(
    db: Session,
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
    data: ContactUpdate,
) -> Optional[Contact]:
    """Partially update a contact strictly scoped to the tenant organization."""
    contact = get_contact(db, org_id, contact_id)
    if not contact:
        return None

    update_dict = data.model_dump(exclude_unset=True)

    # Validate company reference if being modified
    if "company_id" in update_dict and update_dict["company_id"] is not None:
        _verify_tenant_company(db, org_id, update_dict["company_id"])

    # If email is being updated, normalize and perform organization-scoped duplicate pre-check
    target_email = None
    if "email" in update_dict and update_dict["email"] is not None:
        norm_email = normalize_email(str(update_dict["email"]))
        target_email = norm_email or str(update_dict["email"]).strip().lower()
        update_dict["email"] = target_email

        if target_email:
            query = db.query(Contact).filter(
                Contact.organization_id == org_id,
                func.lower(Contact.email) == target_email,
                Contact.id != contact_id,
            )
            if db.bind and db.bind.dialect.name == "postgresql":
                query = query.with_for_update()
            existing = query.first()
            if existing:
                raise DuplicateContactError(
                    f"Contact with email '{target_email}' already exists in this organization."
                )

    for field, val in update_dict.items():
        if field == "email":
            setattr(contact, field, target_email)
        elif isinstance(val, str):
            setattr(contact, field, val.strip())
        else:
            setattr(contact, field, val)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_email_error(exc):
            raise DuplicateContactError(
                f"Contact with email '{target_email or contact.email}' already exists in this organization."
            ) from exc
        raise
    db.refresh(contact)
    return contact


def delete_contact(
    db: Session,
    org_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> bool:
    """Delete a contact strictly scoped to the tenant organization."""
    contact = get_contact(db, org_id, contact_id)
    if not contact:
        return False

    db.delete(contact)
    db.commit()
    return True
