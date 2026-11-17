"""add_full_name_to_users

Revision ID: 1a2b3c4d5e6f
Revises: f6a7b8c9d0e1
Create Date: 2026-11-17 11:00:00.000000

Adds an optional `full_name` column to the `users` table so the self-service
signup flow can collect and store the registering user's full name. The column
is nullable so existing rows are unaffected (no backfill is required).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('full_name', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'full_name')
