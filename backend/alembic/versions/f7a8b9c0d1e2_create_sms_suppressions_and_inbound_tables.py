"""create sms_suppressions and inbound_sms_messages tables

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-26 22:00:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sms_suppressions and inbound_sms_messages tables."""
    # 1. sms_suppressions
    op.create_table(
        'sms_suppressions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('contact_id', sa.Uuid(), sa.ForeignKey('contacts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reason', sa.String(100), nullable=False, server_default='opt_out_keyword'),
        sa.Column('keyword', sa.String(50), nullable=True),
        sa.Column('source', sa.String(50), nullable=False, server_default='inbound_sms'),
        sa.Column('suppressed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'phone', name='uq_sms_suppressions_org_phone'),
    )
    op.create_index('ix_sms_suppressions_organization_id', 'sms_suppressions', ['organization_id'], unique=False)
    op.create_index('ix_sms_suppressions_phone', 'sms_suppressions', ['phone'], unique=False)
    op.create_index('ix_sms_suppressions_contact_id', 'sms_suppressions', ['contact_id'], unique=False)
    op.create_index('ix_sms_suppressions_org_phone', 'sms_suppressions', ['organization_id', 'phone'], unique=False)

    # 2. inbound_sms_messages
    op.create_table(
        'inbound_sms_messages',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_sid', sa.String(100), nullable=False, unique=True),
        sa.Column('from_phone', sa.String(50), nullable=False),
        sa.Column('to_phone', sa.String(50), nullable=False),
        sa.Column('body_snippet', sa.String(255), nullable=True),
        sa.Column('is_opt_out', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('opt_out_keyword', sa.String(50), nullable=True),
        sa.Column('matched_contact_id', sa.Uuid(), sa.ForeignKey('contacts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('matched_outreach_id', sa.Uuid(), sa.ForeignKey('outreach.id', ondelete='SET NULL'), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_inbound_sms_messages_organization_id', 'inbound_sms_messages', ['organization_id'], unique=False)
    op.create_index('ix_inbound_sms_messages_message_sid', 'inbound_sms_messages', ['message_sid'], unique=True)
    op.create_index('ix_inbound_sms_messages_from_phone', 'inbound_sms_messages', ['from_phone'], unique=False)
    op.create_index('ix_inbound_sms_messages_to_phone', 'inbound_sms_messages', ['to_phone'], unique=False)
    op.create_index('ix_inbound_sms_messages_is_opt_out', 'inbound_sms_messages', ['is_opt_out'], unique=False)
    op.create_index('ix_inbound_sms_messages_matched_contact_id', 'inbound_sms_messages', ['matched_contact_id'], unique=False)
    op.create_index('ix_inbound_sms_messages_matched_outreach_id', 'inbound_sms_messages', ['matched_outreach_id'], unique=False)
    op.create_index('ix_inbound_sms_org_from', 'inbound_sms_messages', ['organization_id', 'from_phone'], unique=False)
    op.create_index('ix_inbound_sms_org_received', 'inbound_sms_messages', ['organization_id', 'received_at'], unique=False)


def downgrade() -> None:
    """Drop inbound_sms_messages and sms_suppressions tables."""
    op.drop_index('ix_inbound_sms_org_received', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_org_from', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_matched_outreach_id', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_matched_contact_id', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_is_opt_out', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_to_phone', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_from_phone', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_message_sid', table_name='inbound_sms_messages')
    op.drop_index('ix_inbound_sms_messages_organization_id', table_name='inbound_sms_messages')
    op.drop_table('inbound_sms_messages')

    op.drop_index('ix_sms_suppressions_org_phone', table_name='sms_suppressions')
    op.drop_index('ix_sms_suppressions_contact_id', table_name='sms_suppressions')
    op.drop_index('ix_sms_suppressions_phone', table_name='sms_suppressions')
    op.drop_index('ix_sms_suppressions_organization_id', table_name='sms_suppressions')
    op.drop_table('sms_suppressions')
