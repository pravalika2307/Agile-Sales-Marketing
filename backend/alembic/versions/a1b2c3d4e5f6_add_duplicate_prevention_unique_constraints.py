"""add_duplicate_prevention_unique_constraints

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-10-12 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Company unique lower domain per tenant
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_org_lower_domain
        ON companies (organization_id, LOWER(domain))
        WHERE domain IS NOT NULL AND TRIM(domain) != '';
    """)

    # 2. Company unique HubSpot ID per tenant
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_org_hubspot_id
        ON companies (organization_id, hubspot_id)
        WHERE hubspot_id IS NOT NULL;
    """)

    # 3. Contact unique HubSpot ID per tenant
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_org_hubspot_id
        ON contacts (organization_id, hubspot_id)
        WHERE hubspot_id IS NOT NULL;
    """)

    # 4. Lead unique lower email per tenant
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_org_lower_email
        ON leads (organization_id, LOWER(email))
        WHERE email IS NOT NULL AND TRIM(email) != '';
    """)

    # 5. Pre-check for Contact email duplicates
    # Per safety policy: Verify no duplicates before attempting unique constraint.
    # If duplicates exist, stop/skip this constraint, preserve existing data, and report blocker.
    conn = op.get_bind()
    contact_dupes = conn.execute(sa.text("""
        SELECT organization_id, LOWER(email), COUNT(*)
        FROM contacts
        WHERE email IS NOT NULL AND TRIM(email) != ''
        GROUP BY organization_id, LOWER(email)
        HAVING COUNT(*) > 1
    """)).fetchall()

    if contact_dupes:
        # Detected existing duplicate contact records.
        # As per rule: Do not clean up or overwrite business data.
        # Report blocker and do not create uq_contacts_org_lower_email.
        print(f"[MIGRATION NOTICE] uq_contacts_org_lower_email blocked by {len(contact_dupes)} existing duplicate group(s):")
        for org_id, email, cnt in contact_dupes:
            print(f"  - Org: {org_id}, Email: {email}, Count: {cnt}")
        print("Safely skipped uq_contacts_org_lower_email to preserve business data. Race protection enforced via application locking.")
    else:
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_org_lower_email
            ON contacts (organization_id, LOWER(email))
            WHERE email IS NOT NULL AND TRIM(email) != '';
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_contacts_org_lower_email;")
    op.execute("DROP INDEX IF EXISTS uq_leads_org_lower_email;")
    op.execute("DROP INDEX IF EXISTS uq_contacts_org_hubspot_id;")
    op.execute("DROP INDEX IF EXISTS uq_companies_org_hubspot_id;")
    op.execute("DROP INDEX IF EXISTS uq_companies_org_lower_domain;")
