# Held-out Italian PII benchmark (`it_pii_heldout_v1`)

An independent test set for the Pseudora engine. It was written **after** the detection sprint, with
its own code, data and layouts, and frozen by hash before any system was run on it
([FREEZE.md](FREEZE.md)). It exists to answer one question: how much of the sprint's gain on
`it_pii_v1` (leak 24.4% to 3.9%) carries over to text the rules were not written against?

## Results at a glance

| `generic_professional` preset | Lenient F1 | Strict F1 | Leak rate | FP on negatives | ms / 1k chars |
|---|---|---|---|---|---|
| Before the sprint (f790d04), original `it_pii_v1` | 78.3 | 66.8 | 24.4 | 15.6 | 331 |
| Before the sprint (f790d04), **held-out** | 70.0 [68.3, 71.5] | 53.4 | 31.5 [29.8, 33.2] | 16.7 | 290 |
| After the sprint (master, `balanced`), original `it_pii_v1` | 95.5 | 90.6 | 3.9 | 8.1 | 329 |
| After the sprint (master, `balanced`), **held-out** | **78.2** [76.5, 79.8] | **65.5** | **17.3** [15.8, 19.0] | **13.2** [11.5, 15.0] | 301 |

- **The sprint generalises, but only partly.** On unseen documents the leak rate falls from 31.5% to
  17.3% (−14.2 points; paired 95% CI −15.7 to −12.6), against −20.5 points on the corpus the rules were
  tuned on. About **70% of the leak reduction and half of the F1 gain carry over**. The rest was
  fitting to our own templates.
- **The headline 3.9% leak does not hold on new text: expect about 17%.** Part of that is a harder
  corpus, not overfitting. Untuned systems also do worse here: the pre-sprint engine leaks +7.1 points,
  Rizzo-PII +4.7, vanilla Presidio +6.4. The tuned rules lose more (+13.5), so the overfitting share
  is roughly 6 to 9 leak points.
- **Keep the transformers on by default.** On the original corpus regex+Presidio looked as good as the
  full pipeline. On held-out data, dropping the transformers raises the leak from 17.3% to 24.8%
  (+6.6 to +8.3 points, paired CI) for the same F1. It is 10× faster (28 vs 301 ms per 1k characters)
  and masks fewer look-alikes (8.6% vs 13.2%). The transformers are what handles phrasings nobody
  wrote a rule for.
- **`maximum` is still not worth it as a default:** −0.3 to −0.6 leak points for +2.4 points of false
  masking.
- **Rizzo-PII leaks about half as much (8.8%) but masks 47% of look-alikes.** Its advantage is concentrated
  in ALL-CAPS names, birth places in form fields and table-cell identifiers, which shows where our recall gaps are.

### Sintesi (IT)

Il corpus held-out (442 documenti, scritto da zero dopo lo sprint e congelato per hash prima di
qualsiasi esecuzione) mostra che lo sprint funziona anche su testi nuovi, ma molto meno di quanto
dica il benchmark su cui è stato tarato. Con il preset `generic_professional` il leak passa dal 31,5%
(motore pre-sprint) al 17,3% (master): −14 punti, contro i −20,5 su `it_pii_v1`. Circa il 70% del
guadagno sul leak si trasferisce, la metà di quello sull'F1. Il 3,9% di leak non va citato: su testo
nuovo la stima onesta è intorno al 17%. I transformer vanno tenuti attivi di default. Senza di
loro il leak sale al 24,8% (+7,5 punti) a parità di F1, in cambio di una latenza 10 volte più bassa.
Il livello `maximum` non conviene come default. Le perdite principali: nomi in MAIUSCOLO, luoghi di
nascita nei moduli (CU, F24), matricole nelle tabelle, date tipo «16-GIU-1979», identificativi
indiretti, e-mail offuscate o URL-encoded, IPv6.


## Corpus

