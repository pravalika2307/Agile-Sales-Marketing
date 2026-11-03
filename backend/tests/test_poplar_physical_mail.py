"""Comprehensive test suite for Poplar Direct Mail integration.

Validates:
1. Domestic US postal address validation (USPS rules, 2-letter state codes, 5-digit & 9-digit ZIPs).
2. Invalid postal addresses (missing street, bad state, invalid ZIP, non-US country, missing addressee).
3. Test versus Production configuration and credential isolation (refusal to silently fall back).
4. Fail-closed safety (POPLAR_ALLOW_LIVE_SENDING=False enforces mock simulation).
5. Poplar API client request schema and response parsing (POST /v1/mailing, GET /v1/mailing/:id).
6. Safe timeouts, rate limits (429), auth failures (401), and sanitized error messages.
7. Pre-flight campaign recipient address validation and invalid recipient categorization.
8. Cost calculation ($1.15 per valid recipient) and merge tag preview.
9. Explicit approval requirement before submission (approved=True guard).
10. Duplicate-submission prevention (idempotency key protection).
11. Partial failure resilience (one bad recipient does not abort the entire batch).
12. Safe retry for failed mailings without redialing successful ones.
13. Strict multi-tenant isolation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization, User
from app.services.physical_mail.address_validator import (
    AddressValidationResult,
    validate_usps_address,
)
from app.services.physical_mail.poplar_client import (
    PoplarAPIError,
    PoplarAuthenticationError,
    PoplarClient,
    PoplarConfigurationError,
    PoplarNotFoundError,
    PoplarPermissionError,
    PoplarRateLimitError,
    PoplarRecipient,
    PoplarTimeoutError,
    PoplarValidationError,
)
from app.services.physical_mail.service import (
    CampaignNotFoundError,
    CampaignSubmissionResult,
    DuplicateSubmissionError,
    MailPreviewResult,
    MailValidationReport,
    PhysicalMailService,
    PoplarPersistenceError,
    UnapprovedCampaignError,
    _EXECUTED_APPROVAL_TOKENS,
    send_single_physical_mail_outreach,
)


# ── Database Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite database for isolated test execution."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_test_tenant(db: Session, suffix: str = "A") -> Dict[str, Any]:
    """Helper to populate organization, campaign, contacts, and enrollments."""
    org = Organization(
        id=uuid.uuid4(),
        name=f"Direct Mail Org {suffix}",
        slug=f"direct-mail-org-{suffix.lower()}",
    )
    db.add(org)
    db.flush()

    user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=f"admin_{suffix.lower()}@testmail.com",
        full_name=f"Admin {suffix}",
        role="admin",
        hashed_password="fake_hash_value_1234567890",
        is_active=True,
    )
    db.add(user)

    company = Company(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Acme Corp {suffix}",
        domain=f"acme{suffix.lower()}.com",
        city="Austin",
        country="US",
    )
    db.add(company)

    campaign = Campaign(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Q4 Physical Mail Drive {suffix}",
        status="active",
        workflow_config={
            "nodes": [
                {"id": "node-1", "type": "start", "title": "Start"},
                {
                    "id": "node-2",
                    "type": "physical_mail",
                    "title": "Poplar 4x6 Postcard",
                    "config": {
                        "campaign_id": "cmp_poplar_test_123",
                        "creative_id": "crt_postcard_4x6",
                    },
                },
            ],
            "edges": [],
        },
    )
    db.add(campaign)
    db.commit()

    return {"org": org, "user": user, "company": company, "campaign": campaign}


def create_contact_with_address(
    db: Session,
    org: Organization,
    company: Company,
    first: str = "Jane",
    last: str = "Doe",
    addr1: Optional[str] = "123 Main St",
    city: Optional[str] = "Austin",
    state: Optional[str] = "TX",
    zip_code: Optional[str] = "78701",
    addr2: Optional[str] = None,
    country: Optional[str] = "US",
) -> Contact:
    """Helper to create a Contact with full postal address fields."""
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        company_id=company.id,
        first_name=first,
        last_name=last,
        email=f"{first.lower()}.{last.lower()}@acme.com",
        phone="+15125550199",
        lead_status="qualified",
        address_line_1=addr1,
        address_line_2=addr2,
        city=city,
        state=state,
        postal_code=zip_code,
        country=country,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ── 1. Postal Address Validation Tests ────────────────────────────────────────

def test_usps_address_validation_valid():
    """Accepts valid 5-digit ZIP, 9-digit ZIP+4, and 2-letter state abbreviations."""
    # 5-digit ZIP
    res1 = validate_usps_address(
        address_1="100 Congress Ave",
        city="Austin",
        state="tx",  # Case insensitive
        postal_code="78701",
        full_name="Alice Smith",
    )
    assert res1.is_valid is True
    assert res1.cleaned_address["state"] == "TX"
    assert res1.cleaned_address["postal_code"] == "78701"

    # 9-digit ZIP+4 with hyphen
    res2 = validate_usps_address(
        address_1="350 5th Ave",
        address_2="Suite 400",
        city="New York",
        state="NY",
        postal_code="10118-0110",
        company="Empire State Building Co",
    )
    assert res2.is_valid is True
    assert res2.cleaned_address["postal_code"] == "10118-0110"
    assert res2.cleaned_address["address_2"] == "Suite 400"

    # 9-digit unhyphenated ZIP is normalized
    res3 = validate_usps_address(
        address_1="200 S Michigan Ave",
        city="Chicago",
        state="IL",
        postal_code="606041234",
        full_name="Bob Jones",
    )
    assert res3.is_valid is True
    assert res3.cleaned_address["postal_code"] == "60604-1234"


def test_usps_address_validation_invalid():
    """Identifies and reports missing street, bad state, invalid ZIP, non-US country, or missing name."""
    # Missing street address
    r_no_street = validate_usps_address(
        address_1="",
        city="Austin",
        state="TX",
        postal_code="78701",
        full_name="Jane Doe",
    )
    assert r_no_street.is_valid is False
    assert any("street address" in e.lower() for e in r_no_street.errors)

    # Street address too short
    r_short = validate_usps_address(
        address_1="1",
        city="Austin",
        state="TX",
        postal_code="78701",
        full_name="Jane Doe",
    )
    assert r_short.is_valid is False
    assert any("too short" in e.lower() for e in r_short.errors)

    # Missing city
    r_no_city = validate_usps_address(
        address_1="123 Main St",
        city="",
        state="TX",
        postal_code="78701",
        full_name="Jane Doe",
    )
    assert r_no_city.is_valid is False
    assert any("missing city" in e.lower() for e in r_no_city.errors)

    # Invalid state abbreviation
    r_bad_state = validate_usps_address(
        address_1="123 Main St",
        city="Austin",
        state="TEXAS",  # Must be 2-letter code
        postal_code="78701",
        full_name="Jane Doe",
    )
    assert r_bad_state.is_valid is False
    assert any("state abbreviation" in e.lower() for e in r_bad_state.errors)

    # Invalid ZIP format
    r_bad_zip = validate_usps_address(
        address_1="123 Main St",
        city="Austin",
        state="TX",
        postal_code="ABCDE",
        full_name="Jane Doe",
    )
    assert r_bad_zip.is_valid is False
    assert any("postal code format" in e.lower() for e in r_bad_zip.errors)

    # Non-US country
    r_non_us = validate_usps_address(
        address_1="10 Downing St",
        city="London",
        state="LD",
        postal_code="SW1A2",
        country="UK",
        full_name="Prime Minister",
    )
    assert r_non_us.is_valid is False
    assert any("domestic us destinations" in e.lower() for e in r_non_us.errors)

    # Missing addressee (both full_name and company are empty)
    r_no_name = validate_usps_address(
        address_1="123 Main St",
        city="Austin",
        state="TX",
        postal_code="78701",
        full_name="",
        company="",
    )
    assert r_no_name.is_valid is False
    assert any("addressee name" in e.lower() for e in r_no_name.errors)


# ── 2. Poplar API Client Configuration & Security Tests ───────────────────────

def test_poplar_client_test_mode_isolation():
    """In test environment, client requires test key and refuses to silently use production key."""
    # Missing test key raises configuration error
    with pytest.raises(PoplarConfigurationError) as exc_info:
        PoplarClient(
            test_api_key=None,
            production_api_key="prod_secret_production_key_123456",
            environment="test",
        )
    assert "refuses to fall back to production" in str(exc_info.value).lower()

    # Valid test key initializes correctly
    client = PoplarClient(
        test_api_key="test_sample_access_token_12345",
        environment="test",
    )
    assert client.is_test_mode is True
    assert client.environment == "test"


def test_poplar_client_production_mode_guards():
    """Production mode strictly requires POPLAR_ALLOW_LIVE_SENDING=True and production key."""
    # Live sending flag False -> blocked
    with pytest.raises(PoplarConfigurationError) as exc_info:
        PoplarClient(
            production_api_key="prod_real_key_123",
            environment="production",
            allow_live_sending=False,
        )
    assert "live sending is disabled" in str(exc_info.value).lower()

    # Live sending True without key -> blocked
    with pytest.raises(PoplarConfigurationError) as exc_info2:
        PoplarClient(
            production_api_key="",
            environment="production",
            allow_live_sending=True,
        )
    assert "production api key is missing" in str(exc_info2.value).lower()

    # Live sending True with key -> permitted
    client = PoplarClient(
        production_api_key="prod_real_key_123",
        environment="production",
        allow_live_sending=True,
    )
    assert client.is_test_mode is False


def test_poplar_client_error_sanitization_and_rate_limits():
    """Client handles 401, 403, 404, 429, 500, timeouts and never logs API keys."""
    mock_http = MagicMock()

    # 401 Unauthorized
    resp_401 = httpx.Response(
        status_code=401,
        json={"error": "Unauthorized token test_secret_token_123"},
        request=httpx.Request("POST", "https://api.heypoplar.com/v1/mailing"),
    )
    mock_http.post.return_value = resp_401

    client = PoplarClient(test_api_key="test_secret_token_123", http_client=mock_http)
    with pytest.raises(PoplarAuthenticationError) as exc_401:
        client.create_mailing(
            campaign_id="cmp_123",
            recipient=PoplarRecipient(address_1="123 Main St", city="Austin", state="TX", postal_code="78701", full_name="Jane"),
        )
    assert "test_secret_token_123" not in str(exc_401.value)
    assert "authentication rejected" in str(exc_401.value).lower()

    # 429 Rate Limit with Retry-After header
    resp_429 = httpx.Response(
        status_code=429,
        headers={"Retry-After": "30"},
        json={"error": "Too Many Requests"},
        request=httpx.Request("POST", "https://api.heypoplar.com/v1/mailing"),
    )
    mock_http.post.return_value = resp_429
    with pytest.raises(PoplarRateLimitError) as exc_429:
        client.create_mailing(
            campaign_id="cmp_123",
            recipient=PoplarRecipient(address_1="123 Main St", city="Austin", state="TX", postal_code="78701", full_name="Jane"),
        )
    assert exc_429.value.retry_after == 30

    # Timeout
    mock_http.post.side_effect = httpx.ConnectTimeout("Connection timed out")
    with pytest.raises(PoplarTimeoutError):
        client.create_mailing(
            campaign_id="cmp_123",
            recipient=PoplarRecipient(address_1="123 Main St", city="Austin", state="TX", postal_code="78701", full_name="Jane"),
        )


def test_poplar_client_successful_request_and_schema():
    """POST /v1/mailing constructs correct payload and parses response."""
    mock_http = MagicMock()
    mock_http.post.return_value = httpx.Response(
        status_code=200,
        json={
            "id": "mlg_9876543210abcdef",
            "status": "mailing_queued",
            "campaign_id": "cmp_poplar_test_123",
            "created_at": "2026-10-22T20:00:00Z",
            "proof_url": "https://assets.heypoplar.com/proofs/sample.pdf",
            "estimated_delivery_date": "2026-10-28",
        },
        request=httpx.Request("POST", "https://api.heypoplar.com/v1/mailing"),
    )

    client = PoplarClient(test_api_key="test_sample_token", http_client=mock_http)
    recipient = PoplarRecipient(
        address_1="100 Congress Ave",
        address_2="Suite 200",
        city="Austin",
        state="TX",
        postal_code="78701",
        full_name="Bruce Wayne",
        company="Wayne Enterprises",
        identifier="outreach_uuid_123",
    )
    merge_tags = {"custom_greeting": "Valued Partner"}

    result = client.create_mailing(
        campaign_id="cmp_poplar_test_123",
        recipient=recipient,
        merge_tags=merge_tags,
        creative_id="crt_postcard_4x6",
    )

    assert result.id == "mlg_9876543210abcdef"
    assert result.status == "mailing_queued"
    assert result.proof_url == "https://assets.heypoplar.com/proofs/sample.pdf"

    # Verify posted payload matches documented schema
    called_kwargs = mock_http.post.call_args[1]
    posted_json = called_kwargs["json"]
    assert posted_json["campaign_id"] == "cmp_poplar_test_123"
    assert posted_json["creative_id"] == "crt_postcard_4x6"
    assert posted_json["recipient"]["address_1"] == "100 Congress Ave"
    assert posted_json["recipient"]["address_2"] == "Suite 200"
    assert posted_json["recipient"]["city"] == "Austin"
    assert posted_json["recipient"]["state"] == "TX"
    assert posted_json["recipient"]["postal_code"] == "78701"
    assert posted_json["recipient"]["full_name"] == "Bruce Wayne"
    assert posted_json["recipient"]["company"] == "Wayne Enterprises"
    assert posted_json["recipient"]["identifier"] == "outreach_uuid_123"
    assert posted_json["merge_tags"]["custom_greeting"] == "Valued Partner"


# ── 3. Campaign Pre-Flight Audit & Cost Preview Tests ─────────────────────────

def test_campaign_recipient_address_validation_report(db):
    """Categorizes campaign audience into valid and invalid recipients with itemized error lists."""
    tenant = create_test_tenant(db, "ValReport")
    org = tenant["org"]
    camp = tenant["campaign"]
    comp = tenant["company"]

    # 1. Valid recipient
    c1 = create_contact_with_address(db, org, comp, "Alice", "Valid", "100 Congress Ave", "Austin", "TX", "78701")
    # 2. Invalid recipient (missing street)
    c2 = create_contact_with_address(db, org, comp, "Bob", "NoStreet", "", "Austin", "TX", "78701")
    # 3. Invalid recipient (bad state code)
    c3 = create_contact_with_address(db, org, comp, "Charlie", "BadState", "200 Main St", "Austin", "TEXAS", "78701")

    # Enroll all three contacts in campaign
    for c in [c1, c2, c3]:
        db.add(CampaignContact(id=uuid.uuid4(), campaign_id=camp.id, contact_id=c.id, enrollment_status="in_progress"))
    db.commit()

    service = PhysicalMailService(db=db)
    report = service.validate_campaign_recipients(org_id=org.id, campaign_id=camp.id)

    assert report.total_recipients == 3
    assert report.valid_count == 1
    assert report.invalid_count == 2
    assert report.valid_recipients[0].full_name == "Alice Valid"

    invalid_names = [i.full_name for i in report.invalid_recipients]
    assert "Bob NoStreet" in invalid_names
    assert "Charlie BadState" in invalid_names


def test_campaign_mail_preview_and_cost_calculation(db):
    """Calculates estimated total cost ($1.15 per valid piece) and renders merge sample."""
    tenant = create_test_tenant(db, "Preview")
    org = tenant["org"]
    camp = tenant["campaign"]
    comp = tenant["company"]

    # 4 valid contacts, 1 invalid contact
    for i in range(4):
        c = create_contact_with_address(db, org, comp, f"User{i}", "Test", f"{100+i} Congress Ave", "Austin", "TX", "78701")
        db.add(CampaignContact(id=uuid.uuid4(), campaign_id=camp.id, contact_id=c.id, enrollment_status="in_progress"))
    # Invalid contact
    bad_c = create_contact_with_address(db, org, comp, "Bad", "Zip", "123 Main St", "Austin", "TX", "BADZIP")
    db.add(CampaignContact(id=uuid.uuid4(), campaign_id=camp.id, contact_id=bad_c.id, enrollment_status="in_progress"))
    db.commit()

    service = PhysicalMailService(db=db)
    preview = service.preview_campaign_mail(org_id=org.id, campaign_id=camp.id, unit_cost=1.15)

    assert preview.total_recipients == 5
    assert preview.valid_count == 4
    assert preview.invalid_count == 1
    # 4 valid recipients * $1.15 = $4.60
    assert preview.estimated_total_cost == 4.60
    assert preview.approval_required is True
    assert preview.sample_preview is not None
    assert preview.sample_preview["recipient"]["city"] == "Austin"
    assert len(preview.invalid_recipients) == 1


# ── 4. Approval Gate & Submission Orchestration Tests ─────────────────────────

def test_unapproved_submission_rejected(db):
    """Submission without approved=True is rejected before any mailings are created."""
    tenant = create_test_tenant(db, "Unapproved")
    service = PhysicalMailService(db=db)

    with pytest.raises(UnapprovedCampaignError) as exc_info:
        service.submit_approved_campaign(
            org_id=tenant["org"].id,
            campaign_id=tenant["campaign"].id,
            approved=False,  # Unapproved!
            approval_token="token_test_123",
        )
    assert "explicit approval before dispatch" in str(exc_info.value).lower()


def test_duplicate_submission_prevention(db):
    """Submitting the same approval token a second time raises DuplicateSubmissionError."""
    tenant = create_test_tenant(db, "Duplicate")
    org = tenant["org"]
    camp = tenant["campaign"]
    comp = tenant["company"]

    c = create_contact_with_address(db, org, comp, "Alice", "Test", "123 Main St", "Austin", "TX", "78701")
    db.add(CampaignContact(id=uuid.uuid4(), campaign_id=camp.id, contact_id=c.id, enrollment_status="in_progress"))
    db.commit()

    service = PhysicalMailService(db=db)
    token = f"approval_token_{uuid.uuid4().hex}"

    # First submission -> succeeds
    res1 = service.submit_approved_campaign(
        org_id=org.id,
        campaign_id=camp.id,
        approved=True,
        approval_token=token,
        force_mock=True,
    )
    assert res1.total_submitted == 1

    # Second submission with exact same token -> rejected
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        service.submit_approved_campaign(
            org_id=org.id,
            campaign_id=camp.id,
            approved=True,
            approval_token=token,
            force_mock=True,
        )
    assert "already been processed" in str(exc_info.value).lower()


def test_fail_closed_mock_simulation_mode(db):
    """When POPLAR_ALLOW_LIVE_SENDING is False, dispatches operate in safe mock mode."""
    tenant = create_test_tenant(db, "MockMode")
    org = tenant["org"]
    camp = tenant["campaign"]
    comp = tenant["company"]

    c = create_contact_with_address(db, org, comp, "Diana", "Prince", "456 Oak St", "Austin", "TX", "78701")
    db.add(CampaignContact(id=uuid.uuid4(), campaign_id=camp.id, contact_id=c.id, enrollment_status="in_progress"))
    db.commit()

    service = PhysicalMailService(db=db)
    token = f"mock_token_{uuid.uuid4().hex}"

    with patch.object(settings, "POPLAR_ENABLED", False):
        with patch.object(settings, "POPLAR_ALLOW_LIVE_SENDING", False):
            result = service.submit_approved_campaign(
                org_id=org.id,
                campaign_id=camp.id,
                approved=True,
                approval_token=token,
                force_mock=False,  # Still simulates because settings flags are False
            )

    assert result.total_submitted == 1
    outcome = result.outcomes[0]
    assert outcome.success is True
    assert outcome.simulated is True
    assert outcome.mailing_id.startswith("mlg_mock_")
    assert outcome.status == "sending"

    # Outreach record persisted with channel='physical_mail'
    outreach = db.get(Outreach, outcome.outreach_id)
    assert outreach.channel == "physical_mail"
    assert outreach.status == "sending"
    assert outreach.provider_message_id == outcome.mailing_id


def test_partial_failure_handling(db):
    """If provider rejects one recipient in a batch, others succeed and failure is recorded."""
    tenant = create_test_tenant(db, "PartialFail")
    org = tenant["org"]
    camp = tenant["campaign"]
    comp = tenant["company"]

    c1 = create_contact_with_address(db, org, comp, "GoodOne", "A", "100 First St", "Austin", "TX", "78701")
    c2 = create_contact_with_address(db, org, comp, "GoodTwo", "B", "200 Second St", "Austin", "TX", "78701")
    c3 = create_contact_with_address(db, org, comp, "FailingOne", "C", "300 Third St", "Austin", "TX", "78701")

    for c in [c1, c2, c3]:
        db.add(CampaignContact(id=uuid.uuid4(), campaign_id=camp.id, contact_id=c.id, enrollment_status="in_progress"))
    db.commit()

    # Create mock client that fails specifically for c3
    mock_client = MagicMock()
    def mock_create(campaign_id, recipient, **kwargs):
        full_name = recipient.full_name if isinstance(recipient, PoplarRecipient) else recipient.get("full_name")
        if "FailingOne" in str(full_name):
            raise PoplarValidationError("Poplar CASS Address rejected: Suite number missing.")
        mock_id = f"mlg_live_{uuid.uuid4().hex[:8]}"
        from app.services.physical_mail.poplar_client import PoplarMailingResult
        return PoplarMailingResult(id=mock_id, status="mailing_queued", campaign_id=campaign_id)

    mock_client.create_mailing.side_effect = mock_create

    service = PhysicalMailService(db=db, client=mock_client)
    token = f"partial_token_{uuid.uuid4().hex}"

    with patch.object(settings, "POPLAR_ENABLED", True):
        with patch.object(settings, "POPLAR_ALLOW_LIVE_SENDING", True):
            result = service.submit_approved_campaign(
                org_id=org.id,
                campaign_id=camp.id,
                approved=True,
                approval_token=token,
            )

    assert result.total_processed == 3
    assert result.total_submitted == 2
    assert result.total_failed == 1

    good_outcomes = [o for o in result.outcomes if o.success is True]
    failed_outcomes = [o for o in result.outcomes if o.success is False]
    assert len(good_outcomes) == 2
    assert len(failed_outcomes) == 1
    assert "CASS Address rejected" in failed_outcomes[0].error


def test_tenant_isolation(db):
    """Organization A cannot validate, preview, or submit Organization B's campaign."""
    tenant_a = create_test_tenant(db, "OrgA")
    tenant_b = create_test_tenant(db, "OrgB")

    service = PhysicalMailService(db=db)

    # Org B attempts to preview Org A's campaign
    with pytest.raises(CampaignNotFoundError):
        service.preview_campaign_mail(
            org_id=tenant_b["org"].id,  # Wrong organization ID
            campaign_id=tenant_a["campaign"].id,
        )

    # Org B attempts to submit Org A's campaign
    with pytest.raises(CampaignNotFoundError):
        service.submit_approved_campaign(
            org_id=tenant_b["org"].id,
            campaign_id=tenant_a["campaign"].id,
            approved=True,
            approval_token="cross_tenant_token",
            force_mock=True,
        )


