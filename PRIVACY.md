# Privacy Policy

This project is intended to help you process text while reducing exposure of personal data.

## What the application stores

The application may store:
- encrypted mapping records needed for deanonymization
- audit events describing API usage
- payload-free usage events used for limits and reporting
- policy and configuration metadata

## What the application should not store

The application should not store raw request text in telemetry, audit, or usage tables unless your own deployment adds that behavior.

## Data minimization

- Use `dry_run` when you only need detection results.
- Disable raw entity values in responses unless they are truly needed.
- Prefer the smallest practical retention period for mappings and logs.

## Access control

- Admin endpoints must remain restricted.
- Service keys should be scoped to the minimum permissions required.
- De-anonymization should only be available to trusted workflows.

## User expectations

If you deploy this system for end users, you should document:
- what categories of personal data are processed
- how long encrypted mappings and logs are retained
- who can access anonymization and deanonymization capabilities
- whether outputs are deterministic or reversible