import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "run_synthetic.py"
SPEC = importlib.util.spec_from_file_location("run_synthetic", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_percentile_uses_nearest_rank() -> None:
    values = [40.0, 10.0, 30.0, 20.0]

    assert MODULE.percentile(values, 0.50) == 20.0
    assert MODULE.percentile(values, 0.95) == 40.0
    assert MODULE.percentile(values, 0.99) == 40.0


@pytest.mark.parametrize("quantile", [0, -0.1, 1.1])
def test_percentile_rejects_invalid_quantile(quantile: float) -> None:
    with pytest.raises(ValueError):
        MODULE.percentile([1.0], quantile)


def test_percentile_requires_values() -> None:
    with pytest.raises(ValueError):
        MODULE.percentile([], 0.95)
