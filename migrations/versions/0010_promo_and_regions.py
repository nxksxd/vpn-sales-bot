"""Add ``valid_until`` to promo_codes and seed default regions.

Promo codes can now have an optional expiry date (``valid_until``). When
set, the code is considered inactive after the timestamp passes.

Also seeds two default server regions if the table is empty:

* ``fi`` — Финляндия, inbound 1
* ``de`` — Германия, inbound 4

The seeding is idempotent — it only inserts rows for codes that do not
already exist in the table, so re-running the migration after manual
edits is safe.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0010_promo_and_regions"
down_revision = "0009_subscription_sub_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promo_codes",
        sa.Column("valid_until", sa.DateTime(), nullable=True),
    )

    bind = op.get_bind()
    regions_table = sa.table(
        "server_regions",
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("server_address", sa.String),
        sa.column("inbound_id", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )

    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT code FROM server_regions")).fetchall()
    }

    defaults = [
        {"code": "fi", "label": "🇫🇮 Финляндия", "server_address": "", "inbound_id": 1, "is_active": True},
        {"code": "de", "label": "🇩🇪 Германия", "server_address": "", "inbound_id": 4, "is_active": True},
    ]
    to_insert = [row for row in defaults if row["code"] not in existing]
    if to_insert:
        op.bulk_insert(regions_table, to_insert)


def downgrade() -> None:
    op.drop_column("promo_codes", "valid_until")
