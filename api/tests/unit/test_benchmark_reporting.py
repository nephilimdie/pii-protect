from app.reporting.benchmark import BenchmarkSample, score


def test_benchmark_reports_per_type_quality_metrics():
    result = score([
        BenchmarkSample("Mario Rossi mario@example.com", [("PERSON", "Mario Rossi"), ("EMAIL", "mario@example.com")]),
    ])

    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["macro_f1"] == 1.0
    assert result["per_type"]["PERSON"]["f1"] == 1.0
    assert result["per_type"]["EMAIL"]["recall"] == 1.0
