"""add linkedin_profile_url to leads and contacts tables

Revision ID: e7f8a9b0c1d3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-28 00:30:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head' WITHOUT EXPLICIT APPROVAL.
This migration file is prepared for execution when approved by user.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add linkedin_profile_url column to leads and contacts tables."""
    op.add_column(
        'leads',
        sa.Column('linkedin_profile_url', sa.String(500), nullable=True),
    )
    op.add_column(
        'contacts',
        sa.Column('linkedin_profile_url', sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Drop linkedin_profile_url column from contacts and leads tables."""
    op.drop_column('contacts', 'linkedin_profile_url')
    op.drop_column('leads', 'linkedin_profile_url')
