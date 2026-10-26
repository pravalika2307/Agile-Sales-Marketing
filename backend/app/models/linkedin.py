"""LinkedIn Integration database models for OAuth connection management and state verification."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.tenant import Organization, User

ALLOWED_LINKEDIN_STATUSES = {"connected", "disconnected", "expired"}


class LinkedInConnection(Base):
    """
    Persistent tenant connection representing an authorized LinkedIn account.
    Enforces strict multi-tenant isolation (one active connection per organization).
    Tokens are stored exclusively in encrypted ciphertext format.
    """
    __tablename__ = "linkedin_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    linkedin_member_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    member_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    member_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    profile_picture_url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    encrypted_access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    access_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    refresh_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scopes: Mapped[str] = mapped_column(
        String(500),
        default="openid,profile,email",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="connected",
        nullable=False,
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(
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
    organization: Mapped[Organization] = relationship("Organization", back_populates="linkedin_connection")
    user: Mapped[Optional[User]] = relationship("User")

    def __repr__(self) -> str:
        # Strict security: never print token values in repr
        return (
            f"<LinkedInConnection id={self.id} org_id={self.organization_id} "
            f"member_id='{self.linkedin_member_id}' status='{self.status}'>"
        )


class LinkedInOAuthState(Base):
    """
    OAuth state record for replay prevention, TTL expiry, and cryptographic verification.
    Binds the authorization attempt to the initiating user and organization.
    """
    __tablename__ = "linkedin_oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    state: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nonce: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<LinkedInOAuthState id={self.id} org_id={self.organization_id} "
            f"is_used={self.is_used} expires_at={self.expires_at}>"
        )
