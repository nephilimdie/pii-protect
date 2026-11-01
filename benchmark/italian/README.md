# Italian PII detection benchmark (`it_pii_v1`)

A reproducible benchmark of Italian PII detection on synthetic documents. It compares
the Pseudora engine (full pipeline, every domain preset, layer ablations) with vanilla
Microsoft Presidio and the one other open-source Italian anonymizer we could run locally.
It was written to find out where we are weak, not to produce a marketing number. Read the
limitations section before quoting any figure.

## Results at a glance

| System | Lenient F1 [95% CI] | Strict F1 [95% CI] | Leak rate [95% CI] | FP on negatives [95% CI] | ms / 1k chars |
|---|---|---|---|---|---|
| Pseudora, `generic_professional` preset (reference) | 78.3 [77.2, 79.4] | 66.8 [65.6, 68.0] | 24.4 [23.1, 25.8] | 15.6 [14.2, 17.1] | 331 |
| Pseudora, preset matched to genre | 78.1 [77.0, 79.1] | 66.4 [65.3, 67.6] | 25.8 [24.4, 27.1] | 12.9 [11.6, 14.2] | 323 |
| Ablation: regex+checksum + Presidio/spaCy only | 78.2 [77.2, 79.2] | 68.5 [67.3, 69.7] | 37.6 [36.0, 39.0] | 4.6 [3.8, 5.3] | 33 |
| Vanilla Presidio, Italian spaCy | 67.5 [66.5, 68.5] | 52.3 [51.3, 53.3] | 25.0 [23.9, 26.2] | 25.3 [23.6, 27.0] | 18 |
| Rizzo-PII, `pii_only` config | **81.5** [80.3, 82.6] | 59.8 [58.7, 60.9] | **4.0** [3.4, 4.7] | 46.6 [44.6, 48.6] | 215 |

