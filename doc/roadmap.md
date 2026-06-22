# Roadmap

← [README](../README.md)

This roadmap reflects current priorities. Items may shift based on community feedback.

---

## v0.next — gRPC transport (pii-protect ↔ pii-cloud)

- [ ] **gRPC server** — expose a gRPC endpoint alongside the existing HTTP API on a separate port (default `50051`); proto definition in `proto/pii_protect.proto`
- [ ] **AnonymizationService** — `Anonymize`, `AnonymizeBatch`, `Detect`, `Ping` RPCs mirroring the existing REST endpoints
- [ ] **AdminConfigService** — `ListConfig`, `GetConfig`, `SetConfig`, `DeleteConfig` RPCs for scoped config CRUD
- [ ] **StatsService** — `GetStats` RPC
- [ ] **gRPC metadata auth** — read `x-api-key`, `x-pii-tenant-id`, `x-router-auth` from gRPC request metadata (mirrors HTTP headers)
- [ ] **pii-cloud GrpcTransport** — pii-cloud already has `GrpcTransport` + generated stub placeholder; activate once the engine exposes the gRPC port

---

## Architecture — Option B (open-core + cloud private module)

The engine follows an **open-core, self-hosted-first** model. Running with `MULTITENANCY_ENABLED=false` (the default) gives a fully isolated single-tenant deployment: no cloud dependency, no tenant headers, no shared state. The Plugin Manager foundation (shipped in v0.1) defines the extension boundary between core and optional modules.

The hosted cloud service is built as a private module that connects to the same engine via internal API keys and the `X-Pii-Tenant-Id` header — routing, billing, and tenant isolation live outside the open-core. This means self-hosted users get the full detection and policy engine without any cloud entanglement, while the cloud tier adds multitenancy, provisioning, and usage metering as a separate layer on top.

---

## v0.2 — Detection quality

- [ ] **Unit test suite for regex patterns** — precision/recall per type on a labelled Italian corpus (target: 500+ documents)
- [ ] **Benchmark pipeline** — automated evaluation script: `make benchmark` generates precision/recall/F1 table per PII type
- [ ] **PERSON recall improvements** — handle abbreviated names (M. Rossi), compound surnames, foreign names
- [ ] **ADDRESS precision** — structured address parser to reduce false positives
- [ ] **Regex pattern library** — additional European formats: DE tax ID, FR SIRET/SIREN, ES DNI/NIE, UK NI number, NL BSN
- [ ] **NER model selection** — configurable per context type (Presidio-only / ML-only / full cascade)

---

## v0.3 — Policy and workflow

- [ ] **Policy versioning** — track and diff policy changes over time; rollback support
- [ ] **Per-entity confidence threshold** — configurable minimum score per PII type
- [x] **Batch endpoint** — `POST /v1/anonymize/batch` for processing multiple documents in one call
- [ ] **Async job endpoint** — long documents via background task + webhook notification
- [x] **Policy dry-run** — `POST /v1/anonymize?dry_run=true` returns detected entities without saving mappings
- [ ] **Entity allow-list** — whitelist specific values that should never be masked (e.g. company name in a contract)

---

## v0.4 — Integrations

- [ ] **LangChain document transformer** — `PiiProtectTransformer` wraps the anonymize endpoint for direct use in RAG pipelines
- [ ] **LlamaIndex node parser** — pre-processing step for index ingestion
- [ ] **OpenAI-compatible proxy mode** — intercept requests to `/v1/chat/completions`, anonymize before forwarding, de-anonymize response
- [ ] **Kafka consumer** — stream-based anonymization for event pipelines
- [ ] **S3 / GCS trigger** — anonymize on file upload, write output to separate bucket

---

## v0.5 — Plugin ecosystem

- [x] **Plugin foundation** — base plugin contract, in-memory registry, and admin listing endpoint
- [ ] **Plugin manifest** — stable `plugin.json` schema with name, version, compatibility, permissions, and entrypoints
- [ ] **Filesystem plugin loader** — discover and load plugins from a local `plugins/` directory
- [ ] **Plugin lifecycle controls** — enable, disable, configure, and inspect plugins from the self-hosted admin UI
- [ ] **Plugin package installer** — install local packages with checksum validation and safe extraction
- [ ] **Signed package verification** — verify marketplace or private packages before installation
- [ ] **Plugin SDK and template** — documented extension points, sample plugin, and compatibility tests
- [ ] **Marketplace client** — browse a remote catalog and download free or entitled plugins into self-hosted deployments

Commercial marketplace operations remain outside the core: accounts, payments, entitlements, publisher console, review workflow, package hosting, and revenue share belong to a separate remote marketplace service.

---

## v0.6 — Enterprise features

- [ ] **Multi-tenancy** — namespace all data by tenant ID; per-tenant policy + model configuration
- [ ] **RBAC expansion** — custom roles with per-endpoint permissions
- [ ] **SSO / OIDC** — admin UI login via external identity provider
- [ ] **Per-tenant mapping encryption** — ogni tenant ha la propria chiave di cifratura per `pii_mappings.original_encrypted`; tre approcci valutati: (1) DEK/KEK simmetrico con secret manager (standard AWS/GCP), (2) asimmetrico zero-knowledge con chiave privata solo client-side, (3) ibrido con keypair per tenant + copia chiave privata inviata via email al cliente per backup personale. Approccio da scegliere prima dell'implementazione.
- [ ] **Mapping encryption key rotation** — re-encrypt existing mappings without data loss
- [ ] **GDPR right-to-erasure endpoint** — delete all mappings for a given data subject
- [ ] **Data residency controls** — configurable model cache and DB region

---

## Backlog (unscheduled)

- PDF/DOCX input support (with embedded text extraction)
- Browser extension for real-time PII redaction in web forms
- On-device mode (SQLite + smaller models) for air-gapped environments
- Differential privacy noise on numeric aggregates (salaries, ages)
- Active learning loop: flag uncertain entities for human review

---

## How to contribute

Open an issue or discussion on GitHub. PRs welcome — especially for non-Italian regex pattern libraries and language-specific test corpora.
