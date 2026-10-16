"""create_campaigns_and_campaign_contacts_tables

Revision ID: 8f4b2a1c09de
Revises: 73bc8a4d19e0
Create Date: 2026-10-07 01:44:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f4b2a1c09de'
down_revision: Union[str, Sequence[str], None] = '73bc8a4d19e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create campaigns and campaign_contacts tables."""
    # 1. campaigns table
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='draft', nullable=False),
        sa.Column('schedule_settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "type IN ('sales_outbound', 'marketing_social', 'hybrid')",
            name=op.f('ck_campaigns_type'),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed')",
            name=op.f('ck_campaigns_status'),
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_campaigns_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaigns')),
    )
    op.create_index(op.f('ix_campaigns_organization_id'), 'campaigns', ['organization_id'], unique=False)
    op.create_index(op.f('ix_campaigns_status'), 'campaigns', ['status'], unique=False)

    # 2. campaign_contacts table
    op.create_table(
        'campaign_contacts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('enrollment_status', sa.String(length=50), server_default='queued', nullable=False),
        sa.Column('current_step', sa.Integer(), server_default='0', nullable=False),
        sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "enrollment_status IN ('queued', 'in_progress', 'replied', 'bounced', 'completed')",
            name=op.f('ck_campaign_contacts_enrollment_status'),
        ),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.id'],
            name=op.f('fk_campaign_contacts_campaign_id_campaigns'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['contact_id'],
            ['contacts.id'],
            name=op.f('fk_campaign_contacts_contact_id_contacts'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_contacts')),
        sa.UniqueConstraint('campaign_id', 'contact_id', name='uq_campaign_contact'),
    )
    op.create_index(op.f('ix_campaign_contacts_campaign_id'), 'campaign_contacts', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_campaign_contacts_contact_id'), 'campaign_contacts', ['contact_id'], unique=False)
    op.create_index(op.f('ix_campaign_contacts_enrollment_status'), 'campaign_contacts', ['enrollment_status'], unique=False)


def downgrade() -> None:
    """Drop campaign_contacts and campaigns tables."""
    op.drop_index(op.f('ix_campaign_contacts_enrollment_status'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_contact_id'), table_name='campaign_contacts')
    op.drop_index(op.f('ix_campaign_contacts_campaign_id'), table_name='campaign_contacts')
    op.drop_table('campaign_contacts')

    op.drop_index(op.f('ix_campaigns_status'), table_name='campaigns')
    op.drop_index(op.f('ix_campaigns_organization_id'), table_name='campaigns')
    op.drop_table('campaigns')
