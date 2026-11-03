"""Comprehensive test suite for LinkedIn OAuth 2.0 and OpenID Connect integration."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_active_user, get_current_organization, get_db
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models.linkedin import LinkedInConnection, LinkedInOAuthState
from app.models.tenant import Organization, User
from app.services.integrations.linkedin.client import LinkedInOAuthClient
from app.services.integrations.linkedin.encryption import (
    decrypt_token,
    encrypt_token,
    get_encryption_key,
)
from app.services.integrations.linkedin.service import (
    OAUTH_STATE_TTL_MINUTES,
    LinkedInIntegrationService,
    _ensure_utc,
)


# ── Test RSA Key Helper for OpenID ID Token Verification ─────────────────────

@pytest.fixture(scope="session")
def rsa_keypair():
    """Generate in-memory 2048-bit RSA key pair for testing ID token signatures."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


# ── In-Memory SQLite Test Fixture ─────────────────────────────────────────────

@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database session."""
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


@pytest.fixture
def test_tenants(db_session: Session):
    """Create two test organizations and users for tenant isolation testing."""
    org1 = Organization(
        id=uuid.uuid4(),
        name="Agile Receivables Primary",
        slug="agile-receivables-primary",
        billing_status="active",
    )
    org2 = Organization(
        id=uuid.uuid4(),
        name="Competitor Corp",
        slug="competitor-corp",
        billing_status="trial",
    )
    user1 = User(
        id=uuid.uuid4(),
        organization_id=org1.id,
        email="sdr@agilereceivables.com",
        hashed_password="mock_hashed_pw",
        full_name="Sarah SDR",
        role="admin",
        is_active=True,
    )
    user2 = User(
        id=uuid.uuid4(),
        organization_id=org2.id,
        email="user@competitor.com",
        hashed_password="mock_hashed_pw",
        full_name="Charlie Competitor",
        role="member",
        is_active=True,
    )
    db_session.add_all([org1, org2, user1, user2])
    db_session.commit()
    return {"org1": org1, "org2": org2, "user1": user1, "user2": user2}


# ── Token Encryption Tests ───────────────────────────────────────────────────

def test_token_encryption_and_decryption():
    """Verify that tokens are encrypted to ciphertext and decrypt cleanly."""
    plaintext = "AQV_linkedin_access_token_super_secret_12345"
    ciphertext = encrypt_token(plaintext)

    assert ciphertext is not None
    assert ciphertext != plaintext
    assert plaintext not in ciphertext
    assert ciphertext.startswith("gAAAAA")

    decrypted = decrypt_token(ciphertext)
    assert decrypted == plaintext


def test_token_decryption_tamper_detection():
    """Verify that tampering with ciphertext fails authentication."""
    plaintext = "AQV_secret_token"
    ciphertext = encrypt_token(plaintext)
    assert ciphertext is not None

    # Tamper with the ciphertext
    tampered = ciphertext[:-4] + "AAAA"
    with pytest.raises(ValueError, match="invalid or tampered token ciphertext"):
        decrypt_token(tampered)


def test_token_encryption_empty_handling():
    """Verify handling of None and empty token values."""
    assert encrypt_token(None) is None
    assert encrypt_token("") is None
    assert decrypt_token(None) is None
    assert decrypt_token("") is None


# ── OAuth State & Replay Protection Tests ─────────────────────────────────────

def test_oauth_state_creation_and_expiry(db_session: Session, test_tenants):
    """Verify state creation binds user, org, and sets 15-minute TTL."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)

    org = test_tenants["org1"]
    user = test_tenants["user1"]

    flow = service.create_authorization_flow(user=user, org=org)
    assert "authorization_url" in flow
    assert "state" in flow
    assert flow["state"] in flow["authorization_url"]
    assert "response_type=code" in flow["authorization_url"]
    assert "client_id=test_client_id" in flow["authorization_url"]

    # Verify DB persistence
    state_rec = db_session.query(LinkedInOAuthState).filter_by(state=flow["state"]).first()
    assert state_rec is not None
    assert state_rec.organization_id == org.id
    assert state_rec.user_id == user.id
    assert not state_rec.is_used
    assert state_rec.nonce is not None
    # Expiry is roughly 15 minutes in the future
    assert _ensure_utc(state_rec.expires_at) > datetime.now(timezone.utc)
    delta = _ensure_utc(state_rec.expires_at) - _ensure_utc(state_rec.created_at)
    assert abs(delta.total_seconds() - (OAUTH_STATE_TTL_MINUTES * 60)) < 10