def test_verify_connection_read_only_endpoint():
    """Verify that PoplarClient.verify_connection issues a read-only GET /v1/me request."""
    captured_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path == "/v1/me" and request.method == "GET":
            return httpx.Response(
                200,
                json={"id": "mock-acc-123", "name": "Test Account", "mode": "test"},
            )
        return httpx.Response(404, json={"error": "Not Found"})

    client = PoplarClient(
        test_api_key="test_sample_key_12345",
        environment="test",
        http_client=httpx.Client(transport=httpx.MockTransport(mock_handler)),
    )

    result = client.verify_connection()
    assert result["connected"] is True
    assert result["status_code"] == 200
    assert result["data"]["mode"] == "test"
    assert len(captured_requests) == 1
    assert captured_requests[0].method == "GET"
    assert captured_requests[0].url.path == "/v1/me"
    assert "Bearer test_sample_key_12345" in captured_requests[0].headers["Authorization"]



def test_mailpiece_configuration_validation(db):
    """Verifies mailpiece specification validation for sizes, formats, paper types, and postage tiers."""
    service = PhysicalMailService(db=db)

    # Valid combinations
    valid, errors, cost = service.validate_mailpiece_configuration(
        mailpiece_size="4x6",
        format_type="bw_envelope",
        paper_type="premium_coated",
        postage_class="usps_first_class",
    )
    assert valid is True
    assert len(errors) == 0
    assert cost > 0

    # Invalid size and format
    invalid, errors, cost = service.validate_mailpiece_configuration(
        mailpiece_size="8x10",  # invalid
        format_type="magazine",  # invalid
        paper_type="cheap_newsprint",  # invalid
        postage_class="fedex_express",  # invalid
    )
    assert invalid is False
    assert len(errors) == 4
    assert any("mailpiece size" in e.lower() for e in errors)
    assert any("format" in e.lower() for e in errors)
    assert any("paper type" in e.lower() for e in errors)
    assert any("postage class" in e.lower() for e in errors)


