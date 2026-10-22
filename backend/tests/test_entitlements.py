"""Tests for SaaS Multi-Tenant Channel Entitlements and Upgrade Request Workflow."""
import uuid
from typing import Tuple

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.entitlement import (
    ChannelUpgradeRequest,
    EntitlementAuditLog,
    OrganizationChannelEntitlement,
)
from app.models.tenant import Organization, User


@pytest.fixture
def test_db_session():
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


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> Tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    data = resp.json()
    return data["tokens"]["access_token"], data["organization"]["id"]


def create_platform_admin(db: Session, email: str = "superadmin@agile.internal") -> Tuple[str, User]:
    """Helper creating a platform superadmin user for administrative approval tests."""
    admin_org = Organization(name="Agile Internal Admin", slug=f"admin-org-{uuid.uuid4().hex[:8]}")
    db.add(admin_org)
    db.flush()

    admin_user = User(
        organization_id=admin_org.id,
        email=email,
        hashed_password="hashed_admin_password",
        full_name="Platform Superadmin",
        role="superadmin",
        is_active=True,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    token = create_access_token(user_id=admin_user.id, organization_id=admin_org.id, role="superadmin")
    return token, admin_user


@pytest.mark.asyncio
async def test_list_channel_capabilities_default_tier(test_db_session):
    """Default trial tenant has Email included, other 4 channels upgrade_required."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "entitlements1@test.com", "Entitlements Org 1")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/entitlements/channels", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["organization_id"] == org_id
        assert data["billing_status"] == "trial"

        channels = {c["channel"]: c for c in data["channels"]}
        assert len(channels) == 5

        # Email is base channel
        assert channels["email"]["status"] == "included"
        assert channels["email"]["is_unlocked"] is True
        assert "Namecheap" in channels["email"]["description"]

        # Advanced channels require upgrade
        for ch in ["sms", "voice", "ringless_voicemail", "physical_mail"]:
            assert channels[ch]["status"] == "upgrade_required"
            assert channels[ch]["is_unlocked"] is False

        # Verify MMS features on SMS channel
        assert any("MMS" in f for f in channels["sms"]["features"])
        assert channels["sms"]["limits"]["max_character_count"] == 1600


@pytest.mark.asyncio
async def test_request_channel_upgrade_workflow(test_db_session):
    """Tenant can submit an upgrade request and channel status updates to upgrade_requested."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "entitlements2@test.com", "Entitlements Org 2")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Submit upgrade request for SMS
        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={
                "channel": "sms",
                "estimated_volume": "2500/month",
                "justification": "Outbound executive SDR follow-up campaign",
            },
            headers=headers,
        )
        assert req_resp.status_code == 202
        req_data = req_resp.json()
        assert req_data["channel"] == "sms"
        assert req_data["status"] == "upgrade_requested"
        assert req_data["request_id"] is not None

        # Verify SQL persistence in test database
        persisted_req = (
            test_db_session.query(ChannelUpgradeRequest)
            .filter(ChannelUpgradeRequest.id == uuid.UUID(req_data["request_id"]))
            .first()
        )
        assert persisted_req is not None
        assert persisted_req.status == "pending"
        assert persisted_req.estimated_volume == "2500/month"

        # Verify audit log was created
        audit_log = (
            test_db_session.query(EntitlementAuditLog)
            .filter(EntitlementAuditLog.organization_id == uuid.UUID(org_id))
            .first()
        )
        assert audit_log is not None
        assert audit_log.action == "upgrade_requested"
        assert audit_log.channel == "sms"

        # 2. Check channel list now reflects upgrade_requested
        resp = await client.get("/api/v1/entitlements/channels", headers=headers)
        assert resp.status_code == 200
        channels = {c["channel"]: c for c in resp.json()["channels"]}
        assert channels["sms"]["status"] == "upgrade_requested"
        assert channels["sms"]["is_unlocked"] is False

        # 3. Check tenant can view their own requests via GET /upgrade-requests
        my_reqs_resp = await client.get("/api/v1/entitlements/upgrade-requests", headers=headers)
        assert my_reqs_resp.status_code == 200
        my_reqs = my_reqs_resp.json()
        assert len(my_reqs) == 1
        assert my_reqs[0]["channel"] == "sms"
        assert my_reqs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_tenant_isolation_on_upgrade_requests(test_db_session):
    """Tenant A's upgrade request does not unlock or affect Tenant B's channels or request list."""
    async with make_client() as client:
        token_a, org_a = await register_tenant(client, "tenant_a@test.com", "Tenant A Org")
        token_b, org_b = await register_tenant(client, "tenant_b@test.com", "Tenant B Org")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A requests SMS upgrade
        await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={"channel": "sms", "estimated_volume": "1000"},
            headers=headers_a,
        )

        # Tenant A sees upgrade_requested
        resp_a = await client.get("/api/v1/entitlements/channels", headers=headers_a)
        channels_a = {c["channel"]: c for c in resp_a.json()["channels"]}
        assert channels_a["sms"]["status"] == "upgrade_requested"

        # Tenant B still sees upgrade_required
        resp_b = await client.get("/api/v1/entitlements/channels", headers=headers_b)
        channels_b = {c["channel"]: c for c in resp_b.json()["channels"]}
        assert channels_b["sms"]["status"] == "upgrade_required"
        assert channels_b["sms"]["is_unlocked"] is False

        # Tenant B cannot see Tenant A's upgrade requests
        reqs_b = await client.get("/api/v1/entitlements/upgrade-requests", headers=headers_b)
        assert reqs_b.status_code == 200
        assert len(reqs_b.json()) == 0