def test_oauth_state_replay_protection(db_session: Session, test_tenants):
    """Verify that an OAuth state cannot be used more than once."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)

    org = test_tenants["org1"]
    user = test_tenants["user1"]

    flow = service.create_authorization_flow(user=user, org=org)
    state = flow["state"]

    # First validation succeeds and consumes the state
    first_consumed = service.validate_and_consume_state(state)
    assert first_consumed.is_used is True

    # Immediate second validation must fail with replay protection error
    with pytest.raises(ValueError, match="replay attack prevented"):
        service.validate_and_consume_state(state)


def test_expired_oauth_state_rejected(db_session: Session, test_tenants):
    """Verify that an expired OAuth state is rejected."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)

    org = test_tenants["org1"]
    user = test_tenants["user1"]

    flow = service.create_authorization_flow(user=user, org=org)
    state = flow["state"]

    # Backdate expires_at
    state_rec = db_session.query(LinkedInOAuthState).filter_by(state=state).first()
    state_rec.expires_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    db_session.commit()

    with pytest.raises(ValueError, match="OAuth state has expired"):
        service.validate_and_consume_state(state)


# ── ID Token Validation Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_id_token_validation_success(rsa_keypair):
    """Verify successful validation of a valid OpenID Connect ID token."""
    private_key, public_pem = rsa_keypair
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")

    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iss": "https://www.linkedin.com",
        "aud": "test_client_id",
        "sub": "li_member_987654",
        "name": "Jane LinkedIn Executive",
        "email": "jane@agilereceivables.com",
        "picture": "https://media.licdn.com/dms/image/v2/mock.jpg",
        "nonce": "test_nonce_abc123",
        "exp": now + 3600,
        "iat": now,
    }
    id_token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test-kid"})

    claims = await client.validate_id_token(
        id_token=id_token,
        nonce="test_nonce_abc123",
        signing_key_override=public_pem,
    )
    assert claims["sub"] == "li_member_987654"
    assert claims["name"] == "Jane LinkedIn Executive"
    assert claims["email"] == "jane@agilereceivables.com"


@pytest.mark.asyncio
async def test_id_token_validation_failure_modes(rsa_keypair):
    """Verify that invalid issuer, expired tokens, audience mismatch, and nonce mismatch fail."""
    private_key, public_pem = rsa_keypair
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    now = int(datetime.now(timezone.utc).timestamp())

    # 1. Invalid Issuer
    bad_iss = jwt.encode(
        {"iss": "https://evil.com", "aud": "test_client_id", "sub": "123", "exp": now + 3600},
        private_key,
        algorithm="RS256",
    )
    with pytest.raises(ValueError, match="issuer mismatch"):
        await client.validate_id_token(bad_iss, signing_key_override=public_pem)

    # 2. Audience Mismatch
    bad_aud = jwt.encode(
        {"iss": "https://www.linkedin.com", "aud": "wrong_aud", "sub": "123", "exp": now + 3600},
        private_key,
        algorithm="RS256",
    )
    with pytest.raises(ValueError, match="audience mismatch"):
        await client.validate_id_token(bad_aud, signing_key_override=public_pem)

    # 3. Expired Token
    expired = jwt.encode(
        {"iss": "https://www.linkedin.com", "aud": "test_client_id", "sub": "123", "exp": now - 300},
        private_key,
        algorithm="RS256",
    )
    with pytest.raises(ValueError, match="ID token has expired"):
        await client.validate_id_token(expired, signing_key_override=public_pem)

    # 4. Nonce Mismatch
    bad_nonce = jwt.encode(
        {"iss": "https://www.linkedin.com", "aud": "test_client_id", "sub": "123", "nonce": "nonce_A", "exp": now + 3600},
        private_key,
        algorithm="RS256",
    )
    with pytest.raises(ValueError, match="nonce does not match"):
        await client.validate_id_token(bad_nonce, nonce="nonce_B", signing_key_override=public_pem)


