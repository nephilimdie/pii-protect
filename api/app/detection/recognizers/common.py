"""Shared building blocks for the code-level Italian recognizers.

Why: birth, identifier, person and key/value recognizers need the same date, city and name
grammar; defining it once keeps their boundaries consistent.
What: regex fragments (dates, cities, name tokens), protection levels and an entity factory.
Test: tests/unit/test_recognizers.py exercises every fragment through the recognizers.
"""
from __future__ import annotations

import re
from datetime import date

from app.detection.entities import PiiEntity

BALANCED = "balanced"
MAXIMUM = "maximum"
PROTECTION_LEVELS = (BALANCED, MAXIMUM)
SOURCE = "regex"  # deterministic: the merger lets these beat overlapping ML spans

MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
          "settembre", "ottobre", "novembre", "dicembre")
_MONTH_RE = "|".join(MONTHS) + r"|gen|feb|mar|apr|mag|giu|lug|ago|sett?|ott|nov|dic"
# OCR-tolerant digit, used only behind a strong context cue (O/o -> 0, I/l -> 1)
_D = r"[0-9OoIl]"
DATE = (
    rf"(?:{_D}{{1,2}}\s?[./\-]\s?{_D}{{1,2}}\s?[./\-]\s?(?:{_D}{{4}}|{_D}{{2}})(?![0-9])"
    rf"|(?:19|20)\d{{2}}-\d{{1,2}}-\d{{1,2}}(?![0-9])"
    rf"|\d{{1,2}}\s+(?i:{_MONTH_RE})\.?\s+(?:\d{{4}}|'?\d{{2}})(?![0-9]))"
)
# Capitalised or UPPERCASE place name, up to four words with Italian connectors (no newlines).
_CITY_WORD = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+"
CITY = rf"{_CITY_WORD}(?:[ \-](?:(?i:di|de|del|della|dei|sul|sulla|in|al|d'|sull')[ ]?)?{_CITY_WORD}){{0,3}}"

_OCR_DIGITS = str.maketrans("OoIl", "0011")


def entity(text: str, start: int, end: int, pii_type: str, score: float = 1.0) -> PiiEntity:
    """Why: every recognizer emits the same deterministic-source entity shape.
    What: PiiEntity for text[start:end] with source "regex".
    Test: entity("ab", 0, 1, "X").text == "a".
    """
    return PiiEntity(start=start, end=end, pii_type=pii_type, text=text[start:end], score=score, source=SOURCE)


def parse_date(value: str) -> date | None:
    """Why: CF consistency and date sanity need the calendar value, not the string.
    What: parses d/m/y (2- or 4-digit year, OCR digits allowed), ISO y-m-d and "d mese yyyy".
    Test: parse_date("3/7/00") == date(2000, 7, 3); parse_date("1951-03-17").year == 1951.
    """
    s = value.strip().lower().translate(_OCR_DIGITS)
    try:
        if m := re.fullmatch(r"((?:19|20)\d\d)-(\d{1,2})-(\d{1,2})", s):
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
        elif m := re.fullmatch(r"(\d{1,2})\s?[./\-]\s?(\d{1,2})\s?[./\-]\s?(\d{2}|\d{4})", s):
            d, mo, y = int(m[1]), int(m[2]), int(m[3])
        elif m := re.fullmatch(r"(\d{1,2})\s+([a-z]+)\.?\s+'?(\d{2}|\d{4})", s):
            mo = next((i + 1 for i, name in enumerate(MONTHS) if name.startswith(m[2][:3])), 0)
            d, y = int(m[1]), int(m[3])
        else:
            return None
        if y < 100:
            y += 1900 if y > date.today().year % 100 else 2000
        return date(y, mo, d)
    except ValueError:
        return None
