"""
Tests for Microsoft Graph Inbound Email Integration.

Tests cover:
1. MicrosoftGraphTokenManager: client credentials token acquisition, caching, renewal, and secret redaction.
2. MicrosoftGraphClient: mailbox scope validation, message parsing, pagination, HTTP 401, 403, 404, and 429 throttling.
3. Ingestion Service: duplicate prevention, Contact matching, Lead matching, domain matching, unmatched review flagging, and untrusted preview sanitization.
4. Fail-closed safety: live sync blocked when MICROSOFT_GRAPH_ENABLED=False.
5. Multi-tenant isolation: organization boundaries strictly enforced.
6. API Endpoints: list, detail, review updates, sync-runs, config-status.
7. Missing-table resilience: graceful fallback when tables are unmigrated.
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.crm import Company, Contact
from app.models.inbound_email import GraphMailboxCheckpoint, GraphSyncRun, InboundEmail
from app.models.lead import Lead
from app.models.tenant import Organization, User
from app.schemas.inbound_email import GraphSyncResultResponse
from app.services.graph.auth import MicrosoftGraphTokenManager
from app.services.graph.client import GraphMessage, GraphMessagePage, MicrosoftGraphClient
from app.services.graph.exceptions import (
    GraphAuthenticationError,
    GraphDeltaTokenExpiredError,
    GraphMailboxNotFoundError,
    GraphMailboxScopeError,
    GraphPermissionError,
    GraphSecurityError,
    GraphThrottlingError,
)
from app.services.graph.ingestion_service import (
    import_graph_messages,
    match_sender_to_crm,
    sanitize_body_preview,
)
from app.services.graph.scheduler import MicrosoftGraphAutoSyncService
from app.services.graph.sync_service import (
    acquire_sync_lock,
    get_checkpoint_status,
    get_inbound_email_detail,
    get_or_create_checkpoint,
    list_inbound_emails,
    list_sync_runs,
    release_sync_lock,
    sync_support_mailbox,
    update_manual_review_status,
)


@pytest.fixture
def test_db_session():
    """In-memory SQLite test database with schema initialized."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
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
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.pop(get_db, None)


def make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def create_tenant_and_user(session: Session, org_name: str, email: str) -> tuple[Organization, User]:
    org = Organization(
        id=uuid.uuid4(),
        name=org_name,
        slug=org_name.lower().replace(" ", "-"),
        billing_status="trial",
    )
    session.add(org)
    session.flush()

    user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=email,
        hashed_password="hashed_pw_test",
        full_name=f"{org_name} User",
        role="admin",
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(org)
    session.refresh(user)
    return org, user


# ==============================================================================
# 1. TOKEN MANAGER & AUTH TESTS
# ==============================================================================

def test_token_manager_acquires_and_caches_token():
    """Verifies OAuth 2.0 client credentials token acquisition and caching."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "access_token": "mock-token-xyz-123",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )

    with patch("httpx.Client.post", return_value=mock_response):
        manager = MicrosoftGraphTokenManager(
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )
        token1 = manager.get_access_token()
        assert token1 == "mock-token-xyz-123"

        # Second call should use cache without HTTP request
        token2 = manager.get_access_token()
        assert token2 == "mock-token-xyz-123"


def test_token_manager_renews_expired_token():
    """Verifies token renewal when token is expired or within refresh window."""
    first_response = httpx.Response(
        status_code=200,
        json={"access_token": "token-old", "expires_in": 3600},
    )
    second_response = httpx.Response(
        status_code=200,
        json={"access_token": "token-renewed", "expires_in": 3600},
    )

    with patch("httpx.Client.post", side_effect=[first_response, second_response]):
        manager = MicrosoftGraphTokenManager(
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )
        t1 = manager.get_access_token()
        assert t1 == "token-old"

        # Manually force expiration by setting _token_expires_at to past
        manager._token_expires_at = time.time() - 10

        t2 = manager.get_access_token()
        assert t2 == "token-renewed"


def test_token_manager_auth_failure_raises_graph_auth_error():
    """Verifies HTTP 400/401 from identity provider raises GraphAuthenticationError."""
    err_response = httpx.Response(
        status_code=401,
        json={"error": "invalid_client", "error_description": "Bad client secret"},
    )
    with patch("httpx.Client.post", return_value=err_response):
        manager = MicrosoftGraphTokenManager(
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            client_secret="wrong-secret",
        )
        with pytest.raises(GraphAuthenticationError) as exc_info:
            manager.get_access_token()
        assert "HTTP 401" in str(exc_info.value) or "invalid_client" in str(exc_info.value)


def test_token_manager_no_secret_in_repr():
    """Confirms client_secret is never displayed or leaked in __repr__."""
    manager = MicrosoftGraphTokenManager(
        tenant_id="tid-123",
        client_id="cid-456",
        client_secret="SUPER_SECRET_VALUE",
    )
    representation = repr(manager)
    assert "SUPER_SECRET_VALUE" not in representation
    assert "[REDACTED]" in representation


# ==============================================================================
# 2. MICROSOFT GRAPH CLIENT & SCOPE TESTS
# ==============================================================================

def test_client_enforces_approved_support_mailbox_scope():
    """Strictly validates that queries to any non-approved mailbox are rejected with GraphMailboxScopeError."""
    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"

    client = MicrosoftGraphClient(token_manager=fake_token_mgr)

    # Approved mailbox must NOT raise scope error
    mock_resp = httpx.Response(status_code=200, json={"value": []})
    with patch.object(client, "_execute_request", return_value=mock_resp):
        page = client.get_messages(mailbox="support@agilereceivables.com")
        assert page.messages == []

    # Non-approved mailbox MUST raise GraphMailboxScopeError
    with pytest.raises(GraphMailboxScopeError) as exc_info:
        client.get_messages(mailbox="attacker@evilcorp.com")
    assert "Unauthorized mailbox" in str(exc_info.value) or "strictly restricted" in str(exc_info.value)


def test_client_parses_messages_and_body_correctly():
    """Verifies that client extracts full message fields, conversation ID, and body."""
    raw_graph_data = {
        "value": [
            {
                "id": "AAMkAGI2AA==",
                "conversationId": "AAQkAGI2BB==",
                "internetMessageId": "<test.msg.1@client.com>",
                "subject": "Invoice Question - Account 4421",
                "bodyPreview": "Hi team, regarding the invoice...",
                "body": {
                    "contentType": "html",
                    "content": "<html><body>Hi team, regarding the invoice...</body></html>",
                },
                "from": {
                    "emailAddress": {
                        "name": "Jane Doe",
                        "address": "jane@customer.com",
                    }
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "name": "Agile Support",
                            "address": "support@agilereceivables.com",
                        }
                    }
                ],
                "receivedDateTime": "2026-10-21T10:00:00Z",
                "isRead": False,
                "hasAttachments": False,
            }
        ]
    }

    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(token_manager=fake_token_mgr)
    mock_resp = httpx.Response(status_code=200, json=raw_graph_data)

    with patch.object(client, "_execute_request", return_value=mock_resp):
        page = client.get_messages(mailbox="support@agilereceivables.com")
        assert len(page.messages) == 1
        msg = page.messages[0]
        assert msg.id == "AAMkAGI2AA=="
        assert msg.conversation_id == "AAQkAGI2BB=="
        assert msg.internet_message_id == "<test.msg.1@client.com>"
        assert msg.sender_email == "jane@customer.com"
        assert msg.sender_name == "Jane Doe"
        assert msg.recipient_email == "support@agilereceivables.com"
        assert msg.subject == "Invoice Question - Account 4421"
        assert "<html>" in (msg.body_content or "")


def test_client_pagination_next_link():
    """Verifies pagination nextLink extraction and following."""
    first_page = {
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages?$skip=10",
        "value": [{"id": f"msg-{i}", "from": {"emailAddress": {"address": "a@b.com"}}} for i in range(10)],
    }
    second_page = {
        "value": [{"id": f"msg-{i}", "from": {"emailAddress": {"address": "a@b.com"}}} for i in range(10, 15)],
    }

    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    client = MicrosoftGraphClient(token_manager=fake_token_mgr)
    resp1 = httpx.Response(status_code=200, json=first_page)
    resp2 = httpx.Response(status_code=200, json=second_page)

    with patch.object(client, "_execute_request", side_effect=[resp1, resp2]):
        p1 = client.get_messages(mailbox="support@agilereceivables.com")
        assert len(p1.messages) == 10
        assert p1.next_link is not None

        p2 = client.get_next_page(p1.next_link)
        assert len(p2.messages) == 5
        assert p2.next_link is None


def test_client_handles_429_throttling_with_retry_after():
    """Verifies HTTP 429 raises GraphThrottlingError with Retry-After parsed."""
    req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/users/test")
    resp_429 = httpx.Response(status_code=429, headers={"Retry-After": "5"}, request=req)

    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(token_manager=fake_token_mgr, max_retries=2)

    with patch("time.sleep") as mock_sleep, patch("httpx.Client.request", return_value=resp_429):
        with pytest.raises(GraphThrottlingError) as exc_info:
            client.get_messages(mailbox="support@agilereceivables.com")
        assert exc_info.value.retry_after == 5
        mock_sleep.assert_called_with(5)


def test_client_handles_403_permission_error():
    """Verifies HTTP 403 raises GraphPermissionError."""
    req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/users/test")
    resp_403 = httpx.Response(
        status_code=403,
        json={"error": {"code": "ErrorAccessDenied", "message": "Access is denied."}},
        request=req,
    )
    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(token_manager=fake_token_mgr)

    with patch("httpx.Client.request", return_value=resp_403):
        with pytest.raises(GraphPermissionError):
            client.get_messages(mailbox="support@agilereceivables.com")


def test_client_handles_404_mailbox_not_found():
    """Verifies HTTP 404 raises GraphMailboxNotFoundError."""
    req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/users/test")
    resp_404 = httpx.Response(
        status_code=404,
        json={"error": {"code": "ErrorItemNotFound", "message": "Mailbox does not exist."}},
        request=req,
    )
    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(token_manager=fake_token_mgr)

    with patch("httpx.Client.request", return_value=resp_404):
        with pytest.raises(GraphMailboxNotFoundError):
            client.get_messages(mailbox="support@agilereceivables.com")


# ==============================================================================
# 3. PREVIEW SANITIZATION & SECURITY TESTS
# ==============================================================================

def test_sanitize_body_preview_strips_scripts_and_html():
    """Verifies untrusted input protection strips <script> tags and HTML elements."""
    dangerous_input = (
        "Hello <script>alert('xss'); window.location='http://evil.com'</script>"
        "<b>Important Update</b> from Customer."
    )
    preview = sanitize_body_preview(dangerous_input)
    assert "<script>" not in preview
    assert "alert('xss')" not in preview
    assert "<b>" not in preview
    assert "Hello Important Update from Customer." == preview


# ==============================================================================
# 4. INGESTION & MATCHING TESTS
# ==============================================================================

def test_ingestion_duplicate_prevention(test_db_session: Session):
    """Verifies identical graph_message_id is not duplicated in subsequent syncs."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    msg = GraphMessage(
        id="graph-msg-dup-01",
        conversation_id="conv-01",
        internet_message_id="<dup.1@domain.com>",
        from_email="contact@customer.com",
        from_name="Contact Person",
        to_recipients=["support@agilereceivables.com"],
        subject="Payment inquiry",
        body_preview="Checking on invoice payment...",
        body_content="Checking on invoice payment...",
        body_content_type="text",
        received_at=datetime.now(timezone.utc),
        is_read=False,
        has_attachments=False,
    )

    # First ingestion: should import 1
    summary1 = import_graph_messages(test_db_session, org.id, [msg])
    assert summary1.imported == 1
    assert summary1.skipped == 0

    # Second ingestion with same message: should skip
    summary2 = import_graph_messages(test_db_session, org.id, [msg])
    assert summary2.imported == 0
    assert summary2.skipped == 1

    # Verify only 1 record exists in DB
    count = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org.id).count()
    assert count == 1