# ── Full Callback, Token Exchange, and Persistence Tests ──────────────────────

@pytest.mark.asyncio
async def test_callback_successful_exchange_and_encryption(db_session: Session, test_tenants, rsa_keypair):
    """Verify end-to-end callback execution, token encryption, and member profile storage."""
    private_key, public_pem = rsa_keypair
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)

    org = test_tenants["org1"]
    user = test_tenants["user1"]
    flow = service.create_authorization_flow(user=user, org=org)
    state = flow["state"]

    # Mock token response and ID token
    now = int(datetime.now(timezone.utc).timestamp())
    mock_id_token = jwt.encode(
        {
            "iss": "https://www.linkedin.com",
            "aud": "test_client_id",
            "sub": "linkedin_member_12345",
            "name": "Alex Receivables",
            "email": "alex@agilereceivables.com",
            "picture": "https://media.licdn.com/dms/image/alex.jpg",
            "exp": now + 3600,
            "iat": now,
        },
        private_key,
        algorithm="RS256",
    )

    mock_exchange_tokens = {
        "access_token": "live_real_format_access_token_abc_xyz",
        "expires_in": 5184000,
        "scope": "openid profile email",
        "id_token": mock_id_token,
    }

    client.exchange_code_for_tokens = AsyncMock(return_value=mock_exchange_tokens)
    client.validate_id_token = AsyncMock(return_value={
        "sub": "linkedin_member_12345",
        "name": "Alex Receivables",
        "email": "alex@agilereceivables.com",
        "picture": "https://media.licdn.com/dms/image/alex.jpg",
    })

    conn = await service.handle_callback(state=state, code="auth_code_from_linkedin_redirect")

    assert conn.status == "connected"
    assert conn.organization_id == org.id
    assert conn.linkedin_member_id == "linkedin_member_12345"
    assert conn.member_name == "Alex Receivables"
    assert conn.member_email == "alex@agilereceivables.com"
    assert conn.profile_picture_url == "https://media.licdn.com/dms/image/alex.jpg"

    # CRITICAL: Verify token at rest is encrypted and NOT plaintext
    assert conn.encrypted_access_token != "live_real_format_access_token_abc_xyz"
    assert conn.encrypted_access_token.startswith("gAAAAA")
    decrypted = decrypt_token(conn.encrypted_access_token)
    assert decrypted == "live_real_format_access_token_abc_xyz"


@pytest.mark.asyncio
async def test_callback_handles_user_cancellation(db_session: Session, test_tenants):
    """Verify that user cancellation in OAuth dialog is safely handled and state consumed."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)

    org = test_tenants["org1"]
    user = test_tenants["user1"]
    flow = service.create_authorization_flow(user=user, org=org)
    state = flow["state"]

    with pytest.raises(ValueError, match="LinkedIn authorization was cancelled"):
        await service.handle_callback(
            state=state,
            code=None,
            error="user_cancelled_authorize",
            error_description="The user cancelled the authorization request",
        )

    # State must be marked used even on cancellation to avoid reuse
    state_rec = db_session.query(LinkedInOAuthState).filter_by(state=state).first()
    assert state_rec.is_used is True


# ── Tenant Isolation Tests ────────────────────────────────────────────────────

def test_tenant_isolation(db_session: Session, test_tenants):
    """Verify that Organization A's connection cannot be viewed or modified by Organization B."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)

    org1 = test_tenants["org1"]
    org2 = test_tenants["org2"]

    # Create connection for org1
    conn1 = LinkedInConnection(
        organization_id=org1.id,
        user_id=test_tenants["user1"].id,
        linkedin_member_id="org1_member_id",
        member_name="Org 1 Executive",
        member_email="exec@org1.com",
        encrypted_access_token=encrypt_token("token_org1") or "",
        status="connected",
        connected_at=datetime.now(timezone.utc),
    )
    db_session.add(conn1)
    db_session.commit()

    # Query status for org1: connected
    status1 = service.get_connection_status(org1)
    assert status1["connected"] is True
    assert status1["member_name"] == "Org 1 Executive"

    # Query status for org2: disconnected and completely isolated
    status2 = service.get_connection_status(org2)
    assert status2["connected"] is False
    assert status2["status"] == "disconnected"
    assert status2["member_name"] is None

    # Org2 disconnects: does NOT affect org1
    service.disconnect(org2)
    db_session.refresh(conn1)
    assert conn1.status == "connected"


