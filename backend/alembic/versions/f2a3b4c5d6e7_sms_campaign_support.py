"""add sms support to campaign_steps step_type constraint

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-19 21:00:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand campaign_steps.step_type check constraint to include 'sms'."""
    # Drop existing single-channel constraint
    op.drop_constraint('ck_campaign_steps_step_type', 'campaign_steps', type_='check')
    
    # Re-create constraint allowing both 'email' and 'sms'
    op.create_check_constraint(
        'ck_campaign_steps_step_type',
        'campaign_steps',
        "step_type IN ('email', 'sms')",
    )


def downgrade() -> None:
    """Revert campaign_steps.step_type check constraint back to email only."""
    op.drop_constraint('ck_campaign_steps_step_type', 'campaign_steps', type_='check')
    op.create_check_constraint(
        'ck_campaign_steps_step_type',
        'campaign_steps',
        "step_type IN ('email')",
    )
