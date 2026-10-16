"""HubSpot Synchronization Run Record Model."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.tenant import Organization


class HubSpotSyncRun(Base):
    """
    Audit log record of an executed HubSpot CRM sync operation.
    Tenant-scoped to ensure strict multi-tenant isolation.
    """
    __tablename__ = "hubspot_sync_runs"

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
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="completed",  # "completed", "partial", "failed"
    )
    contacts_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    companies_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    deals_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    portal_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    permission_errors: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
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

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")

    def __repr__(self) -> str:
        return f"<HubSpotSyncRun id={self.id} org_id={self.organization_id} status='{self.status}' contacts={self.contacts_count}>"
