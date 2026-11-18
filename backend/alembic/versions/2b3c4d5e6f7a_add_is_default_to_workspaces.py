"""add_is_default_to_workspaces

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-18 10:00:00.000000

Adds is_default boolean column to workspaces table (NOT NULL, server_default false)
and backfills is_default = true where slug = 'default'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspaces',
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.execute("UPDATE workspaces SET is_default = true WHERE slug = 'default'")


def downgrade() -> None:
    op.drop_column('workspaces', 'is_default')
