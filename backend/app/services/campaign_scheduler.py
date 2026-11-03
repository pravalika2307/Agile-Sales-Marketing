"""Campaign execution scheduler service managing multi-day cadences, delays, and stop conditions."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import threading
from sqlalchemy import text
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

# Session-level 64-bit integer advisory lock key for PostgreSQL
CAMPAIGN_SCHEDULER_LOCK_ID = 88492048123491
# Process-level thread lock for SQLite / in-process concurrency coordination
_in_process_scheduler_lock = threading.Lock()
# Dedicated connections for active PostgreSQL advisory locks to ensure unlock executes on the same connection
_active_lock_connections: dict[int, Any] = {}
_lock_registry_lock = threading.Lock()


def acquire_scheduler_lock(db: Session) -> bool:
    """
    Acquires an advisory lock for the scheduler tick to prevent duplicate concurrent runs.
    - On PostgreSQL: Checks out a dedicated connection from the engine and calls pg_try_advisory_lock()
      so the lock is held reliably across intermediate session commits/rollbacks.
    - On SQLite/others: Falls back to an in-process non-blocking threading.Lock().
    Returns True if the lock was successfully acquired, False otherwise.
    """
    if db.bind and db.bind.dialect.name == "postgresql":
        try:
            lock_conn = db.get_bind().connect()
            res = lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": CAMPAIGN_SCHEDULER_LOCK_ID},
            ).scalar()
            if not res:
                lock_conn.close()
                return False
            with _lock_registry_lock:
                _active_lock_connections[id(db)] = lock_conn
            return True
        except Exception as exc:
            logger.warning("Error acquiring PostgreSQL scheduler advisory lock: %s", exc)
            return True
    else:
        return _in_process_scheduler_lock.acquire(blocking=False)


def release_scheduler_lock(db: Session, acquired: bool) -> None:
    """Releases the scheduler lock acquired earlier."""
    if not acquired:
        return
    if db.bind and db.bind.dialect.name == "postgresql":
        with _lock_registry_lock:
            lock_conn = _active_lock_connections.pop(id(db), None)
        if lock_conn is not None:
            try:
                lock_conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": CAMPAIGN_SCHEDULER_LOCK_ID},
                )
            except Exception as exc:
                logger.warning("Error releasing PostgreSQL scheduler advisory lock on dedicated connection: %s", exc)
            finally:
                lock_conn.close()
        else:
            try:
                db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": CAMPAIGN_SCHEDULER_LOCK_ID},
                )
            except Exception as exc:
                logger.warning("Error releasing PostgreSQL scheduler advisory lock: %s", exc)
    else:
        try:
            _in_process_scheduler_lock.release()
        except RuntimeError:
            pass


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
    held_count: int = 0
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
            "held_count": self.held_count,
            "error_count": self.error_count,
            "details": self.details,
        }


def mark_outreach_held(
    db: Session,
    outreach: Outreach,
    reason: str,
    overdue_hours: float,
    current_time: datetime,
) -> Any:
    """Marks an outreach as held for manual review due to overdue staleness threshold."""
    from app.models.outreach import OutreachEvent

    outreach.status = "draft"
    evt = OutreachEvent(
        organization_id=outreach.organization_id,
        outreach_id=outreach.id,
        event_type="scheduled",
        event_metadata={
            "held_for_manual_review": True,
            "hold_reason": reason,
            "overdue_hours": round(overdue_hours, 2),
            "original_scheduled_at": _ensure_utc(outreach.scheduled_at).isoformat() if outreach.scheduled_at else None,
            "held_at": current_time.isoformat(),
        },
        occurred_at=current_time,
    )
    db.add(evt)
    return evt


def list_held_outreaches(db: Session, org_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Lists all outreach steps currently held for manual review in an organization."""
    from app.models.outreach import Outreach, OutreachEvent

    held_events = (
        db.query(OutreachEvent)
        .filter(
            OutreachEvent.organization_id == org_id,
        )
        .order_by(OutreachEvent.occurred_at.asc())
        .all()
    )
    held_state: dict[uuid.UUID, dict] = {}
    for evt in held_events:
        if evt.event_metadata and "held_for_manual_review" in evt.event_metadata:
            if evt.event_metadata.get("held_for_manual_review") is True:
                held_state[evt.outreach_id] = {
                    "hold_reason": evt.event_metadata.get("hold_reason"),
                    "overdue_hours": evt.event_metadata.get("overdue_hours"),
                    "held_at": evt.occurred_at.isoformat() if evt.occurred_at else None,
                }
            else:
                held_state.pop(evt.outreach_id, None)

    if not held_state:
        return []

    held_outreaches = (
        db.query(Outreach)
        .filter(
            Outreach.id.in_(list(held_state.keys())),
            Outreach.organization_id == org_id,
            Outreach.status == "draft",
        )
        .all()
    )

    results = []
    for o in held_outreaches:
        info = held_state.get(o.id, {})
        camp_name = o.campaign.name if o.campaign else None
        results.append({
            "outreach_id": o.id,
            "campaign_id": o.campaign_id,
            "campaign_name": camp_name,
            "contact_id": o.contact_id,
            "recipient": o.recipient_email or o.recipient,
            "channel": o.channel,
            "status": o.status,
            "subject": o.subject,
            "scheduled_at": o.scheduled_at.isoformat() if o.scheduled_at else None,
            "overdue_hours": info.get("overdue_hours"),
            "hold_reason": info.get("hold_reason"),
            "held_at": info.get("held_at"),
        })
    return results