def test_configure_or_create_poplar_campaign_unit(db):
    """Configures physical mail and creates/links campaign in Poplar TEST environment."""
    tenant = create_test_tenant(db, "PoplarConfig")
    org = tenant["org"]
    campaign = tenant["campaign"]

    service = PhysicalMailService(db=db)

    # Mock PoplarClient to avoid network calls during unit test
    mock_client = MagicMock()
    mock_client.get_campaign.return_value = {
        "id": "cmp_test_mock_12345",
        "name": f"Agile - {campaign.name}",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="6x9",
            format_type="color_envelope",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            design_url="https://assets.heypoplar.com/templates/sample.pdf",
            design_name="Special Reactivation Letter",
            poplar_campaign_id="cmp_test_mock_12345",
        )

        assert res["campaign_id"] == campaign.id
        assert res["poplar_campaign_id"] == "cmp_test_mock_12345"
        assert res["poplar_status"] == "linked_existing"
        assert res["mailpiece"]["size"] == "6x9"
        assert res["mailpiece"]["format"] == "color_envelope"
        assert res["mailpiece"]["paper"] == "premium_coated"
        assert res["mailpiece"]["postage"] == "usps_first_class"
        assert res["design"]["name"] == "Special Reactivation Letter"

        # Verify campaign workflow_config was saved in database
        db.refresh(campaign)
        assert campaign.workflow_config is not None
        assert "poplar" in campaign.workflow_config
        assert campaign.workflow_config["poplar"]["campaign_id"] == "cmp_test_mock_12345"
        assert "physical_mail" in campaign.workflow_config["channels"]

        # Verify get_campaign_physical_mail_config retrieves it
        config_details = service.get_campaign_physical_mail_config(
            org_id=org.id,
            campaign_id=campaign.id,
        )
        assert config_details["configured"] is True
        assert config_details["poplar_campaign_id"] == "cmp_test_mock_12345"
        assert config_details["config"]["mailpiece"]["size"] == "6x9"

        # Verify create_campaign was NOT called
        mock_client.create_campaign.assert_not_called()


