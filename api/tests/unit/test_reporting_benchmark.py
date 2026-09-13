from app.reporting.benchmark import DATASET, score


def test_synthetic_benchmark_reports_quality_metrics() -> None:
    result = score(DATASET)

    assert result["synthetic_dataset"] is True
    assert result["dataset_size"] == len(DATASET)
    assert 0 <= result["precision"] <= 1
    assert 0 <= result["recall"] <= 1
    assert 0 <= result["f1"] <= 1
    assert result["latency_p95_ms"] >= 0
