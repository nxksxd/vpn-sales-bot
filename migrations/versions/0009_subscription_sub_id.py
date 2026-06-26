"""Add ``sub_id`` to subscriptions for 3x-ui subscription URLs.

Each VPN client in 3x-ui can have a ``subId`` field. When set, the panel
exposes a unified subscription URL (``/sub/<subId>``) that aggregates all
configs for that client. We store the value alongside the subscription so
the bot can show users a stable, copy-pasteable link instead of the raw
VLESS inline string.

The column is nullable so legacy rows (created before this migration)
remain valid; the bot falls back to ``vless_link`` for them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_subscription_sub_id"
down_revision = "0008_user_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("sub_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_subscriptions_sub_id",
        "subscriptions",
        ["sub_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_sub_id", table_name="subscriptions")
    op.drop_column("subscriptions", "sub_id")