| | |
|---|---|
| Documents | 442: 342 with PII, 100 PII-free near-miss documents |
| Characters | 275,227 |
| Gold PII spans | 3,964 (PERSON 1,415 · FISCAL_CODE 380 · DATE_OF_BIRTH 336 · ADDRESS 319 · EMAIL 254 · PHONE 247 · BIRTH_PLACE 209 · IBAN 198 · EMPLOYEE_ID 117 · ID_DOCUMENT 77 · CONTRACT_ID 77 · LICENSE_PLATE 73 · IP_ADDRESS 67 · USERNAME 59 · INDIRECT 42 · CADASTRAL_REF 27 · CREDIT_CARD 21 · CASE_ID 20 · VAT_NUMBER 14 · SOCIAL_SECURITY 12) |
| Negative look-alikes | 2,980 (MONEY 704 · CODE 570 · DOC_DATE 461 · ORG 335 · DOC_NUMBER 324 · LAW_REF 297 · PUBLIC_BODY 156 · COMMON_WORD 133) |
| Genres (sub-genres) | legal 84 (PEC, verbali, atti di citazione, ricorsi) · hr_tax 50 (buste paga, CU, F24) · real_estate_medical 56 (locazioni, perizie, referti) · chat 44 (WhatsApp, mixed IT/EN) · structured 66 (CRM CSV, server logs, JSON API, spreadsheets) · free_text 42 (letters, whistleblowing, esposti, helpdesk tickets) · negative 100 (delibere, eponymous streets/hospitals, name-like words, product codes, history notes, case-law summaries, tech logs) |
| Scanner noise | 49 documents (own noise model, see FREEZE.md) |
| Hard cases (spans) | first name only 417 · foreign 341 · surname only 289 · particle surname 273 · uppercase 263 · lowercase 186 · word-like name 148 · spaced code 134 · double surname 109 · ... (full list in `dataset/*.stats.json`) |

How it was written, and what "independent" does and does not mean here, is in [FREEZE.md](FREEZE.md).
Gold schema, taxonomy, matching rules and metrics are exactly those of [`benchmark/italian`](../italian/README.md),
so the numbers are directly comparable. `COMMON_WORD` negatives here also cover eponymous public
places used in a non-identifying sense ("piazza Aldo Moro sarà chiusa al traffico").

## Results

Engine: production code of `master` 697bac8 (`api/` mounted read-only into `docjobs-engine:base`, the
same image and pinned model cache as the original benchmark), HTTP `/v1/anonymize` dry run. Vanilla
Presidio and Rizzo-PII 0.3B v1.5.0 run as in the original harness. One machine: Docker VM, 6 CPUs,
8 GB, aarch64, no GPU. All values in %; 1,000 document-level bootstrap resamples.

<!-- heldout:start -->
### Held-out vs original corpus

| System | Lenient F1 held-out [95% CI] | original | Strict F1 held-out | original | Leak held-out [95% CI] | original | FP on negatives held-out [95% CI] | original | ms / 1k chars held-out | original |
|---|---|---|---|---|---|---|---|---|---|---|
| `pseudora_presprint_generic_professional` | **70.0** [68.3, 71.5] | 78.3 | 53.4 | 66.8 | **31.5** [29.8, 33.2] | 24.4 | 16.7 [14.8, 18.6] | 15.6 | 289.58 | 330.99 |
| `pseudora_generic_professional` | **78.2** [76.5, 79.8] | 95.5 | 65.5 | 90.6 | **17.3** [15.8, 19.0] | 3.9 | 13.2 [11.5, 15.0] | 8.1 | 301.0 | 328.71 |
| `pseudora_generic_professional_maximum` | **77.7** [76.1, 79.2] | 95.3 | 64.5 | 90.9 | **16.9** [15.4, 18.5] | 3.4 | 15.6 [13.8, 17.4] | 8.4 | 297.43 | 320.13 |
| `ablation_regex_presidio` | **78.2** [76.8, 79.6] | 96.2 | 67.5 | 91.6 | **24.8** [23.2, 26.4] | 5.1 | 8.6 [7.3, 10.3] | 5.6 | 28.01 | 35.25 |
| `ablation_regex` | **67.7** [65.8, 69.6] | 91.3 | 60.9 | 89.8 | **38.3** [36.1, 40.5] | 13.6 | 3.2 [2.4, 3.9] | 4.6 | 8.82 | 16.37 |
| `presidio_vanilla_it` | **57.9** [56.3, 59.3] | 67.5 | 44.1 | 52.3 | **31.4** [29.7, 33.1] | 25.0 | 28.7 [26.8, 30.7] | 25.3 | 18.02 | 17.72 |
| `rizzo_pii_only` | **70.6** [68.3, 72.7] | 81.5 | 50.7 | 59.8 | **8.8** [7.4, 10.2] | 4.0 | 46.8 [45.0, 48.7] | 46.6 | 228.52 | 214.89 |
| `rizzo_default` | **64.9** [62.6, 67.0] | 76.6 | 46.3 | 55.9 | **8.5** [7.2, 10.0] | 3.9 | 77.7 [75.7, 79.5] | 76.9 | 283.32 | 218.59 |

