"""create_icp_and_leads_tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c3
Create Date: 2026-10-07 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ideal_customer_profiles and leads tables with constraints and indexes."""
    # 1. ideal_customer_profiles
    op.create_table(
        'ideal_customer_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('industries', sa.JSON(), nullable=True),
        sa.Column('company_size_min', sa.Integer(), nullable=True),
        sa.Column('company_size_max', sa.Integer(), nullable=True),
        sa.Column('countries', sa.JSON(), nullable=True),
        sa.Column('cities', sa.JSON(), nullable=True),
        sa.Column('company_domains', sa.JSON(), nullable=True),
        sa.Column('job_titles', sa.JSON(), nullable=True),
        sa.Column('seniority_levels', sa.JSON(), nullable=True),
        sa.Column('departments', sa.JSON(), nullable=True),
        sa.Column('technologies', sa.JSON(), nullable=True),
        sa.Column('keywords', sa.JSON(), nullable=True),
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
        sa.CheckConstraint(
            'company_size_min IS NULL OR company_size_min >= 0',
            name='ck_icp_company_size_min',
        ),
        sa.CheckConstraint(
            'company_size_min IS NULL OR company_size_max IS NULL OR company_size_max >= company_size_min',
            name='ck_icp_company_size_max',
        ),
    )

    op.create_index(
        'ix_ideal_customer_profiles_organization_id',
        'ideal_customer_profiles',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_ideal_customer_profiles_is_active',
        'ideal_customer_profiles',
        ['is_active'],
        unique=False,
    )

    # 2. leads
    op.create_table(
        'leads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'icp_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('ideal_customer_profiles.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'company_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('companies.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'contact_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('contacts.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('source', sa.String(length=100), nullable=False, server_default='mock'),
        sa.Column('source_external_id', sa.String(length=255), nullable=True),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('company_domain', sa.String(length=255), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('employee_count_range', sa.String(length=50), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('job_title', sa.String(length=255), nullable=True),
        sa.Column('qualification_status', sa.String(length=50), nullable=False, server_default='new'),
        sa.Column('lead_temperature', sa.String(length=20), nullable=False, server_default='cold'),
        sa.Column('lead_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qualification_reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='new'),
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
        sa.CheckConstraint(
            'lead_score >= 0 AND lead_score <= 100',
            name='ck_lead_score_range',
        ),
        sa.CheckConstraint(
            "qualification_status IN ('new', 'qualified', 'disqualified', 'reviewed')",
            name='ck_lead_qualification_status',
        ),
        sa.CheckConstraint(
            "lead_temperature IN ('cold', 'warm', 'hot')",
            name='ck_lead_temperature',
        ),
        sa.CheckConstraint(
            "status IN ('new', 'selected', 'enrolled', 'contacted', 'replied', 'converted', 'rejected')",
            name='ck_lead_status',
        ),
        sa.UniqueConstraint(
            'organization_id',
            'source',
            'source_external_id',
            name='uq_leads_org_source_ext',
        ),
    )

    op.create_index('ix_leads_organization_id', 'leads', ['organization_id'], unique=False)
    op.create_index('ix_leads_icp_id', 'leads', ['icp_id'], unique=False)
    op.create_index('ix_leads_company_id', 'leads', ['company_id'], unique=False)
    op.create_index('ix_leads_contact_id', 'leads', ['contact_id'], unique=False)
    op.create_index('ix_leads_source', 'leads', ['source'], unique=False)
    op.create_index('ix_leads_company_domain', 'leads', ['company_domain'], unique=False)
    op.create_index('ix_leads_industry', 'leads', ['industry'], unique=False)
    op.create_index('ix_leads_city', 'leads', ['city'], unique=False)
    op.create_index('ix_leads_country', 'leads', ['country'], unique=False)
    op.create_index('ix_leads_email', 'leads', ['email'], unique=False)
    op.create_index('ix_leads_job_title', 'leads', ['job_title'], unique=False)
    op.create_index('ix_leads_qualification_status', 'leads', ['qualification_status'], unique=False)
    op.create_index('ix_leads_lead_temperature', 'leads', ['lead_temperature'], unique=False)
    op.create_index('ix_leads_lead_score', 'leads', ['lead_score'], unique=False)
    op.create_index('ix_leads_status', 'leads', ['status'], unique=False)


def downgrade() -> None:
    """Drop leads and ideal_customer_profiles tables."""
    op.drop_index('ix_leads_status', table_name='leads')
    op.drop_index('ix_leads_lead_score', table_name='leads')
    op.drop_index('ix_leads_lead_temperature', table_name='leads')
    op.drop_index('ix_leads_qualification_status', table_name='leads')
    op.drop_index('ix_leads_job_title', table_name='leads')
    op.drop_index('ix_leads_email', table_name='leads')
    op.drop_index('ix_leads_country', table_name='leads')
    op.drop_index('ix_leads_city', table_name='leads')
    op.drop_index('ix_leads_industry', table_name='leads')
    op.drop_index('ix_leads_company_domain', table_name='leads')
    op.drop_index('ix_leads_source', table_name='leads')
    op.drop_index('ix_leads_contact_id', table_name='leads')
    op.drop_index('ix_leads_company_id', table_name='leads')
    op.drop_index('ix_leads_icp_id', table_name='leads')
    op.drop_index('ix_leads_organization_id', table_name='leads')
    op.drop_table('leads')

    op.drop_index('ix_ideal_customer_profiles_is_active', table_name='ideal_customer_profiles')
    op.drop_index('ix_ideal_customer_profiles_organization_id', table_name='ideal_customer_profiles')
    op.drop_table('ideal_customer_profiles')
