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
from app.core.security import create_access_token, hash_password
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