def test_list_account_creatives(db: Session):
    """Verify listing creatives across Poplar account."""
    tenant = create_test_tenant(db)
    service = PhysicalMailService(db=db)
    mock_client = MagicMock()
    mock_client.list_account_creatives.return_value = [
        {
            "id": "crt_postcard_001",
            "name": "Test postcard",
            "mail_type": "postcard",
            "format": "4x6",
            "state": "active",
            "thumbnail_url": "https://assets.heypoplar.com/templates/thumb1.png",
        }
    ]
    with patch.object(service, "_get_active_client", return_value=mock_client):
        creatives = service.list_account_creatives()
        assert len(creatives) == 1
        assert creatives[0]["id"] == "crt_postcard_001"
        assert creatives[0]["name"] == "Test postcard"


def test_validate_creative_asset_dimensions_and_bleed():
    """Verify asset file size, extension, and dimensional specs."""
    from app.services.physical_mail.service import validate_creative_asset

    # Valid 4x6 PDF
    res = validate_creative_asset(
        file_name="proof.pdf",
        file_size_bytes=1024 * 1024,
        mailpiece_size="4x6",
    )
    assert res["is_valid"] is True
    assert res["spec"]["dimensions_px_300dpi"] == [1275, 1875]
    assert len(res["errors"]) == 0

    # Oversized file > 25MB
    res_large = validate_creative_asset(
        file_name="huge.pdf",
        file_size_bytes=30 * 1024 * 1024,
        mailpiece_size="4x6",
    )
    assert res_large["is_valid"] is False
    assert any("25 MB" in err for err in res_large["errors"])

    # Unsupported format (.docx)
    res_docx = validate_creative_asset(
        file_name="letter.docx",
        mailpiece_size="4x6",
    )
    assert res_docx["is_valid"] is False
    assert any("Allowed: PDF, PNG, JPEG" in err for err in res_docx["errors"])


