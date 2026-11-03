"""LinkedIn Integration API Endpoints for OAuth 2.0 and OpenID Connect connection lifecycle."""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_organization
from app.core.config import settings
from app.core.database import get_db
from app.models.tenant import Organization, User
import uuid
from app.schemas.linkedin import (
    LinkedInAuthorizeResponse,
    LinkedInCallbackResponse,
    LinkedInCapabilitiesResponse,
    LinkedInDisconnectResponse,
    LinkedInStatusResponse,
    LinkedInAssistedQueueResponse,
    LinkedInConfirmActionRequest,
    LinkedInConfirmActionResponse,
    LinkedInUpdateProspectProfileRequest,
    LinkedInUpdateProspectProfileResponse,
)
from app.services.integrations.linkedin.client import LinkedInOAuthClient
from app.services.integrations.linkedin.service import LinkedInIntegrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/linkedin", tags=["LinkedIn Integration"])


def get_linkedin_service(db: Session = Depends(get_db)) -> LinkedInIntegrationService:
    """Dependency factory providing LinkedInIntegrationService."""
    return LinkedInIntegrationService(db=db, client=LinkedInOAuthClient())


@router.get(
    "/status",
    response_model=LinkedInStatusResponse,
    summary="Get LinkedIn account connection status",
)
def get_linkedin_status(
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInStatusResponse:
    """
    Retrieve connection status, member identity (name, email, profile photo),
    and granted scopes for the active tenant organization.
    Tokens are strictly redacted and never returned to the caller.
    """
    status_data = service.get_connection_status(org=org)
    return LinkedInStatusResponse(**status_data)


@router.get(
    "/authorize",
    response_model=LinkedInAuthorizeResponse,
    summary="Initiate LinkedIn OAuth authorization flow",
)
def authorize_linkedin(
    user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInAuthorizeResponse:
    """
    Generate a cryptographically random, replay-protected OAuth state,
    bind it to the initiating user and organization with a 15-minute TTL,
    and return the LinkedIn authorization URL.
    """
    try:
        flow_data = service.create_authorization_flow(user=user, org=org)
        return LinkedInAuthorizeResponse(**flow_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/callback",
    summary="LinkedIn OAuth authorization-code callback",
)
async def linkedin_callback(
    request: Request,
    state: str = Query(..., description="OAuth state token for replay protection and session binding"),
    code: Optional[str] = Query(None, description="Authorization code from LinkedIn"),
    error: Optional[str] = Query(None, description="Error code if authorization was denied or cancelled"),
    error_description: Optional[str] = Query(None, description="Error description from LinkedIn"),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
):
    """
    Handle the OAuth redirect callback from LinkedIn.
    Validates state replay protection, handles user cancellation, exchanges authorization code,
    verifies OpenID Connect ID token signature/claims, encrypts tokens, and stores the connection.
    Redirects web clients back to the frontend integrations screen with status query parameters.
    """
    accept_header = request.headers.get("accept", "")
    wants_json = "application/json" in accept_header and "text/html" not in accept_header

    try:
        connection = await service.handle_callback(
            state=state,
            code=code,
            error=error,
            error_description=error_description,
        )

        if wants_json:
            return LinkedInCallbackResponse(
                success=True,
                status="connected",
                member_id=connection.linkedin_member_id,
                member_name=connection.member_name,
                message="LinkedIn account successfully connected.",
            )

        # Web browser redirect to frontend integrations page
        redirect_url = f"{settings.LINKEDIN_FRONTEND_REDIRECT_URL}?linkedin=connected"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as exc:
        err_msg = str(exc)
        logger.warning("LinkedIn OAuth callback rejected: %s", err_msg)

        if wants_json:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )

        # Web browser redirect to frontend with error parameter
        redirect_url = f"{settings.LINKEDIN_FRONTEND_REDIRECT_URL}?linkedin_error={quote(err_msg)}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/disconnect",
    response_model=LinkedInDisconnectResponse,
    summary="Disconnect LinkedIn account for organization",
)
def disconnect_linkedin(
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInDisconnectResponse:
    """
    Disconnect the active LinkedIn connection for this tenant organization.
    Erases encrypted tokens, updates status to 'disconnected', and prevents further channel usage.
    """
    service.disconnect(org=org)
    return LinkedInDisconnectResponse(
        success=True,
        message="LinkedIn account disconnected successfully.",
    )


@router.get(
    "/capabilities",
    response_model=LinkedInCapabilitiesResponse,
    summary="Get detailed LinkedIn API capability matrix",
)
def get_linkedin_capabilities(
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInCapabilitiesResponse:
    """
    Evaluates granted scopes and reports official capabilities:
    profile reading (available), email reading (available), organization pages (restricted),
    and automated 1-to-1 messaging/invitations (unsupported, assisted workflow provided).
    """
    cap_data = service.get_capabilities(org=org)
    return LinkedInCapabilitiesResponse(**cap_data)


@router.get(
    "/campaigns/{campaign_id}/queue",
    response_model=LinkedInAssistedQueueResponse,
    summary="Get assisted LinkedIn outreach queue for campaign",
)
def get_linkedin_campaign_queue(
    campaign_id: uuid.UUID,
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInAssistedQueueResponse:
    """
    Returns enrolled prospects with pre-rendered, personalized copy-ready
    connection notes (<=300 chars) and follow-up messages with booking URLs.
    """
    try:
        queue_data = service.get_campaign_assisted_queue(org=org, campaign_id=campaign_id)
        return LinkedInAssistedQueueResponse(**queue_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/campaigns/{campaign_id}/confirm",
    response_model=LinkedInConfirmActionResponse,
    summary="Confirm manual LinkedIn connection request or message",
)
def confirm_linkedin_action(
    campaign_id: uuid.UUID,
    payload: LinkedInConfirmActionRequest,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInConfirmActionResponse:
    """
    Records user confirmation that a LinkedIn connection request or message was sent manually.
    Creates or updates Outreach record, updates contact progress, and logs an audit event.
    """
    try:
        res = service.confirm_assisted_action(
            user=current_user,
            org=org,
            campaign_id=campaign_id,
            campaign_contact_id=payload.campaign_contact_id,
            action_type=payload.action_type,
            notes=payload.notes,
        )
        return LinkedInConfirmActionResponse(**res)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@router.post(
    "/campaigns/{campaign_id}/prospects/{campaign_contact_id}/linkedin-url",
    response_model=LinkedInUpdateProspectProfileResponse,
    summary="Update prospect LinkedIn profile URL from assisted queue",
)
def update_prospect_linkedin_url(
    campaign_id: uuid.UUID,
    campaign_contact_id: uuid.UUID,
    payload: LinkedInUpdateProspectProfileRequest,
    org: Organization = Depends(get_current_organization),
    service: LinkedInIntegrationService = Depends(get_linkedin_service),
) -> LinkedInUpdateProspectProfileResponse:
    """
    Updates the LinkedIn profile URL for an enrolled prospect in the campaign queue.
    Syncs across CRM Contact and Lead records with tenant isolation.
    """
    try:
        res = service.update_prospect_linkedin_url(
            org=org,
            campaign_id=campaign_id,
            campaign_contact_id=campaign_contact_id,
            profile_url=payload.linkedin_profile_url,
        )
        return LinkedInUpdateProspectProfileResponse(**res)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

