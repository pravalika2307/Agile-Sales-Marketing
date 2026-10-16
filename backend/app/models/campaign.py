"""Campaign and CampaignContact domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.campaign_step import CampaignStep
    from app.models.contact_list import CampaignList
    from app.models.crm import Contact
    from app.models.outreach import Outreach
    from app.models.tenant import Organization

ALLOWED_CAMPAIGN_TYPES = {
    "sales_outbound",
    "marketing_social",
    "hybrid",
}

ALLOWED_CAMPAIGN_STATUSES = {
    "draft",
    "active",
    "paused",
    "completed",
}

ALLOWED_ENROLLMENT_STATUSES = {
    "queued",
    "in_progress",
    "replied",
    "bounced",
    "completed",
}


class Campaign(Base):
    """
    Campaign domain model representing an outreach or marketing effort.
    Belongs strictly to one Organization.
    """
    __tablename__ = "campaigns"

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
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="sales_outbound",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="draft",
        index=True,
    )
    schedule_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    workflow_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
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
        back_populates="campaigns",
    )
    campaign_contacts: Mapped[List[CampaignContact]] = relationship(
        "CampaignContact",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    outreaches: Mapped[List[Outreach]] = relationship(
        "Outreach",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    steps: Mapped[List[CampaignStep]] = relationship(
        "CampaignStep",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignStep.step_number.asc()",
    )
    list_associations: Mapped[List[CampaignList]] = relationship(
        "CampaignList",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('sales_outbound', 'marketing_social', 'hybrid')",
            name="ck_campaigns_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed')",
            name="ck_campaigns_status",
        ),
    )

    @property
    def contacts_count(self) -> int:
        return len(self.campaign_contacts) if self.campaign_contacts is not None else 0

    @property
    def steps_count(self) -> int:
        return len(self.steps) if self.steps is not None else 0

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} org_id={self.organization_id} name='{self.name}' status='{self.status}'>"


class CampaignContact(Base):
    """
    Join model representing the enrollment of a Contact in a Campaign.
    Unique by (campaign_id, contact_id).
    """
    __tablename__ = "campaign_contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enrollment_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="queued",
        index=True,
    )
    current_step: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
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
    campaign: Mapped[Campaign] = relationship(
        "Campaign",
        back_populates="campaign_contacts",
    )
    contact: Mapped[Contact] = relationship(
        "Contact",
        back_populates="campaign_contacts",
    )
    outreaches: Mapped[List[Outreach]] = relationship(
        "Outreach",
        back_populates="campaign_contact",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_contact"),
        CheckConstraint(
            "enrollment_status IN ('queued', 'in_progress', 'replied', 'bounced', 'completed')",
            name="ck_campaign_contacts_enrollment_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<CampaignContact id={self.id} campaign_id={self.campaign_id} contact_id={self.contact_id} status='{self.enrollment_status}'>"