def test_fastapi_poplar_health_endpoint_connected(db: Session):
    """Verify GET /api/v1/physical-mail/health reports connected state when provider succeeds."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "HealthTest")
    org = tenant["org"]
    user = tenant["user"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_poplar = MagicMock()
        mock_poplar.verify_connection.return_value = {
            "connected": True,
            "status_code": 200,
            "data": {
                "id": "55655657-43f7-48ee-bc1a-06ed6926a41b",
                "name": "Agile Receivables Inc",
                "mode": "test",
            },
        }
        with patch("app.api.v1.physical_mail.get_poplar_client", return_value=mock_poplar):
            with patch.object(settings, "POPLAR_ENABLED", True):
                with patch.object(settings, "POPLAR_TEST_API_KEY", "test_valid_key"):
                    resp = client.get("/api/v1/physical-mail/health")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["configured"] is True
                    assert data["connected"] is True
                    assert data["account_name"] == "Agile Receivables Inc"
                    assert data["account_id"] == "55655657-43f7-48ee-bc1a-06ed6926a41b"
                    assert data["allow_live_sending"] is False
    finally:
        app.dependency_overrides.clear()

def test_fastapi_poplar_health_endpoint_provider_error(db: Session):
    """Verify GET /api/v1/physical-mail/health gracefully returns connected=False on provider error."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "HealthFailTest")
    org = tenant["org"]
    user = tenant["user"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_poplar = MagicMock()
        mock_poplar.verify_connection.side_effect = PoplarAPIError(500, "Poplar upstream 500 error")
        with patch("app.api.v1.physical_mail.get_poplar_client", return_value=mock_poplar):
            with patch.object(settings, "POPLAR_ENABLED", True):
                with patch.object(settings, "POPLAR_TEST_API_KEY", "test_valid_key"):
                    resp = client.get("/api/v1/physical-mail/health")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["configured"] is True
                    assert data["connected"] is False
                    assert "Unable to reach Poplar API" in data["message"]
                    assert "Poplar upstream 500" in data["error"]
    finally:
        app.dependency_overrides.clear()


def test_fastapi_poplar_health_endpoint_unconfigured(db: Session):
    """Verify GET /api/v1/physical-mail/health reports configured=False when disabled."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "HealthUnconfigTest")
    org = tenant["org"]
    user = tenant["user"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        with patch.object(settings, "POPLAR_ENABLED", False):
            resp = client.get("/api/v1/physical-mail/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is False
            assert data["connected"] is False
            assert "unconfigured or disabled" in data["message"].lower()
    finally:
        app.dependency_overrides.clear()


def test_fastapi_poplar_creatives_endpoint(db: Session):
    """Verify GET /api/v1/physical-mail/creatives returns creative catalog."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "CreativesTest")
    org = tenant["org"]
    user = tenant["user"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_creatives = [
            {
                "id": "crt_postcard_123",
                "name": "Spring Reactivation",
                "mail_type": "postcard",
                "format": "4x6",
                "state": "active",
                "thumbnail_url": "https://assets.heypoplar.com/thumb.png",
            }
        ]
        with patch.object(PhysicalMailService, "list_account_creatives", return_value=mock_creatives):
            resp = client.get("/api/v1/physical-mail/creatives")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["creatives"][0]["id"] == "crt_postcard_123"
            assert data["creatives"][0]["name"] == "Spring Reactivation"
    finally:
        app.dependency_overrides.clear()


def test_configure_poplar_campaign_preserves_supplied_id_and_links_locally(db: Session):
    """Verify that a supplied Poplar campaign ID is preserved, verified via GET, and saved locally."""
    tenant = create_test_tenant(db, "PreserveIdTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.return_value = {
        "id": "c80a191d-9bf4-4d40-b463-f2c67a27a8c2",
        "name": "postcard - single send",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="6x9",
            format_type="color_envelope",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            poplar_campaign_id="c80a191d-9bf4-4d40-b463-f2c67a27a8c2",
        )

        # 1. Supplied ID is preserved
        assert res["poplar_campaign_id"] == "c80a191d-9bf4-4d40-b463-f2c67a27a8c2"
        assert res["poplar_status"] == "linked_existing"

        # 2. Verified using GET campaign-by-ID
        mock_client.get_campaign.assert_called_once_with("c80a191d-9bf4-4d40-b463-f2c67a27a8c2")

        # 3. Remote creation and mailing NEVER called
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()

        # 4. Verified association saved in local campaign configuration
        db.refresh(campaign)
        assert campaign.workflow_config["poplar"]["campaign_id"] == "c80a191d-9bf4-4d40-b463-f2c67a27a8c2"
        assert campaign.workflow_config["poplar"]["name"] == "postcard - single send"
        assert campaign.workflow_config["poplar"]["status"] == "linked_existing"


def test_configure_poplar_campaign_invalid_id_raises_error_without_creating(db: Session):
    """Verify that an invalid or not-found Poplar campaign ID raises a clear error and never creates remote campaigns."""
    tenant = create_test_tenant(db, "InvalidIdTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.side_effect = PoplarNotFoundError(404, "Campaign not found on Poplar.")

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError) as exc_info:
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="6x9",
                format_type="color_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                poplar_campaign_id="non_existent_campaign_id",
            )

        assert "does not exist in your Poplar account" in str(exc_info.value)
        # Asserts zero remote creations and zero mailings
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()


def test_configure_poplar_campaign_missing_id_raises_error_without_creating(db: Session):
    """Verify that omitting a Poplar campaign ID raises an error and refuses to auto-create a remote campaign."""
    tenant = create_test_tenant(db, "MissingIdTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError) as exc_info:
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="6x9",
                format_type="color_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                poplar_campaign_id=None,
            )

        assert "Poplar campaign ID is required" in str(exc_info.value)
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()


def test_failed_get_does_not_trigger_post_campaign_or_mailing(db: Session):
    """Verify that upstream Poplar API failure on GET does NOT fall back to POST /v1/campaigns or POST /v1/mailing."""
    tenant = create_test_tenant(db, "FailedGetTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.side_effect = PoplarAPIError(500, "Poplar internal server error")

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError) as exc_info:
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="6x9",
                format_type="color_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                poplar_campaign_id="cmp_err_test",
            )

        assert "Failed to verify Poplar campaign 'cmp_err_test'" in str(exc_info.value)
        # Critical safety check: GET failure must NEVER fall back to POST
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()


def test_list_poplar_campaigns_read_only(db: Session):
    """Verify that listing Poplar campaigns performs only read-only GET requests and never writes."""
    tenant = create_test_tenant(db, "ListCampaignsTest")
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.list_campaigns.return_value = [
        {"id": "cmp_1", "name": "Letter Campaign", "purpose": "acquisition"},
        {"id": "cmp_2", "name": "Postcard Campaign", "purpose": "retention"},
    ]

    with patch.object(service, "_get_active_client", return_value=mock_client):
        campaigns = service.list_poplar_campaigns()
        assert len(campaigns) == 2
        assert campaigns[0]["id"] == "cmp_1"
        assert campaigns[1]["id"] == "cmp_2"

        mock_client.list_campaigns.assert_called_once()
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()


def test_fastapi_poplar_campaigns_endpoint(db: Session):
    """Verify GET /api/v1/physical-mail/campaigns returns read-only campaign listing."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiCampaignsTest")
    org = tenant["org"]
    user = tenant["user"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_campaigns = [
            {"id": "cmp_abc_1", "name": "Holiday Promo", "purpose": "acquisition", "status": "active"},
            {"id": "cmp_abc_2", "name": "Winback Letter", "purpose": "retention", "status": "active"},
        ]
        with patch.object(PhysicalMailService, "list_poplar_campaigns", return_value=mock_campaigns):
            resp = client.get("/api/v1/physical-mail/campaigns")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert data["campaigns"][0]["id"] == "cmp_abc_1"
            assert data["campaigns"][0]["name"] == "Holiday Promo"
            assert data["campaigns"][1]["id"] == "cmp_abc_2"
    finally:
        app.dependency_overrides.clear()


def test_fastapi_configure_campaign_with_existing_poplar_id(db: Session):
    """Verify POST /api/v1/campaigns/{id}/physical-mail/configure accepts and binds existing Poplar ID."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiConfigureTest")
    org = tenant["org"]
    user = tenant["user"]
    campaign = tenant["campaign"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_client = MagicMock()
        mock_client.get_campaign.return_value = {
            "id": "c80a191d-9bf4-4d40-b463-f2c67a27a8c2",
            "name": "postcard - single send",
        }
        with patch.object(PhysicalMailService, "_get_active_client", return_value=mock_client):
            payload = {
                "mailpiece_size": "6x9",
                "format_type": "color_envelope",
                "paper_type": "premium_coated",
                "postage_class": "usps_first_class",
                "poplar_campaign_id": "c80a191d-9bf4-4d40-b463-f2c67a27a8c2",
            }
            resp = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["poplar_campaign_id"] == "c80a191d-9bf4-4d40-b463-f2c67a27a8c2"
            assert data["poplar_status"] == "linked_existing"
            mock_client.create_campaign.assert_not_called()
            mock_client.send_mailing.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_configure_poplar_campaign_mismatched_id_rejected(db: Session):
    """Verify that if the Poplar GET-by-ID returns a different ID than requested, validation fails and nothing is saved."""
    tenant = create_test_tenant(db, "MismatchedIdTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.return_value = {
        "id": "poplar_campaign_different_uuid_999",
        "name": "letter - single send",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError) as exc_info:
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="6x9",
                format_type="color_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                poplar_campaign_id="manual_sales_uuid_123",
            )

        assert "Poplar verification mismatch" in str(exc_info.value)
        assert "manual_sales_uuid_123" in str(exc_info.value)
        assert "poplar_campaign_different_uuid_999" in str(exc_info.value)

        # Critical safety: no remote creations or sends
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()

        # Config remains unmutated / unlinked
        db.refresh(campaign)
        assert "poplar" not in (campaign.workflow_config or {})


