"""LeadResearch domain model for pre-call intelligence."""
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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.tenant import Organization

ALLOWED_RESEARCH_STATUSES = {
    "pending",
    "completed",
    "failed",
    "stale",
}


class LeadResearch(Base):
    """
    Structured company and lead intelligence profile gathered prior to outbound outreach.
    Scoped strictly to Organization (tenant) and Lead.
    """
    __tablename__ = "lead_researches"

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
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Structured Intelligence
    company_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )
    company_size: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Rich analytical points (stored as JSON arrays of strings or key-value objects)
    business_signals: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    potential_pain_points: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    personalization_points: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    # Narrative Summary for SDR / Voice Agent Context
    research_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Source Attribution
    source_urls: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    # Execution & Freshness Metadata
    researched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    research_status: Mapped[str] = mapped_column(
        String(50),
        default="completed",
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Standard Timestamps
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
    lead: Mapped[Lead] = relationship(
        "Lead",
        back_populates="research",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "lead_id",
            name="uq_lead_researches_org_lead",
        ),
        CheckConstraint(
            "research_status IN ('pending', 'completed', 'failed', 'stale')",
            name="ck_lead_research_status",
        ),
    )

    def check_freshness(self, max_age_days: int = 7) -> bool:
        """Determines whether the research is within the acceptable freshness window."""
        if self.research_status != "completed":
            return False
        researched = self.researched_at
        if researched.tzinfo is None:
            researched = researched.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - researched
        return delta.total_seconds() < (max_age_days * 86400)

    @property
    def is_fresh(self) -> bool:
        """Default 7-day freshness check property."""
        return self.check_freshness(max_age_days=7)

    def __repr__(self) -> str:
        return f"<LeadResearch id={self.id} lead_id={self.lead_id} status='{self.research_status}' researched_at={self.researched_at}>"
