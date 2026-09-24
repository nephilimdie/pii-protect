#!/usr/bin/env bash
# Restore a backup into an explicitly non-production database and run a smoke query.
set -euo pipefail

if [[ "${RESTORE_DRILL:-}" != "1" ]]; then
    echo "Refusing restore drill: set RESTORE_DRILL=1 explicitly." >&2
    exit 1
fi
if [[ "${PII_ENVIRONMENT:-}" == "production" ]]; then
    echo "Refusing restore drill against production." >&2
    exit 1
fi
if [[ "${APP_ENV:-}" == "production" ]]; then
    echo "Refusing restore drill against production APP_ENV." >&2
    exit 1
fi
: "${BACKUP_FILE:?Set BACKUP_FILE to a .dump.gz backup}"
: "${PII_DB_NAME:?Set PII_DB_NAME}"
: "${PII_DB_USER:?Set PII_DB_USER}"
: "${PII_DB_PASSWORD:?Set PII_DB_PASSWORD}"

[[ -f "$BACKUP_FILE" ]] || { echo "Backup not found: $BACKUP_FILE" >&2; exit 1; }
if [[ "$PII_DB_NAME" != *restore* && "$PII_DB_NAME" != *drill* ]]; then
    echo "Refusing restore drill: target PII_DB_NAME must contain 'restore' or 'drill'." >&2
    exit 1
fi
started_at=$(date +%s)
checksum=$(sha256sum "$BACKUP_FILE" | awk '{print $1}')
echo "backup_sha256=${checksum}"
echo "Restoring $BACKUP_FILE into non-production database $PII_DB_NAME"
gunzip -c "$BACKUP_FILE" | PGPASSWORD="$PII_DB_PASSWORD" pg_restore \
    --host="${PII_DB_HOST:-127.0.0.1}" --port="${PII_DB_PORT:-5432}" \
    --username="$PII_DB_USER" --dbname="$PII_DB_NAME" --clean --if-exists --no-owner
PGPASSWORD="$PII_DB_PASSWORD" psql \
    --host="${PII_DB_HOST:-127.0.0.1}" --port="${PII_DB_PORT:-5432}" \
    --username="$PII_DB_USER" --dbname="$PII_DB_NAME" -v ON_ERROR_STOP=1 \
    -c 'SELECT 1 AS restore_drill_ok;'
finished_at=$(date +%s)
echo "restore_duration_seconds=$((finished_at - started_at))"
echo "Restore drill completed successfully"