def resolve_held_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    action: str,
    provider: Optional[EmailProvider] = None,
    user_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Resolves a held outreach step by either 'approve' (dispatching immediately) or 'dismiss' (cancelling).
    """
    from app.models.outreach import Outreach, OutreachEvent

    if action not in ("approve", "dismiss"):
        raise ValueError(f"Invalid resolution action '{action}'. Must be 'approve' or 'dismiss'.")

    outreach = (
        db.query(Outreach)
        .filter(Outreach.id == outreach_id, Outreach.organization_id == org_id)
        .first()
    )
    if not outreach:
        raise ValueError(f"Outreach '{outreach_id}' not found in organization.")

    now = datetime.now(timezone.utc)

    if action == "approve":
        # Record un-hold approval event
        evt = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="scheduled",
            event_metadata={
                "held_for_manual_review": False,
                "approved_by": str(user_id) if user_id else "manual_review",
                "approved_at": now.isoformat(),
            },
            occurred_at=now,
        )
        db.add(evt)
        outreach.status = "draft"
        db.flush()

        # Dispatch
        channel = outreach.channel
        dispatch_status = "sent"
        if channel == "email":
            from app.services.outreach.service import send_outreach
            sent_o = send_outreach(
                db=db,
                org_id=org_id,
                outreach_id=outreach.id,
                provider=provider,
                raise_on_failure=True,
                auto_advance_sequence=False,
                sent_at=now,
            )
            dispatch_status = sent_o.status
        elif channel == "voice":
            from app.services.voice.service import send_voice_outreach
            voice_o = send_voice_outreach(
                db=db,
                org_id=org_id,
                outreach_id=outreach.id,
                raise_on_failure=True,
                force_mock=True,
            )
            dispatch_status = voice_o.status
        elif channel == "sms":
            from app.services.sms.service import send_sms_outreach
            sms_o = send_sms_outreach(
                db=db,
                org_id=org_id,
                outreach_id=outreach.id,
                raise_on_failure=True,
                auto_advance_sequence=False,
                sent_at=now,
            )
            dispatch_status = sms_o.status
        elif channel == "physical_mail":
            from app.services.physical_mail.service import send_single_physical_mail_outreach
            mail_o = send_single_physical_mail_outreach(
                db=db,
                org_id=org_id,
                outreach_id=outreach.id,
                force_mock=True,
            )
            dispatch_status = mail_o.status

        # Advance enrollment sequence if applicable
        if outreach.campaign_contact_id and dispatch_status == "sent":
            advance_campaign_contact_sequence(
                db=db,
                campaign_contact_id=outreach.campaign_contact_id,
                org_id=org_id,
                now=now,
                email_provider=provider,
                auto_dispatch=True,
            )

        db.commit()
        return {
            "outreach_id": outreach_id,
            "action": "approved",
            "status": dispatch_status,
            "message": f"Held step approved and dispatched via {channel}.",
        }

    elif action == "dismiss":
        outreach.status = "cancelled"
        evt = OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="cancelled",
            event_metadata={
                "held_for_manual_review": False,
                "dismissed_by": str(user_id) if user_id else "manual_review",
                "dismissed_at": now.isoformat(),
            },
            occurred_at=now,
        )
        db.add(evt)
        if outreach.campaign_id:
            check_and_update_campaign_completion(db, outreach.campaign_id)
        db.commit()
        return {
            "outreach_id": outreach_id,
            "action": "dismissed",
            "status": "cancelled",
            "message": "Held step dismissed and cancelled.",
        }


def check_and_update_campaign_completion(db: Session, campaign_id: uuid.UUID) -> bool:
    """
    Checks if all enrolled contacts in a campaign have reached a terminal state
    (completed, replied, bounced).
    If no contacts remain in 'queued' or 'in_progress', transitions campaign to 'completed'.
    Returns True if campaign transitioned to completed.
    """
    db.flush()
    remaining_active = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.enrollment_status.in_(["queued", "in_progress"]),
        )
        .count()
    )
    if remaining_active == 0:
        total = db.query(CampaignContact).filter(CampaignContact.campaign_id == campaign_id).count()
        if total > 0:
            camp = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if camp and camp.status == "active":
                camp.status = "completed"
                db.flush()
                return True
    return False


def _extract_step_condition(camp: Campaign, step_num: int) -> Optional[str]:
    """Extract condition requirement from workflow_config if configured."""
    if camp.workflow_config and isinstance(camp.workflow_config, dict):
        w_nodes = camp.workflow_config.get("nodes", [])
        comm_idx = 1
        for wn in w_nodes:
            if isinstance(wn, dict) and wn.get("type") in ("email", "sms", "voice", "physical_mail", "linkedin"):
                if comm_idx == step_num:
                    return wn.get("config", {}).get("condition_type")
                comm_idx += 1
    return None


def _cancel_enrollment_pending_outreaches(
    db: Session,
    campaign_contact_id: uuid.UUID,
    org_id: uuid.UUID,
    now: datetime,
    reason: str,
) -> None:
    """Helper to cancel pending draft or scheduled outreaches for a halted enrollment."""
    from app.models.outreach import OutreachEvent

    pending = (
        db.query(Outreach)
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
        db.add(evt)


def _create_step_outreach(
    db: Session,
    camp: Campaign,
    cc: CampaignContact,
    contact: Contact,
    step: Any,
    scheduled_at: Optional[datetime] = None,
    initial_status: str = "draft",
    sender_name: Optional[str] = None,
) -> Outreach:
    """Helper to render template and create Outreach record for a campaign step."""
    company = (
        db.query(Company)
        .filter(
            Company.id == contact.company_id,
            Company.organization_id == camp.organization_id,
        )
        .first()
        if contact.company_id else None
    )
    org_booking_url = get_organization_booking_url(db, camp.organization_id)
    step_channel = getattr(step, "step_type", "email") or "email"

    if step_channel == "sms":
        rendered_subj = None
        rendered_body = (
            render_template(step.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
            if step.body_template else ""
        )
        recipient = contact.phone
    elif step_channel == "voice":
        rendered_subj = step.subject_template or f"Step {step.step_number}: AI Voice SDR Call"
        rendered_body = step.body_template or "Outbound AI Voice SDR call via Retell."
        recipient = contact.phone
    elif step_channel == "physical_mail":
        rendered_subj = step.subject_template or "Poplar Direct Mail"
        addr1 = getattr(contact, "address_line_1", None) or getattr(contact, "postal_address_line1", None) or "Address on file"
        city = getattr(contact, "city", None) or getattr(contact, "postal_city", None) or ""
        rendered_body = f"Physical mailing to {addr1}, {city}".strip()
        recipient = addr1
    elif step_channel == "linkedin":
        rendered_subj = step.subject_template or "LinkedIn Connection Request"
        rendered_body = (
            render_template(step.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
            if step.body_template else ""
        )
        recipient = getattr(contact, "linkedin_url", None) or contact.email or f"{contact.first_name} {contact.last_name}"
    else:  # email
        rendered_subj = (
            render_template(step.subject_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
            if step.subject_template else ""
        )
        rendered_body = (
            render_template(step.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
            if step.body_template else ""
        )
        recipient = contact.email

    outreach_payload = OutreachCreate(
        campaign_id=camp.id,
        contact_id=cc.contact_id,
        campaign_contact_id=cc.id,
        channel=step_channel,
        subject=rendered_subj,
        body=rendered_body,
        scheduled_at=scheduled_at,
    )
    outreach = create_outreach(db, camp.organization_id, outreach_payload, commit=False)
    if recipient:
        outreach.recipient = recipient
    if initial_status and initial_status != outreach.status:
        outreach.status = initial_status
    return outreach


def advance_campaign_contact_sequence(
    db: Session,
    campaign_contact_id: uuid.UUID,
    org_id: Optional[uuid.UUID] = None,
    now: Optional[datetime] = None,
    email_provider: Optional[EmailProvider] = None,
    retell_client: Optional[Any] = None,
    auto_dispatch: bool = True,
    sender_name: Optional[str] = None,
    max_steps_per_call: int = 10,
    force_mock: bool = False,
) -> List[Dict[str, Any]]:
    """
    Advances an individual CampaignContact sequence through eligible steps:
    1. Zero-delay steps become eligible immediately after preceding step finishes (status='sent').
    2. Sequential execution: runs immediately and loops to subsequent zero-delay steps without artificial delay.
    3. Configured delay steps are scheduled for 'sent_at + delay' (status='scheduled').
    4. Halts progression on stop conditions (opt-out, reply, bounce, meeting).
    5. Asynchronous actions (voice calls) advance only when completed.
    6. Strict idempotency and duplicate execution protection.
    7. Marks CampaignContact and Campaign completed when sequence finishes.
    """
    actions_taken: List[Dict[str, Any]] = []

    for _ in range(max_steps_per_call):
        current_time = _ensure_utc(now) or datetime.now(timezone.utc)
        # 1. Fetch CampaignContact with row locking where supported
        cc_query = db.query(CampaignContact).filter(CampaignContact.id == campaign_contact_id)
        if db.bind and db.bind.dialect.name == "postgresql":
            cc_query = cc_query.with_for_update(skip_locked=True)
        cc = cc_query.first()
        if not cc or cc.enrollment_status != "in_progress":
            break

        # 2. Fetch Campaign strictly scoped to tenant
        camp_query = db.query(Campaign).filter(Campaign.id == cc.campaign_id)
        if org_id:
            camp_query = camp_query.filter(Campaign.organization_id == org_id)
        camp = camp_query.first()
        if not camp or camp.status != "active":
            break
        resolved_org_id = camp.organization_id

        # 3. Fetch Contact
        contact = db.query(Contact).filter(
            Contact.id == cc.contact_id,
            Contact.organization_id == resolved_org_id,
        ).first()
        if not contact:
            break

        # 4. Fetch existing outreaches for this enrollment ordered by created_at asc
        existing_outreaches = (
            db.query(Outreach)
            .filter(
                Outreach.campaign_contact_id == cc.id,
                Outreach.organization_id == resolved_org_id,
            )
            .order_by(Outreach.created_at.asc())
            .all()
        )

        # 5. Check Stop Conditions
        # Opt-out / Unsubscribe
        if contact.lead_status in ("opted_out", "unsubscribed"):
            cc.enrollment_status = "completed"
            _cancel_enrollment_pending_outreaches(db, cc.id, resolved_org_id, current_time, "Recipient opted out or unsubscribed")
            check_and_update_campaign_completion(db, camp.id)
            db.commit()
            actions_taken.append({"action": "halted", "reason": f"Opt-out ({contact.lead_status})"})
            break

        # Reply
        has_replied = (
            contact.lead_status == "replied"
            or any(o.first_replied_at is not None for o in existing_outreaches)
        )
        if has_replied:
            cc.enrollment_status = "replied"
            _cancel_enrollment_pending_outreaches(db, cc.id, resolved_org_id, current_time, "Prospect replied to outreach")
            check_and_update_campaign_completion(db, camp.id)
            db.commit()
            actions_taken.append({"action": "halted", "reason": "Prospect replied"})
            break

        # Bounce
        has_bounced = any(o.first_bounced_at is not None for o in existing_outreaches)
        if has_bounced:
            cc.enrollment_status = "bounced"
            _cancel_enrollment_pending_outreaches(db, cc.id, resolved_org_id, current_time, "Outreach bounced")
            check_and_update_campaign_completion(db, camp.id)
            db.commit()
            actions_taken.append({"action": "halted", "reason": "Outreach bounced"})
            break

        # 6. Step Ordering and Exhaustion Check
        from app.services.workflow_service import get_campaign_ordered_steps
        active_steps = [s for s in get_campaign_ordered_steps(db, camp) if s.is_active]
        if not active_steps:
            break

        steps_by_num = {s.step_number: s for s in active_steps}
        max_step_num = max(steps_by_num.keys())
        next_step_num = cc.current_step + 1

        if next_step_num > max_step_num or next_step_num not in steps_by_num:
            # Cadence completely exhausted
            cc.enrollment_status = "completed"
            check_and_update_campaign_completion(db, camp.id)
            db.commit()
            actions_taken.append({"action": "completed", "max_step": max_step_num})
            break

        next_step = steps_by_num[next_step_num]
        required_condition = _extract_step_condition(camp, next_step_num)

        # 7. Meeting Engagement Stop Check
        # Prospect requesting a meeting halts the cold cadence unless this next step explicitly handles meeting follow-up
        scheduler_svc = CampaignSchedulerService(db=db)
        has_meeting = scheduler_svc.check_meeting_engagement(resolved_org_id, contact.id)
        if has_meeting and required_condition != "meeting_requested":
            cc.enrollment_status = "completed"
            _cancel_enrollment_pending_outreaches(db, cc.id, resolved_org_id, current_time, "Meeting requested or confirmed")
            check_and_update_campaign_completion(db, camp.id)
            db.commit()
            actions_taken.append({"action": "halted", "reason": "Meeting requested/confirmed"})
            break

        # 8. Current Step Completion Check
        last_outreach = existing_outreaches[-1] if existing_outreaches else None
        is_failure_handler = required_condition in ("call_failed", "no_answer")
        expected_statuses = {"sent"} if not is_failure_handler else {"failed", "sent"}
        if not last_outreach or last_outreach.status not in expected_statuses:
            last_status = last_outreach.status if last_outreach else "missing"
            actions_taken.append({
                "action": "awaiting_completion",
                "status": last_status,
                "step": cc.current_step,
            })
            break

        # 8. Check Delay and Due Time
        sent_time = _ensure_utc(last_outreach.sent_at or last_outreach.created_at)
        delay_delta = timedelta(days=next_step.delay_days, hours=next_step.delay_hours)
        due_time = sent_time + delay_delta
        is_zero_delay = (next_step.delay_days == 0 and next_step.delay_hours == 0)

        existing_for_step = existing_outreaches[next_step_num - 1:] if len(existing_outreaches) >= next_step_num else []

        # If not zero delay and delay has not elapsed: Schedule step
        if not is_zero_delay and current_time < due_time:
            if not existing_for_step:
                outreach = _create_step_outreach(
                    db=db,
                    camp=camp,
                    cc=cc,
                    contact=contact,
                    step=next_step,
                    scheduled_at=due_time,
                    initial_status="scheduled",
                    sender_name=sender_name,
                )
                if last_outreach and getattr(last_outreach, "call_record_id", None):
                    outreach.call_record_id = last_outreach.call_record_id
                cc.current_step = next_step_num
                db.commit()
                actions_taken.append({
                    "action": "scheduled",
                    "step_number": next_step_num,
                    "scheduled_at": due_time.isoformat(),
                    "outreach_id": str(outreach.id),
                })
            break

        # 9. Step is Due -> Evaluate Eligibility
        evaluation = evaluate_subsequent_step_eligibility(
            campaign=camp,
            campaign_contact=cc,
            contact=contact,
            next_step=next_step,
            last_sent_outreach=last_outreach,
            existing_outreaches_for_next_step=existing_for_step,
            now=current_time,
            has_meeting_requested=has_meeting,
            required_condition=required_condition,
        )

        if evaluation.result != EvaluationResult.ELIGIBLE:
            if evaluation.result == EvaluationResult.HELD:
                # Step is overdue beyond max staleness threshold -> Hold for manual review
                target_outreach = None
                if existing_for_step:
                    target_outreach = existing_for_step[0]
                    target_outreach.status = "draft"
                else:
                    target_outreach = _create_step_outreach(
                        db=db,
                        camp=camp,
                        cc=cc,
                        contact=contact,
                        step=next_step,
                        scheduled_at=due_time,
                        initial_status="draft",
                        sender_name=sender_name,
                    )
                overdue_hours = (current_time - due_time).total_seconds() / 3600.0
                mark_outreach_held(db, target_outreach, evaluation.reason or "Overdue staleness gate exceeded", overdue_hours, current_time)
                cc.current_step = next_step_num
                db.commit()
                actions_taken.append({
                    "action": "held",
                    "step_number": next_step_num,
                    "reason": evaluation.reason,
                    "outreach_id": str(target_outreach.id),
                })
                break
            else:
                actions_taken.append({
                    "action": "skipped",
                    "step_number": next_step_num,
                    "reason": evaluation.reason,
                })
                break

        # 10. Prepare or Retrieve Outreach for next_step_num
        target_outreach = None
        if existing_for_step:
            target_outreach = existing_for_step[0]
            if target_outreach.status == "sent":
                cc.current_step = next_step_num
                db.flush()
                continue
            elif target_outreach.status in ("sending", "failed", "cancelled"):
                break
        else:
            target_outreach = _create_step_outreach(
                db=db,
                camp=camp,
                cc=cc,
                contact=contact,
                step=next_step,
                scheduled_at=None if is_zero_delay else due_time,
                initial_status="draft" if not auto_dispatch else "draft",
                sender_name=sender_name,
            )
            if last_outreach and getattr(last_outreach, "call_record_id", None):
                target_outreach.call_record_id = last_outreach.call_record_id
            cc.current_step = next_step_num
            db.flush()

        if not auto_dispatch:
            db.commit()
            actions_taken.append({
                "action": "draft_created",
                "step_number": next_step_num,
                "outreach_id": str(target_outreach.id),
            })
            break

        # 11. Auto-dispatch the step
        channel = getattr(next_step, "step_type", "email") or "email"
        dispatch_success = False

        if channel == "email":
            try:
                from app.services.outreach.service import send_outreach
                sent_o = send_outreach(
                    db=db,
                    org_id=resolved_org_id,
                    outreach_id=target_outreach.id,
                    provider=email_provider,
                    raise_on_failure=True,
                    auto_advance_sequence=False,
                    sent_at=current_time,
                )
                if sent_o and sent_o.status == "sent":
                    dispatch_success = True
                    actions_taken.append({
                        "action": "dispatched",
                        "step_number": next_step_num,
                        "channel": "email",
                        "outreach_id": str(sent_o.id),
                    })
            except Exception as exc:
                logger.warning("Failed email auto-dispatch for step %s of %s: %s", next_step_num, cc.id, exc)
                actions_taken.append({
                    "action": "failed",
                    "step_number": next_step_num,
                    "error": str(exc),
                })
                break

        elif channel == "voice":
            try:
                from app.services.voice.service import send_voice_outreach
                voice_o = send_voice_outreach(
                    db=db,
                    org_id=resolved_org_id,
                    outreach_id=target_outreach.id,
                    retell_client=retell_client,
                    raise_on_failure=True,
                    force_mock=force_mock,
                )
                actions_taken.append({
                    "action": "dispatched",
                    "step_number": next_step_num,
                    "channel": "voice",
                    "outreach_id": str(voice_o.id),
                })
                # Voice call is in-flight ('sending'). Progression pauses until completion event!
                break
            except Exception as exc:
                logger.warning("Failed voice auto-dispatch for step %s of %s: %s", next_step_num, cc.id, exc)
                actions_taken.append({
                    "action": "failed",
                    "step_number": next_step_num,
                    "error": str(exc),
                })
                break

        elif channel == "sms":
            try:
                from app.services.sms.service import send_sms_outreach
                sms_o = send_sms_outreach(
                    db=db,
                    org_id=resolved_org_id,
                    outreach_id=target_outreach.id,
                    raise_on_failure=True,
                    auto_advance_sequence=False,
                    sent_at=current_time,
                )
                if sms_o and sms_o.status == "sent":
                    dispatch_success = True
                    actions_taken.append({
                        "action": "dispatched",
                        "step_number": next_step_num,
                        "channel": "sms",
                        "outreach_id": str(sms_o.id),
                    })
            except Exception as exc:
                logger.warning("Failed SMS auto-dispatch for step %s of %s: %s", next_step_num, cc.id, exc)
                actions_taken.append({
                    "action": "failed",
                    "step_number": next_step_num,
                    "error": str(exc),
                })
                break

        elif channel == "physical_mail":
            try:
                from app.services.physical_mail.service import send_single_physical_mail_outreach
                mail_o = send_single_physical_mail_outreach(
                    db=db,
                    org_id=resolved_org_id,
                    outreach_id=target_outreach.id,
                    force_mock=force_mock,
                )
                actions_taken.append({
                    "action": "dispatched",
                    "step_number": next_step_num,
                    "channel": "physical_mail",
                    "outreach_id": str(mail_o.id),
                })
                # Physical mail is queued for print & delivery; pauses progression
                break
            except Exception as exc:
                logger.warning("Failed physical mail auto-dispatch for step %s of %s: %s", next_step_num, cc.id, exc)
                break

        elif channel == "linkedin":
            actions_taken.append({
                "action": "queued",
                "step_number": next_step_num,
                "channel": "linkedin",
                "outreach_id": str(target_outreach.id),
            })
            break

        # If synchronous dispatch succeeded (email/sms), loop to next step!
        if dispatch_success:
            continue
        else:
            break

    return actions_taken


class CampaignSchedulerService:
    """
    Core scheduler service managing multi-day step progression and automated dispatch.
    Enforces strict tenant isolation, UTC timezone awareness, and comprehensive stop conditions.
    """

    def __init__(self, db: Session):
        self.db = db

    def advance_campaign_contact_sequence(
        self,
        campaign_contact_id: uuid.UUID,
        org_id: Optional[uuid.UUID] = None,
        now: Optional[datetime] = None,
        email_provider: Optional[EmailProvider] = None,
        retell_client: Optional[Any] = None,
        auto_dispatch: bool = True,
        sender_name: Optional[str] = None,
        max_steps_per_call: int = 10,
        force_mock: bool = False,
    ) -> List[Dict[str, Any]]:
        return advance_campaign_contact_sequence(
            db=self.db,
            campaign_contact_id=campaign_contact_id,
            org_id=org_id,
            now=now,
            email_provider=email_provider,
            retell_client=retell_client,
            auto_dispatch=auto_dispatch,
            sender_name=sender_name,
            max_steps_per_call=max_steps_per_call,
            force_mock=force_mock,
        )

    def list_held_outreaches(self, org_id: uuid.UUID) -> List[Dict[str, Any]]:
        return list_held_outreaches(self.db, org_id)

    def resolve_held_outreach(
        self,
        org_id: uuid.UUID,
        outreach_id: uuid.UUID,
        action: str,
        provider: Optional[EmailProvider] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        return resolve_held_outreach(self.db, org_id, outreach_id, action, provider=provider, user_id=user_id)

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
        org_id: uuid.UUID,
        campaign_id: Optional[uuid.UUID] = None,
        now: Optional[datetime] = None,
        dry_run: bool = False,
        sender_name: Optional[str] = None,
    ) -> SchedulerTickResult:
        """
        Evaluates eligible enrollments across active campaigns and advances due steps.
        Requires an explicit org_id to strictly enforce tenant isolation and prevent global sweeps.
        Calculates delays using delay_days and delay_hours relative to previous step completion.
        Enforces stop conditions (replies, bounces, opt-outs, meetings) and exhausts completed sequences.
        """
        if org_id is None:
            raise ValueError("plan_due_steps requires an explicit org_id. Unrestricted global sweeps are prohibited.")

        current_time = now if now is not None else datetime.now(timezone.utc)
        result = SchedulerTickResult(dry_run=dry_run)

        # 1. Query active campaigns strictly scoped to the tenant organization
        camp_query = self.db.query(Campaign).filter(
            Campaign.status == "active",
            Campaign.organization_id == org_id,
        )
        if campaign_id:
            camp_query = camp_query.filter(Campaign.id == campaign_id)

        campaigns = camp_query.all()
        if not campaigns:
            result.message = "No active campaigns found for scheduling."
            return result

        for camp in campaigns:
            try:
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

                            # Step 1 Staleness Gate
                            max_overdue_seconds = settings.SCHEDULER_MAX_OVERDUE_HOURS * 3600
                            overdue_seconds = (current_time - step1_due_time).total_seconds()
                            if overdue_seconds > max_overdue_seconds:
                                overdue_hours = overdue_seconds / 3600.0
                                hold_reason = (
                                    f"Step 1 is overdue by {overdue_hours:.1f}h (due at {step1_due_time.isoformat()}), "
                                    f"exceeding the maximum allowed staleness threshold of {settings.SCHEDULER_MAX_OVERDUE_HOURS}h. "
                                    "Held for manual review."
                                )
                                if not dry_run:
                                    company = (
                                        self.db.query(Company)
                                        .filter(Company.id == contact.company_id, Company.organization_id == camp.organization_id)
                                        .first()
                                        if contact.company_id else None
                                    )
                                    step1_channel = getattr(step_1, "step_type", "email") or "email"
                                    rendered_subj = (
                                        render_template(step_1.subject_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                        if step_1.subject_template else (None if step1_channel in ("sms", "voice") else "")
                                    )
                                    rendered_body = (
                                        render_template(step_1.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                        if step_1.body_template else (None if step1_channel == "voice" else "")
                                    )
                                    outreach_payload = OutreachCreate(
                                        campaign_id=camp.id,
                                        contact_id=cc.contact_id,
                                        campaign_contact_id=cc.id,
                                        channel=step1_channel,
                                        subject=rendered_subj,
                                        body=rendered_body,
                                        scheduled_at=step1_due_time,
                                    )
                                    new_o = create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
                                    mark_outreach_held(self.db, new_o, hold_reason, overdue_hours, current_time)
                                    cc.enrollment_status = "in_progress"
                                    cc.current_step = 1
                                    self.db.flush()
                                result.held_count += 1
                                result.details.append({
                                    "campaign_contact_id": str(cc.id),
                                    "contact_id": str(contact.id),
                                    "action": "held",
                                    "step_number": 1,
                                    "reason": hold_reason,
                                })
                                continue

                            evaluation = evaluate_campaign_contact(camp, cc, contact, existing_outreaches)
                            if evaluation.result != EvaluationResult.ELIGIBLE:
                                if evaluation.result == EvaluationResult.HELD:
                                    if not dry_run:
                                        if not existing_for_step:
                                            company = (
                                                self.db.query(Company)
                                                .filter(Company.id == contact.company_id, Company.organization_id == camp.organization_id)
                                                .first()
                                                if contact.company_id else None
                                            )
                                            next_channel = getattr(next_step, "step_type", "email") or "email"
                                            rendered_subj = (
                                                render_template(next_step.subject_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                                if next_step.subject_template else (None if next_channel in ("sms", "voice") else "")
                                            )
                                            rendered_body = (
                                                render_template(next_step.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                                if next_step.body_template else (None if next_channel == "voice" else "")
                                            )
                                            sent_time = _ensure_utc(last_outreach.sent_at or last_outreach.created_at)
                                            delay_delta = timedelta(days=next_step.delay_days, hours=next_step.delay_hours)
                                            due_time = sent_time + delay_delta
                                            outreach_payload = OutreachCreate(
                                                campaign_id=camp.id,
                                                contact_id=cc.contact_id,
                                                campaign_contact_id=cc.id,
                                                channel=next_channel,
                                                subject=rendered_subj,
                                                body=rendered_body,
                                                scheduled_at=due_time,
                                            )
                                            new_o = create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
                                            overdue_hours = (current_time - due_time).total_seconds() / 3600.0
                                            mark_outreach_held(self.db, new_o, evaluation.reason or "Overdue staleness", overdue_hours, current_time)
                                            cc.current_step = next_step_num
                                            self.db.flush()
                                    result.held_count += 1
                                    result.details.append({
                                        "campaign_contact_id": str(cc.id),
                                        "contact_id": str(contact.id),
                                        "action": "held",
                                        "step_number": next_step_num,
                                        "reason": evaluation.reason,
                                    })
                                    continue
                                else:
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
                            if step1_channel == "sms":
                                from app.services.sms.service import is_sms_suppressed
                                suppressed, supp_reason = is_sms_suppressed(self.db, camp.organization_id, phone=contact.phone, contact=contact)
                                if suppressed:
                                    result.details.append({
                                        "campaign_contact_id": str(cc.id),
                                        "action": "skipped_sms_suppression",
                                        "reason": supp_reason,
                                    })
                                    continue
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
                                    scheduled_at=current_time,
                                )
                                new_o = create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
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
                                if evaluation.result == EvaluationResult.HELD:
                                    if not dry_run:
                                        if not existing_for_step:
                                            company = (
                                                self.db.query(Company)
                                                .filter(Company.id == contact.company_id, Company.organization_id == camp.organization_id)
                                                .first()
                                                if contact.company_id else None
                                            )
                                            next_channel = getattr(next_step, "step_type", "email") or "email"
                                            rendered_subj = (
                                                render_template(next_step.subject_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                                if next_step.subject_template else (None if next_channel in ("sms", "voice") else "")
                                            )
                                            rendered_body = (
                                                render_template(next_step.body_template, contact=contact, company=company, sender_name=sender_name, booking_link=org_booking_url)
                                                if next_step.body_template else (None if next_channel == "voice" else "")
                                            )
                                            sent_time = _ensure_utc(last_outreach.sent_at or last_outreach.created_at)
                                            delay_delta = timedelta(days=next_step.delay_days, hours=next_step.delay_hours)
                                            due_time = sent_time + delay_delta
                                            outreach_payload = OutreachCreate(
                                                campaign_id=camp.id,
                                                contact_id=cc.contact_id,
                                                campaign_contact_id=cc.id,
                                                channel=next_channel,
                                                subject=rendered_subj,
                                                body=rendered_body,
                                                scheduled_at=due_time,
                                            )
                                            new_o = create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
                                            overdue_hours = (current_time - due_time).total_seconds() / 3600.0
                                            mark_outreach_held(self.db, new_o, evaluation.reason or "Overdue staleness", overdue_hours, current_time)
                                            cc.current_step = next_step_num
                                            self.db.flush()
                                    result.held_count += 1
                                    result.details.append({
                                        "campaign_contact_id": str(cc.id),
                                        "contact_id": str(contact.id),
                                        "action": "held",
                                        "step_number": next_step_num,
                                        "reason": evaluation.reason,
                                    })
                                    continue
                                else:
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
                            if next_channel == "sms":
                                from app.services.sms.service import is_sms_suppressed
                                suppressed, supp_reason = is_sms_suppressed(self.db, camp.organization_id, phone=contact.phone, contact=contact)
                                if suppressed:
                                    result.details.append({
                                        "campaign_contact_id": str(cc.id),
                                        "action": "skipped_sms_suppression",
                                        "reason": supp_reason,
                                    })
                                    continue
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
                                sent_time = _ensure_utc(last_outreach.sent_at or last_outreach.created_at)
                                delay_delta = timedelta(days=next_step.delay_days, hours=next_step.delay_hours)
                                due_time = sent_time + delay_delta
                                outreach_payload = OutreachCreate(
                                    campaign_id=camp.id,
                                    contact_id=cc.contact_id,
                                    campaign_contact_id=cc.id,
                                    channel=next_channel,
                                    subject=rendered_subj,
                                    body=rendered_body,
                                    scheduled_at=due_time,
                                )
                                new_o = create_outreach(self.db, camp.organization_id, outreach_payload, commit=False)
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

            except Exception as camp_exc:
                logger.error("Error processing campaign %s ('%s'): %s", camp.id, getattr(camp, 'name', 'unknown'), camp_exc, exc_info=True)
                self.db.rollback()
                result.error_count += 1
                result.details.append({
                    'campaign_id': str(camp.id),
                    'action': 'campaign_error',
                    'reason': str(camp_exc),
                })
                continue
        if not dry_run:
            self.db.commit()

        result.message = (
            f"Scheduler planning complete: {result.planned_count} planned, "
            f"{result.completed_count} completed, {result.held_count} held, "
            f"{result.halted_count} halted, {result.skipped_count} skipped, {result.error_count} errors."
        )
        return result

    def dispatch_scheduled_outreach(
        self,
        org_id: uuid.UUID,
        now: Optional[datetime] = None,
        dry_run: bool = False,
        provider: Optional[EmailProvider] = None,
    ) -> SchedulerTickResult:
        """
        Dispatches pending scheduled Outreach records whose scheduled_at timestamp is due.
        Requires an explicit org_id to strictly enforce tenant isolation and prevent global sweeps.
        Enforces maximum overdue staleness gate: any outreach overdue by > SCHEDULER_MAX_OVERDUE_HOURS
        is automatically held for manual review and never dispatched.
        """
        if org_id is None:
            raise ValueError("dispatch_scheduled_outreach requires an explicit org_id. Unrestricted global sweeps are prohibited.")

        current_time = now if now is not None else datetime.now(timezone.utc)
        result = SchedulerTickResult(dry_run=dry_run)

        query = (
            self.db.query(Outreach)
            .filter(
                Outreach.organization_id == org_id,
                Outreach.status.in_(["scheduled", "draft"]),
            )
            .order_by(Outreach.scheduled_at.asc().nullsfirst())
        )

        if not dry_run and self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        all_candidates = query.limit(settings.SCHEDULER_BATCH_SIZE * 2).all()
        if not all_candidates:
            return result

        cand_ids = [c.id for c in all_candidates]
        from app.models.outreach import OutreachEvent
        held_events = (
            self.db.query(OutreachEvent)
            .filter(
                OutreachEvent.outreach_id.in_(cand_ids),
            )
            .order_by(OutreachEvent.occurred_at.asc())
            .all()
        )
        held_map: dict[uuid.UUID, bool] = {}
        for evt in held_events:
            if evt.event_metadata and "held_for_manual_review" in evt.event_metadata:
                held_map[evt.outreach_id] = bool(evt.event_metadata.get("held_for_manual_review"))

        due_outreaches = []
        for o in all_candidates:
            # 1. Skip if already held for manual review
            if held_map.get(o.id) is True:
                result.skipped_count += 1
                result.details.append({
                    "outreach_id": str(o.id),
                    "action": "skipped_held",
                    "reason": "Outreach is held for manual review.",
                })
                continue

            # 2. Check overdue staleness gate on scheduled_at
            if o.scheduled_at:
                sched_utc = _ensure_utc(o.scheduled_at)
                overdue_seconds = (current_time - sched_utc).total_seconds()
                max_overdue_seconds = settings.SCHEDULER_MAX_OVERDUE_HOURS * 3600
                if overdue_seconds > max_overdue_seconds:
                    overdue_hours = overdue_seconds / 3600.0
                    hold_reason = (
                        f"Outreach scheduled for {sched_utc.isoformat()} is overdue by {overdue_hours:.1f}h, "
                        f"exceeding the maximum allowed staleness threshold of {settings.SCHEDULER_MAX_OVERDUE_HOURS}h. "
                        "Held for manual review."
                    )
                    if not dry_run:
                        mark_outreach_held(self.db, o, hold_reason, overdue_hours, current_time)
                        self.db.flush()
                    result.held_count += 1
                    result.details.append({
                        "outreach_id": str(o.id),
                        "action": "held",
                        "reason": hold_reason,
                    })
                    continue

            # 3. Check if due for dispatch
            is_due = (
                (o.status == "scheduled" and o.scheduled_at and _ensure_utc(o.scheduled_at) <= current_time)
                or (o.status == "draft" and o.campaign_contact_id is not None and (o.scheduled_at is None or _ensure_utc(o.scheduled_at) <= current_time))
            )
            if is_due:
                due_outreaches.append(o)
                if len(due_outreaches) >= settings.SCHEDULER_BATCH_SIZE:
                    break

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
                sent_o = send_outreach(
                    db=self.db,
                    org_id=o.organization_id,
                    outreach_id=o.id,
                    provider=provider,
                    raise_on_failure=False,
                    auto_advance_sequence=False,
                    sent_at=current_time,
                )
                if sent_o and sent_o.status == "sent":
                    result.dispatched_count += 1
                    result.details.append({
                        "outreach_id": str(o.id),
                        "action": "dispatched",
                        "recipient": o.recipient_email,
                    })
                    if o.campaign_contact_id:
                        advance_campaign_contact_sequence(
                            db=self.db,
                            campaign_contact_id=o.campaign_contact_id,
                            org_id=o.organization_id,
                            now=current_time,
                            email_provider=provider,
                            auto_dispatch=True,
                        )
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
        auto_dispatch: Optional[bool] = None,
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

        # Multi-Instance & Concurrency Protection: Acquire non-blocking advisory lock
        lock_acquired = False
        if not dry_run:
            lock_acquired = acquire_scheduler_lock(self.db)
            if not lock_acquired:
                logger.info("Another scheduler worker is currently executing a tick. Skipping run to prevent duplicate processing.")
                return SchedulerTickResult(
                    status="skipped",
                    message="Skipped: concurrent scheduler worker active.",
                    dry_run=dry_run,
                )

        try:
            # Target organization determination with strict tenant scoping
            target_org_ids: List[uuid.UUID] = []
            if org_id is not None:
                # Explicit org requested -> verify authorization
                if org_id not in settings.authorized_scheduler_org_ids:
                    logger.warning(
                        "Scheduler tick requested for unauthorized org_id: %s. "
                        "Configured authorized orgs: %s. Fails closed.",
                        org_id, settings.authorized_scheduler_org_ids,
                    )
                    return SchedulerTickResult(
                        status="skipped",
                        message=f"Organization {org_id} is not authorized for scheduler execution.",
                        dry_run=dry_run,
                    )
                target_org_ids = [org_id]
            else:
                # No org passed -> NEVER do a global sweep!
                # Iterate strictly over authorized orgs from settings
                target_org_ids = list(settings.authorized_scheduler_org_ids)
                if not target_org_ids:
                    logger.info(
                        "SCHEDULER_AUTHORIZED_ORGS is empty. Scheduler tick fails closed without executing any sweeps."
                    )
                    return SchedulerTickResult(
                        status="skipped",
                        message="No authorized organizations configured in SCHEDULER_AUTHORIZED_ORGS. Scheduler tick fails closed.",
                        dry_run=dry_run,
                    )

            combined_result = SchedulerTickResult(dry_run=dry_run)
            should_dispatch = auto_dispatch if auto_dispatch is not None else settings.SCHEDULER_AUTO_DISPATCH

            for target_org in target_org_ids:
                try:
                    # 1. Step planning and sequence advancement strictly scoped to target_org
                    plan_res = self.plan_due_steps(
                        org_id=target_org,
                        campaign_id=campaign_id,
                        now=now,
                        dry_run=dry_run,
                        sender_name=sender_name,
                    )

                    # 2. Message dispatch strictly scoped to target_org
                    dispatch_res = SchedulerTickResult(dry_run=dry_run)
                    if should_dispatch:
                        dispatch_res = self.dispatch_scheduled_outreach(
                            org_id=target_org,
                            now=now,
                            dry_run=dry_run,
                            provider=provider,
                        )

                    # 3. Persistent asynchronous campaign execution job worker processing
                    if should_dispatch and not dry_run:
                        try:
                            from app.services.campaign_execution.worker import CampaignJobWorker
                            job_worker = CampaignJobWorker(self.db, email_provider=provider)
                            worker_res = job_worker.run_single_tick(org_id=target_org, now=now)
                            combined_result.dispatched_count += worker_res.get("processed_count", 0)
                            combined_result.held_count += worker_res.get("held_count", 0)
                        except Exception as worker_exc:
                            logger.warning("Error running asynchronous job worker tick for org %s: %s", target_org, worker_exc)

                    combined_result.planned_count += plan_res.planned_count
                    combined_result.completed_count += plan_res.completed_count
                    combined_result.dispatched_count += dispatch_res.dispatched_count
                    combined_result.skipped_count += plan_res.skipped_count + dispatch_res.skipped_count
                    combined_result.halted_count += plan_res.halted_count + dispatch_res.halted_count
                    combined_result.held_count += plan_res.held_count + dispatch_res.held_count
                    combined_result.error_count += plan_res.error_count + dispatch_res.error_count
                    combined_result.details.extend(plan_res.details)
                    combined_result.details.extend(dispatch_res.details)
                except Exception as org_exc:
                    logger.error("Error executing scheduler tick for org %s: %s", target_org, org_exc, exc_info=True)
                    combined_result.error_count += 1
                    combined_result.details.append({
                        "org_id": str(target_org),
                        "action": "error",
                        "reason": str(org_exc),
                    })

            combined_result.status = "completed" if combined_result.error_count == 0 else "completed_with_errors"
            combined_result.message = (
                f"Scheduler tick complete: {combined_result.planned_count} planned, "
                f"{combined_result.dispatched_count} dispatched, {combined_result.held_count} held, "
                f"{combined_result.halted_count} halted, {combined_result.skipped_count} skipped, "
                f"{combined_result.error_count} errors across {len(target_org_ids)} authorized organization(s)."
            )
            return combined_result
        finally:
            if not dry_run and lock_acquired:
                release_scheduler_lock(self.db, lock_acquired)

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
