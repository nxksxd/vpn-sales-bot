"""Add payment events table and expanded subscription statuses."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_payment_events_and_statuses"
down_revision = "0003_product_fields_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount_stars", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("charge_id", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charge_id"),
    )
    op.create_index(op.f("ix_payment_events_user_id"), "payment_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_events_user_id"), table_name="payment_events")
    op.drop_table("payment_events")