@pytest.mark.asyncio
async def test_customer_cannot_self_approve_upgrade(test_db_session):
    """A customer (even with owner role) cannot access admin decision endpoints to approve their own upgrade."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "owner@customer.com", "Customer Org")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Request SMS upgrade
        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={"channel": "sms", "estimated_volume": "5000"},
            headers=headers,
        )
        req_id = req_resp.json()["request_id"]

        # 2. Attempt to self-approve via admin endpoint -> Must be rejected with 403 Forbidden
        decision_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={"action": "approve", "allocated_quota": 5000},
            headers=headers,
        )
        assert decision_resp.status_code == 403
        assert "Platform administrator privileges required" in decision_resp.text

        # Verify channel remains locked
        cap_resp = await client.get("/api/v1/entitlements/channels", headers=headers)
        channels = {c["channel"]: c for c in cap_resp.json()["channels"]}
        assert channels["sms"]["is_unlocked"] is False


@pytest.mark.asyncio
async def test_platform_admin_approval_unlocks_channel_and_audits(test_db_session):
    """An authorized platform administrator can approve an upgrade, unlocking the channel and recording audit log."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "tenant_corp@example.com", "Corp Tenant")
        tenant_headers = {"Authorization": f"Bearer {token}"}

        # 1. Tenant submits upgrade request
        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={
                "channel": "sms",
                "estimated_volume": "10000/month",
                "justification": "National outbound sales sprint",
            },
            headers=tenant_headers,
        )
        req_id = req_resp.json()["request_id"]

        # 2. Create Platform Superadmin
        admin_token, admin_user = create_platform_admin(test_db_session)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 3. Admin lists all requests
        admin_list_resp = await client.get("/api/v1/entitlements/admin/upgrade-requests", headers=admin_headers)
        assert admin_list_resp.status_code == 200
        all_reqs = admin_list_resp.json()
        assert any(r["id"] == req_id for r in all_reqs)

        # 4. Admin approves the request
        decision_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={
                "action": "approve",
                "allocated_quota": 10000,
                "admin_notes": "Approved for 10k monthly SMS with 10DLC registration pending",
            },
            headers=admin_headers,
        )
        assert decision_resp.status_code == 200
        d_data = decision_resp.json()
        assert d_data["status"] == "approved"
        assert d_data["reviewing_admin_id"] == str(admin_user.id)

        # 5. Check persistent entitlement in test DB
        persisted_ent = (
            test_db_session.query(OrganizationChannelEntitlement)
            .filter(
                OrganizationChannelEntitlement.organization_id == uuid.UUID(org_id),
                OrganizationChannelEntitlement.channel == "sms",
            )
            .first()
        )
        assert persisted_ent is not None
        assert persisted_ent.is_unlocked is True
        assert persisted_ent.status == "approved"
        assert persisted_ent.allocated_quota == 10000

        # 6. Check tenant capabilities endpoint now shows SMS unlocked!
        cap_resp = await client.get("/api/v1/entitlements/channels", headers=tenant_headers)
        channels = {c["channel"]: c for c in cap_resp.json()["channels"]}
        assert channels["sms"]["status"] == "approved"
        assert channels["sms"]["is_unlocked"] is True
        assert channels["sms"]["allocated_quota"] == 10000

        # 7. Check audit log has upgrade_approved
        approval_audit = (
            test_db_session.query(EntitlementAuditLog)
            .filter(
                EntitlementAuditLog.organization_id == uuid.UUID(org_id),
                EntitlementAuditLog.action == "upgrade_approved",
            )
            .first()
        )
        assert approval_audit is not None
        assert approval_audit.actor_role == "superadmin"


