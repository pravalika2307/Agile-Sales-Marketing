"""add_email_tracking_fields_and_events

Revision ID: c3d4e5f6a7b2
Revises: b2c3d4e5f6a1
Create Date: 2026-10-07 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b2'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tracking timestamp columns to outreach and update outreach_events event_type constraint."""
    # 1. Add tracking timestamp columns to outreach
    op.add_column('outreach', sa.Column('first_delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach', sa.Column('first_opened_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach', sa.Column('first_clicked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach', sa.Column('first_replied_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outreach', sa.Column('first_bounced_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Update check constraint on outreach_events table
    op.drop_constraint('ck_outreach_events_event_type', 'outreach_events', type_='check')
    op.create_check_constraint(
        'ck_outreach_events_event_type',
        'outreach_events',
        "event_type IN ('created', 'scheduled', 'sending', 'sent', 'failed', 'cancelled', 'delivered', 'opened', 'clicked', 'replied', 'bounced')",
    )


def downgrade() -> None:
    """Revert outreach_events check constraint and drop tracking columns."""
    # Revert check constraint on outreach_events
    op.drop_constraint('ck_outreach_events_event_type', 'outreach_events', type_='check')
    op.create_check_constraint(
        'ck_outreach_events_event_type',
        'outreach_events',
        "event_type IN ('created', 'scheduled', 'sending', 'sent', 'failed', 'cancelled')",
    )

    # Drop tracking timestamp columns from outreach
    op.drop_column('outreach', 'first_bounced_at')
    op.drop_column('outreach', 'first_replied_at')
    op.drop_column('outreach', 'first_clicked_at')
    op.drop_column('outreach', 'first_opened_at')
    op.drop_column('outreach', 'first_delivered_at')
