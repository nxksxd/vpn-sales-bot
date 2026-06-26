#!/usr/bin/env python3
"""Migrate data from legacy SQLite database to PostgreSQL.

Usage:
    python3 scripts/migrate_sqlite_to_postgres.py /path/to/legacy.db

The target PostgreSQL database is taken from DATABASE_URL.
Expected flow:
1. Start PostgreSQL.
2. Run `alembic upgrade head`.
3. Run this script with the path to the old SQLite DB.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from bot.config import settings  # noqa: E402

TABLES = [
    "users",
    "subscriptions",
    "transactions",
    "vpn_keys",
    "notifications",
]


def read_sqlite_rows(db_path: Path, table: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def insert_rows(pg_engine, table: str, rows: list[dict]) -> None:
    if not rows:
        return

    columns = list(rows[0].keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    column_list = ", ".join(columns)
    sql = text(f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})")

    with pg_engine.begin() as conn:
        conn.execute(sql, rows)


def reset_sequences(pg_engine) -> None:
    statements = [
        "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM users",
        "SELECT setval(pg_get_serial_sequence('subscriptions', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM subscriptions",
        "SELECT setval(pg_get_serial_sequence('transactions', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM transactions",
        "SELECT setval(pg_get_serial_sequence('vpn_keys', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM vpn_keys",
        "SELECT setval(pg_get_serial_sequence('notifications', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM notifications",
    ]
    with pg_engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def ensure_empty_target(pg_engine) -> None:
    with pg_engine.begin() as conn:
        for table in TABLES:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            if count:
                raise RuntimeError(
                    f"Target PostgreSQL table '{table}' is not empty ({count} rows). "
                    "Use an empty database for migration."
                )


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/migrate_sqlite_to_postgres.py /path/to/legacy.db")
        return 1

    sqlite_path = Path(sys.argv[1]).expanduser().resolve()
    if not sqlite_path.exists():
        print(f"SQLite database not found: {sqlite_path}")
        return 1

    if not settings.database_url.startswith("postgresql+"):
        print("DATABASE_URL must point to PostgreSQL before running this migration.")
        return 1

    pg_engine = create_engine(settings.database_url.replace("+asyncpg", ""))

    ensure_empty_target(pg_engine)

    for table in TABLES:
        rows = read_sqlite_rows(sqlite_path, table)
        insert_rows(pg_engine, table, rows)
        print(f"Migrated {len(rows)} rows into {table}")

    reset_sequences(pg_engine)
    print("Migration completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