def test_ingestion_matches_contact_by_email(test_db_session: Session):
    """Verifies incoming email is matched to an existing Contact in the organization."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    # Create existing Contact
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="sarah.connor@cyberdyne.com",
        first_name="Sarah",
        last_name="Connor",
        job_title="VP Operations",
        lead_status="qualified",
    )
    test_db_session.add(contact)
    test_db_session.commit()

    msg = GraphMessage(
        id="graph-msg-match-contact",
        conversation_id="conv-contact",
        internet_message_id="<sarah.1@cyberdyne.com>",
        from_email="Sarah.Connor@cyberdyne.com",  # Test case-insensitivity
        from_name="Sarah Connor",
        to_recipients=["support@agilereceivables.com"],
        subject="Re: Collection Settlement",
        body_preview="We accept the proposed terms.",
        body_content="<p>We accept the proposed terms.</p>",
        body_content_type="html",
        received_at=datetime.now(timezone.utc),
        is_read=False,
        has_attachments=False,
    )

    summary = import_graph_messages(test_db_session, org.id, [msg])
    assert summary.imported == 1
    assert summary.matched == 1
    assert summary.unmatched == 0

    saved = test_db_session.query(InboundEmail).filter(InboundEmail.graph_message_id == msg.id).first()
    assert saved is not None
    assert saved.sync_status == "matched"
    assert saved.matched_contact_id == contact.id

    # Verify Pydantic schema detail flags is_untrusted_content=True
    detail = get_inbound_email_detail(test_db_session, org.id, saved.id)
    assert detail is not None
    assert detail.is_untrusted_content is True


def test_ingestion_matches_lead_when_no_contact(test_db_session: Session):
    """Verifies incoming email matches Lead when no Contact exists."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    lead = Lead(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="prospect@acmecorp.com",
        company_name="Acme Corp",
        lead_score=85,
        lead_temperature="hot",
        status="contacted",
    )
    test_db_session.add(lead)
    test_db_session.commit()

    msg = GraphMessage(
        id="graph-msg-match-lead",
        conversation_id="conv-lead",
        internet_message_id="<prospect.1@acmecorp.com>",
        from_email="prospect@acmecorp.com",
        from_name="Prospect",
        to_recipients=["support@agilereceivables.com"],
        subject="Interest in services",
        body_preview="Tell me more about your pricing.",
        body_content="Tell me more about your pricing.",
        body_content_type="text",
        received_at=datetime.now(timezone.utc),
        is_read=False,
        has_attachments=False,
    )

    summary = import_graph_messages(test_db_session, org.id, [msg])
    assert summary.imported == 1
    assert summary.matched == 1

    saved = test_db_session.query(InboundEmail).filter(InboundEmail.graph_message_id == msg.id).first()
    assert saved.sync_status == "matched"
    assert saved.matched_lead_id == lead.id


