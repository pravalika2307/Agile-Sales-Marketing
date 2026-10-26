"""Tenant and User domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.business import BusinessProfile
    from app.models.campaign import Campaign
    from app.models.crm import Company, Contact, Deal, Pipeline
    from app.models.icp import IdealCustomerProfile
    from app.models.lead import Lead
    from app.models.outreach import Outreach
    from app.models.linkedin import LinkedInConnection


class Organization(Base):
    """
    Tenant root representing a subscribing business or organization.
    Owns all domain data and users.
    """
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    billing_status: Mapped[str] = mapped_column(
        String(50),
        default="trial",
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
    users: Mapped[List[User]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    business_profile: Mapped[Optional[BusinessProfile]] = relationship(
        "BusinessProfile",
        back_populates="organization",
        uselist=False,
        cascade="all, delete-orphan",
    )
    companies: Mapped[List[Company]] = relationship(
        "Company",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[List[Contact]] = relationship(
        "Contact",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    pipelines: Mapped[List[Pipeline]] = relationship(
        "Pipeline",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    deals: Mapped[List[Deal]] = relationship(
        "Deal",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    campaigns: Mapped[List[Campaign]] = relationship(
        "Campaign",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    outreaches: Mapped[List[Outreach]] = relationship(
        "Outreach",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    ideal_customer_profiles: Mapped[List[IdealCustomerProfile]] = relationship(
        "IdealCustomerProfile",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    leads: Mapped[List[Lead]] = relationship(
        "Lead",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    linkedin_connection: Mapped[Optional[LinkedInConnection]] = relationship(
        "LinkedInConnection",
        back_populates="organization",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name='{self.name}' slug='{self.slug}'>"


class User(Base):
    """
    User account belonging to an organization.
    """
    __tablename__ = "users"

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
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default="member",
        nullable=False,
    )
    access_level: Mapped[str] = mapped_column(
        String(20),
        default="both",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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
        back_populates="users",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' org_id={self.organization_id}>"
