"""Tests for Dedicated QA Organization Isolation & Production Data Safeguards."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.qa_safeguard import (
    PRODUCTION_ORG_ID,
    PRODUCTION_ORG_SLUG,
    QA_SANDBOX_ORG_ID,
    QA_SANDBOX_SLUG,
    QA_LEGACY_SLUG,
    ProductionDataProtectionError,
    AmbiguousOrganizationError,
    QASandboxNotFoundError,
    assert_safe_test_organization,
    get_qa_organization,
    resolve_script_target_organization,
    install_production_mutation_guard,
)
from app.models.tenant import Organization, User
from app.models.lead import Lead
from app.models.crm import Contact
from app.core.security import create_access_token, verify_password


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
    try:
        # Seed test database with both the mock production org and QA sandbox org
        prod_org = Organization(
            id=PRODUCTION_ORG_ID,
            name="Agile Sales & Marketing",
            slug=PRODUCTION_ORG_SLUG,
        )
        qa_org = Organization(
            id=QA_SANDBOX_ORG_ID,
            name="Agile QA Sandbox",
            slug=QA_SANDBOX_SLUG,
        )
        session.add_all([prod_org, qa_org])
        session.commit()
        yield session
    finally:
        session.close()


class TestProductionProtectionGuard:
    """Tests asserting that production organization can never be targeted by test routines."""

    def test_production_id_raises_error(self, monkeypatch):
        monkeypatch.delenv("ALLOW_PRODUCTION_CRM_MUTATION", raising=False)
        with pytest.raises(ProductionDataProtectionError) as exc_info:
            assert_safe_test_organization(PRODUCTION_ORG_ID)
        assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)
        assert str(PRODUCTION_ORG_ID) in str(exc_info.value)

    def test_production_string_id_raises_error(self, monkeypatch):
        monkeypatch.delenv("ALLOW_PRODUCTION_CRM_MUTATION", raising=False)
        with pytest.raises(ProductionDataProtectionError):
            assert_safe_test_organization(str(PRODUCTION_ORG_ID))

    def test_qa_sandbox_id_is_permitted(self):
        # Should not raise
        assert_safe_test_organization(QA_SANDBOX_ORG_ID)
        assert_safe_test_organization(str(QA_SANDBOX_ORG_ID))

    def test_arbitrary_test_org_id_is_permitted(self):
        test_uuid = uuid.uuid4()
        assert_safe_test_organization(test_uuid)

    def test_explicit_override_allows_production_mutation(self, monkeypatch):
        monkeypatch.setenv("ALLOW_PRODUCTION_CRM_MUTATION", "true")
        # Should not raise when override is explicitly present
        assert_safe_test_organization(PRODUCTION_ORG_ID)


class TestQASandboxResolvers:
    """Tests for resolving the official QA organization and script targets."""

    def test_get_qa_organization_by_id(self, test_db_session: Session):
        org = get_qa_organization(test_db_session)
        assert org is not None
        assert org.id == QA_SANDBOX_ORG_ID

    def test_get_qa_organization_by_legacy_slug(self, test_db_session: Session):
        # Temporarily change QA org ID to verify fallback to legacy slug
        qa_org = test_db_session.query(Organization).filter(Organization.id == QA_SANDBOX_ORG_ID).first()
        qa_org.id = uuid.uuid4()
        qa_org.slug = QA_LEGACY_SLUG
        test_db_session.commit()

        resolved = get_qa_organization(test_db_session)
        assert resolved is not None
        assert resolved.slug == QA_LEGACY_SLUG

    def test_get_qa_organization_not_found_raises(self, test_db_session: Session):
        # Remove QA org from DB
        test_db_session.query(Organization).filter(
            Organization.id.in_([QA_SANDBOX_ORG_ID])
        ).delete()
        test_db_session.commit()

        with pytest.raises(QASandboxNotFoundError):
            get_qa_organization(test_db_session)

    def test_resolve_script_target_blocks_production_id(self, test_db_session: Session, monkeypatch):
        monkeypatch.delenv("ALLOW_PRODUCTION_CRM_MUTATION", raising=False)
        with pytest.raises(ProductionDataProtectionError):
            resolve_script_target_organization(test_db_session, target_id=PRODUCTION_ORG_ID)

    def test_resolve_script_target_blocks_production_slug(self, test_db_session: Session, monkeypatch):
        monkeypatch.delenv("ALLOW_PRODUCTION_CRM_MUTATION", raising=False)
        with pytest.raises(ProductionDataProtectionError):
            resolve_script_target_organization(test_db_session, target_slug=PRODUCTION_ORG_SLUG)

    def test_resolve_script_target_defaults_to_qa_sandbox(self, test_db_session: Session):
        org = resolve_script_target_organization(test_db_session)
        assert org.id == QA_SANDBOX_ORG_ID

    def test_resolve_script_target_fails_closed_when_disallowing_default(self, test_db_session: Session):
        with pytest.raises(AmbiguousOrganizationError):
            resolve_script_target_organization(test_db_session, allow_default_to_qa=False)


class TestSessionMutationGuard:
    """Tests intercepting raw ORM flushes that attempt to mutate production."""

    def test_install_guard_blocks_production_lead_insert(self, test_db_session: Session, monkeypatch):
        monkeypatch.delenv("ALLOW_PRODUCTION_CRM_MUTATION", raising=False)
        install_production_mutation_guard(test_db_session)

        # Attempting to flush a Lead pointing to production tenant
        bad_lead = Lead(
            id=uuid.uuid4(),
            organization_id=PRODUCTION_ORG_ID,
            company_name="Malicious Lead",
            email="bad@exploratory.test",
        )
        test_db_session.add(bad_lead)

        with pytest.raises(ProductionDataProtectionError) as exc_info:
            test_db_session.flush()
        assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)
        assert "leads" in str(exc_info.value)

        test_db_session.rollback()

    def test_install_guard_allows_qa_sandbox_lead_insert(self, test_db_session: Session):
        install_production_mutation_guard(test_db_session)

        qa_lead = Lead(
            id=uuid.uuid4(),
            organization_id=QA_SANDBOX_ORG_ID,
            company_name="Safe Sandbox Lead",
            email="sandbox@agiletesting.local",
            is_test=True,
        )
        test_db_session.add(qa_lead)
        # Flush should succeed cleanly
        test_db_session.flush()
        assert qa_lead.id is not None
