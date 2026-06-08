# pii-protect

Standalone PII pseudonymization microservice for Italian personal data. Detects and anonymizes personal information through a configurable multi-layer detection pipeline, with support for realistic surrogates and per-domain policies.

---

## Documentation

| Document | Contents |
|----------|----------|
| [Architecture & Development](doc/development.md) | Tech stack, project structure, adding layers, local dev |
| [Detection Layers](doc/detection-layers.md) | The 4 ML/regex layers, priorities, regex patterns, denylist, context words |
| [Anonymization Modes](doc/anonymization-modes.md) | Tag vs surrogate, coherent profiles, Codice Fiscale, reversibility |
| [Policy System](doc/policy-system.md) | Context types, domain policies, PII type registry, reclassification rules |
| [API Reference](doc/api-reference.md) | All REST endpoints with curl examples |

---

## Features

| Feature | Description |
|---------|-------------|
| **Multi-layer detection** | 4-layer cascade: Presidio+spaCy, openai/privacy-filter, AI4Privacy, DB Regex. Regex always wins on overlaps. |
| **Tag mode** | Replaces PII with opaque tokens `[PERSON_1]`. Reversible via `/v1/deanonymize`. |
| **Surrogate mode** | Replaces PII with realistic fake values (name, CF, IBAN, plate). Deterministic: same input → same output. |
| **Coherent profiles** | PERSON and FISCAL_CODE share a fake profile per `context_id`: the fake CF encodes the same name/date/city as the fake person. |
| **Context types** | A single `context_type` field in the API call automatically configures policy and mode. |
| **Domain policies** | Per domain (fine_appeal, contract, medical…) defines which PII types to protect, leave visible, or replace with Faker. |
| **PII Type Registry** | ~33 PII types categorized (IDENTITY, CONTACT, FINANCIAL, LEGAL, VEHICLE, NETWORK, CREDENTIAL) with default action and Faker strategy. |
| **Reclassification rules** | Post-detection rules that change an entity's type based on context (e.g. PERSON containing `@` → ACCOUNT). Visualized as a bipartite graph. |
| **Configurable regex** | Regex patterns stored in DB, hot-reloaded on change. Manageable from the admin UI without restart. |
| **Denylist** | Word/phrase lists to exclude from detection (recurring false positives). |
| **Audit log** | Every API call is logged: action type, entity count, context type, key used. |
| **API key management** | Roles: `admin`, `service`, `auditor`. Keys with optional expiry. |
| **Multi-language** | spaCy supports IT, EN, DE, FR, ES, PT. Models installable from the admin UI. |
| **Admin UI** | React + Tailwind. Full management of all components without touching code. |

---

## Installation

### Prerequisites

- Docker + Docker Compose
- `make` (pre-installed on macOS/Linux)

### Quick start

```bash
make setup   # creates .env from .env.example
# → edit .env: set PII_ENCRYPTION_KEY and PII_ADMIN_INITIAL_KEY
make start   # build images + start services + run migrations
```

Generate the Fernet encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

| Service | Default URL |
|---------|-------------|
| REST API | http://localhost:15500 |
| API Docs (Swagger) | http://localhost:15500/docs |
| Admin UI | http://localhost:15501 |
| PostgreSQL | localhost:15433 |

On first boot the API creates an admin key from `PII_ADMIN_INITIAL_KEY`. Open http://localhost:15501 and enter it.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PII_ENCRYPTION_KEY` | — | **Required.** Fernet key for encrypting PII mappings |
| `PII_ADMIN_INITIAL_KEY` | — | **Required.** Initial admin API key |
| `PII_DB_PASSWORD` | — | PostgreSQL password |
| `PII_DB_NAME` | `pii_protect` | Database name |
| `PII_DB_PORT` | `15433` | PostgreSQL host port |
| `PII_API_PORT` | `15500` | API host port |
| `PII_UI_PORT` | `15501` | Admin UI host port |
| `PII_MAPPING_TTL_DAYS` | `30` | Days before mappings expire |

---

## Screenshots

### Dashboard
![Dashboard](doc/img/dashboard.png)

### Regex Patterns
![Regex Patterns](doc/img/regex_patterns.png)

### Reclassification Rules
![Reclassification Rules](doc/img/reclassification_rules.png)

### PII Type Registry
![PII Type Registry](doc/img/pii_types_registry.png)

### Context Types — inline policy editor
![Context Types](doc/img/context_types_policy_editor.png)

### API Keys
![API Keys](doc/img/api_keys.png)

### Languages
![Languages](doc/img/languages.png)

### Stats
![Stats](doc/img/stats.png)

---

## License

MIT — see [LICENSE](./LICENSE).  
Copyright © 2026 Stefano Bassetto.
