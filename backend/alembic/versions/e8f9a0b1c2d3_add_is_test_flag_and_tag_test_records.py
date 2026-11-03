"""add is_test flag and tag test records in leads and contacts tables

Revision ID: e8f9a0b1c2d3
Revises: e7f8a9b0c1d3
Create Date: 2026-10-30 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'e7f8a9b0c1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Exact 42 verified QA/test lead UUIDs identified during the forensic audit
CONFIRMED_TEST_LEAD_IDS = [
    # 12 Black Mesa Research Leads (October 28)
    'aa3b2f11-5628-4f35-ae01-6d7e2367f2dc',
    'a2f48993-0860-4851-89d7-99f54f500191',
    '2cf33ae2-70ec-4dfc-a644-f8aa500e42cf',
    '5e7397b8-829e-45df-8e1f-8e88d670e643',
    'ccc153e6-0271-492a-b20c-4e591c10cd9d',
    '584024e2-36ad-4964-bab0-4edf85895276',
    '94e7fe42-84a0-4670-8d89-99e5a87507d7',
    'b63c790c-d2a5-4f1c-a77f-032bc72a5cf9',
    '45149536-3c42-49ac-b330-ffcb0eae25f2',
    'f2d16060-0d2a-469a-b026-66ded76d5cac',
    '6279a787-5ebf-4581-bd01-b79a488ad165',
    '7b0ef752-0aa2-419b-8ef4-0c8b27c8b03f',
    # 2 Philosopher E2E Edit Leads (October 28)
    '1df35e16-f5f1-429e-a0c0-10903c97de5c',
    '608394ab-c721-467c-b756-1758c71898b1',
    # 2 Manual Audit / CSV Ingestion Leads (October 28)
    '29ad25b3-4ea7-407a-ade0-e1b2aca7431b',
    '0f1d5a14-12b4-436b-8708-b04b82ef97ec',
    # 5 Demo CSV Import Leads (October 14)
    '370791ff-2ea3-4019-82ed-29e73b30f517',
    'efd92f08-551b-4c7e-8ad1-0529fca88fa8',
    '7496e1c9-80c7-4b77-9820-c2fecd622ca4',
    '98e21411-efb2-424b-822b-fb44c38d0ab4',
    '6b914f9b-bf45-4ef0-89f8-aa9e41a706d6',
    # 20 HubSpot Sandbox Synced Leads (October 9)
    '28fbca38-7b99-4749-af26-e6b3ba168a4b',
    '8eefd937-99b4-40dd-a8ae-7eac225fa4f8',
    '274fa87d-86d0-4257-8b0c-b914f7b0fce8',
    'd3f2b472-930b-4f3c-ab5d-dd080e066753',
    '6880a397-062c-4b96-9946-bc9bdbee44f3',
    'c899a6d2-c30b-410a-a776-449812e3817f',
    '370fbb43-f975-4fcd-b2c5-5d943dc86d95',
    '786cb1b8-6ecf-46b2-91f8-b81d9d298194',
    '5e6b6fe6-5958-4429-ac38-e126fb062890',
    '3fae7af3-5806-4ffb-b558-ae45b19478d4',
    '646b831a-438d-4855-a934-e42ac295623e',
    '112835b5-d82c-4802-b8e2-792c4e94916d',
    'fa710c82-8a8b-46e7-a4c4-7a49ca90e74e',
    '971348dd-8f2d-48b0-ae6c-288a78fd7895',
    '8161eafe-9b6f-4393-867b-d82f25b62cc8',
    'f89801f3-a7b9-47d2-845c-82c1ea5d55d0',
    '80b8455a-fd33-400f-a1ca-dfc633ce345d',
    '834a0352-edfb-430c-914a-557e766181f9',
    '9d6d82b8-1522-40be-961b-2de477f41831',
    '5c7f140d-4836-48df-9669-98ece2bada4b',
    # 1 Retell Voice Mock Lead (October 8)
    'be5bafe0-e705-449a-813a-52f3ef3edf41'
]


def upgrade() -> None:
    """Add is_test columns to leads and contacts, and classify the 42 test records."""
    # 1. Add is_test column to leads with server_default=false (safe production default)
    op.add_column(
        'leads',
        sa.Column('is_test', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.create_index('ix_leads_is_test', 'leads', ['is_test'], unique=False)

    # 2. Add is_test column to contacts with server_default=false
    op.add_column(
        'contacts',
        sa.Column('is_test', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.create_index('ix_contacts_is_test', 'contacts', ['is_test'], unique=False)

    # 3. Classify the exact 42 verified test leads
    formatted_lead_ids = ", ".join(f"'{lid}'" for lid in CONFIRMED_TEST_LEAD_IDS)
    op.execute(
        f"UPDATE leads SET is_test = true WHERE id IN ({formatted_lead_ids})"
    )

    # 4. Classify linked contacts of confirmed test leads and Poplar QA test contact
    op.execute(
        "UPDATE contacts SET is_test = true WHERE id IN ("
        "  SELECT contact_id FROM leads WHERE is_test = true AND contact_id IS NOT NULL"
        ") OR email = 'poplar.qa.test@agiletesting.local'"
    )


def downgrade() -> None:
    """Drop is_test columns and indexes from contacts and leads tables."""
    op.drop_index('ix_contacts_is_test', table_name='contacts')
    op.drop_column('contacts', 'is_test')
    op.drop_index('ix_leads_is_test', table_name='leads')
    op.drop_column('leads', 'is_test')