### Overfitting gap (held-out minus original, percentage points)

| System | Δ lenient F1 | Δ strict F1 | Δ leak | Δ FP on negatives |
|---|---|---|---|---|
| `pseudora_presprint_generic_professional` | -8.3 | -13.4 | +7.1 | +1.1 |
| `pseudora_generic_professional` | -17.3 | -25.0 | +13.5 | +5.2 |
| `pseudora_generic_professional_maximum` | -17.6 | -26.4 | +13.5 | +7.1 |
| `ablation_regex_presidio` | -17.9 | -24.1 | +19.8 | +3.0 |
| `ablation_regex` | -23.5 | -28.9 | +24.7 | -1.5 |
| `presidio_vanilla_it` | -9.6 | -8.2 | +6.4 | +3.3 |
| `rizzo_pii_only` | -10.9 | -9.1 | +4.7 | +0.2 |
| `rizzo_default` | -11.7 | -9.6 | +4.7 | +0.7 |

### Paired difference vs `pseudora_generic_professional` on the held-out set (95% bootstrap CI, points)

| System | Δ lenient F1 | Δ leak (positive = leaks more) |
|---|---|---|
| `pseudora_presprint_generic_professional` | [-9.2, -7.2] | [12.6, 15.7] |
| `pseudora_generic_professional_maximum` | [-0.8, -0.2] | [-0.6, -0.3] |
| `ablation_regex_presidio` | [-0.9, 1.0] | [6.6, 8.3] |
| `ablation_regex` | [-12.2, -8.6] | [19.2, 22.7] |
| `presidio_vanilla_it` | [-21.7, -19.0] | [12.3, 15.8] |
| `rizzo_pii_only` | [-9.3, -6.0] | [-10.0, -7.2] |
| `rizzo_default` | [-14.8, -11.8] | [-10.2, -7.4] |

### Leak rate by entity type, held-out (original in parentheses for the reference)

| Type (held-out gold spans) | `pseudora_generic_professional` | `pseudora_generic_professional_maximum` | `ablation_regex_presidio` | `rizzo_pii_only` |
|---|---|---|---|---|
| PERSON (1415) | 21.2 (4.2) | 20.0 | 35.5 | 7.1 |
| BIRTH_PLACE (209) | 48.4 (0.0) | 45.7 | 68.9 | 4.8 |
| EMPLOYEE_ID (117) | 67.8 (4.0) | 67.8 | 74.4 | 8.3 |
| DATE_OF_BIRTH (336) | 18.1 (0.6) | 18.1 | 25.1 | 0.3 |
| INDIRECT (42) | 96.8 (99.0) | 96.5 | 99.7 | 89.0 |
| CONTRACT_ID (77) | 50.4 (0.0) | 50.4 | 49.6 | 12.8 |
| ADDRESS (319) | 10.1 (4.2) | 9.6 | 17.0 | 3.4 |
| FISCAL_CODE (380) | 7.8 (0.5) | 7.8 | 8.0 | 6.4 |
| EMAIL (254) | 6.8 (0.0) | 6.7 | 11.3 | 5.3 |
| IP_ADDRESS (67) | 11.8 (0.0) | 13.9 | 9.7 | 20.8 |
| CREDIT_CARD (21) | 33.3 (0.0) | 33.3 | 7.4 | 0.0 |
| USERNAME (59) | 10.3 (0.0) | 8.2 | 57.7 | 86.6 |
| IBAN (198) | 2.9 (0.0) | 2.9 | 2.9 | 0.0 |
| ID_DOCUMENT (77) | 6.5 (0.0) | 6.5 | 6.5 | 2.6 |
| CADASTRAL_REF (27) | 15.7 (0.0) | 15.7 | 15.7 | 4.8 |
| CASE_ID (20) | 0.0 (0.0) | 0.0 | 0.0 | 0.0 |
| LICENSE_PLATE (73) | 0.0 (0.9) | 0.0 | 0.0 | 0.0 |
| PHONE (247) | 0.0 (0.2) | 0.0 | 5.0 | 6.0 |
| SOCIAL_SECURITY (12) | 0.0 (0.0) | 0.0 | 0.0 | 0.0 |
| VAT_NUMBER (14) | 0.0 (0.0) | 0.0 | 0.0 | 0.0 |

