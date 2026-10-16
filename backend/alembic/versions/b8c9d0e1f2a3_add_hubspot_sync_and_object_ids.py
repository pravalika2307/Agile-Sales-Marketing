"""add_hubspot_sync_and_object_ids

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add hubspot_id to companies
    op.add_column(
        'companies',
        sa.Column('hubspot_id', sa.String(100), nullable=True),
    )
    op.create_index(
        'ix_companies_hubspot_id',
        'companies',
        ['hubspot_id'],
        unique=False,
    )
    op.create_index(
        'ix_companies_org_hubspot_id',
        'companies',
        ['organization_id', 'hubspot_id'],
        unique=False,
    )

    # 2. Add hubspot_id to contacts
    op.add_column(
        'contacts',
        sa.Column('hubspot_id', sa.String(100), nullable=True),
    )
    op.create_index(
        'ix_contacts_hubspot_id',
        'contacts',
        ['hubspot_id'],
        unique=False,
    )
    op.create_index(
        'ix_contacts_org_hubspot_id',
        'contacts',
        ['organization_id', 'hubspot_id'],
        unique=False,
    )

    # 3. Add hubspot_id to deals
    op.add_column(
        'deals',
        sa.Column('hubspot_id', sa.String(100), nullable=True),
    )
    op.create_index(
        'ix_deals_hubspot_id',
        'deals',
        ['hubspot_id'],
        unique=False,
    )
    op.create_index(
        'ix_deals_org_hubspot_id',
        'deals',
        ['organization_id', 'hubspot_id'],
        unique=False,
    )

    # 4. Create hubspot_sync_runs table
    op.create_table(
        'hubspot_sync_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String(50), nullable=False, server_default='completed'),
        sa.Column('contacts_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('companies_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deals_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('portal_id', sa.String(50), nullable=True),
        sa.Column('permission_errors', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        'ix_hubspot_sync_runs_org_id',
        'hubspot_sync_runs',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_hubspot_sync_runs_created_at',
        'hubspot_sync_runs',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_hubspot_sync_runs_created_at', table_name='hubspot_sync_runs')
    op.drop_index('ix_hubspot_sync_runs_org_id', table_name='hubspot_sync_runs')
    op.drop_table('hubspot_sync_runs')

    op.drop_index('ix_deals_org_hubspot_id', table_name='deals')
    op.drop_index('ix_deals_hubspot_id', table_name='deals')
    op.drop_column('deals', 'hubspot_id')

    op.drop_index('ix_contacts_org_hubspot_id', table_name='contacts')
    op.drop_index('ix_contacts_hubspot_id', table_name='contacts')
    op.drop_column('contacts', 'hubspot_id')

    op.drop_index('ix_companies_org_hubspot_id', table_name='companies')
    op.drop_index('ix_companies_hubspot_id', table_name='companies')
    op.drop_column('companies', 'hubspot_id')
