# Real-World Examples

← [README](../README.md)

All examples use `context_type` to configure policy and mode automatically. Replace `$KEY` with your admin key.

---

## Italian traffic fine appeal (tag mode)

**Input:**
```
Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, residente in Via Roma 12, 00100 Roma,
tel. 333-1234567, pec: mario.rossi@pec.it, ha presentato ricorso avverso il verbale
n. PRAT-2024-001234 del 15/04/2024, per violazione dell'art. 142 c.d.s.,
relativo al veicolo tg. AB123CD, importo € 543,00.
```

**Request:**
```bash
curl -X POST http://localhost:15500/v1/anonymize \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, residente in Via Roma 12, 00100 Roma, tel. 333-1234567, pec: mario.rossi@pec.it, ha presentato ricorso avverso il verbale n. PRAT-2024-001234 del 15/04/2024, per violazione dell'\''art. 142 c.d.s., relativo al veicolo tg. AB123CD, importo € 543,00.",
    "context_id": "ricorso-2024-001234",
    "context_type": "fine_appeal"
  }'
```

**Output:**
```
Il sig. [PERSON_1], C.F. [FISCAL_CODE_1], residente in [ADDRESS_1],
tel. [PHONE_1], pec: [EMAIL_1], ha presentato ricorso avverso il verbale
n. [PRACTICE_ID_1] del 15/04/2024, per violazione dell'art. 142 c.d.s.,
relativo al veicolo tg. AB123CD, importo € 543,00.
```

> Policy `fine_appeal`: PERSON, FISCAL_CODE, ADDRESS, PHONE, EMAIL, PRACTICE_ID are protected.  
> DATE, TARGA, LAW_REF, MONEY are kept visible (they are part of the legal record).

---

## Medical record (tag mode)

**Input:**
```
Paziente: Giulia Bianchi, nata a Firenze il 22/05/1978 (C.F. BNCGLI78E62D612X),
tessera sanitaria: IT 80 38 7000004 05 2024 75, tel. 340-9876543.
Diagnosi: ipertensione arteriosa. Prossimo controllo: 10/09/2024.
```

**Request:**
```bash
curl -X POST http://localhost:15500/v1/anonymize \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Paziente: Giulia Bianchi, nata a Firenze il 22/05/1978 (C.F. BNCGLI78E62D612X), tessera sanitaria: IT 80 38 7000004 05 2024 75, tel. 340-9876543. Diagnosi: ipertensione arteriosa. Prossimo controllo: 10/09/2024.",
    "context_id": "cartella-2024-GBianchi",
    "context_type": "medical"
  }'
```

**Output:**
```
Paziente: [PERSON_1], nata a [CITY_BORN_1] il [DATE_BORN_1] (C.F. [FISCAL_CODE_1]),
tessera sanitaria: [HEALTH_CARD_1], tel. [PHONE_1].
Diagnosi: ipertensione arteriosa. Prossimo controllo: 10/09/2024.
```

> DATE_BORN detected via reclassification: the date "22/05/1978" is preceded by "nata a Firenze il" → reclassified from DATE to DATE_BORN.

---

## Contract for LLM embedding (surrogate mode)

**Input:**
```
Contratto di locazione tra Luca Ferrari (C.F. FRRLCU85M12F205X, IBAN IT60X0542811101000001234567)
e Immobiliare Alfa S.r.l. (P.IVA 01234567890). Canone mensile: € 1.200,00.
Decorrenza: 01/01/2025.
```

**Request:**
```bash
curl -X POST http://localhost:15500/v1/anonymize \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contratto di locazione tra Luca Ferrari (C.F. FRRLCU85M12F205X, IBAN IT60X0542811101000001234567) e Immobiliare Alfa S.r.l. (P.IVA 01234567890). Canone mensile: € 1.200,00. Decorrenza: 01/01/2025.",
    "context_id": "contratto-2025-LF",
    "context_type": "embedding",
    "language": "it"
  }'
```

**Output:**
```
Contratto di locazione tra Marco Conti (C.F. CNTMRC91P03L219K, IBAN IT29P0306901789100000046169)
e Costruzioni Rossi S.p.A. (P.IVA 09876543210). Canone mensile: € 1.100,00.
Decorrenza: 03/04/2025.
```

> Surrogate mode: all values are deterministic fakes. The fake CF (`CNTMRC91P03L219K`) encodes the same name/date/city as the fake person `Marco Conti`. Safe to send to an LLM or vector DB.

---

## De-anonymize (restore original)

After tagging, restore originals using the same `context_id` and `context_type`:

```bash
curl -X POST http://localhost:15500/v1/deanonymize \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Il sig. [PERSON_1], C.F. [FISCAL_CODE_1], tel. [PHONE_1]",
    "context_id": "ricorso-2024-001234",
    "context_type": "fine_appeal"
  }'
```

**Response:**
```json
{
  "original_text": "Il sig. Mario Rossi, C.F. RSSMRA80A01H501U, tel. 333-1234567"
}
```

---

## Per-request policy override

Override the domain policy inline — e.g. protect TARGA for this specific request:

```bash
curl -X POST http://localhost:15500/v1/anonymize \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Verbale intestato a Mario Rossi, tg. AB123CD, data 15/04/2024, importo € 200,00.",
    "context_id": "caso-speciale-001",
    "context_type": "fine_appeal",
    "policy": {
      "protect": ["PERSON", "FISCAL_CODE", "TARGA"],
      "keep": ["DATE", "MONEY"]
    }
  }'
```

**Output:**
```
Verbale intestato a [PERSON_1], tg. [TARGA_1], data 15/04/2024, importo € 200,00.
```

---

## English document (EN locale surrogates)

```bash
curl -X POST http://localhost:15500/v1/anonymize \
  -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Dear John Smith, your invoice for $3,500 is due on 2025-03-15. Contact us at j.smith@company.com or +1-555-0123.",
    "context_id": "invoice-EN-001",
    "context_type": "embedding",
    "language": "en",
    "mode": "surrogate"
  }'
```

**Output:**
```
Dear Michael Johnson, your invoice for $3,500 is due on 2025-07-18. Contact us at m.johnson@company.com or +1-555-9847.
```

> Surrogates use `en_US` Faker locale: American names, US phone format.
