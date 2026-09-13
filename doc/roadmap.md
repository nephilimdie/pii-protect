# Roadmap

← [README](../README.md)

This roadmap reflects current priorities. Items may shift based on community feedback.

For the detailed plan to evolve the engine into an AI Privacy Gateway, see [AI Privacy Gateway Roadmap](roadmap-ai-privacy-gateway.md).

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

- [x] **Unit test suite for regex patterns** — synthetic labelled corpus and detector tests are executed in CI; expand to 500+ authorized documents before a quality claim
- [x] **Benchmark pipeline** — `make benchmark` and `benchmark/run_synthetic.py` generate precision/recall/F1 and latency reports
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
- [x] **OpenAI-compatible proxy mode** — implemented in the separate `pii-gateway` repository, including Chat Completions and Responses API
- [ ] **Kafka consumer** — stream-based anonymization for event pipelines
- [ ] **S3 / GCS trigger** — anonymize on file upload, write output to separate bucket

---

## v0.5 — Plugin ecosystem

- [x] **Plugin foundation** — base plugin contract, in-memory registry, and admin listing endpoint
- [x] **Plugin manifest** — validated `plugin.json` schema with name, version, compatibility, permissions, and entrypoint
- [x] **Filesystem plugin loader** — opt-in discovery and loading from a local `plugins/` directory
- [x] **Plugin lifecycle controls** — inspect and disable loaded plugins from the self-hosted admin API; enable is controlled by explicit autoload configuration
- [ ] **Plugin package installer** — install local packages with checksum validation and safe extraction
- [ ] **Signed package verification** — verify marketplace or private packages before installation
- [ ] **Plugin SDK and template** — documented extension points, sample plugin, and compatibility tests
- [ ] **Marketplace client** — browse a remote catalog and download free or entitled plugins into self-hosted deployments

Commercial marketplace operations remain outside the core: accounts, payments, entitlements, publisher console, review workflow, package hosting, and revenue share belong to a separate remote marketplace service.

---

## v0.6 — Enterprise features

- [x] **Multi-tenancy** — namespace mappings, audit, usage, policies and configuration by tenant ID
- [ ] **RBAC expansion** — custom roles with per-endpoint permissions
- [ ] **SSO / OIDC** — admin UI login via external identity provider
- [x] **Per-tenant mapping encryption** — DEK per tenant cifrato con KEK applicativo e risolto tramite `KeyProvider`
- [x] **Mapping encryption key rotation** — tenant-scoped admin endpoint re-encrypts existing mappings before replacing the DEK
- [x] **GDPR right-to-erasure endpoint** — tenant-scoped erasure endpoint deletes mappings and preserves a minimal audit event
- [ ] **Data residency controls** — configurable model cache and DB region

---

## Backlog (unscheduled)

- PDF/DOCX input support (with embedded text extraction)
- Browser extension for real-time PII redaction in web forms
- On-device mode (SQLite + smaller models) for air-gapped environments
- Differential privacy noise on numeric aggregates (salaries, ages)
- Active learning loop: flag uncertain entities for human review
- **Image PII redaction layer** — extend the detection pipeline to images (JPEG, PNG, PDF pages). The layer runs in two passes: (1) an OCR pass (e.g. Tesseract / EasyOCR) extracts text tokens with their bounding-box coordinates, feeds them through the existing text pipeline, and blacks out regions that contain PII; (2) a vision pass (e.g. face detector via OpenCV/MediaPipe or a YOLO variant) detects biometric data (faces, hands, signatures) and applies pixel-level redaction. The output is the original image with sensitive regions replaced by solid fills or blurred patches. API contract: `POST /v1/anonymize/image` accepts multipart or base64, returns the redacted image (same format) plus a JSON sidecar listing detected regions, types, and confidence scores — same shape as the text endpoint for pipeline consistency. The image layer is opt-in and ships as a plugin to keep core dependencies lean.

---

## How to contribute

Open an issue or discussion on GitHub. PRs welcome — especially for non-Italian regex pattern libraries and language-specific test corpora.
