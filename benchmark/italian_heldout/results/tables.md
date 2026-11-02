Dataset `it_pii_heldout_v1.jsonl` · 442 documents · bootstrap 1000 resamples over documents · all values in %.

### Overall

| System | Strict F1 [95% CI] | Lenient P | Lenient R | Lenient F1 [95% CI] | Leak rate [95% CI] | FP on negatives [95% CI] | ms / 1k chars |
|---|---|---|---|---|---|---|---|
| `ablation_regex_presidio` | 67.5 [65.9, 69.2] | 85.8 | 71.9 | **78.2** [76.8, 79.6] | 24.8 [23.2, 26.4] | 8.6 [7.3, 10.3] | 28.01 |
| `pseudora_generic_professional` | 65.5 [63.8, 67.3] | 78.0 | 78.4 | **78.2** [76.5, 79.8] | 17.3 [15.8, 19.0] | 13.2 [11.5, 15.0] | 301.0 |
| `pseudora_generic_professional_maximum` | 64.5 [62.8, 66.2] | 76.4 | 79.0 | **77.7** [76.1, 79.2] | 16.9 [15.4, 18.5] | 15.6 [13.8, 17.4] | 297.43 |
| `rizzo_pii_only` | 50.7 [48.9, 52.4] | 59.0 | 87.9 | **70.6** [68.3, 72.7] | 8.8 [7.4, 10.2] | 46.8 [45.0, 48.7] | 228.52 |
| `pseudora_presprint_generic_professional` | 53.4 [51.5, 55.3] | 71.1 | 68.9 | **70.0** [68.3, 71.5] | 31.5 [29.8, 33.2] | 16.7 [14.8, 18.6] | 289.58 |
| `ablation_regex` | 60.9 [59.0, 62.8] | 91.5 | 53.8 | **67.7** [65.8, 69.6] | 38.3 [36.1, 40.5] | 3.2 [2.4, 3.9] | 8.82 |
| `rizzo_default` | 46.3 [44.6, 48.0] | 51.5 | 87.8 | **64.9** [62.6, 67.0] | 8.5 [7.2, 10.0] | 77.7 [75.7, 79.5] | 283.32 |
| `presidio_vanilla_it` | 44.1 [42.6, 45.5] | 50.6 | 67.6 | **57.9** [56.3, 59.3] | 31.4 [29.7, 33.1] | 28.7 [26.8, 30.7] | 18.02 |

### Difference vs `pseudora_generic_professional` (paired bootstrap, 95% CI; positive leak delta = leaks more)

| System | Δ strict F1 | Δ lenient F1 | Δ leak rate |
|---|---|---|---|
| `ablation_regex_presidio` | [1.1, 2.8] | [-0.9, 1.0] | [6.6, 8.3] |
| `pseudora_generic_professional_maximum` | [-1.4, -0.7] | [-0.8, -0.2] | [-0.6, -0.3] |
| `rizzo_pii_only` | [-17.3, -12.3] | [-9.3, -6.0] | [-10.0, -7.2] |
| `pseudora_presprint_generic_professional` | [-13.6, -10.8] | [-9.2, -7.2] | [12.6, 15.7] |
| `ablation_regex` | [-6.7, -2.7] | [-12.2, -8.6] | [19.2, 22.7] |
| `rizzo_default` | [-21.4, -16.9] | [-14.8, -11.8] | [-10.2, -7.4] |
| `presidio_vanilla_it` | [-23.0, -20.1] | [-21.7, -19.0] | [12.3, 15.8] |

### Lenient recall by entity type (leak rate in parentheses)

| Type (gold spans) | `pseudora_generic_professional` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|
| PERSON (1415) | 80.1 (21.2) | 64.6 (35.5) | 64.8 (27.8) | 92.7 (7.1) |
| FISCAL_CODE (380) | 97.1 (7.8) | 97.1 (8.0) | 87.9 (30.3) | 99.2 (6.4) |
| DATE_OF_BIRTH (336) | 74.1 (18.1) | 67.0 (25.1) | 63.4 (27.1) | 89.9 (0.3) |
| ADDRESS (319) | 99.7 (10.1) | 99.4 (17.0) | 81.8 (48.0) | 100.0 (3.4) |
| EMAIL (254) | 93.7 (6.8) | 90.2 (11.3) | 90.2 (7.7) | 92.5 (5.3) |
| PHONE (247) | 100.0 (0.0) | 98.4 (5.0) | 78.5 (14.9) | 93.5 (6.0) |
| BIRTH_PLACE (209) | 21.1 (48.4) | 21.1 (68.9) | 79.9 (17.3) | 93.3 (4.8) |
| IBAN (198) | 82.8 (2.9) | 82.8 (2.9) | 98.5 (2.7) | 100.0 (0.0) |
| EMPLOYEE_ID (117) | 8.5 (67.8) | 8.5 (74.4) | 0.0 (78.5) | 14.5 (8.3) |
| CONTRACT_ID (77) | 27.3 (50.4) | 27.3 (49.6) | 0.0 (87.2) | 7.8 (12.8) |
| ID_DOCUMENT (77) | 93.5 (6.5) | 93.5 (6.5) | 66.2 (32.5) | 75.3 (2.6) |
| LICENSE_PLATE (73) | 97.3 (0.0) | 97.3 (0.0) | 0.0 (79.5) | 100.0 (0.0) |
| IP_ADDRESS (67) | 86.6 (11.8) | 88.1 (9.7) | 100.0 (2.8) | 85.1 (20.8) |
| USERNAME (59) | 44.1 (10.3) | 44.1 (57.7) | 0.0 (81.4) | 0.0 (86.6) |
| INDIRECT (42) | 16.7 (96.8) | 2.4 (99.7) | 47.6 (91.4) | 52.4 (89.0) |
| CADASTRAL_REF (27) | 88.9 (15.7) | 88.9 (15.7) | 0.0 (90.4) | 100.0 (4.8) |
| CREDIT_CARD (21) | 71.4 (33.3) | 95.2 (7.4) | 100.0 (0.0) | 100.0 (0.0) |
| CASE_ID (20) | 100.0 (0.0) | 100.0 (0.0) | 0.0 (100.0) | 100.0 (0.0) |
| VAT_NUMBER (14) | 100.0 (0.0) | 100.0 (0.0) | 78.6 (21.4) | 100.0 (0.0) |
| SOCIAL_SECURITY (12) | 58.3 (0.0) | 58.3 (0.0) | 0.0 (41.7) | 0.0 (0.0) |

