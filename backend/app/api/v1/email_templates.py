"""API router for reusable email templates."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.email_template import (
    AIEmailGenerateRequest,
    AIEmailGenerateResponse,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
)
from app.services.campaign_steps.ai_template_service import (
    AITemplateConfigurationError,
    AITemplateGenerationError,
    generate_email_template,
)
from app.services import email_template_service
from app.services.email_template_service import EmailTemplateNotFoundError

router = APIRouter(prefix="/templates", tags=["Email Templates"])


@router.post(
    "",
    response_model=EmailTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a reusable email template",
    description="Saves an email template scoped strictly to the authenticated organization.",
)
async def create_template_endpoint(
    data: EmailTemplateCreate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> EmailTemplateResponse:
    template = email_template_service.create_template(db, current_org.id, data)
    return EmailTemplateResponse.model_validate(template)


@router.post(
    "/generate-ai",
    response_model=AIEmailGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate email template with AI (AWS Bedrock)",
    description="Uses AWS Bedrock Claude Sonnet 4.5 to generate email subject and body content.",
)
async def generate_ai_email_template_endpoint(
    payload: AIEmailGenerateRequest,
    current_org: Organization = Depends(get_current_organization),
) -> AIEmailGenerateResponse:
    try:
        return generate_email_template(payload)
    except AITemplateConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except AITemplateGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=List[EmailTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="List reusable email templates",
    description="Returns templates belonging to the authenticated organization with search and category filtering.",
)
async def list_templates_endpoint(
    response: Response,
    category: Optional[str] = Query(None, description="Filter by category (e.g. outbound, follow_up)"),
    search: Optional[str] = Query(None, description="Search by name, subject, or description"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> List[EmailTemplateResponse]:
    templates, total = email_template_service.list_templates(
        db,
        current_org.id,
        category=category,
        search=search,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total)
    return [EmailTemplateResponse.model_validate(t) for t in templates]


@router.get(
    "/{template_id}",
    response_model=EmailTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get an email template by ID",
    description="Retrieves a specific email template belonging to the authenticated organization.",
)
async def get_template_endpoint(
    template_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> EmailTemplateResponse:
    template = email_template_service.get_template(db, current_org.id, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found.",
        )
    return EmailTemplateResponse.model_validate(template)


@router.patch(
    "/{template_id}",
    response_model=EmailTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an email template",
    description="Updates fields on a saved template within the organization.",
)
async def update_template_endpoint(
    template_id: uuid.UUID,
    data: EmailTemplateUpdate,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> EmailTemplateResponse:
    try:
        template = email_template_service.update_template(db, current_org.id, template_id, data)
        return EmailTemplateResponse.model_validate(template)
    except EmailTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email template",
    description="Deletes a saved email template within the organization.",
)
async def delete_template_endpoint(
    template_id: uuid.UUID,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> None:
    deleted = email_template_service.delete_template(db, current_org.id, template_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found.",
        )
