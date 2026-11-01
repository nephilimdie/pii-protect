"""Code-level Italian recognizers and the ML precision filter, behind one entry point each.

Why: context rules (birth data, cue-based names, key-aware logs, obfuscated identifiers) need
code, not single DB regexes; the regex layer and the anonymizer call them through this module
so neither has to know the individual recognizers.
What: detect_contextual() runs every recognizer; precision_filter() drops ML false positives.
Test: tests/unit/test_recognizers.py covers each rule through these two functions.
"""
from __future__ import annotations

from app.detection.entities import PiiEntity
from app.detection.recognizers.birth import detect_birth
from app.detection.recognizers.common import BALANCED, MAXIMUM, PROTECTION_LEVELS
from app.detection.recognizers.identifiers import detect_identifiers
from app.detection.recognizers.key_value import detect_key_values
from app.detection.recognizers.obfuscated import detect_obfuscated
from app.detection.recognizers.persons import detect_persons
from app.detection.recognizers.precision import precision_filter

__all__ = ["BALANCED", "MAXIMUM", "PROTECTION_LEVELS", "detect_contextual", "precision_filter"]

_RECOGNIZERS = (detect_birth, detect_identifiers, detect_key_values, detect_obfuscated, detect_persons)


def detect_contextual(text: str, level: str = BALANCED) -> list[PiiEntity]:
    """Why: one call site for the regex layer.
    What: concatenated output of every recognizer (the merger resolves overlaps).
    Test: detect_contextual("ip=10.0.0.1") contains an IP_ADDRESS span "10.0.0.1".
    """
    return [e for recognize in _RECOGNIZERS for e in recognize(text)]