### Held-out results by genre (lenient F1 / leak / FP on negatives)

| Genre | `pseudora_generic_professional` | `pseudora_generic_professional_maximum` | `ablation_regex_presidio` | `rizzo_pii_only` |
|---|---|---|---|---|
| chat | 89.6 / 11.1 / 7.8 | 89.4 / 10.4 / 7.8 | 85.9 / 19.7 / 2.0 | 68.2 / 10.1 / 25.5 |
| free_text | 76.0 / 18.4 / 8.5 | 75.8 / 17.9 / 8.5 | 78.2 / 27.5 / 2.1 | 75.5 / 14.6 / 54.3 |
| hr_tax | 67.3 / 20.4 / 4.0 | 65.1 / 19.2 / 12.6 | 68.1 / 31.0 / 0.5 | 61.0 / 5.2 / 39.9 |
| legal | 80.0 / 22.7 / 14.2 | 79.7 / 22.4 / 14.8 | 80.6 / 29.9 / 10.2 | 80.6 / 11.0 / 51.1 |
| negative | – / – / 19.6 | – / – / 20.2 | – / – / 16.7 | – / – / 52.6 |
| real_estate_medical | 78.0 / 23.9 / 5.6 | 78.0 / 23.3 / 6.3 | 80.5 / 28.2 / 0.0 | 78.5 / 9.9 / 45.2 |
| structured | 82.6 / 12.4 / 11.9 | 81.8 / 12.2 / 16.6 | 81.0 / 20.2 / 3.6 | 80.1 / 6.1 / 37.3 |

### Hard cases on the held-out set (lenient recall)

| Hard case (spans) | `pseudora_generic_professional` | `pseudora_generic_professional_maximum` | `ablation_regex_presidio` | `rizzo_pii_only` |
|---|---|---|---|---|
| urlencoded (15) | 6.7 | 6.7 | 0.0 | 0.0 |
| compact (41) | 9.8 | 9.8 | 0.0 | 22.0 |
| ocr_hyphen (15) | 40.0 | 40.0 | 26.7 | 60.0 |
| ocr_value (27) | 44.4 | 48.1 | 40.7 | 74.1 |
| uppercase (263) | 47.1 | 52.1 | 30.8 | 90.5 |
| ambiguous_word (148) | 75.7 | 77.7 | 64.9 | 87.2 |
| surname_only (289) | 76.8 | 78.9 | 54.7 | 95.8 |
| particle (273) | 77.3 | 77.7 | 71.1 | 91.2 |
| foreign (341) | 78.0 | 78.9 | 66.6 | 93.8 |
| uppercase_surname (69) | 78.3 | 79.7 | 71.0 | 97.1 |
| first_name_only (417) | 78.7 | 79.9 | 57.3 | 84.4 |
| obfuscated (10) | 80.0 | 80.0 | 0.0 | 60.0 |
| lowercase (186) | 81.2 | 81.7 | 76.9 | 95.7 |
| surname_first (90) | 84.4 | 84.4 | 71.1 | 97.8 |
| double_surname (109) | 87.2 | 86.2 | 76.1 | 91.7 |
| spaced (134) | 90.3 | 90.3 | 90.3 | 97.8 |
| initial (82) | 92.7 | 92.7 | 87.8 | 90.2 |
| city_first (29) | 100.0 | 100.0 | 100.0 | 100.0 |
| nickname (9) | 100.0 | 100.0 | 100.0 | 77.8 |
| pec (42) | 100.0 | 100.0 | 100.0 | 100.0 |

