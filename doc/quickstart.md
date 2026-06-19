# Quickstart

← [README](../README.md)

Get PII anonymization running in under 5 minutes.

---

## 1. Start the engine

```bash
# 1. Clone and start
git clone https://github.com/your-org/pii-protect
cp .env.example .env
# edit .env: set DATABASE_URL, ENCRYPTION_KEY, ADMIN_INITIAL_KEY
docker compose up -d

# 2. Get your API key
export PII_KEY=$(grep ADMIN_INITIAL_KEY .env | cut -d= -f2)
export PII_URL=http://localhost:15500
```

---

## 2. Anonymize text

### curl

```bash
export PII_KEY="your_api_key"
export PII_URL="https://your-engine-host:15500"

curl -s -X POST "$PII_URL/v1/anonymize" \
  -H "X-Api-Key: $PII_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Mario Rossi, CF RSSMRA80A01H501U, tel 333-1234567",
    "context_id": "doc-001",
    "context_type": "fine_appeal",
    "language": "it"
  }' | jq .
```

Response:

```json
{
  "ok": true,
  "text": "[PERSON_1], CF [FISCAL_CODE_1], tel [PHONE_1]",
  "entities": [
    { "type": "PERSON",      "original": "Mario Rossi",        "token": "[PERSON_1]" },
    { "type": "FISCAL_CODE", "original": "RSSMRA80A01H501U",  "token": "[FISCAL_CODE_1]" },
    { "type": "PHONE",       "original": "333-1234567",        "token": "[PHONE_1]" }
  ]
}
```

### De-anonymize

```bash
curl -s -X POST "$PII_URL/v1/deanonymize" \
  -H "X-Api-Key: $PII_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "[PERSON_1], CF [FISCAL_CODE_1], tel [PHONE_1]",
    "context_id": "doc-001",
    "context_type": "fine_appeal"
  }' | jq .
```

---

## 3. SDK examples

### Python

```python
import httpx

PII_URL = "https://your-engine-host:15500"
PII_KEY = "your_api_key"

headers = {"X-Api-Key": PII_KEY}

def anonymize(text: str, context_id: str, context_type: str = "fine_appeal", language: str = "it") -> dict:
    r = httpx.post(f"{PII_URL}/v1/anonymize", headers=headers, json={
        "text": text,
        "context_id": context_id,
        "context_type": context_type,
        "language": language,
    })
    r.raise_for_status()
    return r.json()

def deanonymize(text: str, context_id: str, context_type: str = "fine_appeal") -> dict:
    r = httpx.post(f"{PII_URL}/v1/deanonymize", headers=headers, json={
        "text": text,
        "context_id": context_id,
        "context_type": context_type,
    })
    r.raise_for_status()
    return r.json()

# Usage
result = anonymize("Mario Rossi, CF RSSMRA80A01H501U", context_id="doc-001")
print(result["text"])  # "[PERSON_1], CF [FISCAL_CODE_1]"

original = deanonymize(result["text"], context_id="doc-001")
print(original["text"])  # "Mario Rossi, CF RSSMRA80A01H501U"
```

Install: `pip install httpx`

### Node.js

```js
const PII_URL = 'https://your-engine-host:15500';
const PII_KEY = 'your_api_key';

const headers = { 'X-Api-Key': PII_KEY, 'Content-Type': 'application/json' };

async function anonymize(text, contextId, contextType = 'fine_appeal', language = 'it') {
  const res = await fetch(`${PII_URL}/v1/anonymize`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ text, context_id: contextId, context_type: contextType, language }),
  });
  if (!res.ok) throw new Error(`PII engine error: ${res.status}`);
  return res.json();
}

async function deanonymize(text, contextId, contextType = 'fine_appeal') {
  const res = await fetch(`${PII_URL}/v1/deanonymize`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ text, context_id: contextId, context_type: contextType }),
  });
  if (!res.ok) throw new Error(`PII engine error: ${res.status}`);
  return res.json();
}

// Usage (Node 18+ with built-in fetch)
const result = await anonymize('Mario Rossi, CF RSSMRA80A01H501U', 'doc-001');
console.log(result.text); // "[PERSON_1], CF [FISCAL_CODE_1]"

const original = await deanonymize(result.text, 'doc-001');
console.log(original.text); // "Mario Rossi, CF RSSMRA80A01H501U"
```

### PHP

```php
<?php

const PII_URL = 'https://your-engine-host:15500';
const PII_KEY = 'your_api_key';

function pii_request(string $path, array $payload): array
{
    $ch = curl_init(PII_URL . $path);
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode($payload),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => [
            'X-Api-Key: ' . PII_KEY,
            'Content-Type: application/json',
            'Accept: application/json',
        ],
    ]);
    $body = curl_exec($ch);
    curl_close($ch);
    return json_decode($body, true);
}

// Anonymize
$result = pii_request('/v1/anonymize', [
    'text'         => 'Mario Rossi, CF RSSMRA80A01H501U',
    'context_id'   => 'doc-001',
    'context_type' => 'fine_appeal',
    'language'     => 'it',
]);
echo $result['text']; // "[PERSON_1], CF [FISCAL_CODE_1]"

// De-anonymize
$original = pii_request('/v1/deanonymize', [
    'text'         => $result['text'],
    'context_id'   => 'doc-001',
    'context_type' => 'fine_appeal',
]);
echo $original['text']; // "Mario Rossi, CF RSSMRA80A01H501U"
```

---

## 4. Surrogate mode

Replace PII with realistic fakes instead of opaque tokens. Useful for RAG pipelines where semantic meaning must be preserved.

```bash
curl -s -X POST "$PII_URL/v1/anonymize" \
  -H "X-Api-Key: $PII_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Mario Rossi, CF RSSMRA80A01H501U",
    "context_id": "doc-001",
    "context_type": "fine_appeal",
    "mode": "surrogate",
    "language": "it"
  }' | jq .text
# "Luca Bianchi, CF BNCLCU79B15F205K"
```

The same `context_id` always produces the same surrogate — consistent across multiple calls.

---

## 5. Batch mode

```bash
curl -s -X POST "$PII_URL/v1/anonymize/batch" \
  -H "X-Api-Key: $PII_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "id": "a", "text": "Mario Rossi vive a Roma", "context_id": "doc-001", "context_type": "fine_appeal" },
      { "id": "b", "text": "IBAN IT60X0542811101000000123456", "context_id": "doc-002", "context_type": "fine_appeal" }
    ]
  }' | jq .
```

---

## 6. Context types

Context types auto-configure the pipeline (which PII types to protect, mode, surrogate strategy):

```bash
# List available context types
curl -s "$PII_URL/v1/admin/context-types" -H "X-Api-Key: $PII_KEY" | jq '.data[].code'
```

Built-in types: `fine_appeal`, `contract`, `medical`, `generic`.
Custom types can be created via `POST /v1/admin/context-types`.

---

## Next steps

- [API Reference](api-reference.md) — full endpoint documentation
- [Anonymization modes](anonymization-modes.md) — tag vs surrogate vs dry-run
- [Detection layers](detection-layers.md) — how the 4-layer pipeline works
- [Policy system](policy-system.md) — context types, domain policies, reclassification
