"""add idempotency and delivery events

Revision ID: 8f1e2d3c4b5a
Revises: 7e6ad80d7ca6
Create Date: 2026-10-28 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8f1e2d3c4b5a'
down_revision: Union[str, None] = '7e6ad80d7ca6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OWNERSHIP_MARKER = 'migration:8f1e2d3c4b5a'


def _is_table_owned(bind, table_name: str) -> bool:
    try:
        res = bind.execute(
            sa.text("SELECT obj_description(to_regclass(:table_name), 'pg_class')"),
            {"table_name": table_name},
        ).scalar()
        return res == OWNERSHIP_MARKER
    except Exception:
        return False


def _is_index_owned(bind, index_name: str) -> bool:
    try:
        res = bind.execute(
            sa.text("SELECT obj_description(to_regclass(:index_name), 'pg_class')"),
            {"index_name": index_name},
        ).scalar()
        return res == OWNERSHIP_MARKER
    except Exception:
        return False


def _is_column_owned(bind, table_name: str, column_name: str) -> bool:
    try:
        res = bind.execute(
            sa.text("""
                SELECT col_description(to_regclass(:table_name), attnum)
                FROM pg_attribute
                WHERE attrelid = to_regclass(:table_name)
                  AND attname = :column_name
                  AND NOT attisdropped
            """),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
        return res == OWNERSHIP_MARKER
    except Exception:
        return False


def _get_owned_fk(bind, table_name: str) -> str | None:
    try:
        res = bind.execute(
            sa.text("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = to_regclass(:table_name)
                  AND contype = 'f'
                  AND obj_description(oid, 'pg_constraint') = :marker
            """),
            {"table_name": table_name, "marker": OWNERSHIP_MARKER},
        ).scalar()
        return res
    except Exception:
        return None