### Where `pseudora_generic_professional` still leaks: top 10 types by leaked tokens (excerpts; all data is fake)

⟦…⟧ marks the gold span; *full* = no token of it was masked, *partial* = some tokens were.

| Type (leaked tokens) | Document | Excerpt |
|---|---|---|
| PERSON (547) | `atto_citazione-003` (full) | …878/2022);⏎tutto ciò premesso, l'attore CITA ⟦GIANFRANCO LO PRESTI⟧ a comparire all'udienza del 11 giugno 2027 i… |
| PERSON (547) | `atto_citazione-003` (full) | … il contributo unificato di 36.171,75€.⏎Avv. ⟦I. Lo Russo⟧⏎ |
| INDIRECT (336) | `narrativa-007` (full) | …024/6557976 del 22/03/2024⏎Descrivo i fatti: ⟦la vedova dell'ex sindaco di Ancona⟧ riceve da tempo pagamenti in contanti dal fo… |
| INDIRECT (336) | `narrativa-012` (full) | …n. 236411/U del 18/07/2026⏎Descrivo i fatti: ⟦il magazziniere che a marzo ha avuto l'infarto sul muletto⟧ riceve da tempo pagamenti in contanti dal fo… |
| ADDRESS (201) | `atto_citazione-002` (partial) | … attore -⏎contro⏎Ivano Ferraro, residente in ⟦STRADA PROVINCIALE 22 45bis 06024 GUBBIO PG⟧, cod. fisc. FRRVNI71S14D883I⏎- convenuto -⏎P… |
| ADDRESS (201) | `atto_citazione-003` (partial) | … -⏎contro⏎Gianfranco Lo Presti, residente in ⟦Località Pian del Lago 20/A - 90144 - Palermo (PA)⟧, cod. fisc. LPRGFR50T25H501V⏎- convenuto -⏎P… |
| DATE_OF_BIRTH (168) | `atto_citazione-001` (full) | …er CUOMO Lorenzo (CMULNZ79H16F205P), nascita ⟦16-GIU-1979⟧ (Milano), elettivamente domiciliato presso l… |
| DATE_OF_BIRTH (168) | `atto_citazione-006` (full) | …LA SCOGNAMIGLIO (SCGGZL60L49E372G), n. Vasto ⟦09-LUG-1960⟧, elettivamente domiciliata presso lo studio … |
| BIRTH_PLACE (140) | `atto_citazione-001` (full) | …nzo (CMULNZ79H16F205P), nascita 16-GIU-1979 (⟦Milano⟧), elettivamente domiciliato presso lo studio… |
| BIRTH_PLACE (140) | `atto_citazione-002` (full) | … Marchetti (MRCGNN53D55D883B), originaria di ⟦Gallipoli⟧, dove è nata il 15/04/1953, elettivamente do… |
| EMPLOYEE_ID (82) | `busta_paga-001` (full) | …        Codice fiscale      ⏎Liv.  Qualifica⏎⟦12339⟧     Pellegatta Trombetta Rosa    PLLRSO90E58… |
| EMPLOYEE_ID (82) | `busta_paga-003` (full) | …        Codice fiscale       Liv.  Qualifica⏎⟦46240⟧     Rinaldi Ginevra    RNLGVR91M45H223G     … |
| EMAIL (63) | `crm_csv-002` (full) | …fiscale;note;fatturato⏎C031767;Filippo;Sanna;⟦sanna71 [at] alice [dot] it⟧;3493240948;Viale delle Rimembranze 39bis;24/… |
| EMAIL (63) | `crm_csv-010` (full) | …EUR 32.573,24⏎C570550;Benedetta;Scognamiglio;⟦b.scognamiglio [at] libero [dot] it⟧;3395103123;Via del Lavoro n. 51bis, 61032 Fa… |
| CONTRACT_ID (59) | `json_api-002` (full) | …0", "appVersion": "8.26.21"},"loyaltyCard": "⟦FID6286783535⟧", "createdAt": "28 dicembre 2022"}⏎ |
| CONTRACT_ID (59) | `json_api-003` (full) | …, "appVersion": "8.7.99"},⏎  "loyaltyCard": "⟦FID4883554109⟧", "createdAt": "5 dicembre 2021"⏎}⏎ |
| FISCAL_CODE (40) | `cu-014` (full) | …LTRO PERCETTORE DELLE SOMME⏎1 CODICE FISCALE ⟦RVI BDT 93M63 E730Z⟧⏎2 COGNOME RIVA   3 NOME BENEDETTA   4 SESSO … |
| FISCAL_CODE (40) | `f24-004` (full) | …resso BPER Banca⏎CONTRIBUENTE⏎codice fiscale ⟦FBB SNT 70M62 F839J⟧⏎dati anagrafici: cognome , denominazione o r… |
| IP_ADDRESS (34) | `server_log-014` (full) | …th.LoginService - login ok user=c.pisu25 src=⟦2001:db8:2f87:376:53e6::117⟧ req=3bb1a1d01c17⏎2025-03-15T04:23:06Z DEBUG … |
| IP_ADDRESS (34) | `ticket-001` (full) | …e nel portale da ieri. il mio indirizzo IP è ⟦37.204.7.58⟧. codice cliente CL-4644417.⏎⏎--- Risposta op… |

