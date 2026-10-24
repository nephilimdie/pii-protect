"""Regression guard for transitive spaCy pins (CREDIT_CARD non-detection, 2026-10-24)."""
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements.txt"


def test_preshed_pinned_below_broken_release():
    """Why: preshed 3.0.14 made spaCy 3.7.6 raise OverflowError at load, so Presidio silently
    failed and Presidio-only types (CREDIT_CARD) were no longer detected or blocked.
    What: asserts requirements.txt pins preshed to the last compatible release.
    Test: remove the pin from requirements.txt and this test fails.
    """
    pins = {line.split("==")[0].strip(): line.split("==")[1].strip()
            for line in REQUIREMENTS.read_text().splitlines() if "==" in line and not line.startswith("#")}
    assert pins.get("spacy") == "3.7.6"
    assert pins.get("preshed") == "3.0.13"
