"""create_lead_routing_rules

Revision ID: e7f8a9b0c1d2
Revises: c9d0e1f2a3b4
Create Date: 2026-10-12 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create lead_routing_rules table
    op.create_table(
        'lead_routing_rules',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('industries', sa.JSON(), nullable=True),
        sa.Column('company_size_min', sa.Integer(), nullable=True),
        sa.Column('company_size_max', sa.Integer(), nullable=True),
        sa.Column('countries', sa.JSON(), nullable=True),
        sa.Column('cities', sa.JSON(), nullable=True),
        sa.Column('min_score', sa.Integer(), nullable=True),
        sa.Column('max_score', sa.Integer(), nullable=True),
        sa.Column('qualification_statuses', sa.JSON(), nullable=True),
        sa.Column('assigned_to_user_id', sa.Uuid(), nullable=True),
        sa.Column('assigned_team', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lead_routing_rules_organization_id'), 'lead_routing_rules', ['organization_id'], unique=False)
    op.create_index(op.f('ix_lead_routing_rules_is_active'), 'lead_routing_rules', ['is_active'], unique=False)
    op.create_index(op.f('ix_lead_routing_rules_assigned_to_user_id'), 'lead_routing_rules', ['assigned_to_user_id'], unique=False)

    # 2. Add routing columns to leads table
    op.add_column('leads', sa.Column('assigned_to_user_id', sa.Uuid(), nullable=True))
    op.add_column('leads', sa.Column('routing_rule_id', sa.Uuid(), nullable=True))
    op.add_column('leads', sa.Column('routed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('leads', sa.Column('routing_notes', sa.Text(), nullable=True))

    op.create_foreign_key(
        'fk_leads_assigned_to_user',
        'leads', 'users',
        ['assigned_to_user_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_leads_routing_rule',
        'leads', 'lead_routing_rules',
        ['routing_rule_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index(op.f('ix_leads_assigned_to_user_id'), 'leads', ['assigned_to_user_id'], unique=False)
    op.create_index(op.f('ix_leads_routing_rule_id'), 'leads', ['routing_rule_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_leads_routing_rule_id'), table_name='leads')
    op.drop_index(op.f('ix_leads_assigned_to_user_id'), table_name='leads')
    op.drop_constraint('fk_leads_routing_rule', 'leads', type_='foreignkey')
    op.drop_constraint('fk_leads_assigned_to_user', 'leads', type_='foreignkey')
    op.drop_column('leads', 'routing_notes')
    op.drop_column('leads', 'routed_at')
    op.drop_column('leads', 'routing_rule_id')
    op.drop_column('leads', 'assigned_to_user_id')

    op.drop_index(op.f('ix_lead_routing_rules_assigned_to_user_id'), table_name='lead_routing_rules')
    op.drop_index(op.f('ix_lead_routing_rules_is_active'), table_name='lead_routing_rules')
    op.drop_index(op.f('ix_lead_routing_rules_organization_id'), table_name='lead_routing_rules')
    op.drop_table('lead_routing_rules')