### Near-misses most often masked by `pseudora_generic_professional` (should stay visible)

| Look-alike | Text | Times masked |
|---|---|---|
| PUBLIC_BODY | Cass. civ. | 14 |
| COMMON_WORD | Tizio | 14 |
| COMMON_WORD | Caio | 14 |
| ORG | ufficio.contenzioso@pec.inps.gov.it | 13 |
| COMMON_WORD | viale Giacomo Matteotti | 12 |
| DOC_DATE | 17 marzo 1861 | 12 |
| LAW_REF | art. 139 Cost. | 12 |
| ORG | Leroy Merlin | 10 |
| ORG | protocollo@pec.comune.fano.pu.it | 9 |
| ORG | Intesa Sanpaolo | 9 |
| COMMON_WORD | via Giuseppe Garibaldi | 9 |
| COMMON_WORD | largo Enrico Berlinguer | 8 |
<!-- heldout:end -->

Charts: [F1 with CIs](results/charts/f1_ci.svg) · [leak vs false masking](results/charts/leak_vs_fp.svg) ·
[recall by type](results/charts/recall_by_type.svg). Full per-system tables: [results/tables.md](results/tables.md).

## Gap analysis: where the remaining leaks are

Read with the per-type table and the excerpts above.

1. **ALL-CAPS and form-field names.** `PERSON` leaks 21% of tokens (4% on the original). Recall on
   uppercase names is 47% (Rizzo 91%). The worst cases are names after the verb "CITA" in an atto,
   all-caps forms (CU, F24, verbali typed in capitals), and surname and first name in separate fields
   ("Cognome RIVA  Nome BENEDETTA", CSV columns, JSON `firstName`/`lastName`).
2. **Birth place without the "nato a" cue.** `BIRTH_PLACE` leaks 48% (0% on the original). Typical
   misses: "Comune (o Stato estero) di nascita X", "nascita 16-GIU-1979 (Milano)", "originaria di
   Gallipoli, dove è nata il …". `DATE_OF_BIRTH` leaks 18%: month abbreviations ("09-LUG-1960"),
   compact `16061979`, and dates far from a cue word.
3. **Identifiers in table layouts.** `EMPLOYEE_ID` leaks 68%: matricole in a payslip row under a
   header line, spreadsheet cells. `CONTRACT_ID` leaks 50%: loyalty cards, claim numbers, POD codes.
   `CREDIT_CARD` leaks 33% (`pan=` in logs).
