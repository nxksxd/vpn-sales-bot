"""Normalize transactions and add idempotency metadata.

NOTE: All schema changes from this migration were merged into the initial
schema (0001_initial_schema.py). This migration is kept as a no-op so that
the alembic version history remains consistent for any environment that
may have been stamped with this revision id.
"""

from __future__ import annotations


revision = "0002_transaction_normalization"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: schema already created in 0001_initial_schema.
    pass


def downgrade() -> None:
    # No-op: corresponding objects are dropped by 0001 downgrade.
    pass
