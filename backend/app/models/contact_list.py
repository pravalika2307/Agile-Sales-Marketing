"""Contact List, Membership, and Campaign Association models."""
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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.crm import Contact
    from app.models.lead import Lead
    from app.models.tenant import Organization


class ContactList(Base):
    """
    Named contact/lead list scoped to an Organization.
    Initial release supports static lists with filter criteria preservation for future dynamic lists.
    """
    __tablename__ = "contact_lists"

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
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="static",
    )
    filter_criteria: Mapped[Optional[Dict[str, Any]]] = mapped_column(
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
    organization: Mapped[Organization] = relationship(
        "Organization",
    )
    members: Mapped[List[ContactListMember]] = relationship(
        "ContactListMember",
        back_populates="contact_list",
        cascade="all, delete-orphan",
        order_by="ContactListMember.added_at.desc()",
    )
    campaign_associations: Mapped[List[CampaignList]] = relationship(
        "CampaignList",
        back_populates="contact_list",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("uq_contact_lists_org_lower_name", "organization_id", func.lower(text("name")), unique=True),
    )

    def __repr__(self) -> str:
        return f"<ContactList id={self.id} org_id={self.organization_id} name='{self.name}'>"


class ContactListMember(Base):
    """
    Dual-pointer membership model.
    References a canonical Contact (if resolved/enrolled) and/or a Lead (source prospect).
    Allows prospects without emails to belong to lists without creating invalid CRM contacts.
    """
    __tablename__ = "contact_list_members"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    contact_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("contact_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    contact_list: Mapped[ContactList] = relationship(
        "ContactList",
        back_populates="members",
    )
    contact: Mapped[Optional[Contact]] = relationship(
        "Contact",
        foreign_keys=[contact_id],
    )
    lead: Mapped[Optional[Lead]] = relationship(
        "Lead",
        foreign_keys=[lead_id],
    )

    __table_args__ = (
        CheckConstraint(
            "(contact_id IS NOT NULL) OR (lead_id IS NOT NULL)",
            name="ck_contact_list_members_target_present",
        ),
        Index(
            "uq_list_member_contact",
            "contact_list_id",
            "contact_id",
            unique=True,
            postgresql_where=(contact_id.isnot(None)),
        ),
        Index(
            "uq_list_member_lead",
            "contact_list_id",
            "lead_id",
            unique=True,
            postgresql_where=(lead_id.isnot(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<ContactListMember id={self.id} list_id={self.contact_list_id} contact_id={self.contact_id} lead_id={self.lead_id}>"


class CampaignList(Base):
    """
    Associates a ContactList with a Campaign.
    Allows a list to be reused across multiple campaigns and multiple lists attached to one campaign.
    """
    __tablename__ = "campaign_lists"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("contact_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    associated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    campaign: Mapped[Campaign] = relationship(
        "Campaign",
        back_populates="list_associations",
    )
    contact_list: Mapped[ContactList] = relationship(
        "ContactList",
        back_populates="campaign_associations",
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_list_id", name="uq_campaign_lists_campaign_list"),
    )

    def __repr__(self) -> str:
        return f"<CampaignList id={self.id} campaign_id={self.campaign_id} list_id={self.contact_list_id}>"
