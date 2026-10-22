"""create channel entitlements and upgrade requests tables

Revision ID: a2b3c4d5e6f7
Revises: f2a3b4c5d6e7
Create Date: 2026-10-19 23:20:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create organization_channel_entitlements table
    op.create_table(
        'organization_channel_entitlements',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='upgrade_required'),
        sa.Column('is_unlocked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('tier', sa.String(length=50), nullable=False, server_default='starter'),
        sa.Column('allocated_quota', sa.Integer(), nullable=True),
        sa.Column('current_usage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
        sa.Column('approved_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'channel', name='uq_org_channel_entitlement'),
        sa.CheckConstraint(
            "channel IN ('email', 'sms', 'voice', 'ringless_voicemail', 'physical_mail')",
            name='ck_org_channel_entitlement_channel',
        ),
        sa.CheckConstraint(
            "status IN ('included', 'upgrade_required', 'upgrade_requested', 'approved', 'suspended')",
            name='ck_org_channel_entitlement_status',
        ),
    )
    op.create_index(
        'ix_organization_channel_entitlements_organization_id',
        'organization_channel_entitlements',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_organization_channel_entitlements_channel',
        'organization_channel_entitlements',
        ['channel'],
        unique=False,
    )

    # 2. Create channel_upgrade_requests table
    op.create_table(
        'channel_upgrade_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('requesting_user_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('estimated_volume', sa.String(length=255), nullable=True),
        sa.Column('business_justification', sa.Text(), nullable=True),
        sa.Column('reviewing_admin_id', sa.Uuid(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requesting_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewing_admin_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "channel IN ('email', 'sms', 'voice', 'ringless_voicemail', 'physical_mail')",
            name='ck_channel_upgrade_request_channel',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name='ck_channel_upgrade_request_status',
        ),
    )
    op.create_index(
        'ix_channel_upgrade_requests_organization_id',
        'channel_upgrade_requests',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_channel_upgrade_requests_channel',
        'channel_upgrade_requests',
        ['channel'],
        unique=False,
    )
    op.create_index(
        'ix_channel_upgrade_requests_status',
        'channel_upgrade_requests',
        ['status'],
        unique=False,
    )

    # 3. Create entitlement_audit_logs table
    op.create_table(
        'entitlement_audit_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('actor_role', sa.String(length=50), nullable=False),
        sa.Column('old_status', sa.String(length=50), nullable=True),
        sa.Column('new_status', sa.String(length=50), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_entitlement_audit_logs_organization_id',
        'entitlement_audit_logs',
        ['organization_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table('entitlement_audit_logs')
    op.drop_table('channel_upgrade_requests')
    op.drop_table('organization_channel_entitlements')
