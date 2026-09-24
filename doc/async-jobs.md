# Asynchronous anonymization jobs

Long documents can be submitted without keeping the client request open:

```http
POST /v1/anonymize/jobs
X-Api-Key: <service-key>
Content-Type: application/json

{"text":"...","context_id":"batch-42","context_type":"generic","mode":"tag"}
```

The API returns `202 Accepted` with `job_id`, `status` and `status_url`. Poll the
status URL with the same API key. Jobs are scoped to both API key and tenant;
another tenant or service key cannot read the result. Request and result payloads
are encrypted with `ENCRYPTION_KEY` at rest.

## Worker

The API only persists jobs. A separate worker must be supervised by the runtime:

```bash
python -m app.jobs.worker
```

With Docker Compose, the worker is opt-in and does not start with the normal
stack:

```bash
docker compose --profile async-jobs up --build -d worker
# or
make async-worker
```

Set `ASYNC_JOB_WORKER_API_URL` to the private API URL reachable by the worker.
The worker reuses the normal `/v1/anonymize` pipeline, so policy, detection
layers, mapping encryption, usage and fail-closed behavior remain identical to
synchronous requests. It claims rows with PostgreSQL `SKIP LOCKED`, retries
transient failures up to `ASYNC_JOB_MAX_ATTEMPTS`, and never logs the payload.

## Webhooks

Callbacks are disabled unless the hostname is explicitly listed:

```dotenv
ASYNC_JOB_WEBHOOK_HOSTS=hooks.example.com
```

Only HTTPS URLs whose exact hostname appears in that allow-list are accepted.
The callback includes the job id and anonymized result, plus
`X-Pseudora-Job-Id`; consumers must make delivery idempotent. Delivery failures
are logged and do not expose the original request.

Webhook delivery is best effort in this first implementation: the job result
is durable and remains available through the polling endpoint, while a failed
callback does not cause the anonymization to run twice. Use polling when the
consumer requires guaranteed receipt.
