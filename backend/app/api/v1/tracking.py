import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_organization
from app.core.config import settings
from app.core.database import get_db
from app.models.tenant import Organization
from app.schemas.tracking import (
    InboundReplyCreate,
    InboundReplyResponse,
    TrackingEventCreate,
    TrackingEventResponse,
)
from app.services.outreach import (
    AmbiguousReplyAssociationError,
    InvalidTrackingStateError,
    OutreachNotFoundError,
    associate_inbound_reply,
    record_bounced,
    record_clicked,
    record_delivered,
    record_opened,
    record_replied,
)
from app.services.outreach.sns_verifier import (
    InvalidSNSSignatureError,
    MalformedSNSPayloadError,
    UntrustedSNSCertificateURLError,
    confirm_sns_subscription,
    is_valid_sns_subscribe_url,
    verify_sns_message,
)

router = APIRouter(prefix="/outreach", tags=["Tracking"])
tracking_webhook_router = APIRouter(prefix="/tracking", tags=["Tracking"])


@router.post(
    "/{outreach_id}/tracking/delivered",
    response_model=TrackingEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Record outreach delivered event",
    description="Records a delivered event and idempotently populates first_delivered_at without mutating outreach status.",
)
async def track_delivered(
    outreach_id: uuid.UUID,
    data: Optional[TrackingEventCreate] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> TrackingEventResponse:
    metadata = data.event_metadata if data else None
    try:
        event = record_delivered(db, current_org.id, outreach_id, event_metadata=metadata)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTrackingStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TrackingEventResponse.model_validate(event)


@router.post(
    "/{outreach_id}/tracking/opened",
    response_model=TrackingEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Record outreach opened event",
    description="Records an opened event and idempotently populates first_opened_at without mutating outreach status.",
)
async def track_opened(
    outreach_id: uuid.UUID,
    data: Optional[TrackingEventCreate] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> TrackingEventResponse:
    metadata = data.event_metadata if data else None
    try:
        event = record_opened(db, current_org.id, outreach_id, event_metadata=metadata)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTrackingStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TrackingEventResponse.model_validate(event)


@router.post(
    "/{outreach_id}/tracking/clicked",
    response_model=TrackingEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Record outreach clicked event",
    description="Records a clicked event and idempotently populates first_clicked_at without mutating outreach status.",
)
async def track_clicked(
    outreach_id: uuid.UUID,
    data: Optional[TrackingEventCreate] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> TrackingEventResponse:
    metadata = data.event_metadata if data else None
    try:
        event = record_clicked(db, current_org.id, outreach_id, event_metadata=metadata)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTrackingStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TrackingEventResponse.model_validate(event)


@router.post(
    "/{outreach_id}/tracking/replied",
    response_model=TrackingEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Record outreach replied event",
    description="Records a replied event, populates first_replied_at, and transitions contact lead_status to replied unless opted_out.",
)
async def track_replied(
    outreach_id: uuid.UUID,
    data: Optional[TrackingEventCreate] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> TrackingEventResponse:
    metadata = data.event_metadata if data else None
    try:
        event = record_replied(db, current_org.id, outreach_id, event_metadata=metadata)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTrackingStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TrackingEventResponse.model_validate(event)


@router.post(
    "/{outreach_id}/tracking/bounced",
    response_model=TrackingEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Record outreach bounced event",
    description="Records a bounced event and populates first_bounced_at while preserving contact and campaign enrollment intact.",
)
async def track_bounced(
    outreach_id: uuid.UUID,
    data: Optional[TrackingEventCreate] = None,
    current_org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> TrackingEventResponse:
    metadata = data.event_metadata if data else None
    try:
        event = record_bounced(db, current_org.id, outreach_id, event_metadata=metadata)
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTrackingStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return TrackingEventResponse.model_validate(event)


def verify_inbound_webhook_auth(
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """
    Verify webhook authentication for inbound reply endpoints.
    Requires server-side secret INBOUND_REPLY_WEBHOOK_SECRET to be configured and matched.
    Supports 'X-Webhook-Secret: <secret>' or 'Authorization: Bearer <secret>'.
    Fails closed if the secret is unconfigured or credentials are missing/invalid.
    """
    server_secret = settings.INBOUND_REPLY_WEBHOOK_SECRET
    if not server_secret or not server_secret.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inbound reply webhook secret is not configured on the server. Access denied.",
        )

    provided_secret = None
    if x_webhook_secret:
        provided_secret = x_webhook_secret.strip()
    elif authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_secret = parts[1].strip()
        elif len(parts) == 1:
            provided_secret = parts[0].strip()

    if not provided_secret or not secrets.compare_digest(provided_secret, server_secret.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook authentication credentials.",
        )


async def _handle_ses_webhook(payload: dict, db: Session) -> dict:
    import json
    from sqlalchemy import or_
    from app.models.crm import Contact
    from app.models.outreach import Outreach

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload: expected JSON object.",
        )

    msg_type = payload.get("Type")
    is_sns = msg_type in ("Notification", "SubscriptionConfirmation", "UnsubscribeConfirmation")

    # 1. Cryptographic SNS Signature Verification & Safety Guard
    if settings.AWS_SNS_VERIFY_WEBHOOK_SIGNATURE:
        if not is_sns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Untrusted payload: missing required AWS SNS envelope and cryptographic signature.",
            )
        try:
            await verify_sns_message(payload, verify_signature=True)
        except UntrustedSNSCertificateURLError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Untrusted certificate URL: {exc}")
        except InvalidSNSSignatureError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid SNS signature: {exc}")
        except MalformedSNSPayloadError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed SNS payload: {exc}")
    elif is_sns:
        # If signature verification is disabled (e.g. for mock tests), validate basic envelope safely
        try:
            await verify_sns_message(payload, verify_signature=False)
        except MalformedSNSPayloadError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed SNS payload: {exc}")

    # 2. Safe Subscription Confirmation Handling
    if msg_type == "SubscriptionConfirmation":
        subscribe_url = payload.get("SubscribeURL", "")
        if not is_valid_sns_subscribe_url(subscribe_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Untrusted or invalid SubscribeURL format in SubscriptionConfirmation.",
            )
        confirmed = await confirm_sns_subscription(subscribe_url)
        return {
            "status": "subscription_confirmed" if confirmed else "subscription_confirmation_verified",
            "SubscribeURL": subscribe_url,
        }

    # 3. Parse SNS Notification or Direct Event Payload
    sns_message_id = payload.get("MessageId") if is_sns else None
    event_data = payload
    if is_sns and "Message" in payload:
        try:
            event_data = json.loads(payload["Message"])
        except Exception:
            event_data = payload

    event_type = (event_data.get("eventType") or event_data.get("event_type") or "").strip()
    mail_info = event_data.get("mail", {})
    message_id = (
        mail_info.get("messageId")
        or mail_info.get("commonHeaders", {}).get("messageId")
        or event_data.get("message_id")
    )

    if not event_type:
        return {"status": "ignored", "reason": "missing_event_type"}

    # 4. Resolve Outreach record
    outreach = None

    # Step A: Check for outreach_id in SES tags
    tags_data = mail_info.get("tags") or {}
    tag_outreach_id = None
    if isinstance(tags_data, dict):
        val = tags_data.get("outreach_id")
        tag_outreach_id = val[0] if isinstance(val, list) and val else val
    elif isinstance(tags_data, list):
        for t in tags_data:
            if isinstance(t, dict) and t.get("Name") == "outreach_id":
                tag_outreach_id = t.get("Value")
                break

    if tag_outreach_id:
        try:
            outreach = db.query(Outreach).filter(Outreach.id == uuid.UUID(str(tag_outreach_id))).first()
        except Exception:
            outreach = None

    # Step B: Match by candidate provider message IDs
    if not outreach and message_id:
        raw_id = str(message_id).strip()
        clean_id = raw_id.strip("<>")
        candidates = [raw_id, clean_id, f"<{clean_id}>"]
        if "@" in clean_id:
            candidates.append(clean_id.split("@")[0])
        candidates = list(dict.fromkeys(candidates))

        outreach = (
            db.query(Outreach)
            .filter(Outreach.provider_message_id.in_(candidates))
            .first()
        )

    # Step C: Fallback to destination email address matching for recent sent outreach
    if not outreach:
        destinations = mail_info.get("destination") or []
        if isinstance(destinations, str):
            destinations = [destinations]
        clean_dests = [d.strip().lower() for d in destinations if isinstance(d, str) and "@" in d]
        if clean_dests:
            contact_ids = [
                row[0]
                for row in db.query(Contact.id)
                .filter(Contact.email.in_(clean_dests))
                .all()
            ]
            conditions = [Outreach.recipient.in_(clean_dests)]
            if contact_ids:
                conditions.append(Outreach.contact_id.in_(contact_ids))

            outreach = (
                db.query(Outreach)
                .filter(
                    or_(*conditions),
                    Outreach.status.in_(["sent", "sending"]),
                )
                .order_by(Outreach.sent_at.desc(), Outreach.created_at.desc())
                .first()
            )

    if not outreach:
        return {"status": "ignored", "reason": "outreach_not_found"}

    # 5. Map SES event type to domain tracking action with deduplication metadata
    event_type_lower = event_type.strip().lower()
    metadata = {
        "ses_event": event_data,
        "source": "aws_ses_webhook",
        "sns_message_id": sns_message_id,
        "provider_message_id": message_id,
    }

    try:
        if event_type_lower in ("delivery", "delivered"):
            record_delivered(db, outreach.organization_id, outreach.id, event_metadata=metadata)
        elif event_type_lower in ("open", "opened"):
            record_opened(db, outreach.organization_id, outreach.id, event_metadata=metadata)
        elif event_type_lower in ("click", "clicked"):
            record_clicked(db, outreach.organization_id, outreach.id, event_metadata=metadata)
        elif event_type_lower in ("bounce", "bounced", "complaint", "reject"):
            record_bounced(db, outreach.organization_id, outreach.id, event_metadata=metadata)
        elif event_type_lower in ("reply", "replied", "inbound", "received"):
            record_replied(db, outreach.organization_id, outreach.id, event_metadata=metadata)
        elif event_type_lower in ("send", "sent"):
            return {
                "status": "processed",
                "outreach_id": str(outreach.id),
                "event_type": "sent",
                "organization_id": str(outreach.organization_id),
            }
        else:
            return {"status": "ignored", "reason": f"unhandled_event_type_{event_type}"}

        return {
            "status": "processed",
            "outreach_id": str(outreach.id),
            "event_type": event_type,
            "organization_id": str(outreach.organization_id),
        }
    except (OutreachNotFoundError, InvalidTrackingStateError) as exc:
        return {"status": "error", "detail": str(exc)}


@router.post(
    "/tracking/ses-webhook",
    status_code=status.HTTP_200_OK,
    summary="Process AWS SES / SNS webhook events",
    description="Ingests delivery, open, click, bounce, and complaint notifications from AWS SES/SNS and updates tracking.",
)
async def process_ses_webhook(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    return await _handle_ses_webhook(payload, db)


@tracking_webhook_router.post(
    "/ses-webhook",
    status_code=status.HTTP_200_OK,
    summary="Process AWS SES / SNS webhook events (direct mount)",
    description="Direct mount for AWS SES/SNS webhook notifications.",
)
async def process_ses_webhook_direct(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    return await _handle_ses_webhook(payload, db)


async def _handle_inbound_reply(data: InboundReplyCreate, db: Session) -> InboundReplyResponse:
    try:
        outreach, event = associate_inbound_reply(
            db=db,
            from_email=data.from_email,
            to_email=data.to_email,
            subject=data.subject,
            body=data.body,
            in_reply_to=data.in_reply_to,
            references=data.references,
            provider_message_id=data.provider_message_id,
            raw_payload=data.raw_payload,
        )
        return InboundReplyResponse(
            status="processed",
            outreach_id=outreach.id,
            contact_id=outreach.contact_id,
            campaign_id=outreach.campaign_id,
            event_id=event.id,
            event_type="replied",
            from_email=data.from_email,
            subject=data.subject,
        )
    except OutreachNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AmbiguousReplyAssociationError as exc:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail=str(exc),
        )
    except (InvalidTrackingStateError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/tracking/inbound-reply",
    response_model=InboundReplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Process inbound email reply",
    description="Ingests incoming email reply and associates with the correct contact, campaign, and outreach record.",
    dependencies=[Depends(verify_inbound_webhook_auth)],
)
async def process_inbound_reply_scoped(
    data: InboundReplyCreate,
    db: Session = Depends(get_db),
) -> InboundReplyResponse:
    return await _handle_inbound_reply(data, db)


@tracking_webhook_router.post(
    "/inbound-reply",
    response_model=InboundReplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Process inbound email reply (direct mount)",
    description="Direct mount for inbound email replies from email providers or forwarders.",
    dependencies=[Depends(verify_inbound_webhook_auth)],
)
async def process_inbound_reply_direct(
    data: InboundReplyCreate,
    db: Session = Depends(get_db),
) -> InboundReplyResponse:
    return await _handle_inbound_reply(data, db)

