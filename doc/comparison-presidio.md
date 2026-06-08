# pii-protect vs Microsoft Presidio

← [README](../README.md)

pii-protect is built **on top of** Presidio, not against it. Presidio handles one detection layer; pii-protect adds three more layers, a policy engine, surrogate generation, and an admin UI around it.

---

## At a glance

| Capability | Microsoft Presidio | pii-protect |
|------------|-------------------|-------------|
| Detection layers | 1 (spaCy / custom recognizers) | 4 (Presidio + 2 transformers + DB regex) |
| Italian-specific types (CF, TARGA, PIVA…) | Partial (custom recognizers needed) | Built-in regex patterns, hot-reloadable |
| Regex management | Code / YAML files | Admin UI, live DB update, no restart |
| Policy engine | None | protect / keep / surrogate per PII type, per domain |
| Context types | None | One field configures everything |
| Surrogate mode | None | Deterministic, format-preserving, locale-aware |
| Coherent personas (PERSON ↔ CF) | None | Shared `surrogate_profiles` per context |
| De-anonymization | None | Built-in, Fernet-encrypted token store |
| Admin UI | None | Full React admin |
| Multi-tenant / API key roles | None | admin / service / auditor |
| Audit log | None | Per-call log with entity counts |
| Deployment | Python library | Docker Compose microservice |
| License | MIT | MIT |

---

## When to use Presidio directly

- You need a **Python library** to embed in your application, not a sidecar
- Your use case is English-only with standard NER types (PERSON, EMAIL, PHONE…)
- You want full control over every recognizer and need no policy abstraction
- You're building a custom pipeline and Presidio is one component among many

## When to use pii-protect

- You need a **language-agnostic REST sidecar** deployable next to any stack
- You work with **Italian documents** (Codice Fiscale, Targa, PIVA, Tessera Sanitaria…)
- You need **domain-specific policies** (different rules for legal, medical, HR documents)
- You need **surrogate mode** to feed LLMs or vector DBs without exposing real PII
- You want **runtime configurability** without touching code (regex patterns, policies, rules from UI)
- You need **de-anonymization** and encrypted mapping persistence

---

## Architecture relationship

```
pii-protect
├── Detection layer 1: Presidio + spaCy        ← uses Presidio as a library
├── Detection layer 2: openai/privacy-filter
├── Detection layer 3: AI4Privacy (distilbert)
├── Detection layer 4: DB Regex
├── Entity merger + reclassification
├── Policy engine (context types → domain policies → registry)
├── Surrogate engine (Faker IT/EN/DE/…, CF codec, coherent profiles)
├── Fernet-encrypted mapping store
└── Admin UI + REST API
```

Presidio is a first-class citizen inside pii-protect's detection pipeline. It is not replaced — it is extended.

---

## Accuracy comparison

Direct comparison is difficult because Presidio's accuracy depends heavily on configured recognizers and the target language. pii-protect's advantage is in structured Italian PII types (CF, IBAN, TARGA) where regex is near-perfect, and in PERSON/ADDRESS where the ensemble of three ML models outperforms any single model.

See [README — Accuracy & Limitations](../README.md#accuracy--limitations) for pii-protect's preliminary benchmark.
