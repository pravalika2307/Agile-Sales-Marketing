"""Domain service for managing reusable email templates with organization isolation."""
from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.schemas.email_template import EmailTemplateCreate, EmailTemplateUpdate


class EmailTemplateNotFoundError(Exception):
    """Raised when an email template is not found in the organization."""
    pass


def list_templates(
    db: Session,
    org_id: uuid.UUID,
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[EmailTemplate], int]:
    """
    Lists reusable email templates belonging strictly to the authenticated organization.
    Supports category filtering, name/subject search, and pagination.
    """
    try:
        query = db.query(EmailTemplate).filter(EmailTemplate.organization_id == org_id)

        if category and category.strip():
            query = query.filter(EmailTemplate.category == category.strip().lower())

        if is_active is not None:
            query = query.filter(EmailTemplate.is_active == is_active)

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            query = query.filter(
                func.lower(EmailTemplate.name).like(term)
                | func.lower(EmailTemplate.subject_template).like(term)
                | func.lower(EmailTemplate.description).like(term)
            )

        total = query.count()
        templates = (
            query.order_by(EmailTemplate.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return templates, total
    except (ProgrammingError, OperationalError):
        db.rollback()
        return [], 0


def get_template(
    db: Session,
    org_id: uuid.UUID,
    template_id: uuid.UUID,
) -> Optional[EmailTemplate]:
    """Retrieves an email template scoped strictly to the organization."""
    return (
        db.query(EmailTemplate)
        .filter(EmailTemplate.id == template_id, EmailTemplate.organization_id == org_id)
        .first()
    )


def create_template(
    db: Session,
    org_id: uuid.UUID,
    data: EmailTemplateCreate,
) -> EmailTemplate:
    """Creates a new reusable email template belonging to the organization."""
    template = EmailTemplate(
        organization_id=org_id,
        name=data.name.strip(),
        description=data.description.strip() if data.description else None,
        category=(data.category or "outbound").strip().lower(),
        subject_template=data.subject_template.strip(),
        body_template=data.body_template.strip(),
        is_active=data.is_active,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(
    db: Session,
    org_id: uuid.UUID,
    template_id: uuid.UUID,
    data: EmailTemplateUpdate,
) -> EmailTemplate:
    """Updates an existing email template, strictly enforcing tenant boundaries."""
    template = get_template(db, org_id, template_id)
    if not template:
        raise EmailTemplateNotFoundError(f"Template '{template_id}' not found.")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        if val is not None and isinstance(val, str):
            val = val.strip()
        setattr(template, field, val)

    db.commit()
    db.refresh(template)
    return template


def delete_template(
    db: Session,
    org_id: uuid.UUID,
    template_id: uuid.UUID,
) -> bool:
    """Deletes an email template, strictly enforcing tenant boundaries."""
    template = get_template(db, org_id, template_id)
    if not template:
        return False

    db.delete(template)
    db.commit()
    return True
