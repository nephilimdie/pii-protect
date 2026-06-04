# pii-protect

Standalone PII pseudonymization microservice. Detects and anonymizes Italian personal data using a cascaded multi-layer detection pipeline. Designed as a sidecar for lavvocato but usable independently.

## Architecture

```
text input
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       DetectorRegistry                          │
│  sorted by priority, filtered by is_available()                 │
│                                                                 │
│  Layer 1: Presidio + spaCy it_core_news_lg    priority=10       │
│  Layer 2: openai/privacy-filter (ONNX)        priority=20       │
│  Layer 3: Isotonic/distilbert ai4privacy      priority=25       │
│  Layer 4: Regex patterns (from DB)            priority=30       │
│                                                                 │
│  EntityMerger: overlaps resolved by score; Regex (1.0) wins     │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
PiiAnonymizer  →  snap-to-word-boundary  →  encrypted mapping (PostgreSQL)
    │
    ▼
anonymized text + entity list + context_id
```

**Domain layout:**

```
api/app/
├── detection/          # PII detection (Strategy + Registry + Provider)
│   ├── contracts/      # DetectorContract ABC
│   ├── layers/         # One file per detection layer
│   ├── entities.py     # PiiEntity dataclass
│   ├── detector_registry.py
│   └── detector_provider.py   ← only file to touch when adding a new layer
├── anonymization/      # Pseudonymization logic + Fernet encryption
├── identity/           # API key auth, roles
├── audit/              # Audit log
└── reporting/          # Stats endpoint
```

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- `make` (pre-installed on macOS/Linux)
- Python 3.11+ (for local dev only)

### One-command startup

```bash
make setup   # creates .env from .env.example (skipped if .env already exists)
# → edit .env: set PII_ENCRYPTION_KEY and PII_ADMIN_INITIAL_KEY
make start   # build images + start services + run migrations
```

`Makefile` is at the project root: `/path/to/pii-protect/Makefile`.

Available commands:

```
make setup     copy .env.example → .env (skip if .env exists)
make start     build images + start all services + run migrations
make stop      stop all services
make restart   stop → start
make migrate   run Alembic migrations
make logs      tail API logs
make test      run pytest inside the API container
make clean     stop + remove volumes (destructive)
```

### Manual startup (without make)

**1. Configure**

```bash
cp .env.example .env
```

Generate the Fernet encryption key (required — the service will not start without it):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Edit `.env` and set at minimum:

```env
PII_ENCRYPTION_KEY=<generated Fernet key>
PII_ADMIN_INITIAL_KEY=<choose a strong admin key>
PII_DB_PASSWORD=<choose a strong DB password>
```

**2. Start services**

```bash
docker compose up --build -d
```

Services started:
| Service | Default URL |
|---------|-------------|
| REST API | http://localhost:15500 |
| API Docs (Swagger) | http://localhost:15500/docs |
| Admin UI | http://localhost:15501 |
| PostgreSQL | localhost:15433 |

**3. Migrations**

Migrations run automatically at boot via `entrypoint.sh`. No manual step needed.

**4. First login**

Migrations run automatically at boot. On first boot, the API also creates an admin API key using the value in `PII_ADMIN_INITIAL_KEY`. Use it in the `X-Api-Key` header to access the UI or call protected endpoints.

Open http://localhost:15501 and enter your admin key.

---

## Configuration

All configuration is via environment variables (see `.env.example` for the full list).

| Variable | Default | Description |
|----------|---------|-------------|
| `PII_ENCRYPTION_KEY` | — | **Required.** Fernet key for encrypting PII mappings |
| `PII_ADMIN_INITIAL_KEY` | — | **Required.** Initial admin API key created on first boot |
| `PII_DB_NAME` | `pii_protect` | PostgreSQL database name |
| `PII_DB_USER` | `pii_protect` | PostgreSQL user |
| `PII_DB_PASSWORD` | — | PostgreSQL password |
| `PII_DB_PORT` | `15433` | PostgreSQL host port |
| `PII_API_PORT` | `15500` | API host port |
| `PII_UI_PORT` | `15501` | Admin UI host port |
| `PII_SPACY_MODEL` | `it_core_news_lg` | spaCy model for Presidio layer |
| `PII_PRIVACY_FILTER_MODEL` | `openai/privacy-filter` | HuggingFace model ID for privacy-filter layer (loaded via ONNX quantized) |
| `PII_AI4PRIVACY_MODEL` | `Isotonic/distilbert_finetuned_ai4privacy_v2` | HuggingFace model ID for ai4privacy layer |
| `PII_MAPPING_TTL_DAYS` | `30` | Days before expired mappings are eligible for cleanup |
| `PII_DETECTION_LAYERS` | see below | JSON config enabling/disabling layers |

### Detection layers config

```env
PII_DETECTION_LAYERS={"regex":{"enabled":true},"presidio":{"enabled":true},"privacy_filter":{"enabled":true}}
```

Set `"enabled": false` for any layer to disable it without code changes.

---

## API Reference

