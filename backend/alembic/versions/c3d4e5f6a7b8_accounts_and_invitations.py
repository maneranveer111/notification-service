"""accounts_and_invitations

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-01 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add email_verified_at and password_changed_at to users
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Backfill email_verified_at = now() for all existing users
    op.execute("UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL")

    # 3. Create invitations table
    op.create_table(
        'invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_invitations_workspace_id', 'invitations', ['workspace_id'])

    # 4. Partial unique index on (workspace_id, email) WHERE status = 'pending'
    op.execute(
        "CREATE UNIQUE INDEX uq_invitations_workspace_email_pending "
        "ON invitations (workspace_id, email) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_invitations_workspace_email_pending")
    op.drop_index('ix_invitations_workspace_id', table_name='invitations')
    op.drop_table('invitations')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'email_verified_at')

