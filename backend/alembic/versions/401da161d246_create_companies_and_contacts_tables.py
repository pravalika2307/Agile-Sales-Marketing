"""create_companies_and_contacts_tables

Revision ID: 401da161d246
Revises: 9f008e0f621f
Create Date: 2026-10-07 01:23:54.488814

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '401da161d246'
down_revision: Union[str, Sequence[str], None] = '9f008e0f621f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create companies and contacts tables."""
    # 1. companies table
    op.create_table(
        'companies',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=True),
        sa.Column('industry', sa.String(length=255), nullable=True),
        sa.Column('employee_count_range', sa.String(length=100), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_companies_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_companies')),
    )
    op.create_index(op.f('ix_companies_organization_id'), 'companies', ['organization_id'], unique=False)
    op.create_index(op.f('ix_companies_name'), 'companies', ['name'], unique=False)

    # 2. contacts table
    op.create_table(
        'contacts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('company_id', sa.Uuid(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('job_title', sa.String(length=150), nullable=True),
        sa.Column('lead_status', sa.String(length=50), server_default='new', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['organizations.id'],
            name=op.f('fk_contacts_organization_id_organizations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['company_id'],
            ['companies.id'],
            name=op.f('fk_contacts_company_id_companies'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contacts')),
    )
    op.create_index(op.f('ix_contacts_organization_id'), 'contacts', ['organization_id'], unique=False)
    op.create_index(op.f('ix_contacts_company_id'), 'contacts', ['company_id'], unique=False)
    op.create_index(op.f('ix_contacts_email'), 'contacts', ['email'], unique=False)
    op.create_index('ix_contacts_org_email', 'contacts', ['organization_id', 'email'], unique=False)


def downgrade() -> None:
    """Drop contacts and companies tables."""
    op.drop_index('ix_contacts_org_email', table_name='contacts')
    op.drop_index(op.f('ix_contacts_email'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_company_id'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_organization_id'), table_name='contacts')
    op.drop_table('contacts')

    op.drop_index(op.f('ix_companies_name'), table_name='companies')
    op.drop_index(op.f('ix_companies_organization_id'), table_name='companies')
    op.drop_table('companies')
