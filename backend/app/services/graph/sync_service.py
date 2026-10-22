"""Synchronization and query service for Microsoft Graph inbound email integration."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.crm import Company, Contact
from app.models.inbound_email import GraphMailboxCheckpoint, GraphSyncRun, InboundEmail
from app.models.lead import Lead
from app.schemas.inbound_email import (
    GraphCheckpointStatusResponse,
    GraphSyncResultResponse,
    InboundEmailDetailResponse,
    InboundEmailListResponse,
    InboundEmailResponse,
    MatchedEntityInfo,
)
from app.services.graph.client import GraphMessage, MicrosoftGraphClient
from app.services.graph.ingestion_service import import_graph_messages

logger = logging.getLogger(__name__)


def _build_matched_entity_summary(
    email_record: InboundEmail,
) -> Optional[MatchedEntityInfo]:
    """Helper formatting matched Contact, Lead, or Company snapshot for API responses."""
    if not (email_record.matched_contact or email_record.matched_lead or email_record.matched_company):
        return None

    info = MatchedEntityInfo()
    if email_record.matched_contact:
        c = email_record.matched_contact
        info.contact_id = c.id
        info.contact_name = f"{c.first_name} {c.last_name}".strip()
        info.contact_job_title = c.job_title
        info.contact_lead_status = c.lead_status

    if email_record.matched_lead:
        ld = email_record.matched_lead
        info.lead_id = ld.id
        info.lead_score = ld.lead_score
        info.lead_temperature = ld.lead_temperature
        info.lead_company_name = ld.company_name

    if email_record.matched_company:
        co = email_record.matched_company
        info.company_id = co.id
        info.company_name = co.name
        info.company_domain = co.domain

    return info


def get_or_create_checkpoint(
    db: Session,
    org_id: uuid.UUID,
    mailbox_address: str,
) -> Optional[GraphMailboxCheckpoint]:
    """Retrieves or initializes the persisted synchronization checkpoint for a tenant mailbox."""
    clean_box = mailbox_address.strip().lower()
    try:
        cp = (
            db.query(GraphMailboxCheckpoint)
            .filter(
                GraphMailboxCheckpoint.organization_id == org_id,
                func.lower(GraphMailboxCheckpoint.mailbox_address) == clean_box,
            )
            .first()
        )
        if not cp:
            try:
                cp = GraphMailboxCheckpoint(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    mailbox_address=clean_box,
                    delta_link=None,
                    is_syncing=False,
                    sync_started_at=None,
                    last_sync_status="idle",
                    total_imported=0,
                )
                db.add(cp)
                db.commit()
                db.refresh(cp)
            except IntegrityError:
                # Concurrent worker created checkpoint row simultaneously
                db.rollback()
                cp = (
                    db.query(GraphMailboxCheckpoint)
                    .filter(
                        GraphMailboxCheckpoint.organization_id == org_id,
                        func.lower(GraphMailboxCheckpoint.mailbox_address) == clean_box,
                    )
                    .first()
                )
        return cp
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("GraphMailboxCheckpoint table not yet migrated: %s", exc)
        return None


def acquire_sync_lock(
    db: Session,
    org_id: uuid.UUID,
    mailbox_address: str,
) -> bool:
    """
    Attempts to atomically acquire a synchronization lock for the specified mailbox.
    Safe across multiple concurrent workers and FastAPI instances.

    1. Uses row-level pessimistic locking (with_for_update) on existing checkpoints.
    2. Handles concurrent first-time checkpoint creation conflicts via IntegrityError and rollback.
    3. Prevents overlapping sync jobs from executing concurrently.
    4. Automatically reclaims stale locks if the lock timeout has expired.
    """
    clean_box = mailbox_address.strip().lower()
    now = datetime.now(timezone.utc)
    lock_timeout_secs = settings.MICROSOFT_GRAPH_SYNC_LOCK_TIMEOUT_SECONDS

    try:
        # Step 1: Query with row lock
        cp = (
            db.query(GraphMailboxCheckpoint)
            .filter(
                GraphMailboxCheckpoint.organization_id == org_id,
                func.lower(GraphMailboxCheckpoint.mailbox_address) == clean_box,
            )
            .with_for_update()
            .first()
        )

        if not cp:
            # Step 2: Row doesn't exist yet, attempt atomic insert with is_syncing=True
            try:
                cp = GraphMailboxCheckpoint(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    mailbox_address=clean_box,
                    delta_link=None,
                    is_syncing=True,
                    sync_started_at=now,
                    last_sync_status="running",
                    total_imported=0,
                )
                db.add(cp)
                db.commit()
                return True
            except IntegrityError:
                # Concurrent worker inserted checkpoint simultaneously.
                db.rollback()
                # Re-query the checkpoint with row lock to evaluate its state
                cp = (
                    db.query(GraphMailboxCheckpoint)
                    .filter(
                        GraphMailboxCheckpoint.organization_id == org_id,
                        func.lower(GraphMailboxCheckpoint.mailbox_address) == clean_box,
                    )
                    .with_for_update()
                    .first()
                )
                if not cp:
                    return False

        # Step 3: Evaluate lock state
        if cp.is_syncing and cp.sync_started_at:
            started_at = (
                cp.sync_started_at.replace(tzinfo=timezone.utc)
                if cp.sync_started_at.tzinfo is None
                else cp.sync_started_at
            )
            elapsed = (now - started_at).total_seconds()
            if elapsed < lock_timeout_secs:
                logger.warning(
                    "Mailbox sync lock active for %s (started %ds ago). Overlapping job blocked.",
                    clean_box,
                    int(elapsed),
                )
                return False
            else:
                logger.warning(
                    "Stale sync lock detected for %s (held for %ds > timeout %ds). Reclaiming lock.",
                    clean_box,
                    int(elapsed),
                    lock_timeout_secs,
                )

        cp.is_syncing = True
        cp.sync_started_at = now
        cp.last_sync_status = "running"
        db.commit()
        return True

    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("Lock acquisition fallback for unmigrated table: %s", exc)
        return True


def release_sync_lock(
    db: Session,
    org_id: uuid.UUID,
    mailbox_address: str,
    status: str,
    new_delta_link: Optional[str] = None,
    imported_count: int = 0,
    error_msg: Optional[str] = None,
) -> None:
    """Releases the synchronization lock and persists updated checkpoint state."""
    clean_box = mailbox_address.strip().lower()
    now = datetime.now(timezone.utc)
    try:
        cp = (
            db.query(GraphMailboxCheckpoint)
            .filter(
                GraphMailboxCheckpoint.organization_id == org_id,
                func.lower(GraphMailboxCheckpoint.mailbox_address) == clean_box,
            )
            .with_for_update()
            .first()
        )
        if cp:
            cp.is_syncing = False
            cp.sync_started_at = None
            cp.last_sync_status = status
            if status in ("completed", "partial"):
                if new_delta_link:
                    cp.delta_link = new_delta_link
                cp.total_imported += imported_count
                cp.error_message = None
                if status == "completed":
                    cp.last_successful_sync_at = now
            elif status == "failed":
                cp.error_message = error_msg
            cp.updated_at = now
            db.commit()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("Lock release fallback for unmigrated table: %s", exc)


def get_checkpoint_status(
    db: Session,
    org_id: uuid.UUID,
    mailbox_address: Optional[str] = None,
) -> GraphCheckpointStatusResponse:
    """Returns the current checkpoint and concurrency status for the support mailbox."""
    target_box = (mailbox_address or settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX).strip().lower()
    try:
        cp = (
            db.query(GraphMailboxCheckpoint)
            .filter(
                GraphMailboxCheckpoint.organization_id == org_id,
                func.lower(GraphMailboxCheckpoint.mailbox_address) == target_box,
            )
            .first()
        )
        if not cp:
            return GraphCheckpointStatusResponse(
                mailbox=target_box,
                has_checkpoint=False,
                is_syncing=False,
                last_sync_status="idle",
                last_successful_sync_at=None,
                sync_started_at=None,
                total_imported=0,
                error_message=None,
            )
        return GraphCheckpointStatusResponse(
            mailbox=cp.mailbox_address,
            has_checkpoint=bool(cp.delta_link),
            is_syncing=cp.is_syncing,
            last_sync_status=cp.last_sync_status,
            last_successful_sync_at=cp.last_successful_sync_at,
            sync_started_at=cp.sync_started_at,
            total_imported=cp.total_imported,
            error_message=cp.error_message,
        )
    except (ProgrammingError, OperationalError):
        db.rollback()
        return GraphCheckpointStatusResponse(
            mailbox=target_box,
            has_checkpoint=False,
            is_syncing=False,
            last_sync_status="unmigrated",
            last_successful_sync_at=None,
            sync_started_at=None,
            total_imported=0,
            error_message="Checkpoint table not yet created in database.",
        )


def sync_support_mailbox(
    db: Session,
    org_id: uuid.UUID,
    max_messages: int = 50,
    folder: str = "Inbox",
    trigger: str = "manual",
    use_delta: bool = True,
    client_override: Optional[MicrosoftGraphClient] = None,
    mock_messages: Optional[List[GraphMessage]] = None,
) -> GraphSyncResultResponse:
    """
    Executes a synchronization run from the approved Microsoft Graph support mailbox.

    SAFETY & RELIABILITY CONTROLS:
    1. Fail-closed: Requires MICROSOFT_GRAPH_ENABLED=True for live Graph calls unless mock_messages are provided.
    2. Mailbox Isolation: Targets ONLY settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX.
    3. Multi-Tenant Isolation: Ingested emails are bound strictly to caller org_id.
    4. Concurrency Guard: Prevents overlapping sync runs using an acquired lock.
    5. Incremental Delta Checkpoint: Uses Microsoft Graph Delta query with persisted @odata.deltaLink
       so restarts and periodic runs only process new/changed messages.
    6. Strictly Read-Only: Never calls PATCH, DELETE, or SEND endpoints on Exchange Online.
    """
    target_mailbox = settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX
    max_messages = min(max(max_messages, 1), 250)
    run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 1. Check live sending/sync guard
    is_live_allowed = settings.is_graph_live_sync_allowed or bool(mock_messages is not None)

    if not is_live_allowed:
        logger.info(
            "Microsoft Graph live sync blocked by safety guard (MICROSOFT_GRAPH_ENABLED=False). "
            "No external Microsoft Graph requests were initiated."
        )
        return GraphSyncResultResponse(
            sync_run_id=run_id,
            organization_id=org_id,
            mailbox=target_mailbox,
            status="blocked_by_safety_guard",
            messages_fetched=0,
            messages_imported=0,
            messages_matched=0,
            messages_unmatched=0,
            messages_skipped=0,
            checkpoint_delta_link=None,
            error_message=(
                "Live Microsoft Graph synchronization is disabled by safety configuration "
                "(MICROSOFT_GRAPH_ENABLED=False). Enable MICROSOFT_GRAPH_ENABLED in .env "
                "to permit real mailbox retrieval."
            ),
            started_at=now,
            completed_at=datetime.now(timezone.utc),
        )

    # 2. Concurrency Lock: Prevent overlapping runs for the same mailbox
    lock_acquired = acquire_sync_lock(db, org_id, target_mailbox)
    if not lock_acquired:
        return GraphSyncResultResponse(
            sync_run_id=run_id,
            organization_id=org_id,
            mailbox=target_mailbox,
            status="skipped_concurrency_lock",
            messages_fetched=0,
            messages_imported=0,
            messages_matched=0,
            messages_unmatched=0,
            messages_skipped=0,
            checkpoint_delta_link=None,
            error_message=(
                "A synchronization run is currently active for this mailbox. "
                "Concurrency lock prevented an overlapping execution."
            ),
            started_at=now,
            completed_at=datetime.now(timezone.utc),
        )

    messages: List[GraphMessage] = []
    new_delta_link: Optional[str] = None
    error_msg: Optional[str] = None
    status = "completed"

    try:
        if mock_messages is not None:
            messages = mock_messages[:max_messages]
            new_delta_link = "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?$deltatoken=mock_delta_token"
        else:
            try:
                client = client_override or MicrosoftGraphClient()
                if use_delta:
                    # Retrieve checkpoint delta link if available
                    checkpoint = get_or_create_checkpoint(db, org_id, target_mailbox)
                    existing_delta = checkpoint.delta_link if checkpoint else None
                    delta_res = client.get_delta_messages(
                        mailbox=target_mailbox,
                        folder=folder,
                        delta_link=existing_delta,
                        max_messages=max_messages,
                    )
                    messages = delta_res[0]
                    new_delta_link = delta_res[1]
                    is_complete = getattr(delta_res, "is_complete", True)
                    if not is_complete and status == "completed":
                        status = "partial"
                else:
                    page = client.get_messages(
                        mailbox=target_mailbox,
                        folder=folder,
                        top=max_messages,
                    )
                    messages = page.messages
                    new_delta_link = page.delta_link
            except Exception as exc:
                logger.error("Error retrieving messages from Microsoft Graph: %s", exc)
                status = "failed"
                error_msg = str(exc)

        # 3. Ingest fetched messages
        ingestion = import_graph_messages(db, org_id, messages)
        if error_msg:
            ingestion.errors += 1

        completed_at = datetime.now(timezone.utc)

        # 4. Release sync lock and update checkpoint
        release_sync_lock(
            db=db,
            org_id=org_id,
            mailbox_address=target_mailbox,
            status=status if not error_msg else "failed",
            new_delta_link=new_delta_link,
            imported_count=ingestion.imported,
            error_msg=error_msg,
        )

        # 5. Record GraphSyncRun audit record if table exists
        try:
            sync_run = GraphSyncRun(
                id=run_id,
                organization_id=org_id,
                mailbox_address=target_mailbox,
                sync_trigger=trigger,
                status=status if not error_msg else "failed",
                messages_fetched=ingestion.fetched,
                messages_imported=ingestion.imported,
                messages_matched=ingestion.matched,
                messages_unmatched=ingestion.unmatched,
                messages_skipped=ingestion.skipped,
                checkpoint_delta_link=new_delta_link,
                error_message=error_msg,
                started_at=now,
                completed_at=completed_at,
                created_at=completed_at,
            )
            db.add(sync_run)
            db.commit()
        except (ProgrammingError, OperationalError) as exc:
            db.rollback()
            logger.debug("GraphSyncRun table missing or unmigrated: %s", exc)

        return GraphSyncResultResponse(
            sync_run_id=run_id,
            organization_id=org_id,
            mailbox=target_mailbox,
            status=status if not error_msg else "failed",
            messages_fetched=ingestion.fetched,
            messages_imported=ingestion.imported,
            messages_matched=ingestion.matched,
            messages_unmatched=ingestion.unmatched,
            messages_skipped=ingestion.skipped,
            checkpoint_delta_link=new_delta_link,
            error_message=error_msg,
            started_at=now,
            completed_at=completed_at,
        )

    except Exception as exc:
        db.rollback()
        release_sync_lock(
            db=db,
            org_id=org_id,
            mailbox_address=target_mailbox,
            status="failed",
            error_msg=str(exc),
        )
        raise



def list_inbound_emails(
    db: Session,
    org_id: uuid.UUID,
    status_filter: Optional[str] = None,
    review_status_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> InboundEmailListResponse:
    """
    Lists ingested inbound emails for the authenticated tenant with filtering and search.
    Safely handles unmigrated tables by returning empty results.
    """
    offset = max(page - 1, 0) * limit

    try:
        query = db.query(InboundEmail).filter(InboundEmail.organization_id == org_id)

        if status_filter and status_filter.strip().lower() != "all":
            query = query.filter(InboundEmail.sync_status == status_filter.strip().lower())

        if review_status_filter and review_status_filter.strip().lower() != "all":
            query = query.filter(InboundEmail.manual_review_status == review_status_filter.strip().lower())

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(InboundEmail.sender_email).like(term),
                    func.lower(InboundEmail.sender_name).like(term),
                    func.lower(InboundEmail.subject).like(term),
                )
            )

        total = query.count()
        unmatched_count = (
            db.query(InboundEmail)
            .filter(
                InboundEmail.organization_id == org_id,
                InboundEmail.sync_status == "unmatched",
                InboundEmail.manual_review_status == "pending",
            )
            .count()
        )
        unread_count = (
            db.query(InboundEmail)
            .filter(
                InboundEmail.organization_id == org_id,
                InboundEmail.is_read == False,
            )
            .count()
        )

        rows = query.order_by(InboundEmail.received_at.desc()).offset(offset).limit(limit).all()

        items: List[InboundEmailResponse] = []
        for r in rows:
            summary = _build_matched_entity_summary(r)
            items.append(
                InboundEmailResponse(
                    id=r.id,
                    organization_id=r.organization_id,
                    graph_message_id=r.graph_message_id,
                    graph_conversation_id=r.graph_conversation_id,
                    internet_message_id=r.internet_message_id,
                    sender_email=r.sender_email,
                    sender_name=r.sender_name,
                    recipient_email=r.recipient_email,
                    subject=r.subject,
                    body_preview=r.body_preview,
                    received_at=r.received_at,
                    is_read=r.is_read,
                    has_attachments=r.has_attachments,
                    sync_status=r.sync_status,
                    manual_review_status=r.manual_review_status,
                    matched_contact_id=r.matched_contact_id,
                    matched_lead_id=r.matched_lead_id,
                    matched_company_id=r.matched_company_id,
                    matched_entity=summary,
                    created_at=r.created_at,
                )
            )

        return InboundEmailListResponse(
            items=items,
            total=total,
            unmatched_count=unmatched_count,
            unread_count=unread_count,
            page=page,
            limit=limit,
        )

    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("InboundEmail table not yet migrated: %s", exc)
        return InboundEmailListResponse(
            items=[],
            total=0,
            unmatched_count=0,
            unread_count=0,
            page=page,
            limit=limit,
        )


def get_inbound_email_detail(
    db: Session,
    org_id: uuid.UUID,
    email_id: uuid.UUID,
) -> Optional[InboundEmailDetailResponse]:
    """Retrieves full inbound email detail by ID scoped to tenant organization."""
    try:
        r = (
            db.query(InboundEmail)
            .filter(
                InboundEmail.id == email_id,
                InboundEmail.organization_id == org_id,
            )
            .first()
        )
        if not r:
            return None

        # Mark as read when opened
        if not r.is_read:
            r.is_read = True
            db.commit()
            db.refresh(r)

        summary = _build_matched_entity_summary(r)
        return InboundEmailDetailResponse(
            id=r.id,
            organization_id=r.organization_id,
            graph_message_id=r.graph_message_id,
            graph_conversation_id=r.graph_conversation_id,
            internet_message_id=r.internet_message_id,
            sender_email=r.sender_email,
            sender_name=r.sender_name,
            recipient_email=r.recipient_email,
            subject=r.subject,
            body_preview=r.body_preview,
            body_content=r.body_content,
            body_content_type=r.body_content_type,
            received_at=r.received_at,
            is_read=r.is_read,
            has_attachments=r.has_attachments,
            sync_status=r.sync_status,
            manual_review_status=r.manual_review_status,
            review_notes=r.review_notes,
            matched_contact_id=r.matched_contact_id,
            matched_lead_id=r.matched_lead_id,
            matched_company_id=r.matched_company_id,
            matched_entity=summary,
            raw_metadata=r.raw_metadata,
            is_untrusted_content=True,
            created_at=r.created_at,
        )
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("InboundEmail table not yet migrated: %s", exc)
        return None


def update_manual_review_status(
    db: Session,
    org_id: uuid.UUID,
    email_id: uuid.UUID,
    new_status: str,
    notes: Optional[str] = None,
) -> Optional[InboundEmailDetailResponse]:
    """Updates manual review status and notes for an unmatched inbound email."""
    try:
        r = (
            db.query(InboundEmail)
            .filter(
                InboundEmail.id == email_id,
                InboundEmail.organization_id == org_id,
            )
            .first()
        )
        if not r:
            return None

        r.manual_review_status = new_status
        if notes is not None:
            r.review_notes = notes
        r.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)

        return get_inbound_email_detail(db, org_id, email_id)
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("InboundEmail table not yet migrated: %s", exc)
        return None


def list_sync_runs(
    db: Session,
    org_id: uuid.UUID,
    limit: int = 20,
) -> List[GraphSyncResultResponse]:
    """Retrieves recent sync runs for the tenant organization."""
    try:
        runs = (
            db.query(GraphSyncRun)
            .filter(GraphSyncRun.organization_id == org_id)
            .order_by(GraphSyncRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [
            GraphSyncResultResponse(
                sync_run_id=r.id,
                organization_id=r.organization_id,
                mailbox=r.mailbox_address,
                status=r.status,
                messages_fetched=r.messages_fetched,
                messages_imported=r.messages_imported,
                messages_matched=r.messages_matched,
                messages_unmatched=r.messages_unmatched,
                messages_skipped=r.messages_skipped,
                error_message=r.error_message,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in runs
        ]
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        logger.debug("GraphSyncRun table not yet migrated: %s", exc)
        return []

