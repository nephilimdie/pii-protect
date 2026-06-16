# Security Policy

`pii-protect` is designed to minimize raw PII exposure, but security still depends on correct deployment and key management.

## Reporting a vulnerability

Report security issues privately to the maintainers through the normal project contact channel used in your organization.

Include:
- a short description of the issue
- affected endpoint or component
- reproduction steps
- whether the issue exposes raw text, mappings, API keys, or audit data

## Security expectations

- Keep `PII_ENCRYPTION_KEY` secret and rotate it with care.
- Treat admin API keys as privileged credentials.
- Use TLS in production and terminate HTTPS at a trusted reverse proxy.
- Prefer fail-closed mode unless you have an explicit operational reason to do otherwise.
- Do not expose the admin UI or admin endpoints without authentication.

## Response handling

- The API should not log raw input text unless you explicitly add that behavior in your own deployment.
- Usage telemetry is intended to remain payload-free.
- Mappings are encrypted at rest, but they are still sensitive secrets and should be protected accordingly.

## Supported fixes

Security fixes should be deployed as soon as possible. If a change affects the threat model, update the related documentation in the same release.