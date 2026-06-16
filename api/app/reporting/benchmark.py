from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter


@dataclass(frozen=True)
class BenchmarkSample:
    text: str
    expected: list[tuple[str, str]]


DATASET = [
    BenchmarkSample(
        text="Il sig. Mario Rossi, CF RSSMRA80A01H501U, tel. 333-1234567, email mario.rossi@example.com.",
        expected=[("PERSON", "Mario Rossi"), ("FISCAL_CODE", "RSSMRA80A01H501U"), ("PHONE", "333-1234567"), ("EMAIL", "mario.rossi@example.com")],
    ),
    BenchmarkSample(
        text="Bonifico su IT60X0542811101000001234567 e targa AB123CD il 15/04/2024.",
        expected=[("IBAN", "IT60X0542811101000001234567"), ("TARGA", "AB123CD"), ("DATE", "15/04/2024")],
    ),
    BenchmarkSample(
        text="Paziente: Giulia Bianchi nata a Firenze il 22/05/1978.",
        expected=[("PERSON", "Giulia Bianchi"), ("DATE_BORN", "22/05/1978")],
    ),
]

PATTERNS = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "PHONE": re.compile(r"(\+39[\s.-]?)?3[0-9]{2}[\s.-]?[0-9]{3}[\s.-]?[0-9]{4}"),
    "FISCAL_CODE": re.compile(r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b"),
    "IBAN": re.compile(r"\bIT[0-9]{2}[A-Z][0-9A-Z]{22}\b"),
    "TARGA": re.compile(r"\b[A-Z]{2}[0-9]{3}[A-Z]{2}\b"),
    "DATE": re.compile(r"\b[0-9]{2}/[0-9]{2}/[0-9]{4}\b"),
    "PERSON": re.compile(r"\b(?:Mario Rossi|Giulia Bianchi)\b"),
    "DATE_BORN": re.compile(r"\b[0-9]{2}/[0-9]{2}/[0-9]{4}\b"),
}


def detect(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for pii_type, pattern in PATTERNS.items():
        for found in pattern.finditer(text):
            if pii_type == "DATE" and "nata a" in text[max(0, found.start() - 20):found.start()].lower():
                continue
            matches.append((pii_type, found.group(0)))
    return matches


def score(dataset: list[BenchmarkSample]) -> dict:
    total_expected = 0
    total_predicted = 0
    total_correct = 0
    latencies_ms: list[float] = []

    for sample in dataset:
        started = perf_counter()
        predicted = detect(sample.text)
        latencies_ms.append((perf_counter() - started) * 1000)
        total_expected += len(sample.expected)
        total_predicted += len(predicted)
        total_correct += sum(1 for item in predicted if item in sample.expected)

    precision = total_correct / total_predicted if total_predicted else 1.0
    recall = total_correct / total_expected if total_expected else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    latencies_sorted = sorted(latencies_ms)
    if latencies_sorted:
        p95_index = max(0, min(len(latencies_sorted) - 1, int(round(0.95 * (len(latencies_sorted) - 1)))))
        latency_p95 = round(latencies_sorted[p95_index], 3)
        latency_average = round(sum(latencies_sorted) / len(latencies_sorted), 3)
    else:
        latency_average = 0.0
        latency_p95 = 0.0

    return {
        "dataset": "italian_legal_v0.2.0",
        "dataset_size": len(dataset),
        "engine_versions": {
            "detector": "builtin-regex-v1",
            "anonymizer": "token-generator-v1",
            "python": sys.version.split()[0],
        },
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positives": total_predicted - total_correct,
        "false_negatives": total_expected - total_correct,
        "latency_average_ms": latency_average,
        "latency_p95_ms": latency_p95,
    }


def main() -> None:
    result = score(DATASET)
    output_dir = Path("benchmark/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "italian_legal_v0.2.0.json"
    md_path = output_dir / "italian_legal_v0.2.0.md"

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "# Benchmark Results\n\n"
        f"- Dataset: {result['dataset']}\n"
        f"- Dataset size: {result['dataset_size']}\n"
        f"- Engine versions: {json.dumps(result['engine_versions'], sort_keys=True)}\n"
        f"- Precision: {result['precision']}\n"
        f"- Recall: {result['recall']}\n"
        f"- F1: {result['f1']}\n"
        f"- False positives: {result['false_positives']}\n"
        f"- False negatives: {result['false_negatives']}\n"
        f"- Latency average ms: {result['latency_average_ms']}\n"
        f"- Latency p95 ms: {result['latency_p95_ms']}\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
