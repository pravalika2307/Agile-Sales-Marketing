"""SQLAlchemy domain models for SaaS Multi-Tenant Channel Entitlements and Upgrade Requests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
    from app.models.tenant import Organization, User

ALLOWED_CHANNELS = {
    "email",
    "sms",
    "voice",
    "ringless_voicemail",
    "physical_mail",
}

ALLOWED_ENTITLEMENT_STATUSES = {
    "included",
    "upgrade_required",
    "upgrade_requested",
    "approved",
    "suspended",
}

ALLOWED_UPGRADE_REQUEST_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "cancelled",
}


class OrganizationChannelEntitlement(Base):
    """
    Persistent organization-level communication channel entitlement.
    Enforces feature gates, volume quotas, and tier unlock states per tenant.
    """
    __tablename__ = "organization_channel_entitlements"

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
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="upgrade_required",
    )
    is_unlocked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    tier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="starter",
    )
    allocated_quota: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    current_usage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    approved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
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
    )
    approved_by: Mapped[Optional[User]] = relationship(
        "User",
        foreign_keys=[approved_by_user_id],
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "channel", name="uq_org_channel_entitlement"),
        CheckConstraint(
            "channel IN ('email', 'sms', 'voice', 'ringless_voicemail', 'physical_mail')",
            name="ck_org_channel_entitlement_channel",
        ),
        CheckConstraint(
            "status IN ('included', 'upgrade_required', 'upgrade_requested', 'approved', 'suspended')",
            name="ck_org_channel_entitlement_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationChannelEntitlement org_id={self.organization_id} channel='{self.channel}' status='{self.status}'>"


class ChannelUpgradeRequest(Base):
    """
    Persistent tenant request to unlock an advanced communication channel.
    Tracks business justification, requester identity, administrative reviewer, and decision status.
    """
    __tablename__ = "channel_upgrade_requests"

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
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    requesting_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )
    estimated_volume: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    business_justification: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    reviewing_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    admin_notes: Mapped[Optional[str]] = mapped_column(
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

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization",
    )
    requesting_user: Mapped[Optional[User]] = relationship(
        "User",
        foreign_keys=[requesting_user_id],
    )
    reviewing_admin: Mapped[Optional[User]] = relationship(
        "User",
        foreign_keys=[reviewing_admin_id],
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'sms', 'voice', 'ringless_voicemail', 'physical_mail')",
            name="ck_channel_upgrade_request_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_channel_upgrade_request_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<ChannelUpgradeRequest id={self.id} org_id={self.organization_id} channel='{self.channel}' status='{self.status}'>"


class EntitlementAuditLog(Base):
    """
    Immutable audit history of all channel entitlement transitions, approvals, and quota updates.
    """
    __tablename__ = "entitlement_audit_logs"

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
    channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    old_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    new_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
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
    actor_user: Mapped[Optional[User]] = relationship(
        "User",
        foreign_keys=[actor_user_id],
    )

    def __repr__(self) -> str:
        return f"<EntitlementAuditLog id={self.id} org_id={self.organization_id} action='{self.action}' by='{self.actor_user_id}'>"
