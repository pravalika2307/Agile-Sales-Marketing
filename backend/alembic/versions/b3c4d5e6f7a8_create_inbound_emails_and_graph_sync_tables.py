"""create inbound emails and graph sync tables

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-10-21 18:30:00.000000

NOTE: PROPOSED MIGRATION ONLY.
PER STRICT USER AUTHORIZATION RULES, DO NOT EXECUTE 'alembic upgrade head'.
This migration file is prepared for future execution when schema updates are scheduled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create inbound_emails table
    op.create_table(
        'inbound_emails',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('graph_message_id', sa.String(length=255), nullable=False),
        sa.Column('graph_conversation_id', sa.String(length=255), nullable=True),
        sa.Column('internet_message_id', sa.String(length=255), nullable=True),
        sa.Column('sender_email', sa.String(length=255), nullable=False),
        sa.Column('sender_name', sa.String(length=255), nullable=True),
        sa.Column('recipient_email', sa.String(length=255), nullable=False, server_default='support@agilereceivables.com'),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('body_preview', sa.Text(), nullable=True),
        sa.Column('body_content', sa.Text(), nullable=True),
        sa.Column('body_content_type', sa.String(length=20), nullable=False, server_default='html'),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('has_attachments', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('matched_contact_id', sa.Uuid(), nullable=True),
        sa.Column('matched_lead_id', sa.Uuid(), nullable=True),
        sa.Column('matched_company_id', sa.Uuid(), nullable=True),
        sa.Column('sync_status', sa.String(length=50), nullable=False, server_default='unmatched'),
        sa.Column('manual_review_status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('raw_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['matched_lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['matched_company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'graph_message_id', name='uq_inbound_emails_org_graph_msg_id'),
        sa.CheckConstraint("sync_status IN ('matched', 'unmatched', 'review_required', 'error')", name='ck_inbound_emails_sync_status'),
        sa.CheckConstraint("manual_review_status IN ('pending', 'reviewed', 'dismissed', 'archived')", name='ck_inbound_emails_review_status'),
    )
    op.create_index('ix_inbound_emails_organization_id', 'inbound_emails', ['organization_id'])
    op.create_index('ix_inbound_emails_graph_message_id', 'inbound_emails', ['graph_message_id'])
    op.create_index('ix_inbound_emails_graph_conversation_id', 'inbound_emails', ['graph_conversation_id'])
    op.create_index('ix_inbound_emails_internet_message_id', 'inbound_emails', ['internet_message_id'])
    op.create_index('ix_inbound_emails_sender_email', 'inbound_emails', ['sender_email'])
    op.create_index('ix_inbound_emails_received_at', 'inbound_emails', ['received_at'])
    op.create_index('ix_inbound_emails_matched_contact_id', 'inbound_emails', ['matched_contact_id'])
    op.create_index('ix_inbound_emails_matched_lead_id', 'inbound_emails', ['matched_lead_id'])
    op.create_index('ix_inbound_emails_matched_company_id', 'inbound_emails', ['matched_company_id'])
    op.create_index('ix_inbound_emails_sync_status', 'inbound_emails', ['sync_status'])
    op.create_index('ix_inbound_emails_manual_review_status', 'inbound_emails', ['manual_review_status'])
    op.create_index('ix_inbound_emails_org_received', 'inbound_emails', ['organization_id', 'received_at'])
    op.create_index('ix_inbound_emails_org_sender', 'inbound_emails', ['organization_id', 'sender_email'])
    op.create_index('ix_inbound_emails_org_sync_status', 'inbound_emails', ['organization_id', 'sync_status'])
    op.create_index('ix_inbound_emails_org_review_status', 'inbound_emails', ['organization_id', 'manual_review_status'])

    # 2. Create graph_sync_runs table
    op.create_table(
        'graph_sync_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('mailbox_address', sa.String(length=255), nullable=False),
        sa.Column('sync_trigger', sa.String(length=50), nullable=False, server_default='manual'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='completed'),
        sa.Column('messages_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_imported', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_matched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_unmatched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('checkpoint_delta_link', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('completed', 'partial', 'failed', 'running', 'skipped_concurrency_lock')", name='ck_graph_sync_runs_status'),
    )
    op.create_index('ix_graph_sync_runs_organization_id', 'graph_sync_runs', ['organization_id'])
    op.create_index('ix_graph_sync_runs_created_at', 'graph_sync_runs', ['created_at'])
    op.create_index('ix_graph_sync_runs_org_created', 'graph_sync_runs', ['organization_id', 'created_at'])

    # 3. Create graph_mailbox_checkpoints table
    op.create_table(
        'graph_mailbox_checkpoints',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('mailbox_address', sa.String(length=255), nullable=False),
        sa.Column('delta_link', sa.Text(), nullable=True),
        sa.Column('is_syncing', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('sync_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_status', sa.String(length=50), nullable=False, server_default='idle'),
        sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_imported', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'mailbox_address', name='uq_graph_mailbox_checkpoint_org_mailbox'),
    )
    op.create_index('ix_graph_checkpoint_org_mailbox', 'graph_mailbox_checkpoints', ['organization_id', 'mailbox_address'])


def downgrade() -> None:
    op.drop_table('graph_mailbox_checkpoints')
    op.drop_table('graph_sync_runs')
    op.drop_table('inbound_emails')
