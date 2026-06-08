# pii-protect

Microservizio standalone di pseudonimizzazione PII per documenti italiani. Rileva e anonimizza dati personali tramite una pipeline multi-layer configurabile, con supporto a surrogati realistici e politiche per dominio.

---

## Documentazione

| Documento | Contenuto |
|-----------|-----------|
| [Architettura & sviluppo](doc/development.md) | Stack tecnico, struttura progetto, aggiungere layer, dev locale |
| [Layer di detection](doc/detection-layers.md) | I 4 layer ML/regex, priorità, regex patterns, denylist, context words |
| [Modalità di anonimizzazione](doc/anonymization-modes.md) | Tag vs surrogate, profili coerenti, Codice Fiscale, reversibilità |
| [Sistema di policy](doc/policy-system.md) | Context types, domain policies, PII type registry, reclassification rules |
| [API Reference](doc/api-reference.md) | Tutti gli endpoint REST con esempi curl |

---

## Feature

| Feature | Descrizione |
|---------|-------------|
| **Detection multi-layer** | 4 layer in cascata: Presidio+spaCy, openai/privacy-filter, AI4Privacy, Regex DB. Le regex hanno sempre priorità sugli overlap. |
| **Modalità tag** | Sostituisce PII con token opachi `[PERSON_1]`. Reversibile via `/v1/deanonymize`. |
| **Modalità surrogate** | Sostituisce PII con valori finti ma realistici (nome, CF, IBAN, targa). Deterministica: stesso input → stesso output. |
| **Profili coerenti** | PERSON e FISCAL_CODE condividono un profilo finto per `context_id`: il CF finto codifica lo stesso nome/data/città della persona fittizia. |
| **Context types** | Un singolo campo `context_type` nella chiamata API configura automaticamente policy e modalità. |
| **Domain policies** | Per ogni dominio (fine_appeal, contratto, medico…) definisce quali tipi PII proteggere, lasciare visibili, o sostituire con Faker. |
| **PII Type Registry** | ~33 tipi PII categorizzati (IDENTITY, CONTACT, FINANCIAL, LEGAL, VEHICLE, NETWORK, CREDENTIAL) con azione di default e strategia Faker. |
| **Reclassification rules** | Regole post-detection che cambiano il tipo di un'entità in base al contesto (es. PERSON con `@` → ACCOUNT). Visualizzate come grafo bipartito. |
| **Regex configurabili** | Pattern regex salvati in DB, ricaricati a caldo. Gestibili dall'admin UI senza restart. |
| **Denylist** | Liste di parole/frasi da escludere dal riconoscimento (falsi positivi ricorrenti). |
| **Audit log** | Ogni chiamata API è tracciata: tipo di azione, numero di entità, context type, chiave usata. |
| **API key management** | Ruoli `admin`, `service`, `auditor`. Chiavi con scadenza opzionale. |
| **Multi-lingua** | spaCy supporta IT, EN, DE, FR, ES, PT. Modelli installabili dall'admin UI. |
| **Admin UI** | React + Tailwind. Gestione completa di tutti i componenti senza toccare il codice. |

---

## Installazione

### Prerequisiti

- Docker + Docker Compose
- `make` (pre-installato su macOS/Linux)

### Avvio rapido

```bash
make setup   # crea .env da .env.example
# → modifica .env: imposta PII_ENCRYPTION_KEY e PII_ADMIN_INITIAL_KEY
make start   # build immagini + avvia servizi + esegue migrazioni
```

Genera la chiave di cifratura:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

| Servizio | URL default |
|----------|-------------|
| REST API | http://localhost:15500 |
| API Docs (Swagger) | http://localhost:15500/docs |
| Admin UI | http://localhost:15501 |
| PostgreSQL | localhost:15433 |

Al primo avvio l'API crea automaticamente una chiave admin da `PII_ADMIN_INITIAL_KEY`. Aprire http://localhost:15501 e inserirla.

### Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `PII_ENCRYPTION_KEY` | — | **Obbligatoria.** Chiave Fernet per cifrare i mapping PII |
| `PII_ADMIN_INITIAL_KEY` | — | **Obbligatoria.** Chiave admin iniziale |
| `PII_DB_PASSWORD` | — | Password PostgreSQL |
| `PII_DB_NAME` | `pii_protect` | Nome database |
| `PII_DB_PORT` | `15433` | Porta PostgreSQL sull'host |
| `PII_API_PORT` | `15500` | Porta API sull'host |
| `PII_UI_PORT` | `15501` | Porta Admin UI sull'host |
| `PII_MAPPING_TTL_DAYS` | `30` | Giorni prima che i mapping scadano |

---

## Screenshot

### Dashboard
![Dashboard](doc/img/dashboard.png)

### Regex Patterns
![Regex Patterns](doc/img/regex_patterns.png)

### Reclassification Rules
![Reclassification Rules](doc/img/reclassification_rules.png)

### PII Type Registry
![PII Type Registry](doc/img/pii_types_registry.png)

### Context Types — policy editor inline
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
