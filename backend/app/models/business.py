"""Business Profile domain model."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.tenant import Organization


class BusinessProfile(Base):
    """
    Business context and Ideal Customer Profile (ICP) definition.
    Maintains a strict 1:1 relationship with Organization.
    """
    __tablename__ = "business_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    target_icp_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    value_proposition: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    website_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
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
        back_populates="business_profile",
    )

    def __repr__(self) -> str:
        return f"<BusinessProfile id={self.id} org_id={self.organization_id} company='{self.company_name}'>"
