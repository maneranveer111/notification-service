"""add missing indexes

Revision ID: 9b1a2c3d4e5f
Revises: 8f1e2d3c4b5a
Create Date: 2026-10-28 13:17:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1a2c3d4e5f'
down_revision: Union[str, None] = '8f1e2d3c4b5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_status_created ON notifications (status, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_recipient ON notifications (recipient)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_provider_message_id ON notifications (provider_message_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_status_updated_at ON notifications (status, updated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_delivery_events_notification_id ON delivery_events (notification_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_delivery_events_notification_id")
    op.execute("DROP INDEX IF EXISTS ix_notifications_status_updated_at")
    op.execute("DROP INDEX IF EXISTS ix_notifications_created_at")
    op.execute("DROP INDEX IF EXISTS ix_notifications_provider_message_id")
    op.execute("DROP INDEX IF EXISTS ix_notifications_recipient")
    op.execute("DROP INDEX IF EXISTS ix_notifications_status_created")

