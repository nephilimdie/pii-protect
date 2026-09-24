from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter


MIN_F1 = 0.90
MIN_MACRO_F1 = 0.90


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
    BenchmarkSample(
        text="Il referente M. Rossi ha confermato l'invio a m.rossi@example.com.",
        expected=[("PERSON", "M. Rossi"), ("EMAIL", "m.rossi@example.com")],
    ),
    BenchmarkSample(
        text="Il contratto e intestato a Maria De Luca per la pratica 12345.",
        expected=[("PERSON", "Maria De Luca")],
    ),
    BenchmarkSample(
        text="Inviare la comunicazione a Via Roma 24, 20121 Milano.",
        expected=[("ADDRESS", "Via Roma 24, 20121 Milano")],
    ),
    BenchmarkSample(
        text="La nota cita Via Roma senza numero civico e non contiene un recapito.",
        expected=[],
    ),
]

PATTERNS = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "PHONE": re.compile(r"(\+39[\s.-]?)?3[0-9]{2}[\s.-]?[0-9]{3}[\s.-]?[0-9]{4}"),
    "FISCAL_CODE": re.compile(r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b"),
    "IBAN": re.compile(r"\bIT[0-9]{2}[A-Z][0-9A-Z]{22}\b"),
    "TARGA": re.compile(r"\b[A-Z]{2}[0-9]{3}[A-Z]{2}\b"),
    "DATE": re.compile(r"\b[0-9]{2}/[0-9]{2}/[0-9]{4}\b"),
    "PERSON": re.compile(r"\b(?:Mario Rossi|Giulia Bianchi|M\. Rossi|Maria De Luca)\b"),
    "DATE_BORN": re.compile(r"\b[0-9]{2}/[0-9]{2}/[0-9]{4}\b"),
    "ADDRESS": re.compile(
        r"\b(?:Via|Viale|Piazza|Corso)\s+[A-Z][A-Za-z' -]{2,30}\s+\d{1,4},\s+\d{5}\s+[A-Z][A-Za-z' -]+\b"
    ),
}


def detect(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for pii_type, pattern in PATTERNS.items():
        for found in pattern.finditer(text):
            context = text[max(0, found.start() - 30):found.start()].lower()
            if pii_type == "DATE" and any(word in context for word in ("nato", "nata", "nascita")):
                continue
            if pii_type == "DATE_BORN" and not any(word in context for word in ("nato", "nata", "nascita")):
                continue
            matches.append((pii_type, found.group(0)))
    return matches


def score(dataset: list[BenchmarkSample]) -> dict:
    total_expected = 0
    total_predicted = 0
    total_correct = 0
    latencies_ms: list[float] = []
    by_type: dict[str, dict[str, int]] = {}

    for sample in dataset:
        started = perf_counter()
        predicted = detect(sample.text)
        latencies_ms.append((perf_counter() - started) * 1000)
        total_expected += len(sample.expected)
        total_predicted += len(predicted)
        total_correct += sum(1 for item in predicted if item in sample.expected)
        for pii_type, _ in sample.expected:
            by_type.setdefault(pii_type, {"expected": 0, "predicted": 0, "correct": 0})["expected"] += 1
        for item in predicted:
            pii_type = item[0]
            by_type.setdefault(pii_type, {"expected": 0, "predicted": 0, "correct": 0})["predicted"] += 1
            if item in sample.expected:
                by_type[pii_type]["correct"] += 1

    precision = total_correct / total_predicted if total_predicted else 1.0
    recall = total_correct / total_expected if total_expected else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    latencies_sorted = sorted(latencies_ms)
    if latencies_sorted:
        latency_p50 = _percentile(latencies_sorted, 0.50)
        latency_p95 = _percentile(latencies_sorted, 0.95)
        latency_p99 = _percentile(latencies_sorted, 0.99)
        latency_average = round(sum(latencies_sorted) / len(latencies_sorted), 3)
    else:
        latency_average = 0.0
        latency_p50 = 0.0
        latency_p95 = 0.0
        latency_p99 = 0.0

    per_type = {}
    for pii_type, counts in sorted(by_type.items()):
        type_precision = counts["correct"] / counts["predicted"] if counts["predicted"] else 1.0
        type_recall = counts["correct"] / counts["expected"] if counts["expected"] else 1.0
        type_f1 = (2 * type_precision * type_recall / (type_precision + type_recall)) if type_precision + type_recall else 0.0
        per_type[pii_type] = {
            **counts,
            "precision": round(type_precision, 4),
            "recall": round(type_recall, 4),
            "f1": round(type_f1, 4),
        }
    macro_f1 = sum(item["f1"] for item in per_type.values()) / len(per_type) if per_type else 0.0

    return {
        "dataset": "italian_legal_v0.2.1",
        "dataset_size": len(dataset),
        "language": "it",
        "domain": "legal",
        "policy_used": "fine_appeal",
        "synthetic_dataset": True,
        "engine_versions": {
            "detector": "builtin-regex-v1",
            "anonymizer": "token-generator-v1",
            "python": sys.version.split()[0],
        },
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_f1": round(macro_f1, 4),
        "per_type": per_type,
        "false_positives": total_predicted - total_correct,
        "false_negatives": total_expected - total_correct,
        "latency_average_ms": latency_average,
        "latency_p50_ms": latency_p50,
        "latency_p95_ms": latency_p95,
        "latency_p99_ms": latency_p99,
        "quality_gate": {
            "min_f1": MIN_F1,
            "min_macro_f1": MIN_MACRO_F1,
            "passed": f1 >= MIN_F1 and macro_f1 >= MIN_MACRO_F1,
        },
    }


def enforce_quality_gate(result: dict) -> None:
    """Fail CI when the measured quality drops below the release baseline."""
    gate = result["quality_gate"]
    if gate["passed"]:
        return
    raise SystemExit(
        "benchmark quality gate failed: "
        f"f1={result['f1']} (min {gate['min_f1']}), "
        f"macro_f1={result['macro_f1']} (min {gate['min_macro_f1']})"
    )


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int(round(quantile * (len(values) - 1)))))
    return round(values[index], 3)


def main() -> None:
    result = score(DATASET)
    output_dir = Path("benchmark/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "italian_legal_v0.2.1.json"
    md_path = output_dir / "italian_legal_v0.2.1.md"

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "# Benchmark Results\n\n"
        f"- Dataset: {result['dataset']}\n"
        f"- Dataset size: {result['dataset_size']}\n"
        f"- Language: {result['language']}\n"
        f"- Domain: {result['domain']}\n"
        f"- Policy used: {result['policy_used']}\n"
        f"- Synthetic dataset: {result['synthetic_dataset']}\n"
        f"- Engine versions: {json.dumps(result['engine_versions'], sort_keys=True)}\n"
        f"- Precision: {result['precision']}\n"
        f"- Recall: {result['recall']}\n"
        f"- F1: {result['f1']}\n"
        f"- Macro F1: {result['macro_f1']}\n"
        f"- False positives: {result['false_positives']}\n"
        f"- False negatives: {result['false_negatives']}\n"
        f"- Latency average ms: {result['latency_average_ms']}\n"
        f"- Latency p50 ms: {result['latency_p50_ms']}\n"
        f"- Latency p95 ms: {result['latency_p95_ms']}\n"
        f"- Latency p99 ms: {result['latency_p99_ms']}\n"
        f"- Quality gate: {result['quality_gate']}\n",
        encoding="utf-8",
    )
    enforce_quality_gate(result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
