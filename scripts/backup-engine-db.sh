#!/usr/bin/env bash
# Backup pii-protect engine (PostgreSQL) database.
# Usage: ./scripts/backup-engine-db.sh
# Env vars required: PII_DB_HOST, PII_DB_PORT, PII_DB_USER, PII_DB_PASSWORD, PII_DB_NAME
# Optional: BACKUP_DIR (default: /var/backups/pii-engine), BACKUP_RETAIN_DAYS (default: 30)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/pii-engine}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-30}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
FILE="${BACKUP_DIR}/engine-db-${TIMESTAMP}.dump.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u +%FT%TZ)] Starting backup -> ${FILE}"

PGPASSWORD="${PII_DB_PASSWORD}" pg_dump \
    --host="${PII_DB_HOST:-127.0.0.1}" \
    --port="${PII_DB_PORT:-5432}" \
    --username="${PII_DB_USER}" \
    --format=custom \
    --compress=9 \
    "${PII_DB_NAME}" \
  | gzip -9 > "${FILE}"

echo "[$(date -u +%FT%TZ)] Backup written: $(du -sh "${FILE}" | cut -f1)"

find "${BACKUP_DIR}" -name "engine-db-*.dump.gz" -mtime "+${RETAIN_DAYS}" -delete
echo "[$(date -u +%FT%TZ)] Pruned backups older than ${RETAIN_DAYS} days"

# --- Restore instructions ---
# gunzip -c "${FILE}" | PGPASSWORD="${PII_DB_PASSWORD}" pg_restore \
#     --host="${PII_DB_HOST}" --port="${PII_DB_PORT}" --username="${PII_DB_USER}" \
#     --dbname="${PII_DB_NAME}" --no-owner --role="${PII_DB_USER}"
