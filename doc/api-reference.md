# API Reference

← [README](../README.md)

Full OpenAPI spec interattiva: http://localhost:15500/docs  
File YAML: [`openapi.yaml`](../openapi.yaml)

---

## Autenticazione

Ogni endpoint (tranne `/health`) richiede la chiave API nell'header:

```
X-Api-Key: your-api-key-here
```

### Ruoli

| Ruolo | Permessi |
|-------|----------|
| `admin` | Accesso completo |
| `service` | Anonimizza e de-anonimizza |
| `auditor` | Lettura stats e audit log |

---

## Core

### `POST /v1/anonymize`

Rileva PII nel testo e le sostituisce con token o surrogati.

```bash
curl -X POST http://localhost:15500/v1/anonymize \
  -H "X-Api-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U, tel: 333-1234567",
    "context_id": "550e8400-e29b-41d4-a716-446655440000",
    "context_type": "fine_appeal"
  }'
```

**Body:**

| Campo | Tipo | Required | Descrizione |
|-------|------|----------|-------------|
| `text` | string | ✓ | Testo da anonimizzare |
| `context_id` | string | ✓ | Identificatore documento/sessione |
| `context_type` | string | ✓ | Configura policy e mode automaticamente |
| `language` | string | — | Lingua NER (default: `it`) |
| `mode` | `tag`\|`surrogate` | — | Sovrascrive il default del context type |
| `policy` | object | — | `{"protect":[...], "keep":[...], "surrogate":[...]}` |
| `detection_mode` | `permissive`\|`strict` | — | Sensibilità detection (default: `permissive`) |

**Risposta:**

```json
{
  "anonymized_text": "Il sig. [PERSON_1], CF: [FISCAL_CODE_1], tel: [PHONE_1]",
  "entity_count": 3,
  "pii_types_found": ["PERSON", "FISCAL_CODE", "PHONE"],
  "mode": "tag",
  "entities": [
    { "type": "PERSON", "value": "Mario Rossi", "start": 8, "end": 19, "confidence": 0.99, "replacement": "[PERSON_1]" }
  ]
}
```

---

### `POST /v1/deanonymize`

Ripristina i valori originali in un testo precedentemente anonimizzato.

```bash
curl -X POST http://localhost:15500/v1/deanonymize \
  -H "X-Api-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Il sig. [PERSON_1], CF: [FISCAL_CODE_1]",
    "context_id": "550e8400-e29b-41d4-a716-446655440000",
    "context_type": "fine_appeal"
  }'
```

**Risposta:**
```json
{ "original_text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U" }
```

---

## Admin — Statistiche e log

### `GET /v1/admin/stats`

```bash
curl http://localhost:15500/v1/admin/stats -H "X-Api-Key: your-key"
```

### `GET /v1/admin/audit-log`

Query params: `page`, `page_size` (max 200), `context_id`, `context_type`, `action`, `from_date`, `to_date`

### `POST /v1/admin/cleanup`

Elimina i mapping scaduti (> `PII_MAPPING_TTL_DAYS` giorni).

---

## Admin — Configurazione policy

### Context Types

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/context-types` | Lista tutti i context type |
| `POST` | `/v1/admin/context-types` | Crea context type |
| `PUT` | `/v1/admin/context-types/{code}` | Aggiorna |
| `DELETE` | `/v1/admin/context-types/{code}` | Elimina |

### Domain Policies

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/domain-policies` | Lista tutte le policy |
| `PUT` | `/v1/admin/domain-policies/{domain}` | Crea o aggiorna (upsert) |
| `DELETE` | `/v1/admin/domain-policies/{domain}` | Elimina |

### PII Type Registry

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/pii-types` | Lista tutti i tipi |
| `PUT` | `/v1/admin/pii-types/{code}` | Aggiorna campi (default_action, faker_strategy, …) |

---

## Admin — Configurazione detection

### Regex Patterns

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/regex-patterns` | Lista pattern |
| `POST` | `/v1/admin/regex-patterns` | Crea pattern |
| `PUT` | `/v1/admin/regex-patterns/{id}` | Aggiorna |
| `DELETE` | `/v1/admin/regex-patterns/{id}` | Elimina |

### Reclassification Rules

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/reclassification-rules` | Lista regole |
| `POST` | `/v1/admin/reclassification-rules` | Crea regola |
| `PUT` | `/v1/admin/reclassification-rules/{id}` | Aggiorna |
| `DELETE` | `/v1/admin/reclassification-rules/{id}` | Elimina |

### Denylist

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/denylist` | Lista entries |
| `POST` | `/v1/admin/denylist` | Aggiungi entry |
| `PUT` | `/v1/admin/denylist/{id}` | Aggiorna |
| `DELETE` | `/v1/admin/denylist/{id}` | Elimina |

### Context Words (Presidio)

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/presidio-context` | Lista context words |
| `POST` | `/v1/admin/presidio-context` | Aggiungi |
| `PUT` | `/v1/admin/presidio-context/{id}` | Aggiorna |
| `DELETE` | `/v1/admin/presidio-context/{id}` | Elimina |

---

## Admin — Sistema

### API Keys

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/auth/api-keys` | Lista chiavi (solo metadata) |
| `POST` | `/v1/auth/api-keys` | Crea chiave — il valore raw è mostrato una sola volta |
| `DELETE` | `/v1/auth/api-keys/{id}` | Revoca chiave |

### Languages

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/languages` | Modelli spaCy installati |
| `POST` | `/v1/admin/languages/{code}/install` | Installa modello (`it`, `en`, `de`, …) |

### Mappings

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/v1/admin/mappings` | Mapping token→valore (paginati) |
| `DELETE` | `/v1/admin/mappings/bulk` | Eliminazione bulk |

### Health

```bash
curl http://localhost:15500/health
# → {"status": "ok"}
```
