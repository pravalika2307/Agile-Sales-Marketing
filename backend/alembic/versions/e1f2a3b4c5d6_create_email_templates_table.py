"""create email_templates table for reusable cross-campaign templates

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-10-16 21:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'email_templates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), server_default='outbound', nullable=False),
        sa.Column('subject_template', sa.Text(), nullable=False),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_templates_org_id', 'email_templates', ['organization_id'], unique=False)
    op.create_index('ix_email_templates_org_category', 'email_templates', ['organization_id', 'category'], unique=False)
    op.create_index('ix_email_templates_org_name', 'email_templates', ['organization_id', 'name'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_email_templates_org_name', table_name='email_templates')
    op.drop_index('ix_email_templates_org_category', table_name='email_templates')
    op.drop_index('ix_email_templates_org_id', table_name='email_templates')
    op.drop_table('email_templates')
