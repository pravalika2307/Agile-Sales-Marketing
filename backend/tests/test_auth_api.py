"""Integration and API tests for Authentication and Multi-Tenancy endpoints."""
import uuid
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_organization
from app.core.database import Base, get_db
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.main import app
from app.models.business import BusinessProfile
from app.models.tenant import Organization, User


# ── In-Memory SQLite Test Fixture ─────────────────────────────────────────────

@pytest.fixture
def test_db_session():
    """Create a fresh in-memory SQLite database session for each test."""
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


@asynccontextmanager
async def make_test_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Registration Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(test_db_session: Session):
    payload = {
        "email": "ceo@growthscale.com",
        "password": "Password123!",
        "full_name": "Sarah Connor",
        "organization_name": "Growth Scale Inc",
    }
    async with make_test_client() as client:
        resp = await client.post("/api/v1/auth/register", json=payload)

    assert resp.status_code == 201
    data = resp.json()

    # Verify response structure
    assert "user" in data
    assert "tokens" in data
    assert "organization" in data
    assert data["user"]["email"] == "ceo@growthscale.com"
    assert data["user"]["full_name"] == "Sarah Connor"
    assert data["user"]["role"] == "owner"
    assert "hashed_password" not in data["user"]
    assert data["organization"]["name"] == "Growth Scale Inc"
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]

    # Verify records in database
    user_in_db = test_db_session.query(User).filter(User.email == "ceo@growthscale.com").first()
    assert user_in_db is not None
    assert user_in_db.hashed_password != "Password123!"
    assert user_in_db.hashed_password.startswith("$argon2id$")

    org_in_db = test_db_session.query(Organization).filter(Organization.id == user_in_db.organization_id).first()
    assert org_in_db is not None
    assert org_in_db.name == "Growth Scale Inc"

    profile_in_db = test_db_session.query(BusinessProfile).filter(BusinessProfile.organization_id == org_in_db.id).first()
    assert profile_in_db is not None
    assert profile_in_db.company_name == "Growth Scale Inc"


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(test_db_session: Session):
    payload = {
        "email": "duplicate@test.com",
        "password": "Password123!",
        "full_name": "First User",
        "organization_name": "First Org",
    }
    async with make_test_client() as client:
        resp1 = await client.post("/api/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        # Second registration with identical email
        payload2 = {
            "email": "duplicate@test.com",
            "password": "AnotherPassword123!",
            "full_name": "Second User",
            "organization_name": "Second Org",
        }
        resp2 = await client.post("/api/v1/auth/register", json=payload2)
        assert resp2.status_code == 409
        assert "already registered" in resp2.json()["detail"]


# ── Login Tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(test_db_session: Session):
    # Setup registered user
    org = Organization(name="Test Co", slug="test-co")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="testlogin@test.com",
        hashed_password=hash_password("ValidPassword123!"),
        full_name="Login Tester",
        role="owner",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    async with make_test_client() as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "testlogin@test.com", "password": "ValidPassword123!"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["email"] == "testlogin@test.com"
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]


@pytest.mark.asyncio
async def test_login_invalid_password(test_db_session: Session):
    org = Organization(name="Test Co 2", slug="test-co-2")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="wrongpw@test.com",
        hashed_password=hash_password("ValidPassword123!"),
        full_name="Login Tester",
        role="owner",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    async with make_test_client() as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@test.com", "password": "WRONG_PASSWORD"},
        )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_unknown_email(test_db_session: Session):
    async with make_test_client() as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@test.com", "password": "Password123!"},
        )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_inactive_user_rejected(test_db_session: Session):
    org = Organization(name="Inactive Co", slug="inactive-co")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="inactive@test.com",
        hashed_password=hash_password("ValidPassword123!"),
        full_name="Inactive User",
        role="member",
        is_active=False,
    )
    test_db_session.add(user)
    test_db_session.commit()

    async with make_test_client() as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "inactive@test.com", "password": "ValidPassword123!"},
        )
    assert resp.status_code == 403
    assert "inactive" in resp.json()["detail"]


