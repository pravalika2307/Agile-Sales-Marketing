"""designate agile qa sandbox org

Revision ID: f0a1b2c3d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-11-02 20:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QA_SANDBOX_ORG_ID = 'c0aae7f1-95bb-485f-bb9b-e3ed95469912'


def upgrade() -> None:
    """Formally designate organization c0aae7f1 as official Agile QA Sandbox."""
    op.execute(
        f"UPDATE organizations "
        f"SET name = 'Agile QA Sandbox', slug = 'agile-qa-sandbox-org' "
        f"WHERE id = '{QA_SANDBOX_ORG_ID}'"
    )


def downgrade() -> None:
    """Revert organization designation to legacy E2E Testing Org."""
    op.execute(
        f"UPDATE organizations "
        f"SET name = 'E2E Testing Org', slug = 'e2e-testing-org' "
        f"WHERE id = '{QA_SANDBOX_ORG_ID}'"
    )
