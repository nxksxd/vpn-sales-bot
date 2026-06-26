"""Add ON DELETE cascades/set-null to foreign keys.

PostgreSQL-only: recreates the (originally unnamed) foreign keys with
explicit ON DELETE behaviour so deleting a user no longer leaves orphan
subscriptions/transactions/keys/payment events/notifications.

On SQLite this is a no-op (SQLite cannot ALTER a constraint in place;
fresh databases get the correct schema from the models via create_all).
"""

from __future__ import annotations

from alembic import op

revision = "0006_fk_ondelete_cascades"
down_revision = "0005_server_regions_and_promos"
branch_labels = None
depends_on = None


# (table, constraint_name, column, ref_table, ref_column, ondelete)
_U = "users"
_TID = "telegram_id"
_SUB = "subscriptions"
_FKS = [
    ("subscriptions", "subscriptions_user_id_fkey", "user_id", _U, _TID, "CASCADE"),
    ("transactions", "transactions_user_id_fkey", "user_id", _U, _TID, "CASCADE"),
    ("vpn_keys", "vpn_keys_subscription_id_fkey", "subscription_id", _SUB, "id", "CASCADE"),
    ("vpn_keys", "vpn_keys_user_id_fkey", "user_id", _U, _TID, "CASCADE"),
    ("payment_events", "payment_events_user_id_fkey", "user_id", _U, _TID, "CASCADE"),
    ("notifications", "notifications_user_id_fkey", "user_id", _U, _TID, "CASCADE"),
    ("notifications", "notifications_subscription_id_fkey",
     "subscription_id", _SUB, "id", "SET NULL"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, col, ref_table, ref_col, ondelete in _FKS:
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}')
        op.create_foreign_key(
            name, table, ref_table, [col], [ref_col], ondelete=ondelete
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, name, col, ref_table, ref_col, _ondelete in _FKS:
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}')
        op.create_foreign_key(name, table, ref_table, [col], [ref_col])
