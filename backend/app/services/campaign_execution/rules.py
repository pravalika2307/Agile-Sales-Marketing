"""Eligibility and validation rules for campaign outreach execution (Step 8)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Contact
from app.models.outreach import Outreach


class EvaluationResult(str, Enum):
    ELIGIBLE = "eligible"
    SKIPPED = "skipped"
    REJECTED = "rejected"


@dataclass
class ContactEvaluation:
    campaign_contact_id: uuid.UUID
    result: EvaluationResult
    reason: Optional[str] = None


# Statuses that prevent creating another outreach for the initial step
NON_DUPLICATE_OUTREACH_STATUSES = {
    "draft",
    "scheduled",
    "sending",
    "sent",
    "failed",
}


def evaluate_campaign_contact(
    campaign: Campaign,
    campaign_contact: CampaignContact,
    contact: Optional[Contact],
    existing_outreaches: List[Outreach],
) -> ContactEvaluation:
    """
    Evaluates whether a CampaignContact is eligible, skipped, or rejected for initial outreach.

    Rules:
    - REJECTED if:
      - Relationship inconsistency (contact_id mismatch, campaign_id mismatch, contact missing)
      - Cross-tenant contact detected
    - SKIPPED if:
      - Campaign status is not 'active'
      - CampaignContact enrollment_status is not 'queued'
      - Contact lead_status is 'opted_out'
      - Existing outreach already exists with status in draft/scheduled/sending/sent/failed
    - ELIGIBLE if all rules pass.
    """
    cc_id = campaign_contact.id

    # 1. Validation & Relationship Inconsistency -> REJECTED
    if campaign_contact.campaign_id != campaign.id:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.REJECTED,
            reason="CampaignContact does not belong to the target campaign.",
        )

    if not contact or campaign_contact.contact_id != contact.id:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.REJECTED,
            reason="Contact does not match enrollment or contact record is missing.",
        )

    if contact.organization_id != campaign.organization_id:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.REJECTED,
            reason="Contact belongs to a different organization (cross-tenant relationship).",
        )

    # 2. Campaign State Rule -> SKIPPED if not active
    if campaign.status != "active":
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Campaign is in '{campaign.status}' status, must be 'active'.",
        )

    # 3. Enrollment Status Rule -> SKIPPED if not queued
    if campaign_contact.enrollment_status != "queued":
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Enrollment status is '{campaign_contact.enrollment_status}', must be 'queued'.",
        )

    # 4. Opt-Out Safety Rule -> SKIPPED if contact is opted_out
    if contact.lead_status == "opted_out":
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason="Contact lead_status is 'opted_out'.",
        )

    # 5. Duplicate Outreach Rule -> SKIPPED if draft/scheduled/sending/sent/failed outreach exists
    has_existing_outreach = any(o.status in NON_DUPLICATE_OUTREACH_STATUSES for o in existing_outreaches)
    if has_existing_outreach:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason="An outreach record already exists for this enrollment.",
        )

    # 6. All criteria met -> ELIGIBLE
    return ContactEvaluation(
        campaign_contact_id=cc_id,
        result=EvaluationResult.ELIGIBLE,
        reason="Enrollment qualifies for initial outreach.",
    )


def evaluate_subsequent_step_eligibility(
    campaign: Campaign,
    campaign_contact: CampaignContact,
    contact: Optional[Contact],
    next_step: CampaignStep,
    last_sent_outreach: Optional[Outreach],
    existing_outreaches_for_next_step: List[Outreach],
    now: datetime,
    has_meeting_requested: bool = False,
    required_condition: Optional[str] = None,
) -> ContactEvaluation:
    """
    Evaluates whether an in_progress CampaignContact is eligible for the next sequence step.

    Rules:
    - REJECTED if:
      - Relationship inconsistency (contact_id mismatch, campaign_id mismatch, contact missing)
      - Cross-tenant contact detected
    - SKIPPED if:
      - Campaign status is not 'active'
      - CampaignContact enrollment_status is not 'in_progress'
      - Contact lead_status is 'opted_out' or 'unsubscribed'
      - Contact has replied (lead_status is 'replied' or last outreach has first_replied_at)
      - Last outreach has first_bounced_at
      - Contact has requested or confirmed a meeting
      - Previous step outreach is not in 'sent' status (failed or missing delivery halts sequence)
      - Delay duration (delay_days + delay_hours) has not elapsed since previous outreach sent_at
      - Duplicate outreach already exists for the target step
    - ELIGIBLE if all rules pass.
    """
    cc_id = campaign_contact.id

    # 1. Validation & Relationship Inconsistency -> REJECTED
    if campaign_contact.campaign_id != campaign.id:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.REJECTED,
            reason="CampaignContact does not belong to the target campaign.",
        )

    if not contact or campaign_contact.contact_id != contact.id:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.REJECTED,
            reason="Contact does not match enrollment or contact record is missing.",
        )

    if contact.organization_id != campaign.organization_id:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.REJECTED,
            reason="Contact belongs to a different organization (cross-tenant relationship).",
        )

    # 2. Campaign State Rule -> SKIPPED if not active
    if campaign.status != "active":
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Campaign is in '{campaign.status}' status, must be 'active'.",
        )

    # 3. Enrollment Status Rule -> SKIPPED if not in_progress
    if campaign_contact.enrollment_status != "in_progress":
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Enrollment status is '{campaign_contact.enrollment_status}', must be 'in_progress'.",
        )

    # 4. Opt-Out & Suppression Rule
    if contact.lead_status in ("opted_out", "unsubscribed"):
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Contact lead_status is '{contact.lead_status}'.",
        )

    # 5. Reply Stop Condition
    if contact.lead_status == "replied" or (last_sent_outreach and last_sent_outreach.first_replied_at is not None):
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason="Prospect has replied to campaign outreach.",
        )

    # 6. Bounce Stop Condition
    if last_sent_outreach and last_sent_outreach.first_bounced_at is not None:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason="Previous step outreach delivery bounced.",
        )

    # 7. Meeting Requested Stop Condition
    if has_meeting_requested:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason="Prospect requested or confirmed a meeting (cold cadence halted).",
        )

    # 8. Previous Step Delivery Rule: Sequence only advances if previous step succeeded
    if not last_sent_outreach or last_sent_outreach.status != "sent":
        prev_status = last_sent_outreach.status if last_sent_outreach else "missing"
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Previous step delivery is not 'sent' (current status: '{prev_status}').",
        )

    # 8.5 Required Condition Rule (e.g. email_opened)
    if required_condition == "email_opened" and last_sent_outreach and last_sent_outreach.first_opened_at is None:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Step {next_step.step_number} requires previous email to be opened before advancing.",
        )

    # 9. Delay Elapsed Rule
    sent_time = last_sent_outreach.sent_at or last_sent_outreach.created_at
    if sent_time.tzinfo is None:
        sent_time = sent_time.replace(tzinfo=timezone.utc)
    current_time = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    due_time = sent_time + timedelta(days=next_step.delay_days, hours=next_step.delay_hours)
    if current_time < due_time:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"Step {next_step.step_number} delay not elapsed. Due at {due_time.isoformat()} (current: {current_time.isoformat()}).",
        )

    # 10. Duplicate Outreach Rule for target step
    has_dup = any(o.status in NON_DUPLICATE_OUTREACH_STATUSES for o in existing_outreaches_for_next_step)
    if has_dup:
        return ContactEvaluation(
            campaign_contact_id=cc_id,
            result=EvaluationResult.SKIPPED,
            reason=f"An outreach record already exists for step {next_step.step_number}.",
        )

    # 11. All criteria met -> ELIGIBLE
    return ContactEvaluation(
        campaign_contact_id=cc_id,
        result=EvaluationResult.ELIGIBLE,
        reason=f"Enrollment qualifies for step {next_step.step_number}.",
    )

