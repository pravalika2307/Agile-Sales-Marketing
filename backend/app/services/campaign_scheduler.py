"""Campaign execution scheduler service managing multi-day cadences, delays, and stop conditions."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.outreach import Outreach
from app.schemas.outreach import OutreachCreate
from app.services.campaign_execution.rules import (
    NON_DUPLICATE_OUTREACH_STATUSES,
    EvaluationResult,
    evaluate_campaign_contact,
    evaluate_subsequent_step_eligibility,
)
from app.services.campaign_steps.template_renderer import (
    find_unresolved_placeholders,
    render_template,
)
from app.services.organization_config import get_organization_booking_url
from app.services.outreach.base import EmailProvider
from app.services.outreach.service import create_outreach, send_outreach

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Guarantees a datetime is timezone-aware UTC, safely handling SQLite naive datetimes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class SchedulerTickResult:
    """Consolidated summary of a scheduler execution run."""
    status: str = "completed"
    message: Optional[str] = None
    dry_run: bool = False
    planned_count: int = 0
    completed_count: int = 0
    dispatched_count: int = 0
    skipped_count: int = 0
    halted_count: int = 0
    error_count: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "dry_run": self.dry_run,
            "planned_count": self.planned_count,
            "completed_count": self.completed_count,
            "dispatched_count": self.dispatched_count,
            "skipped_count": self.skipped_count,
            "halted_count": self.halted_count,
            "error_count": self.error_count,
            "details": self.details,
        }


class CampaignSchedulerService:
    """
    Core scheduler service managing multi-day step progression and automated dispatch.
    Enforces strict tenant isolation, UTC timezone awareness, and comprehensive stop conditions.
    """

    def __init__(self, db: Session):
        self.db = db

    def check_meeting_engagement(
        self,
        org_id: uuid.UUID,
        contact_id: uuid.UUID,
    ) -> bool:
        """
        Check if the prospect has requested a meeting or has an active commercial meeting engagement.
        Under Kunal's requirements, meeting engagement halts automated outbound cold cadences.
        Does NOT alter Deal stages or mark deals won.
        """
        # 1. Check CallRecord for MEETING_REQUESTED or meeting followup
        call_meeting = (
            self.db.query(CallRecord)
            .filter(
                CallRecord.organization_id == org_id,
                CallRecord.contact_id == contact_id,
                CallRecord.call_outcome.in_(["MEETING_REQUESTED", "QUALIFIED"]),
            )
            .first()
        )
        if call_meeting:
            return True

        return False

    def plan_due_steps(
        self,
        org_id: Optional[uuid.UUID] = None,
        campaign_id: Optional[uuid.UUID] = None,
        now: Optional[datetime] = None,
        dry_run: bool = False,
        sender_name: Optional[str] = None,
    ) -> SchedulerTickResult:
        """
        Evaluates eligible enrollments across active campaigns and advances due steps.
        Calculates delays using delay_days and delay_hours relative to previous step completion.
        Enforces stop conditions (replies, bounces, opt-outs, meetings) and exhausts completed sequences.
        """
        current_time = now if now is not None else datetime.now(timezone.utc)
        result = SchedulerTickResult(dry_run=dry_run)

        # 1. Query active campaigns strictly scoped
        camp_query = self.db.query(Campaign).filter(Campaign.status == "active")
        if org_id:
            camp_query = camp_query.filter(Campaign.organization_id == org_id)
        if campaign_id:
            camp_query = camp_query.filter(Campaign.id == campaign_id)

        campaigns = camp_query.all()
        if not campaigns:
            result.message = "No active campaigns found for scheduling."
            return result

        for camp in campaigns:
            org_booking_url = get_organization_booking_url(self.db, camp.organization_id)
            # 2. Get active campaign steps ordered by step_number from visual workflow graph or legacy steps
            from app.services.workflow_service import get_campaign_ordered_steps
            active_steps = [s for s in get_campaign_ordered_steps(self.db, camp) if s.is_active]

            if not active_steps:
                continue

            steps_by_num = {s.step_number: s for s in active_steps}
            max_step_num = max(steps_by_num.keys())
            step_1 = steps_by_num.get(1)

            # 3. Query active enrollments for this campaign
            enrollment_query = (
                self.db.query(CampaignContact)
                .filter(
                    CampaignContact.campaign_id == camp.id,
                    CampaignContact.enrollment_status.in_(["queued", "in_progress"]),
                )
                .order_by(CampaignContact.enrolled_at.asc())
            )
            # PostgreSQL row-level locking where supported
            if not dry_run and self.db.bind and self.db.bind.dialect.name == "postgresql":
                enrollment_query = enrollment_query.with_for_update(skip_locked=True)

            enrollments = enrollment_query.all()

            for cc in enrollments:
                try:
                    # Resolve contact
                    contact = (
                        self.db.query(Contact)
                        .filter(
                            Contact.id == cc.contact_id,
                            Contact.organization_id == camp.organization_id,
                        )
                        .first()
                    )
                    if not contact:
                        result.error_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "action": "rejected",
                            "reason": "Contact record missing or cross-tenant",
                        })
                        continue

                    # Fetch all existing outreaches for this enrollment ordered by created_at
                    existing_outreaches = (
                        self.db.query(Outreach)
                        .filter(
                            Outreach.campaign_contact_id == cc.id,
                            Outreach.organization_id == camp.organization_id,
                        )
                        .order_by(Outreach.created_at.asc())
                        .all()
                    )

                    # ── STOP CONDITION EVALUATION ─────────────────────────────

                    # Stop Condition 1: Opt-out / Unsubscribe
                    if contact.lead_status in ("opted_out", "unsubscribed"):
                        if not dry_run:
                            cc.enrollment_status = "completed"
                            self._cancel_pending_outreaches(cc.id, camp.organization_id, current_time, "Recipient opted out or unsubscribed")
                            self.db.flush()
                        result.halted_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "contact_id": str(contact.id),
                            "action": "halted",
                            "reason": f"Contact opted out ({contact.lead_status})",
                        })
                        continue

                    # Stop Condition 2: Email Reply
                    has_replied = (
                        contact.lead_status == "replied"
                        or any(o.first_replied_at is not None for o in existing_outreaches)
                    )
                    if has_replied:
                        if not dry_run:
                            cc.enrollment_status = "replied"
                            self._cancel_pending_outreaches(cc.id, camp.organization_id, current_time, "Prospect replied to outreach")
                            self.db.flush()
                        result.halted_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "contact_id": str(contact.id),
                            "action": "halted",
                            "reason": "Prospect replied (sequence stopped)",
                        })
                        continue

                    # Stop Condition 3: Hard Bounce
                    has_bounced = any(o.first_bounced_at is not None for o in existing_outreaches)
                    if has_bounced:
                        if not dry_run:
                            cc.enrollment_status = "bounced"
                            self._cancel_pending_outreaches(cc.id, camp.organization_id, current_time, "Outreach bounced")
                            self.db.flush()
                        result.halted_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "contact_id": str(contact.id),
                            "action": "halted",
                            "reason": "Outreach delivery bounced",
                        })
                        continue

                    # Stop Condition 4: Meeting Requested or Confirmed
                    has_meeting = self.check_meeting_engagement(camp.organization_id, contact.id)
                    if has_meeting:
                        if not dry_run:
                            cc.enrollment_status = "completed"
                            self._cancel_pending_outreaches(cc.id, camp.organization_id, current_time, "Meeting requested or confirmed")
                            self.db.flush()
                        result.halted_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "contact_id": str(contact.id),
                            "action": "halted",
                            "reason": "Meeting requested/confirmed (cold sequence stopped)",
                        })
                        continue

                    # ── STEP ADVANCEMENT LOGIC ─────────────────────────────────

                    # Case A: Contact is newly queued (current_step == 0)
                    if cc.enrollment_status == "queued" or cc.current_step == 0:
                        if not step_1:
                            result.skipped_count += 1
                            continue

                        # Check Step 1 delay relative to enrollment
                        enrolled_time = _ensure_utc(cc.enrolled_at)
                        step1_due_time = enrolled_time + timedelta(days=step_1.delay_days, hours=step_1.delay_hours)
                        if current_time < step1_due_time:
                            result.skipped_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "skipped",
                                "reason": f"Step 1 delay not elapsed. Due at {step1_due_time.isoformat()}",
                            })
                            continue

                        evaluation = evaluate_campaign_contact(camp, cc, contact, existing_outreaches)
                        if evaluation.result != EvaluationResult.ELIGIBLE:
                            result.skipped_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "skipped",
                                "reason": evaluation.reason,
                            })
                            continue

                        # Render Step 1
                        company = (
                            self.db.query(Company)
                            .filter(
                                Company.id == contact.company_id,
                                Company.organization_id == camp.organization_id,
                            )
                            .first()
                            if contact.company_id else None
                        )
                        step1_channel = getattr(step_1, "step_type", "email") or "email"
                        if step1_channel == "physical_mail":
                            rendered_subj = step_1.subject_template or "Poplar Direct Mail"
                            rendered_body = f"Physical mailing to {contact.postal_address_line1}, {contact.postal_city or ''}"
                        else:
                            rendered_subj = (
                                render_template(step_1.subject_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                if step_1.subject_template
                                else (None if step1_channel in ("sms", "voice") else "")
                            )
                            rendered_body = (
                                render_template(step_1.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                if step_1.body_template
                                else (None if step1_channel == "voice" else "")
                            )

                        unresolved = []
                        if step1_channel in ("email", "sms"):
                            unresolved = (find_unresolved_placeholders(rendered_subj) if rendered_subj else []) + (find_unresolved_placeholders(rendered_body) if rendered_body else [])
                        if unresolved:
                            result.error_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "error",
                                "reason": f"Unresolved template placeholders: {unresolved}",
                            })
                            continue

                        if not dry_run:
                            outreach_payload = OutreachCreate(
                                campaign_id=camp.id,
                                contact_id=cc.contact_id,
                                campaign_contact_id=cc.id,
                                channel=step1_channel,
                                subject=rendered_subj,
                                body=rendered_body,
                                scheduled_at=None,
                            )
                            create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
                            cc.enrollment_status = "in_progress"
                            cc.current_step = 1
                            self.db.flush()

                        result.planned_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "contact_id": str(contact.id),
                            "action": "planned",
                            "step_number": 1,
                        })
                        continue

                    # Case B: Contact is in_progress (current_step >= 1)
                    if cc.enrollment_status == "in_progress":
                        # Inspect the outreach for current_step
                        # In the chronological sequence, outreach for current_step corresponds to existing_outreaches[current_step - 1]
                        last_outreach = existing_outreaches[-1] if existing_outreaches else None

                        # Failed Delivery Rule: Sequence does not advance if last outreach failed or not sent
                        if not last_outreach or last_outreach.status != "sent":
                            last_status = last_outreach.status if last_outreach else "missing"
                            result.skipped_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "skipped",
                                "reason": f"Current step {cc.current_step} is not sent (status: '{last_status}'). Awaiting delivery before advancing.",
                            })
                            continue

                        next_step_num = cc.current_step + 1

                        # Cadence Exhaustion Rule: Check if all active steps are completed
                        if next_step_num > max_step_num:
                            if not dry_run:
                                cc.enrollment_status = "completed"
                                self.db.flush()
                            result.completed_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "completed",
                                "reason": f"All {max_step_num} configured steps completed.",
                            })
                            continue

                        next_step = steps_by_num.get(next_step_num)
                        if not next_step:
                            if not dry_run:
                                cc.enrollment_status = "completed"
                                self.db.flush()
                            result.completed_count += 1
                            continue

                        # Check if next step outreach already exists (idempotency check)
                        existing_for_step = existing_outreaches[next_step_num - 1:] if len(existing_outreaches) >= next_step_num else []

                        # Extract condition requirement from workflow_config if configured
                        required_condition = None
                        if camp.workflow_config and isinstance(camp.workflow_config, dict):
                            w_nodes = camp.workflow_config.get("nodes", [])
                            comm_idx = 1
                            for wn in w_nodes:
                                if isinstance(wn, dict) and wn.get("type") in ("email", "sms", "voice"):
                                    if comm_idx == next_step_num:
                                        required_condition = wn.get("config", {}).get("condition_type")
                                        break
                                    comm_idx += 1

                        evaluation = evaluate_subsequent_step_eligibility(
                            campaign=camp,
                            campaign_contact=cc,
                            contact=contact,
                            next_step=next_step,
                            last_sent_outreach=last_outreach,
                            existing_outreaches_for_next_step=existing_for_step,
                            now=current_time,
                            has_meeting_requested=False,
                            required_condition=required_condition,
                        )

                        if evaluation.result != EvaluationResult.ELIGIBLE:
                            result.skipped_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "skipped",
                                "reason": evaluation.reason,
                            })
                            continue

                        # Render template for next step
                        company = (
                            self.db.query(Company)
                            .filter(
                                Company.id == contact.company_id,
                                Company.organization_id == camp.organization_id,
                            )
                            .first()
                            if contact.company_id else None
                        )
                        next_channel = getattr(next_step, "step_type", "email") or "email"
                        if next_channel == "physical_mail":
                            rendered_subj = next_step.subject_template or "Poplar Direct Mail"
                            rendered_body = f"Physical mailing to {contact.postal_address_line1}, {contact.postal_city or ''}"
                        else:
                            rendered_subj = (
                                render_template(next_step.subject_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                if next_step.subject_template
                                else (None if next_channel in ("sms", "voice") else "")
                            )
                            rendered_body = (
                                render_template(next_step.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                if next_step.body_template
                                else (None if next_channel == "voice" else "")
                            )

                        unresolved = []
                        if next_channel in ("email", "sms"):
                            unresolved = (find_unresolved_placeholders(rendered_subj) if rendered_subj else []) + (find_unresolved_placeholders(rendered_body) if rendered_body else [])
                        if unresolved:
                            result.error_count += 1
                            result.details.append({
                                "campaign_contact_id": str(cc.id),
                                "action": "error",
                                "reason": f"Unresolved template placeholders in step {next_step_num}: {unresolved}",
                            })
                            continue

                        if not dry_run:
                            outreach_payload = OutreachCreate(
                                campaign_id=camp.id,
                                contact_id=cc.contact_id,
                                campaign_contact_id=cc.id,
                                channel=next_channel,
                                subject=rendered_subj,
                                body=rendered_body,
                                scheduled_at=None,
                            )
                            create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
                            cc.current_step = next_step_num
                            self.db.flush()

                        result.planned_count += 1
                        result.details.append({
                            "campaign_contact_id": str(cc.id),
                            "contact_id": str(contact.id),
                            "action": "planned",
                            "step_number": next_step_num,
                        })

                except Exception as exc:
                    logger.warning("Error processing campaign_contact %s: %s", cc.id, exc)
                    result.error_count += 1
                    result.details.append({
                        "campaign_contact_id": str(cc.id),
                        "action": "error",
                        "reason": str(exc),
                    })

        if not dry_run:
            self.db.commit()

        result.message = (
            f"Scheduler planning complete: {result.planned_count} planned, "
            f"{result.completed_count} completed, {result.halted_count} halted, "
            f"{result.skipped_count} skipped, {result.error_count} errors."
        )
        return result

    def dispatch_scheduled_outreach(
        self,
        org_id: Optional[uuid.UUID] = None,
        now: Optional[datetime] = None,
        dry_run: bool = False,
        provider: Optional[EmailProvider] = None,
    ) -> SchedulerTickResult:
        """
        Dispatches pending scheduled Outreach records whose scheduled_at timestamp is due.
        Separates scheduling/planning from message delivery.
        """
        current_time = now if now is not None else datetime.now(timezone.utc)
        result = SchedulerTickResult(dry_run=dry_run)

        query = (
            self.db.query(Outreach)
            .filter(
                Outreach.status == "scheduled",
                Outreach.scheduled_at.isnot(None),
            )
            .order_by(Outreach.scheduled_at.asc())
        )
        if org_id:
            query = query.filter(Outreach.organization_id == org_id)

        if not dry_run and self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        all_candidates = query.limit(settings.SCHEDULER_BATCH_SIZE * 2).all()
        due_outreaches = [
            o for o in all_candidates
            if o.scheduled_at and _ensure_utc(o.scheduled_at) <= current_time
        ][:settings.SCHEDULER_BATCH_SIZE]

        for o in due_outreaches:
            if dry_run:
                result.dispatched_count += 1
                result.details.append({
                    "outreach_id": str(o.id),
                    "action": "dry_run_dispatch",
                    "recipient": o.recipient_email,
                })
                continue

            try:
                send_outreach(
                    db=self.db,
                    org_id=o.organization_id,
                    outreach_id=o.id,
                    provider=provider,
                    raise_on_failure=False,
                )
                result.dispatched_count += 1
                result.details.append({
                    "outreach_id": str(o.id),
                    "action": "dispatched",
                    "recipient": o.recipient_email,
                })
            except Exception as exc:
                logger.warning("Failed to dispatch scheduled outreach %s: %s", o.id, exc)
                result.error_count += 1
                result.details.append({
                    "outreach_id": str(o.id),
                    "action": "error",
                    "reason": str(exc),
                })

        return result

    def tick(
        self,
        now: Optional[datetime] = None,
        org_id: Optional[uuid.UUID] = None,
        campaign_id: Optional[uuid.UUID] = None,
        dry_run: bool = False,
        auto_dispatch: bool = False,
        force: bool = False,
        provider: Optional[EmailProvider] = None,
        sender_name: Optional[str] = None,
    ) -> SchedulerTickResult:
        """
        Executes a complete scheduler tick.
        Strictly enforces that scheduler is disabled by default unless force=True or SCHEDULER_ENABLED=True.
        """
        # Strict Delivery Safety: Disabled by default
        if not settings.SCHEDULER_ENABLED and not force and not dry_run:
            return SchedulerTickResult(
                status="disabled",
                message="Scheduler is disabled by default (settings.SCHEDULER_ENABLED is False).",
                dry_run=dry_run,
            )

        # 1. Step planning and sequence advancement
        plan_res = self.plan_due_steps(
            org_id=org_id,
            campaign_id=campaign_id,
            now=now,
            dry_run=dry_run,
            sender_name=sender_name,
        )

        # 2. Optional message dispatch if auto_dispatch configured
        dispatch_res = SchedulerTickResult(dry_run=dry_run)
        if auto_dispatch or settings.SCHEDULER_AUTO_DISPATCH:
            dispatch_res = self.dispatch_scheduled_outreach(
                org_id=org_id,
                now=now,
                dry_run=dry_run,
                provider=provider,
            )

        # Consolidated result
        total_details = plan_res.details + dispatch_res.details
        return SchedulerTickResult(
            status="completed",
            message=f"{plan_res.message} Dispatched: {dispatch_res.dispatched_count}.",
            dry_run=dry_run,
            planned_count=plan_res.planned_count,
            completed_count=plan_res.completed_count,
            dispatched_count=dispatch_res.dispatched_count,
            skipped_count=plan_res.skipped_count,
            halted_count=plan_res.halted_count,
            error_count=plan_res.error_count + dispatch_res.error_count,
            details=total_details,
        )

    def _cancel_pending_outreaches(
        self,
        campaign_contact_id: uuid.UUID,
        org_id: uuid.UUID,
        now: datetime,
        reason: str,
    ) -> None:
        """Helper to cancel pending draft or scheduled outreaches for a halted enrollment."""
        from app.models.outreach import OutreachEvent

        pending = (
            self.db.query(Outreach)
            .filter(
                Outreach.campaign_contact_id == campaign_contact_id,
                Outreach.organization_id == org_id,
                Outreach.status.in_(["draft", "scheduled"]),
            )
            .all()
        )
        for p in pending:
            p.status = "cancelled"
            evt = OutreachEvent(
                organization_id=org_id,
                outreach_id=p.id,
                event_type="cancelled",
                event_metadata={"reason": reason},
                occurred_at=now,
            )
            self.db.add(evt)
