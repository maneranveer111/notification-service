"""add_suppression_and_notification_category

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create suppressions table
    op.execute("""
        CREATE TABLE suppressions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            channel VARCHAR(20) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            reason VARCHAR(20) NOT NULL,
            source VARCHAR(30) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_suppressions_channel_recipient UNIQUE (channel, recipient)
        )
    """)

    # 2. Add category column to notifications
    op.execute("""
        ALTER TABLE notifications
        ADD COLUMN IF NOT EXISTS category VARCHAR(20) NOT NULL DEFAULT 'transactional'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS category")
    op.execute("DROP TABLE IF EXISTS suppressions")