4. **Format variants of "solved" types.** Codice fiscale grouped 3-3-5-5 ("RVI BDT 93M63 E730Z"),
   e-mails written "nome [at] dominio [dot] it" or URL-encoded in query strings, IPv6 addresses, and
   an IP given in a lowercase sentence.
5. **Indirect identifiers** ("la vedova dell'ex sindaco di Ancona") leak 97%, as on the original.
   No system finds them without masking almost everything.
6. **False masking on near-misses** (19.6% of look-alikes in PII-free documents): legal placeholders
   ("Tizio", "Caio"), case-law citations ("Cass. civ."), eponymous streets ("viale Giacomo Matteotti"),
   historical dates after "nata il" ("17 marzo 1861"), and institutional PEC addresses. The 22 PEC
   addresses are a policy call: masking them is arguably fine, and they move the FP rate by under
   1 point.

## Recommendation

- **Default stays `balanced` with transformers on.** On held-out data they are worth about 7.5 points
  of leak (−30% relative) for about 270 ms per 1k characters. For a redaction product the leak is
  what matters.
- **Offer the regex+Presidio pipeline only as an explicit "fast" option** for high-volume,
  low-variety inputs such as logs and fixed exports. Document that it leaks about 1.4× more on
  unfamiliar text.
- **Stop quoting 3.9%.** Use the held-out numbers with their CIs, and keep `it_pii_v1` as a regression test.

## Next improvements (to be measured on a *new* held-out set, not this one)

1. Name detection robust to case: run ML on case-normalised text, or add a capitalised-token fallback
   gated by name lexicons. This is the largest single source of leaks.
2. Key/value and table awareness: map column headers and JSON/CSV keys (`Cognome`, `Nome`,
   `Matricola`, `firstName`, `birthPlace`, ...) to the cells under or after them.
3. Birth-data cues beyond "nato a": form labels ("Comune di nascita", "luogo e data di nascita"),
   parenthesised places, Italian month abbreviations.
4. Normalisation before regex: `[at]`/`[dot]`, `%40`, IPv6, alternative CF grouping, `pan=`/`card=` keys.
5. A short list of legal placeholders (Tizio/Caio/Sempronio) and case-law citation shapes for the precision filter.
6. Build `it_pii_heldout_v2` with different templates and, ideally, a human author, before measuring
   any of the above.


## Reproduce

```bash
python3 benchmark/italian_heldout/build.py --check          # corpus rebuilds byte-for-byte, hash matches FREEZE.md
python3 -m pytest benchmark/italian_heldout/tests -q
# re-score committed predictions (stdlib only), then regenerate tables and this README block
python3 benchmark/italian/score.py --dataset benchmark/italian_heldout/dataset/it_pii_heldout_v1.jsonl \
    --predictions benchmark/italian_heldout/results/predictions --out benchmark/italian_heldout/results/summary.json
python3 benchmark/italian/report.py --results benchmark/italian_heldout/results
python3 benchmark/italian_heldout/compare.py
# re-run the systems (Docker, engine image, pinned HF cache; Rizzo checkout + weights as in ../italian)
python3 benchmark/italian/run.py --image docjobs-engine:base --cache-volume docjobs-hf \
    --dataset benchmark/italian_heldout/dataset/it_pii_heldout_v1.jsonl --out benchmark/italian_heldout/results \
    --systems pseudora_generic_professional,pseudora_generic_professional_maximum,ablation_regex_presidio,ablation_regex,presidio_vanilla_it,rizzo_default,rizzo_pii_only \
    --rizzo-src ../rizzo-pii --rizzo-model-volume rizzo-models
```

CI re-scores the committed predictions and fails on any drift, as for the original benchmark.

## Rules for using this set

- **Do not tune on it.** Once an engine change is written after looking at these documents or at the
  leak excerpts above, this set stops being held-out for that change. Fix what it reveals with tests
  of your own, then build `it_pii_heldout_v2` (new templates, new seeds) to measure the fix.
- The data is synthetic and fake. Real documents will differ again; treat these numbers as a better
  estimate than `it_pii_v1`, not as production accuracy.
