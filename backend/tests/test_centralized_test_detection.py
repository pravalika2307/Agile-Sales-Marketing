"""Tests for Centralized Test-Data Detection & Ingestion Safeguards."""
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.test_detection import classify_is_test
from app.models.tenant import Organization
from app.models.lead import Lead
from app.models.crm import Contact
from app.schemas.lead import LeadCreate, LeadImportRow
from app.schemas.contact import ContactCreate
from app.services.lead_generation.service import create_lead, import_leads, list_leads
from app.services.contact_service import create_contact, list_contacts
from app.services.integrations.hubspot.sync import HubSpotSyncEngine


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
        yield session
    finally:
        session.close()


class TestClassifyIsTestHelper:
    """Direct unit tests for classify_is_test logic."""

    def test_explicit_flag_true(self):
        assert classify_is_test(explicit_is_test=True) is True
        assert classify_is_test(explicit_is_test=True, email="client@legitcompany.com") is True

    def test_test_domains_and_suffixes(self):
        assert classify_is_test(email="gordon@blackmesa.org") is True
        assert classify_is_test(email="sub@dept.blackmesa.org") is True
        assert classify_is_test(email="tester@testacme.com") is True
        assert classify_is_test(email="qa@agiletesting.local") is True
        assert classify_is_test(email="person@example.com") is True
        assert classify_is_test(email="person@sub.example.com") is True
        assert classify_is_test(email="user@site.test") is True
        assert classify_is_test(email="user@site.invalid") is True
        assert classify_is_test(email="user@site.localhost") is True

    def test_automated_test_prefixes(self):
        assert classify_is_test(email="csvtest_15ded1@randomcompany.com") is True
        assert classify_is_test(email="tunnel_test@domain.com") is True
        assert classify_is_test(email="test@somebusiness.com") is True
        assert classify_is_test(email="test2@somebusiness.com") is True
        assert classify_is_test(email="qa1@somebusiness.com") is True
        assert classify_is_test(email="alice+test@realcorp.com") is True
        assert classify_is_test(email="alice+qa@realcorp.com") is True
        assert classify_is_test(email="nina.patel.demo@realcorp.com") is True

    def test_test_names(self):
        assert classify_is_test(first_name="Test", last_name="Prospect") is True
        assert classify_is_test(first_name="QA", last_name="Tester") is True
        assert classify_is_test(first_name="Poplar QA", last_name="Test Contact") is True
        assert classify_is_test(first_name="Demo", last_name="User") is True

    def test_test_companies(self):
        assert classify_is_test(company_name="Black Mesa Research Facility") is True
        assert classify_is_test(company_name="Test Company Inc") is True
        assert classify_is_test(company_name="Acme Test Labs") is True

    def test_test_sources(self):
        assert classify_is_test(source="mock") is True
        assert classify_is_test(source="synthetic") is True
        assert classify_is_test(source="test") is True

    def test_bypass_prevention_explicit_false(self):
        """Passing explicit_is_test=False MUST NOT bypass classification for test domains."""
        assert classify_is_test(explicit_is_test=False, email="eli@blackmesa.org") is True
        assert classify_is_test(explicit_is_test=False, email="user@example.com") is True
        assert classify_is_test(explicit_is_test=False, first_name="Test", last_name="User") is True

    def test_genuine_records_not_flagged(self):
        """Genuine records with valid business domains or Arabic/uncommon names must be False."""
        assert classify_is_test(email="sarah.connor@cyberdyne-defense.com", first_name="Sarah", last_name="Connor") is False
        assert classify_is_test(email="tariq.alqasimi@gulfholdings.ae", first_name="Tariq", last_name="Al-Qasimi") is False
        assert classify_is_test(email="farooq@qasimpllc.com", first_name="Farooq", last_name="Qasim") is False
        assert classify_is_test(email="pravalikapalle@agilereceivables.com", first_name="Pravalika", last_name="Palle") is False
        assert classify_is_test(email="jerome.zech@collectly.co", first_name="Jerome", last_name="Zech") is False
        assert classify_is_test(email="pam@promenasetthestandard.com", first_name="Pamela", last_name="McElvane") is False


