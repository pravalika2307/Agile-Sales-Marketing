"""Campaign Execution Job Service.

Provides durable, asynchronous campaign step execution management:
- Enqueuing jobs with frozen immutable execution payloads
- Atomic job claiming with PostgreSQL row-level locks (FOR UPDATE SKIP LOCKED)
- Worker lease management, fencing tokens, and heartbeat renewal
- Exponential backoff retry logic for transient provider failures
- Ambiguous provider outcome detection (dispatch_unknown) and reconciliation
- Anti-orphaning entity deletion safeguards
- Automatic reclamation of expired or crashed worker leases
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_execution_job import (
    ALLOWED_JOB_CHANNELS,
    ALLOWED_JOB_STATUSES,
    AUTODISPATCH_ALLOWED_CHANNELS,
    CampaignExecutionJob,
)
from app.models.crm import Contact

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class CampaignJobError(Exception):
    """Base exception for campaign job errors."""
    pass


class LeaseLostError(CampaignJobError):
    """Raised when a worker attempts to update a job whose lease has expired or been reclaimed."""
    pass


class InvalidPayloadError(CampaignJobError):
    """Raised when an execution payload is malformed or missing required channel parameters."""
    pass


# ── Service Implementation ───────────────────────────────────────────────────

class CampaignExecutionJobService:
    """Service managing persistent campaign execution jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Enqueueing ────────────────────────────────────────────────────────────

    def enqueue_step_job(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        campaign_contact_id: uuid.UUID,
        contact_id: uuid.UUID,
        step_number: int,
        channel: str = "email",
        scheduled_at: Optional[datetime] = None,
        step_identifier: Optional[str] = None,
        campaign_step_id: Optional[uuid.UUID] = None,
        execution_payload: Optional[Dict[str, Any]] = None,
        campaign_name_snapshot: Optional[str] = None,
        recipient_snapshot: Optional[str] = None,
        max_attempts: int = 3,
        auto_commit: bool = True,
    ) -> CampaignExecutionJob:
        """
        Enqueues an immutable persistent execution job for a campaign step.
        Guarantees idempotency via (org_id:campaign_contact_id:step_number).
        If the job already exists, returns the existing job without re-executing.
        """
        if channel not in ALLOWED_JOB_CHANNELS:
            raise InvalidPayloadError(f"Unsupported channel: {channel}. Allowed: {ALLOWED_JOB_CHANNELS}")

        # Validate and prepare execution payload
        payload = execution_payload or {}
        if not isinstance(payload, dict):
            raise InvalidPayloadError("execution_payload must be a valid JSON dictionary")

        # Validate required channel parameters before creation
        self._validate_payload_for_channel(channel, payload)

        # Restrict automated dispatch: physical_mail and linkedin must start in 'held'
        if channel not in AUTODISPATCH_ALLOWED_CHANNELS:
            initial_status = "held"
        else:
            initial_status = "pending"

        target_scheduled_at = scheduled_at or datetime.now(timezone.utc)
        if target_scheduled_at.tzinfo is None:
            target_scheduled_at = target_scheduled_at.replace(tzinfo=timezone.utc)

        idempotency_key = f"{org_id}:{campaign_contact_id}:{step_number}"

        # Check existing job for durable idempotency
        existing = (
            self.db.query(CampaignExecutionJob)
            .filter(CampaignExecutionJob.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return existing

        job_id = uuid.uuid4()

        # Fetch audit snapshots if not provided
        if not campaign_name_snapshot:
            camp = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if camp:
                campaign_name_snapshot = camp.name

        if not recipient_snapshot:
            contact = self.db.query(Contact).filter(Contact.id == contact_id).first()
            if contact:
                recipient_snapshot = contact.email or contact.phone or f"Contact:{contact.id}"

        # Insert job (using PostgreSQL ON CONFLICT if running on postgresql)
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(CampaignExecutionJob).values(
                id=job_id,
                organization_id=org_id,
                campaign_id=campaign_id,
                campaign_contact_id=campaign_contact_id,
                contact_id=contact_id,
                campaign_step_id=campaign_step_id,
                step_number=step_number,
                step_identifier=step_identifier,
                channel=channel,
                status=initial_status,
                scheduled_at=target_scheduled_at,
                attempts=0,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
                execution_payload=payload,
                campaign_name_snapshot=campaign_name_snapshot,
                recipient_snapshot=recipient_snapshot,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ).on_conflict_do_nothing(
                index_elements=["idempotency_key"]
            )
            self.db.execute(stmt)
        else:
            new_job = CampaignExecutionJob(
                id=job_id,
                organization_id=org_id,
                campaign_id=campaign_id,
                campaign_contact_id=campaign_contact_id,
                contact_id=contact_id,
                campaign_step_id=campaign_step_id,
                step_number=step_number,
                step_identifier=step_identifier,
                channel=channel,
                status=initial_status,
                scheduled_at=target_scheduled_at,
                attempts=0,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
                execution_payload=payload,
                campaign_name_snapshot=campaign_name_snapshot,
                recipient_snapshot=recipient_snapshot,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(new_job)

        if auto_commit:
            self.db.commit()
        else:
            self.db.flush()

        job = (
            self.db.query(CampaignExecutionJob)
            .filter(CampaignExecutionJob.idempotency_key == idempotency_key)
            .first()
        )
        if not job:
            raise CampaignJobError(f"Failed to retrieve or create job for idempotency key: {idempotency_key}")

        logger.info(
            "Enqueued execution job id=%s org=%s step=%d channel=%s status=%s scheduled_at=%s",
            job.id, org_id, step_number, channel, job.status, job.scheduled_at.isoformat(),
        )
        return job

    def _validate_payload_for_channel(self, channel: str, payload: Dict[str, Any]) -> None:
        """Validates that required dispatch fields exist in the execution payload."""
        if channel == "email":
            has_subject = bool(payload.get("rendered_subject") or payload.get("subject_template") or payload.get("subject"))
            has_body = bool(payload.get("rendered_body") or payload.get("body_template") or payload.get("body"))
            if not has_subject or not has_body:
                raise InvalidPayloadError("Email execution payload requires non-empty subject and body templates")

        elif channel == "voice":
            has_voice = bool(
                payload.get("retell_agent_id")
                or payload.get("script")
                or payload.get("body_template")
                or payload.get("subject")
                or payload.get("title")
            )
            if not has_voice:
                raise InvalidPayloadError("Voice execution payload requires agent ID, script, or title")

        elif channel == "sms":
            has_sms = bool(payload.get("rendered_body") or payload.get("body_template") or payload.get("body"))
            if not has_sms:
                raise InvalidPayloadError("SMS execution payload requires non-empty body template")

    # ── Claiming & Leases ─────────────────────────────────────────────────────

    def claim_next_jobs(
        self,
        org_id: uuid.UUID,
        worker_id: str,
        batch_size: int = 10,
        lease_duration_seconds: int = 120,
        now: Optional[datetime] = None,
        channels: Optional[Set[str]] = None,
    ) -> List[CampaignExecutionJob]:
        """
        Atomically claims a batch of eligible jobs for an organization using
        SELECT ... FOR UPDATE SKIP LOCKED.
        Sets lease_token, worker_id, lease_expires_at, and transitions status to 'processing'.
        """
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        target_channels = channels or AUTODISPATCH_ALLOWED_CHANNELS

        query = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.organization_id == org_id,
                CampaignExecutionJob.status.in_(["pending", "retry_scheduled"]),
                CampaignExecutionJob.scheduled_at <= current_time,
                CampaignExecutionJob.channel.in_(target_channels),
                CampaignExecutionJob.campaign_id.isnot(None),
                CampaignExecutionJob.contact_id.isnot(None),
                CampaignExecutionJob.campaign_contact_id.isnot(None),
            )
            .order_by(CampaignExecutionJob.scheduled_at.asc())
            .limit(batch_size)
        )

        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        jobs = query.all()
        if not jobs:
            return []

        lease_expires = current_time + timedelta(seconds=lease_duration_seconds)
        claimed: List[CampaignExecutionJob] = []

        for job in jobs:
            token = uuid.uuid4()
            job.status = "processing"
            job.worker_id = worker_id
            job.lease_token = token
            job.leased_at = current_time
            job.lease_expires_at = lease_expires
            job.heartbeat_at = current_time
            job.updated_at = current_time
            claimed.append(job)

        self.db.commit()
        logger.info("Worker %s claimed %d jobs for org %s", worker_id, len(claimed), org_id)
        return claimed

    def renew_lease(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_token: uuid.UUID,
        extension_seconds: int = 120,
        now: Optional[datetime] = None,
    ) -> bool:
        """Heartbeat renewal: Extends lease_expires_at for long-running jobs."""
        current_time = now or datetime.now(timezone.utc)
        new_expiry = current_time + timedelta(seconds=extension_seconds)

        res = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.id == job_id,
                CampaignExecutionJob.worker_id == worker_id,
                CampaignExecutionJob.lease_token == lease_token,
                CampaignExecutionJob.status == "processing",
            )
            .update(
                {
                    "lease_expires_at": new_expiry,
                    "heartbeat_at": current_time,
                    "updated_at": current_time,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return res > 0

    def mark_dispatch_started(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_token: uuid.UUID,
        now: Optional[datetime] = None,
    ) -> bool:
        """Records dispatch_started_at immediately before initiating external provider call."""
        current_time = now or datetime.now(timezone.utc)
        res = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.id == job_id,
                CampaignExecutionJob.worker_id == worker_id,
                CampaignExecutionJob.lease_token == lease_token,
                CampaignExecutionJob.status == "processing",
            )
            .update(
                {
                    "dispatch_started_at": current_time,
                    "updated_at": current_time,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        if res == 0:
            raise LeaseLostError(f"Worker {worker_id} lost lease for job {job_id} before dispatch start")
        return True

    # ── State Finalization ────────────────────────────────────────────────────

    def complete_job(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_token: uuid.UUID,
        outreach_id: Optional[uuid.UUID] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """CAS completion: Transitions job to 'completed' with fencing token verification."""
        current_time = now or datetime.now(timezone.utc)
        res = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.id == job_id,
                CampaignExecutionJob.worker_id == worker_id,
                CampaignExecutionJob.lease_token == lease_token,
                CampaignExecutionJob.status == "processing",
            )
            .update(
                {
                    "status": "completed",
                    "outreach_id": outreach_id,
                    "lease_token": None,
                    "lease_expires_at": None,
                    "updated_at": current_time,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        if res == 0:
            raise LeaseLostError(f"Worker {worker_id} lost lease for job {job_id}; cannot mark completed")
        logger.info("Job %s completed successfully by worker %s (outreach_id=%s)", job_id, worker_id, outreach_id)
        return True

    def fail_job(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_token: uuid.UUID,
        error_message: str,
        is_permanent: bool = False,
        now: Optional[datetime] = None,
    ) -> bool:
        """CAS failure handling: Schedules retry with backoff or marks failed."""
        current_time = now or datetime.now(timezone.utc)
        job = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.id == job_id,
                CampaignExecutionJob.worker_id == worker_id,
                CampaignExecutionJob.lease_token == lease_token,
                CampaignExecutionJob.status == "processing",
            )
            .first()
        )
        if not job:
            raise LeaseLostError(f"Worker {worker_id} lost lease for job {job_id}; cannot fail job")

        new_attempts = job.attempts + 1
        will_retry = (new_attempts < job.max_attempts) and not is_permanent

        if will_retry:
            backoff_seconds = min(3600, 30 * (2 ** (new_attempts - 1)))
            next_scheduled = current_time + timedelta(seconds=backoff_seconds)
            new_status = "retry_scheduled"
        else:
            next_scheduled = job.scheduled_at
            new_status = "failed"

        job.attempts = new_attempts
        job.status = new_status
        job.scheduled_at = next_scheduled
        job.last_error = error_message[:2000] if error_message else None
        job.lease_token = None
        job.lease_expires_at = None
        job.updated_at = current_time

        self.db.commit()
        logger.warning(
            "Job %s failed (attempt %d/%d, status=%s): %s",
            job_id, new_attempts, job.max_attempts, new_status, error_message,
        )
        return True

    def mark_dispatch_unknown(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_token: uuid.UUID,
        reason: str,
        now: Optional[datetime] = None,
    ) -> bool:
        """Transitions job to 'dispatch_unknown' when provider outcome is indeterminate."""
        current_time = now or datetime.now(timezone.utc)
        res = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.id == job_id,
                CampaignExecutionJob.worker_id == worker_id,
                CampaignExecutionJob.lease_token == lease_token,
                CampaignExecutionJob.status == "processing",
            )
            .update(
                {
                    "status": "dispatch_unknown",
                    "last_error": reason[:2000] if reason else "Ambiguous provider outcome",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "updated_at": current_time,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        if res == 0:
            raise LeaseLostError(f"Worker {worker_id} lost lease for job {job_id}; cannot set dispatch_unknown")
        logger.warning("Job %s marked dispatch_unknown: %s", job_id, reason)
        return True

    # ── Recovery & Safeguards ─────────────────────────────────────────────────

    def reclaim_expired_leases(
        self,
        now: Optional[datetime] = None,
    ) -> int:
        """Scans for expired worker leases and safely reclaims them."""
        current_time = now or datetime.now(timezone.utc)
        query = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.status == "processing",
                CampaignExecutionJob.lease_expires_at < current_time,
            )
        )
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        expired_jobs = query.all()
        if not expired_jobs:
            return 0

        reclaimed_count = 0
        for job in expired_jobs:
            if job.dispatch_started_at is not None:
                job.status = "dispatch_unknown"
                job.last_error = (
                    f"Lease expired after dispatch was initiated by worker {job.worker_id}. "
                    "Held in dispatch_unknown for reconciliation to prevent duplicate sending."
                )
            else:
                job.attempts += 1
                if job.attempts < job.max_attempts:
                    job.status = "pending"
                    job.last_error = f"Recovered from crashed or expired worker {job.worker_id}"
                else:
                    job.status = "failed"
                    job.last_error = f"Worker lease expired and max attempts exceeded ({job.attempts}/{job.max_attempts})"

            job.lease_token = None
            job.lease_expires_at = None
            job.updated_at = current_time
            reclaimed_count += 1

        self.db.commit()
        logger.info("Reclaimed %d expired worker leases", reclaimed_count)
        return reclaimed_count

    def reconcile_dispatch_unknown_job(
        self,
        job_id: uuid.UUID,
        confirmed_delivered: bool,
        provider_message_id: Optional[str] = None,
        outreach_id: Optional[uuid.UUID] = None,
        now: Optional[datetime] = None,
    ) -> CampaignExecutionJob:
        """Reconciles a job in 'dispatch_unknown' status after checking provider delivery logs."""
        current_time = now or datetime.now(timezone.utc)
        job = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.id == job_id,
                CampaignExecutionJob.status == "dispatch_unknown",
            )
            .first()
        )
        if not job:
            raise CampaignJobError(f"Job {job_id} not found in dispatch_unknown status")

        if confirmed_delivered:
            job.status = "completed"
            job.outreach_id = outreach_id or job.outreach_id
            job.last_error = f"Reconciled: delivery confirmed by provider (id={provider_message_id})"
        else:
            job.attempts += 1
            if job.attempts < job.max_attempts:
                job.status = "retry_scheduled"
                job.scheduled_at = current_time + timedelta(seconds=60)
                job.last_error = "Reconciled: non-delivery confirmed by provider; scheduled retry"
            else:
                job.status = "failed"
                job.last_error = "Reconciled: non-delivery confirmed; max attempts reached"

        job.updated_at = current_time
        self.db.commit()
        logger.info("Reconciled job %s -> %s (delivered=%s)", job_id, job.status, confirmed_delivered)
        return job

    def cancel_active_jobs_for_enrollment(
        self,
        campaign_contact_id: uuid.UUID,
        reason: str = "Enrollment stopped or cancelled",
        now: Optional[datetime] = None,
    ) -> int:
        """Safely cancels or holds active jobs when an enrollment is stopped."""
        current_time = now or datetime.now(timezone.utc)
        count = (
            self.db.query(CampaignExecutionJob)
            .filter(
                CampaignExecutionJob.campaign_contact_id == campaign_contact_id,
                CampaignExecutionJob.status.in_(["pending", "processing", "retry_scheduled", "dispatch_unknown"]),
            )
            .update(
                {
                    "status": "held",
                    "last_error": reason[:2000],
                    "lease_token": None,
                    "lease_expires_at": None,
                    "updated_at": current_time,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        logger.info("Cancelled %d active jobs for enrollment %s: %s", count, campaign_contact_id, reason)
        return count
