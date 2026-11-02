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