def test_configure_poplar_campaign_manual_id_verification_preserves_equality(db: Session):
    """Verify manual ID entry binds correctly when GET-by-ID confirms ID equality and updates the name."""
    tenant = create_test_tenant(db, "ManualIdPreservesTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.return_value = {
        "id": "manual_sales_uuid_123",
        "name": "testing for sales",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="6x9",
            format_type="color_envelope",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            poplar_campaign_id="manual_sales_uuid_123",
        )

        assert res["poplar_campaign_id"] == "manual_sales_uuid_123"
        assert res["poplar_name"] == "testing for sales"
        assert res["poplar_status"] == "linked_existing"

        db.refresh(campaign)
        assert campaign.workflow_config["poplar"]["campaign_id"] == "manual_sales_uuid_123"
        assert campaign.workflow_config["poplar"]["name"] == "testing for sales"
        assert campaign.workflow_config["poplar"]["status"] == "linked_existing"


def test_configure_poplar_campaign_verification_failure_does_not_mutate_config(db: Session):
    """Verify that when verification fails (e.g. 404), the local campaign configuration is not mutated."""
    tenant = create_test_tenant(db, "FailureNoMutationTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.side_effect = PoplarNotFoundError(404, "Not Found")

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError):
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="6x9",
                format_type="color_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                poplar_campaign_id="nonexistent_id_404",
            )

        db.refresh(campaign)
        assert "poplar" not in (campaign.workflow_config or {})


