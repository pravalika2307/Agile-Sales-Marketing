"""CRM domain models: Company and Contact."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.campaign import CampaignContact
    from app.models.outreach import Outreach
    from app.models.tenant import Organization

ALLOWED_LEAD_STATUSES = {
    "new",
    "contacted",
    "replied",
    "qualified",
    "unresponsive",
    "opted_out",
}

ALLOWED_DEAL_STATUSES = {
    "open",
    "won",
    "lost",
}


class Company(Base):
    """
    Target business account record.
    Belongs strictly to one Organization.
    """
    __tablename__ = "companies"

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
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    domain: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    employee_count_range: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    hubspot_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
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

    __table_args__ = (
        Index("ix_companies_org_hubspot_id", "organization_id", "hubspot_id"),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="companies",
    )
    contacts: Mapped[List[Contact]] = relationship(
        "Contact",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    deals: Mapped[List[Deal]] = relationship(
        "Deal",
        back_populates="company",
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} org_id={self.organization_id} name='{self.name}'>"


class Contact(Base):
    """
    Individual decision-maker prospect record.
    Belongs strictly to one Organization. Optionally references a Company within the same Organization.
    """
    __tablename__ = "contacts"

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
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    job_title: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    lead_status: Mapped[str] = mapped_column(
        String(50),
        default="new",
        nullable=False,
    )
    hubspot_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
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
        back_populates="contacts",
    )
    company: Mapped[Optional[Company]] = relationship(
        "Company",
        back_populates="contacts",
    )
    deals: Mapped[List[Deal]] = relationship(
        "Deal",
        back_populates="contact",
    )
    campaign_contacts: Mapped[List[CampaignContact]] = relationship(
        "CampaignContact",
        back_populates="contact",
        cascade="all, delete-orphan",
    )
    outreaches: Mapped[List[Outreach]] = relationship(
        "Outreach",
        back_populates="contact",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Fast composite lookups for tenant email queries
        Index("ix_contacts_org_email", "organization_id", "email"),
        Index("ix_contacts_org_hubspot_id", "organization_id", "hubspot_id"),
    )

    def __repr__(self) -> str:
        return f"<Contact id={self.id} org_id={self.organization_id} email='{self.email}' status='{self.lead_status}'>"


class Pipeline(Base):
    """
    Sales Pipeline representing a sales cycle workflow.
    Belongs strictly to one Organization.
    """
    __tablename__ = "pipelines"

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
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
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
        back_populates="pipelines",
    )
    stages: Mapped[List[PipelineStage]] = relationship(
        "PipelineStage",
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="PipelineStage.order_index",
    )

    def __repr__(self) -> str:
        return f"<Pipeline id={self.id} org_id={self.organization_id} name='{self.name}' is_default={self.is_default}>"


class PipelineStage(Base):
    """
    Stage within a sales pipeline with ordering and probability weight.
    """
    __tablename__ = "pipeline_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
    probability_pct: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
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
    pipeline: Mapped[Pipeline] = relationship(
        "Pipeline",
        back_populates="stages",
    )
    deals: Mapped[List[Deal]] = relationship(
        "Deal",
        back_populates="pipeline_stage",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("probability_pct >= 0 AND probability_pct <= 100", name="ck_pipeline_stages_probability_pct"),
        Index("ix_pipeline_stages_pipeline_order", "pipeline_id", "order_index"),
    )

    def __repr__(self) -> str:
        return f"<PipelineStage id={self.id} pipeline_id={self.pipeline_id} name='{self.name}' order={self.order_index}>"


class Deal(Base):
    """
    Sales opportunity record representing a commercial deal.
    Belongs strictly to one Organization, requires a PipelineStage, and optionally links to Contact and Company.
    """
    __tablename__ = "deals"

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
    pipeline_stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pipeline_stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(
        Numeric(14, 2),
        default=0.00,
        nullable=False,
    )
    expected_close_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="open",
        nullable=False,
        index=True,
    )
    hubspot_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
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
        back_populates="deals",
    )
    pipeline_stage: Mapped[PipelineStage] = relationship(
        "PipelineStage",
        back_populates="deals",
    )
    contact: Mapped[Optional[Contact]] = relationship(
        "Contact",
        back_populates="deals",
    )
    company: Mapped[Optional[Company]] = relationship(
        "Company",
        back_populates="deals",
    )

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_deals_amount_non_negative"),
        CheckConstraint("status IN ('open', 'won', 'lost')", name="ck_deals_status"),
        Index("ix_deals_org_hubspot_id", "organization_id", "hubspot_id"),
    )

    def __repr__(self) -> str:
        return f"<Deal id={self.id} org_id={self.organization_id} name='{self.name}' status='{self.status}' amount={self.amount}>"
