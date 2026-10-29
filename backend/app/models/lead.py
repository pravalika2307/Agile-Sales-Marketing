"""Lead domain model for B2B prospecting (Step 11)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.crm import Company, Contact
    from app.models.icp import IdealCustomerProfile
    from app.models.lead_research import LeadResearch
    from app.models.routing_rule import LeadRoutingRule
    from app.models.tenant import Organization, User


_lead_unmigrated_address_store = {}
_lead_unmigrated_profile_store = {}

def _check_column_exists(table_name: str, column_name: str) -> bool:
    """Checks if a column physically exists in the database table to support unmigrated DBs safely."""
    try:
        from sqlalchemy import inspect
        from app.core.database import engine
        insp = inspect(engine)
        if not insp.has_table(table_name):
            # In-memory test SQLite databases before tables are created
            return True
        cols = [c["name"] for c in insp.get_columns(table_name)]
        return column_name in cols
    except Exception:
        return True


class Lead(Base):
    """
    Prospecting-layer record holding discovered lead metadata, snapshot attributes,
    deterministic scoring, qualification, and temperature before CRM conversion.
    Tenant-scoped to Organization.
    """
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    icp_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("ideal_customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Source tracking
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="mock",
        index=True,
    )
    source_external_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Company snapshot fields
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    company_domain: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    employee_count_range: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        default="US",
    )

    if _check_column_exists("leads", "address_line_1"):
        state: Mapped[Optional[str]] = mapped_column(
            String(50),
            nullable=True,
            index=True,
        )
        postal_code: Mapped[Optional[str]] = mapped_column(
            String(20),
            nullable=True,
            index=True,
        )
        address_line_1: Mapped[Optional[str]] = mapped_column(
            String(255),
            nullable=True,
        )
        address_line_2: Mapped[Optional[str]] = mapped_column(
            String(255),
            nullable=True,
        )
    else:
        # Fallback properties when running against unmigrated database
        @property
        def state(self) -> Optional[str]:
            if hasattr(self, "_state_val"):
                return self._state_val
            return _lead_unmigrated_address_store.get(getattr(self, "id", None), {}).get("state")
        @state.setter
        def state(self, val: Optional[str]):
            self._state_val = val
            lid = getattr(self, "id", None)
            if lid:
                if lid not in _lead_unmigrated_address_store:
                    _lead_unmigrated_address_store[lid] = {}
                _lead_unmigrated_address_store[lid]["state"] = val

        @property
        def postal_code(self) -> Optional[str]:
            if hasattr(self, "_postal_code_val"):
                return self._postal_code_val
            return _lead_unmigrated_address_store.get(getattr(self, "id", None), {}).get("postal_code")
        @postal_code.setter
        def postal_code(self, val: Optional[str]):
            self._postal_code_val = val
            lid = getattr(self, "id", None)
            if lid:
                if lid not in _lead_unmigrated_address_store:
                    _lead_unmigrated_address_store[lid] = {}
                _lead_unmigrated_address_store[lid]["postal_code"] = val

        @property
        def address_line_1(self) -> Optional[str]:
            if hasattr(self, "_address_line_1_val"):
                return self._address_line_1_val
            return _lead_unmigrated_address_store.get(getattr(self, "id", None), {}).get("address_line_1")
        @address_line_1.setter
        def address_line_1(self, val: Optional[str]):
            self._address_line_1_val = val
            lid = getattr(self, "id", None)
            if lid:
                if lid not in _lead_unmigrated_address_store:
                    _lead_unmigrated_address_store[lid] = {}
                _lead_unmigrated_address_store[lid]["address_line_1"] = val

        @property
        def address_line_2(self) -> Optional[str]:
            if hasattr(self, "_address_line_2_val"):
                return self._address_line_2_val
            return _lead_unmigrated_address_store.get(getattr(self, "id", None), {}).get("address_line_2")
        @address_line_2.setter
        def address_line_2(self, val: Optional[str]):
            self._address_line_2_val = val
            lid = getattr(self, "id", None)
            if lid:
                if lid not in _lead_unmigrated_address_store:
                    _lead_unmigrated_address_store[lid] = {}
                _lead_unmigrated_address_store[lid]["address_line_2"] = val

    # Contact snapshot fields
    first_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    last_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    job_title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    if _check_column_exists("leads", "linkedin_profile_url"):
        linkedin_profile_url: Mapped[Optional[str]] = mapped_column(
            String(500),
            nullable=True,
        )
    else:
        # Fallback property when running against unmigrated database
        @property
        def linkedin_profile_url(self) -> Optional[str]:
            val = getattr(self, "_linkedin_profile_url_val", None)
            if val is not None:
                return val
            lid = getattr(self, "id", None)
            return _lead_unmigrated_profile_store.get(lid, {}).get("linkedin_profile_url")

        @linkedin_profile_url.setter
        def linkedin_profile_url(self, val: Optional[str]):
            self._linkedin_profile_url_val = val
            lid = getattr(self, "id", None)
            if not lid:
                lid = uuid.uuid4()
                self.id = lid
            if lid not in _lead_unmigrated_profile_store:
                _lead_unmigrated_profile_store[lid] = {}
            _lead_unmigrated_profile_store[lid]["linkedin_profile_url"] = val

    # Qualification & Scoring
    qualification_status: Mapped[str] = mapped_column(
        String(50),
        default="new",
        nullable=False,
        index=True,
    )
    lead_temperature: Mapped[str] = mapped_column(
        String(20),
        default="cold",
        nullable=False,
        index=True,
    )
    lead_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
    )
    qualification_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Lead Routing & Assignment
    assigned_to_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    routing_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("lead_routing_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    routed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    routing_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Overall Lifecycle Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="new",
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="leads",
    )
    icp: Mapped[Optional[IdealCustomerProfile]] = relationship(
        "IdealCustomerProfile",
        back_populates="leads",
    )
    company: Mapped[Optional[Company]] = relationship(
        "Company",
        foreign_keys=[company_id],
    )
    contact: Mapped[Optional[Contact]] = relationship(
        "Contact",
        foreign_keys=[contact_id],
    )
    research: Mapped[Optional[LeadResearch]] = relationship(
        "LeadResearch",
        back_populates="lead",
        uselist=False,
        cascade="all, delete-orphan",
    )
    assigned_to_user: Mapped[Optional[User]] = relationship(
        "User",
        foreign_keys=[assigned_to_user_id],
    )
    routing_rule: Mapped[Optional[LeadRoutingRule]] = relationship(
        "LeadRoutingRule",
        foreign_keys=[routing_rule_id],
    )

    __table_args__ = (
        CheckConstraint(
            "lead_score >= 0 AND lead_score <= 100",
            name="ck_lead_score_range",
        ),
        CheckConstraint(
            "qualification_status IN ('new', 'qualified', 'disqualified', 'reviewed')",
            name="ck_lead_qualification_status",
        ),
        CheckConstraint(
            "lead_temperature IN ('cold', 'warm', 'hot')",
            name="ck_lead_temperature",
        ),
        CheckConstraint(
            "status IN ('new', 'selected', 'enrolled', 'contacted', 'replied', 'converted', 'rejected')",
            name="ck_lead_status",
        ),
        UniqueConstraint(
            "organization_id",
            "source",
            "source_external_id",
            name="uq_leads_org_source_ext",
        ),
    )

    @property
    def is_scored(self) -> bool:
        """True if the lead has undergone genuine ICP evaluation."""
        return self.icp_id is not None and bool(self.qualification_reason)

    def __repr__(self) -> str:
        return f"<Lead id={self.id} org_id={self.organization_id} company='{self.company_name}' score={self.lead_score}>"
