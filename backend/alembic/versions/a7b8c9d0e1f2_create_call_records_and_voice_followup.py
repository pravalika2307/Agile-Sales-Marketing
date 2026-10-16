"""create_call_records_and_voice_followup

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-08 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create call_records table and extend outreach table for voice follow-up."""
    # 1. Create call_records table
    op.create_table(
        'call_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'contact_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('contacts.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'lead_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('leads.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'campaign_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('campaigns.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('call_id', sa.String(length=100), nullable=False),
        sa.Column('agent_id', sa.String(length=100), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False, server_default='inbound'),
        sa.Column('call_status', sa.String(length=50), nullable=False, server_default='ended'),
        sa.Column('call_outcome', sa.String(length=50), nullable=True),
        sa.Column('caller_phone', sa.String(length=50), nullable=True),
        sa.Column('to_phone', sa.String(length=50), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('disconnection_reason', sa.String(length=100), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('collected_variables', sa.JSON(), nullable=True),
        sa.Column('call_analysis', sa.JSON(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('followup_status', sa.String(length=50), nullable=False, server_default='none'),
        sa.Column('followup_reason', sa.String(length=255), nullable=True),
        sa.Column(
            'followup_email_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('outreach.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('followup_idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name='ck_call_records_direction',
        ),
        sa.CheckConstraint(
            "followup_status IN ('none', 'sent', 'failed', 'skipped', 'in_progress')",
            name='ck_call_records_followup_status',
        ),
    )

    # Indexes on call_records
    op.create_index(op.f('ix_call_records_organization_id'), 'call_records', ['organization_id'])
    op.create_index(op.f('ix_call_records_contact_id'), 'call_records', ['contact_id'])
    op.create_index(op.f('ix_call_records_lead_id'), 'call_records', ['lead_id'])
    op.create_index(op.f('ix_call_records_campaign_id'), 'call_records', ['campaign_id'])
    op.create_index(op.f('ix_call_records_call_id'), 'call_records', ['call_id'], unique=True)
    op.create_index(op.f('ix_call_records_agent_id'), 'call_records', ['agent_id'])
    op.create_index(op.f('ix_call_records_call_outcome'), 'call_records', ['call_outcome'])
    op.create_index(op.f('ix_call_records_followup_status'), 'call_records', ['followup_status'])
    op.create_index(op.f('ix_call_records_followup_email_id'), 'call_records', ['followup_email_id'])
    op.create_index(op.f('ix_call_records_followup_idempotency_key'), 'call_records', ['followup_idempotency_key'], unique=True)
    op.create_index('ix_call_records_org_call', 'call_records', ['organization_id', 'call_id'])
    op.create_index('ix_call_records_org_outcome', 'call_records', ['organization_id', 'call_outcome'])

    # 2. Modify outreach table for voice follow-up support
    op.add_column(
        'outreach',
        sa.Column('call_record_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'outreach',
        sa.Column('recipient', sa.String(length=255), nullable=True),
    )
    op.alter_column('outreach', 'campaign_id', nullable=True)
    op.alter_column('outreach', 'contact_id', nullable=True)
    op.alter_column('outreach', 'campaign_contact_id', nullable=True)

    op.create_index(op.f('ix_outreach_call_record_id'), 'outreach', ['call_record_id'])
    op.create_foreign_key(
        'fk_outreach_call_record_id',
        'outreach',
        'call_records',
        ['call_record_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema changes."""
    op.drop_constraint('fk_outreach_call_record_id', 'outreach', type_='foreignkey')
    op.drop_index(op.f('ix_outreach_call_record_id'), table_name='outreach')
    op.drop_column('outreach', 'recipient')
    op.drop_column('outreach', 'call_record_id')
    op.alter_column('outreach', 'campaign_contact_id', nullable=False)
    op.alter_column('outreach', 'contact_id', nullable=False)
    op.alter_column('outreach', 'campaign_id', nullable=False)

    op.drop_index('ix_call_records_org_outcome', table_name='call_records')
    op.drop_index('ix_call_records_org_call', table_name='call_records')
    op.drop_index(op.f('ix_call_records_followup_idempotency_key'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_followup_email_id'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_followup_status'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_call_outcome'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_agent_id'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_call_id'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_campaign_id'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_lead_id'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_contact_id'), table_name='call_records')
    op.drop_index(op.f('ix_call_records_organization_id'), table_name='call_records')
    op.drop_table('call_records')
