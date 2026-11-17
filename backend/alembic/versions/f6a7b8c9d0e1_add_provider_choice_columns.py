"""add_provider_choice_columns

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspaces',
        sa.Column('preferred_email_provider', sa.String(length=20), nullable=True)
    )
    op.add_column(
        'notifications',
        sa.Column('requested_provider', sa.String(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('notifications', 'requested_provider')
    op.drop_column('workspaces', 'preferred_email_provider')
