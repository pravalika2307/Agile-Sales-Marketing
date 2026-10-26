"""
Poplar Physical Mail Webhook Service.

Handles:
- Cryptographic signature verification using Poplar's documented X-SLM-Signature (HMAC-SHA1 hex digest).
- Strict JSON payload parsing and schema validation for Attribution Report batch data and single events.
- Idempotent event processing with duplicate suppression.
- Campaign, recipient, and outreach matching via persisted provider identifiers (provider_message_id, identifier).
- Multi-tenant isolation and cross-tenant violation prevention.
- Safe handling of out-of-order, duplicate, and unknown identifier events.
- CampaignContact enrollment status updates and OutreachEvent recording.
- Sanitized logging (zero secrets or recipient PII).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import CampaignContact
from app.models.outreach import Outreach, OutreachEvent

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class PoplarWebhookError(Exception):
    """Base exception for Poplar webhook handling."""
    pass


class PoplarSignatureVerificationError(PoplarWebhookError):
    """Raised when an incoming webhook request has an invalid or missing signature."""
    pass


class PoplarMalformedPayloadError(PoplarWebhookError):
    """Raised when an incoming webhook payload has invalid JSON or missing required fields."""
    pass


class PoplarCrossTenantError(PoplarWebhookError):
    """Raised when an incoming webhook attempts cross-tenant record modification."""
    pass


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class WebhookItemOutcome:
    """Outcome for a single attribution or event record in a webhook payload."""
    mailing_id: Optional[str]
    identifier: Optional[str]
    outreach_id: Optional[uuid.UUID]
    status: str  # "processed", "duplicate", "ignored", "error"
    action: str  # "replied", "already_recorded", "unknown_identifier", "cross_tenant_rejected"
    reason: Optional[str] = None
    duplicate: bool = False


@dataclass
class PoplarWebhookResult:
    """Authoritative result returned after processing a Poplar webhook payload."""
    status: str  # "success", "partial_success", "ignored"
    event_type: str
    total_items: int
    processed_count: int
    duplicate_count: int
    ignored_count: int
    outcomes: List[WebhookItemOutcome] = field(default_factory=list)


# ── Signature Verification ────────────────────────────────────────────────────

def verify_poplar_signature(
    raw_body: bytes,
    signature: Optional[str],
    secret: Optional[str] = None,
) -> bool:
    """
    Verify incoming Poplar webhook request authenticity via X-SLM-Signature.

    Algorithm (Poplar / Share Local Media Specification):
    1. Retrieve the shared secret configured in Poplar (Integrations > Attribution Report).
    2. Compute the HMAC-SHA1 hex digest of the raw request body.
    3. Perform constant-time comparison against the received X-SLM-Signature header.
    """
    configured_secret = (secret or settings.POPLAR_WEBHOOK_SECRET or settings.POPLAR_API_KEY or "").strip()
    if not configured_secret or not signature:
        return False

    computed_digest = hmac.new(
        configured_secret.encode("utf-8"),
        raw_body,
        hashlib.sha1,
    ).hexdigest()

    return hmac.compare_digest(computed_digest.lower(), signature.strip().lower())


# ── Poplar Webhook Service ────────────────────────────────────────────────────

class PoplarWebhookService:
    """
    Processes incoming Poplar webhooks with signature checks, deduplication,
    outreach matching, and tenant isolation.
    """

    def __init__(
        self,
        db: Session,
        secret: Optional[str] = None,
        verify_signature: Optional[bool] = None,
    ) -> None:
        self.db = db
        self.secret = secret or settings.POPLAR_WEBHOOK_SECRET or settings.POPLAR_API_KEY
        self.verify_signature = (
            verify_signature
            if verify_signature is not None
            else settings.POPLAR_VERIFY_WEBHOOK_SIGNATURE
        )

    def process_webhook(
        self,
        raw_body: bytes,
        signature: Optional[str],
        org_id_hint: Optional[uuid.UUID] = None,
    ) -> PoplarWebhookResult:
        """
        Main entry point for processing an incoming Poplar webhook payload.

        Steps:
        1. Signature verification (X-SLM-Signature HMAC-SHA1).
        2. JSON decoding & schema validation.
        3. Match records against persisted Outreach provider IDs.
        4. Enforce tenant isolation.
        5. Idempotent state transitions (duplicate suppression).
        6. Update Outreach, CampaignContact, and OutreachEvent records.
        """
        # 1. Signature Verification
        if self.verify_signature:
            if not signature:
                raise PoplarSignatureVerificationError(
                    "Missing Poplar webhook signature header (X-SLM-Signature)."
                )
            if not verify_poplar_signature(raw_body, signature, self.secret):
                raise PoplarSignatureVerificationError(
                    "Invalid Poplar webhook cryptographic signature (X-SLM-Signature)."
                )

        # 2. Parse JSON Payload
        if not raw_body or not raw_body.strip():
            raise PoplarMalformedPayloadError("Empty webhook request body.")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PoplarMalformedPayloadError(f"Malformed JSON payload: {exc}")

        if not isinstance(payload, dict):
            raise PoplarMalformedPayloadError("Webhook payload must be a JSON object.")

        # 3. Detect Payload Type
        # Case A: Ping / Test event
        event_name = (
            payload.get("event")
            or payload.get("event_type")
            or payload.get("type")
            or ""
        ).strip().lower()

        if event_name in ("ping", "test"):
            logger.info("Poplar webhook ping/test event received and acknowledged.")
            return PoplarWebhookResult(
                status="success",
                event_type=event_name,
                total_items=0,
                processed_count=0,
                duplicate_count=0,
                ignored_count=0,
                outcomes=[],
            )

        # Case B: Batch Attribution Report (documented Poplar schema)
        attribution_items: List[Dict[str, Any]] = []
        if "attribution_data" in payload and isinstance(payload["attribution_data"], list):
            attribution_items = payload["attribution_data"]
            event_type = "attribution_report"
        elif "data" in payload and isinstance(payload["data"], list):
            attribution_items = payload["data"]
            event_type = payload.get("event", "attribution_batch")
        elif "mailing_id" in payload or "identifier" in payload:
            # Case C: Single event / direct notification
            attribution_items = [payload]
            event_type = event_name or "single_event"
        else:
            raise PoplarMalformedPayloadError(
                "Payload missing recognized 'attribution_data' array or mailing identifier keys."
            )

        # 4. Process Each Item Idempotently
        outcomes: List[WebhookItemOutcome] = []
        processed_count = 0
        duplicate_count = 0
        ignored_count = 0

        now_utc = datetime.now(timezone.utc)

        for item in attribution_items:
            if not isinstance(item, dict):
                ignored_count += 1
                outcomes.append(
                    WebhookItemOutcome(
                        mailing_id=None,
                        identifier=None,
                        outreach_id=None,
                        status="ignored",
                        action="malformed_item",
                        reason="Item in attribution_data is not an object",
                    )
                )
                continue

            mailing_id = item.get("mailing_id")
            raw_identifier = item.get("identifier") or item.get("recipient_id") or item.get("custom_id")
            order_id = item.get("order_id")
            conversion_id = item.get("conversion_id")
            amount = item.get("conversion_amount") or item.get("revenue") or item.get("amount")

            # Parse timestamp if present
            matched_at_str = item.get("matched_at") or item.get("timestamp") or item.get("created_at")
            event_timestamp = now_utc
            if matched_at_str and isinstance(matched_at_str, str):
                try:
                    event_timestamp = datetime.fromisoformat(matched_at_str.replace("Z", "+00:00"))
                except ValueError:
                    event_timestamp = now_utc

            # Step 4a: Match against Outreach record
            outreach = self._match_outreach(mailing_id=mailing_id, identifier=raw_identifier)

            if not outreach:
                # Unknown provider identifier: log sanitized warning and ignore safely
                logger.warning(
                    "Poplar webhook received for unknown provider identifier: mailing_id=%s, identifier=%s",
                    mailing_id,
                    raw_identifier,
                )
                ignored_count += 1
                outcomes.append(
                    WebhookItemOutcome(
                        mailing_id=mailing_id,
                        identifier=str(raw_identifier) if raw_identifier else None,
                        outreach_id=None,
                        status="ignored",
                        action="unknown_identifier",
                        reason="No matching Outreach record found for provider identifiers.",
                    )
                )
                continue

            # Step 4b: Tenant Isolation Guard
            if org_id_hint is not None and outreach.organization_id != org_id_hint:
                logger.error(
                    "Tenant isolation violation: Outreach %s belongs to org %s, not caller org %s",
                    outreach.id,
                    outreach.organization_id,
                    org_id_hint,
                )
                raise PoplarCrossTenantError(
                    f"Cross-tenant access violation: Outreach record {outreach.id} does not belong to the requested organization."
                )

            # Step 4c: Check for Out-of-Order or Non-Modifiable State
            if outreach.status == "cancelled":
                logger.info("Outreach %s is cancelled; ignoring status mutation.", outreach.id)
                ignored_count += 1
                outcomes.append(
                    WebhookItemOutcome(
                        mailing_id=mailing_id,
                        identifier=str(raw_identifier) if raw_identifier else None,
                        outreach_id=outreach.id,
                        status="ignored",
                        action="outreach_cancelled",
                        reason="Outreach is already cancelled; mutations ignored.",
                    )
                )
                continue

            # Step 4d: Idempotency & Duplicate Event Detection
            # Check if this exact conversion / attribution event has already been recorded
            dedup_key = str(conversion_id or order_id or f"{mailing_id}:{event_timestamp.isoformat()}")
            if self._is_duplicate_event(outreach.id, dedup_key):
                duplicate_count += 1
                outcomes.append(
                    WebhookItemOutcome(
                        mailing_id=mailing_id,
                        identifier=str(raw_identifier) if raw_identifier else None,
                        outreach_id=outreach.id,
                        status="duplicate",
                        action="already_recorded",
                        reason=f"Event with key {dedup_key} was already recorded for this outreach.",
                        duplicate=True,
                    )
                )
                continue

            # Step 4e: Record State Transition and OutreachEvent
            # Physical mail direct response/conversion maps to 'replied' event in domain model
            if outreach.status == "sending":
                outreach.status = "sent"

            if not outreach.first_replied_at:
                outreach.first_replied_at = event_timestamp

            # Create immutable OutreachEvent
            event_metadata: Dict[str, Any] = {
                "provider": "poplar",
                "mailing_id": mailing_id or outreach.provider_message_id,
                "dedup_key": dedup_key,
                "order_id": order_id,
                "conversion_id": conversion_id,
                "conversion_amount": float(amount) if amount is not None else None,
                "raw_status": item.get("status", "converted"),
                "event_type": event_type,
            }

            outreach_event = OutreachEvent(
                organization_id=outreach.organization_id,
                outreach_id=outreach.id,
                event_type="replied",
                event_metadata=event_metadata,
                occurred_at=event_timestamp,
            )
            self.db.add(outreach_event)

            # Step 4f: Update CampaignContact enrollment status if in-flight
            if outreach.campaign_contact_id:
                enrollment = self.db.get(CampaignContact, outreach.campaign_contact_id)
                if enrollment and enrollment.enrollment_status in ("queued", "in_progress"):
                    enrollment.enrollment_status = "replied"

            self.db.commit()

            processed_count += 1
            outcomes.append(
                WebhookItemOutcome(
                    mailing_id=mailing_id,
                    identifier=str(raw_identifier) if raw_identifier else None,
                    outreach_id=outreach.id,
                    status="processed",
                    action="replied",
                )
            )

        overall_status = "success"
        if processed_count == 0 and duplicate_count > 0 and ignored_count == 0:
            overall_status = "duplicate"
        elif processed_count == 0 and ignored_count > 0:
            overall_status = "ignored"

        return PoplarWebhookResult(
            status=overall_status,
            event_type=event_type,
            total_items=len(attribution_items),
            processed_count=processed_count,
            duplicate_count=duplicate_count,
            ignored_count=ignored_count,
            outcomes=outcomes,
        )

    def _match_outreach(
        self,
        mailing_id: Optional[str] = None,
        identifier: Optional[Union[str, uuid.UUID]] = None,
    ) -> Optional[Outreach]:
        """
        Locates the authoritative Outreach record by provider_message_id or internal UUID identifier.
        """
        # 1. Match by Poplar mailing_id in provider_message_id
        if mailing_id:
            outreach = self.db.execute(
                select(Outreach).where(Outreach.provider_message_id == str(mailing_id))
            ).scalars().first()
            if outreach:
                return outreach

        # 2. Match by internal UUID identifier sent in recipient payload
        if identifier:
            try:
                target_uuid = uuid.UUID(str(identifier))
                outreach = self.db.get(Outreach, target_uuid)
                if outreach:
                    return outreach
            except (ValueError, TypeError):
                pass

        return None

    def _is_duplicate_event(self, outreach_id: uuid.UUID, dedup_key: str) -> bool:
        """
        Checks whether an event with the given dedup_key has already been recorded for this outreach.
        """
        existing_events = self.db.execute(
            select(OutreachEvent).where(
                OutreachEvent.outreach_id == outreach_id,
                OutreachEvent.event_type == "replied",
            )
        ).scalars().all()

        for ev in existing_events:
            meta = ev.event_metadata or {}
            if meta.get("dedup_key") == dedup_key:
                return True
            if meta.get("conversion_id") and meta.get("conversion_id") == dedup_key:
                return True
            if meta.get("order_id") and meta.get("order_id") == dedup_key:
                return True

        return False
