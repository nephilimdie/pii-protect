import pytest

from app.reporting.benchmark import BenchmarkSample, enforce_quality_gate, score


def test_benchmark_reports_per_type_quality_metrics():
    result = score([
        BenchmarkSample("Mario Rossi mario@example.com", [("PERSON", "Mario Rossi"), ("EMAIL", "mario@example.com")]),
    ])

    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["macro_f1"] == 1.0
    assert result["per_type"]["PERSON"]["f1"] == 1.0
    assert result["per_type"]["EMAIL"]["recall"] == 1.0


def test_benchmark_quality_gate_rejects_a_failed_result():
    result = score([BenchmarkSample("Mario Rossi", [("EMAIL", "missing@example.com")])])

    assert result["quality_gate"]["passed"] is False
    with pytest.raises(SystemExit, match="quality gate failed"):
        enforce_quality_gate(result)
