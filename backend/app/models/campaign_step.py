"""CampaignStep domain model for sequential campaign steps and email content templates."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.tenant import Organization

ALLOWED_STEP_TYPES = {"email"}


class CampaignStep(Base):
    """
    CampaignStep domain model representing a sequential outreach step in a campaign.
    Contains template configurations, delay offsets, and step ordering.
    """
    __tablename__ = "campaign_steps"

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
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    step_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="email",
    )
    subject_template: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    body_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    delay_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    delay_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
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
    campaign: Mapped[Campaign] = relationship(
        "Campaign",
        back_populates="steps",
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "step_number", name="uq_campaign_step_number"),
        CheckConstraint("step_number >= 1", name="ck_campaign_steps_step_number"),
        CheckConstraint("delay_days >= 0", name="ck_campaign_steps_delay_days"),
        CheckConstraint("delay_hours >= 0 AND delay_hours < 24", name="ck_campaign_steps_delay_hours"),
        CheckConstraint("step_type IN ('email')", name="ck_campaign_steps_step_type"),
    )

    def __repr__(self) -> str:
        return f"<CampaignStep id={self.id} campaign_id={self.campaign_id} step_number={self.step_number} type='{self.step_type}'>"
