"""Run a small, deterministic detector quality benchmark against /v1/detect."""
import argparse
import json
import sys
import time
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/detect")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--tenant", default="benchmark")
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "datasets/synthetic_v1.json"))
    parser.add_argument("--min-precision", type=float)
    parser.add_argument("--min-recall", type=float)
    parser.add_argument("--min-f1", type=float)
    parser.add_argument("--max-p95-ms", type=float)
    args = parser.parse_args()
    for name in ("min_precision", "min_recall", "min_f1"):
        value = getattr(args, name)
        if value is not None and not 0 <= value <= 1:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")
    if args.max_p95_ms is not None and args.max_p95_ms < 0:
        parser.error("--max-p95-ms must be non-negative")
    import httpx

    rows = json.loads(Path(args.dataset).read_text())
    tp = fp = fn = 0
    latencies = []
    with httpx.Client(timeout=60) as client:
        for row in rows:
            started = time.perf_counter()
            headers = {"X-Api-Key": args.api_key, "X-Pii-Tenant-Id": args.tenant}
            response = client.post(args.url, headers=headers, json={"text": row["text"], "language": "it"})
            response.raise_for_status()
            found = set(response.json().get("pii_types_found", []))
            expected = set(row["expected"])
            tp += len(found & expected)
            fp += len(found - expected)
            fn += len(expected - found)
            latencies.append((time.perf_counter() - started) * 1000)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    latencies.sort()
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
    result = {"samples": len(rows), "precision": precision, "recall": recall, "f1": f1, "p95_ms": p95}
    failures = []
    for name in ("precision", "recall", "f1"):
        threshold = getattr(args, f"min_{name}")
        if threshold is not None and result[name] < threshold:
            failures.append(f"{name}={result[name]:.4f} < {threshold:.4f}")
    if args.max_p95_ms is not None and p95 > args.max_p95_ms:
        failures.append(f"p95_ms={p95:.2f} > {args.max_p95_ms:.2f}")
    result["quality_gate"] = "failed" if failures else "passed"
    print(json.dumps(result, indent=2))
    if failures:
        print("Quality gate failed: " + "; ".join(failures), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
