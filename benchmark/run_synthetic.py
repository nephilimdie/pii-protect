"""Run a small, deterministic detector quality benchmark against /v1/detect."""
import argparse
import json
import time
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/detect")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--tenant", default="benchmark")
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "datasets/synthetic_v1.json"))
    args = parser.parse_args()
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
    print(json.dumps({"samples": len(rows), "precision": precision, "recall": recall, "f1": f1, "p95_ms": p95}, indent=2))


if __name__ == "__main__":
    main()
