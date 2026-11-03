"""CampaignExecutionJob domain model for durable asynchronous campaign step execution."""
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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.campaign import Campaign, CampaignContact
    from app.models.campaign_step import CampaignStep
    from app.models.crm import Contact
    from app.models.outreach import Outreach
    from app.models.tenant import Organization

ALLOWED_JOB_STATUSES = {
    "pending",
    "processing",
    "completed",
    "failed",
    "retry_scheduled",
    "held",
    "dispatch_unknown",
}

ALLOWED_JOB_CHANNELS = {
    "email",
    "voice",
    "sms",
    "physical_mail",
    "linkedin",
}

AUTODISPATCH_ALLOWED_CHANNELS = {
    "email",
    "voice",
    "sms",
}


class CampaignExecutionJob(Base):
    """
    CampaignExecutionJob represents an asynchronous, persistent unit of campaign execution work.
    Guarantees durable idempotency, row-level concurrency control, lease-based worker fencing,
    and automatic crash recovery.
    """
    __tablename__ = "campaign_execution_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    campaign_contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("campaign_contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    campaign_step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("campaign_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    outreach_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("outreach.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Step identification
    step_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    step_identifier: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="email",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    # Scheduling & Attempt Tracking
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Worker Fencing & Lease Tracking
    worker_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    lease_token: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    leased_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Ambiguous Provider Outcome Detection
    dispatch_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Durable Idempotency Key
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    # Immutable Execution Payload Snapshot (JSON with variant JSONB for PostgreSQL)
    execution_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    # Audit Snapshots (Preserved even if CRM records are deleted)
    campaign_name_snapshot: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    recipient_snapshot: Mapped[Optional[str]] = mapped_column(
        String(255),
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
    campaign: Mapped[Optional[Campaign]] = relationship("Campaign")
    campaign_contact: Mapped[Optional[CampaignContact]] = relationship("CampaignContact")
    contact: Mapped[Optional[Contact]] = relationship("Contact")
    campaign_step: Mapped[Optional[CampaignStep]] = relationship("CampaignStep")
    outreach: Mapped[Optional[Outreach]] = relationship("Outreach")

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_campaign_execution_jobs_idempotency_key"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'retry_scheduled', 'held', 'dispatch_unknown')",
            name="ck_campaign_execution_jobs_status",
        ),
        CheckConstraint(
            "channel IN ('email', 'voice', 'sms', 'physical_mail', 'linkedin')",
            name="ck_campaign_execution_jobs_channel",
        ),
        CheckConstraint("attempts >= 0", name="ck_campaign_execution_jobs_attempts"),
        CheckConstraint("max_attempts >= 1", name="ck_campaign_execution_jobs_max_attempts"),
        CheckConstraint(
            "status NOT IN ('pending', 'processing', 'retry_scheduled', 'dispatch_unknown') "
            "OR (campaign_id IS NOT NULL AND contact_id IS NOT NULL AND campaign_contact_id IS NOT NULL)",
            name="ck_campaign_execution_jobs_active_entities",
        ),
        CheckConstraint(
            "channel IN ('email', 'voice', 'sms') OR status IN ('held', 'completed', 'failed')",
            name="ck_campaign_execution_jobs_channel_dispatch",
        ),
        Index("ix_campaign_execution_jobs_poll", "organization_id", "status", "scheduled_at"),
        Index("ix_campaign_execution_jobs_lease_recovery", "status", "lease_expires_at"),
        Index("ix_campaign_execution_jobs_enrollment_step", "campaign_contact_id", "step_number"),
        Index("ix_campaign_execution_jobs_campaign_id", "campaign_id"),
        Index("ix_campaign_execution_jobs_worker_lease", "worker_id", "lease_token"),
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignExecutionJob id={self.id} org_id={self.organization_id} "
            f"step={self.step_number} channel='{self.channel}' status='{self.status}'>"
        )