All values are percentages. The leak rate is the share of gold PII word tokens left unmasked,
whatever label the system used: lower is better, and it is the number that matters most for
a redaction product. "FP on negatives" is the share of non-PII look-alikes (dates of a document,
amounts, law references, protocol numbers, company names, public bodies) that got masked: lower
is better. The full tables, with every system and breakdowns by type, genre and hard case, are
[below](#full-results).

![Lenient F1 by system with 95% CI](results/charts/f1_ci.svg)
![Leak rate vs FP rate on negative look-alikes](results/charts/leak_vs_fp.svg)
![Lenient recall by entity type](results/charts/recall_by_type.svg)

## Where Pseudora loses

- **Leakage: Rizzo-PII leaks about six times less.** It leaves 4.0% of PII tokens unmasked;
  we leave 24.4%. The paired-bootstrap difference is −21.6 to −19.1 points. It also has the
  higher lenient F1, by 1.9 to 4.5 points. We are ahead on strict F1 (exact boundaries), on
  latency, and especially on false masking: it masks 47% of negative look-alikes and every
  document date. On recall, though, it is clearly ahead.
- **Dates of birth (39% recall, 61% leak) and places of birth (23%).** The engine does not
  separate a date of birth from the document's other dates. Rizzo reaches 99.7% recall here,
  but only because it masks all dates (100% of `DOC_DATE` negatives).
- **IP addresses: 0% recall, 100% leak.** No layer emitted an IP span in this run. Vanilla
  Presidio and Rizzo both find 100%.
- **Court case numbers (`CASE_ID`): 0% recall, 99% leak.** Contract IDs are at 39%, licence
  plates at 66% and ID documents at 79%.
- **Usernames** are masked (14% leak), but 93 of 110 carry the `PERSON` label. Strict and
  lenient type-aware recall therefore show close to 0%.
- **Hard cases:** values split by spaces or hyphens (64% recall), OCR-damaged values (71%) and
  indirect identifiers ("the tenant on the third floor", 7%). Rizzo scores 100%, 91% and 93%
  on these. The `logs_json` genre is our weakest (lenient F1 68.4).
- **Domain presets do not help on their own genres.** The "matched" setup gives each document
  the preset a user would pick for it. It is not better than `generic_professional`: lenient
  F1 changes by −0.5 to 0.0, and the leak rate gets 1.0 to 1.8 points worse. The `medical`,
  `fine_appeal`, `contract_analysis`, `condominio` and `default` presets are 5 to 10 points
  of lenient F1 below generic on this mixed corpus. That is partly by design, since they keep
  more types visible.
- **The transformers buy recall, not F1.** Regex+checksum with Presidio/spaCy alone matches
  the full pipeline's lenient F1 (difference −0.7 to +0.6) at about one tenth of the latency.
  It leaks 12 to 14 points more and masks fewer look-alikes. Of the two transformer layers,
  `ai4privacy` alone is weak on Italian (lenient recall 20%).
- **Latency is not a strength.** We take 320–1,070 ms per 1k characters on a 6-CPU Docker VM
  without a GPU, against 18 ms for vanilla Presidio and about 215 ms for Rizzo. The
  `default`, `hr_payroll`, `tax_accounting` and `real_estate_insurance` runs were 2.4 to 3.4
  times slower than the other presets. We have not explained that yet, so treat latency as
  indicative only.

## Systems

| Id | What it is | How it was run |
|---|---|---|
| `pseudora_<preset>` | Full engine pipeline (regex+checksum, Presidio/spaCy, privacy-filter and ai4privacy transformers, merger, denylist, snapping) with one of the 9 domain presets | Engine HTTP `/v1/anonymize` with `dry_run`, ephemeral PostgreSQL. The current `api/` source is mounted read-only, models load offline, and all detector layers must report ready. Only masked spans are scored. |
| `pseudora_matched` | Same pipeline; each document uses the preset a user would choose for its genre (no litigation preset exists, so court documents use `generic_professional`) | as above |
| `ablation_<layers>` | `generic_professional` policy with detection limited to the listed layers (`context_types.detection_layers`) | as above |
| `presidio_vanilla_it` | Microsoft Presidio `AnalyzerEngine` with `it_core_news_lg`, default recognizers and threshold. Every result counts as masked. | inside the engine image |
| `rizzo_default`, `rizzo_pii_only` | [Rizzo-AI-Academy/rizzo-pii](https://github.com/Rizzo-AI-Academy/rizzo-pii) (MIT) at `9057eeff`, model `rizzoaiacademy/rizzo-pii-0.3B` rev `a1c3c838`, through its own `analyze()`. `default` excludes AGE and GENDER; `pii_only` also excludes AMOUNT and ORG (the app's own setting). | inside the engine image, upstream code unchanged |

**Not tested**, with the reason:

- **Cloud APIs** (AWS Comprehend, Google Cloud DLP, Azure AI Language PII, Private AI,
  Nightfall): they are not locally runnable, they would need sending the corpus to a third
  party, and some terms restrict publishing benchmarks.
- **GLiNER PII models** (e.g. `urchade/gliner_multi_pii-v1`, Apache-2.0): they could run
  locally but were not included in this iteration. This is the first follow-up.
- **spaCy `it_core_news_lg` NER alone**: covered in practice by `ablation_presidio` and
  `presidio_vanilla_it`, which wrap it.
- **Italian anonymizers without released code or weights, or with a non-commercial or unclear
  licence**: we did not run them. We only benchmark tools we can legally run and redistribute
  results for.

## Dataset

`dataset/it_pii_v1.jsonl` has **750 synthetic documents** (279k characters). It is generated
deterministically by `generate.py` (seed `20261026`, SHA-256 `1466a601…`) and released under
CC BY 4.0 (`dataset/LICENSE.md`).

- **Genres:** legal 150 (citazioni, sentenze, procure, ricorsi, contratti di locazione), HR 100,
  tax 100, real estate / insurance 100, email and support tickets 85, chat / LLM prompts 90,
  logs and JSON 70, and 55 documents that contain no PII at all. 60 documents carry simulated
  OCR noise.
- **4,600 gold PII spans in 20 types:** PERSON 1,399, FISCAL_CODE 537, ADDRESS 398, EMAIL 385,
  DATE_OF_BIRTH 321, BIRTH_PLACE 272, PHONE 260, IBAN 168, ID_DOCUMENT 110, USERNAME 110,
  LICENSE_PLATE 100, CADASTRAL_REF 82, CASE_ID 79, CONTRACT_ID 74, IP_ADDRESS 70,
  SOCIAL_SECURITY 56, EMPLOYEE_ID 50, VAT_NUMBER 50, CREDIT_CARD 50, INDIRECT 29.
  Identifiers are checksum-valid (codice fiscale with omocodia, IBAN, partita IVA, Luhn).
- **2,766 negative look-alike spans** that must not be masked: document dates 682, amounts 636,
  law references 446, protocol and document numbers 334, codes 273, companies 185, public
  bodies 175, common words that are also surnames 35.
- **Tagged hard cases:** lowercase names, uppercase surnames, surname-first order, foreign
  names, ambiguous words (Rosa, Bianco…), initials, spaced or hyphenated values, OCR-damaged
  values, PEC addresses, abbreviations, rural addresses, omocodia, nicknames, indirect
  identifiers.

## Metrics

- **Strict:** exact start and end with a compatible type, matched one-to-one.
- **Lenient:** any overlap with a compatible type (recall per gold span, precision per
  predicted span).
- **Compatible types** are declared in `taxonomy.json`. Each system's labels are mapped to
  canonical types, and a generic class (e.g. `DATE`) is accepted for a finer gold type
  (`DATE_OF_BIRTH`).
- **Leak rate:** gold word tokens not fully covered by any masked span, whatever the label.
- **FP on negatives:** negative look-alike spans overlapped by any masked span.
- **Direct view:** `ci95_direct` in `summary.json` repeats the metrics with quasi-identifiers
  (BIRTH_PLACE, CASE_ID, CONTRACT_ID, CADASTRAL_REF, INDIRECT) treated as "ignore" regions. In
  that view Pseudora's lenient F1 is 81.9 and its leak rate 20.6; Rizzo's are 80.4 and 2.8.
- **Uncertainty:** 1,000 bootstrap resamples over documents. Every difference against the
  reference is paired (the same resample for both systems).
- **Latency:** wall-clock time per document over HTTP or the in-process call, summed and
  divided per 1k characters. It was measured on one machine (Docker VM with 6 CPUs and 8 GB,
  aarch64, no GPU), with systems run one after another.

## Reproduce

Scoring and charts need only Python 3.11 and the standard library. They are rebuilt from the
committed predictions, and CI does this on every PR and fails on any drift:

```bash
python3 benchmark/italian/score.py && python3 benchmark/italian/report.py
python3 -m pytest benchmark/italian/tests -q        # generator, scorer and report tests
python3 benchmark/italian/generate.py --check       # dataset regenerates byte-for-byte
```

Re-running every system needs Docker, the engine image built from `api/Dockerfile`, and a
Hugging Face cache volume holding the engine's pinned models (the same setup as
`scripts/check-engine-local.py`). The Rizzo-PII systems also need a checkout at the pinned
commit and a volume with the pinned weights:

```bash
python3 benchmark/italian/run.py --image docjobs-engine:base --cache-volume docjobs-hf \
    --rizzo-src ../rizzo-pii --rizzo-model-volume rizzo-models
# quick smoke run: first 2 documents of each sub-genre, written to results-subset/
python3 benchmark/italian/run.py --image docjobs-engine:base --cache-volume docjobs-hf \
    --subset 2 --systems pseudora_generic_professional,ablation_regex,presidio_vanilla_it
```

On the machine described above the measured detection time for all 19 systems adds up to about 35 minutes, plus model loading. Every container uses a
`bench-it-<random>` prefix and is removed when the run ends.

## Limitations

- **The data is synthetic.** The templates were written by the same team that builds the
  engine. Even though the gold spans were fixed before any system was run, the corpus is
  likely to favour patterns we already thought of. Real documents will be messier, and the
  absolute numbers will probably be lower for every system.
- **Label mapping matters.** Strict and lenient F1 depend on `taxonomy.json`. The leak rate
  does not, which is why it is shown next to F1.
- **No production traffic or GPU.** The engine ran with production code and models but on a
  laptop-class Docker VM. Latency on production hardware will differ.
- **The two external tools were run with their published defaults.** Neither was tuned. Rizzo's
  `pii_only` setting comes from its own UI. Our presets are the ones we ship.
- **The FP rate on negatives depends on what we call a look-alike.** For example, Rizzo masks
  every date by design, which some users want.

## Full results

<!-- results:start -->
Dataset `it_pii_v1.jsonl` · 750 documents · bootstrap 1000 resamples over documents · all values in %.

### Overall

| System | Strict F1 [95% CI] | Lenient P | Lenient R | Lenient F1 [95% CI] | Leak rate [95% CI] | FP on negatives [95% CI] | ms / 1k chars |
|---|---|---|---|---|---|---|---|
| `rizzo_pii_only` | 59.8 [58.7, 60.9] | 71.9 | 93.9 | **81.5** [80.3, 82.6] | 4.0 [3.4, 4.7] | 46.6 [44.6, 48.6] | 214.89 |
| `pseudora_generic_professional` | 66.8 [65.6, 68.0] | 78.6 | 78.0 | **78.3** [77.2, 79.4] | 24.4 [23.1, 25.8] | 15.6 [14.2, 17.1] | 330.99 |
| `ablation_regex_presidio` | 68.5 [67.3, 69.7] | 89.6 | 69.4 | **78.2** [77.2, 79.2] | 37.6 [36.0, 39.0] | 4.6 [3.8, 5.3] | 33.43 |
| `pseudora_real_estate_insurance` | 66.4 [65.3, 67.6] | 80.5 | 75.9 | **78.2** [77.1, 79.3] | 25.7 [24.3, 27.1] | 10.9 [9.8, 12.0] | 771.46 |
| `pseudora_matched` | 66.4 [65.3, 67.6] | 79.6 | 76.6 | **78.1** [77.0, 79.1] | 25.8 [24.4, 27.1] | 12.9 [11.6, 14.2] | 323.11 |
| `pseudora_hr_payroll` | 65.5 [64.3, 66.7] | 80.3 | 74.6 | **77.3** [76.2, 78.4] | 27.7 [26.2, 29.2] | 10.9 [9.8, 12.0] | 1064.31 |
| `rizzo_default` | 55.9 [54.8, 57.0] | 64.7 | 93.9 | **76.6** [75.3, 78.0] | 3.9 [3.2, 4.5] | 76.9 [74.8, 78.7] | 218.59 |
| `pseudora_tax_accounting` | 64.4 [63.3, 65.6] | 78.7 | 73.8 | **76.2** [75.1, 77.4] | 27.1 [25.7, 28.7] | 13.8 [12.4, 15.0] | 1071.57 |
| `pseudora_fine_appeal` | 60.1 [58.9, 61.4] | 78.6 | 67.2 | **72.4** [71.3, 73.7] | 34.3 [32.8, 35.9] | 10.9 [9.8, 12.0] | 316.58 |
| `pseudora_condominio` | 60.5 [59.2, 61.8] | 74.6 | 70.1 | **72.3** [71.1, 73.6] | 31.2 [29.7, 32.7] | 10.9 [9.8, 12.0] | 317.5 |
| `pseudora_contract_analysis` | 60.2 [59.0, 61.5] | 76.3 | 68.5 | **72.2** [71.0, 73.6] | 32.1 [30.6, 33.6] | 15.7 [14.6, 16.8] | 316.59 |
| `pseudora_default` | 59.6 [58.4, 61.0] | 71.6 | 70.7 | **71.1** [69.9, 72.5] | 30.8 [29.4, 32.3] | 17.6 [16.3, 18.9] | 976.03 |
| `ablation_no_regex` | 59.2 [57.9, 60.5] | 74.7 | 64.8 | **69.4** [68.3, 70.7] | 31.9 [30.2, 33.5] | 14.1 [12.8, 15.4] | 316.72 |
| `pseudora_medical` | 56.2 [54.8, 57.5] | 77.2 | 62.0 | **68.8** [67.4, 70.2] | 39.9 [38.0, 41.7] | 10.9 [9.8, 12.0] | 317.21 |
| `presidio_vanilla_it` | 52.3 [51.3, 53.3] | 59.2 | 78.5 | **67.5** [66.5, 68.5] | 25.0 [23.9, 26.2] | 25.3 [23.6, 27.0] | 17.72 |
| `ablation_regex` | 58.2 [56.9, 59.5] | 95.8 | 48.5 | **64.4** [63.0, 65.7] | 55.7 [54.2, 57.3] | 3.1 [2.5, 3.7] | 12.13 |
| `ablation_presidio` | 57.1 [55.9, 58.5] | 86.9 | 48.9 | **62.6** [61.6, 63.8] | 54.8 [53.4, 56.2] | 2.2 [1.7, 2.8] | 32.26 |
| `ablation_privacy_filter` | 47.8 [46.5, 49.3] | 74.3 | 47.5 | **58.0** [56.5, 59.5] | 45.1 [43.2, 46.9] | 10.9 [9.8, 12.0] | 292.49 |
| `ablation_ai4privacy` | 13.7 [12.2, 15.2] | 83.9 | 20.4 | **32.8** [31.1, 34.7] | 85.4 [84.2, 86.6] | 3.1 [2.5, 3.8] | 117.01 |

### Difference vs `pseudora_generic_professional` (paired bootstrap, 95% CI; positive leak delta = leaks more)

| System | Δ strict F1 | Δ lenient F1 | Δ leak rate |
|---|---|---|---|
| `rizzo_pii_only` | [-8.3, -5.7] | [1.9, 4.5] | [-21.6, -19.1] |
| `ablation_regex_presidio` | [1.0, 2.3] | [-0.7, 0.6] | [12.0, 14.3] |
| `pseudora_real_estate_insurance` | [-0.9, 0.1] | [-0.6, 0.3] | [0.9, 1.6] |
| `pseudora_matched` | [-0.7, -0.1] | [-0.5, 0.0] | [1.0, 1.8] |
| `pseudora_hr_payroll` | [-1.7, -1.0] | [-1.3, -0.6] | [2.8, 3.8] |
| `rizzo_default` | [-12.3, -9.6] | [-3.1, -0.2] | [-21.8, -19.3] |
| `pseudora_tax_accounting` | [-2.9, -1.9] | [-2.6, -1.6] | [2.2, 3.2] |
| `pseudora_fine_appeal` | [-7.3, -5.9] | [-6.5, -5.2] | [9.0, 10.8] |
| `pseudora_condominio` | [-7.0, -5.7] | [-6.7, -5.4] | [6.0, 7.6] |
| `pseudora_contract_analysis` | [-7.3, -5.9] | [-6.7, -5.5] | [6.9, 8.5] |
| `pseudora_default` | [-7.8, -6.5] | [-7.8, -6.5] | [5.6, 7.2] |
| `ablation_no_regex` | [-8.5, -6.7] | [-9.7, -8.1] | [6.5, 8.4] |
| `pseudora_medical` | [-11.6, -9.6] | [-10.4, -8.6] | [14.0, 16.9] |
| `presidio_vanilla_it` | [-15.8, -13.3] | [-12.1, -9.6] | [-0.7, 1.8] |
| `ablation_regex` | [-9.6, -7.6] | [-14.9, -12.8] | [30.1, 32.6] |
| `ablation_presidio` | [-10.7, -8.5] | [-16.6, -14.6] | [29.0, 31.6] |
| `ablation_privacy_filter` | [-20.3, -17.6] | [-21.6, -19.0] | [19.2, 22.2] |
| `ablation_ai4privacy` | [-54.8, -51.3] | [-47.5, -43.1] | [59.5, 62.5] |

### Lenient recall by entity type (leak rate in parentheses)

| Type (gold spans) | `pseudora_generic_professional` | `pseudora_matched` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|---|
| PERSON (1399) | 91.9 (9.9) | 91.9 (9.9) | 81.3 (20.2) | 85.1 (13.2) | 98.9 (1.8) |
| FISCAL_CODE (537) | 92.0 (17.2) | 92.0 (17.2) | 92.0 (15.8) | 92.4 (13.0) | 100.0 (0.0) |
| ADDRESS (398) | 92.0 (30.5) | 92.0 (30.5) | 54.5 (60.7) | 89.9 (44.3) | 100.0 (0.1) |
| EMAIL (385) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) |
| DATE_OF_BIRTH (321) | 39.3 (60.7) | 37.7 (62.3) | 26.5 (73.5) | 81.3 (18.7) | 99.7 (0.0) |
| BIRTH_PLACE (272) | 22.8 (50.4) | 22.8 (50.4) | 22.8 (77.2) | 93.0 (7.0) | 98.5 (1.5) |
| PHONE (260) | 98.5 (1.3) | 98.5 (1.3) | 77.7 (25.5) | 84.2 (13.6) | 98.5 (4.8) |
| IBAN (168) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) |
| ID_DOCUMENT (110) | 79.1 (26.9) | 63.6 (41.2) | 79.1 (26.1) | 73.6 (21.0) | 85.5 (1.7) |
| USERNAME (110) | 0.9 (14.0) | 0.9 (14.0) | 0.0 (97.8) | 0.0 (96.1) | 0.0 (100.0) |
| LICENSE_PLATE (100) | 66.0 (35.1) | 45.0 (55.1) | 66.0 (39.1) | 0.0 (83.1) | 100.0 (0.0) |
| CADASTRAL_REF (82) | 78.0 (17.5) | 48.8 (46.7) | 78.0 (21.5) | 0.0 (89.0) | 100.0 (0.0) |
| CASE_ID (79) | 0.0 (98.7) | 0.0 (98.7) | 0.0 (100.0) | 0.0 (98.7) | 100.0 (0.0) |
| CONTRACT_ID (74) | 39.2 (72.9) | 39.2 (72.9) | 39.2 (74.3) | 0.0 (58.6) | 44.6 (0.7) |
| IP_ADDRESS (70) | 0.0 (100.0) | 0.0 (100.0) | 0.0 (100.0) | 100.0 (0.0) | 100.0 (0.0) |
| SOCIAL_SECURITY (56) | 87.5 (0.0) | 87.5 (0.0) | 87.5 (0.0) | 0.0 (16.7) | 0.0 (32.1) |
| CREDIT_CARD (50) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) |
| EMPLOYEE_ID (50) | 96.0 (4.0) | 96.0 (4.0) | 96.0 (4.0) | 0.0 (98.0) | 38.0 (0.0) |
| VAT_NUMBER (50) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) | 100.0 (0.0) |
| INDIRECT (29) | 6.9 (98.6) | 6.9 (98.6) | 0.0 (100.0) | 96.6 (76.0) | 93.1 (76.4) |

