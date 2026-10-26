"""create linkedin_connections and linkedin_oauth_states tables

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-26 20:00:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create linkedin_connections and linkedin_oauth_states tables."""
    # 1. linkedin_connections
    op.create_table(
        'linkedin_connections',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('linkedin_member_id', sa.String(100), nullable=False),
        sa.Column('member_name', sa.String(255), nullable=True),
        sa.Column('member_email', sa.String(255), nullable=True),
        sa.Column('profile_picture_url', sa.String(1000), nullable=True),
        sa.Column('encrypted_access_token', sa.Text(), nullable=False),
        sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('encrypted_refresh_token', sa.Text(), nullable=True),
        sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.String(500), nullable=False, server_default='openid,profile,email'),
        sa.Column('status', sa.String(50), nullable=False, server_default='connected'),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_linkedin_connections_organization_id', 'linkedin_connections', ['organization_id'], unique=True)
    op.create_index('ix_linkedin_connections_user_id', 'linkedin_connections', ['user_id'], unique=False)
    op.create_index('ix_linkedin_connections_linkedin_member_id', 'linkedin_connections', ['linkedin_member_id'], unique=False)

    # 2. linkedin_oauth_states
    op.create_table(
        'linkedin_oauth_states',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('state', sa.String(128), nullable=False),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('nonce', sa.String(128), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_linkedin_oauth_states_state', 'linkedin_oauth_states', ['state'], unique=True)
    op.create_index('ix_linkedin_oauth_states_organization_id', 'linkedin_oauth_states', ['organization_id'], unique=False)
    op.create_index('ix_linkedin_oauth_states_user_id', 'linkedin_oauth_states', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop linkedin_oauth_states and linkedin_connections tables."""
    op.drop_index('ix_linkedin_oauth_states_user_id', table_name='linkedin_oauth_states')
    op.drop_index('ix_linkedin_oauth_states_organization_id', table_name='linkedin_oauth_states')
    op.drop_index('ix_linkedin_oauth_states_state', table_name='linkedin_oauth_states')
    op.drop_table('linkedin_oauth_states')

    op.drop_index('ix_linkedin_connections_linkedin_member_id', table_name='linkedin_connections')
    op.drop_index('ix_linkedin_connections_user_id', table_name='linkedin_connections')
    op.drop_index('ix_linkedin_connections_organization_id', table_name='linkedin_connections')
    op.drop_table('linkedin_connections')
