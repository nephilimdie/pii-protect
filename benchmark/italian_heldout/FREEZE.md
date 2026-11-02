# Freeze record: `it_pii_heldout_v1`

- File: `dataset/it_pii_heldout_v1.jsonl` (442 documents: 342 with PII, 100 PII-free near-miss documents)
- sha256: `5475196bb27964832b3aae55a46059e282e4c0afd687698f111bedd53ac2cc59`
- Frozen: 2026-11-02, committed on branch `feat/heldout-benchmark` **before any system was run on it**.
  `tests/test_heldout.py` and CI fail if the file or its hash changes.

## How the corpus was written

1. **Own code, own data.** `fakedata.py`, `markup.py` and the three `templates_*.py` files were written
   from scratch. Nothing is imported from `benchmark/italian/` (no shared name/place pools, no shared
   code generators, no shared noise model). The checksum algorithms (codice fiscale, IBAN mod-97, Luhn)
   are the public ones, re-implemented.
2. **Hand-authored templates, different layouts.** 24 document types written from memory of real
   paperwork: PEC e-mails, condominium and traffic-police *verbali*, *atti di citazione*, *ricorsi*
   (Giudice di Pace, labour court), payslips, Certificazione Unica, F24, lease contracts, medical-legal
   and property appraisals, medical reports, WhatsApp transcripts, CRM CSV exports, server logs,
   JSON API payloads, spreadsheets pasted as text, mixed Italian/English mail and Slack, letters,
   whistleblowing reports, helpdesk tickets; plus 7 near-miss types with no personal data.
3. **Different distributions.** ~22% foreign-born people (Romanian, Albanian, Moroccan, Chinese,
   Ukrainian, Senegalese, Peruvian, Indian, Filipino, ...), double surnames, particles (De, Lo,
   Dell'...), compound first names, nicknames in chats, surname-only and first-name-only fields
   (CU, F24, CSV columns, JSON keys), all-caps forms, lowercase typing, URL-encoded and obfuscated
   e-mails, foreign IBANs and phones, birth data phrased date-first or as key/value.
4. **Own noise model.** Scanner-like noise on ~11% of documents: hyphenated line breaks inside
   words, hard wraps at ~66 columns, B/8 G/6 Z/2 S/$ confusions, ri->n, accent splitting
   (à -> a'), spaces before punctuation, page furniture lines.
5. **Gold.** Offsets are recorded while each document is rendered from inline markup, after noise,
   and asserted against the text. Schema identical to `it_pii_v1` (`entities`, `negatives`,
   `ignore`, `hard` tags). All data is fake.

## Independence statement

- **No detection-sprint rule was written against this set.** The corpus did not exist when the
  sprint (engine 42274b7) was tuned, and it was frozen before any system, Pseudora or otherwise,
  processed it. No engine code is changed on this branch.
- The author did **not** read the engine's recognizers/precision filter or the original generator's
  templates (`benchmark/italian/templates.py`, `itdata.py`) while writing it. The author did read the
  original schema/scorer (`gold.py`, `score.py`, `taxonomy.json`) to keep the gold format and
  span conventions compatible; `gold.py` shows a handful of the original surface forms, which were
  deliberately not copied.
- **Limitation:** the author is an AI agent of the same family that wrote `it_pii_v1` and the sprint
  rules, so "independent" means independent code, data, layouts and no tuning, not an independent
  human annotator team. Shared intuitions about Italian documents are possible.
