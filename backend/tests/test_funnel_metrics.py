"""Tests for Funnel Metrics Calculation & Analytics Overview (Stage C & D)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, get_db
from app.main import app
from app.models.call_record import CallRecord
from app.models.crm import Contact, Deal, Pipeline, PipelineStage
from app.models.lead import Lead
from app.models.outreach import Outreach
from app.models.tenant import Organization, User
from app.services.analytics_service import (
    calculate_funnel_metrics,
    get_analytics_overview,
    get_positive_prospect_responses,
)
from app.services.lead_generation.service import convert_lead_to_crm


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session for funnel metrics tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)


def _create_test_org(session, name: str = "Test Org") -> Organization:
    org = Organization(id=uuid.uuid4(), name=name, slug=f"slug-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def test_empty_funnel_metrics_returns_neutral_zeros(db_session):
    """Empty organization returns factual zeros with neutral None conversion rates (rendered as N/A)."""
    org = _create_test_org(db_session, "Empty Org")

    funnel = calculate_funnel_metrics(db_session, org.id)

    assert funnel.total_leads == 0
    assert funnel.qualified_prospects == 0
    assert funnel.contacted_records == 0
    assert funnel.engaged_records == 0
    assert funnel.pipeline_opportunities == 0
    assert funnel.closed_won == 0
    assert len(funnel.stages) == 6

    for stage in funnel.stages:
        assert stage.count == 0
        # When denominator is 0, conversion rates must return None (rendered as N/A)
        assert stage.conversion_rate_from_previous is None
        assert stage.conversion_rate_from_top is None


def test_funnel_metrics_tenant_isolation(db_session):
    """Verifies that Org A metrics never leak into Org B."""
    org_a = _create_test_org(db_session, "Org A")
    org_b = _create_test_org(db_session, "Org B")

    lead_a = Lead(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        company_name="Alpha Corp",
        qualification_status="qualified",
    )
    db_session.add(lead_a)
    db_session.commit()

    funnel_a = calculate_funnel_metrics(db_session, org_a.id)
    funnel_b = calculate_funnel_metrics(db_session, org_b.id)

    assert funnel_a.total_leads == 1
    assert funnel_a.qualified_prospects == 1
    assert funnel_b.total_leads == 0
    assert funnel_b.qualified_prospects == 0


def test_no_double_counting_between_lead_and_contact(db_session):
    """
    Verifies that a qualified Contact linked to an already qualified Lead
    is not counted twice in qualified_prospects.
    """
    org = _create_test_org(db_session, "Deduplication Org")

    contact_linked = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        lead_status="qualified",
    )
    db_session.add(contact_linked)
    db_session.flush()

    lead_qualified = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_name="Acme Inc",
        contact_id=contact_linked.id,
        qualification_status="qualified",
    )
    db_session.add(lead_qualified)

    # Independent qualified contact not linked to any Lead
    contact_independent = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Bob",
        last_name="Smith",
        email="bob@example.com",
        lead_status="qualified",
    )
    db_session.add(contact_independent)
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    # Total leads is 1
    assert funnel.total_leads == 1
    # Qualified prospects should be 1 (lead) + 1 (independent contact) = 2, NOT 3
    assert funnel.qualified_prospects == 2
    stage = next(s for s in funnel.stages if s.stage_id == "qualified_prospects")
    assert stage.channel_breakdown["lead_qualified"] == 1
    assert stage.channel_breakdown["contact_qualified"] == 1


def test_full_funnel_progression_and_conversion_rates(db_session):
    """
    Verifies progression across all 6 stages:
    Total Leads -> Qualified Prospects -> Contacted -> Engaged -> Opportunities -> Closed Won.
    """
    org = _create_test_org(db_session, "Funnel Progression Org")
    now = datetime.now(timezone.utc)

    # 1. Four leads total, two qualified (linked to real contacts)
    contact1 = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Alice",
        last_name="Lead",
        email="lead1@example.com",
    )
    contact2 = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Bob",
        last_name="Lead",
        email="lead2@example.com",
    )
    db_session.add_all([contact1, contact2])
    db_session.flush()

    lead1 = Lead(id=uuid.uuid4(), organization_id=org.id, contact_id=contact1.id, company_name="C1", qualification_status="qualified")
    lead2 = Lead(id=uuid.uuid4(), organization_id=org.id, contact_id=contact2.id, company_name="C2", qualification_status="qualified")
    lead3 = Lead(id=uuid.uuid4(), organization_id=org.id, company_name="C3", qualification_status="new")
    lead4 = Lead(id=uuid.uuid4(), organization_id=org.id, company_name="C4", qualification_status="disqualified")
    db_session.add_all([lead1, lead2, lead3, lead4])
    db_session.commit()

    # 2. Contacted: 1 sent email outreach to contact1, 1 placed voice call to contact2
    outreach_sent = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact1.id,
        recipient="lead1@example.com",
        channel="email",
        status="sent",
        sent_at=now,
        first_replied_at=now,  # Also replied -> Engaged
    )
    call_connected = CallRecord(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact2.id,
        call_id="call-funnel-1",
        agent_id="agent-1",
        direction="outbound",
        call_status="ended",
        call_outcome="MEETING_REQUESTED",
        duration_ms=45000,  # Connected (>0) -> Engaged
    )
    db_session.add_all([outreach_sent, call_connected])
    db_session.commit()

    # 3. Deals: Pipeline with stage, 1 open deal ($10,000), 1 won deal ($5,000)
    pipeline = Pipeline(id=uuid.uuid4(), organization_id=org.id, name="Sales Pipeline", is_default=True)
    db_session.add(pipeline)
    db_session.flush()

    stage_disc = PipelineStage(id=uuid.uuid4(), pipeline_id=pipeline.id, name="Discovery", order_index=1, probability_pct=20)
    stage_won = PipelineStage(id=uuid.uuid4(), pipeline_id=pipeline.id, name="Won", order_index=2, probability_pct=100)
    db_session.add_all([stage_disc, stage_won])
    db_session.flush()

    deal_open = Deal(
        id=uuid.uuid4(),
        organization_id=org.id,
        pipeline_stage_id=stage_disc.id,
        name="Big Enterprise Deal",
        amount=Decimal("10000.00"),
        status="open",
    )
    deal_won = Deal(
        id=uuid.uuid4(),
        organization_id=org.id,
        pipeline_stage_id=stage_won.id,
        name="Closed Pilot Deal",
        amount=Decimal("5000.00"),
        status="won",
    )
    db_session.add_all([deal_open, deal_won])
    db_session.commit()

    overview = get_analytics_overview(db_session, org.id)
    assert overview.funnel is not None
    funnel = overview.funnel

    assert funnel.total_leads == 4
    assert funnel.qualified_prospects == 2
    assert funnel.contacted_records == 2
    assert funnel.engaged_records == 2
    assert funnel.pipeline_opportunities == 1
    assert funnel.closed_won == 1

    # Check stage conversion rates:
    # Stage 0: Total Leads (4) -> from top: 100%
    assert funnel.stages[0].count == 4
    assert funnel.stages[0].conversion_rate_from_previous == 100.0

    # Stage 1: Qualified (2) -> 2/4 = 50.0%
    assert funnel.stages[1].count == 2
    assert funnel.stages[1].conversion_rate_from_previous == 50.0
    assert funnel.stages[1].conversion_rate_from_top == 50.0

    # Stage 2: Contacted (2) -> 2/2 = 100.0%
    assert funnel.stages[2].count == 2
    assert funnel.stages[2].conversion_rate_from_previous == 100.0

    # Stage 3: Engaged: 1 verified prospect engaged via email reply
    # (voice call engagement is unverified due to lack of environment/test tracking in CallRecord)
    assert funnel.stages[3].count == 1
    assert funnel.stages[3].conversion_rate_from_previous == 50.0
    assert funnel.stages[3].conversion_rate_from_top == 25.0

    # Stage 4: Opportunities (1) -> 1/1 = 100.0% (1 open deal converted from 1 verified engaged prospect)
    assert funnel.stages[4].count == 1
    assert funnel.stages[4].conversion_rate_from_previous == 100.0
    assert funnel.stages[4].conversion_rate_from_top == 25.0

    # Stage 5: Closed Won (1) -> 1/1 = 100.0%
    assert funnel.stages[5].count == 1
    assert funnel.stages[5].conversion_rate_from_previous == 100.0

    # Invariant: Pipeline value distinction
    assert overview.pipeline.total_pipeline_value == 10000.0
    assert overview.pipeline.won_pipeline_value == 5000.0


def test_positive_prospect_responses_and_deal_value_workflow(db_session):
    """
    Validates Kunal's positive response & deal value workflow:
    1. Positive response surfaced (call with MEETING_REQUESTED, email reply, qualified lead).
    2. Before deal creation, deal_id is None, prompting user to enter estimated deal value.
    3. User creates deal with subjective estimated value -> links to response and adds to open pipeline value.
    4. Distinguishes open pipeline value ($) from closed-won revenue ($) and lost deals ($0).
    5. Preserves numerical counts vs dollar values.
    6. Preserves tenant isolation.
    """
    org_a = _create_test_org(db_session, "Org A - Real Estate")
    org_b = _create_test_org(db_session, "Org B - Other")

    pipe_a = Pipeline(id=uuid.uuid4(), organization_id=org_a.id, name="Sales Pipeline", is_default=True)
    stage_a = PipelineStage(id=uuid.uuid4(), pipeline_id=pipe_a.id, name="Discovery", order_index=0)
    db_session.add_all([pipe_a, stage_a])

    # Contact in Org A
    contact_a = Contact(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@acme.com",
        phone="+15551234567",
    )
    db_session.add(contact_a)
    db_session.commit()

    # Positive call response: MEETING_REQUESTED
    call_record = CallRecord(
        id=uuid.uuid4(),
        call_id=f"call_{uuid.uuid4().hex[:12]}",
        agent_id="agent_test_123",
        organization_id=org_a.id,
        contact_id=contact_a.id,
        call_status="ended",
        call_outcome="MEETING_REQUESTED",
        summary="Jane agreed to a demo next Tuesday.",
        duration_ms=125000,
    )
    db_session.add(call_record)
    db_session.commit()

    # Step 1: Query overview before deal creation
    overview_before = get_analytics_overview(db_session, org_a.id)
    assert len(overview_before.positive_responses) >= 1
    pos_resp = next(r for r in overview_before.positive_responses if r.contact_id == contact_a.id)
    assert pos_resp.channel == "voice"
    assert pos_resp.response_type == "meeting_requested"
    assert pos_resp.contact_name == "Jane Doe"
    # Action Needed: Deal not yet created
    assert pos_resp.deal_id is None
    assert pos_resp.deal_amount is None
    # Pipeline value is currently 0
    assert overview_before.pipeline.total_pipeline_value == 0.0
    assert overview_before.pipeline.open_deals == 0

    # Step 2: Customer enters estimated deal value ($5,000) for this opportunity
    deal_a = Deal(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        pipeline_stage_id=stage_a.id,
        contact_id=contact_a.id,
        name="Acme Corp - Jane Doe Opportunity",
        amount=Decimal("5000.00"),
        status="open",
    )
    db_session.add(deal_a)
    db_session.commit()

    overview_after = get_analytics_overview(db_session, org_a.id)
    pos_resp_after = next(r for r in overview_after.positive_responses if r.contact_id == contact_a.id)
    assert pos_resp_after.deal_id == deal_a.id
    assert pos_resp_after.deal_amount == 5000.0
    assert pos_resp_after.deal_status == "open"

    # Invariants:
    # 1. Numerical deal count is 1, open pipeline value is $5,000
    assert overview_after.pipeline.open_deals == 1
    assert overview_after.pipeline.total_pipeline_value == 5000.0
    assert overview_after.pipeline.won_deals == 0
    assert overview_after.pipeline.won_pipeline_value == 0.0

    # Step 3: Deal moves to WON (closed contract)
    deal_a.status = "won"
    db_session.commit()

    overview_won = get_analytics_overview(db_session, org_a.id)
    assert overview_won.pipeline.open_deals == 0
    assert overview_won.pipeline.total_pipeline_value == 0.0
    assert overview_won.pipeline.won_deals == 1
    assert overview_won.pipeline.won_pipeline_value == 5000.0

    # Tenant isolation check: Org B must see 0 positive responses and 0 deals
    overview_b = get_analytics_overview(db_session, org_b.id)
    assert len(overview_b.positive_responses) == 0
    assert overview_b.pipeline.total_deals == 0
    assert overview_b.pipeline.total_pipeline_value == 0.0


def test_positive_response_email_and_lost_deal_handling(db_session):
    """
    Validates email replies and lost deal handling:
    1. Email reply records surface as positive responses.
    2. Lost deals have status 'lost' and are excluded from open pipeline value and won revenue.
    3. Numerical conversion counts (e.g. 1 lost deal, 1 lead) remain distinct from dollar values ($0).
    """
    org = _create_test_org(db_session, "Org C - Outreach")

    pipe = Pipeline(id=uuid.uuid4(), organization_id=org.id, name="Sales Pipeline", is_default=True)
    stage = PipelineStage(id=uuid.uuid4(), pipeline_id=pipe.id, name="Initial Contact", order_index=0)
    db_session.add_all([pipe, stage])

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Bob",
        last_name="Smith",
        email="bob@smithcorp.com",
    )
    db_session.add(contact)
    db_session.commit()

    now = datetime.now(timezone.utc)
    outreach = Outreach(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        channel="email",
        status="sent",
        recipient=contact.email,
        subject="Re: Partnership Proposal",
        sent_at=now,
        first_replied_at=now,
    )
    db_session.add(outreach)
    db_session.commit()

    overview = get_analytics_overview(db_session, org.id)
    assert len(overview.positive_responses) == 1
    resp = overview.positive_responses[0]
    assert resp.channel == "email"
    assert resp.response_type == "email_replied"
    assert resp.contact_name == "Bob Smith"
    assert resp.deal_id is None

    # Now create a deal marked as 'lost'
    deal_lost = Deal(
        id=uuid.uuid4(),
        organization_id=org.id,
        pipeline_stage_id=stage.id,
        contact_id=contact.id,
        name="Bob Smith - Lost Deal",
        amount=Decimal("3000.00"),
        status="lost",
    )
    db_session.add(deal_lost)
    db_session.commit()

    overview_lost = get_analytics_overview(db_session, org.id)
    # Numerical counts: 1 lost deal, 0 open, 0 won
    assert overview_lost.pipeline.total_deals == 1
    assert overview_lost.pipeline.open_deals == 0
    assert overview_lost.pipeline.won_deals == 0
    assert overview_lost.pipeline.lost_deals == 1
    # Dollar values: $0 open pipeline value, $0 won revenue (lost amount is excluded from both)
    assert overview_lost.pipeline.total_pipeline_value == 0.0
    assert overview_lost.pipeline.won_pipeline_value == 0.0


def test_funnel_duplicate_outreach_to_same_prospect(db_session):
    """
    Verifies that multiple emails or calls to the same contact count as 1 contacted prospect,
    while activity breakdown correctly retains total email and call counts.
    """
    org = _create_test_org(db_session, "Duplicate Outreach Org")
    now = datetime.now(timezone.utc)

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Diana",
        last_name="Prince",
        email="diana@themyscira.com",
    )
    db_session.add(contact)
    db_session.commit()

    # 3 emails to Diana
    for i in range(3):
        db_session.add(
            Outreach(
                id=uuid.uuid4(),
                organization_id=org.id,
                contact_id=contact.id,
                channel="email",
                status="sent",
                recipient=contact.email,
                sent_at=now,
            )
        )
    # 2 voice calls to Diana
    for i in range(2):
        db_session.add(
            CallRecord(
                id=uuid.uuid4(),
                call_id=f"call-diana-{i}",
                agent_id="agent-retell",
                organization_id=org.id,
                contact_id=contact.id,
                call_status="ended",
                duration_ms=25000,
            )
        )
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    # Distinct prospect count must be 1, NOT 5!
    assert funnel.contacted_prospects == 1
    # Activity counts must retain all 5 activities (3 emails + 2 calls)
    assert funnel.contacted_records == 5
    assert funnel.contacted_activities["emails_sent"] == 3
    assert funnel.contacted_activities["calls_placed"] == 2
    assert funnel.contacted_activities["total_activities"] == 5

    contacted_stage = next(s for s in funnel.stages if s.stage_id == "contacted")
    assert contacted_stage.count == 1
    assert contacted_stage.channel_breakdown["distinct_prospects"] == 1
    assert contacted_stage.channel_breakdown["total_activities"] == 5


def test_funnel_non_nested_outreach_spans_broader_leads(db_session):
    """
    Verifies that outreach spanning the broader lead pool (contacted > qualified)
    does not produce nonsensical >100% conversion rates (e.g. eliminating the 500% bug).
    The compatible denominator (Total Leads) is used and transparently documented in the formula.
    """
    org = _create_test_org(db_session, "Broader Outreach Org")
    now = datetime.now(timezone.utc)

    # 10 leads total, only 2 marked qualified
    contacts = []
    for i in range(10):
        c = Contact(
            id=uuid.uuid4(),
            organization_id=org.id,
            first_name=f"Lead{i}",
            last_name="Test",
            email=f"lead{i}@example.com",
        )
        contacts.append(c)
        db_session.add(c)
    db_session.flush()

    for i in range(10):
        db_session.add(
            Lead(
                id=uuid.uuid4(),
                organization_id=org.id,
                contact_id=contacts[i].id,
                company_name=f"Company {i}",
                qualification_status="qualified" if i < 2 else "new",
            )
        )
    db_session.commit()

    # Outreach dispatched to 6 distinct contacts (more than the 2 qualified prospects)
    for i in range(6):
        db_session.add(
            Outreach(
                id=uuid.uuid4(),
                organization_id=org.id,
                contact_id=contacts[i].id,
                channel="email",
                status="sent",
                recipient=contacts[i].email,
                sent_at=now,
            )
        )
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    assert funnel.total_leads == 10
    assert funnel.qualified_prospects == 2
    assert funnel.contacted_prospects == 6

    contacted_stage = next(s for s in funnel.stages if s.stage_id == "contacted")
    # Instead of (6 / 2) * 100 = 300% or 500%, uses compatible denominator Total Leads:
    # (6 / 10) * 100 = 60.0%
    assert contacted_stage.conversion_rate_from_previous == 60.0
    assert contacted_stage.denominator_name == "Total Leads"
    assert "broader lead database" in contacted_stage.formula
    assert "6 contacted prospects / 10 total leads" in contacted_stage.formula


def test_funnel_zero_denominator_returns_none_or_na(db_session):
    """
    Verifies that when a denominator is 0 (e.g., Closed Won when Opportunities = 0),
    the conversion rate returns None (rendered as N/A in UI) instead of 0% or an exception.
    """
    org = _create_test_org(db_session, "Zero Denom Org")

    # 1 Lead, 0 qualified, 0 contacted, 0 engaged, 0 open deals, 0 won deals
    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_name="Lone Wolf Inc",
        qualification_status="new",
    )
    db_session.add(lead)
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    assert funnel.total_leads == 1
    assert funnel.qualified_prospects == 0
    assert funnel.contacted_prospects == 0
    assert funnel.engaged_prospects == 0
    assert funnel.pipeline_opportunities == 0
    assert funnel.closed_won == 0

    opps_stage = next(s for s in funnel.stages if s.stage_id == "opportunities")
    closed_won_stage = next(s for s in funnel.stages if s.stage_id == "closed_won")

    # When engaged_prospects = 0, opportunities conversion_rate_from_previous must be None (N/A)
    assert opps_stage.conversion_rate_from_previous is None
    assert "N/A" in opps_stage.formula

    # When open_deals = 0, closed_won conversion_rate_from_previous must be None (N/A)
    assert closed_won_stage.conversion_rate_from_previous is None
    assert "N/A" in closed_won_stage.formula


def test_funnel_meetings_requested_vs_confirmed_bookings(db_session):
    """
    Verifies that meeting requests (prospect high intent) and confirmed calendar bookings
    are counted accurately and strictly distinguished from general call outcomes like INTERESTED.
    """
    org = _create_test_org(db_session, "Meetings Org")

    # Call 1: Prospect requested a meeting during the call
    call_req = CallRecord(
        id=uuid.uuid4(),
        call_id="call-meeting-req-1",
        agent_id="agent-1",
        organization_id=org.id,
        call_status="ended",
        call_outcome="MEETING_REQUESTED",
        duration_ms=65000,
    )
    # Call 2: Confirmed calendar booking
    call_confirmed = CallRecord(
        id=uuid.uuid4(),
        call_id="call-booking-conf-1",
        agent_id="agent-1",
        organization_id=org.id,
        call_status="ended",
        call_outcome="meeting_scheduled",
        duration_ms=90000,
    )
    # Call 3: General positive interest - NOT a meeting request or confirmed booking
    call_interested = CallRecord(
        id=uuid.uuid4(),
        call_id="call-interested-1",
        agent_id="agent-1",
        organization_id=org.id,
        call_status="ended",
        call_outcome="INTERESTED",
        duration_ms=40000,
    )
    db_session.add_all([call_req, call_confirmed, call_interested])
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    # call_req and call_confirmed both contain 'meeting' in outcome
    assert funnel.meetings_requested == 2
    # only call_confirmed has 'meeting_scheduled'
    assert funnel.confirmed_bookings == 1


def test_funnel_engagement_semantics_distinguishes_connection_from_outcome(db_session):
    """
    Verifies that call connections, expressed interest, qualification, meeting requests,
    and confirmed calendar bookings are treated as distinct semantic outcomes and not conflated.
    """
    org = _create_test_org(db_session, "Engagement Semantics Org")
    now = datetime.now(timezone.utc)

    # 5 Contacts
    contacts = [
        Contact(id=uuid.uuid4(), organization_id=org.id, first_name=f"Contact{i}", last_name="Test", email=f"c{i}@example.com")
        for i in range(5)
    ]
    db_session.add_all(contacts)
    db_session.commit()

    # 1. Connected, but not interested (hung up after 15s)
    c1 = CallRecord(
        id=uuid.uuid4(),
        call_id="call-not-interested",
        agent_id="agent-1",
        organization_id=org.id,
        contact_id=contacts[0].id,
        call_status="ended",
        call_outcome="NOT_INTERESTED",
        duration_ms=15000,
    )
    # 2. Connected and expressed general interest
    c2 = CallRecord(
        id=uuid.uuid4(),
        call_id="call-interested",
        agent_id="agent-1",
        organization_id=org.id,
        contact_id=contacts[1].id,
        call_status="ended",
        call_outcome="INTERESTED",
        duration_ms=45000,
    )
    # 3. Connected and qualified against ICP criteria
    c3 = CallRecord(
        id=uuid.uuid4(),
        call_id="call-qualified",
        agent_id="agent-1",
        organization_id=org.id,
        contact_id=contacts[2].id,
        call_status="ended",
        call_outcome="QUALIFIED",
        duration_ms=60000,
    )
    # 4. Connected and explicitly requested a demo meeting
    c4 = CallRecord(
        id=uuid.uuid4(),
        call_id="call-meeting-req",
        agent_id="agent-1",
        organization_id=org.id,
        contact_id=contacts[3].id,
        call_status="ended",
        call_outcome="MEETING_REQUESTED",
        duration_ms=75000,
    )
    # 5. Connected and calendar booking confirmed
    c5 = CallRecord(
        id=uuid.uuid4(),
        call_id="call-booking-conf",
        agent_id="agent-1",
        organization_id=org.id,
        contact_id=contacts[4].id,
        call_status="ended",
        call_outcome="meeting_scheduled",
        duration_ms=90000,
    )
    db_session.add_all([c1, c2, c3, c4, c5])
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    # 1. All 5 had connected calls with duration > 0 -> counted as contacted prospects and engaged activities
    assert funnel.contacted_prospects == 5
    assert funnel.engaged_activities["connected_calls"] == 5
    # Commercial engagement strictly requires verified commercial replies (email replies);
    # voice call engagement is unverified due to lack of environment/test tracking in CallRecord schema
    assert funnel.engaged_prospects == 0
    assert funnel.stages[3].count == 0
    assert funnel.stages[3].conversion_rate_from_previous is None
    assert "Voice call engagement is unverified" in funnel.stages[3].description

    # 2. Strict distinction: A connected call alone does NOT automatically make a prospect qualified!
    assert funnel.qualified_prospects == 0

    # 3. Meetings requested vs confirmed bookings are strictly distinguished:
    assert funnel.meetings_requested == 2  # c4 (MEETING_REQUESTED) + c5 (meeting_scheduled)
    assert funnel.confirmed_bookings == 1  # strictly c5 (meeting_scheduled)

    # 4. Positive responses: NOT_INTERESTED must NEVER be treated as a positive response
    pos_responses = get_positive_prospect_responses(db_session, org.id)
    pos_ids = [r.id for r in pos_responses]
    assert f"call_{c1.id}" not in pos_ids  # NOT_INTERESTED must be excluded!
    assert f"call_{c2.id}" in pos_ids      # INTERESTED is included
    assert f"call_{c3.id}" in pos_ids      # QUALIFIED is included
    assert f"call_{c4.id}" in pos_ids      # MEETING_REQUESTED is included
    assert f"call_{c5.id}" in pos_ids      # meeting_scheduled is included


def test_lead_conversion_does_not_auto_qualify(db_session):
    """
    Verifies that converting an unqualified Lead (status='new') to CRM Contact
    does not automatically grant it 'qualified' status, leaving it 'new'.
    """
    org = _create_test_org(db_session, "Conversion Qualification Org")

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_name="Unqualified Corp",
        first_name="Sam",
        last_name="Tester",
        email="sam.tester@unqualified.com",
        qualification_status="new",
    )
    db_session.add(lead)
    db_session.commit()

    # Convert to CRM Contact
    resp = convert_lead_to_crm(db=db_session, current_org=org, lead_id=lead.id)
    assert resp.status == "converted"
    assert resp.contact_id is not None

    contact = db_session.query(Contact).filter(Contact.id == resp.contact_id).first()
    assert contact is not None
    # Must NOT be qualified merely because it was converted!
    assert contact.lead_status == "new"

    # Funnel must not count it as qualified
    funnel = calculate_funnel_metrics(db_session, org.id)
    assert funnel.total_leads == 1
    assert funnel.qualified_prospects == 0


def test_lead_conversion_preserves_supported_qualification(db_session):
    """
    Verifies that converting a genuinely qualified Lead (qualification_status='qualified')
    preserves its qualified status on the resulting CRM Contact and in the funnel.
    """
    org = _create_test_org(db_session, "Supported Qualification Org")

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_name="Genuinely Qualified Corp",
        first_name="Dana",
        last_name="Leader",
        email="dana@qualified.com",
        qualification_status="qualified",
    )
    db_session.add(lead)
    db_session.commit()

    resp = convert_lead_to_crm(db=db_session, current_org=org, lead_id=lead.id)
    assert resp.status == "converted"

    contact = db_session.query(Contact).filter(Contact.id == resp.contact_id).first()
    assert contact is not None
    assert contact.lead_status == "qualified"

    funnel = calculate_funnel_metrics(db_session, org.id)
    assert funnel.total_leads == 1
    # Lead is qualified; linked contact does not double-count
    assert funnel.qualified_prospects == 1


def test_invalid_qualification_status_on_converted_contact_ignored(db_session):
    """
    Verifies that legacy records where a Contact was marked 'qualified' by previous bugs
    while its linked Lead is 'new' (unqualified) are NOT presented as verified qualified prospects.
    """
    org = _create_test_org(db_session, "Legacy Anomaly Org")

    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Legacy",
        last_name="Bug",
        email="legacy.bug@example.com",
        lead_status="qualified",  # Invalid legacy status stamped by old code
    )
    db_session.add(contact)
    db_session.flush()

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        contact_id=contact.id,
        company_name="Legacy Inc",
        qualification_status="new",  # The lead was never qualified!
    )
    db_session.add(lead)
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)
    assert funnel.total_leads == 1
    # Because the linked lead was never qualified, the invalid contact status must be ignored!
    assert funnel.qualified_prospects == 0


def test_retell_test_artifact_lead_excluded_from_funnel(db_session):
    """
    Verifies that synthetic Retell voice call test artifacts (source='retell_voice_call')
    are excluded from verified qualification metrics, matching project's exclude_test conventions.
    """
    org = _create_test_org(db_session, "Artifact Exclusion Org")

    test_artifact_lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_name="Test Company",
        first_name="Test",
        last_name="Prospect",
        email="test@example.com",
        source="retell_voice_call",
        qualification_status="qualified",
    )
    db_session.add(test_artifact_lead)
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)
    # The synthetic test artifact must not be counted as a verified qualified prospect
    assert funnel.qualified_prospects == 0


def test_truthful_engagement_metrics_without_schema_metadata(db_session):
    """
    Focused test verifying truthful engagement metrics when CallRecord lacks schema metadata:
    1. Connected voice calls (duration_ms > 0) are tracked as contacted prospects and under engaged_activities['connected_calls'].
    2. Because CallRecord has no dedicated is_test/environment column, voice calls cannot be verified
       as commercial prospect engagements without inventing heuristics.
    3. Commercial prospect engagement is strictly determined by verified commercial replies (email replies).
    4. When there are no verified email replies, engaged_prospects reports 0, conversion rate is None,
       and the funnel description clearly explains the limitation.
    5. Positive responses (meetings, qualified outcomes) remain preserved and separate.
    """
    org = _create_test_org(db_session, "Truthful Engagement Org")
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        first_name="Alex",
        last_name="Prospect",
        email="alex@example.com",
    )
    db_session.add(contact)
    db_session.commit()

    # Replayed/development call with duration 45000ms and INTERESTED outcome
    call = CallRecord(
        id=uuid.uuid4(),
        call_id="call-test-replay-45s",
        agent_id="agent-1",
        organization_id=org.id,
        contact_id=contact.id,
        call_status="analyzed",
        call_outcome="INTERESTED",
        duration_ms=45000,
    )
    db_session.add(call)
    db_session.commit()

    funnel = calculate_funnel_metrics(db_session, org.id)

    # Contacted prospects is 1
    assert funnel.contacted_prospects == 1
    # Engaged activity counts preserve the connection
    assert funnel.engaged_activities["connected_calls"] == 1
    # Commercial engaged prospects reports 0 (no verified commercial replies)
    assert funnel.engaged_prospects == 0
    # Engaged stage metrics reflect honest unavailable/unverified state
    engaged_stage = next(s for s in funnel.stages if s.stage_id == "engaged")
    assert engaged_stage.count == 0
    assert engaged_stage.conversion_rate_from_previous is None
    assert engaged_stage.conversion_rate_from_top is None
    assert "Voice call engagement is unverified" in engaged_stage.description
    assert "voice call engagement is unverified" in engaged_stage.formula

    # Positive responses still surface the outcome separately
    pos_responses = get_positive_prospect_responses(db_session, org.id)
    assert len(pos_responses) == 1
    assert pos_responses[0].id == f"call_{call.id}"
    assert pos_responses[0].response_type == "qualified_call"





