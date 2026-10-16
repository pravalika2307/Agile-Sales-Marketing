"""EmailTemplate domain model for reusable campaign email templates."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.tenant import Organization

ALLOWED_TEMPLATE_CATEGORIES = {
    "outbound",
    "follow_up",
    "nurture",
    "referral",
    "announcement",
}


class EmailTemplate(Base):
    """
    Reusable email subject and body template scoped to an Organization.
    Can be browsed, selected, applied, and updated independently of specific campaigns.
    """
    __tablename__ = "email_templates"

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
    category: Mapped[str] = mapped_column(
        String(50),
        default="outbound",
        nullable=False,
    )
    subject_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    body_template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
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
    organization: Mapped["Organization"] = relationship("Organization")

    __table_args__ = (
        Index("ix_email_templates_org_category", "organization_id", "category"),
        Index("ix_email_templates_org_name", "organization_id", "name"),
    )

    def __repr__(self) -> str:
        return f"<EmailTemplate id={self.id} org_id={self.organization_id} name='{self.name}'>"
