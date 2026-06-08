# Detection Layers

← [README](../README.md)

The detection pipeline runs all 4 layers in parallel via `ThreadPoolExecutor`, then merges results with `EntityMerger`.

---

## Priority and merge

Each layer has a numeric priority. When two entities from different layers overlap, the one with the higher score wins. The Regex layer has a fixed score of `1.0` and always wins on overlaps with ML layers.

| Layer | Model | Priority | Score |
|-------|-------|----------|-------|
| Presidio + spaCy | `it_core_news_lg` | 10 | variable |
| openai/privacy-filter | ONNX quantized, CPU | 20 | variable |
| AI4Privacy | `distilbert_finetuned_ai4privacy_v2` | 25 | variable |
| **Regex (DB)** | configurable patterns | **30** | **1.0** |

---

## Layer 1 — Presidio + spaCy

Detected types: `PERSON`, `EMAIL`, `PHONE`, `IBAN`, `FISCAL_CODE`, `DATE`

Uses the Italian NER model `it_core_news_lg`. Context words (words that increase recognition confidence) are configurable from the admin UI under **Detection → Context Words**.

---

## Layer 2 — openai/privacy-filter

Detected types: `PERSON`, `EMAIL`, `PHONE`, `ADDRESS`, `DATE`, `SECRET`

Quantized ONNX model, runs on CPU without GPU. Good for secrets and tokens (API keys, passwords).

---

## Layer 3 — AI4Privacy (distilbert)

Detected types: `PASSWORD`, `USERNAME`, `ACCOUNT_NUMBER`, `CREDIT_CARD`, `CVV`, `PIN`, `IBAN`, `BIC`, `MAC_ADDRESS`, `IP_ADDRESS`, `GPS_COORDINATE`, `URL`, `TARGA`, `PERSON`, `ADDRESS`, `DATE`, `EMAIL`, `PHONE`

Fine-tuned model specifically for PII. Covers technical types that traditional NER layers miss.

---

## Layer 4 — Regex (DB-configurable)

Detected types: `FISCAL_CODE`, `IBAN`, `EMAIL`, `PHONE`, `TARGA`, `PIVA`, `CREDIT_CARD`, `MAC_ADDRESS`, `IP_ADDRESS`, `GPS_COORDINATE`, `HEALTH_CARD`, `PRACTICE_ID`, `TICKET_ID`, `POLICY_NUMBER`, `IMEI`, `PNR`, `ACCOUNT`, `API_KEY`, `BIC`, `CITY_BORN`, `COMPANY`, `SALARY`, `DATE`, `DATE_BORN`

Patterns are stored in the DB (`regex_patterns`) and hot-reloaded on every change. No restart required.

Each pattern has:
- **PII type** — entity type
- **Pattern** — Python regex
- **Flags** — `IGNORECASE`, `MULTILINE`, `DOTALL` (comma-separated)
- **Capture group** — group to extract (0 = full match)
- **Enabled** — on/off without deleting

Manage from **Detection → Regex Patterns**.

![Regex Patterns](img/regex_patterns.png)

---

## Denylist

Words or phrases that, if present as an entity's text, invalidate it (recurring false positive).

Supports two modes:
- **exact** — exact match on a single word (after stripping honorifics)
- **contains** — the entity contains the string

Manage from **Detection → Denylist**.

---

## Context Words (Presidio)

Words that, when appearing near an entity, increase Presidio's confidence score for that type.

Example: adding `"codice fiscale"` for `FISCAL_CODE` makes Presidio more likely to recognize a nearby string as a CF.

Manage from **Detection → Context Words**.

---

## Snap to word boundary

After merging, each entity is snapped to word boundaries:
- Strip leading whitespace (BPE tokenizers often include the preceding space)
- Right-expand if the entity ends mid-word
- For `PERSON`: absorb preceding honorifics (Dr., Avv., Ing., …) and strip relational terms erroneously added by ML models

---

## Reclassification Rules

Rules applied **after** the merge. They change an entity's type based on textual context.

Each rule has:
- **FROM** — source type
- **TO** — target type (null = drop the entity)
- **Context pattern** — regex searched in the N characters before the entity
- **Entity pattern** — regex searched in the entity text itself
- If both patterns are set, both must match (AND logic)
- **Context window** — how many characters to look back (default 60)

Visualized as a bipartite graph (FROM on the left, TO on the right, dashed arrows = disabled rule).

![Reclassification Rules](img/reclassification_rules.png)

Manage from **Detection → Reclass. Rules**.

### Pre-loaded examples

| FROM | TO | Condition |
|------|----|-----------|
| `PERSON` | `ACCOUNT` | entity contains `@` |
| `PERSON` | `ACCOUNT` | context has `username:` or `login:` |
| `PERSON` | `ORGANIZATION` | context has `datore di lavoro:` or `azienda:` |
| `PERSON` | `ORGANIZATION` | entity contains legal suffix (S.r.l., S.p.A.) |
| `PERSON` | `EMAIL` | context has `email:` or `posta elettronica:` |
| `DATE` | `DATE_BORN` | context has `nato/nata a <City> il` (80-char window) |