# ── Disconnect & Expiration Lifecycle Tests ───────────────────────────────────

def test_disconnect_lifecycle(db_session: Session, test_tenants):
    """Verify that disconnecting an account erases tokens and sets disconnected status."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)
    org = test_tenants["org1"]

    conn = LinkedInConnection(
        organization_id=org.id,
        linkedin_member_id="member_to_disconnect",
        member_name="Disconnect Target",
        encrypted_access_token=encrypt_token("active_token") or "",
        status="connected",
        connected_at=datetime.now(timezone.utc),
    )
    db_session.add(conn)
    db_session.commit()

    success = service.disconnect(org)
    assert success is True

    db_session.refresh(conn)
    assert conn.status == "disconnected"
    # Token must be eradicated
    assert conn.encrypted_access_token == ""
    assert conn.disconnected_at is not None

    status = service.get_connection_status(org)
    assert status["connected"] is False
    assert status["status"] == "disconnected"


def test_token_expiration_status(db_session: Session, test_tenants):
    """Verify that an expired token reports status='expired'."""
    client = LinkedInOAuthClient(client_id="test_client_id", client_secret="test_secret")
    service = LinkedInIntegrationService(db=db_session, client=client)
    org = test_tenants["org1"]

    conn = LinkedInConnection(
        organization_id=org.id,
        linkedin_member_id="expired_member",
        member_name="Expired Account",
        encrypted_access_token=encrypt_token("expired_token") or "",
        access_token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status="connected",
        connected_at=datetime.now(timezone.utc) - timedelta(days=61),
    )
    db_session.add(conn)
    db_session.commit()

    status = service.get_connection_status(org)
    assert status["connected"] is False
    assert status["status"] == "expired"
    assert "expired" in status["message"].lower()


# ── Fast API Endpoint Integration Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_api_status_redaction(db_session: Session, test_tenants):
    """Verify /status endpoint returns safe redacted data without secrets or tokens."""
    org1 = test_tenants["org1"]
    user1 = test_tenants["user1"]

    conn = LinkedInConnection(
        organization_id=org1.id,
        linkedin_member_id="api_member_123",
        member_name="API Tester",
        member_email="tester@agilereceivables.com",
        encrypted_access_token=encrypt_token("very_secret_token") or "",
        status="connected",
        connected_at=datetime.now(timezone.utc),
    )
    db_session.add(conn)
    db_session.commit()

    # Configure client settings
    with patch.object(settings, "LINKEDIN_CLIENT_ID", "test_id"), \
         patch.object(settings, "LINKEDIN_CLIENT_SECRET", "test_secret"):

        app.dependency_overrides[get_current_organization] = lambda: org1
        app.dependency_overrides[get_current_active_user] = lambda: user1

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                res = await client.get("/api/v1/integrations/linkedin/status")
                assert res.status_code == 200
                data = res.json()

                assert data["configured"] is True
                assert data["connected"] is True
                assert data["member_name"] == "API Tester"
                assert data["member_email"] == "tester@agilereceivables.com"

                # STRICT: tokens and secret keys must not exist in response payload
                data_str = json.dumps(data)
                assert "access_token" not in data_str
                assert "very_secret_token" not in data_str
                assert "encrypted_access_token" not in data_str
                assert "client_secret" not in data_str
        finally:
            app.dependency_overrides.pop(get_current_organization, None)
            app.dependency_overrides.pop(get_current_active_user, None)


def test_linkedin_capabilities_matrix(db_session: Session, test_tenants):
    """Verify LinkedIn API capability matrix returns all 7 capabilities with correct permission flags."""
    org1 = test_tenants["org1"]
    service = LinkedInIntegrationService(db=db_session)

    caps = service.get_capabilities(org=org1)
    assert caps["workflow_mode"] == "assisted"
    assert caps["booking_url"] == "https://cal.com/agilereceivables/30min"
    assert caps["connection_note_limit"] == 300

    matrix = caps["capabilities"]
    assert "read_profile" in matrix
    assert "read_email" in matrix
    assert "organization_page_info" in matrix
    assert "publish_content" in matrix
    assert "connection_invitations" in matrix
    assert "direct_messages" in matrix
    assert "invitation_acceptance" in matrix

    # Verify assisted notes on gated APIs
    assert matrix["connection_invitations"]["status"] == "unsupported"
    assert matrix["connection_invitations"]["assisted_alternative"] is not None
    assert matrix["direct_messages"]["status"] == "unsupported"


def test_linkedin_campaign_assisted_queue_and_confirmation(db_session: Session, test_tenants):
    """Verify assisted LinkedIn queue generation and manual dispatch confirmation."""
    from app.models.campaign import Campaign, CampaignContact
    from app.models.crm import Company, Contact

    org1 = test_tenants["org1"]
    user1 = test_tenants["user1"]
    service = LinkedInIntegrationService(db=db_session)

    # Create campaign
    camp = Campaign(
        id=uuid.uuid4(),
        organization_id=org1.id,
        name="LinkedIn Assisted Test Campaign",
        type="sales_outbound",
        status="active",
        workflow_config={"steps": [{"step_number": 1, "type": "linkedin"}]},
    )
    db_session.add(camp)

    # Create company
    comp = Company(
        id=uuid.uuid4(),
        organization_id=org1.id,
        name="Apex Healthcare",
    )
    db_session.add(comp)
    db_session.flush()

    # Create contact
    contact = Contact(
        id=uuid.uuid4(),
        organization_id=org1.id,
        company_id=comp.id,
        first_name="Priya",
        last_name="Sharma",
        email="priya.sharma@example.com",
        job_title="VP of Finance",
    )
    db_session.add(contact)
    db_session.flush()

    # Enroll contact
    camp_contact = CampaignContact(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        contact_id=contact.id,
        enrollment_status="queued",
        current_step=1,
    )
    db_session.add(camp_contact)
    db_session.commit()

    # Fetch assisted queue
    queue_resp = service.get_campaign_assisted_queue(org=org1, campaign_id=camp.id)
    assert queue_resp["total"] == 1
    assert queue_resp["pending_count"] == 1
    assert queue_resp["completed_count"] == 0

    item = queue_resp["items"][0]
    assert item["full_name"] == "Priya Sharma"
    assert item["company_name"] == "Apex Healthcare"
    assert len(item["connection_note"]) <= 300
    assert "https://cal.com/agilereceivables/30min" in item["connection_note"]
    assert item["outreach_status"] == "pending"

    # Confirm manual action
    confirm_resp = service.confirm_assisted_action(
        user=user1,
        org=org1,
        campaign_id=camp.id,
        campaign_contact_id=camp_contact.id,
        action_type="connection_request",
        notes="Sent via LinkedIn desktop",
    )
    assert confirm_resp["success"] is True
    assert confirm_resp["status"] == "sent"

    # Re-fetch queue and verify status transition
    updated_queue = service.get_campaign_assisted_queue(org=org1, campaign_id=camp.id)
    assert updated_queue["completed_count"] == 1
    assert updated_queue["items"][0]["outreach_status"] == "sent"
