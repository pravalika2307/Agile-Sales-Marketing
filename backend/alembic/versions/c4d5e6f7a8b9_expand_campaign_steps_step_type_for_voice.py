"""expand campaign_steps step_type check constraint for voice

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-22 18:45:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand campaign_steps.step_type check constraint to include 'voice'."""
    # Drop existing constraint allowing email, sms
    op.drop_constraint('ck_campaign_steps_step_type', 'campaign_steps', type_='check')

    # Re-create constraint allowing 'email', 'sms', and 'voice'
    op.create_check_constraint(
        'ck_campaign_steps_step_type',
        'campaign_steps',
        "step_type IN ('email', 'sms', 'voice')",
    )


def downgrade() -> None:
    """Revert campaign_steps.step_type check constraint to only allow 'email' and 'sms'."""
    op.drop_constraint('ck_campaign_steps_step_type', 'campaign_steps', type_='check')
    op.create_check_constraint(
        'ck_campaign_steps_step_type',
        'campaign_steps',
        "step_type IN ('email', 'sms')",
    )
