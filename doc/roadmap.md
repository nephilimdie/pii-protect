# Roadmap

← [README](../README.md)

This roadmap reflects current priorities. Items may shift based on community feedback.

For the detailed plan to evolve the engine into an AI Privacy Gateway, see [AI Privacy Gateway Roadmap](roadmap-ai-privacy-gateway.md).

---

## v0.next — gRPC transport (pii-protect ↔ pii-cloud)

- [x] **gRPC server** — optional endpoint alongside the existing HTTP API on separate port `50051`; contract in `proto/pii_protect.proto`
- [x] **AnonymizationService** — `Anonymize`, `AnonymizeBatch`, `Detect`, `Ping` bridge to the existing REST endpoints
- [x] **AdminConfigService** — `ListConfig`, `GetConfig`, `SetConfig`, `DeleteConfig` bridge to scoped config CRUD
- [x] **StatsService** — `GetStats` bridge to the existing stats endpoint
- [x] **gRPC metadata auth** — `x-api-key`, `x-pii-tenant-id`, `x-router-auth` are translated to the existing HTTP security boundary
- [x] **pii-cloud GrpcTransport** — Composer runtime and generated PHP stubs are versioned; transport remains opt-in via `PII_PROTECT_TRANSPORT=grpc`

---

## Architecture — Option B (open-core + cloud private module)

The engine follows an **open-core, self-hosted-first** model. Running with `MULTITENANCY_ENABLED=false` (the default) gives a fully isolated single-tenant deployment: no cloud dependency, no tenant headers, no shared state. The Plugin Manager foundation (shipped in v0.1) defines the extension boundary between core and optional modules.

The hosted cloud service is built as a private module that connects to the same engine via internal API keys and the `X-Pii-Tenant-Id` header — routing, billing, and tenant isolation live outside the open-core. This means self-hosted users get the full detection and policy engine without any cloud entanglement, while the cloud tier adds multitenancy, provisioning, and usage metering as a separate layer on top.

---

## v0.2 — Detection quality

- [x] **Unit test suite for regex patterns** — synthetic labelled corpus and detector tests are executed in CI; expand to 500+ authorized documents before a quality claim
- [x] **Benchmark pipeline** — `make benchmark` and `benchmark/run_synthetic.py` generate precision/recall/F1, per-type metrics and latency reports with explicit threshold gates
- [x] **PERSON recall improvements** — contextual deterministic matching handles abbreviated names (M. Rossi) and compound/foreign-style names without broad capitalized-word matching
- [x] **ADDRESS precision** — structured street patterns require a house number and support optional postcode/city, reducing street-name false positives
- [x] **Regex pattern library** — label-scoped DE tax ID, FR SIRET/SIREN, ES DNI/NIE, UK NI number and NL BSN patterns; expand with authorized corpus before quality claims
- [x] **NER model selection** — context types accept an optional `detection_layers` list; runtime intersects it with platform/tenant layer overrides

---

## v0.3 — Policy and workflow

- [x] **Policy versioning** — track and diff policy changes over time; rollback support via the domain-policy and context-type version endpoints
- [x] **Per-entity confidence threshold** — configurable minimum score per PII type in domain policies and scoped overrides
- [x] **Batch endpoint** — `POST /v1/anonymize/batch` for processing multiple documents in one call
- [x] **Async job endpoint** — durable encrypted jobs with tenant/API-key scope, supervised worker, retry policy and optional HTTPS webhook notification; opt-in Compose profile `async-jobs`
- [x] **Policy dry-run** — `POST /v1/anonymize?dry_run=true` returns detected entities without saving mappings
- [x] **Entity allow-list** — whitelist specific values per PII type in domain policies and scoped overrides

---

## v0.4 — Integrations

- [x] **LangChain document transformer** — `PseudoraLangChainTransformer` is shipped in the Python SDK and protects document text before ingestion
- [x] **LlamaIndex node parser** — `PseudoraLlamaIndexTransformer` is shipped in the Python SDK and protects node text before indexing
- [x] **OpenAI-compatible proxy mode** — implemented in the separate `pii-gateway` repository, including Chat Completions and Responses API
- [ ] **Kafka consumer** — stream-based anonymization for event pipelines
- [ ] **S3 / GCS trigger** — anonymize on file upload, write output to separate bucket

---

## v0.5 — Plugin ecosystem

- [x] **Plugin foundation** — base plugin contract, in-memory registry, and admin listing endpoint
- [x] **Plugin manifest** — validated `plugin.json` schema with name, version, compatibility, permissions, and entrypoint
- [x] **Filesystem plugin loader** — opt-in discovery and loading from a local `plugins/` directory
- [x] **Plugin lifecycle controls** — inspect and disable loaded plugins from the self-hosted admin API; enable is controlled by explicit autoload configuration
- [x] **Plugin package installer** — install local packages with required checksum validation and safe extraction
- [x] **Signed package verification** — optional Ed25519 verification is available before installation
- [x] **Plugin SDK and template** — documented extension points, sample plugin, and compatibility test
- [x] **Marketplace client** — browse a configured HTTPS catalog and download free or entitled plugins with checksum/signature verification; installation remains opt-in and does not autoload

Commercial marketplace operations remain outside the core: accounts, payments, entitlements, publisher console, review workflow, package hosting, and revenue share belong to a separate remote marketplace service.

---

## v0.6 — Enterprise features

- [x] **Multi-tenancy** — namespace mappings, audit, usage, policies and configuration by tenant ID
- [ ] **RBAC expansion** — custom roles with per-endpoint permissions
- [ ] **SSO / OIDC** — admin UI login via external identity provider
- [x] **Per-tenant mapping encryption** — DEK per tenant cifrato con KEK applicativo e risolto tramite `KeyProvider`
- [x] **Mapping encryption key rotation** — tenant-scoped admin endpoint re-encrypts existing mappings before replacing the DEK
- [x] **GDPR right-to-erasure endpoint** — tenant-scoped erasure endpoint deletes mappings and preserves a minimal audit event
- [x] **Data residency controls** — configurable model cache and enforced residency declaration; physical DB/backup region remains an infrastructure release gate

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
