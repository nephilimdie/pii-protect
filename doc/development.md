# Architecture & Development

← [README](../README.md)

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + SQLAlchemy async |
| Database | PostgreSQL 17 + pgvector |
| NER Layer 1 | Microsoft Presidio + spaCy `it_core_news_lg` |
| NER Layer 2 | `openai/privacy-filter` (ONNX quantized, CPU) |
| NER Layer 3 | `Isotonic/distilbert_finetuned_ai4privacy_v2` |
| NER Layer 4 | Regex patterns (DB, hot-reload) |
| Surrogates | Faker IT (deterministic seed) + custom CF codec |
| Encryption | Fernet (symmetric, AES-128-CBC) |
| Migrations | Alembic |
| Admin UI | React 18 + Vite + Tailwind CSS + lucide-react |
| Container | Docker Compose |

---

## Project Structure

```
pii-protect/
├── api/
│   ├── app/
│   │   ├── detection/              # Detection pipeline
│   │   │   ├── contracts/          # DetectorContract ABC
│   │   │   ├── layers/             # One file per layer
│   │   │   │   ├── regex_layer.py
│   │   │   │   ├── presidio_layer.py
│   │   │   │   ├── privacy_filter_layer.py
│   │   │   │   └── ai4privacy_layer.py
│   │   │   ├── entities.py         # PiiEntity dataclass
│   │   │   ├── entity_merger.py    # Merge + overlap resolution
│   │   │   ├── detector_registry.py
│   │   │   └── detector_provider.py   ← only file to touch when adding a layer
│   │   ├── anonymization/          # Pseudonymization + Fernet encryption
│   │   ├── surrogates/             # Fake value generation
│   │   │   ├── cf_codec.py         # Italian Codice Fiscale encoder/decoder
│   │   │   ├── generators.py       # Faker IT generators per type
│   │   │   ├── surrogate_service.py
│   │   │   └── policy_service.py
│   │   ├── routers/                # FastAPI endpoints
│   │   ├── identity/               # Auth + roles
│   │   ├── audit/                  # Audit log
│   │   ├── mapping/                # Token↔value persistence
│   │   └── main.py
│   ├── alembic/
│   │   └── versions/               # 027+ sequential migrations
│   └── requirements.txt
├── ui/
│   └── src/
│       ├── pages/                  # One page per admin feature
│       ├── components/             # NavBar, Layout
│       └── lib/api.ts              # Typed API client
├── doc/                            # Technical documentation (this file)
├── openapi.yaml                    # OpenAPI 3.1 spec
└── docker-compose.yml
```

---

## Adding a Detection Layer

**1. Create the file** — `api/app/detection/layers/my_layer.py`

```python
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

class MyCustomDetector(DetectorContract):
    @property
    def layer_name(self) -> str:
        return "my_custom"

    @property
    def priority(self) -> int:
        return 15  # between Presidio (10) and privacy-filter (20)

    def detect(self, text: str, language: str = "it") -> list[PiiEntity]:
        # Never raise exceptions — return [] on error
        return []

    def is_available(self) -> bool:
        return True
```

**2. Register in `detector_provider.py`**

```python
from app.detection.layers.my_layer import MyCustomDetector

# inside build():
registry.register(MyCustomDetector())
```

**3. Rebuild**

```bash
docker compose up -d --build api
```

---

## Adding a PII Type

1. Add an Alembic migration that inserts the type into `pii_type_registry`
2. (Optional) Add the regex pattern in a separate migration
3. (Optional) Add the Faker generator in `surrogates/generators.py` and `_STRATEGY_MAP`

---

## Alembic Migrations

Migrations are sequential (`001` → `027`+). They run automatically at container startup via `entrypoint.sh`.

To add a migration manually:

```bash
# inside the API container
alembic revision -m "description"
# or create the file manually following the NNN_name.py convention
```

Naming convention: `NNN_short_description.py` with `revision = "NNN"` and `down_revision = "NNN-1"`.

---

## Local Development

```bash
# PostgreSQL in Docker
docker compose up postgres -d

# Local API
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download it_core_news_lg

export DATABASE_URL="postgresql+asyncpg://pii_protect:changeme_secret@localhost:15433/pii_protect"
export ENCRYPTION_KEY="your-fernet-key"
export ADMIN_INITIAL_KEY="your-admin-key"

uvicorn app.main:app --reload --port 15500
```

```bash
# Local UI
cd ui
npm install
npm run dev   # → http://localhost:5173
```

---

## Tests

```bash
make test
# or
docker compose exec api pytest
```

---

## Design Principles

- **Fail-open** — if the service is unreachable, the calling app continues rather than blocking
- **Regex always wins** — fixed score 1.0, overwrites any ML overlap
- **Zero vendor lock-in** — all models run locally, no data leaves the infrastructure
- **Operator-controlled** — patterns, policies, rules, and API keys manageable at runtime from the admin UI
- **Context-driven** — a single `context_type` field governs everything: policy, mode, behavior

---

## Integration Patterns

Three main usage patterns:

**Generation (chat / appeal) — tag mode:**
```http
POST /v1/anonymize
{ "text": "...", "context_id": "...", "context_type": "fine_appeal" }
```
Protects identity, leaves legal facts (date, amount, plate, article). De-anonymize output before showing to the user.

**Embedding (external vector DB) — surrogate mode:**
```http
POST /v1/anonymize
{ "text": "...", "context_id": "...", "context_type": "embedding" }
```
Replaces PII with realistic surrogates. The embedding captures semantic meaning without exposing real data. No de-anonymization needed for similarity search.

**Custom per-request policy:**
```http
POST /v1/anonymize
{
  "text": "...",
  "context_id": "...",
  "context_type": "fine_appeal",
  "policy": { "protect": ["PERSON","FISCAL_CODE"], "keep": ["DATE","MONEY","TARGA"] }
}
```

Save `context_id` + `context_type` alongside the anonymized text. Pass both to `/v1/deanonymize` to restore.
