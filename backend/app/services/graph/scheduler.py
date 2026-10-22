"""
Automated background synchronization service for Microsoft Graph support mailbox.

Periodically synchronizes the approved support mailbox (support@agilereceivables.com)
using Microsoft Graph incremental delta queries, persisted checkpoints, and concurrency locks.

STRICT SAFETY CONTROLS:
1. Triple-Gated: Requires is_graph_configured=True, MICROSOFT_GRAPH_ENABLED=True,
   and MICROSOFT_GRAPH_AUTO_SYNC_ENABLED=True. Otherwise remains idle.
2. Mailbox Isolation: Targets solely settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX.
3. Concurrency Protection: Avoids overlapping runs using acquired locks.
4. Read-Only: Never sends, forwards, modifies, or deletes mailbox messages.
5. Structured Logging: Logs sync counts and errors without exposing message bodies or secrets.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant import Organization
from app.schemas.inbound_email import GraphSyncResultResponse
from app.services.graph.sync_service import sync_support_mailbox

logger = logging.getLogger(__name__)


class MicrosoftGraphAutoSyncService:
    """
    Manages automated background synchronization for Microsoft Graph inbound email ingestion.
    """

    def __init__(self, db: Session):
        self.db = db

    def resolve_target_organizations(self) -> List[Organization]:
        """
        Resolves organizations eligible for support mailbox synchronization.
        STRICT MULTI-TENANT ISOLATION RULES:
        1. If MICROSOFT_GRAPH_PRIMARY_ORG_ID is configured:
           - Validates UUID and resolves that specific organization.
           - If not found or invalid UUID, fails closed and returns [] (no fallback).
        2. If MICROSOFT_GRAPH_PRIMARY_ORG_ID is not configured:
           - Resolves the verified internal organization by approved slug.
           - If multiple internal organizations match (ambiguous), fails closed and returns [].
           - If no internal organization matches, fails closed and returns [].
        3. NEVER falls back to arbitrary customer tenant organizations.
        """
        if settings.MICROSOFT_GRAPH_PRIMARY_ORG_ID:
            try:
                target_uuid = uuid.UUID(settings.MICROSOFT_GRAPH_PRIMARY_ORG_ID.strip())
            except (ValueError, AttributeError) as exc:
                logger.warning(
                    "Invalid MICROSOFT_GRAPH_PRIMARY_ORG_ID '%s': %s. Failing closed.",
                    settings.MICROSOFT_GRAPH_PRIMARY_ORG_ID,
                    exc,
                )
                return []

            org = self.db.query(Organization).filter(Organization.id == target_uuid).first()
            if org:
                return [org]
            logger.warning(
                "Configured MICROSOFT_GRAPH_PRIMARY_ORG_ID '%s' not found in database. Failing closed.",
                target_uuid,
            )
            return []

        # Automatic resolution: verify internal Agile Receivables organization by approved slugs
        matching_orgs = (
            self.db.query(Organization)
            .filter(Organization.slug.in_(["agile-receivables", "agile-sales-marketing"]))
            .all()
        )
        if len(matching_orgs) == 1:
            return matching_orgs

        if len(matching_orgs) > 1:
            logger.warning(
                "Ambiguous internal organization resolution for Microsoft Graph auto-sync: "
                "multiple matching organizations found (%s). Failing closed to prevent "
                "cross-tenant email ingestion. Set MICROSOFT_GRAPH_PRIMARY_ORG_ID explicitly.",
                [o.slug for o in matching_orgs],
            )
            return []

        logger.warning(
            "No authorized internal organization found for Microsoft Graph auto-sync. "
            "Failing closed to prevent cross-tenant ingestion."
        )
        return []

    def tick(self, now: Optional[datetime] = None) -> List[GraphSyncResultResponse]:
        """
        Executes a scheduled synchronization tick.
        Blocked if fail-closed safety guards are not explicitly satisfied.
        """
        now = now or datetime.now(timezone.utc)

        if not settings.is_graph_auto_sync_allowed:
            logger.debug(
                "Microsoft Graph auto-sync tick skipped: not permitted by safety guards "
                "(is_graph_configured=%s, MICROSOFT_GRAPH_ENABLED=%s, AUTO_SYNC=%s)",
                settings.is_graph_configured,
                settings.MICROSOFT_GRAPH_ENABLED,
                settings.MICROSOFT_GRAPH_AUTO_SYNC_ENABLED,
            )
            return []

        orgs = self.resolve_target_organizations()
        if not orgs:
            logger.debug("No active organizations resolved for Microsoft Graph auto-sync.")
            return []

        results: List[GraphSyncResultResponse] = []
        for org in orgs:
            try:
                logger.info(
                    "Executing automated delta sync for org '%s' (%s) targeting mailbox '%s'",
                    org.name,
                    org.id,
                    settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX,
                )
                result = sync_support_mailbox(
                    db=self.db,
                    org_id=org.id,
                    trigger="scheduled",
                    use_delta=True,
                )
                results.append(result)
                logger.info(
                    "Auto-sync completed for org %s: status=%s, fetched=%d, imported=%d, matched=%d, unmatched=%d",
                    org.id,
                    result.status,
                    result.messages_fetched,
                    result.messages_imported,
                    result.messages_matched,
                    result.messages_unmatched,
                )
            except Exception as exc:
                logger.error("Unexpected error in auto-sync tick for org %s: %s", org.id, exc)

        return results


async def run_graph_auto_sync_loop() -> None:
    """
    Long-running background asyncio loop for unattended mailbox synchronization.
    Runs every MICROSOFT_GRAPH_SYNC_INTERVAL_MINUTES.
    """
    from app.core.database import SessionLocal

    interval_seconds = max(settings.MICROSOFT_GRAPH_SYNC_INTERVAL_MINUTES * 60, 60)
    logger.info(
        "Starting Microsoft Graph background auto-sync loop (interval: %d minutes)...",
        settings.MICROSOFT_GRAPH_SYNC_INTERVAL_MINUTES,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            db = SessionLocal()
            try:
                service = MicrosoftGraphAutoSyncService(db=db)
                service.tick()
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("Microsoft Graph background auto-sync loop cancelled.")
            break
        except Exception as exc:
            logger.error("Unhandled error in Microsoft Graph background auto-sync loop: %s", exc)
