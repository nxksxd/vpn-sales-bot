"""Add soft-delete column to users.

A non-null ``deleted_at`` marks the account as deleted while preserving
its rows (subscriptions/transactions) for financial history. Reads filter
it out by default; re-engagement revives the account.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_user_soft_delete"
down_revision = "0007_encrypt_sensitive_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
