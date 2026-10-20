# Real engine evaluation

`app.reporting.benchmark` is a historical demo-regex fixture, NOT an engine
accuracy measurement. `run_synthetic.py` exercises HTTP but counts entity types,
not individual spans; finding one email can hide a second missed email.

`evaluate.py` measures actual `/v1/detect` responses against annotated spans:
exact type, start and end, with one-to-one occurrence accounting. Duplicates are
false positives. HTTP failures fail the run rather than disappearing from scores.
Reports include per-type metrics, missing/unexpected offsets and observed latency.
No original text or credentials are included in reports.

## Local isolated run

Build an engine image and populate its model cache first, then run:

```sh
make benchmark-engine ENGINE_IMAGE=your-local-engine-image MODEL_CACHE_VOLUME=your-model-cache
```

This uses current API source with an existing image, an ephemeral PostgreSQL 17
database, random credentials, localhost only and offline model loading. No Cloud,
Redis, UI, production data or third-party LLM is required. The cache is reused,
not removed; ONNX files may be materialized there. Temporary containers/network
are removed on success and failure. The configured port must be free.

Result: `benchmark/results/engine-local.json` (ignored by Git).
Default minimum F1: 0.90. Override explicitly via the underlying script:

```sh
python3 scripts/check-engine-local.py --image your-local-engine-image \
  --cache-volume your-model-cache --benchmark-output /tmp/engine-results.json \
  --min-f1 0.95 --port 15679
```

The script requires Presidio, Privacy Filter and AI4Privacy to load successfully;
readiness alone is not evidence that every optional model is loaded.

## What the dataset means

`engine_spans_v1.json` contains 14 synthetic IT/EN regression examples. It includes
negative examples, repeated entity types, Unicode, JSON, CRLF, and PII near the end
of lines longer than a transformer context window. Annotation offsets use Python
Unicode string indexes, matching the engine, not byte or JavaScript UTF-16 indexes.

This is intentionally a small regression corpus, NOT an independent representative
evaluation. Never market its F1 as overall product accuracy. Do not tune individual
names or phrases into regexes to make this corpus pass.

Next quality milestone: independently annotated holdout data for each supported
language/domain, addresses, phone numbers, secrets, ambiguous negatives, boundary
crossing entities, noisy OCR and policies. Report exact-span and protection coverage
separately; a wider redaction may protect the value but still fail exact-span scoring.

Latency here is measured on sequential warm requests and mixed text lengths. With
14 requests, p95/p99 mostly describe the slowest example, not production capacity.
Concurrency and load tests remain separate from this quality test.

## Existing type-level HTTP smoke runner

The older `datasets/synthetic_v1.json` remains available and contains only
synthetic data. Its runner and CLI have not been removed:

```sh
python benchmark/run_synthetic.py --url http://127.0.0.1:8000/v1/detect \
  --api-key "$PII_API_KEY" --min-precision 0.90 --min-recall 0.90 \
  --min-f1 0.90 --max-p95-ms 1000 --max-p99-ms 1500
```

It measures type presence, not complete redaction or exact spans. Its thresholds
must be approved per dataset/language/document type; do not use it as evidence
for other languages. Its authentication must match the target deployment.
Use the isolated runner above for a self-contained local evaluation.

## Default behavior changed on 2026-10-11

Neural layers no longer skip texts shorter than 200 characters by default.
Existing database overrides of `min_chars` remain authoritative and are NOT
rewritten. Operators must review those overrides explicitly when rolling out.
Long lines now use overlapping model windows; input beyond 512 tokens is no longer
silently truncated by Privacy Filter. Model inference errors propagate to the
request failure policy. Use fail-closed in a protected outbound workflow.
