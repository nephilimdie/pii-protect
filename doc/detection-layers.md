# Layer di Detection

← [README](../README.md)

La pipeline di detection esegue tutti e 4 i layer in parallelo via `ThreadPoolExecutor`, poi unisce i risultati con `EntityMerger`.

---

## Priorità e merge

Ogni layer ha una priorità numerica. In caso di overlap tra due entità rilevate da layer diversi, vince quella con score più alto. Il layer Regex ha score fisso `1.0` e vince sempre sugli overlap con i layer ML.

| Layer | Modello | Priorità | Score |
|-------|---------|----------|-------|
| Presidio + spaCy | `it_core_news_lg` | 10 | variabile |
| openai/privacy-filter | ONNX quantized, CPU | 20 | variabile |
| AI4Privacy | `distilbert_finetuned_ai4privacy_v2` | 25 | variabile |
| **Regex (DB)** | pattern configurabili | **30** | **1.0** |

---

## Layer 1 — Presidio + spaCy

Tipi rilevati: `PERSON`, `EMAIL`, `PHONE`, `IBAN`, `FISCAL_CODE`, `DATE`

Usa il modello NER italiano `it_core_news_lg`. I context words (parole che aumentano la probabilità di riconoscimento) sono configurabili dall'admin UI sotto **Detection → Context Words**.

---

## Layer 2 — openai/privacy-filter

Tipi rilevati: `PERSON`, `EMAIL`, `PHONE`, `ADDRESS`, `DATE`, `SECRET`

Modello ONNX quantizzato, gira su CPU senza GPU. Buono per segreti e token (API key, password).

---

## Layer 3 — AI4Privacy (distilbert)

Tipi rilevati: `PASSWORD`, `USERNAME`, `ACCOUNT_NUMBER`, `CREDIT_CARD`, `CVV`, `PIN`, `IBAN`, `BIC`, `MAC_ADDRESS`, `IP_ADDRESS`, `GPS_COORDINATE`, `URL`, `TARGA`, `PERSON`, `ADDRESS`, `DATE`, `EMAIL`, `PHONE`

Modello fine-tuned specifico per PII. Copre tipi tecnici che i layer NER tradizionali non rilevano.

---

## Layer 4 — Regex (DB-configurabili)

Tipi rilevati: `FISCAL_CODE`, `IBAN`, `EMAIL`, `PHONE`, `TARGA`, `PIVA`, `CREDIT_CARD`, `MAC_ADDRESS`, `IP_ADDRESS`, `GPS_COORDINATE`, `HEALTH_CARD`, `PRACTICE_ID`, `TICKET_ID`, `POLICY_NUMBER`, `IMEI`, `PNR`, `ACCOUNT`, `API_KEY`, `BIC`, `CITY_BORN`, `COMPANY`, `SALARY`, `DATE`, `DATE_BORN`

I pattern sono salvati nel DB (`regex_patterns`) e ricaricati a caldo ad ogni modifica. Non serve restart.

Ogni pattern ha:
- **PII type** — tipo di entità
- **Pattern** — regex Python
- **Flags** — `IGNORECASE`, `MULTILINE`, `DOTALL` (separati da virgola)
- **Capture group** — gruppo da estrarre (0 = full match)
- **Enabled** — on/off senza eliminare

Gestisci da **Detection → Regex Patterns**.

![Regex Patterns](img/regex_patterns.png)

---

## Denylist

Parole o frasi che, se presenti come testo di un'entità, la invalidano (falso positivo ricorrente).

Supporta due modalità:
- **exact** — match esatto su singola parola (dopo stripping degli onorificis)
- **contains** — l'entità contiene la stringa

Gestisci da **Detection → Denylist**.

---

## Context Words (Presidio)

Parole che, se appaiono vicino a un'entità, aumentano il confidence score di Presidio per quel tipo.

Esempio: aggiungere `"codice fiscale"` per `FISCAL_CODE` fa sì che Presidio sia più propenso a riconoscere una stringa vicina come CF.

Gestisci da **Detection → Context Words**.

---

## Snap to word boundary

Dopo il merge, ogni entità viene "snappata" ai bordi di parola:
- Strip leading whitespace (i tokenizer BPE includono spesso lo spazio precedente)
- Espansione destra se l'entità termina a metà parola
- Per `PERSON`: assorbimento onorificis precedenti (Dr., Avv., Ing., …) e strip di termini di parentela aggiunti per errore dai modelli ML

---

## Reclassification Rules

Regole applicate **dopo** il merge. Cambiano il tipo di un'entità in base al contesto testuale.

Ogni regola ha:
- **FROM** — tipo sorgente
- **TO** — tipo destinazione (null = elimina l'entità)
- **Context pattern** — regex cercata nei N caratteri prima dell'entità
- **Entity pattern** — regex cercata nel testo dell'entità stessa
- Se entrambi i pattern sono impostati, devono matchare entrambi (AND logic)
- **Context window** — quanti caratteri prima guardare (default 60)

Visualizzate come grafo bipartito (FROM a sinistra, TO a destra, frecce tratteggiate = regola disabilitata).

![Reclassification Rules](img/reclassification_rules.png)

Gestisci da **Detection → Reclass. Rules**.

### Esempi pre-caricati

| FROM | TO | Condizione |
|------|----|-----------|
| `PERSON` | `ACCOUNT` | entity contiene `@` |
| `PERSON` | `ACCOUNT` | context ha `username:` o `login:` |
| `PERSON` | `ORGANIZATION` | context ha `datore di lavoro:` o `azienda:` |
| `PERSON` | `ORGANIZATION` | entity contiene forma giuridica (S.r.l., S.p.A.) |
| `PERSON` | `EMAIL` | context ha `email:` o `posta elettronica:` |
| `DATE` | `DATE_BORN` | context ha `nato/nata a <Città> il` (80 char window) |
