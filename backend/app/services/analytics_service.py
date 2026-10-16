"""Analytics service calculating truthful, tenant-scoped operational metrics from PostgreSQL."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.contact_list import ContactList, ContactListMember
from app.models.crm import Company, Contact, Deal, PipelineStage
from app.models.lead import Lead
from app.models.outreach import Outreach
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    CampaignMetricsOverview,
    CampaignPerformanceSummary,
    EmailActivityDetails,
    FunnelMetrics,
    FunnelStageMetrics,
    LeadMetrics,
    OutreachMetricsOverview,
    PipelineMetricsOverview,
    PositiveProspectResponse,
    UnifiedActivityItem,
    UnifiedActivityResponse,
    VoiceActivityDetails,
    VoiceCallMetricsOverview,
)


def get_analytics_overview(db: Session, organization_id: uuid.UUID) -> AnalyticsOverviewResponse:
    """
    Computes real analytics metrics directly from database records for the given organization.
    Never fabricates or projects synthetic data.
    """
    # ── 1. Leads Metrics ──────────────────────────────────────────────────────────
    total_leads = (
        db.query(func.count(Lead.id))
        .filter(Lead.organization_id == organization_id)
        .scalar()
        or 0
    )
    qualified_leads = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.organization_id == organization_id,
            Lead.qualification_status == "qualified",
            Lead.source != "retell_voice_call",
        )
        .scalar()
        or 0
    )

    lead_status_rows = (
        db.query(Lead.status, func.count(Lead.id))
        .filter(Lead.organization_id == organization_id)
        .group_by(Lead.status)
        .all()
    )
    lead_status_breakdown = {row[0]: row[1] for row in lead_status_rows if row[0]}

    temp_rows = (
        db.query(Lead.lead_temperature, func.count(Lead.id))
        .filter(Lead.organization_id == organization_id)
        .group_by(Lead.lead_temperature)
        .all()
    )
    lead_temp_breakdown = {row[0]: row[1] for row in temp_rows if row[0]}

    leads_overview = LeadMetrics(
        total_leads=total_leads,
        qualified_leads=qualified_leads,
        status_breakdown=lead_status_breakdown,
        temperature_breakdown=lead_temp_breakdown,
    )

    # ── 2. Campaigns Overview ───────────────────────────────────────────────────
    campaign_status_rows = (
        db.query(Campaign.status, func.count(Campaign.id))
        .filter(Campaign.organization_id == organization_id)
        .group_by(Campaign.status)
        .all()
    )
    camp_status_dict = {row[0]: row[1] for row in campaign_status_rows if row[0]}

    total_campaigns = sum(camp_status_dict.values())
    active_campaigns = camp_status_dict.get("active", 0)
    draft_campaigns = camp_status_dict.get("draft", 0)
    paused_campaigns = camp_status_dict.get("paused", 0)
    completed_campaigns = camp_status_dict.get("completed", 0)

    enrolled_contacts = (
        db.query(func.count(CampaignContact.id))
        .join(Campaign, CampaignContact.campaign_id == Campaign.id)
        .filter(Campaign.organization_id == organization_id)
        .scalar()
        or 0
    )

    campaigns_overview = CampaignMetricsOverview(
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        draft_campaigns=draft_campaigns,
        paused_campaigns=paused_campaigns,
        completed_campaigns=completed_campaigns,
        enrolled_contacts=enrolled_contacts,
    )

    # ── 3. Outreach Metrics ───────────────────────────────────────────────────────
    outreach_rows = (
        db.query(
            Outreach.status,
            func.count(Outreach.id),
        )
        .filter(Outreach.organization_id == organization_id)
        .group_by(Outreach.status)
        .all()
    )
    outreach_status_dict = {row[0]: row[1] for row in outreach_rows if row[0]}

    total_outreach = sum(outreach_status_dict.values())
    draft_outreach = outreach_status_dict.get("draft", 0)
    scheduled_outreach = outreach_status_dict.get("scheduled", 0)
    sent_outreach = outreach_status_dict.get("sent", 0)
    failed_outreach = outreach_status_dict.get("failed", 0)

    # Event milestone counts from timestamp fields
    delivered_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_delivered_at.isnot(None),
        )
        .scalar()
        or 0
    )
    opened_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_opened_at.isnot(None),
        )
        .scalar()
        or 0
    )
    clicked_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_clicked_at.isnot(None),
        )
        .scalar()
        or 0
    )
    replied_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_replied_at.isnot(None),
        )
        .scalar()
        or 0
    )
    bounced_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_bounced_at.isnot(None),
        )
        .scalar()
        or 0
    )

    channel_rows = (
        db.query(Outreach.channel, func.count(Outreach.id))
        .filter(Outreach.organization_id == organization_id)
        .group_by(Outreach.channel)
        .all()
    )
    channel_breakdown = {row[0]: row[1] for row in channel_rows if row[0]}

    outreach_overview = OutreachMetricsOverview(
        total_outreach=total_outreach,
        draft=draft_outreach,
        scheduled=scheduled_outreach,
        sent=sent_outreach,
        delivered=delivered_count,
        opened=opened_count,
        clicked=clicked_count,
        replied=replied_count,
        bounced=bounced_count,
        failed=failed_outreach,
        channel_breakdown=channel_breakdown,
    )

    # ── 4. Voice Call Metrics ───────────────────────────────────────────────────
    total_calls = (
        db.query(func.count(CallRecord.id))
        .filter(CallRecord.organization_id == organization_id)
        .scalar()
        or 0
    )

    completed_calls = (
        db.query(func.count(CallRecord.id))
        .filter(
            CallRecord.organization_id == organization_id,
            (CallRecord.call_status.in_(["ended", "analyzed"])) | (CallRecord.duration_ms > 0),
        )
        .scalar()
        or 0
    )

    avg_duration_ms = (
        db.query(func.avg(CallRecord.duration_ms))
        .filter(
            CallRecord.organization_id == organization_id,
            CallRecord.duration_ms.isnot(None),
        )
        .scalar()
    )
    avg_duration_sec = round(float(avg_duration_ms) / 1000.0, 1) if avg_duration_ms is not None else None

    outcome_rows = (
        db.query(CallRecord.call_outcome, func.count(CallRecord.id))
        .filter(CallRecord.organization_id == organization_id)
        .group_by(CallRecord.call_outcome)
        .all()
    )
    outcome_breakdown = {
        (row[0] or "UNRECORDED"): row[1]
        for row in outcome_rows
    }

    voice_overview = VoiceCallMetricsOverview(
        total_calls=total_calls,
        completed_calls=completed_calls,
        average_duration_seconds=avg_duration_sec,
        outcome_breakdown=outcome_breakdown,
    )

    # ── 5. Pipeline & Deals Metrics ─────────────────────────────────────────────
    deal_rows = (
        db.query(Deal.status, func.count(Deal.id), func.sum(Deal.amount))
        .filter(Deal.organization_id == organization_id)
        .group_by(Deal.status)
        .all()
    )
    total_deals = 0
    open_deals = 0
    won_deals = 0
    lost_deals = 0
    total_pipeline_value = 0.0
    won_pipeline_value = 0.0

    for status_name, count_val, sum_amount in deal_rows:
        total_deals += count_val
        val = float(sum_amount) if sum_amount else 0.0
        if status_name == "open":
            open_deals = count_val
            total_pipeline_value += val
        elif status_name == "won":
            won_deals = count_val
            won_pipeline_value += val
        elif status_name == "lost":
            lost_deals = count_val

    pipeline_overview = PipelineMetricsOverview(
        total_deals=total_deals,
        open_deals=open_deals,
        won_deals=won_deals,
        lost_deals=lost_deals,
        total_pipeline_value=total_pipeline_value,
        won_pipeline_value=won_pipeline_value,
    )

    # ── 6. Campaign Performance Summary ─────────────────────────────────────────
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.organization_id == organization_id)
        .order_by(Campaign.created_at.desc())
        .all()
    )

    perf_list: List[CampaignPerformanceSummary] = []
    for camp in campaigns:
        enrolled_c = (
            db.query(func.count(CampaignContact.id))
            .filter(CampaignContact.campaign_id == camp.id)
            .scalar()
            or 0
        )
        camp_outreach = (
            db.query(func.count(Outreach.id))
            .filter(Outreach.campaign_id == camp.id)
            .scalar()
            or 0
        )
        camp_sent = (
            db.query(func.count(Outreach.id))
            .filter(Outreach.campaign_id == camp.id, Outreach.status == "sent")
            .scalar()
            or 0
        )
        camp_deliv = (
            db.query(func.count(Outreach.id))
            .filter(Outreach.campaign_id == camp.id, Outreach.first_delivered_at.isnot(None))
            .scalar()
            or 0
        )
        camp_open = (
            db.query(func.count(Outreach.id))
            .filter(Outreach.campaign_id == camp.id, Outreach.first_opened_at.isnot(None))
            .scalar()
            or 0
        )
        camp_reply = (
            db.query(func.count(Outreach.id))
            .filter(Outreach.campaign_id == camp.id, Outreach.first_replied_at.isnot(None))
            .scalar()
            or 0
        )
        camp_bounce = (
            db.query(func.count(Outreach.id))
            .filter(Outreach.campaign_id == camp.id, Outreach.first_bounced_at.isnot(None))
            .scalar()
            or 0
        )

        perf_list.append(
            CampaignPerformanceSummary(
                id=camp.id,
                name=camp.name,
                type=camp.type,
                status=camp.status,
                enrolled_contacts_count=enrolled_c,
                outreach_count=camp_outreach,
                sent_count=camp_sent,
                delivered_count=camp_deliv,
                opened_count=camp_open,
                replied_count=camp_reply,
                bounced_count=camp_bounce,
            )
        )

    funnel_metrics = calculate_funnel_metrics(db, organization_id)
    positive_responses = get_positive_prospect_responses(db, organization_id)

    return AnalyticsOverviewResponse(
        leads=leads_overview,
        campaigns=campaigns_overview,
        outreach=outreach_overview,
        voice=voice_overview,
        pipeline=pipeline_overview,
        campaign_performance=perf_list,
        funnel=funnel_metrics,
        positive_responses=positive_responses,
    )


def get_positive_prospect_responses(
    db: Session, organization_id: uuid.UUID, limit: int = 50
) -> List[PositiveProspectResponse]:
    """
    Retrieves real positive prospect responses across channels (meeting requests, email replies,
    qualified leads) within the tenant organization.
    Links existing commercial deals if already present, or surfaces the response as needing
    an estimated subjective deal value from the user.
    """
    responses: List[PositiveProspectResponse] = []
    seen_contacts: set = set()

    # 1. Deals map for quick lookup: contact_id -> deal
    deals = (
        db.query(Deal)
        .filter(Deal.organization_id == organization_id)
        .order_by(Deal.created_at.desc())
        .all()
    )
    contact_to_deal: Dict[uuid.UUID, Deal] = {}
    for d in deals:
        if d.contact_id and d.contact_id not in contact_to_deal:
            contact_to_deal[d.contact_id] = d

    # 2. Voice calls with MEETING_REQUESTED or positive outcomes
    calls = (
        db.query(CallRecord)
        .filter(
            CallRecord.organization_id == organization_id,
            CallRecord.call_outcome.isnot(None),
            ~CallRecord.call_outcome.ilike("%not%"),
            ~CallRecord.call_outcome.ilike("%wrong%"),
            ~CallRecord.call_outcome.ilike("%do_not_contact%"),
            or_(
                CallRecord.call_outcome.ilike("%meeting%"),
                CallRecord.call_outcome.ilike("%positive%"),
                CallRecord.call_outcome == "INTERESTED",
                CallRecord.call_outcome == "QUALIFIED",
                CallRecord.call_outcome == "MEETING_REQUESTED",
            ),
        )
        .order_by(CallRecord.created_at.desc())
        .limit(limit)
        .all()
    )

    for c in calls:
        contact_id = c.contact_id
        contact_name = None
        company_name = None
        email = None
        phone = c.caller_phone or c.to_phone

        if contact_id:
            contact = db.query(Contact).filter(Contact.id == contact_id).first()
            if contact:
                contact_name = f"{contact.first_name} {contact.last_name}".strip()
                email = contact.email
                if contact.phone:
                    phone = contact.phone
                if contact.company:
                    company_name = contact.company.name
            seen_contacts.add(contact_id)

        deal = contact_to_deal.get(contact_id) if contact_id else None

        preview = c.summary or f"Voice Call outcome: {c.call_outcome}"
        responses.append(
            PositiveProspectResponse(
                id=f"call_{c.id}",
                contact_id=contact_id,
                contact_name=contact_name,
                company_name=company_name,
                email=email,
                phone=phone,
                channel="voice",
                response_type="meeting_requested" if "meeting" in (c.call_outcome or "").lower() else "qualified_call",
                response_preview=preview,
                occurred_at=c.created_at,
                deal_id=deal.id if deal else None,
                deal_name=deal.name if deal else None,
                deal_amount=float(deal.amount) if deal else None,
                deal_status=deal.status if deal else None,
                pipeline_stage_id=deal.pipeline_stage_id if deal else None,
                pipeline_stage_name=deal.pipeline_stage.name if deal and deal.pipeline_stage else None,
            )
        )

    # 3. Outreach emails that received replies
    replied_outreaches = (
        db.query(Outreach)
        .filter(
            Outreach.organization_id == organization_id,
            or_(
                Outreach.first_replied_at.isnot(None),
                Outreach.status == "replied",
            ),
        )
        .order_by(Outreach.first_replied_at.desc().nullslast())
        .limit(limit)
        .all()
    )

    for o in replied_outreaches:
        contact_id = o.contact_id
        contact_name = None
        company_name = None
        email = None
        phone = None

        if contact_id:
            if contact_id in seen_contacts:
                continue
            contact = db.query(Contact).filter(Contact.id == contact_id).first()
            if contact:
                contact_name = f"{contact.first_name} {contact.last_name}".strip()
                email = contact.email
                phone = contact.phone
                if contact.company:
                    company_name = contact.company.name
            seen_contacts.add(contact_id)

        deal = contact_to_deal.get(contact_id) if contact_id else None

        responses.append(
            PositiveProspectResponse(
                id=f"outreach_{o.id}",
                contact_id=contact_id,
                contact_name=contact_name,
                company_name=company_name,
                email=email,
                phone=phone,
                channel="email",
                response_type="email_replied",
                response_preview=f"Direct email reply received: {o.subject or 'Outreach response'}",
                occurred_at=o.first_replied_at or o.sent_at,
                deal_id=deal.id if deal else None,
                deal_name=deal.name if deal else None,
                deal_amount=float(deal.amount) if deal else None,
                deal_status=deal.status if deal else None,
                pipeline_stage_id=deal.pipeline_stage_id if deal else None,
                pipeline_stage_name=deal.pipeline_stage.name if deal and deal.pipeline_stage else None,
            )
        )

    # 4. Qualified Leads
    qualified_leads = (
        db.query(Lead)
        .filter(
            Lead.organization_id == organization_id,
            Lead.qualification_status == "qualified",
            Lead.source != "retell_voice_call",
        )
        .order_by(Lead.updated_at.desc().nullslast())
        .limit(limit)
        .all()
    )

    for l in qualified_leads:
        if l.contact_id and l.contact_id in seen_contacts:
            continue
        if l.contact_id:
            seen_contacts.add(l.contact_id)

        deal = contact_to_deal.get(l.contact_id) if l.contact_id else None

        responses.append(
            PositiveProspectResponse(
                id=f"lead_{l.id}",
                lead_id=l.id,
                contact_id=l.contact_id,
                contact_name=f"{l.first_name or ''} {l.last_name or ''}".strip() or None,
                company_name=l.company_name,
                email=l.email,
                phone=l.phone,
                channel="qualification",
                response_type="qualified_lead",
                response_preview=f"Lead qualified with score {l.lead_score or 0}/100 ({l.lead_temperature or 'warm'} temperature)",
                occurred_at=l.updated_at or l.created_at,
                deal_id=deal.id if deal else None,
                deal_name=deal.name if deal else None,
                deal_amount=float(deal.amount) if deal else None,
                deal_status=deal.status if deal else None,
                pipeline_stage_id=deal.pipeline_stage_id if deal else None,
                pipeline_stage_name=deal.pipeline_stage.name if deal and deal.pipeline_stage else None,
            )
        )

    return responses


def calculate_funnel_metrics(db: Session, organization_id: uuid.UUID) -> FunnelMetrics:
    """
    Calculates truthful, tenant-scoped end-to-end sales and marketing funnel metrics.
    Avoids double-counting between leads and contacts.
    Only counts actual verified activities and persisted database records.
    Never invents conversion rates or synthetic data.
    """
    # 1. Total Leads
    total_leads = (
        db.query(func.count(Lead.id))
        .filter(Lead.organization_id == organization_id)
        .scalar()
        or 0
    )

    # 2. Qualified Prospects: Genuine qualified leads (excluding synthetic retell_voice_call test artifacts)
    #    plus standalone qualified contacts (contacts created directly in CRM, not converted from an unqualified lead).
    qualified_leads = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.organization_id == organization_id,
            Lead.qualification_status == "qualified",
            Lead.source != "retell_voice_call",
        )
        .scalar()
        or 0
    )
    linked_contact_subq = (
        select(Lead.contact_id)
        .where(
            Lead.organization_id == organization_id,
            Lead.contact_id.isnot(None),
        )
    )
    unlinked_qualified_contacts = (
        db.query(func.count(Contact.id))
        .filter(
            Contact.organization_id == organization_id,
            Contact.lead_status == "qualified",
            Contact.id.notin_(linked_contact_subq),
        )
        .scalar()
        or 0
    )
    qualified_prospects = qualified_leads + unlinked_qualified_contacts

    # 3. Contacted Prospects (Distinct prospects with qualifying, persisted outreach evidence)
    # Evidence: Email sent (Outreach.sent_at is not None)
    #           Voice call placed (CallRecord.call_status in ['ended', 'analyzed'] or duration_ms > 0)
    email_contact_ids = set(
        r[0]
        for r in db.query(Outreach.contact_id)
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.sent_at.isnot(None),
            Outreach.contact_id.isnot(None),
        )
        .distinct()
        .all()
        if r[0]
    )

    voice_contact_ids = set(
        r[0]
        for r in db.query(CallRecord.contact_id)
        .filter(
            CallRecord.organization_id == organization_id,
            (CallRecord.call_status.in_(["ended", "analyzed"])) | (CallRecord.duration_ms > 0),
            CallRecord.contact_id.isnot(None),
        )
        .distinct()
        .all()
        if r[0]
    )

    voice_lead_ids = set(
        r[0]
        for r in db.query(CallRecord.lead_id)
        .filter(
            CallRecord.organization_id == organization_id,
            (CallRecord.call_status.in_(["ended", "analyzed"])) | (CallRecord.duration_ms > 0),
            CallRecord.lead_id.isnot(None),
        )
        .distinct()
        .all()
        if r[0]
    )

    all_contacted_contacts = email_contact_ids.union(voice_contact_ids)

    # Avoid double-counting if a contacted lead is already linked to a contacted contact
    if voice_lead_ids and all_contacted_contacts:
        linked_contacted_leads = set(
            r[0]
            for r in db.query(Lead.id)
            .filter(
                Lead.organization_id == organization_id,
                Lead.id.in_(voice_lead_ids),
                Lead.contact_id.in_(all_contacted_contacts),
            )
            .all()
            if r[0]
        )
        unlinked_contacted_leads = voice_lead_ids - linked_contacted_leads
    else:
        unlinked_contacted_leads = voice_lead_ids

    contacted_prospects = len(all_contacted_contacts) + len(unlinked_contacted_leads)

    # Activity counts (activities, strictly distinguished from unique prospects)
    email_sent_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.sent_at.isnot(None),
        )
        .scalar()
        or 0
    )
    voice_placed_count = (
        db.query(func.count(CallRecord.id))
        .filter(
            CallRecord.organization_id == organization_id,
            (CallRecord.call_status.in_(["ended", "analyzed"])) | (CallRecord.duration_ms > 0),
        )
        .scalar()
        or 0
    )
    total_outreach_activities = email_sent_count + voice_placed_count

    # 4. Engaged Prospects (Distinct prospects who actively engaged in business outreach)
    # Verification Rules & Provenance:
    # - Email outreach replies (Outreach.first_replied_at is not None) are authoritatively tracked and verified.
    # - Voice call engagement: CallRecord schema currently lacks test/environment metadata (no is_test or environment column).
    #   Per strict business rules: Connected calls (duration_ms > 0) represent telephony connection activities,
    #   NOT confirmed positive prospect engagement or qualification.
    #   Because reliable identification of test calls from genuine production calls is impossible using existing schema fields
    #   without inventing ad-hoc heuristics (such as matching email domains, contact names, or call duration),
    #   voice calls cannot be verified as commercial prospect engagements.
    #   Commercial prospect engagement is therefore strictly determined by verified commercial replies (email replies).
    #   Telephony connection activities are preserved separately under call activities and engaged_activities.
    email_engaged_contact_ids = set(
        r[0]
        for r in db.query(Outreach.contact_id)
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_replied_at.isnot(None),
            Outreach.contact_id.isnot(None),
        )
        .distinct()
        .all()
        if r[0]
    )

    engaged_prospects = len(email_engaged_contact_ids)

    # Engaged activity counts
    email_replies_count = (
        db.query(func.count(Outreach.id))
        .filter(
            Outreach.organization_id == organization_id,
            Outreach.first_replied_at.isnot(None),
        )
        .scalar()
        or 0
    )
    voice_connected_count = (
        db.query(func.count(CallRecord.id))
        .filter(
            CallRecord.organization_id == organization_id,
            CallRecord.duration_ms > 0,
            CallRecord.call_status.in_(["ended", "analyzed"]),
        )
        .scalar()
        or 0
    )
    total_engaged_activities = email_replies_count + voice_connected_count

    # 5. Pipeline Opportunities (Deals in open status)
    open_deals = (
        db.query(func.count(Deal.id))
        .filter(
            Deal.organization_id == organization_id,
            Deal.status == "open",
        )
        .scalar()
        or 0
    )

    # 6. Closed Won (Deals in won status)
    won_deals = (
        db.query(func.count(Deal.id))
        .filter(
            Deal.organization_id == organization_id,
            Deal.status == "won",
        )
        .scalar()
        or 0
    )

    # Meetings Requested vs Confirmed Bookings
    meetings_requested = (
        db.query(func.count(CallRecord.id))
        .filter(
            CallRecord.organization_id == organization_id,
            CallRecord.call_outcome.ilike("%meeting%"),
        )
        .scalar()
        or 0
    )
    confirmed_bookings = (
        db.query(func.count(CallRecord.id))
        .filter(
            CallRecord.organization_id == organization_id,
            CallRecord.call_outcome.in_(["meeting_scheduled", "booking_confirmed"]),
        )
        .scalar()
        or 0
    )

    # Calculate stage-to-stage and top-of-funnel conversion rates
    def calc_rate(numerator: int, denominator: int) -> Optional[float]:
        if denominator <= 0:
            return None
        return round((float(numerator) / float(denominator)) * 100.0, 1)

    top_count = total_leads if total_leads > 0 else (qualified_prospects if qualified_prospects > 0 else 0)

    # Determine stage-to-stage conversion for Contacted Prospects:
    # Rule: Use stage-to-stage rates only when numerator and denominator represent compatible populations.
    # If contacted prospects are not drawn exclusively from qualified prospects (e.g. contacted > qualified),
    # an unadjusted ratio would produce false percentages (e.g. 200% or 500%).
    # We check if contacted prospects is a subset of qualified prospects:
    if qualified_prospects > 0 and contacted_prospects <= qualified_prospects:
        contacted_prev_rate = calc_rate(contacted_prospects, qualified_prospects)
        contacted_formula = f"({contacted_prospects} contacted / {qualified_prospects} qualified prospects) × 100 = {contacted_prev_rate}%"
    elif top_count > 0:
        # Compatible baseline: Contacted prospects drawn from total lead pool
        contacted_prev_rate = calc_rate(contacted_prospects, top_count)
        contacted_formula = f"({contacted_prospects} contacted prospects / {top_count} total leads) × 100 = {contacted_prev_rate}% (outreach spans broader lead database)"
    else:
        contacted_prev_rate = None
        contacted_formula = "N/A (No prior lead population to evaluate)"

    stages = [
        FunnelStageMetrics(
            stage_id="total_leads",
            stage_name="Total Leads",
            count=total_leads,
            conversion_rate_from_previous=100.0 if total_leads > 0 else None,
            conversion_rate_from_top=100.0 if total_leads > 0 else None,
            channel_breakdown={"leads": total_leads},
            description="Tenant-scoped unique prospecting lead records in database",
            formula="Top-of-funnel discovery baseline (100%)",
            denominator_name="Total Leads",
        ),
        FunnelStageMetrics(
            stage_id="qualified_prospects",
            stage_name="Qualified Prospects",
            count=qualified_prospects,
            conversion_rate_from_previous=calc_rate(qualified_prospects, total_leads),
            conversion_rate_from_top=calc_rate(qualified_prospects, top_count),
            channel_breakdown={"lead_qualified": qualified_leads, "contact_qualified": unlinked_qualified_contacts},
            description="Verified qualification without lead/contact double-counting",
            formula=f"({qualified_prospects} qualified prospects / {total_leads} total leads) × 100 = {calc_rate(qualified_prospects, total_leads)}%" if total_leads > 0 else "N/A (0 total leads)",
            denominator_name="Total Leads",
        ),
        FunnelStageMetrics(
            stage_id="contacted",
            stage_name="Contacted Prospects",
            count=contacted_prospects,
            conversion_rate_from_previous=contacted_prev_rate,
            conversion_rate_from_top=calc_rate(contacted_prospects, top_count),
            channel_breakdown={
                "distinct_prospects": contacted_prospects,
                "emails_sent": email_sent_count,
                "calls_placed": voice_placed_count,
                "total_activities": total_outreach_activities,
            },
            description=f"{contacted_prospects} distinct prospects contacted across {total_outreach_activities} activities ({email_sent_count} emails, {voice_placed_count} calls)",
            formula=contacted_formula,
            denominator_name="Total Leads" if (qualified_prospects == 0 or contacted_prospects > qualified_prospects) else "Qualified Prospects",
        ),
        FunnelStageMetrics(
            stage_id="engaged",
            stage_name="Engaged Prospects",
            count=engaged_prospects,
            conversion_rate_from_previous=calc_rate(engaged_prospects, contacted_prospects) if engaged_prospects > 0 else None,
            conversion_rate_from_top=calc_rate(engaged_prospects, top_count) if engaged_prospects > 0 else None,
            channel_breakdown={
                "distinct_prospects": engaged_prospects,
                "email_replies": email_replies_count,
                "connected_calls": voice_connected_count,
                "total_activities": total_engaged_activities,
            },
            description=(
                f"{engaged_prospects} distinct prospect(s) engaged across {total_engaged_activities} activity sessions ({email_replies_count} replies, {voice_connected_count} connected calls)"
                if engaged_prospects > 0
                else (
                    f"0 verified commercial prospect engagements ({email_replies_count} email replies). Voice call engagement is unverified across {voice_connected_count} connected calls due to schema limitations (CallRecord lacks environment/test tracking)."
                    if voice_connected_count > 0
                    else "0 verified commercial prospect engagements across outreach channels."
                )
            ),
            formula=(
                f"({engaged_prospects} engaged prospects / {contacted_prospects} contacted prospects) × 100 = {calc_rate(engaged_prospects, contacted_prospects)}% (from verified email replies)"
                if engaged_prospects > 0 and contacted_prospects > 0
                else (
                    "N/A (No verified commercial responses; voice call engagement is unverified due to lack of environment/test tracking in CallRecord)"
                    if voice_connected_count > 0
                    else "N/A (0 verified commercial responses across outreach channels)"
                )
            ),
            denominator_name="Contacted Prospects",
        ),
        FunnelStageMetrics(
            stage_id="opportunities",
            stage_name="Pipeline Opportunities",
            count=open_deals,
            conversion_rate_from_previous=calc_rate(open_deals, engaged_prospects) if engaged_prospects > 0 else None,
            conversion_rate_from_top=calc_rate(open_deals, top_count) if engaged_prospects > 0 else None,
            channel_breakdown={"open_deals": open_deals},
            description="Active commercial opportunities in the sales pipeline",
            formula=(
                f"({open_deals} open deals / {engaged_prospects} engaged prospects) × 100 = {calc_rate(open_deals, engaged_prospects)}%"
                if engaged_prospects > 0
                else "N/A (0 verified engaged prospects to convert into pipeline opportunities)"
            ),
            denominator_name="Engaged Prospects",
        ),
        FunnelStageMetrics(
            stage_id="closed_won",
            stage_name="Closed Won",
            count=won_deals,
            conversion_rate_from_previous=calc_rate(won_deals, open_deals),
            conversion_rate_from_top=calc_rate(won_deals, top_count),
            channel_breakdown={"won_deals": won_deals},
            description="Won commercial deals and onboarded clients",
            formula=f"({won_deals} won deals / {open_deals} open deals) × 100 = {calc_rate(won_deals, open_deals)}%" if open_deals > 0 else "N/A (0 open deals to close)",
            denominator_name="Pipeline Opportunities",
        ),
    ]

    return FunnelMetrics(
        stages=stages,
        total_leads=total_leads,
        qualified_prospects=qualified_prospects,
        contacted_prospects=contacted_prospects,
        engaged_prospects=engaged_prospects,
        pipeline_opportunities=open_deals,
        closed_won=won_deals,
        contacted_records=total_outreach_activities,
        engaged_records=total_engaged_activities,
        contacted_breakdown={"emails_sent": email_sent_count, "calls_placed": voice_placed_count, "total_activities": total_outreach_activities},
        engaged_breakdown={"email_replies": email_replies_count, "connected_calls": voice_connected_count, "total_activities": total_engaged_activities},
        contacted_activities={"emails_sent": email_sent_count, "calls_placed": voice_placed_count, "total_activities": total_outreach_activities},
        engaged_activities={"email_replies": email_replies_count, "connected_calls": voice_connected_count, "total_activities": total_engaged_activities},
        meetings_requested=meetings_requested,
        confirmed_bookings=confirmed_bookings,
    )


# ── Unified Activity Stream Service ───────────────────────────────────────────

def get_unified_activities(
    db: Session,
    organization_id: uuid.UUID,
    lead_id: Optional[uuid.UUID] = None,
    contact_id: Optional[uuid.UUID] = None,
    list_id: Optional[uuid.UUID] = None,
    campaign_id: Optional[uuid.UUID] = None,
    channel: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> UnifiedActivityResponse:
    """
    Computes a truthful, unified chronological stream of verified activities (Email + Voice).
    Enforces strict tenant isolation, preserves event provenance, and never infers delivery,
    reply, or connection without reliable application data.
    """
    target_lead: Optional[Lead] = None
    target_contact: Optional[Contact] = None
    target_list: Optional[ContactList] = None

    if lead_id:
        target_lead = (
            db.query(Lead)
            .filter(Lead.id == lead_id, Lead.organization_id == organization_id)
            .first()
        )
        if not target_lead:
            return UnifiedActivityResponse(items=[], total=0, skip=skip, limit=limit)

    if contact_id:
        target_contact = (
            db.query(Contact)
            .filter(Contact.id == contact_id, Contact.organization_id == organization_id)
            .first()
        )
        if not target_contact:
            return UnifiedActivityResponse(items=[], total=0, skip=skip, limit=limit)

    member_contact_ids: List[uuid.UUID] = []
    member_lead_ids: List[uuid.UUID] = []
    member_lead_emails: List[str] = []

    if list_id:
        target_list = (
            db.query(ContactList)
            .filter(ContactList.id == list_id, ContactList.organization_id == organization_id)
            .first()
        )
        if not target_list:
            return UnifiedActivityResponse(items=[], total=0, skip=skip, limit=limit)

        members = (
            db.query(ContactListMember)
            .filter(ContactListMember.contact_list_id == list_id)
            .all()
        )
        member_contact_ids = [m.contact_id for m in members if m.contact_id]
        member_lead_ids = [m.lead_id for m in members if m.lead_id]
        if member_lead_ids:
            member_lead_emails = [
                r[0]
                for r in db.query(Lead.email)
                .filter(
                    Lead.id.in_(member_lead_ids),
                    Lead.organization_id == organization_id,
                    Lead.email.isnot(None),
                )
                .all()
            ]

    all_activities: List[UnifiedActivityItem] = []
    channel_clean = channel.strip().lower() if channel and channel.strip() else None

    # ── 1. Email Activities (Outreach) ─────────────────────────────────────────
    if channel_clean in (None, "email"):
        outreach_query = db.query(Outreach).filter(Outreach.organization_id == organization_id)

        if campaign_id:
            outreach_query = outreach_query.filter(Outreach.campaign_id == campaign_id)

        if contact_id:
            outreach_query = outreach_query.filter(Outreach.contact_id == contact_id)

        if target_lead:
            conds = []
            if target_lead.contact_id:
                conds.append(Outreach.contact_id == target_lead.contact_id)
            if target_lead.email:
                conds.append(Outreach.recipient == target_lead.email)

            call_ids = [
                r[0]
                for r in db.query(CallRecord.id)
                .filter(CallRecord.lead_id == target_lead.id, CallRecord.organization_id == organization_id)
                .all()
            ]
            if call_ids:
                conds.append(Outreach.call_record_id.in_(call_ids))

            if conds:
                outreach_query = outreach_query.filter(or_(*conds))
            else:
                outreach_query = outreach_query.filter(Outreach.id.is_(None))

        if target_list:
            conds = []
            if member_contact_ids:
                conds.append(Outreach.contact_id.in_(member_contact_ids))
            if member_lead_emails:
                conds.append(Outreach.recipient.in_(member_lead_emails))

            if conds:
                outreach_query = outreach_query.filter(or_(*conds))
            else:
                outreach_query = outreach_query.filter(Outreach.id.is_(None))

        outreach_records = outreach_query.all()
        for o in outreach_records:
            occurred = o.sent_at or o.created_at

            if o.first_replied_at:
                act_type = "email_replied"
                act_title = f"Email Replied: {o.subject or 'No subject'}"
            elif o.first_bounced_at:
                act_type = "email_bounced"
                act_title = f"Email Bounced: {o.subject or 'No subject'}"
            elif o.first_delivered_at:
                act_type = "email_delivered"
                act_title = f"Email Delivered: {o.subject or 'No subject'}"
            elif o.status == "sent":
                act_type = "email_sent"
                act_title = f"Email Sent: {o.subject or 'No subject'}"
            elif o.status == "failed":
                act_type = "email_failed"
                act_title = f"Email Failed: {o.subject or 'No subject'}"
            elif o.status == "cancelled":
                act_type = "email_cancelled"
                act_title = f"Email Cancelled: {o.subject or 'No subject'}"
            elif o.status == "scheduled":
                act_type = "email_scheduled"
                act_title = f"Email Scheduled: {o.subject or 'No subject'}"
            else:
                act_type = "email_draft"
                act_title = f"Email Draft: {o.subject or 'No subject'}"

            c_name = f"{o.contact.first_name} {o.contact.last_name}".strip() if o.contact else None
            comp_name = o.contact.company.name if (o.contact and o.contact.company) else None
            camp_name = (
                o.campaign.name
                if o.campaign
                else (f"Voice Follow-up ({o.call_record.call_id})" if o.call_record else None)
            )

            resolved_lead_id = target_lead.id if target_lead else None
            if not resolved_lead_id and o.contact_id:
                matched_lead = (
                    db.query(Lead.id)
                    .filter(Lead.contact_id == o.contact_id, Lead.organization_id == organization_id)
                    .first()
                )
                if matched_lead:
                    resolved_lead_id = matched_lead[0]
            if not resolved_lead_id and o.recipient:
                matched_lead = (
                    db.query(Lead.id)
                    .filter(Lead.email == o.recipient, Lead.organization_id == organization_id)
                    .first()
                )
                if matched_lead:
                    resolved_lead_id = matched_lead[0]

            preview = (
                o.body[:200] + ("..." if len(o.body) > 200 else "")
                if o.body
                else None
            )

            all_activities.append(
                UnifiedActivityItem(
                    id=str(o.id),
                    channel="email",
                    activity_type=act_type,
                    title=act_title,
                    description=preview,
                    occurred_at=occurred,
                    lead_id=resolved_lead_id,
                    contact_id=o.contact_id,
                    campaign_id=o.campaign_id,
                    campaign_name=camp_name,
                    contact_name=c_name,
                    company_name=comp_name,
                    email_details=EmailActivityDetails(
                        status=o.status,
                        subject=o.subject,
                        body_preview=preview,
                        provider=o.provider,
                        sent_at=o.sent_at,
                        delivered_at=o.first_delivered_at,
                        opened_at=o.first_opened_at,
                        clicked_at=o.first_clicked_at,
                        replied_at=o.first_replied_at,
                        bounced_at=o.first_bounced_at,
                        is_delivered=bool(o.first_delivered_at),
                        is_replied=bool(o.first_replied_at),
                        is_bounced=bool(o.first_bounced_at),
                    ),
                    provenance={
                        "source_model": "outreach",
                        "record_id": str(o.id),
                        "provider": o.provider,
                        "provider_message_id": o.provider_message_id,
                        "delivery_verified": bool(o.first_delivered_at),
                        "reply_verified": bool(o.first_replied_at),
                        "bounced_verified": bool(o.first_bounced_at),
                    },
                )
            )

    # ── 2. Voice Activities (CallRecord) ───────────────────────────────────────
    if channel_clean in (None, "voice"):
        call_query = db.query(CallRecord).filter(CallRecord.organization_id == organization_id)

        if campaign_id:
            call_query = call_query.filter(CallRecord.campaign_id == campaign_id)

        if contact_id:
            call_query = call_query.filter(CallRecord.contact_id == contact_id)

        if target_lead:
            call_conds = [CallRecord.lead_id == target_lead.id]
            if target_lead.contact_id:
                call_conds.append(CallRecord.contact_id == target_lead.contact_id)
            call_query = call_query.filter(or_(*call_conds))

        if target_list:
            call_conds = []
            if member_contact_ids:
                call_conds.append(CallRecord.contact_id.in_(member_contact_ids))
            if member_lead_ids:
                call_conds.append(CallRecord.lead_id.in_(member_lead_ids))

            if call_conds:
                call_query = call_query.filter(or_(*call_conds))
            else:
                call_query = call_query.filter(CallRecord.id.is_(None))

        call_records = call_query.all()
        for c in call_records:
            occurred = c.started_at or c.created_at
            dur_sec = round(c.duration_ms / 1000) if c.duration_ms is not None else 0
            is_connected = bool(
                c.duration_ms
                and c.duration_ms > 0
                and (c.disconnection_reason or "") not in ("dial_busy", "dial_failed", "dial_no_answer")
            )

            if c.call_outcome == "MEETING_REQUESTED":
                act_type = "voice_call_meeting_requested"
            elif c.call_outcome == "QUALIFIED":
                act_type = "voice_call_qualified"
            elif c.call_outcome == "INTERESTED":
                act_type = "voice_call_interested"
            elif is_connected:
                act_type = "voice_call_connected"
            else:
                act_type = "voice_call_initiated"

            direction_label = (c.direction or "inbound").capitalize()
            dur_label = f" ({dur_sec}s)" if dur_sec > 0 else ""
            outcome_label = f" — {c.call_outcome.replace('_', ' ').title()}" if c.call_outcome else ""
            act_title = f"{direction_label} Voice Call{dur_label}{outcome_label}"

            c_name = None
            comp_name = None
            if c.contact:
                c_name = f"{c.contact.first_name} {c.contact.last_name}".strip()
                if c.contact.company:
                    comp_name = c.contact.company.name
            elif c.lead:
                c_name = f"{c.lead.first_name or ''} {c.lead.last_name or ''}".strip() or None
                comp_name = c.lead.company_name

            camp_name = c.campaign.name if c.campaign else None
            summary_desc = (
                c.summary
                or (c.transcript[:200] + "..." if c.transcript else None)
                or c.disconnection_reason
            )

            all_activities.append(
                UnifiedActivityItem(
                    id=str(c.id),
                    channel="voice",
                    activity_type=act_type,
                    title=act_title,
                    description=summary_desc,
                    occurred_at=occurred,
                    lead_id=c.lead_id,
                    contact_id=c.contact_id,
                    campaign_id=c.campaign_id,
                    campaign_name=camp_name,
                    contact_name=c_name,
                    company_name=comp_name,
                    voice_details=VoiceActivityDetails(
                        call_id=c.call_id,
                        direction=c.direction or "inbound",
                        call_status=c.call_status,
                        call_outcome=c.call_outcome,
                        duration_seconds=dur_sec,
                        caller_phone=c.caller_phone,
                        to_phone=c.to_phone,
                        is_connected=is_connected,
                        disconnection_reason=c.disconnection_reason,
                        summary=c.summary,
                        transcript_snippet=c.transcript[:300] if c.transcript else None,
                    ),
                    provenance={
                        "source_model": "call_records",
                        "record_id": str(c.id),
                        "call_id": c.call_id,
                        "agent_id": c.agent_id,
                        "connected_verified": is_connected,
                        "has_summary": bool(c.summary),
                        "has_transcript": bool(c.transcript),
                    },
                )
            )

    # ── 3. Sort Chronologically (Newest First) & Paginate ──────────────────────
    all_activities.sort(key=lambda a: a.occurred_at, reverse=True)
    total_count = len(all_activities)
    paginated = all_activities[skip : skip + limit]

    return UnifiedActivityResponse(
        items=paginated,
        total=total_count,
        skip=skip,
        limit=limit,
    )

