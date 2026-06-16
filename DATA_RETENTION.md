# Data Retention

This document describes the intended retention posture for `pii-protect` deployments.

## Default retention model

- Encrypted mapping records should follow the configured mapping TTL.
- Audit records should be retained only as long as needed for operational and compliance purposes.
- Usage events should remain payload-free and should be retained for reporting and limits according to your policy.
- Policy metadata can be retained longer because it does not contain raw user text.

## Recommended retention guidance

- Mappings: short TTL, aligned to the reverse-anonymization window.
- Audit logs: medium TTL, aligned to incident review and compliance needs.
- Usage events: short to medium TTL, aligned to billing or quota reporting.
- Backups: protect them with the same controls as primary data and apply the same retention policy.

## Deletion and expiry

When a record expires, the deployment should remove or archive it according to your storage policy. If you rely on backups, ensure expired data is purged from backup sets on the same schedule or is otherwise cryptographically inaccessible.

## Operator note

If you need stricter guarantees, document the exact TTLs in your deployment runbook and keep them consistent with the application configuration.