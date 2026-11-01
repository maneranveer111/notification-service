"""multi_tenancy_core

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-01 21:15:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create workspaces and memberships; add new users columns; add four workspace_id columns as nullable
    op.create_table(
        'workspaces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_workspaces_slug', 'workspaces', ['slug'], unique=True)

    op.create_table(
        'memberships',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column('users', sa.Column('is_superadmin', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('last_workspace_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.add_column('notifications', sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('templates', sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('api_clients', sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('suppressions', sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True))

    # 2. Insert one workspace: name 'Default Workspace', slug 'default'
    default_ws_id = uuid.uuid4()
    op.execute(
        sa.text("INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, 'Default Workspace', 'default', now())")
        .bindparams(id=default_ws_id)
    )

    # 3. Backfill: set workspace_id = that id on all existing rows of the four tables
    op.execute(sa.text("UPDATE notifications SET workspace_id = :ws_id WHERE workspace_id IS NULL").bindparams(ws_id=default_ws_id))
    op.execute(sa.text("UPDATE templates SET workspace_id = :ws_id WHERE workspace_id IS NULL").bindparams(ws_id=default_ws_id))
    op.execute(sa.text("UPDATE api_clients SET workspace_id = :ws_id WHERE workspace_id IS NULL").bindparams(ws_id=default_ws_id))
    op.execute(sa.text("UPDATE suppressions SET workspace_id = :ws_id WHERE workspace_id IS NULL").bindparams(ws_id=default_ws_id))

    # 4. Backfill memberships: every existing user becomes a member of default workspace
    op.execute(
        sa.text("INSERT INTO memberships (user_id, workspace_id, role, created_at) "
                "SELECT id, :ws_id, CASE WHEN role = 'admin' THEN 'owner' ELSE 'viewer' END, now() "
                "FROM users ON CONFLICT DO NOTHING").bindparams(ws_id=default_ws_id)
    )
    op.execute(sa.text("UPDATE users SET is_superadmin = true WHERE role = 'admin'"))
    op.execute(sa.text("UPDATE users SET last_workspace_id = :ws_id WHERE last_workspace_id IS NULL").bindparams(ws_id=default_ws_id))

    # 5. Alter the four workspace_id columns to NOT NULL; apply uniqueness and index changes
    op.alter_column('notifications', 'workspace_id', nullable=False)
    op.alter_column('templates', 'workspace_id', nullable=False)
    op.alter_column('api_clients', 'workspace_id', nullable=False)
    op.alter_column('suppressions', 'workspace_id', nullable=False)

    op.create_foreign_key('fk_notifications_workspace_id_workspaces', 'notifications', 'workspaces', ['workspace_id'], ['id'])
    op.create_foreign_key('fk_templates_workspace_id_workspaces', 'templates', 'workspaces', ['workspace_id'], ['id'])
    op.create_foreign_key('fk_api_clients_workspace_id_workspaces', 'api_clients', 'workspaces', ['workspace_id'], ['id'])
    op.create_foreign_key('fk_suppressions_workspace_id_workspaces', 'suppressions', 'workspaces', ['workspace_id'], ['id'])

    op.drop_constraint('uq_suppressions_channel_recipient', 'suppressions', type_='unique')
    op.create_unique_constraint('uq_suppressions_workspace_channel_recipient', 'suppressions', ['workspace_id', 'channel', 'recipient'])

    op.drop_constraint('api_clients_name_key', 'api_clients', type_='unique')
    op.create_unique_constraint('uq_api_clients_workspace_name', 'api_clients', ['workspace_id', 'name'])

    op.create_index('ix_notifications_workspace_status_created', 'notifications', ['workspace_id', 'status', 'created_at'], unique=False)
    op.create_index('ix_notifications_workspace_created', 'notifications', ['workspace_id', 'created_at'], unique=False)
    op.create_index('ix_templates_workspace_id', 'templates', ['workspace_id'], unique=False)
    op.create_index('ix_api_clients_workspace_id', 'api_clients', ['workspace_id'], unique=False)
    op.create_index('ix_memberships_workspace_id', 'memberships', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_memberships_workspace_id', table_name='memberships')
    op.drop_index('ix_api_clients_workspace_id', table_name='api_clients')
    op.drop_index('ix_templates_workspace_id', table_name='templates')
    op.drop_index('ix_notifications_workspace_created', table_name='notifications')
    op.drop_index('ix_notifications_workspace_status_created', table_name='notifications')

    op.drop_constraint('uq_api_clients_workspace_name', 'api_clients', type_='unique')
    op.create_unique_constraint('api_clients_name_key', 'api_clients', ['name'])

    op.drop_constraint('uq_suppressions_workspace_channel_recipient', 'suppressions', type_='unique')
    op.create_unique_constraint('uq_suppressions_channel_recipient', 'suppressions', ['channel', 'recipient'])

    op.drop_constraint('fk_suppressions_workspace_id_workspaces', 'suppressions', type_='foreignkey')
    op.drop_constraint('fk_api_clients_workspace_id_workspaces', 'api_clients', type_='foreignkey')
    op.drop_constraint('fk_templates_workspace_id_workspaces', 'templates', type_='foreignkey')
    op.drop_constraint('fk_notifications_workspace_id_workspaces', 'notifications', type_='foreignkey')

    op.drop_column('suppressions', 'workspace_id')
    op.drop_column('api_clients', 'workspace_id')
    op.drop_column('templates', 'workspace_id')
    op.drop_column('notifications', 'workspace_id')

    op.drop_column('users', 'last_workspace_id')
    op.drop_column('users', 'is_superadmin')

    op.drop_table('memberships')
    op.drop_index('ix_workspaces_slug', table_name='workspaces')
    op.drop_table('workspaces')

