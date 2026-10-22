"""Inbound Email and Microsoft Graph Synchronization domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    Boolean,
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
    from app.models.crm import Company, Contact
    from app.models.lead import Lead
    from app.models.tenant import Organization

ALLOWED_SYNC_STATUSES = {
    "matched",
    "unmatched",
    "review_required",
    "error",
}

ALLOWED_MANUAL_REVIEW_STATUSES = {
    "pending",
    "reviewed",
    "dismissed",
    "archived",
}

ALLOWED_GRAPH_SYNC_RUN_STATUSES = {
    "completed",
    "partial",
    "failed",
    "running",
    "skipped_concurrency_lock",
}


class InboundEmail(Base):
    """
    Inbound email message imported from the approved Microsoft Graph support mailbox.
    Belongs strictly to one Organization for multi-tenant data isolation.
    Associates with matched Contact, Lead, or Company records, or flags for manual review.
    """
    __tablename__ = "inbound_emails"

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

    # Microsoft Graph identifiers
    graph_message_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    graph_conversation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    internet_message_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Message header data
    sender_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    sender_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    recipient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="support@agilereceivables.com",
    )
    subject: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    # Content data (treated as untrusted input)
    body_preview: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    body_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    body_content_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="html",
    )

    # Metadata & Flags
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    has_attachments: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # CRM Entity Matching
    matched_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Workflow & Review Status
    sync_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unmatched",
        index=True,
    )
    manual_review_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )
    review_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Raw metadata preserved for auditing & troubleshooting
    raw_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
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
    organization: Mapped[Organization] = relationship("Organization")
    matched_contact: Mapped[Optional[Contact]] = relationship("Contact", foreign_keys=[matched_contact_id])
    matched_lead: Mapped[Optional[Lead]] = relationship("Lead", foreign_keys=[matched_lead_id])
    matched_company: Mapped[Optional[Company]] = relationship("Company", foreign_keys=[matched_company_id])

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "graph_message_id",
            name="uq_inbound_emails_org_graph_msg_id",
        ),
        CheckConstraint(
            "sync_status IN ('matched', 'unmatched', 'review_required', 'error')",
            name="ck_inbound_emails_sync_status",
        ),
        CheckConstraint(
            "manual_review_status IN ('pending', 'reviewed', 'dismissed', 'archived')",
            name="ck_inbound_emails_review_status",
        ),
        Index("ix_inbound_emails_org_received", "organization_id", "received_at"),
        Index("ix_inbound_emails_org_sender", "organization_id", "sender_email"),
        Index("ix_inbound_emails_org_sync_status", "organization_id", "sync_status"),
        Index("ix_inbound_emails_org_review_status", "organization_id", "manual_review_status"),
    )

    def __repr__(self) -> str:
        return (
            f"<InboundEmail id={self.id} org_id={self.organization_id} "
            f"sender='{self.sender_email}' subject='{self.subject}' status='{self.sync_status}'>"
        )


class GraphSyncRun(Base):
    """
    Audit record tracking execution of Microsoft Graph mailbox synchronization runs.
    Tenant-scoped for isolation and operational visibility.
    """
    __tablename__ = "graph_sync_runs"

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
    mailbox_address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    sync_trigger: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",  # "manual", "scheduled", "webhook"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="completed",  # "completed", "partial", "failed"
    )
    messages_fetched: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    messages_imported: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    messages_matched: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    messages_unmatched: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    messages_skipped: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    checkpoint_delta_link: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    organization: Mapped[Organization] = relationship("Organization")

    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'partial', 'failed', 'running', 'skipped_concurrency_lock')",
            name="ck_graph_sync_runs_status",
        ),
        Index("ix_graph_sync_runs_org_created", "organization_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<GraphSyncRun id={self.id} org_id={self.organization_id} "
            f"mailbox='{self.mailbox_address}' status='{self.status}'>"
        )


class GraphMailboxCheckpoint(Base):
    """
    Persisted state tracking incremental synchronization checkpoints and concurrency locks.
    Prevents repeated full mailbox crawls across backend restarts and avoids overlapping sync jobs.
    """
    __tablename__ = "graph_mailbox_checkpoints"

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
    mailbox_address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    delta_link: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_syncing: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    sync_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_sync_status: Mapped[str] = mapped_column(
        String(50),
        default="idle",
        nullable=False,
    )
    last_successful_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    total_imported: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
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

    organization: Mapped[Organization] = relationship("Organization")

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "mailbox_address",
            name="uq_graph_mailbox_checkpoint_org_mailbox",
        ),
        Index("ix_graph_checkpoint_org_mailbox", "organization_id", "mailbox_address"),
    )

    def __repr__(self) -> str:
        return (
            f"<GraphMailboxCheckpoint id={self.id} org_id={self.organization_id} "
            f"mailbox='{self.mailbox_address}' is_syncing={self.is_syncing}>"
        )

