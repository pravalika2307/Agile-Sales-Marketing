"""Outreach and OutreachEvent domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.call_record import CallRecord
    from app.models.campaign import Campaign, CampaignContact
    from app.models.crm import Contact
    from app.models.tenant import Organization

ALLOWED_OUTREACH_CHANNELS = {
    "email",
    "linkedin",
    "voice",
    "sms",
}

ALLOWED_OUTREACH_STATUSES = {
    "draft",
    "scheduled",
    "sending",
    "sent",
    "failed",
    "cancelled",
}

ALLOWED_OUTREACH_EVENT_TYPES = {
    "created",
    "scheduled",
    "sending",
    "sent",
    "failed",
    "cancelled",
    "delivered",
    "opened",
    "clicked",
    "replied",
    "bounced",
}


class Outreach(Base):
    """
    Outreach domain model representing an individual outreach interaction (e.g. email).
    Belongs strictly to one Organization, linked to Campaign, Contact, and CampaignContact.
    """
    __tablename__ = "outreach"

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
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    campaign_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("campaign_contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    call_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("call_records.id", ondelete="SET NULL", use_alter=True, name="fk_outreach_call_record_id"),
        nullable=True,
        index=True,
    )
    recipient: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="email",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="draft",
        index=True,
    )
    subject: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    body: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    provider: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_clicked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_replied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_bounced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
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
        back_populates="outreaches",
    )
    campaign: Mapped[Optional[Campaign]] = relationship(
        "Campaign",
        back_populates="outreaches",
    )
    contact: Mapped[Optional[Contact]] = relationship(
        "Contact",
        back_populates="outreaches",
    )
    campaign_contact: Mapped[Optional[CampaignContact]] = relationship(
        "CampaignContact",
        back_populates="outreaches",
    )
    call_record: Mapped[Optional[CallRecord]] = relationship(
        "CallRecord",
        foreign_keys=[call_record_id],
    )
    events: Mapped[List[OutreachEvent]] = relationship(
        "OutreachEvent",
        back_populates="outreach",
        cascade="all, delete-orphan",
        order_by="OutreachEvent.occurred_at.asc()",
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'linkedin', 'voice', 'sms')",
            name="ck_outreach_channel",
        ),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'sending', 'sent', 'failed', 'cancelled')",
            name="ck_outreach_status",
        ),
    )

    @property
    def recipient_email(self) -> Optional[str]:
        """Safely derive recipient email from explicit recipient field or associated Contact."""
        if self.recipient:
            return self.recipient
        return self.contact.email if self.contact else None

    @property
    def outreach_id(self) -> uuid.UUID:
        """Alias for id."""
        return self.id

    def __repr__(self) -> str:
        return f"<Outreach id={self.id} org_id={self.organization_id} channel='{self.channel}' status='{self.status}'>"


class OutreachEvent(Base):
    """
    OutreachEvent domain model tracking state transitions and lifecycle occurrences for an Outreach.
    """
    __tablename__ = "outreach_events"

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
    outreach_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("outreach.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    event_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization",
    )
    outreach: Mapped[Outreach] = relationship(
        "Outreach",
        back_populates="events",
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'scheduled', 'sending', 'sent', 'failed', 'cancelled', 'delivered', 'opened', 'clicked', 'replied', 'bounced')",
            name="ck_outreach_events_event_type",
        ),
        Index("ix_outreach_events_org_type", "organization_id", "event_type"),
        Index("ix_outreach_events_occurred", "outreach_id", "occurred_at"),
    )

    def __repr__(self) -> str:
        return f"<OutreachEvent id={self.id} outreach_id={self.outreach_id} event_type='{self.event_type}'>"
