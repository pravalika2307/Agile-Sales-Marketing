"""create contact lists, members, and campaign lists tables

Revision ID: d1e2f3a4b5c6
Revises: b2c3d4e5f6a7
Create Date: 2026-10-14 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create contact_lists table
    op.create_table(
        'contact_lists',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(length=50), server_default='static', nullable=False),
        sa.Column('filter_criteria', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contact_lists_org_id', 'contact_lists', ['organization_id'], unique=False)
    op.create_index(
        'uq_contact_lists_org_lower_name',
        'contact_lists',
        ['organization_id', sa.text('lower(name)')],
        unique=True,
    )

    # 2. Create contact_list_members table
    op.create_table(
        'contact_list_members',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('contact_list_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=True),
        sa.Column('lead_id', sa.Uuid(), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            '(contact_id IS NOT NULL) OR (lead_id IS NOT NULL)',
            name='ck_contact_list_members_target_present',
        ),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_list_id'], ['contact_lists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contact_list_members_list_id', 'contact_list_members', ['contact_list_id'], unique=False)
    op.create_index('ix_contact_list_members_contact_id', 'contact_list_members', ['contact_id'], unique=False)
    op.create_index('ix_contact_list_members_lead_id', 'contact_list_members', ['lead_id'], unique=False)
    op.create_index(
        'uq_list_member_contact',
        'contact_list_members',
        ['contact_list_id', 'contact_id'],
        unique=True,
        postgresql_where=sa.text('contact_id IS NOT NULL'),
    )
    op.create_index(
        'uq_list_member_lead',
        'contact_list_members',
        ['contact_list_id', 'lead_id'],
        unique=True,
        postgresql_where=sa.text('lead_id IS NOT NULL'),
    )

    # 3. Create campaign_lists table
    op.create_table(
        'campaign_lists',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('contact_list_id', sa.Uuid(), nullable=False),
        sa.Column('associated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_list_id'], ['contact_lists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'contact_list_id', name='uq_campaign_lists_campaign_list'),
    )
    op.create_index('ix_campaign_lists_campaign_id', 'campaign_lists', ['campaign_id'], unique=False)
    op.create_index('ix_campaign_lists_list_id', 'campaign_lists', ['contact_list_id'], unique=False)


def downgrade() -> None:
    op.drop_table('campaign_lists')
    op.drop_table('contact_list_members')
    op.drop_table('contact_lists')
