"""add postal address fields and physical_mail channel support

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-22 20:30:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add postal address columns and physical_mail channel support."""
    # 1. contacts address columns
    op.add_column('contacts', sa.Column('address_line_1', sa.String(255), nullable=True))
    op.add_column('contacts', sa.Column('address_line_2', sa.String(255), nullable=True))
    op.add_column('contacts', sa.Column('city', sa.String(100), nullable=True))
    op.add_column('contacts', sa.Column('state', sa.String(50), nullable=True))
    op.add_column('contacts', sa.Column('postal_code', sa.String(20), nullable=True))
    op.add_column('contacts', sa.Column('country', sa.String(100), nullable=True, server_default='US'))

    # 2. leads address columns (leads already has city and country)
    op.add_column('leads', sa.Column('address_line_1', sa.String(255), nullable=True))
    op.add_column('leads', sa.Column('address_line_2', sa.String(255), nullable=True))
    op.add_column('leads', sa.Column('state', sa.String(50), nullable=True))
    op.add_column('leads', sa.Column('postal_code', sa.String(20), nullable=True))

    # 3. outreach channel check constraint
    op.drop_constraint('ck_outreach_channel', 'outreach', type_='check')
    op.create_check_constraint(
        'ck_outreach_channel',
        'outreach',
        "channel IN ('email', 'linkedin', 'voice', 'sms', 'physical_mail')"
    )

    # 4. campaign_steps step_type check constraint
    op.drop_constraint('ck_campaign_steps_step_type', 'campaign_steps', type_='check')
    op.create_check_constraint(
        'ck_campaign_steps_step_type',
        'campaign_steps',
        "step_type IN ('email', 'sms', 'voice', 'physical_mail')"
    )


def downgrade() -> None:
    """Revert postal address columns and channel constraints."""
    op.drop_constraint('ck_campaign_steps_step_type', 'campaign_steps', type_='check')
    op.create_check_constraint(
        'ck_campaign_steps_step_type',
        'campaign_steps',
        "step_type IN ('email', 'sms', 'voice')"
    )

    op.drop_constraint('ck_outreach_channel', 'outreach', type_='check')
    op.create_check_constraint(
        'ck_outreach_channel',
        'outreach',
        "channel IN ('email', 'linkedin', 'voice', 'sms')"
    )

    op.drop_column('leads', 'postal_code')
    op.drop_column('leads', 'state')
    op.drop_column('leads', 'address_line_2')
    op.drop_column('leads', 'address_line_1')

    op.drop_column('contacts', 'country')
    op.drop_column('contacts', 'postal_code')
    op.drop_column('contacts', 'state')
    op.drop_column('contacts', 'city')
    op.drop_column('contacts', 'address_line_2')
    op.drop_column('contacts', 'address_line_1')
