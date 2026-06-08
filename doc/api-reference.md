# API Reference

← [README](../README.md)

Interactive OpenAPI spec: http://localhost:15500/docs  
YAML file: [`openapi.yaml`](../openapi.yaml)

---

## Authentication

Every endpoint (except `/health`) requires the API key in the header:

```
X-Api-Key: your-api-key-here
```

### Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access |
| `service` | Anonymize and de-anonymize |
| `auditor` | Read-only stats and audit log |

---

## Core

### `POST /v1/anonymize`

Detects PII in the text and replaces it with tokens or surrogates.

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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | ✓ | Text to anonymize |
| `context_id` | string | ✓ | Document/session identifier |
| `context_type` | string | ✓ | Automatically configures policy and mode |
| `language` | string | — | NER language hint (default: `it`) |
| `mode` | `tag`\|`surrogate` | — | Overrides the context type default |
| `policy` | object | — | `{"protect":[...], "keep":[...], "surrogate":[...]}` |
| `detection_mode` | `permissive`\|`strict` | — | Detection sensitivity (default: `permissive`) |

**Response:**

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

Restores original values in a previously anonymized text.

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

**Response:**
```json
{ "original_text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U" }
```

---

## Admin — Stats and log

### `GET /v1/admin/stats`

```bash
curl http://localhost:15500/v1/admin/stats -H "X-Api-Key: your-key"
```

### `GET /v1/admin/audit-log`

Query params: `page`, `page_size` (max 200), `context_id`, `context_type`, `action`, `from_date`, `to_date`

### `POST /v1/admin/cleanup`

Deletes expired mappings (older than `PII_MAPPING_TTL_DAYS` days).

---

## Admin — Policy configuration

### Context Types

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/context-types` | List all context types |
| `POST` | `/v1/admin/context-types` | Create context type |
| `PUT` | `/v1/admin/context-types/{code}` | Update |
| `DELETE` | `/v1/admin/context-types/{code}` | Delete |

### Domain Policies

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/domain-policies` | List all policies |
| `PUT` | `/v1/admin/domain-policies/{domain}` | Create or update (upsert) |
| `DELETE` | `/v1/admin/domain-policies/{domain}` | Delete |

### PII Type Registry

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/pii-types` | List all types |
| `PUT` | `/v1/admin/pii-types/{code}` | Update fields (default_action, faker_strategy, …) |

---

## Admin — Detection configuration

### Regex Patterns

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/regex-patterns` | List patterns |
| `POST` | `/v1/admin/regex-patterns` | Create pattern |
| `PUT` | `/v1/admin/regex-patterns/{id}` | Update |
| `DELETE` | `/v1/admin/regex-patterns/{id}` | Delete |

### Reclassification Rules

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/reclassification-rules` | List rules |
| `POST` | `/v1/admin/reclassification-rules` | Create rule |
| `PUT` | `/v1/admin/reclassification-rules/{id}` | Update |
| `DELETE` | `/v1/admin/reclassification-rules/{id}` | Delete |

### Denylist

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/denylist` | List entries |
| `POST` | `/v1/admin/denylist` | Add entry |
| `PUT` | `/v1/admin/denylist/{id}` | Update |
| `DELETE` | `/v1/admin/denylist/{id}` | Delete |

### Context Words (Presidio)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/presidio-context` | List context words |
| `POST` | `/v1/admin/presidio-context` | Add |
| `PUT` | `/v1/admin/presidio-context/{id}` | Update |
| `DELETE` | `/v1/admin/presidio-context/{id}` | Delete |

---

## Admin — System

### API Keys

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/auth/api-keys` | List keys (metadata only) |
| `POST` | `/v1/auth/api-keys` | Create key — raw value shown once only |
| `DELETE` | `/v1/auth/api-keys/{id}` | Revoke key |

### Languages

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/languages` | Installed spaCy models |
| `POST` | `/v1/admin/languages/{code}/install` | Install model (`it`, `en`, `de`, …) |

### Mappings

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/mappings` | Token mappings (paginated) |
| `DELETE` | `/v1/admin/mappings/bulk` | Bulk delete |

### Health

```bash
curl http://localhost:15500/health
# → {"status": "ok"}
```