def test_fastapi_configure_campaign_rejects_mismatched_id(db: Session):
    """Verify POST /api/v1/campaigns/{id}/physical-mail/configure returns 400 when Poplar ID mismatches."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiMismatchTest")
    org = tenant["org"]
    user = tenant["user"]
    campaign = tenant["campaign"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_client = MagicMock()
        mock_client.get_campaign.return_value = {
            "id": "remote_different_id_789",
            "name": "letter - single send",
        }
        with patch.object(PhysicalMailService, "_get_active_client", return_value=mock_client):
            payload = {
                "mailpiece_size": "6x9",
                "format_type": "color_envelope",
                "paper_type": "premium_coated",
                "postage_class": "usps_first_class",
                "poplar_campaign_id": "requested_user_id_123",
            }
            resp = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload)
            assert resp.status_code == 400
            assert "Poplar verification mismatch" in resp.json()["detail"]
            mock_client.create_campaign.assert_not_called()
            mock_client.send_mailing.assert_not_called()
    finally:
        app.dependency_overrides.clear()


# ── Dual-Workflow Tests (Connect Existing vs Create New) ──────────────────────

def test_configure_poplar_campaign_create_mode_success(db: Session):
    """Verify workflow_mode='create' calls client.create_campaign, verifies via GET, and saves status='created_remote'."""
    tenant = create_test_tenant(db, "CreateModeSuccessTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.create_campaign.return_value = {
        "id": "new_poplar_uuid_888",
        "name": "Agile - New Campaign",
        "purpose": "retention",
        "sub_purpose": "reactivation",
        "status": "active",
    }
    mock_client.get_campaign.return_value = {
        "id": "new_poplar_uuid_888",
        "name": "Agile - New Campaign",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="6x9",
            format_type="color_envelope",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            workflow_mode="create",
            new_campaign_name="Agile - New Campaign",
            purpose="retention",
            sub_purpose="reactivation",
            description="Automated sales outreach",
        )

        assert res["poplar_campaign_id"] == "new_poplar_uuid_888"
        assert res["poplar_status"] == "created_remote"
        assert res["poplar_name"] == "Agile - New Campaign"

        # Verify client calls
        mock_client.create_campaign.assert_called_once_with(
            name="Agile - New Campaign",
            purpose="retention",
            sub_purpose="reactivation",
            description="Automated sales outreach",
        )
        mock_client.get_campaign.assert_called_once_with("new_poplar_uuid_888")
        mock_client.send_mailing.assert_not_called()

        # Local persistence verification
        db.refresh(campaign)
        assert campaign.workflow_config["poplar"]["campaign_id"] == "new_poplar_uuid_888"
        assert campaign.workflow_config["poplar"]["status"] == "created_remote"
        assert campaign.workflow_config["poplar"]["name"] == "Agile - New Campaign"


def test_configure_poplar_campaign_create_mode_blank_name_rejected(db: Session):
    """Verify workflow_mode='create' rejects empty or whitespace-only campaign name."""
    tenant = create_test_tenant(db, "BlankNameTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError) as exc_info:
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="4x6",
                format_type="bw_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                workflow_mode="create",
                new_campaign_name="   ",
            )

        assert "name cannot be blank" in str(exc_info.value).lower()
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()


def test_configure_poplar_campaign_create_mode_upstream_error(db: Session):
    """Verify upstream errors during remote campaign creation are handled cleanly without mutating database."""
    tenant = create_test_tenant(db, "UpstreamErrorTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.create_campaign.side_effect = PoplarAPIError(500, "Poplar gateway error")

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarAPIError):
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="4x6",
                format_type="bw_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                workflow_mode="create",
                new_campaign_name="Agile - Error Campaign",
            )

        mock_client.create_campaign.assert_called_once()
        mock_client.get_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()

        db.refresh(campaign)
        assert "poplar" not in (campaign.workflow_config or {})


def test_configure_poplar_campaign_create_mode_verification_failure(db: Session):
    """Verify that if post-creation GET verification returns a mismatched ID, operation fails and nothing is saved."""
    tenant = create_test_tenant(db, "CreateVerificationMismatchTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.create_campaign.return_value = {
        "id": "created_poplar_id_aaa",
        "name": "Agile - Mismatch",
    }
    mock_client.get_campaign.return_value = {
        "id": "different_retrieved_id_bbb",
        "name": "Agile - Mismatch",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with pytest.raises(PoplarValidationError) as exc_info:
            service.configure_or_create_poplar_campaign(
                org_id=org.id,
                campaign_id=campaign.id,
                mailpiece_size="6x9",
                format_type="color_envelope",
                paper_type="premium_coated",
                postage_class="usps_first_class",
                workflow_mode="create",
                new_campaign_name="Agile - Mismatch",
            )

        assert "Poplar verification mismatch" in str(exc_info.value)
        db.refresh(campaign)
        assert "poplar" not in (campaign.workflow_config or {})


def test_configure_poplar_campaign_create_mode_persistence_failure_retains_remote_id(db: Session):
    """Verify that if remote creation succeeds but database commit fails, PoplarPersistenceError preserves remote ID."""
    tenant = create_test_tenant(db, "PersistenceFailureTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.create_campaign.return_value = {
        "id": "created_remote_uuid_999",
        "name": "Agile - Persistence Test",
    }
    mock_client.get_campaign.return_value = {
        "id": "created_remote_uuid_999",
        "name": "Agile - Persistence Test",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        with patch.object(service.db, "commit", side_effect=Exception("Database connection terminated")):
            with pytest.raises(PoplarPersistenceError) as exc_info:
                service.configure_or_create_poplar_campaign(
                    org_id=org.id,
                    campaign_id=campaign.id,
                    mailpiece_size="6x9",
                    format_type="color_envelope",
                    paper_type="premium_coated",
                    postage_class="usps_first_class",
                    workflow_mode="create",
                    new_campaign_name="Agile - Persistence Test",
                )

            assert exc_info.value.poplar_campaign_id == "created_remote_uuid_999"
            assert "created_remote_uuid_999" in str(exc_info.value)
            assert "Connect Existing" in str(exc_info.value)


def test_configure_poplar_campaign_connect_mode_never_calls_create_campaign(db: Session):
    """Verify that workflow_mode='connect' strictly uses GET verification and NEVER calls create_campaign."""
    tenant = create_test_tenant(db, "ConnectModeSafetyTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.return_value = {
        "id": "existing_campaign_uuid_333",
        "name": "Pre-existing Poplar Campaign",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="4x6",
            format_type="bw_envelope",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            workflow_mode="connect",
            poplar_campaign_id="existing_campaign_uuid_333",
        )

        assert res["poplar_status"] == "linked_existing"
        assert res["poplar_campaign_id"] == "existing_campaign_uuid_333"

        # Explicit safety assertion: create_campaign was NEVER called
        mock_client.create_campaign.assert_not_called()
        mock_client.send_mailing.assert_not_called()


def test_fastapi_configure_endpoint_create_mode(db: Session):
    """Verify POST /api/v1/campaigns/{id}/physical-mail/configure end-to-end with workflow_mode='create'."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiCreateTest")
    org = tenant["org"]
    user = tenant["user"]
    campaign = tenant["campaign"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_client = MagicMock()
        mock_client.create_campaign.return_value = {
            "id": "api_created_id_555",
            "name": "Agile - Spring Drop",
            "purpose": "retention",
            "sub_purpose": "reactivation",
            "status": "active",
        }
        mock_client.get_campaign.return_value = {
            "id": "api_created_id_555",
            "name": "Agile - Spring Drop",
        }

        with patch.object(PhysicalMailService, "_get_active_client", return_value=mock_client):
            payload = {
                "workflow_mode": "create",
                "new_campaign_name": "Agile - Spring Drop",
                "purpose": "retention",
                "sub_purpose": "reactivation",
                "mailpiece_size": "6x9",
                "format_type": "color_envelope",
                "paper_type": "premium_coated",
                "postage_class": "usps_first_class",
            }
            resp = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["poplar_campaign_id"] == "api_created_id_555"
            assert data["poplar_status"] == "created_remote"
            assert data["poplar_name"] == "Agile - Spring Drop"

            mock_client.create_campaign.assert_called_once()
            mock_client.send_mailing.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_fastapi_configure_endpoint_persistence_failure(db: Session):
    """Verify POST /api/v1/campaigns/{id}/physical-mail/configure returns 500 with remote campaign ID on persistence error."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiPersistenceFailTest")
    org = tenant["org"]
    user = tenant["user"]
    campaign = tenant["campaign"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_client = MagicMock()
        mock_client.create_campaign.return_value = {
            "id": "orphaned_poplar_id_777",
            "name": "Agile - Fail Persistence",
        }
        mock_client.get_campaign.return_value = {
            "id": "orphaned_poplar_id_777",
            "name": "Agile - Fail Persistence",
        }

        with patch.object(PhysicalMailService, "_get_active_client", return_value=mock_client):
            with patch.object(Session, "commit", side_effect=Exception("Database write conflict")):
                payload = {
                    "workflow_mode": "create",
                    "new_campaign_name": "Agile - Fail Persistence",
                    "mailpiece_size": "6x9",
                    "format_type": "color_envelope",
                    "paper_type": "premium_coated",
                    "postage_class": "usps_first_class",
                }
                resp = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload)
                assert resp.status_code == 500
                detail = resp.json()["detail"]
                assert detail["poplar_campaign_id"] == "orphaned_poplar_id_777"
                assert detail["code"] == "POPLAR_PERSISTENCE_FAILED"
    finally:
        app.dependency_overrides.clear()



# ── Purpose and Sub-Purpose Enum Validation Regression Tests ─────────────────

def test_create_campaign_valid_purpose_mappings_and_normalization(db: Session):
    """Verify that valid purpose ('retention') and sub-purpose ('reactivation') are accepted and normalized."""
    tenant = create_test_tenant(db, "PurposeMappingNormalizationTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.create_campaign.return_value = {
        "id": "poplar_norm_123",
        "name": "Agile - Normalized Test",
        "purpose": "retention",
        "sub_purpose": "reactivation",
    }
    mock_client.get_campaign.return_value = {
        "id": "poplar_norm_123",
        "name": "Agile - Normalized Test",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        # Case variation and extra whitespace should normalize cleanly
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="6x9",
            format_type="color_envelope",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            workflow_mode="create",
            new_campaign_name="Agile - Normalized Test",
            purpose="  Retention  ",
            sub_purpose="  REACTIVATION  ",
        )

        assert res["poplar_campaign_id"] == "poplar_norm_123"
        assert res["poplar_status"] == "created_remote"

        # Verify normalized values passed to client.create_campaign
        mock_client.create_campaign.assert_called_once_with(
            name="Agile - Normalized Test",
            purpose="retention",
            sub_purpose="reactivation",
            description=None,
        )


def test_create_campaign_invalid_purpose_rejected(db: Session):
    """Verify that unverified/invalid purpose (e.g., 'acquisition', 'loyalty') is rejected before remote calls."""
    tenant = create_test_tenant(db, "InvalidPurposeTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()

    with patch.object(service, "_get_active_client", return_value=mock_client):
        for invalid_purpose in ["acquisition", "loyalty", "prospecting", "invalid_enum"]:
            with pytest.raises(PoplarValidationError) as exc_info:
                service.configure_or_create_poplar_campaign(
                    org_id=org.id,
                    campaign_id=campaign.id,
                    mailpiece_size="6x9",
                    format_type="color_envelope",
                    paper_type="premium_coated",
                    postage_class="usps_first_class",
                    workflow_mode="create",
                    new_campaign_name="Agile - Invalid Purpose",
                    purpose=invalid_purpose,
                    sub_purpose="reactivation",
                )
            assert f"Invalid Poplar campaign purpose '{invalid_purpose}'" in str(exc_info.value)
            assert "Accepted values: retention" in str(exc_info.value)

        # Ensure no remote creation calls were attempted
        mock_client.create_campaign.assert_not_called()


def test_create_campaign_invalid_sub_purpose_rejected(db: Session):
    """Verify that unverified/invalid sub-purpose (e.g., 'prospecting', 'winback', 'nurture') is rejected before remote calls."""
    tenant = create_test_tenant(db, "InvalidSubPurposeTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()

    with patch.object(service, "_get_active_client", return_value=mock_client):
        for invalid_sub in ["prospecting", "winback", "nurture", "general", "invalid_enum"]:
            with pytest.raises(PoplarValidationError) as exc_info:
                service.configure_or_create_poplar_campaign(
                    org_id=org.id,
                    campaign_id=campaign.id,
                    mailpiece_size="6x9",
                    format_type="color_envelope",
                    paper_type="premium_coated",
                    postage_class="usps_first_class",
                    workflow_mode="create",
                    new_campaign_name="Agile - Invalid Sub-Purpose",
                    purpose="retention",
                    sub_purpose=invalid_sub,
                )
            assert f"Invalid Poplar campaign sub-purpose '{invalid_sub}'" in str(exc_info.value)
            assert "Accepted values: reactivation" in str(exc_info.value)

        # Ensure no remote creation calls were attempted
        mock_client.create_campaign.assert_not_called()


def test_poplar_client_create_campaign_enum_validation():
    """Verify PoplarClient.create_campaign validates purpose and sub_purpose directly without making network requests."""
    client = PoplarClient(test_api_key="test_sample_api_key_12345", environment="test")

    # Invalid purpose
    with pytest.raises(PoplarValidationError) as exc1:
        client.create_campaign(name="Direct Test", purpose="acquisition", sub_purpose="reactivation")
    assert "Invalid Poplar campaign purpose 'acquisition'" in str(exc1.value)

    # Invalid sub-purpose
    with pytest.raises(PoplarValidationError) as exc2:
        client.create_campaign(name="Direct Test", purpose="retention", sub_purpose="prospecting")
    assert "Invalid Poplar campaign sub-purpose 'prospecting'" in str(exc2.value)


def test_fastapi_configure_endpoint_invalid_purpose_and_sub_purpose_rejected(db: Session):
    """Verify FastAPI endpoint rejects invalid purpose or sub_purpose with 400 error."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiPurposeValidationTest")
    org = tenant["org"]
    user = tenant["user"]
    campaign = tenant["campaign"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_client = MagicMock()
        with patch.object(PhysicalMailService, "_get_active_client", return_value=mock_client):
            # Test rejected purpose: 'acquisition'
            payload_purpose = {
                "workflow_mode": "create",
                "new_campaign_name": "Agile - Invalid Purpose API",
                "purpose": "acquisition",
                "sub_purpose": "reactivation",
                "mailpiece_size": "6x9",
                "format_type": "color_envelope",
                "paper_type": "premium_coated",
                "postage_class": "usps_first_class",
            }
            resp1 = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload_purpose)
            assert resp1.status_code == 400
            assert "Invalid Poplar campaign purpose 'acquisition'" in resp1.json()["detail"]

            # Test rejected sub_purpose: 'prospecting'
            payload_sub = {
                "workflow_mode": "create",
                "new_campaign_name": "Agile - Invalid Sub-Purpose API",
                "purpose": "retention",
                "sub_purpose": "prospecting",
                "mailpiece_size": "6x9",
                "format_type": "color_envelope",
                "paper_type": "premium_coated",
                "postage_class": "usps_first_class",
            }
            resp2 = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload_sub)
            assert resp2.status_code == 400
            assert "Invalid Poplar campaign sub-purpose 'prospecting'" in resp2.json()["detail"]

            mock_client.create_campaign.assert_not_called()
    finally:
        app.dependency_overrides.clear()