### Lenient F1 by genre (FP rate on negative look-alikes in parentheses)

| Genre | `pseudora_generic_professional` | `pseudora_matched` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|---|
| chat_prompt | 84.3 (8.8) | 84.3 (8.8) | 80.5 (0.0) | 73.6 (37.5) | 91.9 (30.0) |
| email_ticket | 88.4 (16.0) | 88.4 (16.0) | 88.0 (0.0) | 75.1 (20.4) | 89.9 (36.0) |
| hr | 82.0 (13.9) | 83.3 (9.2) | 82.3 (7.4) | 61.4 (24.8) | 73.1 (37.9) |
| legal | 78.3 (16.1) | 75.4 (13.2) | 78.1 (1.0) | 72.6 (25.2) | 92.7 (41.7) |
| logs_json | 68.4 (10.6) | 68.4 (10.6) | 67.2 (0.8) | 61.6 (52.7) | 58.9 (84.9) |
| negative | – (13.0) | – (13.0) | – (7.2) | – (24.4) | – (45.9) |
| real_estate_insurance | 71.6 (16.3) | 73.3 (6.6) | 72.6 (6.9) | 62.6 (22.6) | 80.9 (49.1) |
| tax | 81.8 (24.0) | 82.3 (22.0) | 81.4 (6.5) | 70.6 (13.8) | 82.4 (46.8) |