class TestIngestionPathways:
    """Integration tests verifying is_test propagation across DB ingestion pathways."""

    @pytest.fixture
    def test_org(self, test_db_session: Session) -> Organization:
        org = Organization(name=f"Detection Test Org {uuid.uuid4().hex[:6]}", slug=f"detection-test-{uuid.uuid4().hex[:6]}")
        test_db_session.add(org)
        test_db_session.commit()
        test_db_session.refresh(org)
        return org

    def test_create_lead_classification(self, test_db_session: Session, test_org: Organization):
        # 1. Test lead with Black Mesa domain
        lead_data = LeadCreate(
            company_name="Black Mesa Research",
            email="barney@blackmesa.org",
            first_name="Barney",
            last_name="Calhoun",
        )
        lead = create_lead(test_db_session, test_org, lead_data)
        assert lead.is_test is True
        # Verify linked contact also classified as test
        assert lead.contact_id is not None
        contact = test_db_session.query(Contact).filter(Contact.id == lead.contact_id).first()
        assert contact is not None
        assert contact.is_test is True

        # 2. Genuine lead
        genuine_data = LeadCreate(
            company_name="Genuine Client Corp",
            email=f"client_{uuid.uuid4().hex[:6]}@genuineclientcorp.com",
            first_name="Robert",
            last_name="Paulson",
        )
        gen_lead = create_lead(test_db_session, test_org, genuine_data)
        assert gen_lead.is_test is False
        assert gen_lead.contact_id is not None
        gen_contact = test_db_session.query(Contact).filter(Contact.id == gen_lead.contact_id).first()
        assert gen_contact is not None
        assert gen_contact.is_test is False

    def test_import_leads_csv_classification(self, test_db_session: Session, test_org: Organization):
        rows = [
            LeadImportRow(
                company_name="Test Company",
                email="test_csv_1@example.com",
                first_name="Test",
                last_name="CSV1",
            ),
            LeadImportRow(
                company_name="Black Mesa",
                email="scientist@blackmesa.org",
                first_name="Science",
                last_name="Team",
            ),
            LeadImportRow(
                company_name="Production Corp",
                email=f"real_user_{uuid.uuid4().hex[:6]}@productioncorp.com",
                first_name="Alice",
                last_name="Smith",
            ),
            LeadImportRow(
                company_name="Explicit Test Row",
                email=f"custom_email_{uuid.uuid4().hex[:6]}@somehost.com",
                first_name="Explicit",
                last_name="Tester",
                is_test=True,
            ),
        ]
        resp = import_leads(test_db_session, test_org, rows)
        assert resp.imported_count == 4

        leads = test_db_session.query(Lead).filter(Lead.id.in_(resp.imported_ids)).all()
        leads_by_email = {l.email: l for l in leads}

        assert leads_by_email["test_csv_1@example.com"].is_test is True
        assert leads_by_email["scientist@blackmesa.org"].is_test is True
        assert leads_by_email[rows[2].email].is_test is False
        assert leads_by_email[rows[3].email].is_test is True

    def test_create_contact_classification(self, test_db_session: Session, test_org: Organization):
        # 1. Contact with test domain
        c_data_test = ContactCreate(
            first_name="QA",
            last_name="Engineer",
            email="qa_eng@testacme.com",
        )
        c_test = create_contact(test_db_session, test_org.id, c_data_test)
        assert c_test.is_test is True

        # 2. Contact attempting bypass with explicit False
        c_data_bypass = ContactCreate(
            first_name="Gordon",
            last_name="Freeman",
            email="freeman@blackmesa.org",
            is_test=False,
        )
        c_bypass = create_contact(test_db_session, test_org.id, c_data_bypass)
        assert c_bypass.is_test is True

        # 3. Genuine contact
        c_data_gen = ContactCreate(
            first_name="Elena",
            last_name="Rostova",
            email=f"elena_{uuid.uuid4().hex[:6]}@rostovaindustries.com",
        )
        c_gen = create_contact(test_db_session, test_org.id, c_data_gen)
        assert c_gen.is_test is False

    @pytest.mark.asyncio
    async def test_hubspot_sync_classification(self, test_db_session: Session, test_org: Organization):
        class MockClient:
            is_configured = True
            async def get(self, endpoint, params=None, check_status=True):
                class MockResponse:
                    status_code = 200
                    def json(self):
                        return {
                            "results": [
                                {
                                    "id": f"hs_{uuid.uuid4().hex[:8]}",
                                    "properties": {
                                        "email": "sandbox_user@example.com",
                                        "firstname": "Sandbox",
                                        "lastname": "User",
                                        "company": "Sandbox Corp",
                                    },
                                    "associations": {},
                                },
                                {
                                    "id": f"hs_{uuid.uuid4().hex[:8]}",
                                    "properties": {
                                        "email": f"genuine_hs_{uuid.uuid4().hex[:6]}@clientcompany.com",
                                        "firstname": "Genuine",
                                        "lastname": "Client",
                                        "company": "Client Company",
                                    },
                                    "associations": {},
                                },
                            ],
                            "paging": {},
                        }
                return MockResponse()

        engine = HubSpotSyncEngine(client=MockClient())
        res = await engine.sync_contacts(test_db_session, test_org.id)
        assert res.status == "synced"

        # Check imported contacts
        c_test = test_db_session.query(Contact).filter(
            Contact.organization_id == test_org.id,
            Contact.email == "sandbox_user@example.com"
        ).first()
        assert c_test is not None
        assert c_test.is_test is True

        l_test = test_db_session.query(Lead).filter(
            Lead.organization_id == test_org.id,
            Lead.email == "sandbox_user@example.com"
        ).first()
        assert l_test is not None
        assert l_test.is_test is True

        # Check genuine contact
        c_gen = test_db_session.query(Contact).filter(
            Contact.organization_id == test_org.id,
            Contact.email.like("genuine_hs_%@clientcompany.com")
        ).first()
        assert c_gen is not None
        assert c_gen.is_test is False

        l_gen = test_db_session.query(Lead).filter(
            Lead.organization_id == test_org.id,
            Lead.email.like("genuine_hs_%@clientcompany.com")
        ).first()
        assert l_gen is not None
        assert l_gen.is_test is False
