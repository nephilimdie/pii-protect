#!/bin/sh
set -eu

mkdir -p /backups

while true; do
  timestamp="$(date +%Y%m%d-%H%M%S)"
  pg_dump -h postgres -U "$PII_DB_USER" "$PII_DB_NAME" > "/backups/${timestamp}.sql"
  find /backups -type f -mtime +7 -delete
  sleep 86400
done