"""Campaign eligibility checking and safe enrollment service for qualified leads (Phase 5)."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Contact
from app.models.lead import Lead
from app.models.tenant import Organization
from app.schemas.qualification import (
    CampaignEligibilityResult,
    LeadCampaignEnrollResult,
)
from app.services.campaign_service import (
    ContactAlreadyEnrolledError,
    enroll_contact,
)
from app.services.lead_generation.service import convert_lead_to_crm


def check_lead_campaign_eligibility(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> CampaignEligibilityResult:
    """
    Evaluates whether a Lead is eligible for enrollment in a specified campaign.
    Checks qualification status, opt-out suppression, and duplicate enrollment.
    """
    lead = db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' not found.",
        )

    campaign = db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.organization_id == current_org.id,
        )
    ).scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign '{campaign_id}' not found.",
        )

    reasons: List[str] = []
    suppression_reasons: List[str] = []
    already_enrolled = False

    # 1. Qualification Status Guard
    if lead.qualification_status != "qualified":
        suppression_reasons.append(
            f"Lead is not qualified (current status: '{lead.qualification_status}'). Only qualified leads can be enrolled."
        )
    else:
        reasons.append(f"Lead is qualified with score {lead.lead_score or 0}/100.")

    # 2. Opt-out & Suppression Guard
    contact: Optional[Contact] = None
    if lead.contact_id:
        contact = db.execute(
            select(Contact).where(Contact.id == lead.contact_id)
        ).scalar_one_or_none()

    if contact and contact.lead_status == "opted_out":
        suppression_reasons.append("Associated CRM contact has opted out of communications.")
    elif lead.status in ("opted_out", "rejected"):
        suppression_reasons.append(f"Lead lifecycle status is '{lead.status}' (suppressed).")

    # 3. Campaign Status Check
    if campaign.status not in ("active", "draft"):
        suppression_reasons.append(f"Campaign is in '{campaign.status}' status (must be 'active' or 'draft').")
    else:
        reasons.append(f"Campaign '{campaign.name}' is {campaign.status}.")

    # 4. Duplicate Enrollment Check
    if contact:
        existing_enrollment = db.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.contact_id == contact.id,
            )
        ).scalar_one_or_none()

        if existing_enrollment:
            already_enrolled = True
            suppression_reasons.append(
                f"Contact is already enrolled in this campaign (status: '{existing_enrollment.enrollment_status}')."
            )

    # 5. Channel Availability Check
    is_linkedin_campaign = False
    if getattr(campaign, "type", "") == "linkedin":
        is_linkedin_campaign = True
    elif campaign.workflow_config and isinstance(campaign.workflow_config, dict):
        nodes = campaign.workflow_config.get("nodes", [])
        if any(n.get("type") in ("linkedin", "linkedinNode") for n in nodes if isinstance(n, dict)):
            is_linkedin_campaign = True

    has_li_url = bool(getattr(lead, "linkedin_profile_url", None) or (contact and getattr(contact, "linkedin_profile_url", None)))

    if is_linkedin_campaign:
        if has_li_url:
            reasons.append("LinkedIn profile URL is available for assisted outreach.")
        else:
            reasons.append("Notice: Lead is missing a LinkedIn profile URL (manual lookup will be required in workspace).")
        # For LinkedIn campaigns, absence of email is non-fatal if LinkedIn or name is present
        if not lead.email and not (contact and contact.email) and not has_li_url:
            suppression_reasons.append("Lead has neither an email address nor a LinkedIn profile URL recorded.")
    else:
        if not lead.email and not (contact and contact.email):
            suppression_reasons.append("Lead does not have an email address recorded for campaign communication.")
        else:
            reasons.append("Valid communication channel (email) is present.")

    is_eligible = len(suppression_reasons) == 0 and not already_enrolled

    return CampaignEligibilityResult(
        lead_id=lead.id,
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        campaign_status=campaign.status,
        is_eligible=is_eligible,
        reasons=reasons,
        suppression_reasons=suppression_reasons,
        contact_id=contact.id if contact else None,
        already_enrolled=already_enrolled,
    )


def enroll_qualified_lead_in_campaign(
    db: Session,
    current_org: Organization,
    lead_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> LeadCampaignEnrollResult:
    """
    Explicitly enrolls a qualified Lead into a campaign.
    Converts lead to CRM Contact if not yet converted, enrolls into CampaignContact,
    and updates lead lifecycle status to 'enrolled'.
    Guarantees:
    - Never triggers automated message dispatch or calls upon enrollment.
    - Strictly prevents duplicate enrollments.
    - Honors opt-out and suppression rules.
    """
    eligibility = check_lead_campaign_eligibility(
        db=db,
        current_org=current_org,
        lead_id=lead_id,
        campaign_id=campaign_id,
    )

    if not eligibility.is_eligible:
        reasons_text = "; ".join(eligibility.suppression_reasons)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Lead is not eligible for campaign: {reasons_text}",
        )

    lead = db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == current_org.id,
        )
    ).scalar_one()

    # Resolve or create CRM Contact
    contact_id = lead.contact_id
    if not contact_id:
        conv_res = convert_lead_to_crm(db=db, current_org=current_org, lead_id=lead.id)
        contact_id = conv_res.contact_id

    # Enroll contact using existing campaign enrollment service
    try:
        campaign_contact = enroll_contact(
            db=db,
            org_id=current_org.id,
            campaign_id=campaign_id,
            contact_id=contact_id,
            enrollment_status="queued",
        )
    except ContactAlreadyEnrolledError:
        return LeadCampaignEnrollResult(
            lead_id=lead.id,
            campaign_id=campaign_id,
            contact_id=contact_id,
            status="already_enrolled",
            message=f"Lead contact is already enrolled in campaign '{eligibility.campaign_name}'.",
        )

    lead.status = "enrolled"
    db.commit()

    return LeadCampaignEnrollResult(
        lead_id=lead.id,
        campaign_id=campaign_id,
        contact_id=contact_id,
        campaign_contact_id=campaign_contact.id if campaign_contact else None,
        status="enrolled",
        message=f"Successfully enrolled into campaign '{eligibility.campaign_name}'. Outreach remains queued in draft state until explicit campaign activation.",
    )
