# Anonymization Modes

← [README](../README.md)

The `mode` field in the request (or the `default_mode` of the context type) determines how detected PII entities are handled.

---

## Tag mode (default)

Entities are replaced with numbered opaque tokens:

```
Input:  "Il sig. Mario Rossi, CF: RSSMRA80A01H501U, tel: 333-1234567"
Output: "Il sig. [PERSON_1], CF: [FISCAL_CODE_1], tel: [PHONE_1]"
```

Tokens are **stable per value**: the same real text always produces the same token within the same `context_id`. `Mario Rossi` is always `[PERSON_1]`, no matter how many times it appears.

Token→real value mappings are saved encrypted (Fernet) in PostgreSQL under the `context_id` and can be retrieved via `/v1/deanonymize`.

---

## Surrogate mode

Entities are replaced with fake but **realistic and format-preserving** values:

```
Input:  "Il sig. Mario Rossi, CF: RSSMRA80A01H501U, IBAN: IT60X0542811101000001234567"
Output: "Il sig. Luca Bianchi, CF: BNCLCU85M12F205X, IBAN: IT29P0306901789100000046169"
```

| Type | Surrogate |
|------|-----------|
| `PERSON` | Fake Italian name and surname |
| `FISCAL_CODE` | Valid 16-character CF |
| `EMAIL` | Fake email with same structure |
| `PHONE` | Fake Italian number |
| `IBAN` | Structurally valid Italian IBAN |
| `TARGA` | Plate in the AA000BB format |
| `DATE` | Date shifted by N days (consistent) |
| `ADDRESS` | Fake Italian address |
| `CITY_BORN` | Fake Italian city |

### Locale-aware generation

Surrogates adapt to the document language via the `language` field in the request:

| `language` | Faker locale | Names | Phone format | Company suffixes |
|------------|-------------|-------|--------------|-----------------|
| `it` | `it_IT` | Italian | +39 | S.r.l., S.p.A. |
| `en` | `en_US` | American | +1 | LLC, Inc., Corp. |
| `de` | `de_DE` | German | +49 | GmbH, AG, KG |
| `fr` | `fr_FR` | French | +33 | SARL, SA, SAS |
| `es` | `es_ES` | Spanish | +34 | S.L., S.A. |
| `pt` | `pt_PT` | Portuguese | +351 | Lda., S.A. |
| `nl` | `nl_NL` | Dutch | +31 | B.V., N.V. |

Format-neutral types (IBAN, IP, MAC, URL, IMEI, PNR) are generated identically regardless of locale.

> **Note:** FISCAL_CODE and TARGA are Italian-specific PII types. Their surrogate generators always use Italian format — these types are not expected to appear in non-Italian documents.

### Determinism

Surrogates are generated deterministically:

```python
seed = int(sha256(f"{real_value}|{context_id}".encode()).hexdigest()[:16], 16)
faker = Faker(locale)  # derived from the request's language field
faker.seed_instance(seed)
```

Same `real_value` + same `context_id` + same `language` → same surrogate, always. No DB read is needed to generate: the DB acts as a cache to support de-anonymization.

---

## Coherent profiles (PERSON + FISCAL_CODE)

The Italian Codice Fiscale encodes name, surname, date of birth, gender, and municipality. A fake CF generated independently from the fake name would be incoherent.

**Solution:** `surrogate_profiles` — a table linking `context_id` + `real_name_key` to a complete fake profile:

| Field | Example |
|-------|---------|
| `fake_first_name` | Luca |
| `fake_last_name` | Bianchi |
| `fake_birth_date` | 1985-08-12 |
| `fake_gender` | M |
| `fake_city` | Milano |
| `fake_belfiore` | F205 |
| `fake_cf` | BNCLCU85M12F205X |

When anonymizing `Mario Rossi`:
1. The system looks up or creates the profile for `mario rossi` in the `context_id`
2. Uses `fake_first_name + " " + fake_last_name` as the PERSON surrogate
3. When it then finds CF `RSSMRA80A01H501U`, it partially decodes it to extract the gender, looks up the same profile, and returns `fake_cf`

Result: the fake name and the fake CF refer to the **same fictional person**.

---

## Codice Fiscale — algorithm

The `cf_codec.py` module implements the full Italian encoding:

| Component | Rule |
|-----------|------|
| Surname | 3 consonants; if fewer, fill with vowels then `X` |
| Name | ≥4 consonants → 1st, 3rd, 4th; otherwise consonants+vowels+`X` |
| Year | last 2 digits |
| Month | letter code (`ABCDEHLMPRST`) |
| Day | 01-31 for M, +40 for F |
| Municipality | Belfiore code (e.g. `H501` for Roma) |
| Check char | ODD/EVEN tables on odd/even positions + modulo 26 |

---

## Per-type surrogate control

From the policy it is possible to set surrogate mode per individual PII type, independently of the context type's mode:

- **Hide** (🛡) — opaque tag
- **Keep** (👁) — leave in text
- **Faker** (✨) — always replace with surrogate even if the context type is in `tag` mode

Configurable from **Policy → Context Types** (inline editor) or **Policy → Domain Policies**.

---

## De-anonymization

```http
POST /v1/deanonymize
{
  "text": "Il sig. [PERSON_1], CF: [FISCAL_CODE_1]",
  "context_id": "case_file_uuid",
  "context_type": "fine_appeal"
}
```

Response:
```json
{ "original_text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U" }
```

Surrogates in `surrogate` mode are saved as tokens in the `mapping_tokens` table (`token` = fake value, `original` = real value) — the same mechanism used for tags. De-anonymization therefore works identically for both modes.
