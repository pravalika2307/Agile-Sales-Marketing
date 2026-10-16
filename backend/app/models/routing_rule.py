"""Lead routing rule domain model for automated lead assignment (Phase 4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
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

if TYPE_CHECKING:
    from app.models.tenant import Organization, User


class LeadRoutingRule(Base):
    """
    Configurable, tenant-scoped routing rule matching leads by firmographics,
    qualification outcome, geography, and score, routing to a genuine user or team.
    """
    __tablename__ = "lead_routing_rules"

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
    priority: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    # Criteria / Condition filters
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
    min_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    max_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    qualification_statuses: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
    )

    # Action / Assignee Target
    assigned_to_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_team: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Timestamps
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
    assigned_to_user: Mapped[Optional[User]] = relationship("User", foreign_keys=[assigned_to_user_id])

    def __repr__(self) -> str:
        return f"<LeadRoutingRule id={self.id} org_id={self.organization_id} name='{self.name}' priority={self.priority}>"