@pytest.mark.asyncio
async def test_platform_admin_rejection_workflow(test_db_session):
    """Platform administrator rejection transitions request to rejected and keeps channel locked."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "reject_me@example.com", "Reject Tenant")
        tenant_headers = {"Authorization": f"Bearer {token}"}

        # 1. Request voice channel
        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={"channel": "voice", "estimated_volume": "5000 mins"},
            headers=tenant_headers,
        )
        req_id = req_resp.json()["request_id"]

        # 2. Admin rejects request
        admin_token, _ = create_platform_admin(test_db_session)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        decision_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={
                "action": "reject",
                "rejection_reason": "Account requires 30 days of clean email history before unlocking Voice SDR.",
            },
            headers=admin_headers,
        )
        assert decision_resp.status_code == 200
        assert decision_resp.json()["status"] == "rejected"
        assert "30 days" in decision_resp.json()["rejection_reason"]

        # 3. Channel remains locked
        cap_resp = await client.get("/api/v1/entitlements/channels", headers=tenant_headers)
        channels = {c["channel"]: c for c in cap_resp.json()["channels"]}
        assert channels["voice"]["is_unlocked"] is False


@pytest.mark.asyncio
async def test_admin_decision_rejects_invalid_quota(test_db_session):
    """Admin approval with negative or zero quota must be rejected with 422 Unprocessable Entity."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "quota_tenant@example.com", "Quota Tenant")
        tenant_headers = {"Authorization": f"Bearer {token}"}

        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={"channel": "sms"},
            headers=tenant_headers,
        )
        req_id = req_resp.json()["request_id"]

        admin_token, _ = create_platform_admin(test_db_session)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Negative quota
        neg_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={"action": "approve", "allocated_quota": -500},
            headers=admin_headers,
        )
        assert neg_resp.status_code == 422
        assert "positive integer" in neg_resp.text

        # Zero quota
        zero_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={"action": "approve", "allocated_quota": 0},
            headers=admin_headers,
        )
        assert zero_resp.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_admin_decisions_rejected(test_db_session):
    """Attempting a second decision on an already finalized upgrade request returns HTTP 400."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "dup_tenant@example.com", "Dup Tenant")
        tenant_headers = {"Authorization": f"Bearer {token}"}

        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={"channel": "sms"},
            headers=tenant_headers,
        )
        req_id = req_resp.json()["request_id"]

        admin_token, _ = create_platform_admin(test_db_session)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. First approval succeeds
        first_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={"action": "approve", "allocated_quota": 1000},
            headers=admin_headers,
        )
        assert first_resp.status_code == 200

        # 2. Second approval on same request returns 400
        second_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={"action": "approve", "allocated_quota": 2000},
            headers=admin_headers,
        )
        assert second_resp.status_code == 400
        assert "already finalized" in second_resp.text


@pytest.mark.asyncio
async def test_rejection_requires_mandatory_reason(test_db_session):
    """Declining an upgrade request without a non-empty rejection reason returns 422."""
    async with make_client() as client:
        token, org_id = await register_tenant(client, "no_reason@example.com", "No Reason Tenant")
        tenant_headers = {"Authorization": f"Bearer {token}"}

        req_resp = await client.post(
            "/api/v1/entitlements/upgrade-request",
            json={"channel": "voice"},
            headers=tenant_headers,
        )
        req_id = req_resp.json()["request_id"]

        admin_token, _ = create_platform_admin(test_db_session)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Reject without reason
        blank_resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{req_id}/decision",
            json={"action": "reject", "rejection_reason": "   "},
            headers=admin_headers,
        )
        assert blank_resp.status_code == 422
        assert "rejection reason is mandatory" in blank_resp.text


@pytest.mark.asyncio
async def test_non_existent_upgrade_request_returns_400(test_db_session):
    """Attempting a decision on a nonexistent request ID returns HTTP 400."""
    async with make_client() as client:
        admin_token, _ = create_platform_admin(test_db_session)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/entitlements/admin/upgrade-requests/{fake_id}/decision",
            json={"action": "approve", "allocated_quota": 500},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "not found" in resp.text
