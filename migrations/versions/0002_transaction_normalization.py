"""Normalize transactions and add idempotency metadata."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_transaction_normalization"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("amount_rub", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("amount_stars", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("rate_snapshot", sa.String(length=50), nullable=True))
    op.add_column("transactions", sa.Column("idempotency_key", sa.String(length=255), nullable=True))

    op.execute("UPDATE transactions SET amount_rub = amount WHERE amount_rub IS NULL")
    op.alter_column("transactions", "amount_rub", nullable=False)
    op.create_unique_constraint("uq_transactions_idempotency_key", "transactions", ["idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_transactions_idempotency_key", "transactions", type_="unique")
    op.drop_column("transactions", "idempotency_key")
    op.drop_column("transactions", "rate_snapshot")
    op.drop_column("transactions", "amount_stars")
    op.drop_column("transactions", "amount_rub")
