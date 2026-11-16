"""set_null_on_delete_template_id

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-11-01 20:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('fk_notifications_template_id_templates', 'notifications', type_='foreignkey')
    op.create_foreign_key(
        'fk_notifications_template_id_templates',
        'notifications',
        'templates',
        ['template_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_notifications_template_id_templates', 'notifications', type_='foreignkey')
    op.create_foreign_key(
        'fk_notifications_template_id_templates',
        'notifications',
        'templates',
        ['template_id'],
        ['id'],
    )

