# Sistema di Policy

← [README](../README.md)

La policy determina **cosa fare** con ogni tipo PII rilevato. È configurata su tre livelli gerarchici:

```
Context Type
    ↓ punta a
Domain Policy  →  protect_types / keep_types / surrogate_types
    ↓ fallback
PII Type Registry  →  default_action per tipo
```

---

## PII Type Registry

Registro centrale di tutti i tipi PII riconosciuti dal sistema (~33 tipi).

Ogni tipo ha:

| Campo | Descrizione |
|-------|-------------|
| `code` | Identificatore (es. `FISCAL_CODE`) |
| `category` | `IDENTITY`, `CONTACT`, `FINANCIAL`, `LEGAL`, `VEHICLE`, `NETWORK`, `CREDENTIAL` |
| `display_name` | Nome leggibile |
| `default_action` | `protect`, `keep`, o `redact` — usato se nessuna policy lo sovrascrive |
| `faker_strategy` | Generatore Faker da usare in surrogate mode |
| `reversible` | Se il surrogate può essere de-anonimizzato |
| `enabled` | Abilita/disabilita il tipo a livello globale |

![PII Type Registry](img/pii_types_registry.png)

Gestisci da **Policy → PII Types**.

### Tipi per categoria

| Categoria | Tipi |
|-----------|------|
| IDENTITY | PERSON, FISCAL_CODE, DATE_BORN, CITY_BORN, PASSPORT, IDENTITY_CARD, DRIVER_LICENSE, HEALTH_CARD |
| CONTACT | ACCOUNT, ADDRESS, EMAIL, PHONE |
| FINANCIAL | BIC, CREDIT_CARD, IBAN, MONEY, SALARY |
| LEGAL | DATE, LAW_REF, LOYALTY_ID, POLICY_NUMBER, PRACTICE_ID, PNR, TICKET_ID |
| VEHICLE | IMEI, TARGA |
| NETWORK | API_KEY, GPS_COORDINATE, IP_ADDRESS, MAC_ADDRESS, URL |
| CREDENTIAL | SECRET |

---

## Domain Policies

Una domain policy definisce, per un dato dominio applicativo, quali tipi PII:
- **Proteggere** (🛡 nascondi) — anonimizzati con tag o surrogate
- **Lasciare visibili** (👁 vedi) — lasciati invariati nel testo
- **Sostituire con Faker** (✨) — sempre surrogati, anche se il context type è in modalità `tag`
- **Non assegnati** — seguono il `default_action` del tipo nel registry

### Policy pre-caricate

| Domain | Protect | Keep |
|--------|---------|------|
| `default` | Tutti i tipi IDENTITY, CONTACT, FINANCIAL | DATE, MONEY, LAW_REF, URL, GPS |
| `fine_appeal` | PERSON, CF, EMAIL, PHONE, ADDRESS, IBAN, IDENTITY_CARD, DRIVER_LICENSE | DATE, MONEY, LAW_REF, **TARGA**, PRACTICE_ID, TICKET_ID |
| `contract_analysis` | PERSON, CF, EMAIL, PHONE, ADDRESS, IBAN, CREDIT_CARD, **TARGA**, COMPANY | DATE, MONEY, LAW_REF, POLICY_NUMBER |
| `medical` | PERSON, CF, EMAIL, PHONE, ADDRESS, **HEALTH_CARD** | DATE, MONEY, LAW_REF, PRACTICE_ID |

> `TARGA` è in **keep** per `fine_appeal` (la targa è parte del fascicolo) ma in **protect** per `contract_analysis`.

Gestisci da **Policy → Domain Policies**.

---

## Context Types

I context type sono il punto di entrata della pipeline. Il caller passa un singolo campo `context_type` e il sistema configura automaticamente policy e modalità.

| Campo | Descrizione |
|-------|-------------|
| `code` | Stringa da passare come `context_type` nella chiamata API |
| `display_name` | Nome leggibile nell'admin UI |
| `domain` | Domain policy collegata (FK → `domain_policies`) |
| `default_mode` | `tag` o `surrogate` — usato se non sovrascritto nella richiesta |
| `enabled` | Abilita/disabilita il context type |

### Context type pre-caricati

| Code | Domain | Mode | Uso tipico |
|------|--------|------|-----------|
| `default` | default | tag | Generico |
| `fine_appeal` | fine_appeal | tag | Ricorsi infrazioni stradali |
| `contract_analysis` | contract_analysis | tag | Analisi contratti |
| `medical` | medical | tag | Documenti sanitari |
| `hr` | default | tag | Risorse umane |
| `legal_brief` | contract_analysis | tag | Atti legali |
| `embedding` | default | **surrogate** | Testo per LLM/vector DB |

![Context Types](img/context_types.png)

![Context Types — Policy Editor](img/context_types_policy_editor.png)

Cliccando su una riga nella pagina Context Types si apre l'editor inline della policy collegata: è possibile assegnare ogni tipo PII a protect/keep/faker senza uscire dalla pagina.

Gestisci da **Policy → Context Types**.

---

## Risoluzione della policy — ordine di precedenza

```
1. inline policy nel body della richiesta   (massima priorità)
2. domain policy del context_type
3. default_action del tipo nel PII registry (fallback)
```

Il `mode` segue la stessa logica:
```
1. mode nel body della richiesta
2. default_mode del context_type
3. "tag" (fallback globale)
```

---

## Override inline nella richiesta

```json
{
  "text": "...",
  "context_id": "uuid",
  "context_type": "fine_appeal",
  "mode": "surrogate",
  "policy": {
    "protect":   ["PERSON", "FISCAL_CODE"],
    "keep":      ["DATE", "TARGA"],
    "surrogate": ["EMAIL", "PHONE"]
  }
}
```

L'override inline sostituisce completamente la domain policy collegata al context type.