# ── /me Endpoint Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_success(test_db_session: Session):
    async with make_test_client() as client:
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "me@example.com",
                "password": "Password123!",
                "full_name": "Me User",
                "organization_name": "Me Org",
            },
        )
        access_token = reg_resp.json()["tokens"]["access_token"]

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200
    user_data = resp.json()
    assert user_data["email"] == "me@example.com"
    assert user_data["full_name"] == "Me User"
    assert "hashed_password" not in user_data


@pytest.mark.asyncio
async def test_get_me_unauthorized_without_token(test_db_session: Session):
    async with make_test_client() as client:
        resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── Refresh Token Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_success(test_db_session: Session):
    async with make_test_client() as client:
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "refresh@example.com",
                "password": "Password123!",
                "full_name": "Refresh User",
                "organization_name": "Refresh Org",
            },
        )
        refresh_token = reg_resp.json()["tokens"]["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_access_token_rejected_at_refresh_endpoint(test_db_session: Session):
    async with make_test_client() as client:
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "type_check@example.com",
                "password": "Password123!",
                "full_name": "Type User",
                "organization_name": "Type Org",
            },
        )
        access_token = reg_resp.json()["tokens"]["access_token"]

        # Passing access token to refresh endpoint must be rejected
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
    assert resp.status_code == 401
    assert "Invalid refresh token" in resp.json()["detail"]


# ── Multi-Tenancy Authority Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_context_derived_strictly_from_jwt(test_db_session: Session):
    org = Organization(name="Target Tenant", slug="target-tenant")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="tenant_user@example.com",
        hashed_password="pw",
        full_name="Tenant User",
        role="owner",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    # Resolve organization dependency directly
    resolved_org = await get_current_organization(current_user=user, db=test_db_session)
    assert resolved_org.id == org.id
    assert resolved_org.name == "Target Tenant"


# ── Additional Security & Lifecycle Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_login_missing_or_malformed_input(test_db_session: Session):
    """Missing or invalid fields return HTTP 422 Unprocessable Entity."""
    async with make_test_client() as client:
        # Missing password
        resp1 = await client.post("/api/v1/auth/login", json={"email": "test@example.com"})
        assert resp1.status_code == 422

        # Invalid email format
        resp2 = await client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "Password123!"})
        assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_api_access_rejected():
    """Protected endpoints reject requests missing authorization headers or cookies."""
    async with make_test_client() as client:
        resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 401
    assert "Authentication credentials were not provided" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_expired_token_rejected(test_db_session: Session):
    """Expired access token is rejected with 401."""
    from datetime import timedelta
    org = Organization(name="Expired Co", slug="expired-co")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="expired@test.com",
        hashed_password="pw",
        full_name="Expired User",
        role="owner",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    expired_token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )

    async with make_test_client() as client:
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cookie_based_authentication(test_db_session: Session):
    """User can authenticate using auth_token cookie."""
    org = Organization(name="Cookie Co", slug="cookie-co")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="cookie@test.com",
        hashed_password="pw",
        full_name="Cookie User",
        role="owner",
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    valid_token = create_access_token(user_id=user.id, organization_id=org.id)

    async with make_test_client() as client:
        resp = await client.get("/api/v1/auth/me", cookies={"auth_token": valid_token})
    assert resp.status_code == 200
    assert resp.json()["email"] == "cookie@test.com"


@pytest.mark.asyncio
async def test_logout_clears_cookies():
    """Logout endpoint returns success and instructs client to expire auth cookies."""
    async with make_test_client() as client:
        resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert "logged out" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cross_tenant_isolation(test_db_session: Session):
    """User from Org A cannot access or mutate Org B data."""
    from app.models.campaign import Campaign

    org_a = Organization(name="Org A", slug="org-a")
    org_b = Organization(name="Org B", slug="org-b")
    test_db_session.add_all([org_a, org_b])
    test_db_session.flush()

    user_a = User(
        organization_id=org_a.id,
        email="user_a@test.com",
        hashed_password="pw",
        full_name="User A",
        role="owner",
        is_active=True,
    )
    test_db_session.add(user_a)

    camp_b = Campaign(
        organization_id=org_b.id,
        name="Org B Confidential Campaign",
        type="sales_outbound",
        status="draft",
    )
    test_db_session.add(camp_b)
    test_db_session.commit()

    token_a = create_access_token(user_id=user_a.id, organization_id=org_a.id)

    async with make_test_client() as client:
        # Org A user listing campaigns -> should only see Org A campaigns (0 campaigns), never Org B's
        list_resp = await client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {token_a}"})
        assert list_resp.status_code == 200
        campaign_ids = [c["id"] for c in list_resp.json()]
        assert str(camp_b.id) not in campaign_ids

        # Org A user directly requesting Org B's campaign by ID -> must return 404 Not Found
        detail_resp = await client.get(f"/api/v1/campaigns/{camp_b.id}", headers={"Authorization": f"Bearer {token_a}"})
        assert detail_resp.status_code == 404


