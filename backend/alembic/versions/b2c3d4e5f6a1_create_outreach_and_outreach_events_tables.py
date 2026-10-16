"""create_outreach_and_outreach_events_tables

Revision ID: b2c3d4e5f6a1
Revises: 8f4b2a1c09de
Create Date: 2026-10-07 01:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a1'
down_revision: Union[str, Sequence[str], None] = '8f4b2a1c09de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create outreach and outreach_events tables."""
    # 1. outreach table
    op.create_table(
        'outreach',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('campaign_contact_id', sa.Uuid(), nullable=False),
        sa.Column('channel', sa.String(length=50), server_default='email', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='draft', nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "channel IN ('email', 'linkedin', 'voice', 'sms')",
            name=op.f('ck_outreach_channel'),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'sending', 'sent', 'failed', 'cancelled')",
            name=op.f('ck_outreach_status'),
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_outreach_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.id'],
            name=op.f('fk_outreach_campaign_id_campaigns'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['contact_id'],
            ['contacts.id'],
            name=op.f('fk_outreach_contact_id_contacts'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['campaign_contact_id'],
            ['campaign_contacts.id'],
            name=op.f('fk_outreach_campaign_contact_id_campaign_contacts'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outreach')),
    )
    op.create_index(op.f('ix_outreach_organization_id'), 'outreach', ['organization_id'], unique=False)
    op.create_index(op.f('ix_outreach_campaign_id'), 'outreach', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_outreach_contact_id'), 'outreach', ['contact_id'], unique=False)
    op.create_index(op.f('ix_outreach_campaign_contact_id'), 'outreach', ['campaign_contact_id'], unique=False)
    op.create_index(op.f('ix_outreach_status'), 'outreach', ['status'], unique=False)

    # 2. outreach_events table
    op.create_table(
        'outreach_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('outreach_id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_metadata', sa.JSON(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created', 'scheduled', 'sending', 'sent', 'failed', 'cancelled')",
            name=op.f('ck_outreach_events_event_type'),
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_outreach_events_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['outreach_id'],
            ['outreach.id'],
            name=op.f('fk_outreach_events_outreach_id_outreach'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outreach_events')),
    )
    op.create_index(op.f('ix_outreach_events_organization_id'), 'outreach_events', ['organization_id'], unique=False)
    op.create_index(op.f('ix_outreach_events_outreach_id'), 'outreach_events', ['outreach_id'], unique=False)
    op.create_index(op.f('ix_outreach_events_event_type'), 'outreach_events', ['event_type'], unique=False)
    op.create_index('ix_outreach_events_org_type', 'outreach_events', ['organization_id', 'event_type'], unique=False)
    op.create_index('ix_outreach_events_occurred', 'outreach_events', ['outreach_id', 'occurred_at'], unique=False)


def downgrade() -> None:
    """Drop outreach_events and outreach tables."""
    op.drop_index('ix_outreach_events_occurred', table_name='outreach_events')
    op.drop_index('ix_outreach_events_org_type', table_name='outreach_events')
    op.drop_index(op.f('ix_outreach_events_event_type'), table_name='outreach_events')
    op.drop_index(op.f('ix_outreach_events_outreach_id'), table_name='outreach_events')
    op.drop_index(op.f('ix_outreach_events_organization_id'), table_name='outreach_events')
    op.drop_table('outreach_events')

    op.drop_index(op.f('ix_outreach_status'), table_name='outreach')
    op.drop_index(op.f('ix_outreach_campaign_contact_id'), table_name='outreach')
    op.drop_index(op.f('ix_outreach_contact_id'), table_name='outreach')
    op.drop_index(op.f('ix_outreach_campaign_id'), table_name='outreach')
    op.drop_index(op.f('ix_outreach_organization_id'), table_name='outreach')
    op.drop_table('outreach')
