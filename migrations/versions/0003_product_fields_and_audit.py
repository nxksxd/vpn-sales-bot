"""Add product fields and audit logs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_product_fields_and_audit"
down_revision = "0002_transaction_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_completed", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("trial_used", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("preferred_region", sa.String(length=50), nullable=True))
    op.execute("UPDATE users SET onboarding_completed = FALSE WHERE onboarding_completed IS NULL")
    op.execute("UPDATE users SET trial_used = FALSE WHERE trial_used IS NULL")
    op.alter_column("users", "onboarding_completed", nullable=False)
    op.alter_column("users", "trial_used", nullable=False)

    op.add_column("subscriptions", sa.Column("region_code", sa.String(length=50), nullable=True))
    op.add_column("subscriptions", sa.Column("promo_code", sa.String(length=50), nullable=True))
    op.add_column("subscriptions", sa.Column("is_trial", sa.Boolean(), nullable=True))
    op.execute("UPDATE subscriptions SET is_trial = FALSE WHERE is_trial IS NULL")
    op.alter_column("subscriptions", "is_trial", nullable=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_admin_telegram_id"), "audit_logs", ["admin_telegram_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_target_user_id"), "audit_logs", ["target_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_target_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_admin_telegram_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_column("subscriptions", "is_trial")
    op.drop_column("subscriptions", "promo_code")
    op.drop_column("subscriptions", "region_code")
    op.drop_column("users", "preferred_region")
    op.drop_column("users", "trial_used")
    op.drop_column("users", "onboarding_completed")
