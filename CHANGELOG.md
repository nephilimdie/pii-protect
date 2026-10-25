# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- Zero-retention document service: `POST /v1/documents/preview`, `/redact`, `/pseudonymize` for PDF (redact only, rasterized black boxes, no text layer), DOCX (in-place, metadata/comments/tracked changes stripped) and TXT. In-memory only, always fail-closed, mapping returned to the client in a ZIP and never stored. Limits via `PII_DOCUMENT_UPLOAD_MAX_BYTES`, `PII_DOCUMENT_UPLOAD_MAX_PAGES`, `PII_DOCUMENT_TIMEOUT_SECONDS`, `PII_DOCUMENT_PDF_DPI`.

- Memory-bounded documents: PDFs are rendered and streamed one page at a time (adaptive DPI under a per-page pixel budget, `X-Pseudora-Pages` header, validate-everything-before-the-first-byte, aborted connection on mid-stream failure); long text is detected in overlapping windows merged into one global entity list; DOCX packages are inspected before parsing (parts, inflated size, ratio, nested archives, external references -> `422 DOCX_*`); per-worker admission control returns `503 ENGINE_BUSY` + `Retry-After` (`PII_DOCUMENT_MAX_CONCURRENT_JOBS` default 2; 4 recommended on the 12 CPU / 47 GB prod host). New env vars: `PII_DOCUMENT_PDF_MAX_PAGE_PIXELS`, `PII_DOCUMENT_PDF_MIN_DPI`, `PII_DOCUMENT_MAX_TEXT_CHARS`, `PII_DOCUMENT_DETECTION_WINDOW_CHARS`, `PII_DOCUMENT_DETECTION_WINDOW_OVERLAP`, `PII_DOCUMENT_MAX_CONCURRENT_JOBS`, `PII_DOCUMENT_BUSY_TIMEOUT_SECONDS`, `PII_DOCUMENT_MAX_RSS_MB`, `PII_DOCUMENT_DOCX_MAX_ENTRIES`, `PII_DOCUMENT_DOCX_MAX_UNCOMPRESSED_BYTES`, `PII_DOCUMENT_DOCX_MAX_RATIO`.

### Changed
- Documents over `PII_DOCUMENT_MAX_TEXT_CHARS` now fail fast with `422 DOCUMENT_TOO_LONG` (was `413 DOCUMENT_TEXT_TOO_LONG`) carrying `max_chars`, `chars` and `estimated_max_pages` (~2,200 chars per page), checked after extraction and before detection, so a 180-page PDF is refused in about a second instead of timing out after `PII_DOCUMENT_TIMEOUT_SECONDS`. Size the limit to detection throughput: prod detects ~1.1k chars/s, so 90000 fits a 100 s timeout.
- Batch multiline Privacy Filter inference to reduce ONNX overhead while preserving entity offsets and single-line fallback compatibility.

### Planned
- See [Roadmap](doc/roadmap.md)

---

## [0.1.0] — 2026-06-05

First public release.

### Added

**Detection pipeline**
- 4-layer parallel detection: Presidio + spaCy (`it_core_news_lg`), openai/privacy-filter (ONNX), AI4Privacy (distilbert), DB-configurable regex
- ~33 PII types across 7 categories (IDENTITY, CONTACT, FINANCIAL, LEGAL, VEHICLE, NETWORK, CREDENTIAL)
- Entity merger with priority-based overlap resolution (regex score = 1.0, always wins)
- Snap-to-word-boundary post-processing; honorific absorption for PERSON
- Denylist (exact / substring match) for recurring false positives
- Presidio context words for confidence boosting
- Reclassification rules (context_pattern + entity_pattern, bipartite graph UI)
- DATE → DATE_BORN reclassification when preceded by "nato/nata a \<City\> il"

**Anonymization modes**
- Tag mode: stable opaque tokens `[PERSON_1]` per `context_id`, fully reversible
- Surrogate mode: deterministic, format-preserving fake values (seed = SHA-256 of value + context_id)
- Coherent PERSON + FISCAL_CODE profiles: fake name and fake CF always refer to the same synthetic persona
- Italian Codice Fiscale encoder/decoder (`cf_codec.py`) with full check-character algorithm
- Per-type surrogate override (protect / keep / faker per PII type, regardless of context-level mode)

**Policy system**
- PII type registry with per-type `default_action` and `faker_strategy`
- Domain policies: `protect_types`, `keep_types`, `surrogate_types` (JSONB)
- Context types: single `context_type` field configures policy + mode automatically
- Policy resolution: inline request > domain policy > registry default
- Pre-loaded policies: `default`, `fine_appeal`, `contract_analysis`, `medical`, `embedding`
- Inline policy editor in the Context Types admin page

**Multi-language surrogates**
- `language` field in the request selects Faker locale (IT, EN, DE, FR, ES, PT, NL, PL, …)
- Added label-scoped European identifier patterns for German, French, Spanish,
  UK and Dutch documents.
- Locale-aware names, phone numbers, addresses, company suffixes
- Passport country code derived from locale

**Admin UI**
- React 18 + Vite + Tailwind CSS
- Grouped navbar with hover dropdowns (Detection, Policy, System)
- Pages: Dashboard, Regex Patterns, Denylist, Context Words, Reclassification Rules (bipartite graph), PII Types, Domain Policies, Context Types (inline editor), API Keys, Languages, Mappings, Audit Log, Stats

**API**
- `POST /v1/anonymize` with `language`, `mode`, `policy`, `detection_mode` fields
- `POST /v1/deanonymize`
- Full admin CRUD for all configuration entities
- API key management with roles (`admin`, `service`, `auditor`) and optional expiry
- OpenAPI 3.1 spec (`openapi.yaml`)

**Infrastructure**
- Docker Compose with PostgreSQL 17 + pgvector
- Alembic migrations (001–027), auto-run at container startup
- Fernet-encrypted PII mappings at rest
- Audit log for every anonymize/deanonymize call
- HuggingFace model cache volume (no re-download on restart)
- `make setup / start / stop / migrate / logs / test / clean`

[0.1.0]: https://github.com/nephilimdie/pii-protect/releases/tag/v0.1.0
