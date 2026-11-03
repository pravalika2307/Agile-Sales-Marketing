"""create campaign_execution_jobs table

Revision ID: a1b2c3d4e5f7
Revises: f0a1b2c3d4e5
Create Date: 2026-11-03 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = 'f0a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'campaign_execution_jobs',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=True),
        sa.Column('campaign_contact_id', sa.Uuid(), nullable=True),
        sa.Column('contact_id', sa.Uuid(), nullable=True),
        sa.Column('campaign_step_id', sa.Uuid(), nullable=True),
        sa.Column('outreach_id', sa.Uuid(), nullable=True),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('step_identifier', sa.String(length=100), nullable=True),
        sa.Column('channel', sa.String(length=50), server_default='email', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        
        # Worker fencing and lease tracking
        sa.Column('worker_id', sa.String(length=100), nullable=True),
        sa.Column('lease_token', sa.Uuid(), nullable=True),
        sa.Column('leased_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        
        # Ambiguous provider outcome detection
        sa.Column('dispatch_started_at', sa.DateTime(timezone=True), nullable=True),
        
        # Permanent durable idempotency key
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        
        # Immutable execution payload snapshot (frozen template, parameters, channel config)
        sa.Column('execution_payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        
        # Audit snapshot fields (preserved even if CRM records are deleted)
        sa.Column('campaign_name_snapshot', sa.String(length=255), nullable=True),
        sa.Column('recipient_snapshot', sa.String(length=255), nullable=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),

        sa.PrimaryKeyConstraint('id', name='pk_campaign_execution_jobs'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_campaign_execution_jobs_organization_id', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name='fk_campaign_execution_jobs_campaign_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_contact_id'], ['campaign_contacts.id'], name='fk_campaign_execution_jobs_campaign_contact_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name='fk_campaign_execution_jobs_contact_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_step_id'], ['campaign_steps.id'], name='fk_campaign_execution_jobs_campaign_step_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['outreach_id'], ['outreach.id'], name='fk_campaign_execution_jobs_outreach_id', ondelete='SET NULL'),
        sa.UniqueConstraint('idempotency_key', name='uq_campaign_execution_jobs_idempotency_key'),
        
        # Check constraints
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'retry_scheduled', 'held', 'dispatch_unknown')",
            name='ck_campaign_execution_jobs_status'
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'voice', 'sms', 'physical_mail', 'linkedin')",
            name='ck_campaign_execution_jobs_channel'
        ),
        sa.CheckConstraint('attempts >= 0', name='ck_campaign_execution_jobs_attempts'),
        sa.CheckConstraint('max_attempts >= 1', name='ck_campaign_execution_jobs_max_attempts'),
        
        # Safe entity deletion check: active and unresolved jobs (including dispatch_unknown) must never be orphaned
        sa.CheckConstraint(
            "status NOT IN ('pending', 'processing', 'retry_scheduled', 'dispatch_unknown') "
            "OR (campaign_id IS NOT NULL AND contact_id IS NOT NULL AND campaign_contact_id IS NOT NULL)",
            name='ck_campaign_execution_jobs_active_entities'
        ),
        
        # Channel authorization check: physical mail & LinkedIn cannot be auto-dispatched
        sa.CheckConstraint(
            "channel IN ('email', 'voice', 'sms') "
            "OR status IN ('held', 'completed', 'failed')",
            name='ck_campaign_execution_jobs_channel_dispatch'
        ),
        
        # Payload structure check: execution_payload must be a valid JSON object
        sa.CheckConstraint(
            "jsonb_typeof(execution_payload) = 'object'",
            name='ck_campaign_execution_jobs_payload_object'
        ),
    )

    # Polling index for active job claiming: tenant-scoped, status, scheduled_at
    op.create_index(
        'ix_campaign_execution_jobs_poll',
        'campaign_execution_jobs',
        ['organization_id', 'status', 'scheduled_at'],
        unique=False
    )

    # Lease recovery index for expired leases and crash recovery
    op.create_index(
        'ix_campaign_execution_jobs_lease_recovery',
        'campaign_execution_jobs',
        ['status', 'lease_expires_at'],
        unique=False
    )

    # Contact enrollment and step lookup index
    op.create_index(
        'ix_campaign_execution_jobs_enrollment_step',
        'campaign_execution_jobs',
        ['campaign_contact_id', 'step_number'],
        unique=False
    )

    # Campaign lookup index
    op.create_index(
        'ix_campaign_execution_jobs_campaign_id',
        'campaign_execution_jobs',
        ['campaign_id'],
        unique=False
    )

    # Worker active lease lookup
    op.create_index(
        'ix_campaign_execution_jobs_worker_lease',
        'campaign_execution_jobs',
        ['worker_id', 'lease_token'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_campaign_execution_jobs_worker_lease', table_name='campaign_execution_jobs')
    op.drop_index('ix_campaign_execution_jobs_campaign_id', table_name='campaign_execution_jobs')
    op.drop_index('ix_campaign_execution_jobs_enrollment_step', table_name='campaign_execution_jobs')
    op.drop_index('ix_campaign_execution_jobs_lease_recovery', table_name='campaign_execution_jobs')
    op.drop_index('ix_campaign_execution_jobs_poll', table_name='campaign_execution_jobs')
    op.drop_table('campaign_execution_jobs')
