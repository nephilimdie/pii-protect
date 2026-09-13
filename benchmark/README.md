# Synthetic quality benchmark

`datasets/synthetic_v1.json` contains no real personal data. Run it against a
local or staging engine:

```bash
python benchmark/run_synthetic.py --url http://127.0.0.1:8000/v1/detect --api-key "$PII_API_KEY"
```

The runner reports precision, recall, F1 and p95 latency. It is a smoke
benchmark, not a certification: expand the dataset by language and document
type before using a quality threshold for a release. Store results with the
engine version, model versions and configuration that produced them.
