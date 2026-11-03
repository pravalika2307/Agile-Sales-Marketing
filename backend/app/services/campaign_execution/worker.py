"""Asynchronous Campaign Job Worker Service.

Processes persistent campaign execution jobs claimed via SELECT ... FOR UPDATE SKIP LOCKED.
Guarantees:
- Strict tenant authorization (SCHEDULER_AUTHORIZED_ORGS only)
- Overdue staleness protection (SCHEDULER_MAX_OVERDUE_HOURS)
- Execution strictly from immutable execution_payload
- Fencing tokens and heartbeat lease renewals
- Safe ambiguous provider outcome handling (dispatch_unknown)
- Decoupled asynchronous step advancement
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_execution_job import (
    AUTODISPATCH_ALLOWED_CHANNELS,
    CampaignExecutionJob,
)
from app.models.crm import Contact
from app.models.outreach import Outreach
from app.services.campaign_execution.job_service import (
    CampaignExecutionJobService,
    CampaignJobError,
    LeaseLostError,
)
from app.services.outreach.base import EmailProvider, MockEmailProvider

logger = logging.getLogger(__name__)


class CampaignJobWorker:
    """Worker service that polls, claims, and executes persistent campaign execution jobs."""

    def __init__(
        self,
        db: Session,
        worker_id: Optional[str] = None,
        email_provider: Optional[EmailProvider] = None,
        retell_client: Optional[Any] = None,
        sms_provider: Optional[Any] = None,
        force_mock: bool = False,
    ) -> None:
        self.db = db
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.email_provider = email_provider
        self.retell_client = retell_client
        self.sms_provider = sms_provider
        self.force_mock = force_mock
        self.job_service = CampaignExecutionJobService(db=self.db)

    def run_single_tick(
        self,
        org_id: uuid.UUID,
        batch_size: int = 10,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Executes a single processing tick for an organization:
        1. Tenant authorization verification
        2. Reclaims expired leases
        3. Claims eligible jobs (FOR UPDATE SKIP LOCKED)
        4. Processes each job strictly from frozen payload
        5. Enqueues next step upon success
        """
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        # 1. Tenant Authorization Guard
        if not self._is_org_authorized(org_id):
            logger.warning("Organization %s is NOT authorized for background execution. Aborting tick.", org_id)
            return {
                "status": "unauthorized",
                "org_id": str(org_id),
                "processed_count": 0,
                "reclaimed_count": 0,
            }

        # 2. Reclaim expired leases across this tenant / system
        reclaimed_count = self.job_service.reclaim_expired_leases(now=current_time)

        # 3. Claim batch of eligible jobs
        claimed_jobs = self.job_service.claim_next_jobs(
            org_id=org_id,
            worker_id=self.worker_id,
            batch_size=batch_size,
            lease_duration_seconds=120,
            now=current_time,
            channels=AUTODISPATCH_ALLOWED_CHANNELS,
        )

        results: List[Dict[str, Any]] = []

        # 4. Process each claimed job
        for job in claimed_jobs:
            try:
                res = self.process_job(job, now=current_time)
                results.append(res)
            except Exception as exc:
                logger.exception("Unexpected error processing job %s: %s", job.id, exc)
                results.append({"job_id": str(job.id), "status": "error", "error": str(exc)})

        return {
            "status": "success",
            "org_id": str(org_id),
            "reclaimed_count": reclaimed_count,
            "claimed_count": len(claimed_jobs),
            "processed_count": len(results),
            "results": results,
        }

    def process_job(
        self,
        job: CampaignExecutionJob,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Processes a single claimed job strictly according to its frozen payload and safeguards."""
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        worker_id = self.worker_id
        lease_token = job.lease_token
        if not lease_token:
            return {"job_id": str(job.id), "status": "skipped", "reason": "No lease token"}

        # A. Check Maximum Overdue Staleness Gate (SCHEDULER_MAX_OVERDUE_HOURS)
        max_overdue_hours = getattr(settings, "SCHEDULER_MAX_OVERDUE_HOURS", 24)
        overdue_threshold = timedelta(hours=max_overdue_hours)
        scheduled_utc = job.scheduled_at if job.scheduled_at.tzinfo else job.scheduled_at.replace(tzinfo=timezone.utc)

        if current_time - scheduled_utc > overdue_threshold:
            overdue_hours = (current_time - scheduled_utc).total_seconds() / 3600.0
            hold_reason = (
                f"Held for manual review: job scheduled at {scheduled_utc.isoformat()} "
                f"is overdue by {overdue_hours:.1f} hours, exceeding the maximum allowed "
                f"staleness threshold of {max_overdue_hours} hours."
            )
            # Mark held
            job.status = "held"
            job.last_error = hold_reason
            job.lease_token = None
            job.lease_expires_at = None
            job.updated_at = current_time
            self.db.commit()
            logger.warning("Job %s held due to overdue staleness gate: %s", job.id, hold_reason)
            return {"job_id": str(job.id), "status": "held", "reason": hold_reason}

        # B. Check Stop Conditions on Contact / Enrollment
        cc = self.db.query(CampaignContact).filter(CampaignContact.id == job.campaign_contact_id).first()
        contact = self.db.query(Contact).filter(Contact.id == job.contact_id).first()
        campaign = self.db.query(Campaign).filter(Campaign.id == job.campaign_id).first()

        if not cc or not contact or not campaign:
            self.job_service.fail_job(
                job.id, worker_id, lease_token,
                "Parent entity (campaign, contact, or enrollment) no longer exists.",
                is_permanent=True,
                now=current_time,
            )
            return {"job_id": str(job.id), "status": "failed", "reason": "Parent entity missing"}

        if campaign.status != "active":
            job.status = "held"
            job.last_error = f"Campaign is in '{campaign.status}' status (must be active to dispatch)."
            job.lease_token = None
            job.lease_expires_at = None
            job.updated_at = current_time
            self.db.commit()
            return {"job_id": str(job.id), "status": "held", "reason": "Campaign not active"}

        if cc.enrollment_status != "in_progress":
            job.status = "held"
            job.last_error = f"Enrollment is in '{cc.enrollment_status}' status."
            job.lease_token = None
            job.lease_expires_at = None
            job.updated_at = current_time
            self.db.commit()
            return {"job_id": str(job.id), "status": "held", "reason": f"Enrollment status is {cc.enrollment_status}"}

        # Opt-out / Unsubscribe stop condition
        if contact.lead_status in ("opted_out", "unsubscribed"):
            cc.enrollment_status = "completed"
            self.job_service.cancel_active_jobs_for_enrollment(cc.id, f"Recipient opted out ({contact.lead_status})", current_time)
            self._check_campaign_completion(campaign.id)
            self.db.commit()
            return {"job_id": str(job.id), "status": "cancelled", "reason": "Recipient opted out"}

        # Reply stop condition
        if contact.lead_status == "replied":
            cc.enrollment_status = "replied"
            self.job_service.cancel_active_jobs_for_enrollment(cc.id, "Recipient replied to campaign", current_time)
            self._check_campaign_completion(campaign.id)
            self.db.commit()
            return {"job_id": str(job.id), "status": "cancelled", "reason": "Recipient replied"}

        # Meeting engagement stop condition
        from app.services.campaign_scheduler import CampaignSchedulerService
        scheduler_svc = CampaignSchedulerService(db=self.db)
        if scheduler_svc.check_meeting_engagement(job.organization_id, contact.id):
            cc.enrollment_status = "completed"
            self.job_service.cancel_active_jobs_for_enrollment(cc.id, "Prospect booked/confirmed a meeting", current_time)
            self._check_campaign_completion(campaign.id)
            self.db.commit()
            return {"job_id": str(job.id), "status": "cancelled", "reason": "Meeting booked"}

        # C. Retrieve or Create Outreach using FROZEN execution_payload
        outreach = None
        if job.outreach_id:
            outreach = self.db.query(Outreach).filter(Outreach.id == job.outreach_id).first()
            if outreach and outreach.status == "failed":
                outreach.status = "draft"
                self.db.commit()

        if not outreach:
            payload = job.execution_payload or {}
            rendered_subj = payload.get("rendered_subject") or payload.get("subject_template") or payload.get("subject")
            rendered_body = payload.get("rendered_body") or payload.get("body_template") or payload.get("body")
            if job.channel in ("voice", "sms"):
                recipient = contact.phone or job.recipient_snapshot
            else:
                recipient = contact.email or job.recipient_snapshot

            outreach = Outreach(
                id=uuid.uuid4(),
                organization_id=job.organization_id,
                campaign_id=job.campaign_id,
                contact_id=job.contact_id,
                campaign_contact_id=job.campaign_contact_id,
                recipient=recipient,
                channel=job.channel,
                status="draft",
                subject=rendered_subj,
                body=rendered_body,
                created_at=current_time,
                updated_at=current_time,
            )
            self.db.add(outreach)
            self.db.flush()
            job.outreach_id = outreach.id

        # D. Record dispatch_started_at right before provider network invocation
        self.job_service.mark_dispatch_started(job.id, worker_id, lease_token, now=current_time)

        # E. Execute Provider Dispatch
        dispatch_success = False
        dispatch_error = None
        is_ambiguous = False

        try:
            if job.channel == "email":
                dispatch_success = self._dispatch_email(job, outreach, current_time)
            elif job.channel == "voice":
                dispatch_success = self._dispatch_voice(job, outreach, current_time)
            elif job.channel == "sms":
                dispatch_success = self._dispatch_sms(job, outreach, current_time)
            else:
                dispatch_error = f"Channel {job.channel} is not authorized for automated dispatch"
        except Exception as exc:
            err_str = str(exc).lower()
            if any(term in err_str for term in ["timeout", "timed out", "connection reset", "504", "gateway timeout"]):
                is_ambiguous = True
            dispatch_error = str(exc)

        # F. Handle Dispatch Outcomes
        if is_ambiguous:
            self.job_service.mark_dispatch_unknown(
                job.id, worker_id, lease_token,
                f"Provider network timeout or ambiguous error: {dispatch_error}",
                now=current_time,
            )
            return {"job_id": str(job.id), "status": "dispatch_unknown", "error": dispatch_error}

        if not dispatch_success:
            self.job_service.fail_job(
                job.id, worker_id, lease_token,
                dispatch_error or "Unknown dispatch failure",
                is_permanent=False,
                now=current_time,
            )
            return {"job_id": str(job.id), "status": "failed_or_retry", "error": dispatch_error}

        # G. Mark Completed (CAS with lease_token)
        self.job_service.complete_job(job.id, worker_id, lease_token, outreach_id=outreach.id, now=current_time)
        cc.current_step = job.step_number
        self.db.commit()

        # H. Advance Sequence: Enqueue Next Step Asynchronously
        next_step_info = self._enqueue_next_sequence_step(campaign, cc, contact, job.step_number, current_time)

        return {
            "job_id": str(job.id),
            "status": "completed",
            "outreach_id": str(outreach.id),
            "step_number": job.step_number,
            "next_step": next_step_info,
        }

    # ── Dispatch Handlers ─────────────────────────────────────────────────────

    def _dispatch_email(self, job: CampaignExecutionJob, outreach: Outreach, current_time: datetime) -> bool:
        """Dispatches an email outreach via email provider (mock or real SES)."""
        from app.services.outreach.service import send_outreach
        provider = self.email_provider or (MockEmailProvider() if self.force_mock else None)

        sent_o = send_outreach(
            db=self.db,
            org_id=job.organization_id,
            outreach_id=outreach.id,
            provider=provider,
            raise_on_failure=True,
            auto_advance_sequence=False,
            sent_at=current_time,
        )
        return bool(sent_o and sent_o.status == "sent")

    def _dispatch_voice(self, job: CampaignExecutionJob, outreach: Outreach, current_time: datetime) -> bool:
        """Dispatches a voice outreach via Retell AI or mock voice service."""
        from app.services.voice.service import send_voice_outreach
        client = self.retell_client
        sent_o = send_voice_outreach(
            db=self.db,
            org_id=job.organization_id,
            outreach_id=outreach.id,
            retell_client=client,
            force_mock=self.force_mock,
            raise_on_failure=True,
        )
        return bool(sent_o and sent_o.status in ("sent", "sending"))

    def _dispatch_sms(self, job: CampaignExecutionJob, outreach: Outreach, current_time: datetime) -> bool:
        """Dispatches an SMS outreach via Twilio or mock SMS provider."""
        from app.services.sms.service import send_sms_outreach
        from app.services.sms.base import MockSMSProvider
        provider = self.sms_provider or (MockSMSProvider() if self.force_mock else None)
        sent_o = send_sms_outreach(
            db=self.db,
            org_id=job.organization_id,
            outreach_id=outreach.id,
            provider=provider,
            raise_on_failure=True,
            auto_advance_sequence=False,
        )
        return bool(sent_o and sent_o.status == "sent")

    # ── Next Step Enqueueing ──────────────────────────────────────────────────

    def _enqueue_next_sequence_step(
        self,
        camp: Campaign,
        cc: CampaignContact,
        contact: Contact,
        completed_step_number: int,
        current_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Determines the next step in the cadence and enqueues a new persistent job.
        If zero-delay, scheduled_at = current_time (eligible immediately).
        If delay configured, scheduled_at = current_time + delay.
        If all steps are exhausted, completes the enrollment and checks campaign completion.
        """
        from app.services.workflow_service import get_campaign_ordered_steps
        active_steps = [s for s in get_campaign_ordered_steps(self.db, camp) if getattr(s, "is_active", True)]
        if not active_steps:
            return None

        steps_by_num = {s.step_number: s for s in active_steps}
        next_step_num = completed_step_number + 1

        if next_step_num not in steps_by_num:
            # Cadence exhausted!
            cc.enrollment_status = "completed"
            self._check_campaign_completion(camp.id)
            self.db.commit()
            logger.info("Cadence exhausted for enrollment %s (completed at step %d)", cc.id, completed_step_number)
            return {"action": "cadence_completed", "final_step": completed_step_number}

        next_step = steps_by_num[next_step_num]
        step_channel = getattr(next_step, "step_type", "email") or "email"

        # Calculate delay
        delay_days = getattr(next_step, "delay_days", 0) or 0
        delay_hours = getattr(next_step, "delay_hours", 0) or 0
        is_zero_delay = (delay_days == 0 and delay_hours == 0)

        if is_zero_delay:
            next_scheduled_at = current_time
        else:
            next_scheduled_at = current_time + timedelta(days=delay_days, hours=delay_hours)

        # Snapshot template & payload
        company = contact.company if getattr(contact, "company", None) else None
        from app.services.organization_config import get_organization_booking_url
        booking_url = get_organization_booking_url(self.db, camp.organization_id)
        from app.services.campaign_steps.template_renderer import render_template

        subj_tmpl = getattr(next_step, "subject_template", None)
        body_tmpl = getattr(next_step, "body_template", None)
        rendered_subj = render_template(subj_tmpl, contact=contact, company=company, booking_link=booking_url) if subj_tmpl else None
        rendered_body = render_template(body_tmpl, contact=contact, company=company, booking_link=booking_url) if body_tmpl else None

        frozen_payload = {
            "step_number": next_step_num,
            "step_identifier": getattr(next_step, "id", None) and str(next_step.id),
            "channel": step_channel,
            "subject_template": subj_tmpl,
            "body_template": body_tmpl,
            "rendered_subject": rendered_subj,
            "rendered_body": rendered_body,
            "channel_config": getattr(next_step, "config", {}) or {},
        }

        # Enqueue the next step job
        next_job = self.job_service.enqueue_step_job(
            org_id=camp.organization_id,
            campaign_id=camp.id,
            campaign_contact_id=cc.id,
            contact_id=contact.id,
            step_number=next_step_num,
            channel=step_channel,
            scheduled_at=next_scheduled_at,
            step_identifier=frozen_payload["step_identifier"],
            campaign_step_id=getattr(next_step, "id", None) if isinstance(getattr(next_step, "id", None), uuid.UUID) else None,
            execution_payload=frozen_payload,
            campaign_name_snapshot=camp.name,
            recipient_snapshot=contact.email or contact.phone,
            auto_commit=True,
        )

        return {
            "action": "enqueued_next_step",
            "step_number": next_step_num,
            "job_id": str(next_job.id),
            "channel": step_channel,
            "is_zero_delay": is_zero_delay,
            "scheduled_at": next_scheduled_at.isoformat(),
        }

    def _check_campaign_completion(self, campaign_id: uuid.UUID) -> None:
        """Marks campaign completed if all enrolled contacts have completed."""
        from app.services.campaign_scheduler import check_and_update_campaign_completion
        check_and_update_campaign_completion(self.db, campaign_id)

    def _is_org_authorized(self, org_id: uuid.UUID) -> bool:
        """Enforces SCHEDULER_AUTHORIZED_ORGS restriction strictly."""
        auth_org_ids = getattr(settings, "authorized_scheduler_org_ids", [])
        if auth_org_ids:
            return any(str(auth_id).lower() == str(org_id).lower() for auth_id in auth_org_ids)
        raw = getattr(settings, "SCHEDULER_AUTHORIZED_ORGS", "")
        if isinstance(raw, str):
            raw_ids = [s.strip().lower() for s in raw.split(",") if s.strip()]
            return str(org_id).lower() in raw_ids
        elif isinstance(raw, (list, set)):
            return any(str(r).lower() == str(org_id).lower() for r in raw)
        return False