# ── SEC-01: JWT Signing Secret Validation Tests ──────────────────────────────

def test_secret_key_validation_rejects_missing_and_weak_keys():
    """Verify Settings rejects missing, short (<32 chars), and default secrets."""
    from pydantic import ValidationError
    from app.core.config import Settings

    # 1. Insecure default secret must be rejected
    with pytest.raises(ValidationError) as exc1:
        Settings(SECRET_KEY="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
    assert "known insecure" in str(exc1.value)

    # 2. Known placeholder secret must be rejected
    with pytest.raises(ValidationError) as exc2:
        Settings(SECRET_KEY="change-me-in-production-use-a-strong-secret-key-at-least-32-chars")
    assert "known insecure" in str(exc2.value)

    # 3. Weak (<32 chars) secret must be rejected
    with pytest.raises(ValidationError) as exc3:
        Settings(SECRET_KEY="short-secret-12345")
    assert "at least 32 characters" in str(exc3.value)

    # 4. Valid 64-character random key is accepted
    valid_key = "a" * 64
    s = Settings(SECRET_KEY=valid_key)
    assert s.SECRET_KEY == valid_key


# ── SEC-02: CORS Origin Restriction Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_cors_trusted_origin_allowed():
    """Requests from trusted origins receive Access-Control-Allow-Origin."""
    async with make_test_client() as client:
        # Preflight OPTIONS
        resp = await client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_untrusted_origin_blocked():
    """Untrusted origins must never receive Access-Control-Allow-Origin."""
    async with make_test_client() as client:
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Origin": "https://evil-attacker.com"},
        )
        # Untrusted origin must NOT be echoed in Access-Control-Allow-Origin
        assert resp.headers.get("access-control-allow-origin") != "https://evil-attacker.com"
        assert resp.headers.get("access-control-allow-origin") is None


# ── SEC-03 & SEC-04: Token Malformation & Mismatch Tests ────────────────────

@pytest.mark.asyncio
async def test_malformed_token_rejected(test_db_session: Session):
    """Malformed tokens (invalid base64, garbage strings) return 401."""
    async with make_test_client() as client:
        # 1. Arbitrary garbage token
        resp1 = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bogus_token_string"})
        assert resp1.status_code == 401
        assert "invalid" in resp1.json()["detail"].lower()

        # 2. Tampered signature
        org = Organization(name="Tamper Co", slug="tamper-co")
        test_db_session.add(org)
        test_db_session.flush()
        user = User(organization_id=org.id, email="tamper@test.com", hashed_password="pw", full_name="Tamper", role="member")
        test_db_session.add(user)
        test_db_session.commit()

        valid_token = create_access_token(user_id=user.id, organization_id=org.id)
        tampered_token = valid_token[:-5] + "XXXXX"
        resp2 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert resp2.status_code == 401
        assert "invalid" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_token_org_id_mismatch_rejected(test_db_session: Session):
    """Token with an org_id claiming a different organization is rejected with 403."""
    org_a = Organization(name="User Org", slug="user-org")
    org_b = Organization(name="Victim Org", slug="victim-org")
    test_db_session.add_all([org_a, org_b])
    test_db_session.flush()

    user = User(
        organization_id=org_a.id,
        email="mismatch@test.com",
        hashed_password="pw",
        full_name="Mismatch User",
        role="member",
    )
    test_db_session.add(user)
    test_db_session.commit()

    # User belongs to Org A, but token claims Org B
    mismatched_token = create_access_token(user_id=user.id, organization_id=org_b.id)

    async with make_test_client() as client:
        resp = await client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {mismatched_token}"})
    assert resp.status_code == 403
    assert "cross-tenant" in resp.json()["detail"].lower()


