# Roadmap

← [README](../README.md)

This roadmap reflects current priorities. Items may shift based on community feedback.

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
- [ ] **Batch endpoint** — `POST /v1/anonymize/batch` for processing multiple documents in one call
- [ ] **Async job endpoint** — long documents via background task + webhook notification
- [ ] **Policy dry-run** — `POST /v1/anonymize?dry_run=true` returns detected entities without saving mappings
- [ ] **Entity allow-list** — whitelist specific values that should never be masked (e.g. company name in a contract)

---

## v0.4 — Integrations

- [ ] **LangChain document transformer** — `PiiProtectTransformer` wraps the anonymize endpoint for direct use in RAG pipelines
- [ ] **LlamaIndex node parser** — pre-processing step for index ingestion
- [ ] **OpenAI-compatible proxy mode** — intercept requests to `/v1/chat/completions`, anonymize before forwarding, de-anonymize response
- [ ] **Kafka consumer** — stream-based anonymization for event pipelines
- [ ] **S3 / GCS trigger** — anonymize on file upload, write output to separate bucket

---

## v0.5 — Enterprise features

- [ ] **Multi-tenancy** — namespace all data by tenant ID; per-tenant policy + model configuration
- [ ] **RBAC expansion** — custom roles with per-endpoint permissions
- [ ] **SSO / OIDC** — admin UI login via external identity provider
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
