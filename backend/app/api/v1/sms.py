"""SMS API endpoints: Configuration status, phone validation, preview/segments, and Twilio delivery webhooks."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.api.deps import get_current_organization
from app.core.config import settings
from app.core.database import get_db
from app.models.crm import Contact
from app.models.lead import Lead
from app.models.tenant import Organization
from app.services.organization_config import get_organization_booking_url
from app.services.sms.base import calculate_sms_segments, normalize_phone_number
from app.services.sms.service import (
    check_sms_consent,
    get_sms_provider,
    preview_sms_step,
    validate_recipient_phone,
)
from app.services.sms.webhook import (
    WebhookSignatureVerificationError,
    handle_twilio_webhook,
    process_twilio_delivery_callback,
    process_twilio_inbound_message,
)

router = APIRouter(prefix="/sms", tags=["SMS"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class SMSConfigStatusResponse(BaseModel):
    configured: bool
    enabled: bool
    live_sending_allowed: bool
    provider: str
    from_number_configured: bool
    mode: str
    message: str


class PhoneValidationRequest(BaseModel):
    phone: str = Field(..., description="Phone number to validate and normalize to E.164")
    default_country_code: str = Field("1", description="Default country code if unprovided")


class PhoneValidationResponse(BaseModel):
    is_valid: bool
    raw_phone: str
    formatted_phone: str
    error_message: Optional[str] = None


class SMSPreviewRequest(BaseModel):
    body: str = Field(..., description="Template body with placeholders")
    contact_id: Optional[uuid.UUID] = Field(None, description="Optional contact ID to evaluate")
    lead_id: Optional[uuid.UUID] = Field(None, description="Optional lead ID to evaluate")
    sample_data: Optional[Dict[str, Any]] = Field(None, description="Fallback sample contact data")


class SMSPreviewResponse(BaseModel):
    rendered_body: str
    character_count: int
    segment_count: int
    encoding: str
    remaining_in_segment: int
    max_per_segment: int
    unresolved_placeholders: List[str]
    phone_validation: PhoneValidationResponse
    consent_eligible: bool
    consent_reason: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/config-status",
    response_model=SMSConfigStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check SMS integration configuration status",
    description="Inspects provider configuration and fail-closed safety state without exposing credentials.",
)
async def get_sms_config_status(
    current_org: Organization = Depends(get_current_organization),
) -> SMSConfigStatusResponse:
    provider = get_sms_provider()
    is_configured = settings.is_twilio_configured
    live_allowed = settings.is_twilio_live_sending_allowed

    mode_description = (
        "Live Twilio Delivery (Authorized)"
        if live_allowed
        else "Safe Mock Mode (No External Twilio Requests)"
    )
    status_message = (
        "Twilio credentials configured and active. Live sending is disabled by default for safety."
        if is_configured
        else "Twilio credentials are not fully configured. Safe mock provider active."
    )

    return SMSConfigStatusResponse(
        configured=is_configured,
        enabled=settings.TWILIO_ENABLED,
        live_sending_allowed=live_allowed,
        provider=provider.provider_name,
        from_number_configured=bool(settings.TWILIO_FROM_NUMBER and settings.TWILIO_FROM_NUMBER.strip()),
        mode=mode_description,
        message=status_message,
    )


@router.post(
    "/validate-phone",
    response_model=PhoneValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate and normalize phone number",
    description="Checks E.164 compliance and standardizes telephone formatting.",
)
async def validate_phone_endpoint(
    data: PhoneValidationRequest,
    current_org: Organization = Depends(get_current_organization),
) -> PhoneValidationResponse:
    res = validate_recipient_phone(data.phone)
    return PhoneValidationResponse(**res)


@router.post(
    "/preview",
    response_model=SMSPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview SMS template personalization and segment metrics",
    description="Renders placeholders, evaluates contact consent, and calculates GSM-7 vs Unicode segments.",
)
async def preview_sms_endpoint(
    data: SMSPreviewRequest,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> SMSPreviewResponse:
    contact_data: Dict[str, Any] = {}
    contact_obj = None

    if data.contact_id:
        contact_obj = (
            db.query(Contact)
            .filter(Contact.id == data.contact_id, Contact.organization_id == current_org.id)
            .first()
        )
        if not contact_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact not found: {data.contact_id}",
            )
        contact_data = {
            "first_name": contact_obj.first_name,
            "last_name": contact_obj.last_name,
            "full_name": f"{contact_obj.first_name} {contact_obj.last_name}".strip(),
            "phone": contact_obj.phone or "",
            "email": contact_obj.email or "",
            "job_title": contact_obj.job_title or "",
            "company_name": contact_obj.company.name if contact_obj.company else "",
            "company": contact_obj.company.name if contact_obj.company else "",
        }
    elif data.lead_id:
        lead_obj = (
            db.query(Lead)
            .filter(Lead.id == data.lead_id, Lead.organization_id == current_org.id)
            .first()
        )
        if not lead_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead not found: {data.lead_id}",
            )
        contact_obj = lead_obj
        contact_data = {
            "first_name": lead_obj.first_name or "",
            "last_name": lead_obj.last_name or "",
            "full_name": f"{lead_obj.first_name or ''} {lead_obj.last_name or ''}".strip(),
            "phone": lead_obj.phone or "",
            "email": lead_obj.email or "",
            "job_title": lead_obj.job_title or "",
            "company_name": lead_obj.company_name or "",
            "company": lead_obj.company_name or "",
        }

    if not contact_data and data.sample_data:
        contact_data = data.sample_data
    elif not contact_data:
        contact_data = {
            "first_name": "Alex",
            "last_name": "Morgan",
            "full_name": "Alex Morgan",
            "phone": "+16416818482",
            "email": "alex.morgan@acmecorp.com",
            "company": "Acme Corp",
            "company_name": "Acme Corp",
            "job_title": "VP of Revenue Operations",
        }

    # Add namespaced keys
    namespaced: Dict[str, Any] = dict(contact_data)
    for k, v in list(contact_data.items()):
        namespaced[f"contact.{k}"] = v

    booking_url = get_organization_booking_url(db, current_org.id)
    preview = preview_sms_step(
        template_body=data.body,
        contact_data=namespaced,
        booking_url=booking_url,
    )

    consent_eligible = True
    consent_reason = None
    if contact_obj:
        consent_eligible, consent_reason = check_sms_consent(contact_obj)

    return SMSPreviewResponse(
        rendered_body=preview["rendered_body"],
        character_count=preview["character_count"],
        segment_count=preview["segment_count"],
        encoding=preview["encoding"],
        remaining_in_segment=preview["remaining_in_segment"],
        max_per_segment=preview["max_per_segment"],
        unresolved_placeholders=preview["unresolved_placeholders"],
        phone_validation=PhoneValidationResponse(**preview["phone_validation"]),
        consent_eligible=consent_eligible,
        consent_reason=consent_reason,
    )


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Twilio messaging webhook (delivery callbacks & inbound SMS)",
    description="Unified webhook endpoint for Twilio SMS delivery callbacks and inbound messages. Enforces cryptographic X-Twilio-Signature validation in all environments.",
)
async def twilio_webhook_callback(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    # Extract form/body data sent by Twilio without external multipart dependency
    from urllib.parse import parse_qs
    import json

    body_bytes = await request.body()
    content_type = request.headers.get("content-type", "").lower()
    payload: Dict[str, Any] = {}

    if "application/json" in content_type:
        try:
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            payload = {}
    else:
        try:
            body_str = body_bytes.decode("utf-8", errors="replace")
            parsed_dict = parse_qs(body_str, keep_blank_values=True)
            payload = {k: v[0] if len(v) == 1 else v for k, v in parsed_dict.items()}
        except Exception:
            payload = {}

    # Determine externally visible request URL (honoring reverse proxy/tunnel headers)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    path = request.url.path
    query = request.url.query
    request_url = f"{proto}://{host}{path}" + (f"?{query}" if query else "")

    # Consistently enforce signature verification when Twilio auth token is configured
    enforce_signature = bool(settings.TWILIO_AUTH_TOKEN and settings.TWILIO_AUTH_TOKEN.strip())

    try:
        result = handle_twilio_webhook(
            db=db,
            payload=payload,
            url=request_url,
            signature=x_twilio_signature,
            enforce_signature=enforce_signature,
        )
        return result
    except WebhookSignatureVerificationError as exc:
        logger.warning("Twilio webhook rejected due to invalid cryptographic signature: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.warning("Malformed Twilio webhook payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Error processing Twilio messaging webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook event.",
        )
