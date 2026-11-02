"""plans_and_quotas

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-02 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add plan to workspaces with server default 'free'
    op.add_column(
        'workspaces',
        sa.Column('plan', sa.String(length=20), server_default='free', nullable=False)
    )
    # Set 'unlimited' for the existing default workspace so deployed v1 behaves as before
    op.execute("UPDATE workspaces SET plan = 'unlimited' WHERE slug = 'default'")


def downgrade() -> None:
    op.drop_column('workspaces', 'plan')