# ── Postcard Format & Creative Alignment Regression Tests ────────────────────

def test_postcard_format_validation():
    """Verify that 'postcard' is recognized as a valid mailpiece format in options and specs."""
    from app.services.physical_mail.service import (
        VALID_FORMATS,
        SUPPORTED_MAILPIECE_OPTIONS,
        DIMENSIONAL_SPECIFICATIONS,
    )

    assert "postcard" in VALID_FORMATS
    format_ids = [fmt["id"] for fmt in SUPPORTED_MAILPIECE_OPTIONS["formats"]]
    assert "postcard" in format_ids
    assert "postcard" in DIMENSIONAL_SPECIFICATIONS


def test_postcard_sizes_and_pricing_tiers(db: Session):
    """Verify that postcard sizes (4x6, 6x9, 6x11) correctly validate and derive costs matching the pricing matrix."""
    service = PhysicalMailService(db=db)

    expected_pricing = [
        ("4x6", "usps_standard", 0.70),
        ("4x6", "usps_first_class", 0.85),
        ("6x9", "usps_standard", 0.95),
        ("6x9", "usps_first_class", 1.15),
        ("6x11", "usps_standard", 1.10),
        ("6x11", "usps_first_class", 1.35),
    ]

    for size, postage, expected_cost in expected_pricing:
        is_valid, errors, unit_cost = service.validate_mailpiece_configuration(
            mailpiece_size=size,
            format_type="postcard",
            paper_type="premium_coated",
            postage_class=postage,
        )
        assert is_valid, f"Expected valid for {size} + {postage}, got errors: {errors}"
        assert len(errors) == 0
        assert unit_cost == expected_cost, f"Cost mismatch for {size} + {postage}: got {unit_cost}, expected {expected_cost}"


def test_letter_and_self_mailer_configurations_continue_working(db: Session):
    """Verify that existing letter and self-mailer formats continue to validate and derive costs correctly."""
    service = PhysicalMailService(db=db)

    letter_mailer_checks = [
        ("bw_envelope", "usps_standard", 0.90),
        ("bw_envelope", "usps_first_class", 1.10),
        ("color_envelope", "usps_standard", 1.05),
        ("color_envelope", "usps_first_class", 1.30),
        ("bifold", "usps_standard", 1.20),
        ("bifold", "usps_first_class", 1.45),
        ("trifold", "usps_standard", 1.25),
        ("trifold", "usps_first_class", 1.55),
    ]

    for fmt, postage, expected_cost in letter_mailer_checks:
        is_valid, errors, unit_cost = service.validate_mailpiece_configuration(
            mailpiece_size="4x6",  # base size
            format_type=fmt,
            paper_type="premium_coated",
            postage_class=postage,
        )
        assert is_valid, f"Expected valid for format {fmt}, got errors: {errors}"
        assert len(errors) == 0
        assert unit_cost == expected_cost, f"Cost mismatch for {fmt} + {postage}: got {unit_cost}, expected {expected_cost}"


def test_invalid_format_and_size_combinations(db: Session):
    """Verify that invalid format or size inputs fail validation with descriptive errors."""
    service = PhysicalMailService(db=db)

    # Invalid format
    is_valid, errors, _ = service.validate_mailpiece_configuration(
        mailpiece_size="6x9",
        format_type="invalid_format_xyz",
        paper_type="premium_coated",
        postage_class="usps_first_class",
    )
    assert not is_valid
    assert any("Invalid format 'invalid_format_xyz'" in e for e in errors)

    # Invalid size
    is_valid2, errors2, _ = service.validate_mailpiece_configuration(
        mailpiece_size="8.5x14_legal",
        format_type="postcard",
        paper_type="premium_coated",
        postage_class="usps_first_class",
    )
    assert not is_valid2
    assert any("Invalid mailpiece size '8.5x14_legal'" in e for e in errors2)


def test_configure_poplar_campaign_with_postcard_format(db: Session):
    """Verify configure_or_create_poplar_campaign persists format_type='postcard' with correct unit cost."""
    tenant = create_test_tenant(db, "PostcardFormatTest")
    org = tenant["org"]
    campaign = tenant["campaign"]
    service = PhysicalMailService(db=db)

    mock_client = MagicMock()
    mock_client.get_campaign.return_value = {
        "id": "poplar_campaign_postcard_001",
        "name": "postcard - single send",
    }

    with patch.object(service, "_get_active_client", return_value=mock_client):
        res = service.configure_or_create_poplar_campaign(
            org_id=org.id,
            campaign_id=campaign.id,
            mailpiece_size="6x9",
            format_type="postcard",
            paper_type="premium_coated",
            postage_class="usps_first_class",
            workflow_mode="connect",
            poplar_campaign_id="poplar_campaign_postcard_001",
            creative_id="a9c859f4-d1e9-4005-bbd1-16f744b7c944",
        )

        assert res["poplar_campaign_id"] == "poplar_campaign_postcard_001"
        assert res["poplar_status"] == "linked_existing"
        assert res["unit_cost"] == 1.15
        assert res["mailpiece"]["format"] == "postcard"
        assert res["mailpiece"]["size"] == "6x9"

        # Verify DB persistence
        db.refresh(campaign)
        mailpiece = campaign.workflow_config["poplar"]["mailpiece"]
        assert mailpiece["format"] == "postcard"
        assert mailpiece["size"] == "6x9"
        assert mailpiece["unit_cost"] == 1.15


def test_fastapi_configure_endpoint_postcard_format(db: Session):
    """Verify FastAPI configure endpoint succeeds with format_type='postcard' and returns 200."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_current_active_user, get_current_organization, get_db

    tenant = create_test_tenant(db, "FastApiPostcardTest")
    org = tenant["org"]
    user = tenant["user"]
    campaign = tenant["campaign"]

    app.dependency_overrides[get_current_organization] = lambda: org
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    try:
        mock_client = MagicMock()
        mock_client.get_campaign.return_value = {
            "id": "poplar_cid_postcard_999",
            "name": "postcard - single send",
        }
        with patch.object(PhysicalMailService, "_get_active_client", return_value=mock_client):
            payload = {
                "workflow_mode": "connect",
                "poplar_campaign_id": "poplar_cid_postcard_999",
                "mailpiece_size": "6x9",
                "format_type": "postcard",
                "paper_type": "premium_coated",
                "postage_class": "usps_first_class",
                "creative_id": "a9c859f4-d1e9-4005-bbd1-16f744b7c944",
            }
            resp = client.post(f"/api/v1/campaigns/{campaign.id}/physical-mail/configure", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["mailpiece"]["format"] == "postcard"
            assert data["mailpiece"]["size"] == "6x9"
            assert data["unit_cost"] == 1.15
    finally:
        app.dependency_overrides.clear()
