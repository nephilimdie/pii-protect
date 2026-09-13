# Restore drill

The drill validates that an encrypted PostgreSQL backup can be restored without
touching production. It must run against an isolated disposable database or a
staging clone with the same schema version.

```bash
RESTORE_DRILL=1 PII_ENVIRONMENT=staging \
  BACKUP_FILE=/var/backups/pii-engine/engine-db-latest.dump.gz \
  PII_DB_HOST=127.0.0.1 PII_DB_PORT=5432 PII_DB_NAME=pii_restore_drill \
  PII_DB_USER=pii_protect PII_DB_PASSWORD='staging-secret' \
  ./scripts/restore-drill.sh
```

Run monthly and after every backup format or migration change. Record date,
backup checksum, restore duration, schema revision, row-count smoke checks and
the operator in the operations log. Never provide a production environment
value to the command. The script intentionally requires both an explicit
`RESTORE_DRILL=1` flag and a non-production environment.
