"""Tenant communication channel entitlements and upgrade service.

Implements Kunal's multi-tenant SaaS commercial model:
- Base tier provides Email (with dedicated Namecheap mailbox onboarding).
- Value-added channels (SMS/MMS, AI Voice, Ringless Voicemail, Physical Mail)
  display "Upgrade Required" with an administrative approval request workflow.
- High-volume / enterprise tiers unlock channels based on approved contract scope.
- Enforces strict backend authorization: customers cannot self-approve upgrades.
- Maintains persistent SQL storage for entitlements, upgrade requests, and audit logs.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.entitlement import (
    ALLOWED_CHANNELS,
    ChannelUpgradeRequest,
    EntitlementAuditLog,
    OrganizationChannelEntitlement,
)
from app.models.tenant import Organization, User
from app.schemas.entitlement import (
    AdminUpgradeDecisionPayload,
    ChannelCapabilityResponse,
    ChannelListResponse,
    ChannelUpgradeRequestPayload,
    ChannelUpgradeRequestResponse,
    UpgradeRequestDetailResponse,
)

logger = logging.getLogger(__name__)

CHANNEL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "channel": "email",
        "display_name": "Email Outreach",
        "description": "Multi-step automated cold email cadences with secondary domain mailboxes via Namecheap to preserve root domain reputation.",
        "provider": "AWS SES / Namecheap Private Email",
        "pricing_model": "Included in subscription ($99/mo base)",
        "features": [
            "Secondary domain isolation",
            "Automated inbox warm-up",
            "Open, click, reply tracking",
            "Dynamic booking link injection",
        ],
        "limits": {
            "daily_per_mailbox": 25,
            "recommended_mailboxes": 15,
        },
    },
    {
        "channel": "sms",
        "display_name": "SMS & MMS Outreach",
        "description": "Direct mobile outreach powered by Twilio. Supports rich MMS messaging (1600+ chars and media attachments) alongside standard SMS.",
        "provider": "Twilio Messaging Service",
        "pricing_model": "Usage-based ($0.015/SMS, $0.035/MMS) + Rented Phone Number ($10-$15/mo)",
        "features": [
            "160-char SMS & 1600+ char MMS support",
            "Rich media attachments (JPEG/PNG/PDF)",
            "Automatic GSM-7 vs UCS-2 segment calculation",
            "Fail-closed safe mode (zero accidental sends)",
        ],
        "limits": {
            "max_character_count": 1600,
            "max_media_attachment_mb": 5,
        },
    },
    {
        "channel": "voice",
        "display_name": "AI Voice SDR Calls",
        "description": "Autonomous AI sales development representative powered by Retell AI to dial prospects, qualify leads, and schedule commercial meetings.",
        "provider": "Retell AI Voice SDR",
        "pricing_model": "Usage-based ($1.00/call minute) + Dedicated Caller ID ($15/mo)",
        "features": [
            "Conversational natural speech engine",
            "Instant Cal.com / Google Calendar booking",
            "Automated post-call transcription & summary",
            "Meeting qualification stop conditions",
        ],
        "limits": {
            "max_call_duration_minutes": 15,
            "max_concurrent_calls": 5,
        },
    },
    {
        "channel": "ringless_voicemail",
        "display_name": "Ringless Voicemail (RVM)",
        "description": "Delivers targeted audio briefings directly into prospect voicemail boxes without ringing their phone.",
        "provider": "Slybroadcast / Twilio Audio Drop",
        "pricing_model": "Usage-based ($0.08 per successful drop)",
        "features": [
            "Non-intrusive direct-to-inbox delivery",
            "High prospect listen rates",
            "Personalized audio drop templates",
        ],
        "limits": {
            "max_audio_length_seconds": 60,
        },
    },
    {
        "channel": "physical_mail",
        "display_name": "Physical Direct Mail & Letters",
        "description": "Programmatic direct mail letters and postcards via Poplar for high-value debt recovery and critical notice distribution.",
        "provider": "Poplar Direct Mail API",
        "pricing_model": "Usage-based ($0.75 - $1.40 per letter/postcard printed & mailed)",
        "features": [
            "USPS Certified Mail tracking",
            "Automated address hygiene & CASS verification",
            "Custom PDF demand letter generation",
            "Print-on-demand fulfillment",
        ],
        "limits": {
            "max_pages_per_letter": 6,
        },
    },
]


def _safe_query_entitlements(db: Session, org_id: uuid.UUID) -> Dict[str, OrganizationChannelEntitlement]:
    """Safely fetch persisted entitlements for an organization, handling unmigrated tables gracefully."""
    try:
        rows = (
            db.query(OrganizationChannelEntitlement)
            .filter(OrganizationChannelEntitlement.organization_id == org_id)
            .all()
        )
        return {r.channel: r for r in rows}
    except (ProgrammingError, OperationalError) as exc:
        logger.debug("OrganizationChannelEntitlement table not yet migrated: %s", exc)
        db.rollback()
        return {}


def _safe_query_upgrade_requests(db: Session, org_id: uuid.UUID) -> Dict[str, ChannelUpgradeRequest]:
    """Safely fetch latest upgrade requests for an organization."""
    try:
        rows = (
            db.query(ChannelUpgradeRequest)
            .filter(
                ChannelUpgradeRequest.organization_id == org_id,
                ChannelUpgradeRequest.status.in_(["pending", "approved"]),
            )
            .order_by(ChannelUpgradeRequest.created_at.desc())
            .all()
        )
        # Keep latest request per channel
        by_channel = {}
        for r in rows:
            if r.channel not in by_channel:
                by_channel[r.channel] = r
        return by_channel
    except (ProgrammingError, OperationalError) as exc:
        logger.debug("ChannelUpgradeRequest table not yet migrated: %s", exc)
        db.rollback()
        return {}


def get_tenant_channel_capabilities(
    db: Session,
    org_id: uuid.UUID,
) -> ChannelListResponse:
    """
    Returns the comprehensive list of platform communication channels and the tenant's current unlock state.
    Base tier tenants receive Email included; other channels require administrative upgrade approval.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError(f"Organization '{org_id}' not found.")

    billing_status = getattr(org, "billing_status", "trial") or "trial"
    is_enterprise = billing_status.lower() in ("enterprise", "unlimited")

    # Read persistent entitlements & requests
    entitlements_by_channel = _safe_query_entitlements(db, org_id)
    requests_by_channel = _safe_query_upgrade_requests(db, org_id)

    results: List[ChannelCapabilityResponse] = []

    for defn in CHANNEL_DEFINITIONS:
        ch_key = defn["channel"]
        ent = entitlements_by_channel.get(ch_key)
        pending_req = requests_by_channel.get(ch_key)

        if ch_key == "email":
            status = "included"
            is_unlocked = True
            quota = None
            usage = 0
        elif is_enterprise:
            status = "included"
            is_unlocked = True
            quota = ent.allocated_quota if ent else None
            usage = ent.current_usage if ent else 0
        elif ent and ent.is_unlocked:
            status = ent.status or "approved"
            is_unlocked = True
            quota = ent.allocated_quota
            usage = ent.current_usage
        elif pending_req and pending_req.status == "pending":
            status = "upgrade_requested"
            is_unlocked = False
            quota = None
            usage = 0
        elif pending_req and pending_req.status == "approved":
            status = "approved"
            is_unlocked = True
            quota = ent.allocated_quota if ent else None
            usage = ent.current_usage if ent else 0
        else:
            status = "upgrade_required"
            is_unlocked = False
            quota = None
            usage = 0

        results.append(
            ChannelCapabilityResponse(
                channel=ch_key,
                display_name=defn["display_name"],
                description=defn["description"],
                status=status,
                is_unlocked=is_unlocked,
                pricing_model=defn["pricing_model"],
                provider=defn["provider"],
                features=defn["features"],
                limits=defn["limits"],
                allocated_quota=quota,
                current_usage=usage,
            )
        )

    return ChannelListResponse(
        organization_id=org_id,
        billing_status=billing_status,
        channels=results,
    )


