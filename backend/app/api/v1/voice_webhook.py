"""
Retell AI Voice Call Webhook and Follow-Up Endpoints.

Handles:
- POST /voice/retell-webhook: Public webhook endpoint for Retell events with HMAC verification.
- POST /voice/replay-analyzed-call: Development & testing replay endpoint.
- GET /voice/call-records: Tenant-scoped listing of voice call records.
- GET /voice/call-records/{call_id}: Detailed inspection of a specific call record.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_organization, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.call_record import CallRecord
from app.models.lead import Lead
from app.models.tenant import Organization, User
from app.schemas.call_record import CallRecordResponse, RetellWebhookResponse
from app.schemas.voice import (
    VoiceAgentDetailResponse,
    VoiceAgentsResponse,
    VoiceAgentSummaryResponse,
    VoiceStatusResponse,
)
from app.services.outreach.voice_followup import (
    UnresolvedOrganizationError,
    VoiceFollowUpService,
)
from app.services.voice.retell_client import (
    RetellAuthenticationError,
    RetellClient,
    RetellError,
    RetellNotFoundError,
    RetellRateLimitError,
    RetellTimeoutError,
    get_retell_client,
)


router = APIRouter(prefix="/voice", tags=["Voice Calls & Retell Webhooks"])


@router.post(
    "/retell-webhook",
    response_model=RetellWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Retell AI voice call event webhook",
    description=(
        "Processes real-time Retell AI call events (call_started, call_ended, call_analyzed). "
        "Verifies x-retell-signature, stores call metrics, extracts structured variables, "
        "evaluates deterministic follow-up rules, and triggers automated emails via Resend."
    ),
)
async def retell_webhook_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    x_retell_signature: Optional[str] = Header(None, alias="x-retell-signature"),
) -> RetellWebhookResponse:
    """Handle incoming Retell AI webhook events with signature verification."""
    raw_body = await request.body()

    # Verify signature if enabled
    if settings.RETELL_VERIFY_WEBHOOK_SIGNATURE:
        is_valid = VoiceFollowUpService.verify_webhook_signature(
            raw_body=raw_body,
            signature_header=x_retell_signature,
            secret=settings.RETELL_WEBHOOK_SECRET or settings.RETELL_API_KEY,
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Retell webhook signature (x-retell-signature).",
            )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {exc}",
        )

    event_type = (
        payload.get("event")
        or payload.get("event_type")
        or (payload.get("call", {}).get("call_status"))
        or "unknown"
    )

    service = VoiceFollowUpService(db=db)

    try:
        # Route based on Retell event
        if event_type == "call_started":
            record = service.handle_call_started(payload)
            return RetellWebhookResponse(
                status="success",
                call_id=record.call_id,
                event="call_started",
                followup_status=record.followup_status,
            )

        elif event_type == "call_ended":
            record = service.handle_call_ended(payload)
            return RetellWebhookResponse(
                status="success",
                call_id=record.call_id,
                event="call_ended",
                followup_status=record.followup_status,
            )

        elif event_type == "call_analyzed":
            result = service.process_call_analyzed(payload)
            return RetellWebhookResponse(
                status=result["status"],
                call_id=result["call_id"],
                event="call_analyzed",
                followup_status=result.get("followup_status"),
                followup_reason=result.get("followup_reason"),
                followup_email_id=result.get("followup_email_id"),
                duplicate=result.get("duplicate", False),
            )

        else:
            call_id = payload.get("call_id") or payload.get("call", {}).get("call_id") or "unknown"
            return RetellWebhookResponse(
                status="ignored",
                call_id=str(call_id),
                event=str(event_type),
                followup_status="none",
                followup_reason=f"Ignored unhandled Retell event: {event_type}",
            )
    except UnresolvedOrganizationError as exc:
        call_id = payload.get("call_id") or payload.get("call", {}).get("call_id") or "unknown"
        return RetellWebhookResponse(
            status="quarantined",
            call_id=str(call_id),
            event=str(event_type),
            followup_status="quarantined",
            followup_reason=f"Quarantined: {str(exc)}. No emails or calls initiated.",
        )


@router.post(
    "/replay-analyzed-call",
    response_model=RetellWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Development/Testing Replay of call_analyzed payload",
    description=(
        "Safely simulates or replays a Retell call_analyzed payload for testing and verification. "
        "Strictly requires tenant user authentication across all environments."
    ),
)
async def replay_analyzed_call_endpoint(
    payload: Dict[str, Any],
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> RetellWebhookResponse:
    """Replay endpoint for testing and pipeline verification, authenticated per tenant."""
    service = VoiceFollowUpService(db=db)
    result = service.process_call_analyzed(payload)

    return RetellWebhookResponse(
        status=result["status"],
        call_id=result["call_id"],
        event="call_analyzed",
        followup_status=result.get("followup_status"),
        followup_reason=result.get("followup_reason"),
        followup_email_id=result.get("followup_email_id"),
        duplicate=result.get("duplicate", False),
    )


@router.get(
    "/call-records",
    response_model=List[CallRecordResponse],
    summary="List tenant voice call records",
)
def list_call_records(
    lead_id: Optional[uuid.UUID] = Query(None, description="Filter by Lead ID"),
    contact_id: Optional[uuid.UUID] = Query(None, description="Filter by Contact ID"),
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by Campaign ID"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    skip: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_organization),
) -> List[CallRecord]:
    """Retrieve call records for the current authenticated organization with safe filtering."""
    stmt = select(CallRecord).where(CallRecord.organization_id == org.id)

    if campaign_id:
        stmt = stmt.where(CallRecord.campaign_id == campaign_id)

    if contact_id:
        stmt = stmt.where(CallRecord.contact_id == contact_id)

    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.organization_id == org.id).first()
        if not lead:
            return []
        if lead.contact_id:
            stmt = stmt.where(or_(CallRecord.lead_id == lead_id, CallRecord.contact_id == lead.contact_id))
        else:
            stmt = stmt.where(CallRecord.lead_id == lead_id)

    records = db.execute(
        stmt.order_by(CallRecord.created_at.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 100))
    ).scalars().all()
    return list(records)


@router.get(
    "/call-records/{call_id}",
    response_model=CallRecordResponse,
    summary="Get single voice call record by Retell call_id",
)
def get_call_record(
    call_id: str,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_current_organization),
) -> CallRecord:
    """Retrieve a specific call record scoped to the authenticated organization."""
    record = db.execute(
        select(CallRecord)
        .where(CallRecord.organization_id == org.id, CallRecord.call_id == call_id)
    ).scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call record '{call_id}' not found for this organization.",
        )

    return record


# ── Status and Agent Discovery Endpoints ─────────────────────────────────────

@router.get(
    "/status",
    response_model=VoiceStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Retell AI voice integration connection status",
    description="Returns live connection health, discovered agent count, configured agent IDs, and caller ID without exposing credentials.",
)
def get_voice_status(
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    client: RetellClient = Depends(get_retell_client),
) -> VoiceStatusResponse:
    """Check Retell AI connectivity and configuration status for the authenticated organization."""
    status_result = client.check_connection()
    return VoiceStatusResponse(
        configured=status_result.configured,
        connected=status_result.connected,
        provider=status_result.provider,
        base_url=status_result.base_url,
        outbound_agent_id=status_result.configured_outbound_agent_id,
        inbound_agent_id=status_result.configured_inbound_agent_id,
        outbound_from_number=status_result.caller_id,
        outbound_agent_valid=status_result.outbound_agent_valid,
        inbound_agent_valid=status_result.inbound_agent_valid,
        agent_count=status_result.agent_count,
        error=status_result.error,
        message=status_result.message,
    )


@router.get(
    "/agents",
    response_model=VoiceAgentsResponse,
    status_code=status.HTTP_200_OK,
    summary="List available Retell voice agents",
    description="Discovers active voice agents available in the configured Retell account.",
)
def list_voice_agents(
    agent_id: Optional[str] = Query(None, description="Optional specific agent ID to retrieve"),
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    client: RetellClient = Depends(get_retell_client),
) -> VoiceAgentsResponse:
    """Retrieve available Retell voice agents for workflow configuration."""
    outbound_sdr_id = getattr(settings, "RETELL_AGENT_ID", None)
    inbound_id = getattr(settings, "RETELL_INBOUND_AGENT_ID", None)

    if not client.is_configured:
        return VoiceAgentsResponse(
            configured=False,
            connected=False,
            count=0,
            items=[],
            configured_outbound_agent_id=outbound_sdr_id,
            configured_inbound_agent_id=inbound_id,
            error="RETELL_API_KEY is not configured",
            message="Retell AI voice provider is unconfigured. Set RETELL_API_KEY to enable.",
        )

    # If specific agent_id requested
    if agent_id:
        try:
            detail = client.get_agent(agent_id)
            item = VoiceAgentSummaryResponse(
                agent_id=detail.agent_id,
                agent_name=detail.agent_name,
                channel=detail.channel,
                voice_id=detail.voice_id,
                response_engine_type=detail.response_engine.get("type") if isinstance(detail.response_engine, dict) else None,
                llm_id=detail.response_engine.get("llm_id") if isinstance(detail.response_engine, dict) else None,
                user_modified_timestamp=detail.last_modification_timestamp,
                is_configured_sdr=bool(outbound_sdr_id and detail.agent_id == outbound_sdr_id),
                is_configured_inbound=bool(inbound_id and detail.agent_id == inbound_id),
            )
            return VoiceAgentsResponse(
                configured=True,
                connected=True,
                count=1,
                items=[item],
                configured_outbound_agent_id=outbound_sdr_id,
                configured_inbound_agent_id=inbound_id,
                message=f"Retrieved agent '{detail.agent_name}'.",
            )
        except RetellNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Retell agent '{agent_id}' not found.",
            )
        except RetellAuthenticationError:
            return VoiceAgentsResponse(
                configured=True,
                connected=False,
                count=0,
                items=[],
                configured_outbound_agent_id=outbound_sdr_id,
                configured_inbound_agent_id=inbound_id,
                error="Authentication failed",
                message="Retell authentication rejected. Check RETELL_API_KEY.",
            )
        except RetellError as exc:
            return VoiceAgentsResponse(
                configured=True,
                connected=False,
                count=0,
                items=[],
                configured_outbound_agent_id=outbound_sdr_id,
                configured_inbound_agent_id=inbound_id,
                error="Provider error",
                message=f"Failed to retrieve agent: {exc}",
            )

    # General list
    try:
        summaries = client.list_agents(limit=100)
        items = [
            VoiceAgentSummaryResponse(
                agent_id=s.agent_id,
                agent_name=s.agent_name,
                channel=s.channel,
                voice_id=s.voice_id,
                response_engine_type=s.response_engine_type,
                llm_id=s.llm_id,
                user_modified_timestamp=s.user_modified_timestamp,
                is_configured_sdr=bool(outbound_sdr_id and s.agent_id == outbound_sdr_id),
                is_configured_inbound=bool(inbound_id and s.agent_id == inbound_id),
            )
            for s in summaries
        ]
        return VoiceAgentsResponse(
            configured=True,
            connected=True,
            count=len(items),
            items=items,
            configured_outbound_agent_id=outbound_sdr_id,
            configured_inbound_agent_id=inbound_id,
            message=f"Discovered {len(items)} Retell voice agent(s).",
        )
    except RetellAuthenticationError:
        return VoiceAgentsResponse(
            configured=True,
            connected=False,
            count=0,
            items=[],
            configured_outbound_agent_id=outbound_sdr_id,
            configured_inbound_agent_id=inbound_id,
            error="Authentication failed",
            message="Retell authentication rejected. Check that RETELL_API_KEY is valid.",
        )
    except RetellRateLimitError:
        return VoiceAgentsResponse(
            configured=True,
            connected=False,
            count=0,
            items=[],
            configured_outbound_agent_id=outbound_sdr_id,
            configured_inbound_agent_id=inbound_id,
            error="Rate limited",
            message="Retell API rate limit reached. Please retry later.",
        )
    except RetellTimeoutError:
        return VoiceAgentsResponse(
            configured=True,
            connected=False,
            count=0,
            items=[],
            configured_outbound_agent_id=outbound_sdr_id,
            configured_inbound_agent_id=inbound_id,
            error="Timeout",
            message="Retell connection timed out.",
        )
    except RetellError as exc:
        return VoiceAgentsResponse(
            configured=True,
            connected=False,
            count=0,
            items=[],
            configured_outbound_agent_id=outbound_sdr_id,
            configured_inbound_agent_id=inbound_id,
            error="Provider error",
            message=f"Retell API communication error occurred: {exc}",
        )


@router.get(
    "/agents/{agent_id}",
    response_model=VoiceAgentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single Retell voice agent detail",
    description="Retrieves full configuration details of a specific Retell agent.",
)
def get_voice_agent_detail(
    agent_id: str,
    current_user: User = Depends(get_current_active_user),
    org: Organization = Depends(get_current_organization),
    client: RetellClient = Depends(get_retell_client),
) -> VoiceAgentDetailResponse:
    """Retrieve full configuration of an individual Retell voice agent."""
    outbound_sdr_id = getattr(settings, "RETELL_AGENT_ID", None)
    inbound_id = getattr(settings, "RETELL_INBOUND_AGENT_ID", None)

    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retell AI voice provider is unconfigured.",
        )

    try:
        detail = client.get_agent(agent_id)
        return VoiceAgentDetailResponse(
            agent_id=detail.agent_id,
            agent_name=detail.agent_name,
            channel=detail.channel,
            voice_id=detail.voice_id,
            voice_model=detail.voice_model,
            language=detail.language,
            responsiveness=detail.responsiveness,
            interruption_sensitivity=detail.interruption_sensitivity,
            enable_backchannel=detail.enable_backchannel,
            ambient_sound=detail.ambient_sound,
            response_engine=detail.response_engine,
            post_call_analysis_data=detail.post_call_analysis_data,
            is_configured_sdr=bool(outbound_sdr_id and detail.agent_id == outbound_sdr_id),
            is_configured_inbound=bool(inbound_id and detail.agent_id == inbound_id),
        )
    except RetellNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retell agent '{agent_id}' not found.",
        )
    except RetellAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Retell authentication rejected by provider.",
        )
    except RetellError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Retell provider error: {exc}",
        )
