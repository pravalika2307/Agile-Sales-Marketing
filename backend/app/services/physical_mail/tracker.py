"""
Physical Mail fulfillment status polling service.

Per verified Poplar architecture:
Poplar does NOT deliver granular real-time USPS scan webhooks to generic external URLs.
Fulfillment status tracking (production, in_transit, delivered, exception, suppressed)
is retrieved programmatically via GET /v1/mailing/:id.

This service polls and synchronizes in-flight direct mail statuses idempotently.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.outreach import Outreach, OutreachEvent
from app.services.physical_mail.poplar_client import (
    PoplarClient,
    PoplarError,
    PoplarNotFoundError,
    get_poplar_client,
)

logger = logging.getLogger(__name__)


@dataclass
class MailingSyncResult:
    outreach_id: uuid.UUID
    mailing_id: str
    previous_status: str
    new_status: str
    poplar_status: str
    updated: bool
    error: Optional[str] = None


@dataclass
class CampaignSyncSummary:
    campaign_id: uuid.UUID
    total_checked: int
    total_updated: int
    total_delivered: int
    total_failed: int
    results: List[MailingSyncResult]


class PhysicalMailTracker:
    """
    Synchronizes fulfillment and USPS tracking status for in-flight physical mailings
    by querying Poplar's GET /v1/mailing/:id endpoint.
    """

    def __init__(self, db: Session, client: Optional[PoplarClient] = None) -> None:
        self.db = db
        self.client = client or get_poplar_client()

    def sync_outreach_mailing(
        self,
        outreach: Outreach,
        simulated_override_status: Optional[str] = None,
    ) -> MailingSyncResult:
        """
        Polls the status of a single in-flight physical mail piece from Poplar.
        """
        mailing_id = outreach.provider_message_id
        if not mailing_id:
            return MailingSyncResult(
                outreach_id=outreach.id,
                mailing_id="none",
                previous_status=outreach.status,
                new_status=outreach.status,
                poplar_status="unknown",
                updated=False,
                error="Outreach record has no provider_message_id",
            )

        previous_status = outreach.status
        now_utc = datetime.now(timezone.utc)

        # Handle mock mailings in test mode safely without live HTTP calls
        if mailing_id.startswith("mlg_mock_"):
            poplar_status = simulated_override_status or "in_transit"
            details = {"simulated": True, "note": "Mock test environment status"}
        else:
            try:
                response = self.client.get_mailing(mailing_id)
                poplar_status = str(response.get("status", "unknown")).lower()
                details = response
            except PoplarNotFoundError:
                logger.warning("Poplar mailing %s not found on provider.", mailing_id)
                return MailingSyncResult(
                    outreach_id=outreach.id,
                    mailing_id=mailing_id,
                    previous_status=previous_status,
                    new_status=previous_status,
                    poplar_status="not_found",
                    updated=False,
                    error="Mailing not found on Poplar API",
                )
            except PoplarError as exc:
                logger.error("Error polling Poplar mailing %s: %s", mailing_id, exc)
                return MailingSyncResult(
                    outreach_id=outreach.id,
                    mailing_id=mailing_id,
                    previous_status=previous_status,
                    new_status=previous_status,
                    poplar_status="error",
                    updated=False,
                    error=str(exc),
                )

        updated = False
        new_status = previous_status

        # Map Poplar fulfillment states to Outreach domain statuses
        if poplar_status == "delivered":
            if outreach.status in ("draft", "sending", "scheduled"):
                outreach.status = "sent"
                new_status = "sent"
                updated = True

            if not outreach.first_delivered_at:
                outreach.first_delivered_at = now_utc
                updated = True

            # Idempotently record delivered event
            if not self._has_event_type(outreach.id, "delivered"):
                self.db.add(
                    OutreachEvent(
                        organization_id=outreach.organization_id,
                        outreach_id=outreach.id,
                        event_type="delivered",
                        event_metadata={"poplar_status": poplar_status, "details": details},
                        occurred_at=now_utc,
                    )
                )
                updated = True

        elif poplar_status in ("exception", "suppressed"):
            if outreach.status != "failed":
                outreach.status = "failed"
                new_status = "failed"
                updated = True

            if not outreach.first_bounced_at:
                outreach.first_bounced_at = now_utc
                updated = True

            if not self._has_event_type(outreach.id, "failed"):
                self.db.add(
                    OutreachEvent(
                        organization_id=outreach.organization_id,
                        outreach_id=outreach.id,
                        event_type="failed",
                        event_metadata={"poplar_status": poplar_status, "details": details},
                        occurred_at=now_utc,
                    )
                )
                updated = True

        elif poplar_status in ("in_transit", "production", "processing", "mailing_queued"):
            # Still in production or in-flight with USPS; remains 'sending'
            if outreach.status == "draft":
                outreach.status = "sending"
                new_status = "sending"
                updated = True

        if updated:
            self.db.commit()
            self.db.refresh(outreach)

        return MailingSyncResult(
            outreach_id=outreach.id,
            mailing_id=mailing_id,
            previous_status=previous_status,
            new_status=new_status,
            poplar_status=poplar_status,
            updated=updated,
        )

    def sync_campaign_mailings(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
    ) -> CampaignSyncSummary:
        """
        Polls and synchronizes all in-flight physical mailings for a given campaign.
        """
        in_flight_mailings = self.db.execute(
            select(Outreach).where(
                Outreach.organization_id == org_id,
                Outreach.campaign_id == campaign_id,
                Outreach.channel == "physical_mail",
                Outreach.status.in_(["sending", "draft"]),
            )
        ).scalars().all()

        results: List[MailingSyncResult] = []
        total_delivered = 0
        total_failed = 0
        total_updated = 0

        for outreach in in_flight_mailings:
            res = self.sync_outreach_mailing(outreach)
            results.append(res)
            if res.updated:
                total_updated += 1
            if res.new_status == "sent" and res.poplar_status == "delivered":
                total_delivered += 1
            elif res.new_status == "failed":
                total_failed += 1

        return CampaignSyncSummary(
            campaign_id=campaign_id,
            total_checked=len(in_flight_mailings),
            total_updated=total_updated,
            total_delivered=total_delivered,
            total_failed=total_failed,
            results=results,
        )

    def _has_event_type(self, outreach_id: uuid.UUID, event_type: str) -> bool:
        """Checks if an OutreachEvent of a particular type already exists."""
        existing = self.db.execute(
            select(OutreachEvent).where(
                OutreachEvent.outreach_id == outreach_id,
                OutreachEvent.event_type == event_type,
            )
        ).scalars().first()
        return existing is not None
