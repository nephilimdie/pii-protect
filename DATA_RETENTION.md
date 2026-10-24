# Data Retention

This document describes the intended retention posture for `pii-protect` deployments.

## Default retention model

- Encrypted mapping records should follow the configured mapping TTL.
- Audit records should be retained only as long as needed for operational and compliance purposes.
- Usage events should remain payload-free and should be retained for reporting and limits according to your policy.
- Policy metadata can be retained longer because it does not contain raw user text.

## Document service (`/v1/documents/*`)

Document requests are zero-retention by design: uploads are parsed in memory
(never spooled to temporary files), no document content, filename, content hash
or pseudonymization mapping is written to the database or to logs, and the
pseudonymization mapping exists only in the response returned to the caller.
Only metadata is recorded (usage event and audit entry: sizes, entity counts
and types, policy id, duration).

## Recommended retention guidance

- Mappings: short TTL, aligned to the reverse-anonymization window.
- Audit logs: medium TTL, aligned to incident review and compliance needs.
- Usage events: short to medium TTL, aligned to billing or quota reporting.
- Backups: protect them with the same controls as primary data and apply the same retention policy.

## Deletion and expiry

When a record expires, the deployment should remove or archive it according to your storage policy. If you rely on backups, ensure expired data is purged from backup sets on the same schedule or is otherwise cryptographically inaccessible.

## Operator note

If you need stricter guarantees, document the exact TTLs in your deployment runbook and keep them consistent with the application configuration.