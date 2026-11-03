# Freeze record: `it_pii_heldout_v2` (TEST set of detection sprint 2)

- File: `dataset/it_pii_heldout_v2.jsonl` (426 documents: 326 with PII, 100 PII-free near-miss documents)
- sha256: `eff917aaea0d7fe833fcc8989e6d3ef5739ecd1347c44a1c3ad49d720640288d`
- Frozen: 2026-11-02, committed on branch `feat/detection-sprint-2` **before any model was trained, any rule
  was tuned, or any system (Pseudora, Rizzo-PII, Presidio) was run on it**. `tests/test_v2.py` fails if the
  file or its hash changes.

## Role in the evaluation protocol

| Set | Use |
|---|---|
| `benchmark/italian` `it_pii_v1` (750 docs) | DEV: error analysis allowed |
| `benchmark/italian_heldout` `it_pii_heldout_v1` (442 docs) | DEV: error analysis allowed from sprint 2 on |
| **`it_pii_heldout_v2` (this, 426 docs)** | **TEST: final measurement only.** No error analysis, no tuning, never used as training data |

## How it differs from the two DEV corpora

1. **Own code, own pools.** `ident.py`, `builder.py`, `snippets.py` and the four `genres_*.py` files import
   nothing from `benchmark/italian*`. First names, surnames, foreign nationalities (Bangladesh, Sri Lanka,
   Pakistan, Poland, Moldova, Tunisia, Ecuador, Nigeria, Egypt, Brazil, Georgia) and towns are disjoint from
   both DEV pools. The test checks this.
2. **Different authoring approach.** v1 renders inline markup strings. v2 appends text piece by piece
   through a builder that records each span at append time, after noise.
3. **Different genres.** Notarial deeds, self-certifications (DPR 445), FOIA-style access requests, family
   status certificates, payment orders, civil judgments, union settlements, insurance CAI forms,
   hospital discharge letters, SSN prescriptions, bank statements, AML questionnaires, CVs, HR letters,
   school forms, speech-to-text dictations, quoted e-mail threads, Telegram chats, forum posts, issue
   tickets, FatturaPA XML, vCard/iCal, SQL dumps, YAML/INI configs, fixed-width and markdown tables.
   Near-miss: textbook placeholders (Tizio/Caio/Sempronio), case-law digests, eponymous street notices,
   historical figures, part catalogues/firmware codes, statistics, public tenders (CIG/CUP), sport/weather.
4. **Different noise.** On 34 documents: noise like a PDF text layer (ligatures ﬁ/ﬂ/ﬀ/ﬃ, NBSP, soft hyphens, curly
   apostrophes, justified double spaces, court line numbers, "Pag. x di y" furniture, O/0 and I/1 swaps in
   codes). Some documents are fully upper-case. Dictations are lower-case with spoken numbers and spoken e-mails.
5. **Gold.** Schema, taxonomy and matching rules are those of [`benchmark/italian`](../italian/README.md),
   so `benchmark/italian/score.py` scores it unchanged.

## Independence statement and limits

- Written before any sprint-2 change. The author did not consult the engine recognizers or the precision
  filter while writing it. The author knew the held-out v1 error categories (ALL-CAPS names, birth place
  without "nato a", table identifiers, month abbreviations, grouped CF, obfuscated e-mails, IPv6), and they
  appear here at natural rates as ordinary real-world forms. They are not over-represented as targets.
- Same limit as v1: the author is an AI agent of the same family that wrote the DEV corpora and the rules.