The full OpenAPI 3.1 specification is in [`openapi.yaml`](./openapi.yaml) at the project root. Import it into Postman, Insomnia, or view it at http://localhost:15500/docs (Swagger UI served by FastAPI automatically).



All endpoints (except `/health`) require `X-Api-Key` header.

### Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access including key management and cleanup |
| `service` | Anonymize and deanonymize |
| `auditor` | Read-only stats and audit log |

### Endpoints

#### `POST /v1/anonymize`
Roles: `service`, `admin`

```json
{
  "text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U, tel: 333-1234567",
  "context_id": "case_file_uuid",
  "context_type": "case_file"
}
```

Response:
```json
{
  "anonymized_text": "Il sig. [PERSON_1], CF: [FISCAL_CODE_1], tel: [PHONE_1]",
  "entity_count": 3,
  "pii_types_found": ["PERSON", "FISCAL_CODE", "PHONE"],
  "entities": [
    {
      "type": "PERSON",
      "value": "Mario Rossi",
      "start": 8,
      "end": 19,
      "confidence": 0.85,
      "replacement": "[PERSON_1]"
    }
  ]
}
```

#### `POST /v1/deanonymize`
Roles: `service`, `admin`

```json
{
  "text": "Il sig. [PERSON_1], CF: [FISCAL_CODE_1]",
  "context_id": "case_file_uuid",
  "context_type": "case_file"
}
```

Response:
```json
{
  "original_text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U"
}
```

#### `GET /v1/admin/stats`
Roles: `admin`, `auditor`

Returns mapping counts, entity type breakdown, and layer hit rates.

#### `GET /v1/admin/audit-log`
Roles: `admin`, `auditor`

Query params: `page`, `page_size`, `context_id`, `from_date`, `to_date`

#### `POST /v1/admin/cleanup`
Roles: `admin`

Deletes mappings older than `PII_MAPPING_TTL_DAYS` days.

#### `POST /v1/auth/api-keys`
Roles: `admin`

```json
{ "name": "lavvocato-backend", "role": "service" }
```

#### `GET /v1/auth/api-keys`
Roles: `admin`

#### `DELETE /v1/auth/api-keys/{id}`
Roles: `admin`

#### `GET /health`
No auth required. Returns `{"status": "ok"}`.

---

## Detected PII Types

### Layer 1 — Presidio + spaCy `it_core_news_lg`
| Type | Examples |
|------|---------|
| `PERSON` | Mario Rossi, Dr. Paolo Ferri |
| `EMAIL` | mario@example.com |
| `PHONE` | +39 333 1234567 |
| `IBAN` | IT60X0542811101000001234567 |
| `FISCAL_CODE` | RSSMRA80A01H501U |
| `DATE` | 1 gennaio 1990 |
| `SECRET` | passaporto, carta d'identità, patente |

### Layer 2 — openai/privacy-filter (ONNX quantized)
| Type | Examples |
|------|---------|
| `PERSON` | Mario Rossi |
| `EMAIL` | mario@example.com |
| `PHONE` | 333 1234567 |
| `ADDRESS` | Via Roma 1, Milano |
| `DATE` | 01/01/1990 |
| `SECRET` | password, token, chiave API |
| `SECRET` | numero conto corrente |

### Layer 3 — Isotonic/distilbert_finetuned_ai4privacy_v2
| Type | Examples |
|------|---------|
| `SECRET` | password, username, numero conto, CVV, SSN |
| `PIN` | 4821 |
| `IBAN` | IT60X... |
| `MAC_ADDRESS` | AA:BB:CC:DD:EE:FF |
| `IP_ADDRESS` | 192.168.1.1, 2001:db8::1 |
| `TARGA` | AB123CD (vehicleVRM) |
| `PERSON` | Mario Rossi |
| `ADDRESS` | Via Roma 1, Milano, CAP |
| `DATE` | data di nascita |
| `EMAIL` | mario@example.com |
| `PHONE` | 333 1234567 |

### Layer 4 — Regex patterns (configurabili da UI)
| Type | Examples |
|------|---------|
| `FISCAL_CODE` | RSSMRA80A01H501U |
| `IBAN` | IT60X0542811101000001234567 |
| `EMAIL` | mario@example.com |
| `PHONE` | 06-12345678, +39 333 1234567 |
| `TARGA` | AB123CD |
| `PIVA` | P.IVA 12345678901 |
| `MAC_ADDRESS` | AA:BB:CC:DD:EE:FF |
| `UUID` | 550e8400-e29b-41d4-a716-446655440000 |
| `CVV` | CVV: 123 |
| `PIN` | PIN: 4821 |
| `IP_ADDRESS` | 192.168.1.1, 2001:db8::1 |

Regex patterns are stored in PostgreSQL and reloaded immediately on change. Manage them from the admin UI at http://localhost:15501/regex-patterns.

### Entity Denylist
Words that must never be classified as PII regardless of model output. Stored in PostgreSQL, reloaded on every change.

