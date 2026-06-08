# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

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
