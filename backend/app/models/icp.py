"""Ideal Customer Profile (ICP) domain model for B2B lead generation (Step 11)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IdealCustomerProfile(Base):
    """
    Defines target persona and firmographic criteria for prospect search and lead qualification.
    Tenant-scoped to Organization.
    """
    __tablename__ = "ideal_customer_profiles"

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
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Firmographic criteria (Company level)
    industries: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    company_size_min: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    company_size_max: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    countries: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    cities: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    company_domains: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Persona criteria (Contact level)
    job_titles: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    seniority_levels: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    departments: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Additional criteria
    technologies: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    keywords: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Status & Timestamps
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
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
    organization = relationship(
        "Organization",
        back_populates="ideal_customer_profiles",
    )
    leads = relationship(
        "Lead",
        back_populates="icp",
    )

    __table_args__ = (
        CheckConstraint(
            "company_size_min IS NULL OR company_size_min >= 0",
            name="ck_icp_company_size_min",
        ),
        CheckConstraint(
            "company_size_min IS NULL OR company_size_max IS NULL OR company_size_max >= company_size_min",
            name="ck_icp_company_size_max",
        ),
    )

    def __repr__(self) -> str:
        return f"<IdealCustomerProfile id={self.id} org_id={self.organization_id} name='{self.name}'>"
