# Production Deployment

`pii-protect` supports a self-hosted business-preview deployment behind a reverse proxy.

## Required environment

Set these variables before starting production:

- `PII_DB_NAME`
- `PII_DB_USER`
- `PII_DB_PASSWORD`
- `PII_ENCRYPTION_KEY`
- `PII_ADMIN_INITIAL_KEY`
- `PII_FAILURE_MODE=closed`
- `PII_BATCH_MAX_ITEMS=50`

## Recommended topology

Use [docker-compose.prod.yml](docker-compose.prod.yml) with:

- `reverse-proxy` for HTTPS termination
- `api` for the FastAPI service
- `ui` for the admin dashboard
- `postgres` as an internal-only database
- `redis` reserved for future queueing and caching needs
- `backup` for scheduled database dumps
- `monitoring` for basic runtime visibility

Do not expose PostgreSQL directly on a public port.

## Certificates

Mount TLS certificates under `docker/nginx/certs/`:

- `fullchain.pem`
- `privkey.pem`

## Safe defaults

- Keep `PII_FAILURE_MODE=closed`
- Do not enable raw entity values for non-admin keys
- Use short-lived, limited API keys for demos and pilots
- Keep `.env` out of the repository

## Deployment checklist

- Database volume is persisted
- Reverse proxy is the only public entry point
- Production secrets are injected from the environment
- Backups are scheduled externally or by a separate job
- Logs do not include raw PII payloads
- Health check endpoint is reachable through the proxy
