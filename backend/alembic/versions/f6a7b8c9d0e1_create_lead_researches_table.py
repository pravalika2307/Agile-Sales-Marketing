"""create_lead_researches_table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-08 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create lead_researches table with tenant isolation and structured intelligence fields."""
    op.create_table(
        'lead_researches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'lead_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('leads.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('company_summary', sa.Text(), nullable=True),
        sa.Column('industry', sa.String(length=150), nullable=True),
        sa.Column('company_size', sa.String(length=100), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('business_signals', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('potential_pain_points', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('personalization_points', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('research_summary', sa.Text(), nullable=True),
        sa.Column('source_urls', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column(
            'researched_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('research_status', sa.String(length=50), nullable=False, server_default='completed'),
        sa.Column('error_message', sa.Text(), nullable=True),
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
        sa.UniqueConstraint('organization_id', 'lead_id', name='uq_lead_researches_org_lead'),
        sa.CheckConstraint(
            "research_status IN ('pending', 'completed', 'failed', 'stale')",
            name='ck_lead_research_status',
        ),
    )

    op.create_index(
        'ix_lead_researches_organization_id',
        'lead_researches',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_lead_researches_lead_id',
        'lead_researches',
        ['lead_id'],
        unique=False,
    )
    op.create_index(
        'ix_lead_researches_industry',
        'lead_researches',
        ['industry'],
        unique=False,
    )
    op.create_index(
        'ix_lead_researches_researched_at',
        'lead_researches',
        ['researched_at'],
        unique=False,
    )
    op.create_index(
        'ix_lead_researches_research_status',
        'lead_researches',
        ['research_status'],
        unique=False,
    )


def downgrade() -> None:
    """Drop lead_researches table and indexes."""
    op.drop_index('ix_lead_researches_research_status', table_name='lead_researches')
    op.drop_index('ix_lead_researches_researched_at', table_name='lead_researches')
    op.drop_index('ix_lead_researches_industry', table_name='lead_researches')
    op.drop_index('ix_lead_researches_lead_id', table_name='lead_researches')
    op.drop_index('ix_lead_researches_organization_id', table_name='lead_researches')
    op.drop_table('lead_researches')
