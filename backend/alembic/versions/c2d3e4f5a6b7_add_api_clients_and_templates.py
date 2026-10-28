"""add api_clients and templates

Revision ID: c2d3e4f5a6b7
Revises: 9b1a2c3d4e5f
Create Date: 2026-10-28 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = '9b1a2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_clients',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=12), nullable=False),
        sa.Column('rate_limit_per_minute', sa.Integer(), server_default='60', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_api_clients_key_hash', 'api_clients', ['key_hash'], unique=True)

    op.create_table(
        'templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('subject_template', sa.String(length=255), nullable=True),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['api_clients.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_templates_client_id', 'templates', ['client_id'], unique=False)

    op.add_column('notifications', sa.Column('client_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_notifications_client_id_api_clients', 'notifications', 'api_clients', ['client_id'], ['id'])
    op.create_index('ix_notifications_client_id', 'notifications', ['client_id'], unique=False)

    op.add_column('notifications', sa.Column('template_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_notifications_template_id_templates', 'notifications', 'templates', ['template_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_notifications_template_id_templates', 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'template_id')
    op.drop_index('ix_notifications_client_id', table_name='notifications')
    op.drop_constraint('fk_notifications_client_id_api_clients', 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'client_id')
    op.drop_index('ix_templates_client_id', table_name='templates')
    op.drop_table('templates')
    op.drop_index('ix_api_clients_key_hash', table_name='api_clients')
    op.drop_table('api_clients')

