"""Widen vpn_keys.email to TEXT for encrypted (Fernet) storage.

VLESS links are already TEXT, so only the email column needs a type
change to hold base64 ciphertext. Existing plaintext values are preserved
and are transparently re-encrypted on the next write (see bot/utils/crypto.py).

PostgreSQL-only; on SQLite this is a no-op (dynamic typing).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_encrypt_sensitive_fields"
down_revision = "0006_fk_ondelete_cascades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.alter_column(
        "vpn_keys",
        "email",
        type_=sa.Text(),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.alter_column(
        "vpn_keys",
        "email",
        type_=sa.String(length=255),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
