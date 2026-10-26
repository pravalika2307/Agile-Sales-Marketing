"""SMS suppression and inbound message domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.crm import Contact
    from app.models.outreach import Outreach
    from app.models.tenant import Organization


class SMSSuppression(Base):
    """
    Durable SMS-specific suppression record.
    Tracks phone numbers that have opted out of SMS outreach (e.g. via STOP keyword)
    within a specific organization.
    
    Guarantees:
    - Multi-tenant isolation: phone numbers are suppressed per organization.
    - Preserves non-SMS channels: contact email and voice outreach remain unaffected
      unless the contact is globally opted out.
    """
    __tablename__ = "sms_suppressions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Normalized E.164 phone number",
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated Contact record if matched",
    )
    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="opt_out_keyword",
        comment="Suppression reason: opt_out_keyword, manual, carrier_stop",
    )
    keyword: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Opt-out keyword received (e.g. STOP, UNSUBSCRIBE)",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="inbound_sms",
        comment="Origin: inbound_sms, admin_ui, api",
    )
    suppressed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    contact: Mapped[Optional[Contact]] = relationship("Contact")

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "phone",
            name="uq_sms_suppressions_org_phone",
        ),
        Index("ix_sms_suppressions_org_phone", "organization_id", "phone"),
    )

    def __repr__(self) -> str:
        return f"<SMSSuppression id={self.id} org_id={self.organization_id} reason='{self.reason}'>"


class InboundSMSMessage(Base):
    """
    Inbound SMS message received via Twilio messaging webhook.
    Tracks receipt for deduplication/idempotency and audit trails.
    
    Privacy guarantee:
    - Never stores sensitive contact message content; only stores sanitized keyword
      or snippet to satisfy TCPA/CTIA audit requirements without accumulating PII.
    """
    __tablename__ = "inbound_sms_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_sid: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Twilio MessageSid / SmsSid for replay prevention and idempotency",
    )
    from_phone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Sender normalized E.164 phone number",
    )
    to_phone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Twilio destination phone number",
    )
    body_snippet: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Sanitized keyword or summary; no full personal message text stored",
    )
    is_opt_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    opt_out_keyword: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    matched_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_outreach_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("outreach.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    contact: Mapped[Optional[Contact]] = relationship("Contact")
    outreach: Mapped[Optional[Outreach]] = relationship("Outreach")

    __table_args__ = (
        Index("ix_inbound_sms_org_from", "organization_id", "from_phone"),
        Index("ix_inbound_sms_org_received", "organization_id", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<InboundSMSMessage id={self.id} sid='{self.message_sid}' is_opt_out={self.is_opt_out}>"
