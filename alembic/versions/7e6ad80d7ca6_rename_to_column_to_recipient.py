"""rename to column to recipient

Revision ID: 7e6ad80d7ca6
Revises: 761db6e67ddf
Create Date: 2026-05-06 09:34:40.489882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e6ad80d7ca6'
down_revision: Union[str, Sequence[str], None] = '761db6e67ddf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename column 'to' to 'recipient'"""
    op.execute('ALTER TABLE notifications RENAME COLUMN "to" TO recipient')

def downgrade() -> None:
    """Rename column 'recipient' back to 'to'"""
    op.execute('ALTER TABLE notifications RENAME COLUMN recipient TO "to"')
