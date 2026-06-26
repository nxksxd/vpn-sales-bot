#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-vpn-bot-db}"
POSTGRES_DB="${POSTGRES_DB:-vpn_bot}"
POSTGRES_USER="${POSTGRES_USER:-vpn_bot}"

mkdir -p "$BACKUP_DIR"

OUTPUT_FILE="$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUTPUT_FILE"

echo "Backup created: $OUTPUT_FILE"
