# Synthetic quality benchmark

`datasets/synthetic_v1.json` contains no real personal data. Run it against a
local or staging engine:

```bash
python benchmark/run_synthetic.py --url http://127.0.0.1:8000/v1/detect --api-key "$PII_API_KEY"
```

The runner reports precision, recall, F1 and p95 latency. For a release gate,
provide explicit thresholds; a failed threshold exits with status 1:

```bash
python benchmark/run_synthetic.py \
  --url http://127.0.0.1:8000/v1/detect \
  --api-key "$PII_API_KEY" \
  --min-precision 0.90 \
  --min-recall 0.90 \
  --min-f1 0.90 \
  --max-p95-ms 1000
```

This is still a smoke benchmark, not a certification. Thresholds must be
approved per dataset, language and document type; do not use the Italian
synthetic set as evidence for other languages. Store results with the engine
version, model versions and configuration that produced them.