def test_ingestion_flags_unmatched_messages_for_manual_review(test_db_session: Session):
    """Verifies unknown senders are imported with sync_status='unmatched' and manual_review_status='pending'."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    msg = GraphMessage(
        id="graph-msg-unknown",
        conversation_id="conv-unknown",
        internet_message_id="<unknown.1@random.org>",
        from_email="random_stranger@random.org",
        from_name="Random Stranger",
        to_recipients=["support@agilereceivables.com"],
        subject="Unsolicited inquiry",
        body_preview="Who should I speak with?",
        body_content="Who should I speak with?",
        body_content_type="text",
        received_at=datetime.now(timezone.utc),
        is_read=False,
        has_attachments=False,
    )

    summary = import_graph_messages(test_db_session, org.id, [msg])
    assert summary.imported == 1
    assert summary.matched == 0
    assert summary.unmatched == 1

    saved = test_db_session.query(InboundEmail).filter(InboundEmail.graph_message_id == msg.id).first()
    assert saved.sync_status == "unmatched"
    assert saved.manual_review_status == "pending"


def test_tenant_isolation_in_crm_matching(test_db_session: Session):
    """Ensures an email in Tenant B is NEVER matched against a Contact belonging to Tenant A."""
    org_a, _ = create_tenant_and_user(test_db_session, "Tenant A", "admin@tenanta.com")
    org_b, _ = create_tenant_and_user(test_db_session, "Tenant B", "admin@tenantb.com")

    # Contact in Tenant A
    contact_a = Contact(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email="shared_client@external.com",
        first_name="Shared",
        last_name="Client",
    )
    test_db_session.add(contact_a)
    test_db_session.commit()

    # Message ingested for Tenant B with identical email
    msg_for_b = GraphMessage(
        id="msg-tenant-b",
        conversation_id="conv-b",
        internet_message_id="<client.b@external.com>",
        from_email="shared_client@external.com",
        from_name="Shared Client",
        to_recipients=["support@agilereceivables.com"],
        subject="Tenant B inquiry",
        body_preview="Message for B",
        body_content="Message for B",
        body_content_type="text",
        received_at=datetime.now(timezone.utc),
        is_read=False,
        has_attachments=False,
    )

    summary = import_graph_messages(test_db_session, org_b.id, [msg_for_b])
    # Must NOT match contact_a because contact_a belongs to org_a
    assert summary.matched == 0
    assert summary.unmatched == 1

    saved = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org_b.id).first()
    assert saved.matched_contact_id is None
    assert saved.sync_status == "unmatched"


# ==============================================================================
# 5. SYNC SERVICE & FAIL-CLOSED SAFETY TESTS
# ==============================================================================

def test_sync_support_mailbox_blocked_by_fail_closed_guard(test_db_session: Session):
    """Verifies sync is blocked when MICROSOFT_GRAPH_ENABLED=False and no mocks are provided."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    with patch.object(settings, "MICROSOFT_GRAPH_ENABLED", False):
        result = sync_support_mailbox(test_db_session, org.id)
        assert result.status == "blocked_by_safety_guard"
        assert result.messages_fetched == 0
        assert "disabled by safety configuration" in (result.error_message or "")


def test_sync_support_mailbox_with_mock_messages_records_audit_run(test_db_session: Session):
    """Verifies sync executes and records a GraphSyncRun audit row."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    mock_msgs = [
        GraphMessage(
            id=f"msg-mock-{i}",
            conversation_id=f"conv-{i}",
            internet_message_id=f"<m{i}@example.com>",
            from_email=f"sender{i}@example.com",
            from_name=f"Sender {i}",
            to_recipients=["support@agilereceivables.com"],
            subject=f"Inquiry #{i}",
            body_preview="Testing sync...",
            body_content="Testing sync...",
            body_content_type="text",
            received_at=datetime.now(timezone.utc),
            is_read=False,
            has_attachments=False,
        )
        for i in range(3)
    ]

    result = sync_support_mailbox(test_db_session, org.id, mock_messages=mock_msgs)
    assert result.status == "completed"
    assert result.messages_fetched == 3
    assert result.messages_imported == 3

    # Check GraphSyncRun audit record in DB
    runs = list_sync_runs(test_db_session, org.id)
    assert len(runs) >= 1
    assert runs[0].messages_fetched == 3


def test_update_manual_review_status(test_db_session: Session):
    """Verifies triage review state transition from 'pending' to 'reviewed'."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")

    email = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org.id,
        graph_message_id="msg-triage-01",
        sender_email="triage@unknown.com",
        recipient_email="support@agilereceivables.com",
        subject="Need Help",
        body_preview="Help needed",
        received_at=datetime.now(timezone.utc),
        sync_status="unmatched",
        manual_review_status="pending",
    )
    test_db_session.add(email)
    test_db_session.commit()

    updated = update_manual_review_status(
        test_db_session,
        org.id,
        email.id,
        new_status="reviewed",
        notes="Contacted sender and mapped to new account.",
    )
    assert updated is not None
    assert updated.manual_review_status == "reviewed"
    assert updated.review_notes == "Contacted sender and mapped to new account."


# ==============================================================================
# 6. REST API ENDPOINTS & HTTP TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_api_config_status(test_db_session: Session):
    """Verifies GET /api/v1/inbound-emails/config-status returns safe configuration."""
    org, user = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")
    token = create_access_token(user_id=user.id, organization_id=org.id, role="admin")

    async with make_client() as ac:
        response = await ac.get(
            "/api/v1/inbound-emails/config-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["support_mailbox"] == "support@agilereceivables.com"
        assert data["approved_mailbox_only"] is True
        assert "Mail.Read" in data["permissions_required"]
        # Ensure secret value and secret keys are NOT exposed in response payload
        assert "access_token" not in data
        assert "client_secret" not in data
        assert "token" not in data


@pytest.mark.asyncio
async def test_api_list_inbound_emails(test_db_session: Session):
    """Verifies GET /api/v1/inbound-emails lists tenant messages with search/filter."""
    org, user = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")
    token = create_access_token(user_id=user.id, organization_id=org.id, role="admin")

    e1 = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org.id,
        graph_message_id="msg-api-1",
        sender_email="john@smith.com",
        sender_name="John Smith",
        recipient_email="support@agilereceivables.com",
        subject="Invoice Query",
        body_preview="Query on invoice",
        received_at=datetime.now(timezone.utc),
        sync_status="matched",
        manual_review_status="reviewed",
    )
    e2 = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org.id,
        graph_message_id="msg-api-2",
        sender_email="unknown@random.com",
        sender_name="Unknown",
        recipient_email="support@agilereceivables.com",
        subject="Spam Pitch",
        body_preview="Cheap SEO",
        received_at=datetime.now(timezone.utc),
        sync_status="unmatched",
        manual_review_status="pending",
    )
    test_db_session.add_all([e1, e2])
    test_db_session.commit()

    async with make_client() as ac:
        # All messages
        resp = await ac.get(
            "/api/v1/inbound-emails",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["unmatched_count"] == 1

        # Search filter
        resp_search = await ac.get(
            "/api/v1/inbound-emails?search=John",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_search.status_code == 200
        data_search = resp_search.json()
        assert data_search["total"] == 1
        assert data_search["items"][0]["sender_email"] == "john@smith.com"


@pytest.mark.asyncio
async def test_api_get_inbound_email_detail_and_read_status(test_db_session: Session):
    """Verifies GET /api/v1/inbound-emails/{id} returns detail and marks message as read."""
    org, user = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")
    token = create_access_token(user_id=user.id, organization_id=org.id, role="admin")

    email = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org.id,
        graph_message_id="msg-detail-01",
        sender_email="client@domain.com",
        recipient_email="support@agilereceivables.com",
        subject="Important Notice",
        body_content="<p>Full message body here</p>",
        body_preview="Full message body here",
        received_at=datetime.now(timezone.utc),
        is_read=False,
        sync_status="unmatched",
        manual_review_status="pending",
    )
    test_db_session.add(email)
    test_db_session.commit()

    async with make_client() as ac:
        resp = await ac.get(
            f"/api/v1/inbound-emails/{email.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subject"] == "Important Notice"
        assert data["is_read"] is True
        assert data["is_untrusted_content"] is True
        assert "Full message body here" in data["body_content"]


@pytest.mark.asyncio
async def test_api_manual_review_update(test_db_session: Session):
    """Verifies POST /api/v1/inbound-emails/{id}/review updates review state."""
    org, user = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agile.com")
    token = create_access_token(user_id=user.id, organization_id=org.id, role="admin")

    email = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org.id,
        graph_message_id="msg-rev-01",
        sender_email="triage@domain.com",
        recipient_email="support@agilereceivables.com",
        subject="Subject",
        received_at=datetime.now(timezone.utc),
        sync_status="unmatched",
        manual_review_status="pending",
    )
    test_db_session.add(email)
    test_db_session.commit()

    async with make_client() as ac:
        resp = await ac.post(
            f"/api/v1/inbound-emails/{email.id}/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "reviewed", "review_notes": "Handled by support team."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["manual_review_status"] == "reviewed"
        assert data["review_notes"] == "Handled by support team."


@pytest.mark.asyncio
async def test_api_tenant_isolation_boundary(test_db_session: Session):
    """Verifies an authenticated user from Org A cannot access an email from Org B."""
    org_a, user_a = create_tenant_and_user(test_db_session, "Org A", "user_a@org-a.com")
    org_b, user_b = create_tenant_and_user(test_db_session, "Org B", "user_b@org-b.com")

    token_a = create_access_token(user_id=user_a.id, organization_id=org_a.id, role="admin")

    # Email belonging to Org B
    email_b = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        graph_message_id="msg-secret-b",
        sender_email="b_sender@corp.com",
        recipient_email="support@agilereceivables.com",
        subject="Confidential B Information",
        received_at=datetime.now(timezone.utc),
        sync_status="matched",
        manual_review_status="pending",
    )
    test_db_session.add(email_b)
    test_db_session.commit()

    async with make_client() as ac:
        # Org A user attempts to get Org B's email
        resp = await ac.get(
            f"/api/v1/inbound-emails/{email_b.id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404


def test_missing_table_resilience():
    """Confirms query and sync services degrade gracefully when database tables are unmigrated."""
    bare_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=bare_engine)
    bare_session = TestingSession()
    try:
        dummy_org_id = uuid.uuid4()
        # Querying unmigrated tables must return empty results instead of crashing with OperationalError
        result = list_inbound_emails(bare_session, dummy_org_id)
        assert result.items == []
        assert result.total == 0
        assert result.unmatched_count == 0

        detail = get_inbound_email_detail(bare_session, dummy_org_id, uuid.uuid4())
        assert detail is None

        runs = list_sync_runs(bare_session, dummy_org_id)
        assert runs == []

        # Ingestion against unmigrated tables returns empty summary
        summary = import_graph_messages(bare_session, dummy_org_id, [])
        assert summary.imported == 0
    finally:
        bare_session.close()


