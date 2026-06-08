# Modalità di Anonimizzazione

← [README](../README.md)

Il campo `mode` nella richiesta (o il `default_mode` del context type) determina come vengono trattate le entità PII rilevate.

---

## Tag mode (default)

Le entità vengono sostituite con token opachi numerati:

```
Input:  "Il sig. Mario Rossi, CF: RSSMRA80A01H501U, tel: 333-1234567"
Output: "Il sig. [PERSON_1], CF: [FISCAL_CODE_1], tel: [PHONE_1]"
```

I token sono **stabili per valore**: lo stesso testo reale produce sempre lo stesso token nello stesso `context_id`. `Mario Rossi` è sempre `[PERSON_1]`, non importa quante volte appare.

I mapping token→valore reale sono salvati cifrati (Fernet) in PostgreSQL sotto il `context_id` e possono essere recuperati via `/v1/deanonymize`.

---

## Surrogate mode

Le entità vengono sostituite con valori finti ma **realistici e format-preserving**:

```
Input:  "Il sig. Mario Rossi, CF: RSSMRA80A01H501U, IBAN: IT60X0542811101000001234567"
Output: "Il sig. Luca Bianchi, CF: BNCLCU85M12F205X, IBAN: IT29P0306901789100000046169"
```

| Tipo | Surrogate |
|------|-----------|
| `PERSON` | Nome e cognome italiano finto |
| `FISCAL_CODE` | CF valido a 16 caratteri |
| `EMAIL` | Email fittizia stessa struttura |
| `PHONE` | Numero italiano finto |
| `IBAN` | IBAN italiano strutturalmente valido |
| `TARGA` | Targa nel formato AA000BB |
| `DATE` | Data spostata di N giorni (coerente) |
| `ADDRESS` | Indirizzo italiano finto |
| `CITY_BORN` | Città italiana finta |

### Determinismo

I surrogati sono generati deterministicamente:

```python
seed = int(sha256(f"{real_value}|{context_id}".encode()).hexdigest()[:16], 16)
faker = Faker("it_IT")
faker.seed_instance(seed)
```

Stesso `real_value` + stesso `context_id` → stesso surrogate, sempre. Non serve leggere il DB per generare: il DB funge da cache per supportare la de-anonimizzazione.

---

## Profili coerenti (PERSON + FISCAL_CODE)

Il Codice Fiscale italiano codifica nome, cognome, data di nascita, sesso e comune. Un CF finto generato in modo indipendente dal nome finto sarebbe incoerente.

**Soluzione:** `surrogate_profiles` — una tabella che lega `context_id` + `real_name_key` a un profilo finto completo:

| Campo | Esempio |
|-------|---------|
| `fake_first_name` | Luca |
| `fake_last_name` | Bianchi |
| `fake_birth_date` | 1985-08-12 |
| `fake_gender` | M |
| `fake_city` | Milano |
| `fake_belfiore` | F205 |
| `fake_cf` | BNCLCU85M12F205X |

Quando si anonimizza `Mario Rossi`:
1. Il sistema cerca/crea il profilo per `mario rossi` nel `context_id`
2. Usa `fake_first_name + " " + fake_last_name` come surrogate del PERSON
3. Quando poi trova il CF `RSSMRA80A01H501U`, lo decodifica parzialmente per estrarre il sesso, cerca lo stesso profilo e restituisce `fake_cf`

Il risultato: nome finto e CF finto si riferiscono alla **stessa persona fittizia**.

---

## Codice Fiscale — algoritmo

Il modulo `cf_codec.py` implementa la codifica italiana completa:

| Componente | Regola |
|------------|--------|
| Cognome | 3 consonanti; se meno, completare con vocali poi `X` |
| Nome | ≥4 consonanti → 1ª, 3ª, 4ª; altrimenti consonanti+vocali+`X` |
| Anno | ultime 2 cifre |
| Mese | codice lettera (`ABCDEHLMPRST`) |
| Giorno | 01-31 per M, +40 per F |
| Comune | codice Belfiore (es. `H501` per Roma) |
| Check char | tabelle ODD/EVEN su posizioni dispari/pari + modulo 26 |

---

## Surrogate per tipo — controllo granulare

Dalla policy è possibile impostare il surrogate per singolo tipo PII, indipendentemente dalla modalità del context type:

- **Nascondi** (🛡) — tag opaco
- **Vedi** (👁) — lascia nel testo
- **Faker** (✨) — sostituisce con surrogate anche se il context type è in modalità `tag`

Configurabile da **Policy → Context Types** (editor inline) o **Policy → Domain Policies**.

---

## De-anonimizzazione

```http
POST /v1/deanonymize
{
  "text": "Il sig. [PERSON_1], CF: [FISCAL_CODE_1]",
  "context_id": "case_file_uuid",
  "context_type": "fine_appeal"
}
```

Risposta:
```json
{ "original_text": "Il sig. Mario Rossi, CF: RSSMRA80A01H501U" }
```

I surrogati in modalità `surrogate` vengono salvati come token nella tabella `mapping_tokens` (colonna `token` = valore finto, `original` = valore reale) — lo stesso meccanismo dei tag. La de-anonimizzazione funziona quindi allo stesso modo per entrambe le modalità.