### Negative look-alikes wrongly masked (lower is better)

| Look-alike (spans) | `pseudora_generic_professional` | `pseudora_matched` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|---|
| CODE (273) | 30.0 | 30.0 | 2.2 | 9.9 | 74.4 |
| COMMON_WORD (35) | 42.9 | 42.9 | 42.9 | 42.9 | 17.1 |
| DOC_DATE (682) | 2.8 | 2.8 | 0.0 | 65.7 | 100.0 |
| DOC_NUMBER (334) | 28.7 | 16.2 | 27.2 | 13.8 | 83.5 |
| LAW_REF (446) | 16.8 | 16.8 | 3.1 | 11.0 | 14.1 |
| MONEY (636) | 14.6 | 9.4 | 0.0 | 1.9 | 5.3 |
| ORG (185) | 12.4 | 12.4 | 0.0 | 43.8 | 0.0 |
| PUBLIC_BODY (175) | 16.6 | 16.6 | 0.0 | 13.1 | 12.6 |

Documents with no PII at all that got at least one mask: `pseudora_generic_professional` 70.9, `pseudora_matched` 70.9, `ablation_regex_presidio` 61.8, `presidio_vanilla_it` 94.5, `rizzo_pii_only` 100.0.

### Hard cases (lenient recall)

| Hard case (spans) | `pseudora_generic_professional` | `pseudora_matched` | `ablation_regex_presidio` | `presidio_vanilla_it` | `rizzo_pii_only` |
|---|---|---|---|---|---|
| lowercase (235) | 87.7 | 87.7 | 77.9 | 78.3 | 99.1 |
| uppercase_surname (185) | 81.6 | 81.6 | 65.4 | 73.5 | 100.0 |
| surname_first (160) | 90.6 | 90.6 | 87.5 | 91.2 | 99.4 |
| foreign (155) | 82.6 | 82.6 | 71.6 | 85.8 | 96.1 |
| ambiguous_word (124) | 83.9 | 83.9 | 72.6 | 75.0 | 96.0 |
| initial (111) | 99.1 | 99.1 | 93.7 | 92.8 | 91.9 |
| spaced (100) | 64.0 | 64.0 | 64.0 | 64.0 | 100.0 |
| ocr_value (89) | 70.8 | 70.8 | 61.8 | 70.8 | 91.0 |
| abbreviated (84) | 83.3 | 83.3 | 0.0 | 95.2 | 100.0 |
| pec (84) | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| uppercase (37) | 83.8 | 83.8 | 75.7 | 59.5 | 100.0 |
| rural (34) | 97.1 | 97.1 | 0.0 | 100.0 | 100.0 |
| indirect (29) | 6.9 | 6.9 | 0.0 | 96.6 | 93.1 |
| omocodia (29) | 96.6 | 96.6 | 96.6 | 96.6 | 100.0 |
| nickname (22) | 90.9 | 90.9 | 86.4 | 86.4 | 86.4 |
<!-- results:end -->
