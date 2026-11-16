"""add scheduling priority and bulk columns

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-28 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'notifications',
        sa.Column('priority', sa.String(length=10), server_default='normal', nullable=False),
    )
    op.add_column(
        'notifications',
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'notifications',
        sa.Column('batch_id', sa.UUID(), nullable=True),
    )
    op.create_index('ix_notifications_batch_id', 'notifications', ['batch_id'], unique=False)
    op.create_index(
        'ix_notifications_status_scheduled_at',
        'notifications',
        ['status', 'scheduled_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_notifications_status_scheduled_at', table_name='notifications')
    op.drop_index('ix_notifications_batch_id', table_name='notifications')
    op.drop_column('notifications', 'batch_id')
    op.drop_column('notifications', 'scheduled_at')
    op.drop_column('notifications', 'priority')

