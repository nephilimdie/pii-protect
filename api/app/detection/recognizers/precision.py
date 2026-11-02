"""Precision filter for ML-layer spans: headings, stopwords, bare numbers, unparseable IPs.

Why: the baseline's false positives on non-PII look-alikes came mostly from ML layers:
privacy_filter ADDRESS on bare numbers (codes, law refs, amounts), ai4privacy IP_ADDRESS on
amounts ("191.799"), and PERSON on headings/greetings ("PROCURA ALLE LITI", "Cordiali", "Lei") and on capitalised payslip/
contract vocabulary ("Contributi", "Canone", "Superminimo") at confident scores.
What: drops ML-sourced (source != "regex") entities whose text cannot be that type. Deterministic
spans are never touched. "maximum" keeps the score-free shape rules but skips the low-confidence
and all-lowercase single-token PERSON rules, trading precision for recall.
Test: PERSON "Cordiali saluti" (ml) -> dropped; ADDRESS "431/1998" (ml) -> dropped;
IP_ADDRESS "191.799" (ml) -> dropped; PERSON "Mario Rossi" (ml) -> kept.
"""
from __future__ import annotations

import ipaddress
import re

from app.detection.entities import PiiEntity
from app.detection.recognizers.common import BALANCED, SOURCE
from app.detection.recognizers.persons import STOPWORDS

_LETTERS = re.compile(r"[A-Za-zÀ-ÿ]{3,}")
_TOKEN_STRIP = ".,:;'’\"()[]"
# a single-token ML PERSON below this score is more often a capitalised common word than a name
_SINGLE_PERSON_MIN_SCORE = 0.85


def _tokens(text: str) -> list[str]:
    return [t.lower().strip(_TOKEN_STRIP) for t in text.split() if t.strip(_TOKEN_STRIP)]


def _person_ok(e: PiiEntity, level: str) -> bool:
    tokens = _tokens(e.text)
    if not tokens or all(t in STOPWORDS for t in tokens):
        return False
    if not re.search(r"[a-zà-ÿ]", e.text) and len(tokens) > 1 and any(t in STOPWORDS for t in tokens):
        return False  # UPPERCASE heading with a function/legal word ("PROCURA ALLE LITI")
    if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", e.text)) < 3:
        return False  # "R.G", initials only
    # balanced: one token that is low-confidence or all-lowercase ("lorda") is a common word, not a name
    return not (level == BALANCED and len(tokens) == 1
                and (e.score < _SINGLE_PERSON_MIN_SCORE or not re.search(r"[A-ZÀ-Ý]", e.text)))


def _ip_ok(e: PiiEntity, _level: str) -> bool:
    try:
        ipaddress.ip_address(e.text.strip())
        return True
    except ValueError:
        return False


def _address_ok(e: PiiEntity, _level: str) -> bool:
    return bool(_LETTERS.search(e.text))


_RULES = {"PERSON": _person_ok, "IP_ADDRESS": _ip_ok, "ADDRESS": _address_ok}


def precision_filter(entities: list[PiiEntity], level: str = BALANCED) -> list[PiiEntity]:
    """Why/What: see module docstring. Test: see module docstring."""
    return [e for e in entities
            if e.source == SOURCE or (rule := _RULES.get(e.pii_type)) is None or rule(e, level)]
