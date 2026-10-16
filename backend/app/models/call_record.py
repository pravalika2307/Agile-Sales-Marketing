"""CallRecord domain model representing Retell voice call events, transcripts, and follow-up states."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.crm import Contact
    from app.models.lead import Lead
    from app.models.outreach import Outreach
    from app.models.tenant import Organization


class CallRecord(Base):
    """
    CallRecord stores metadata, analysis, and follow-up tracking for Retell voice calls.
    Belongs strictly to one Organization, optionally linking to Contact, Lead, Campaign, and Outreach.
    """
    __tablename__ = "call_records"

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
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Retell Call Identifiers
    call_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="inbound",
    )
    call_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ended",
    )
    call_outcome: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    # Telephony metadata
    caller_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    to_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    disconnection_reason: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Transcripts and Summaries
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    transcript: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # JSON Payloads
    collected_variables: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    call_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Automated Follow-up Tracking & Idempotency
    followup_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="none",
        index=True,
    )  # "none", "sent", "failed", "skipped"
    followup_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    followup_email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("outreach.id", ondelete="SET NULL", use_alter=True, name="fk_call_records_followup_email_id"),
        nullable=True,
        index=True,
    )
    followup_idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )

    # Lifecycle Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(
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
    organization: Mapped[Organization] = relationship("Organization")
    contact: Mapped[Optional[Contact]] = relationship("Contact")
    lead: Mapped[Optional[Lead]] = relationship("Lead")
    campaign: Mapped[Optional[Campaign]] = relationship("Campaign")
    followup_email: Mapped[Optional[Outreach]] = relationship(
        "Outreach",
        foreign_keys=[followup_email_id],
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="ck_call_records_direction",
        ),
        CheckConstraint(
            "followup_status IN ('none', 'sent', 'failed', 'skipped', 'in_progress')",
            name="ck_call_records_followup_status",
        ),
        Index("ix_call_records_org_call", "organization_id", "call_id"),
        Index("ix_call_records_org_outcome", "organization_id", "call_outcome"),
    )

    def __repr__(self) -> str:
        return f"<CallRecord id={self.id} call_id='{self.call_id}' direction='{self.direction}' outcome='{self.call_outcome}'>"
