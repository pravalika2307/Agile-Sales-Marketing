"""add_campaign_description_and_workflow_config

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-10 01:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add description and workflow_config columns to campaigns table."""
    op.add_column('campaigns', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('campaigns', sa.Column('workflow_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove description and workflow_config columns from campaigns table."""
    op.drop_column('campaigns', 'workflow_config')
    op.drop_column('campaigns', 'description')