### Lenient F1 by genre (FP rate on negative look-alikes in parentheses)

| Genre | `pseudora_generic_professional` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|
| chat | 89.6 (7.8) | 85.9 (2.0) | 69.6 (25.5) | 68.2 (25.5) |
| free_text | 76.0 (8.5) | 78.2 (2.1) | 62.5 (35.1) | 75.5 (54.3) |
| hr_tax | 67.3 (4.0) | 68.1 (0.5) | 48.2 (14.3) | 61.0 (39.9) |
| legal | 80.0 (14.2) | 80.6 (10.2) | 61.9 (35.1) | 80.6 (51.1) |
| negative | – (19.6) | – (16.7) | – (34.0) | – (52.6) |
| real_estate_medical | 78.0 (5.6) | 80.5 (0.0) | 57.5 (29.0) | 78.5 (45.2) |
| structured | 82.6 (11.9) | 81.0 (3.6) | 63.8 (21.3) | 80.1 (37.3) |

### Negative look-alikes wrongly masked (lower is better)

| Look-alike (spans) | `pseudora_generic_professional` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|
| CODE (570) | 10.5 | 4.2 | 14.7 | 61.1 |
| COMMON_WORD (133) | 68.4 | 68.4 | 72.9 | 66.2 |
| DOC_DATE (461) | 3.0 | 3.0 | 64.2 | 100.0 |
| DOC_NUMBER (324) | 11.1 | 9.6 | 33.6 | 96.0 |
| LAW_REF (297) | 9.1 | 7.7 | 26.9 | 7.7 |
| MONEY (704) | 4.4 | 1.1 | 4.3 | 0.7 |
| ORG (335) | 28.4 | 15.5 | 24.5 | 25.4 |
| PUBLIC_BODY (156) | 25.6 | 9.0 | 49.4 | 46.8 |

Documents with no PII at all that got at least one mask: `pseudora_generic_professional` 80.0, `ablation_regex_presidio` 74.0, `presidio_vanilla_it` 100.0, `rizzo_pii_only` 100.0.

### Hard cases (lenient recall)

| Hard case (spans) | `pseudora_generic_professional` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|
| first_name_only (417) | 78.7 | 57.3 | 60.9 | 84.4 |
| foreign (341) | 78.0 | 66.6 | 74.5 | 93.8 |
| surname_only (289) | 76.8 | 54.7 | 52.6 | 95.8 |
| particle (273) | 77.3 | 71.1 | 72.9 | 91.2 |
| uppercase (263) | 47.1 | 30.8 | 25.5 | 90.5 |
| lowercase (186) | 81.2 | 76.9 | 76.3 | 95.7 |
| ambiguous_word (148) | 75.7 | 64.9 | 62.2 | 87.2 |
| spaced (134) | 90.3 | 90.3 | 64.9 | 97.8 |
| double_surname (109) | 87.2 | 76.1 | 78.0 | 91.7 |
| surname_first (90) | 84.4 | 71.1 | 80.0 | 97.8 |
| initial (82) | 92.7 | 87.8 | 86.6 | 90.2 |
| uppercase_surname (69) | 78.3 | 71.0 | 62.3 | 97.1 |
| pec (42) | 100.0 | 100.0 | 100.0 | 100.0 |
| compact (41) | 9.8 | 0.0 | 0.0 | 22.0 |
| city_first (29) | 100.0 | 100.0 | 100.0 | 100.0 |
| ocr_value (27) | 44.4 | 40.7 | 48.1 | 74.1 |
| ocr_hyphen (15) | 40.0 | 26.7 | 46.7 | 60.0 |
| urlencoded (15) | 6.7 | 0.0 | 0.0 | 0.0 |
| obfuscated (10) | 80.0 | 0.0 | 0.0 | 60.0 |
| nickname (9) | 100.0 | 100.0 | 100.0 | 77.8 |