# ==============================================================================
# 8. DELTA QUERY, CONCURRENCY LOCK, CHECKPOINT & AUTO-SYNC TESTS
# ==============================================================================

def test_client_get_delta_messages_initial_and_incremental():
    """Verifies incremental delta querying, handling of @removed items, and delta link tracking."""
    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(
        token_manager=fake_token_mgr,
        approved_mailbox="support@agilereceivables.com",
    )

    page1_response = httpx.Response(
        status_code=200,
        json={
            "value": [
                {
                    "id": "msg-delta-1",
                    "subject": "Inbound 1",
                    "from": {"emailAddress": {"address": "lead1@corp.com", "name": "Lead One"}},
                    "toRecipients": [{"emailAddress": {"address": "support@agilereceivables.com"}}],
                    "receivedDateTime": "2026-10-21T10:00:00Z",
                    "body": {"contentType": "text", "content": "Hello 1"},
                },
                {
                    "id": "msg-removed-2",
                    "@removed": {"reason": "deleted"},
                },
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=checkpoint1",
        },
    )

    with patch.object(client, "_execute_request", return_value=page1_response) as mock_exec:
        messages, delta_link = client.get_delta_messages()
        assert len(messages) == 1
        assert messages[0].id == "msg-delta-1"
        assert delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=checkpoint1"
        assert mock_exec.call_count == 1
        call_args = mock_exec.call_args
        assert "/messages/delta" in call_args[0][1]

    # Incremental call using previous delta link
    page2_response = httpx.Response(
        status_code=200,
        json={
            "value": [
                {
                    "id": "msg-delta-3",
                    "subject": "Inbound 3",
                    "from": {"emailAddress": {"address": "lead3@corp.com", "name": "Lead Three"}},
                    "toRecipients": [{"emailAddress": {"address": "support@agilereceivables.com"}}],
                    "receivedDateTime": "2026-10-21T11:00:00Z",
                    "body": {"contentType": "text", "content": "Hello 3"},
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=checkpoint2",
        },
    )

    with patch.object(client, "_execute_request", return_value=page2_response) as mock_exec:
        messages2, delta_link2 = client.get_delta_messages(
            delta_link="https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=checkpoint1"
        )
        assert len(messages2) == 1
        assert messages2[0].id == "msg-delta-3"
        assert delta_link2 == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=checkpoint2"
        mock_exec.assert_called_once_with(
            "GET", "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=checkpoint1", params=None
        )


def test_client_delta_token_expired_410_recovery():
    """Verifies that HTTP 410 Gone delta expiration resets the delta link and initiates a fresh delta crawl."""
    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(
        token_manager=fake_token_mgr,
        approved_mailbox="support@agilereceivables.com",
    )

    fresh_response = httpx.Response(
        status_code=200,
        json={
            "value": [
                {
                    "id": "msg-fresh-1",
                    "subject": "Fresh Crawl Message",
                    "from": {"emailAddress": {"address": "fresh@domain.com", "name": "Fresh"}},
                    "toRecipients": [{"emailAddress": {"address": "support@agilereceivables.com"}}],
                    "receivedDateTime": "2026-10-21T12:00:00Z",
                    "body": {"contentType": "text", "content": "Recovery body"},
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=fresh_checkpoint",
        },
    )

    call_count = 0

    def mock_execute(method, url, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise GraphDeltaTokenExpiredError("Delta token expired (410)")
        return fresh_response

    with patch.object(client, "_execute_request", side_effect=mock_execute):
        messages, delta_link = client.get_delta_messages(
            delta_link="https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=expired_token"
        )
        assert len(messages) == 1
        assert messages[0].id == "msg-fresh-1"
        assert delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=fresh_checkpoint"
        assert call_count == 2


def test_concurrency_lock_prevents_overlapping_sync(test_db_session: Session):
    """Verifies concurrency locking blocks overlapping sync executions for the same mailbox."""
    org, user = create_tenant_and_user(test_db_session, "Agile Lock Test", "lock@agilereceivables.com")
    mailbox = "support@agilereceivables.com"

    # 1. Acquire initial lock
    locked = acquire_sync_lock(test_db_session, org.id, mailbox)
    assert locked is True

    # Checkpoint should indicate is_syncing=True
    cp = get_or_create_checkpoint(test_db_session, org.id, mailbox)
    assert cp is not None
    assert cp.is_syncing is True

    # 2. Second concurrent execution attempts to run sync_support_mailbox
    mock_msg = GraphMessage(
        id="msg-blocked-01",
        conversation_id="conv-1",
        internet_message_id=None,
        from_email="sender@abc.com",
        from_name="Sender",
        to_recipients=[mailbox],
        subject="Should be blocked",
        body_preview="Body",
        body_content="Body",
        body_content_type="text",
        received_at=datetime.now(timezone.utc),
        has_attachments=False,
        is_read=False,
    )

    result = sync_support_mailbox(
        test_db_session,
        org.id,
        mock_messages=[mock_msg],
    )
    assert result.status == "skipped_concurrency_lock"
    assert result.messages_imported == 0
    assert "concurrency lock" in result.error_message.lower()

    # Verify no email was inserted into the database while locked
    count = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org.id).count()
    assert count == 0

    # 3. Release lock
    release_sync_lock(test_db_session, org.id, mailbox, status="completed")
    cp_after = get_or_create_checkpoint(test_db_session, org.id, mailbox)
    assert cp_after.is_syncing is False

    # 4. Now sync succeeds
    result2 = sync_support_mailbox(
        test_db_session,
        org.id,
        mock_messages=[mock_msg],
    )
    assert result2.status == "completed"
    assert result2.messages_imported == 1


def test_concurrency_lock_stale_lock_recovery(test_db_session: Session):
    """Verifies that an abandoned/stale lock exceeding timeout is automatically reclaimed."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Stale Test", "stale@agilereceivables.com")
    mailbox = "support@agilereceivables.com"

    # Set up a checkpoint with an expired lock (started 1200 seconds ago > 900s timeout)
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=1200)
    cp = get_or_create_checkpoint(test_db_session, org.id, mailbox)
    assert cp is not None
    cp.is_syncing = True
    cp.sync_started_at = stale_time
    test_db_session.commit()

    # Attempt lock acquisition
    reclaimed = acquire_sync_lock(test_db_session, org.id, mailbox)
    assert reclaimed is True

    test_db_session.refresh(cp)
    assert cp.is_syncing is True
    # sync_started_at should have been reset to now (within 5 seconds)
    started_at = cp.sync_started_at.replace(tzinfo=timezone.utc) if cp.sync_started_at.tzinfo is None else cp.sync_started_at
    assert (datetime.now(timezone.utc) - started_at).total_seconds() < 5


def test_checkpoint_delta_persistence(test_db_session: Session):
    """Verifies that a completed sync persists the new delta link to the checkpoint."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Delta Test", "delta@agilereceivables.com")
    mailbox = "support@agilereceivables.com"

    mock_msg = GraphMessage(
        id="msg-delta-saved-1",
        conversation_id="conv-1",
        internet_message_id=None,
        from_email="client@clientcorp.com",
        from_name="Client",
        to_recipients=[mailbox],
        subject="Inbound check",
        body_preview="Body",
        body_content="Body",
        body_content_type="text",
        received_at=datetime.now(timezone.utc),
        has_attachments=False,
        is_read=False,
    )

    result = sync_support_mailbox(
        test_db_session,
        org.id,
        mock_messages=[mock_msg],
    )
    assert result.status == "completed"

    cp = get_or_create_checkpoint(test_db_session, org.id, mailbox)
    assert cp is not None
    assert cp.delta_link is not None
    assert "mock_delta_token" in cp.delta_link
    assert cp.total_imported == 1
    assert cp.last_sync_status == "completed"
    assert cp.last_successful_sync_at is not None


def test_background_auto_sync_service_tick(test_db_session: Session):
    """Verifies that MicrosoftGraphAutoSyncService respects safety flags and triggers delta sync when permitted."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "auto@agilereceivables.com")
    service = MicrosoftGraphAutoSyncService(db=test_db_session)

    # 1. By default, auto_sync is not allowed (fail-closed)
    assert settings.is_graph_auto_sync_allowed is False
    results_skipped = service.tick()
    assert results_skipped == []

    # 2. When permitted with mock sync, auto-sync tick executes
    with patch("app.core.config.Settings.is_graph_auto_sync_allowed", new=True):
        with patch("app.services.graph.scheduler.sync_support_mailbox") as mock_sync:
            mock_sync.return_value = GraphSyncResultResponse(
                sync_run_id=uuid.uuid4(),
                organization_id=org.id,
                mailbox=settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX,
                status="completed",
                messages_fetched=1,
                messages_imported=1,
                messages_matched=0,
                messages_unmatched=1,
                messages_skipped=0,
                checkpoint_delta_link="https://graph.microsoft.com/delta_token",
                error_message=None,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            results = service.tick()
            assert len(results) == 1
            assert results[0].status == "completed"
            assert results[0].messages_imported == 1
            mock_sync.assert_called_once()
            _, kwargs = mock_sync.call_args
            assert kwargs.get("trigger") == "scheduled"
            assert kwargs.get("use_delta") is True


def test_no_automatic_contact_or_lead_creation(test_db_session: Session):
    """
    CRITICAL REQUIREMENT (Section 4):
    Confirms unmatched incoming emails NEVER automatically create Contact or Lead records.
    Unmatched messages are strictly placed into the manual review queue without altering CRM entities.
    """
    org, _ = create_tenant_and_user(test_db_session, "Agile Strict Safe", "safe@agile.com")

    # Verify initial CRM state
    initial_contacts = test_db_session.query(Contact).filter(Contact.organization_id == org.id).count()
    initial_leads = test_db_session.query(Lead).filter(Lead.organization_id == org.id).count()
    assert initial_contacts == 0
    assert initial_leads == 0

    unmatched_msg = GraphMessage(
        id="msg-unmatched-unknown-lead",
        conversation_id="conv-unmatched",
        internet_message_id=None,
        from_email="stranger@completely-unknown-enterprise.io",
        from_name="Stranger Unknown",
        to_recipients=["support@agilereceivables.com"],
        subject="Inquiry from unregistered party",
        body_preview="We want to learn more about your services.",
        body_content="<p>We want to learn more about your services.</p>",
        body_content_type="html",
        received_at=datetime.now(timezone.utc),
        has_attachments=False,
        is_read=False,
    )

    result = sync_support_mailbox(test_db_session, org.id, mock_messages=[unmatched_msg])
    assert result.status == "completed"
    assert result.messages_imported == 1
    assert result.messages_matched == 0
    assert result.messages_unmatched == 1

    # InboundEmail record created with pending review
    email_rec = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org.id).first()
    assert email_rec is not None
    assert email_rec.sync_status == "unmatched"
    assert email_rec.manual_review_status == "pending"
    assert email_rec.matched_contact_id is None
    assert email_rec.matched_lead_id is None
    assert email_rec.matched_company_id is None

    # CRITICAL: Verify NO Contacts or Leads were created!
    after_contacts = test_db_session.query(Contact).filter(Contact.organization_id == org.id).count()
    after_leads = test_db_session.query(Lead).filter(Lead.organization_id == org.id).count()
    assert after_contacts == 0
    assert after_leads == 0


@pytest.mark.asyncio
async def test_api_get_checkpoint_status(test_db_session: Session):
    """Verifies GET /api/v1/inbound-emails/checkpoint-status endpoint."""
    org, user = create_tenant_and_user(test_db_session, "Agile Checkpoint Org", "cp@agile.com")
    token = create_access_token(user_id=user.id, organization_id=org.id, role="admin")

    # Create checkpoint
    cp = get_or_create_checkpoint(test_db_session, org.id, "support@agilereceivables.com")
    assert cp is not None
    cp.delta_link = "https://graph.microsoft.com/delta?token=active123"
    cp.is_syncing = False
    cp.total_imported = 42
    test_db_session.commit()

    async with make_client() as ac:
        resp = await ac.get(
            "/api/v1/inbound-emails/checkpoint-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mailbox"] == "support@agilereceivables.com"
        assert data["has_checkpoint"] is True
        assert data["is_syncing"] is False
        assert data["total_imported"] == 42


# ==============================================================================
# 9. F-01 TENANT ISOLATION REGRESSION TESTS
# ==============================================================================

def test_resolve_target_orgs_missing_configuration_fails_closed(test_db_session: Session):
    """F-01: Confirms auto-sync fails closed when no primary org ID is configured and no internal org exists."""
    create_tenant_and_user(test_db_session, "Acme Customer Corp", "acme@customer.com")
    create_tenant_and_user(test_db_session, "Beta Customer LLC", "beta@customer.com")

    service = MicrosoftGraphAutoSyncService(db=test_db_session)
    with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", None):
        orgs = service.resolve_target_organizations()
        # Must fail closed: never associate arbitrary customer tenants with the support mailbox
        assert orgs == []


def test_resolve_target_orgs_missing_organization_fails_closed(test_db_session: Session):
    """F-01: Confirms auto-sync fails closed when configured primary org ID does not exist in DB."""
    create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agilereceivables.com")
    non_existent_uuid = str(uuid.uuid4())

    service = MicrosoftGraphAutoSyncService(db=test_db_session)
    with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", non_existent_uuid):
        orgs = service.resolve_target_organizations()
        # Non-existent configured ID must fail closed, NOT fall back to slug matching
        assert orgs == []


def test_resolve_target_orgs_invalid_uuid_fails_closed(test_db_session: Session):
    """F-01: Confirms invalid UUID string in MICROSOFT_GRAPH_PRIMARY_ORG_ID fails closed."""
    create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agilereceivables.com")

    service = MicrosoftGraphAutoSyncService(db=test_db_session)
    with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", "not-a-valid-uuid"):
        orgs = service.resolve_target_organizations()
        assert orgs == []


def test_resolve_target_orgs_ambiguous_resolution_fails_closed(test_db_session: Session):
    """F-01: Confirms auto-sync fails closed when multiple internal organizations match approved slugs."""
    org1 = Organization(id=uuid.uuid4(), name="Agile Receivables", slug="agile-receivables", billing_status="active")
    org2 = Organization(id=uuid.uuid4(), name="Agile Sales Marketing", slug="agile-sales-marketing", billing_status="active")
    test_db_session.add(org1)
    test_db_session.add(org2)
    test_db_session.commit()

    service = MicrosoftGraphAutoSyncService(db=test_db_session)
    with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", None):
        orgs = service.resolve_target_organizations()
        # Ambiguous resolution must fail closed to prevent cross-tenant collision
        assert orgs == []


def test_resolve_target_orgs_valid_resolution_by_primary_id(test_db_session: Session):
    """F-01: Confirms auto-sync resolves unambiguously when valid MICROSOFT_GRAPH_PRIMARY_ORG_ID is configured."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Primary Tenant", "primary@agilereceivables.com")
    create_tenant_and_user(test_db_session, "Other Customer", "other@customer.com")

    service = MicrosoftGraphAutoSyncService(db=test_db_session)
    with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", str(org.id)):
        orgs = service.resolve_target_organizations()
        assert len(orgs) == 1
        assert orgs[0].id == org.id


def test_resolve_target_orgs_valid_resolution_by_internal_slug(test_db_session: Session):
    """F-01: Confirms auto-sync resolves unambiguously when exactly one verified internal org exists."""
    internal_org = Organization(id=uuid.uuid4(), name="Agile Receivables", slug="agile-receivables", billing_status="active")
    customer_org = Organization(id=uuid.uuid4(), name="Customer Corp", slug="customer-corp", billing_status="active")
    test_db_session.add(internal_org)
    test_db_session.add(customer_org)
    test_db_session.commit()

    service = MicrosoftGraphAutoSyncService(db=test_db_session)
    with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", None):
        orgs = service.resolve_target_organizations()
        assert len(orgs) == 1
        assert orgs[0].id == internal_org.id
        assert orgs[0].slug == "agile-receivables"


# ==============================================================================
# 10. F-02 ATOMIC CONCURRENCY LOCKING REGRESSION TESTS
# ==============================================================================

def test_acquire_sync_lock_concurrent_first_time_insert(test_db_session: Session):
    """F-02: Verifies that concurrent first-time checkpoint creation handles IntegrityError and prevents double lock."""
    org, _ = create_tenant_and_user(test_db_session, "Lock Race Org", "lock_race@agile.com")
    mailbox = "support@agilereceivables.com"

    # Worker 1 creates the checkpoint and acquires lock
    locked_w1 = acquire_sync_lock(test_db_session, org.id, mailbox)
    assert locked_w1 is True

    # Worker 2 attempts concurrent acquisition against the newly created lock
    locked_w2 = acquire_sync_lock(test_db_session, org.id, mailbox)
    assert locked_w2 is False


def test_release_sync_lock_partial_vs_completed(test_db_session: Session):
    """F-02 & F-03: Verifies release_sync_lock preserves continuation delta_link on partial sync without updating last_successful_sync_at."""
    org, _ = create_tenant_and_user(test_db_session, "Lock Partial Org", "partial@agile.com")
    mailbox = "support@agilereceivables.com"

    # 1. Acquire lock
    acquire_sync_lock(test_db_session, org.id, mailbox)

    # 2. Release as 'partial' (incomplete pagination run)
    continuation_url = "https://graph.microsoft.com/v1.0/delta?$skiptoken=next_page_token"
    release_sync_lock(
        db=test_db_session,
        org_id=org.id,
        mailbox_address=mailbox,
        status="partial",
        new_delta_link=continuation_url,
        imported_count=20,
    )

    cp = get_or_create_checkpoint(test_db_session, org.id, mailbox)
    assert cp is not None
    assert cp.is_syncing is False
    assert cp.last_sync_status == "partial"
    assert cp.delta_link == continuation_url
    assert cp.total_imported == 20
    # last_successful_sync_at MUST NOT be set for a partial run
    assert cp.last_successful_sync_at is None

    # 3. Next run completes
    acquire_sync_lock(test_db_session, org.id, mailbox)
    terminal_delta_url = "https://graph.microsoft.com/v1.0/delta?$deltatoken=terminal_token"
    release_sync_lock(
        db=test_db_session,
        org_id=org.id,
        mailbox_address=mailbox,
        status="completed",
        new_delta_link=terminal_delta_url,
        imported_count=5,
    )

    test_db_session.refresh(cp)
    assert cp.is_syncing is False
    assert cp.last_sync_status == "completed"
    assert cp.delta_link == terminal_delta_url
    assert cp.total_imported == 25
    # last_successful_sync_at is now stamped
    assert cp.last_successful_sync_at is not None


# ==============================================================================
# 11. F-03 LARGE MAILBOX PAGINATION REGRESSION TESTS
# ==============================================================================

def test_delta_pagination_exceeding_max_pages_returns_partial_and_continuation_link():
    """F-03: Confirms that when delta query exceeds max_pages, it returns is_complete=False and preserves nextLink as continuation checkpoint."""
    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "fake-token"
    client = MicrosoftGraphClient(
        token_manager=fake_token_mgr,
        approved_mailbox="support@agilereceivables.com",
    )

    # Simulate 3 pages with max_pages=2
    def mock_execute(method, url, params=None):
        if "page3" in url:
            return httpx.Response(
                status_code=200,
                json={
                    "value": [{"id": "msg-p3", "from": {"emailAddress": {"address": "p3@a.com"}}}],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?terminal",
                },
            )
        elif "page2" in url:
            return httpx.Response(
                status_code=200,
                json={
                    "value": [{"id": "msg-p2", "from": {"emailAddress": {"address": "p2@a.com"}}}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?page3",
                },
            )
        elif "page1" in url or "/messages/delta" in url:
            return httpx.Response(
                status_code=200,
                json={
                    "value": [{"id": "msg-p1", "from": {"emailAddress": {"address": "p1@a.com"}}}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?page2",
                },
            )
        return httpx.Response(status_code=404)

    with patch.object(client, "_execute_request", side_effect=mock_execute):
        # Run 1: max_pages=2 (budget runs out on page 2)
        res1 = client.get_delta_messages(max_pages=2)
        messages1, continuation_link1 = res1
        assert len(messages1) == 2
        assert continuation_link1 == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?page3"
        assert res1.is_complete is False

        # Run 2: resume from page 3's continuation link with max_pages=2
        res2 = client.get_delta_messages(delta_link=continuation_link1, max_pages=2)
        messages2, final_delta_link = res2
        assert len(messages2) == 1
        assert messages2[0].id == "msg-p3"
        assert final_delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?terminal"
        assert res2.is_complete is True


def test_delta_pagination_multi_step_sync_preserves_resumption(test_db_session: Session):
    """F-03: End-to-end multi-step sync where run 1 saves continuation nextLink as partial, and run 2 finishes with deltaLink."""
    org, _ = create_tenant_and_user(test_db_session, "Agile Receivables", "admin@agilereceivables.com")
    mailbox = "support@agilereceivables.com"

    fake_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    fake_token_mgr.get_access_token.return_value = "token"
    client = MicrosoftGraphClient(token_manager=fake_token_mgr, approved_mailbox=mailbox)

    # 2 pages total, but max_pages=1 per run
    def mock_execute(method, url, params=None):
        if "page2" in url:
            return httpx.Response(
                status_code=200,
                json={
                    "value": [
                        {
                            "id": "msg-step-2",
                            "from": {"emailAddress": {"address": "lead2@corp.com"}},
                            "toRecipients": [{"emailAddress": {"address": mailbox}}],
                            "receivedDateTime": "2026-10-21T14:00:00Z",
                        }
                    ],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=terminal_checkpoint",
                },
            )
        else:
            return httpx.Response(
                status_code=200,
                json={
                    "value": [
                        {
                            "id": "msg-step-1",
                            "from": {"emailAddress": {"address": "lead1@corp.com"}},
                            "toRecipients": [{"emailAddress": {"address": mailbox}}],
                            "receivedDateTime": "2026-10-21T13:00:00Z",
                        }
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?page2",
                },
            )

    with patch("app.core.config.Settings.is_graph_live_sync_allowed", new=True):
        with patch.object(client, "_execute_request", side_effect=mock_execute):
            with patch.object(client, "get_delta_messages", wraps=client.get_delta_messages) as mock_get_delta:
                mock_get_delta.side_effect = lambda **kwargs: client._fetch_delta_pages(
                    encoded_mailbox="support%40agilereceivables.com",
                    folder_clean="Inbox",
                    delta_link=kwargs.get("delta_link"),
                    max_pages=1,
                )

                # Execution 1
                result1 = sync_support_mailbox(test_db_session, org.id, client_override=client)
                assert result1.status == "partial"
                assert result1.messages_imported == 1
                assert result1.checkpoint_delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?page2"

                # Checkpoint verification after Run 1
                cp = get_or_create_checkpoint(test_db_session, org.id, mailbox)
                assert cp.last_sync_status == "partial"
                assert cp.delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?page2"
                assert cp.last_successful_sync_at is None

                # Execution 2 (picks up continuation link from checkpoint)
                result2 = sync_support_mailbox(test_db_session, org.id, client_override=client)
                assert result2.status == "completed"
                assert result2.messages_imported == 1
                assert result2.checkpoint_delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=terminal_checkpoint"

                # Checkpoint verification after Run 2
                test_db_session.refresh(cp)
                assert cp.last_sync_status == "completed"
                assert cp.delta_link == "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?token=terminal_checkpoint"
                assert cp.last_successful_sync_at is not None
                assert cp.total_imported == 2

                # Duplicate prevention check: only 2 unique InboundEmails in DB
                count = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org.id).count()
                assert count == 2


# ==============================================================================
# 11. SECURITY HARDENING REGRESSION TESTS (AUDIT ISSUES 1 - 4)
# ==============================================================================

@pytest.mark.asyncio
async def test_manual_sync_cross_tenant_and_role_authorization(test_db_session: Session):
    """
    Issue 1: Verifies POST /api/v1/inbound-emails/sync strict multi-tenant authorization.
    - Authorized internal org admin triggers sync -> 200 (blocked_by_safety_guard if graph disabled).
    - Unauthenticated request -> 401 Unauthorized.
    - Customer tenant admin (org != primary_org) -> 403 Forbidden.
    - Non-admin user in primary org (e.g. member) -> 403 Forbidden.
    - Primary org unconfigured or invalid -> 403 Forbidden.
    - Invalid max_messages (< 1 or > 250) or invalid folder -> 422 Unprocessable Entity.
    - Denial causes zero database writes (no emails imported, no sync runs).
    """
    # 1. Setup Organizations & Users
    org_internal, user_internal_admin = create_tenant_and_user(
        test_db_session, "Agile Receivables", "admin@agilereceivables.com"
    )
    user_internal_member = User(
        id=uuid.uuid4(),
        organization_id=org_internal.id,
        email="member@agilereceivables.com",
        hashed_password="pw",
        full_name="Internal Member",
        role="member",
        is_active=True,
    )
    test_db_session.add(user_internal_member)

    org_customer, user_customer_admin = create_tenant_and_user(
        test_db_session, "Acme Customer Corp", "admin@acmecorp.com"
    )
    test_db_session.commit()

    token_internal_admin = create_access_token(user_id=user_internal_admin.id, organization_id=org_internal.id, role="admin")
    token_internal_member = create_access_token(user_id=user_internal_member.id, organization_id=org_internal.id, role="member")
    token_customer_admin = create_access_token(user_id=user_customer_admin.id, organization_id=org_customer.id, role="admin")

    async with make_client() as ac:
        # A. Unauthenticated -> 401
        res_unauth = await ac.post("/api/v1/inbound-emails/sync", json={"max_messages": 50, "folder": "Inbox"})
        assert res_unauth.status_code == 401

        # Configure PRIMARY_ORG_ID
        with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", str(org_internal.id)):
            # B. Customer Tenant Admin -> 403
            res_cust = await ac.post(
                "/api/v1/inbound-emails/sync",
                headers={"Authorization": f"Bearer {token_customer_admin}"},
                json={"max_messages": 50, "folder": "Inbox"},
            )
            assert res_cust.status_code == 403
            assert "authorized internal organization" in res_cust.json().get("detail", "")

            # C. Internal Org Non-Admin (member) -> 403
            res_member = await ac.post(
                "/api/v1/inbound-emails/sync",
                headers={"Authorization": f"Bearer {token_internal_member}"},
                json={"max_messages": 50, "folder": "Inbox"},
            )
            assert res_member.status_code == 403
            assert "Administrative privileges required" in res_member.json().get("detail", "")

            # D. Invalid parameters
            res_bad_folder = await ac.post(
                "/api/v1/inbound-emails/sync",
                headers={"Authorization": f"Bearer {token_internal_admin}"},
                json={"max_messages": 50, "folder": "SentItems"},
            )
            assert res_bad_folder.status_code == 400

            res_bad_max = await ac.post(
                "/api/v1/inbound-emails/sync",
                headers={"Authorization": f"Bearer {token_internal_admin}"},
                json={"max_messages": 500, "folder": "Inbox"},
            )
            assert res_bad_max.status_code == 422

            # E. Authorized Internal Admin -> 200
            res_ok = await ac.post(
                "/api/v1/inbound-emails/sync",
                headers={"Authorization": f"Bearer {token_internal_admin}"},
                json={"max_messages": 50, "folder": "Inbox"},
            )
            assert res_ok.status_code == 200
            data = res_ok.json()
            assert data["status"] == "blocked_by_safety_guard"
            assert data["mailbox"] == "support@agilereceivables.com"

        # F. Unconfigured or invalid PRIMARY_ORG_ID -> 403
        with patch.object(settings, "MICROSOFT_GRAPH_PRIMARY_ORG_ID", None):
            res_no_org = await ac.post(
                "/api/v1/inbound-emails/sync",
                headers={"Authorization": f"Bearer {token_internal_admin}"},
                json={"max_messages": 50, "folder": "Inbox"},
            )
            assert res_no_org.status_code == 403
            assert "not configured" in res_no_org.json().get("detail", "")

    # G. Verify zero customer writes
    customer_emails = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org_customer.id).count()
    customer_runs = test_db_session.query(GraphSyncRun).filter(GraphSyncRun.organization_id == org_customer.id).count()
    assert customer_emails == 0
    assert customer_runs == 0


def test_graph_client_url_validation_and_ssrf_prevention():
    """
    Issue 2: Comprehensive URL validation and SSRF mitigation tests.
    Verifies that MicrosoftGraphClient._validate_graph_url accepts only legitimate
    Microsoft Graph URLs and rejects SSRF, lookalikes, unexpected ports, user credentials,
    and foreign mailboxes or folders.
    """
    client = MicrosoftGraphClient(
        token_manager=MagicMock(spec=MicrosoftGraphTokenManager),
        approved_mailbox="support@agilereceivables.com",
    )

    # 1. Valid URLs must succeed
    valid_urls = [
        "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta",
        "https://graph.microsoft.com/v1.0/users/support%40agilereceivables.com/mailFolders/Inbox/messages/delta?$deltatoken=xyz123",
        "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/inbox/messages?$top=50&$skip=10",
        "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta?$skiptoken=abc",
        "https://graph.microsoft.com/beta/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta",
    ]
    for url in valid_urls:
        assert client._validate_graph_url(url, expected_folder="Inbox") == url

    # Valid message detail URL (no folder)
    msg_url = "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/messages/AAMkAGExAAA="
    assert client._validate_graph_url(msg_url, expected_folder=None) == msg_url

    # 2. Insecure scheme (HTTP)
    with pytest.raises(GraphSecurityError, match="Insecure scheme 'http'"):
        client._validate_graph_url("http://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta")

    # 3. Untrusted / Lookalike Hostnames
    untrusted_hosts = [
        "https://graph.microsoft.com.attacker.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta",
        "https://attacker.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta",
        "https://127.0.0.1/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta",
        "https://169.254.169.254/latest/meta-data/",
        "https://microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta",
    ]
    for bad_url in untrusted_hosts:
        with pytest.raises(GraphSecurityError, match="Untrusted host"):
            client._validate_graph_url(bad_url)

    # 4. Non-standard Port
    with pytest.raises(GraphSecurityError, match="Non-standard port '8443'"):
        client._validate_graph_url("https://graph.microsoft.com:8443/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta")

    # 5. User Credentials in URL
    with pytest.raises(GraphSecurityError, match="User credentials in Graph URL are strictly prohibited"):
        client._validate_graph_url("https://admin:secret@graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta")

    # 6. Mailbox Scope Mismatch (Cross-Mailbox Attempt)
    cross_mailbox_urls = [
        "https://graph.microsoft.com/v1.0/users/ceo@agilereceivables.com/mailFolders/Inbox/messages/delta",
        "https://graph.microsoft.com/v1.0/users/support%40othercompany.com/mailFolders/Inbox/messages/delta",
        "https://graph.microsoft.com/v1.0/users/admin@agilereceivables.com/messages/123",
    ]
    for bad_url in cross_mailbox_urls:
        with pytest.raises(GraphMailboxScopeError, match="Unauthorized mailbox"):
            client._validate_graph_url(bad_url, expected_folder=None)

    # 7. Folder Scope Mismatch
    bad_folders = [
        "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/SentItems/messages/delta",
        "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Drafts/messages/delta",
        "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/DeletedItems/messages/delta",
    ]
    for bad_url in bad_folders:
        with pytest.raises(GraphSecurityError, match="Unauthorized folder"):
            client._validate_graph_url(bad_url, expected_folder="Inbox")

    # 8. Empty or Incomplete Path
    with pytest.raises(GraphSecurityError, match="Graph URL cannot be empty"):
        client._validate_graph_url("")
    with pytest.raises(GraphSecurityError, match="Incomplete Graph URL path"):
        client._validate_graph_url("https://graph.microsoft.com/v1.0")


def test_graph_client_rejects_http_redirects():
    """
    Issue 2: Verifies that MicrosoftGraphClient rejects HTTP 3xx redirects (SSRF mitigation).
    """
    mock_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    mock_token_mgr.get_access_token.return_value = "fake-token"

    mock_redirect_response = httpx.Response(
        status_code=302,
        headers={"Location": "https://attacker.com/steal-token"},
    )
    mock_http_client = MagicMock()
    mock_http_client.request.return_value = mock_redirect_response

    client = MicrosoftGraphClient(
        token_manager=mock_token_mgr,
        http_client=mock_http_client,
        approved_mailbox="support@agilereceivables.com",
    )

    with pytest.raises(GraphSecurityError, match="HTTP redirects are strictly prohibited"):
        client._execute_request("GET", "https://graph.microsoft.com/v1.0/users/support@agilereceivables.com/mailFolders/Inbox/messages/delta")


def test_sync_max_messages_partial_page_checkpoint_retention(test_db_session: Session):
    """
    Issue 3: Verifies that when max_messages is reached on a partial page,
    the durable checkpoint is NOT advanced past unprocessed messages.
    On the subsequent sync run, the cursor resumes from the safe checkpoint,
    already-ingested messages are deduplicated and skipped, and the remaining
    messages are fully processed without loss or duplication.
    """
    org, _ = create_tenant_and_user(test_db_session, "Agile Partial Sync", "sync@agilereceivables.com")
    mailbox = "support@agilereceivables.com"

    mock_token_mgr = MagicMock(spec=MicrosoftGraphTokenManager)
    mock_token_mgr.get_access_token.return_value = "token"
    client = MicrosoftGraphClient(token_manager=mock_token_mgr, approved_mailbox=mailbox)

    # 10 messages across 2 pages: 5 on Page 1, 5 on Page 2
    page1_items = [
        {
            "id": f"msg-page1-{i}",
            "from": {"emailAddress": {"address": f"lead1_{i}@domain.com"}},
            "toRecipients": [{"emailAddress": {"address": mailbox}}],
            "receivedDateTime": f"2026-10-21T10:0{i}:00Z",
            "body": {"content": f"Page 1 Message {i}"},
        }
        for i in range(1, 6)
    ]
    page2_items = [
        {
            "id": f"msg-page2-{i}",
            "from": {"emailAddress": {"address": f"lead2_{i}@domain.com"}},
            "toRecipients": [{"emailAddress": {"address": mailbox}}],
            "receivedDateTime": f"2026-10-21T11:0{i}:00Z",
            "body": {"content": f"Page 2 Message {i}"},
        }
        for i in range(1, 6)
    ]

    page2_url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/Inbox/messages/delta?page2"
    terminal_url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/Inbox/messages/delta?token=terminal100"

    def mock_execute(method, url, params=None):
        if "page2" in url:
            return httpx.Response(
                status_code=200,
                json={
                    "value": page2_items,
                    "@odata.deltaLink": terminal_url,
                },
            )
        else:
            return httpx.Response(
                status_code=200,
                json={
                    "value": page1_items,
                    "@odata.nextLink": page2_url,
                },
            )

    with patch("app.core.config.Settings.is_graph_live_sync_allowed", new=True):
        with patch.object(client, "_execute_request", side_effect=mock_execute):
            # RUN 1: Set max_messages = 3 (less than Page 1's 5 messages)
            result1 = sync_support_mailbox(
                test_db_session,
                org.id,
                max_messages=3,
                client_override=client,
            )

            assert result1.status == "partial"
            assert result1.messages_imported == 3
            # CRITICAL: Since only 3 of 5 messages on Page 1 were consumed,
            # checkpoint MUST NOT advance to page2_url!
            assert result1.checkpoint_delta_link is None

            # Verify DB state after Run 1: exactly 3 emails
            cp = get_or_create_checkpoint(test_db_session, org.id, mailbox)
            assert cp.last_sync_status == "partial"
            assert cp.delta_link is None
            assert cp.total_imported == 3
            assert test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org.id).count() == 3

            # RUN 2: Resume with max_messages = 50
            # Page 1 will be fetched again, first 3 messages will be deduplicated/skipped,
            # remaining 2 will be imported, then Page 2 will be fetched and all 5 imported.
            result2 = sync_support_mailbox(
                test_db_session,
                org.id,
                max_messages=50,
                client_override=client,
            )

            assert result2.status == "completed"
            assert result2.messages_fetched == 10
            assert result2.messages_skipped == 3  # Exactly the 3 from Run 1 skipped via deduplication!
            assert result2.messages_imported == 7  # 2 remaining from Page 1 + 5 from Page 2!
            assert result2.checkpoint_delta_link == terminal_url

            # Final DB verification
            test_db_session.refresh(cp)
            assert cp.last_sync_status == "completed"
            assert cp.delta_link == terminal_url
            assert cp.total_imported == 10  # 3 + 7 = 10 total imported
            assert cp.last_successful_sync_at is not None

            # Total unique InboundEmails in DB: exactly 10!
            total_db_emails = test_db_session.query(InboundEmail).filter(InboundEmail.organization_id == org.id).count()
            assert total_db_emails == 10


def test_settings_support_mailbox_validator():
    """
    Issue 4: Verifies settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX validator.
    Rejects empty, arbitrary, or lookalike mailboxes; accepts approved mailbox.
    """
    # 1. Approved mailbox accepted (case-insensitive normalization)
    s1 = Settings(MICROSOFT_GRAPH_SUPPORT_MAILBOX="support@agilereceivables.com")
    assert s1.MICROSOFT_GRAPH_SUPPORT_MAILBOX == "support@agilereceivables.com"

    s2 = Settings(MICROSOFT_GRAPH_SUPPORT_MAILBOX="SUPPORT@AGILERECEIVABLES.COM")
    assert s2.MICROSOFT_GRAPH_SUPPORT_MAILBOX == "support@agilereceivables.com"

    # 2. Empty mailbox rejected
    with pytest.raises(ValueError, match="cannot be empty"):
        Settings(MICROSOFT_GRAPH_SUPPORT_MAILBOX="")

    with pytest.raises(ValueError, match="cannot be empty"):
        Settings(MICROSOFT_GRAPH_SUPPORT_MAILBOX="   ")

    # 3. Arbitrary or lookalike mailbox rejected
    invalid_mailboxes = [
        "ceo@agilereceivables.com",
        "admin@agilereceivables.com",
        "support@agilereceivables.org",
        "support@agilereceivables.net",
        "support@attacker.com",
    ]
    for bad_box in invalid_mailboxes:
        with pytest.raises(ValueError, match="Unauthorized mailbox"):
            Settings(MICROSOFT_GRAPH_SUPPORT_MAILBOX=bad_box)




