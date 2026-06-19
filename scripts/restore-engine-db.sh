#!/usr/bin/env bash
# Restore pii-protect engine PostgreSQL database from a backup produced by backup-engine-db.sh.
# Usage: BACKUP_FILE=/path/engine-db-YYYYMMDDTHHMMSSZ.dump.gz ./scripts/restore-engine-db.sh

set -euo pipefail

BACKUP_FILE="${BACKUP_FILE:?Set BACKUP_FILE to a .dump.gz backup}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Backup file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

: "${PII_DB_HOST:=127.0.0.1}"
: "${PII_DB_PORT:=5432}"
: "${PII_DB_NAME:?Set PII_DB_NAME}"
: "${PII_DB_USER:?Set PII_DB_USER}"
: "${PII_DB_PASSWORD:?Set PII_DB_PASSWORD}"

echo "[$(date -u +%FT%TZ)] Restoring ${BACKUP_FILE} into ${PII_DB_NAME} on ${PII_DB_HOST}:${PII_DB_PORT}"

gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${PII_DB_PASSWORD}" pg_restore \
    --host="${PII_DB_HOST}" \
    --port="${PII_DB_PORT}" \
    --username="${PII_DB_USER}" \
    --dbname="${PII_DB_NAME}" \
    --no-owner \
    --role="${PII_DB_USER}"

echo "[$(date -u +%FT%TZ)] Restore completed"
