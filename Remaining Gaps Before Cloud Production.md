# pii-protect — Remaining Gaps Before Cloud Production

This document tracks what is still missing before `pii-protect` can be positioned as a public multi-tenant cloud service. Items that do not block a self-hosted or pilot deployment are marked accordingly.

> Last updated: 2026-06-16

---

## Status Summary

| Area | Status |
|---|---|
| API rate limiting (req/min, req/hour, req/day, chars/req, chars/month, expiry) | ✅ Implemented |
| Usage telemetry (chars_in/out, latency_ms, entity_count, error_code) | ✅ Implemented |
| `POST /anonymize/batch` | ✅ Implemented |
| `docker-compose.prod.yml` + `PRODUCTION.md` | ✅ Implemented |
| `make benchmark` | ✅ Implemented |
| Business-oriented messaging and docs | ✅ Implemented |
| Multi-tenancy | ❌ Not yet ready — blocks public SaaS |

---

## Remaining Gap: Multi-Tenancy

### Current State

`UsageEvent` has a `tenant_id` tag field, but there is no `Tenant` model. All API keys, policies, audit logs, and limits share a single namespace. The system is best suited for:

- single-organization self-hosted deployments
- dedicated-instance pilot customers

### Missing Capabilities

```text
Tenant model with isolation boundary
Tenant-scoped API keys
Tenant-scoped domain policies and context types
Tenant-scoped audit logs and usage events
Tenant-scoped rate limits
Tenant-scoped analytics
```

### Why It Matters

Without tenant isolation, running multiple customers on the same instance creates:

- data leakage risk between customers
- compliance complexity (GDPR data separation)
- inability to offer per-customer SLAs or billing

### Recommendation

Keep self-hosted and dedicated-instance as the primary deployment model until tenant support is complete. Do not offer shared-instance SaaS without this in place.

---

## Resolved Items (for reference)

These were listed as gaps in earlier versions of this document and have since been addressed:

- **Rate limiting**: `max_requests_per_minute`, `max_requests_per_hour`, `max_requests_per_day`, `max_chars_per_request`, `max_chars_per_month`, `expires_at` — all enforced with `HTTP 429` responses.
- **Usage telemetry**: `UsageEvent` captures `chars_in`, `chars_out`, `entities_count`, `entity_types_summary`, `latency_ms`, `status`, `error_code` without storing raw text or PII values.
- **Batch processing**: `POST /anonymize/batch` is a first-class endpoint, configurable via `PII_BATCH_MAX_ITEMS`.
- **Production deployment**: `docker-compose.prod.yml` includes reverse proxy, Postgres, Redis, backup, and monitoring. `PRODUCTION.md` covers secrets management and health checks.
- **Reproducible benchmarks**: `make benchmark` runs the benchmark suite and outputs results.
- **Business messaging**: `FEATURING-FOR-PROD.md`, `LICENSING.md`, `README.md`, and `SECURITY.md` lead with business outcomes.