def _has_exact_notification_fk(inspector) -> tuple[bool, str | None]:
    try:
        for fk in inspector.get_foreign_keys('delivery_events'):
            referred_table = fk.get('referred_table')
            constrained_cols = fk.get('constrained_columns') or []
            referred_cols = fk.get('referred_columns') or []
            if (
                referred_table == 'notifications'
                and constrained_cols == ['notification_id']
                and referred_cols == ['id']
            ):
                return True, fk.get('name')
    except Exception:
        pass
    return False, None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. notifications.idempotency_key
    notif_cols = {col['name']: col for col in inspector.get_columns('notifications')} if inspector.has_table('notifications') else {}
    if 'idempotency_key' in notif_cols:
        col = notif_cols['idempotency_key']
        if not isinstance(col['type'], (sa.String, sa.VARCHAR)):
            raise ValueError(f"Incompatible type for existing column notifications.idempotency_key: {col['type']}")
        if getattr(col['type'], 'length', None) is not None and col['type'].length < 255:
            raise ValueError(f"Incompatible length for existing column notifications.idempotency_key: {col['type'].length} < 255")
    else:
        op.add_column('notifications', sa.Column('idempotency_key', sa.String(length=255), nullable=True))
        op.execute(f"COMMENT ON COLUMN notifications.idempotency_key IS '{OWNERSHIP_MARKER}'")

    # 2. ux_notifications_idempotency_key
    inspector = sa.inspect(bind)
    notif_indexes = {idx['name']: idx for idx in inspector.get_indexes('notifications')} if inspector.has_table('notifications') else {}
    if 'ux_notifications_idempotency_key' in notif_indexes:
        idx = notif_indexes['ux_notifications_idempotency_key']
        if not idx.get('unique') or idx.get('column_names') != ['idempotency_key']:
            raise ValueError(f"Incompatible definition for existing index ux_notifications_idempotency_key: {idx}")
    else:
        op.create_index('ux_notifications_idempotency_key', 'notifications', ['idempotency_key'], unique=True)
        op.execute(f"COMMENT ON INDEX ux_notifications_idempotency_key IS '{OWNERSHIP_MARKER}'")

    # 3. notifications.request_hash
    inspector = sa.inspect(bind)
    notif_cols = {col['name']: col for col in inspector.get_columns('notifications')} if inspector.has_table('notifications') else {}
    if 'request_hash' in notif_cols:
        col = notif_cols['request_hash']
        if not isinstance(col['type'], (sa.String, sa.VARCHAR)):
            raise ValueError(f"Incompatible type for existing column notifications.request_hash: {col['type']}")
        if getattr(col['type'], 'length', None) is not None and col['type'].length < 64:
            raise ValueError(f"Incompatible length for existing column notifications.request_hash: {col['type'].length} < 64")
    else:
        op.add_column('notifications', sa.Column('request_hash', sa.String(length=64), nullable=True))
        op.execute(f"COMMENT ON COLUMN notifications.request_hash IS '{OWNERSHIP_MARKER}'")

    # 4. notifications.delivered_at
    inspector = sa.inspect(bind)
    notif_cols = {col['name']: col for col in inspector.get_columns('notifications')} if inspector.has_table('notifications') else {}
    if 'delivered_at' in notif_cols:
        col = notif_cols['delivered_at']
        if not isinstance(col['type'], (sa.DateTime, postgresql.TIMESTAMP)):
            raise ValueError(f"Incompatible type for existing column notifications.delivered_at: {col['type']}")
    else:
        op.add_column('notifications', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
        op.execute(f"COMMENT ON COLUMN notifications.delivered_at IS '{OWNERSHIP_MARKER}'")

    # 5. delivery_events table
    inspector = sa.inspect(bind)
    has_delivery_events = inspector.has_table('delivery_events')
    if not has_delivery_events:
        op.create_table(
            'delivery_events',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('notification_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('provider', sa.String(length=50), nullable=False),
            sa.Column('event_type', sa.String(length=50), nullable=False),
            sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], name='fk_delivery_events_notification_id'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.execute(f"COMMENT ON TABLE delivery_events IS '{OWNERSHIP_MARKER}'")
        op.execute(f"COMMENT ON CONSTRAINT fk_delivery_events_notification_id ON delivery_events IS '{OWNERSHIP_MARKER}'")
        op.create_index('ix_delivery_events_notification_id', 'delivery_events', ['notification_id'], unique=False)
        op.execute(f"COMMENT ON INDEX ix_delivery_events_notification_id IS '{OWNERSHIP_MARKER}'")
    else:
        deliv_cols = {col['name'] for col in inspector.get_columns('delivery_events')}
        required_cols = {'id', 'notification_id', 'provider', 'event_type', 'payload', 'received_at'}
        if not required_cols.issubset(deliv_cols):
            raise ValueError(f"Incompatible delivery_events table: missing required columns {required_cols - deliv_cols}")

        # 6. FK constraint check on existing delivery_events table
        has_exact_fk, fk_name = _has_exact_notification_fk(inspector)
        if not has_exact_fk:
            for fk in inspector.get_foreign_keys('delivery_events'):
                if fk.get('constrained_columns') == ['notification_id']:
                    raise ValueError(f"Incompatible foreign key on delivery_events.notification_id: points to {fk}")
            op.create_foreign_key(
                'fk_delivery_events_notification_id',
                'delivery_events',
                'notifications',
                ['notification_id'],
                ['id'],
            )
            op.execute(f"COMMENT ON CONSTRAINT fk_delivery_events_notification_id ON delivery_events IS '{OWNERSHIP_MARKER}'")

        # 7. ix_delivery_events_notification_id on existing delivery_events table
        inspector = sa.inspect(bind)
        delivery_indexes = {idx['name']: idx for idx in inspector.get_indexes('delivery_events')}
        if 'ix_delivery_events_notification_id' in delivery_indexes:
            idx = delivery_indexes['ix_delivery_events_notification_id']
            if idx.get('column_names') != ['notification_id']:
                raise ValueError(f"Incompatible definition for existing index ix_delivery_events_notification_id: {idx}")
        else:
            op.create_index('ix_delivery_events_notification_id', 'delivery_events', ['notification_id'], unique=False)
            op.execute(f"COMMENT ON INDEX ix_delivery_events_notification_id IS '{OWNERSHIP_MARKER}'")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('delivery_events'):
        if _is_table_owned(bind, 'delivery_events'):
            # Safety check: if table was created by this migration but contains records,
            # abort the downgrade to protect against unintended data loss.
            row_count = bind.execute(sa.text("SELECT count(*) FROM delivery_events")).scalar()
            if row_count and row_count > 0:
                raise ValueError(
                    f"Aborting downgrade: delivery_events table contains {row_count} row(s). "
                    "Dropping it would delete delivery-event data. Please archive or clear "
                    "the records first if you intend to remove this table."
                )
            if _is_index_owned(bind, 'ix_delivery_events_notification_id'):
                op.drop_index('ix_delivery_events_notification_id', table_name='delivery_events')
            op.drop_table('delivery_events')
        else:
            # Table existed prior to this migration and is not owned by it.
            # Preserve the table and its records; only remove objects created by this migration.
            if _is_index_owned(bind, 'ix_delivery_events_notification_id'):
                op.drop_index('ix_delivery_events_notification_id', table_name='delivery_events')

            owned_fk = _get_owned_fk(bind, 'delivery_events')
            if owned_fk:
                op.drop_constraint(owned_fk, 'delivery_events', type_='foreignkey')

    # Refresh inspector after potential table drop
    inspector = sa.inspect(bind)
    if inspector.has_table('notifications'):
        # 4. notifications.delivered_at
        if _is_column_owned(bind, 'notifications', 'delivered_at'):
            op.drop_column('notifications', 'delivered_at')

        # 5. notifications.request_hash
        if _is_column_owned(bind, 'notifications', 'request_hash'):
            op.drop_column('notifications', 'request_hash')

        # 6. ux_notifications_idempotency_key
        if _is_index_owned(bind, 'ux_notifications_idempotency_key'):
            op.drop_index('ux_notifications_idempotency_key', table_name='notifications')

        # 7. notifications.idempotency_key
        if _is_column_owned(bind, 'notifications', 'idempotency_key'):
            op.drop_column('notifications', 'idempotency_key')
