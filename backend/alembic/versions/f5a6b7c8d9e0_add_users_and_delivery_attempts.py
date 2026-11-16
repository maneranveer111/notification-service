"""add_users_and_delivery_attempts

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(10) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,
            CONSTRAINT uq_users_email UNIQUE (email)
        )
    """)
    op.execute("CREATE INDEX ix_users_email ON users (email)")

    # 2. Create delivery_attempts table
    op.execute("""
        CREATE TABLE delivery_attempts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            provider VARCHAR(50) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            duration_ms INTEGER NOT NULL,
            outcome VARCHAR(20) NOT NULL,
            error_message VARCHAR(500)
        )
    """)
    op.execute("CREATE INDEX ix_delivery_attempts_notification_id ON delivery_attempts (notification_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS delivery_attempts")
    op.execute("DROP TABLE IF EXISTS users")

