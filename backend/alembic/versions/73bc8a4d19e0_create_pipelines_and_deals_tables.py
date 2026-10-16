"""create_pipelines_and_deals_tables

Revision ID: 73bc8a4d19e0
Revises: 401da161d246
Create Date: 2026-10-07 01:36:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73bc8a4d19e0'
down_revision: Union[str, Sequence[str], None] = '401da161d246'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create pipelines, pipeline_stages, and deals tables."""
    # 1. pipelines table
    op.create_table(
        'pipelines',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_pipelines_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pipelines')),
    )
    op.create_index(op.f('ix_pipelines_organization_id'), 'pipelines', ['organization_id'], unique=False)

    # 2. pipeline_stages table
    op.create_table(
        'pipeline_stages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('pipeline_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('order_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('probability_pct', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            'probability_pct >= 0 AND probability_pct <= 100',
            name=op.f('ck_pipeline_stages_probability_pct'),
        ),
        sa.ForeignKeyConstraint(
            ['pipeline_id'],
            ['pipelines.id'],
            name=op.f('fk_pipeline_stages_pipeline_id_pipelines'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pipeline_stages')),
    )
    op.create_index(op.f('ix_pipeline_stages_pipeline_id'), 'pipeline_stages', ['pipeline_id'], unique=False)
    op.create_index('ix_pipeline_stages_pipeline_order', 'pipeline_stages', ['pipeline_id', 'order_index'], unique=False)

    # 3. deals table
    op.create_table(
        'deals',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('pipeline_stage_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=True),
        sa.Column('company_id', sa.Uuid(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), server_default='0.00', nullable=False),
        sa.Column('expected_close_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='open', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('amount >= 0', name=op.f('ck_deals_amount_non_negative')),
        sa.CheckConstraint("status IN ('open', 'won', 'lost')", name=op.f('ck_deals_status')),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_deals_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['pipeline_stage_id'],
            ['pipeline_stages.id'],
            name=op.f('fk_deals_pipeline_stage_id_pipeline_stages'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['contact_id'],
            ['contacts.id'],
            name=op.f('fk_deals_contact_id_contacts'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['company_id'],
            ['companies.id'],
            name=op.f('fk_deals_company_id_companies'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deals')),
    )
    op.create_index(op.f('ix_deals_organization_id'), 'deals', ['organization_id'], unique=False)
    op.create_index(op.f('ix_deals_pipeline_stage_id'), 'deals', ['pipeline_stage_id'], unique=False)
    op.create_index(op.f('ix_deals_contact_id'), 'deals', ['contact_id'], unique=False)
    op.create_index(op.f('ix_deals_company_id'), 'deals', ['company_id'], unique=False)
    op.create_index(op.f('ix_deals_status'), 'deals', ['status'], unique=False)


def downgrade() -> None:
    """Drop deals, pipeline_stages, and pipelines tables."""
    op.drop_index(op.f('ix_deals_status'), table_name='deals')
    op.drop_index(op.f('ix_deals_company_id'), table_name='deals')
    op.drop_index(op.f('ix_deals_contact_id'), table_name='deals')
    op.drop_index(op.f('ix_deals_pipeline_stage_id'), table_name='deals')
    op.drop_index(op.f('ix_deals_organization_id'), table_name='deals')
    op.drop_table('deals')

    op.drop_index('ix_pipeline_stages_pipeline_order', table_name='pipeline_stages')
    op.drop_index(op.f('ix_pipeline_stages_pipeline_id'), table_name='pipeline_stages')
    op.drop_table('pipeline_stages')

    op.drop_index(op.f('ix_pipelines_organization_id'), table_name='pipelines')
    op.drop_table('pipelines')
