# Architettura & Sviluppo

← [README](../README.md)

---

## Stack tecnico

| Componente | Tecnologia |
|------------|-----------|
| API | FastAPI + SQLAlchemy async |
| Database | PostgreSQL 17 + pgvector |
| NER Layer 1 | Microsoft Presidio + spaCy `it_core_news_lg` |
| NER Layer 2 | `openai/privacy-filter` (ONNX quantized, CPU) |
| NER Layer 3 | `Isotonic/distilbert_finetuned_ai4privacy_v2` |
| NER Layer 4 | Regex patterns (DB, hot-reload) |
| Surrogati | Faker IT (seed deterministico) + CF codec custom |
| Cifratura | Fernet (symmetric, AES-128-CBC) |
| Migrazioni | Alembic |
| Admin UI | React 18 + Vite + Tailwind CSS + lucide-react |
| Container | Docker Compose |

---

## Struttura del progetto

```
pii-protect/
├── api/
│   ├── app/
│   │   ├── detection/              # Pipeline di detection
│   │   │   ├── contracts/          # DetectorContract ABC
│   │   │   ├── layers/             # Un file per layer
│   │   │   │   ├── regex_layer.py
│   │   │   │   ├── presidio_layer.py
│   │   │   │   ├── privacy_filter_layer.py
│   │   │   │   └── ai4privacy_layer.py
│   │   │   ├── entities.py         # PiiEntity dataclass
│   │   │   ├── entity_merger.py    # Merge + overlap resolution
│   │   │   ├── detector_registry.py
│   │   │   └── detector_provider.py   ← unico file da toccare per aggiungere layer
│   │   ├── anonymization/          # Pseudonimizzazione + cifratura Fernet
│   │   ├── surrogates/             # Generazione valori finti
│   │   │   ├── cf_codec.py         # Encoder/decoder Codice Fiscale italiano
│   │   │   ├── generators.py       # Generatori Faker IT per tipo
│   │   │   ├── surrogate_service.py
│   │   │   └── policy_service.py
│   │   ├── routers/                # Endpoint FastAPI
│   │   ├── identity/               # Auth + ruoli
│   │   ├── audit/                  # Audit log
│   │   ├── mapping/                # Persistenza token↔valore
│   │   └── main.py
│   ├── alembic/
│   │   └── versions/               # 027+ migrazioni sequenziali
│   └── requirements.txt
├── ui/
│   └── src/
│       ├── pages/                  # Una pagina per feature admin
│       ├── components/             # NavBar, Layout
│       └── lib/api.ts              # Client API tipizzato
├── doc/                            # Documentazione tecnica (questo file)
├── openapi.yaml                    # Spec OpenAPI 3.1
└── docker-compose.yml
```

---

## Aggiungere un layer di detection

**1. Crea il file** — `api/app/detection/layers/my_layer.py`

```python
from app.detection.contracts.detector_contract import DetectorContract
from app.detection.entities import PiiEntity

class MyCustomDetector(DetectorContract):
    @property
    def layer_name(self) -> str:
        return "my_custom"

    @property
    def priority(self) -> int:
        return 15  # tra Presidio (10) e privacy-filter (20)

    def detect(self, text: str, language: str = "it") -> list[PiiEntity]:
        # Mai sollevare eccezioni — return [] in caso di errore
        return []

    def is_available(self) -> bool:
        return True
```

**2. Registra in `detector_provider.py`**

```python
from app.detection.layers.my_layer import MyCustomDetector

# dentro build():
registry.register(MyCustomDetector())
```

**3. Rebuild**

```bash
docker compose up -d --build api
```

---

## Aggiungere un tipo PII

1. Aggiungi una migration Alembic che inserisce il tipo in `pii_type_registry`
2. (Opzionale) Aggiungi il pattern regex in una migration separata
3. (Opzionale) Aggiungi il generatore Faker in `surrogates/generators.py` e `_STRATEGY_MAP`

---

## Migrazioni Alembic

Le migrazioni sono sequenziali (`001` → `027`). Vengono eseguite automaticamente all'avvio del container tramite `entrypoint.sh`.

Per aggiungere una migrazione manualmente:

```bash
# dentro il container API
alembic revision -m "descrizione"
# oppure crea il file manualmente seguendo la convenzione NNN_nome.py
```

Naming convention: `NNN_descrizione_breve.py` con `revision = "NNN"` e `down_revision = "NNN-1"`.

---

## Sviluppo locale

```bash
# PostgreSQL in Docker
docker compose up postgres -d

# API locale
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
# UI locale
cd ui
npm install
npm run dev   # → http://localhost:5173
```

---

## Test

```bash
make test
# oppure
docker compose exec api pytest
```

---

## Principi di design

- **Fail-open** — se il servizio è irraggiungibile, l'app chiamante continua invece di bloccarsi
- **Regex vince sempre** — score 1.0 fisso, sovrascrive qualsiasi overlap ML
- **Zero vendor lock-in** — tutti i modelli girano localmente, nessun dato esce dall'infrastruttura
- **Operator-controlled** — pattern, policy, regole e chiavi API gestibili a runtime dall'admin UI
- **Context-driven** — un campo `context_type` governa tutto: policy, mode, comportamento

---

## Integrazione con lavvocato

Tre pattern d'uso principali:

**Generazione (chat / ricorso) — tag mode:**
```http
POST /v1/anonymize
{ "text": "...", "context_id": "...", "context_type": "fine_appeal" }
```
Protegge l'identità, lascia i fatti legali (data, importo, targa, articolo). De-anonimizza l'output prima di mostrarlo all'utente.

**Embedding (vector DB esterno) — surrogate mode:**
```http
POST /v1/anonymize
{ "text": "...", "context_id": "...", "context_type": "embedding" }
```
Sostituisce PII con surrogati realistici. L'embedding cattura il significato semantico senza esporre dati reali. Non serve de-anonimizzazione per la similarity search.

**Policy custom per richiesta:**
```http
POST /v1/anonymize
{
  "text": "...",
  "context_id": "...",
  "context_type": "fine_appeal",
  "policy": { "protect": ["PERSON","FISCAL_CODE"], "keep": ["DATE","MONEY","TARGA"] }
}
```

Salva `context_id` + `context_type` insieme al testo anonimizzato. Passa entrambi a `/v1/deanonymize` per ripristinare.