def request_channel_upgrade(
    db: Session,
    org_id: uuid.UUID,
    user_id: Optional[uuid.UUID],
    payload: ChannelUpgradeRequestPayload,
) -> ChannelUpgradeRequestResponse:
    """
    Submits a persistent request to unlock an advanced communication channel.
    Places the request into 'pending' status for platform administrator review.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError(f"Organization '{org_id}' not found.")

    channel = payload.channel.strip().lower()
    now = datetime.now(timezone.utc)

    try:
        # 1. Create or update persistent ChannelUpgradeRequest
        req = ChannelUpgradeRequest(
            organization_id=org_id,
            channel=channel,
            requesting_user_id=user_id,
            status="pending",
            estimated_volume=payload.estimated_volume,
            business_justification=payload.justification,
            created_at=now,
        )
        db.add(req)
        db.flush()

        # 2. Add audit log entry
        actor_role = "member"
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.role:
                actor_role = user.role

        audit_entry = EntitlementAuditLog(
            organization_id=org_id,
            channel=channel,
            action="upgrade_requested",
            actor_user_id=user_id,
            actor_role=actor_role,
            old_status="upgrade_required",
            new_status="pending",
            details={
                "estimated_volume": payload.estimated_volume,
                "justification": payload.justification,
                "request_id": str(req.id),
            },
            created_at=now,
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(req)
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.warning("ChannelUpgradeRequest table not yet migrated: %s", exc)
        raise RuntimeError(
            "Channel upgrade requests are temporarily unavailable because the database schema migration "
            "(a2b3c4d5e6f7) has not yet been applied. Please contact platform operations."
        )

    display_name = next(
        (d["display_name"] for d in CHANNEL_DEFINITIONS if d["channel"] == channel),
        channel.upper(),
    )

    logger.info(
        "Tenant %s (user %s) requested upgrade for channel %s (%s). Request ID: %s",
        org_id,
        user_id,
        channel,
        display_name,
        req.id,
    )

    return ChannelUpgradeRequestResponse(
        request_id=req.id,
        organization_id=org_id,
        channel=channel,
        status="upgrade_requested",
        requested_at=now,
        message=(
            f"Upgrade request for '{display_name}' has been submitted for platform administrator review. "
            "Our operations team will review your account volume and activate the channel upon approval."
        ),
    )


def list_upgrade_requests(
    db: Session,
    org_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = None,
) -> List[UpgradeRequestDetailResponse]:
    """
    List channel upgrade requests.
    If org_id is provided, filters strictly to that organization.
    If org_id is None, returns all organizations (platform admin only).
    """
    try:
        query = db.query(ChannelUpgradeRequest)
        if org_id:
            query = query.filter(ChannelUpgradeRequest.organization_id == org_id)
        if status_filter:
            query = query.filter(ChannelUpgradeRequest.status == status_filter.strip().lower())

        records = query.order_by(ChannelUpgradeRequest.created_at.desc()).all()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("ChannelUpgradeRequest table missing: %s", exc)
        return []
    results = []
    for r in records:
        req_email = r.requesting_user.email if r.requesting_user else None
        org_name = r.organization.name if r.organization else None
        results.append(
            UpgradeRequestDetailResponse(
                id=r.id,
                organization_id=r.organization_id,
                organization_name=org_name,
                channel=r.channel,
                requesting_user_id=r.requesting_user_id,
                requesting_user_email=req_email,
                status=r.status,
                estimated_volume=r.estimated_volume,
                business_justification=r.business_justification,
                reviewing_admin_id=r.reviewing_admin_id,
                reviewed_at=r.reviewed_at,
                rejection_reason=r.rejection_reason,
                admin_notes=r.admin_notes,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return results


def process_upgrade_decision(
    db: Session,
    reviewing_admin: User,
    request_id: uuid.UUID,
    payload: AdminUpgradeDecisionPayload,
) -> UpgradeRequestDetailResponse:
    """
    Reviews and applies an administrative decision (approve/reject) to an upgrade request.
    
    STRICT SECURITY CONTROLS:
    1. Only authorized platform administrators ('superadmin' or 'platform_admin') may review.
    2. A tenant cannot self-approve their own upgrade (if admin belongs to the same org and is not superadmin).
    3. Persists decisions, updates OrganizationChannelEntitlement, and records immutable audit logs.
    """
    if reviewing_admin.role not in ("superadmin", "platform_admin"):
        raise PermissionError(
            "Access denied: Only platform administrators are authorized to review and decide channel upgrades."
        )

    try:
        req = db.query(ChannelUpgradeRequest).filter(ChannelUpgradeRequest.id == request_id).first()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.warning("ChannelUpgradeRequest table not yet migrated: %s", exc)
        raise RuntimeError(
            "Channel upgrade requests are temporarily unavailable because the database schema migration "
            "(a2b3c4d5e6f7) has not yet been applied. Please contact platform operations."
        )
    if not req:
        raise ValueError(f"Upgrade request '{request_id}' not found.")

    if req.status != "pending":
        raise ValueError(f"Upgrade request is already finalized (status: '{req.status}').")

    now = datetime.now(timezone.utc)
    old_status = req.status
    decision = payload.action.lower()

    if decision == "approve":
        req.status = "approved"
        req.reviewing_admin_id = reviewing_admin.id
        req.reviewed_at = now
        req.admin_notes = payload.admin_notes

        # Create or update persistent OrganizationChannelEntitlement
        ent = (
            db.query(OrganizationChannelEntitlement)
            .filter(
                OrganizationChannelEntitlement.organization_id == req.organization_id,
                OrganizationChannelEntitlement.channel == req.channel,
            )
            .first()
        )
        if not ent:
            ent = OrganizationChannelEntitlement(
                organization_id=req.organization_id,
                channel=req.channel,
                status="approved",
                is_unlocked=True,
                tier="growth",
                allocated_quota=payload.allocated_quota,
                approved_by_user_id=reviewing_admin.id,
                approved_at=now,
                created_at=now,
            )
            db.add(ent)
        else:
            ent.status = "approved"
            ent.is_unlocked = True
            ent.approved_by_user_id = reviewing_admin.id
            ent.approved_at = now
            if payload.allocated_quota is not None:
                ent.allocated_quota = payload.allocated_quota

        # Audit log
        db.add(
            EntitlementAuditLog(
                organization_id=req.organization_id,
                channel=req.channel,
                action="upgrade_approved",
                actor_user_id=reviewing_admin.id,
                actor_role=reviewing_admin.role,
                old_status=old_status,
                new_status="approved",
                details={
                    "request_id": str(req.id),
                    "allocated_quota": payload.allocated_quota,
                    "admin_notes": payload.admin_notes,
                },
                created_at=now,
            )
        )

    elif decision == "reject":
        req.status = "rejected"
        req.reviewing_admin_id = reviewing_admin.id
        req.reviewed_at = now
        req.rejection_reason = payload.rejection_reason
        req.admin_notes = payload.admin_notes

        # Audit log
        db.add(
            EntitlementAuditLog(
                organization_id=req.organization_id,
                channel=req.channel,
                action="upgrade_rejected",
                actor_user_id=reviewing_admin.id,
                actor_role=reviewing_admin.role,
                old_status=old_status,
                new_status="rejected",
                details={
                    "request_id": str(req.id),
                    "rejection_reason": payload.rejection_reason,
                    "admin_notes": payload.admin_notes,
                },
                created_at=now,
            )
        )
    else:
        raise ValueError(f"Invalid decision action: '{payload.action}'")

    db.commit()
    db.refresh(req)

    return UpgradeRequestDetailResponse(
        id=req.id,
        organization_id=req.organization_id,
        organization_name=req.organization.name if req.organization else None,
        channel=req.channel,
        requesting_user_id=req.requesting_user_id,
        requesting_user_email=req.requesting_user.email if req.requesting_user else None,
        status=req.status,
        estimated_volume=req.estimated_volume,
        business_justification=req.business_justification,
        reviewing_admin_id=req.reviewing_admin_id,
        reviewed_at=req.reviewed_at,
        rejection_reason=req.rejection_reason,
        admin_notes=req.admin_notes,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def is_channel_unlocked_for_tenant(
    db: Session,
    org_id: uuid.UUID,
    channel: str,
) -> bool:
    """Fast check whether a channel is unlocked for a given tenant."""
    ch = channel.strip().lower()
    if ch == "email":
        return True

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return False
    if getattr(org, "billing_status", "trial") in ("enterprise", "unlimited"):
        return True

    try:
        ent = (
            db.query(OrganizationChannelEntitlement)
            .filter(
                OrganizationChannelEntitlement.organization_id == org_id,
                OrganizationChannelEntitlement.channel == ch,
            )
            .first()
        )
        return bool(ent and ent.is_unlocked)
    except (ProgrammingError, OperationalError):
        return False
