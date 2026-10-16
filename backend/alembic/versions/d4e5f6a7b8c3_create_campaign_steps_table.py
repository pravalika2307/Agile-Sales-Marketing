"""create_campaign_steps_table

Revision ID: d4e5f6a7b8c3
Revises: c3d4e5f6a7b2
Create Date: 2026-10-07 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c3'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create campaign_steps table with ordering, delay, template, and foreign key constraints."""
    op.create_table(
        'campaign_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column(
            'campaign_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('campaigns.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('step_type', sa.String(length=50), nullable=False, server_default='email'),
        sa.Column('subject_template', sa.String(length=500), nullable=True),
        sa.Column('body_template', sa.Text(), nullable=True),
        sa.Column('delay_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('delay_hours', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint('step_number >= 1', name='ck_campaign_steps_step_number'),
        sa.CheckConstraint("step_type IN ('email')", name='ck_campaign_steps_step_type'),
        sa.CheckConstraint('delay_days >= 0', name='ck_campaign_steps_delay_days'),
        sa.CheckConstraint('delay_hours >= 0 AND delay_hours < 24', name='ck_campaign_steps_delay_hours'),
        sa.UniqueConstraint('campaign_id', 'step_number', name='uq_campaign_steps_campaign_step_number'),
    )

    op.create_index(
        'ix_campaign_steps_organization_id',
        'campaign_steps',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_campaign_steps_campaign_id',
        'campaign_steps',
        ['campaign_id'],
        unique=False,
    )
    op.create_index(
        'ix_campaign_steps_is_active',
        'campaign_steps',
        ['is_active'],
        unique=False,
    )


def downgrade() -> None:
    """Drop campaign_steps table."""
    op.drop_index('ix_campaign_steps_is_active', table_name='campaign_steps')
    op.drop_index('ix_campaign_steps_campaign_id', table_name='campaign_steps')
    op.drop_index('ix_campaign_steps_organization_id', table_name='campaign_steps')
    op.drop_table('campaign_steps')
