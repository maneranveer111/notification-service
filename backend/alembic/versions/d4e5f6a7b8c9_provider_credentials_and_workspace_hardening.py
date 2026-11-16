"""provider_credentials_and_workspace_hardening

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-02 10:14:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add use_platform_providers to workspaces
    op.add_column(
        'workspaces',
        sa.Column('use_platform_providers', sa.Boolean(), server_default='false', nullable=False)
    )
    # Set default workspace to use platform providers
    op.execute("UPDATE workspaces SET use_platform_providers = true WHERE slug = 'default'")

    # 2. Add webhook_token to workspaces
    op.add_column(
        'workspaces',
        sa.Column('webhook_token', sa.String(length=64), nullable=True)
    )

    # Populate distinct webhook_token for every existing workspace
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM workspaces")).fetchall()
    for row in rows:
        ws_id = row[0]
        token = secrets.token_urlsafe(32)
        conn.execute(
            sa.text("UPDATE workspaces SET webhook_token = :token WHERE id = :id"),
            {"token": token, "id": ws_id}
        )

    # Make webhook_token NOT NULL and create unique index
    op.alter_column('workspaces', 'webhook_token', nullable=False)
    op.create_index('ix_workspaces_webhook_token', 'workspaces', ['webhook_token'], unique=True)

    # 3. Create provider_credentials table
    op.create_table(
        'provider_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('config_encrypted', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('workspace_id', 'provider', name='uq_provider_credentials_workspace_provider'),
    )
    op.create_index('ix_provider_credentials_workspace_id', 'provider_credentials', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_provider_credentials_workspace_id', table_name='provider_credentials')
    op.drop_table('provider_credentials')
    op.drop_index('ix_workspaces_webhook_token', table_name='workspaces')
    op.drop_column('workspaces', 'webhook_token')
    op.drop_column('workspaces', 'use_platform_providers')

