"""Isolated unit and integration tests for duplicate email error handling on contact updates.

Validates:
A. Updating a contact to an unused email succeeds.
B. Updating a contact to its existing email succeeds.
C. Updating a contact to another contact's email in the same organization returns HTTP 409.
D. Updating a contact to an email used only in another organization succeeds.
E. Email capitalization and whitespace are normalized consistently.
F. A failed update rolls back cleanly and does not leave the database session in a failed state.
G. An unrelated IntegrityError is not incorrectly reported as a duplicate-email error.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.crm import Contact
from app.schemas.contact import ContactCreate, ContactUpdate
from app.services import contact_service
from app.services.contact_service import DuplicateContactError, _is_duplicate_email_error


@pytest.fixture
def test_db_session():
    """Create fresh isolated in-memory SQLite database session for each test."""
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


@pytest.fixture(scope="module")
def pg_engine():
    """Connect to live PostgreSQL database configured in settings."""
    engine = create_engine(settings.DATABASE_URL)
    yield engine
    engine.dispose()


@asynccontextmanager
async def make_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def register_tenant(client: AsyncClient, email: str, org_name: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Tenant Admin",
            "organization_name": org_name,
        },
    )
    assert resp.status_code == 201
    return resp.json()["tokens"]["access_token"]


# ── TEST A: Updating a contact to an unused email succeeds ────────────────────

@pytest.mark.asyncio
async def test_case_a_update_to_unused_email_succeeds(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_case_a@org.com", "Case A Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create contact
        c_resp = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "old.email@company.com", "first_name": "Alice", "last_name": "Smith"},
        )
        assert c_resp.status_code == 201
        contact_id = c_resp.json()["id"]

        # Update to unused email
        patch_resp = await client.patch(
            f"/api/v1/contacts/{contact_id}",
            headers=headers,
            json={"email": "new.email@company.com"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["email"] == "new.email@company.com"


# ── TEST B: Updating a contact to its existing email succeeds ─────────────────

@pytest.mark.asyncio
async def test_case_b_update_to_existing_email_succeeds(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_case_b@org.com", "Case B Org")
        headers = {"Authorization": f"Bearer {token}"}

        c_resp = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "self.same@company.com", "first_name": "Bob", "last_name": "Jones"},
        )
        assert c_resp.status_code == 201
        contact_id = c_resp.json()["id"]

        # Update sending the exact same email alongside other fields
        patch_resp = await client.patch(
            f"/api/v1/contacts/{contact_id}",
            headers=headers,
            json={"email": "self.same@company.com", "first_name": "Robert"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["first_name"] == "Robert"
        assert patch_resp.json()["email"] == "self.same@company.com"


# ── TEST C: Updating to another contact's email in same org returns HTTP 409 ──

@pytest.mark.asyncio
async def test_case_c_update_to_duplicate_email_returns_409(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_case_c@org.com", "Case C Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Contact 1
        c1 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "primary@company.com", "first_name": "Charlie", "last_name": "One"},
        )
        assert c1.status_code == 201

        # Contact 2
        c2 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "secondary@company.com", "first_name": "Charlie", "last_name": "Two"},
        )
        assert c2.status_code == 201
        c2_id = c2.json()["id"]

        # Attempt to change Contact 2's email to Contact 1's email
        patch_resp = await client.patch(
            f"/api/v1/contacts/{c2_id}",
            headers=headers,
            json={"email": "primary@company.com"},
        )
        assert patch_resp.status_code == 409
        body = patch_resp.json()
        assert "already exists in this organization" in body["detail"]


# ── TEST D: Updating to email used only in another org succeeds ───────────────

@pytest.mark.asyncio
async def test_case_d_update_to_other_org_email_succeeds(test_db_session: Session):
    async with make_client() as client:
        token_a = await register_tenant(client, "admin_case_da@org.com", "Org D-A")
        token_b = await register_tenant(client, "admin_case_db@org.com", "Org D-B")

        # Org A has contact with shared email
        shared_email = "universal.partner@corp.com"
        await client.post(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"email": shared_email, "first_name": "Partner", "last_name": "A"},
        )

        # Org B creates contact with distinct email
        c_b = await client.post(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"email": "b.original@corp.com", "first_name": "Partner", "last_name": "B"},
        )
        assert c_b.status_code == 201
        cb_id = c_b.json()["id"]

        # Org B updates contact to the shared email (allowed by tenant isolation)
        patch_resp = await client.patch(
            f"/api/v1/contacts/{cb_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"email": shared_email},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["email"] == shared_email


# ── TEST E: Email capitalization and whitespace are normalized consistently ───

@pytest.mark.asyncio
async def test_case_e_email_capitalization_and_whitespace_normalized(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_case_e@org.com", "Case E Org")
        headers = {"Authorization": f"Bearer {token}"}

        c = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "start.user@domain.com", "first_name": "Edward", "last_name": "Norton"},
        )
        assert c.status_code == 201
        c_id = c.json()["id"]

        # Update with leading/trailing whitespace and mixed case
        patch_resp = await client.patch(
            f"/api/v1/contacts/{c_id}",
            headers=headers,
            json={"email": "  EDWARD.NORTON@Domain.COM  "},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["email"] == "edward.norton@domain.com"

        # Create another contact
        c2 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "other@domain.com", "first_name": "Other", "last_name": "User"},
        )
        assert c2.status_code == 201
        c2_id = c2.json()["id"]

        # Attempt to update c2 with whitespace/caps matching c1
        conflict_patch = await client.patch(
            f"/api/v1/contacts/{c2_id}",
            headers=headers,
            json={"email": "  edward.norton@DOMAIN.com "},
        )
        assert conflict_patch.status_code == 409


# ── TEST F: Failed update rolls back cleanly without session corruption ───────

@pytest.mark.asyncio
async def test_case_f_failed_update_rolls_back_cleanly(test_db_session: Session):
    async with make_client() as client:
        token = await register_tenant(client, "admin_case_f@org.com", "Case F Org")
        headers = {"Authorization": f"Bearer {token}"}

        # Create Contact 1 and Contact 2
        c1 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "c1@testorg.com", "first_name": "First", "last_name": "One"},
        )
        c2 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "c2@testorg.com", "first_name": "Second", "last_name": "Two"},
        )
        c2_id = c2.json()["id"]

        # Failed update attempt: try to rename c2 email to c1
        fail_resp = await client.patch(
            f"/api/v1/contacts/{c2_id}",
            headers=headers,
            json={"email": "c1@testorg.com"},
        )
        assert fail_resp.status_code == 409

        # Confirm session is not broken: c2 still exists and is untouched
        get_c2 = await client.get(f"/api/v1/contacts/{c2_id}", headers=headers)
        assert get_c2.status_code == 200
        assert get_c2.json()["email"] == "c2@testorg.com"

        # Subsequent insert in same session succeeds
        c3 = await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"email": "c3@testorg.com", "first_name": "Third", "last_name": "Three"},
        )
        assert c3.status_code == 201


# ── TEST G: Unrelated IntegrityError is not reported as duplicate-email ───────

def test_case_g_unrelated_integrity_error_is_not_masked():
    # 1. Verify classifier logic directly
    dup_pg_exc = IntegrityError("statement", {}, Exception('duplicate key value violates unique constraint "uq_contacts_org_lower_email"'))
    assert _is_duplicate_email_error(dup_pg_exc) is True

    dup_sqlite_exc = IntegrityError("statement", {}, Exception("UNIQUE constraint failed: contacts.organization_id, contacts.email"))
    assert _is_duplicate_email_error(dup_sqlite_exc) is True

    fk_exc = IntegrityError("statement", {}, Exception('insert or update on table "contacts" violates foreign key constraint "fk_contacts_company_id"'))
    assert _is_duplicate_email_error(fk_exc) is False

    hubspot_exc = IntegrityError("statement", {}, Exception('duplicate key value violates unique constraint "uq_contacts_org_hubspot_id"'))
    assert _is_duplicate_email_error(hubspot_exc) is False

    not_null_exc = IntegrityError("statement", {}, Exception('null value in column "first_name" violates not-null constraint'))
    assert _is_duplicate_email_error(not_null_exc) is False

    # 2. Verify update_contact re-raises unrelated IntegrityError
    mock_db = MagicMock(spec=Session)
    mock_contact = MagicMock(spec=Contact)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_contact
    mock_db.commit.side_effect = fk_exc

    with pytest.raises(IntegrityError):
        contact_service.update_contact(
            mock_db,
            uuid.uuid4(),
            uuid.uuid4(),
            ContactUpdate(first_name="TestName"),
        )
    mock_db.rollback.assert_called_once()