| Rule | Example words | Reason |
|------|--------------|--------|
| Kinship / family roles | coniuge, padre, madre, figlio | NER false positives on form labels |
| Contact labels | telefono, email, indirizzo, pec | Label text, not actual PII |
| Generic document terms | numero, codice, tipo, sede | Noise from structured documents |
| Geographic labels | latitudine, longitudine | Not a person name |

Rules apply to single-word entities only. `Dr. Paolo Ferri` is not affected. Manage from the admin UI at http://localhost:15501/denylist.

---

## Adding a New Detection Layer

The detection pipeline is extensible by design. Adding a layer requires **three small steps** and touches at most two files.

### Step 1 — Create the layer file

Create `api/app/detection/layers/<your_layer>.py`. One class per file, max 400 lines.

Implement `DetectorContract`:

```python
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity


class MyCustomDetector(DetectorContract):

    @property
    def layer_name(self) -> str:
        return "my_custom"

    @property
    def priority(self) -> int:
        return 40  # runs after Regex (30)

    def detect(self, text: str) -> list[PiiEntity]:
        entities = []
        # your detection logic here
        # return [] on failure — never raise
        return entities

    def is_available(self) -> bool:
        # return False if a required model/dependency failed to load
        return True
```

**`PiiEntity` fields:**

```python
@dataclass
class PiiEntity:
    text: str        # original matched text
    entity_type: str # e.g. "FISCAL_CODE", "PERSON"
    start: int       # char offset in input text
    end: int         # char offset in input text
    score: float     # confidence 0.0–1.0
    layer: str       # set to your layer_name
```

**Rules:**
- `detect()` must never raise — catch all exceptions and return `[]`
- Use `is_available()` to guard optional dependencies (models, network)
- Lower `priority` = runs earlier in the cascade
- Choose a unique `layer_name` (used in audit logs and stats)

### Step 2 — Register in DetectorProvider

Open `api/app/detection/detector_provider.py`. This is the **only file** that wires layers into the pipeline.

Add your import and one `if` block:

```python
from app.detection.layers.my_layer import MyCustomDetector  # add this import

class DetectorProvider:
    def build(self) -> DetectorRegistry:
        registry = DetectorRegistry()

        # existing layers ...

        if layer_config.get("my_custom", {}).get("enabled", True):  # add this block
            registry.register(MyCustomDetector())

        return registry
```

### Step 3 — Add to env config (optional)

To allow runtime enable/disable without code changes, add your layer to `PII_DETECTION_LAYERS` in `.env`:

```env
PII_DETECTION_LAYERS={"regex":{"enabled":true},"presidio":{"enabled":true},"privacy_filter":{"enabled":true},"my_custom":{"enabled":true}}
```

If omitted, the `layer_config.get("my_custom", {}).get("enabled", True)` default means it will be **enabled** unless explicitly set to `false`.

### Verify

Restart the API and call `/health`. Logs will show loaded layers:

```
INFO  DetectorRegistry: loaded layers — regex(10), presidio(20), privacy_filter(30), my_custom(40)
```

Call `/v1/anonymize` with text your layer should match and verify the entity appears in the response with `"layer": "my_custom"`.

---

## Local Development

```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download it_core_news_lg

# start only the DB
docker compose up postgres -d

# run API locally
uvicorn app.main:app --reload --port 15500
```

Run tests:

```bash
pytest
```

---

## Integration with lavvocato

```http
POST /v1/anonymize
X-Api-Key: <service_key>
Content-Type: application/json

{
  "text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U",
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "context_type": "case_file"
}
```

Store `context_id` + `context_type` alongside the anonymized text. Pass both to `/v1/deanonymize` when you need to restore original data.

Mappings are scoped per `(context_id, context_type)` pair and expire after `PII_MAPPING_TTL_DAYS` days.

---

## About

**pii-protect** is an open-source project by [Stefano Bassetto](https://github.com/nephilimdie).

Built to solve a real need: sending legal documents through AI pipelines without exposing personal data. The service sits between the application and any LLM/AI provider, pseudonymizing PII on the way in and restoring it on the way out — transparently and reversibly.

### Design principles

- **Fail-open** — if the service is unreachable, the calling app continues unprotected rather than breaking
- **Deterministic last word** — regex patterns (score 1.0) always win over probabilistic models on the same span
- **Zero vendor lock-in** — all models run locally; no data ever leaves your infrastructure
- **Operator-controlled** — patterns, denylist, and API keys are all manageable at runtime via the admin UI

### Tech stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + SQLAlchemy async |
| Database | PostgreSQL (mappings encrypted with Fernet) |
| NER Layer 1 | Microsoft Presidio + spaCy `it_core_news_lg` |
| NER Layer 2 | `openai/privacy-filter` (ONNX quantized, CPU) |
| NER Layer 3 | `Isotonic/distilbert_finetuned_ai4privacy_v2` |
| NER Layer 4 | Regex patterns (stored in DB, hot-reloaded) |
| Admin UI | React + Vite + Tailwind CSS |

---

## License

MIT — see [LICENSE](./LICENSE).
Free to use, modify, and distribute. Attribution to **Stefano Bassetto** must be retained in all copies.