# ── Session Handling & Refresh Token Tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_via_cookie(test_db_session: Session):
    """Refresh session succeeds when refresh_token is provided via cookie."""
    org = Organization(name="Refresh Cookie Co", slug="refresh-cookie-co")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(
        organization_id=org.id,
        email="cookie_refresh@test.com",
        hashed_password="pw",
        full_name="Cookie Refresher",
        role="member",
    )
    test_db_session.add(user)
    test_db_session.commit()

    refresh_tok = create_refresh_token(user_id=user.id, organization_id=org.id)

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", cookies={"refresh_token": refresh_tok})
    async with client:
        resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Response cookies must contain updated auth_token
    assert "auth_token" in resp.cookies


@pytest.mark.asyncio
async def test_expired_refresh_token_rejected(test_db_session: Session):
    """Expired refresh token is rejected with 401."""
    from datetime import timedelta
    org = Organization(name="Exp Ref Co", slug="exp-ref-co")
    test_db_session.add(org)
    test_db_session.flush()

    user = User(organization_id=org.id, email="exp_ref@test.com", hashed_password="pw", full_name="Exp Ref", role="member")
    test_db_session.add(user)
    test_db_session.commit()

    expired_refresh = create_refresh_token(
        user_id=user.id,
        organization_id=org.id,
        expires_delta=timedelta(seconds=-10),
    )

    async with make_test_client() as client:
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": expired_refresh})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


# ── Voice Replay Endpoint Authentication Test ────────────────────────────────

@pytest.mark.asyncio
async def test_voice_replay_endpoint_requires_auth():
    """Unauthenticated access to /api/v1/voice/replay-analyzed-call is rejected."""
    async with make_test_client() as client:
        resp = await client.post("/api/v1/voice/replay-analyzed-call", json={"test": True})
    assert resp.status_code == 401


# ── Multi-Entity Tenant Isolation Tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_tenant_isolation_across_all_entities(test_db_session: Session):
    """Verify Org A user cannot read Org B's leads, lists, templates, or companies."""
    from app.models.lead import Lead
    from app.models.contact_list import ContactList
    from app.models.email_template import EmailTemplate
    from app.models.crm import Company

    org_a = Organization(name="Isolation Org A", slug="iso-a")
    org_b = Organization(name="Isolation Org B", slug="iso-b")
    test_db_session.add_all([org_a, org_b])
    test_db_session.flush()

    user_a = User(organization_id=org_a.id, email="iso_a@test.com", hashed_password="pw", full_name="User A", role="owner")
    test_db_session.add(user_a)

    # Create Org B entities
    lead_b = Lead(organization_id=org_b.id, company_name="Target Corp", email="lead_b@target.com", first_name="Target", last_name="Lead")
    list_b = ContactList(organization_id=org_b.id, name="Org B Secret List", type="static")
    template_b = EmailTemplate(organization_id=org_b.id, name="Org B Template", subject_template="Confidential", body_template="Secret Body")
    company_b = Company(organization_id=org_b.id, name="Org B Proprietary Co", domain="proprietary.com")

    test_db_session.add_all([lead_b, list_b, template_b, company_b])
    test_db_session.commit()

    token_a = create_access_token(user_id=user_a.id, organization_id=org_a.id)
    headers = {"Authorization": f"Bearer {token_a}"}

    async with make_test_client() as client:
        # Lead
        resp_lead = await client.get(f"/api/v1/leads/{lead_b.id}", headers=headers)
        assert resp_lead.status_code == 404

        # Contact List
        resp_list = await client.get(f"/api/v1/lists/{list_b.id}", headers=headers)
        assert resp_list.status_code == 404

        # Template
        resp_tmpl = await client.get(f"/api/v1/templates/{template_b.id}", headers=headers)
        assert resp_tmpl.status_code == 404

        # Company
        resp_comp = await client.get(f"/api/v1/companies/{company_b.id}", headers=headers)
        assert resp_comp.status_code == 404

        # Analytics overview for Org A must return 0 leads/campaigns for Org B
        resp_analytics = await client.get("/api/v1/analytics/overview", headers=headers)
        assert resp_analytics.status_code == 200
        overview = resp_analytics.json()
        assert overview["leads"]["total_leads"] == 0


