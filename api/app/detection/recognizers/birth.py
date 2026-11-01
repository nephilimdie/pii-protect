"""Date and place of birth from Italian context, plus codice-fiscale consistency.

Why: the generic DATE detector cannot tell a birth date from a document date, so birth data
leaked (39% / 23% recall) while document dates must stay readable.
What: emits DATE_BORN / CITY_BORN only next to birth cues ("nato/a a|in X (PR) il ...",
"n. a", "in data", "il giorno", "data di nascita:", "luogo/comune di nascita:") and for any
date equal to the birth date encoded in a valid codice fiscale of the same text.
Test: "Mario, nato in Venezia il 09/09/1985" -> CITY_BORN "Venezia", DATE_BORN "09/09/1985";
"udienza del 06.10.2020" -> nothing.
"""
from __future__ import annotations

import re

from app.detection.checksums import is_valid_codice_fiscale
from app.detection.entities import PiiEntity
from app.detection.recognizers.common import CITY, DATE, entity, parse_date

_PROV = r"(?:\s*\(\s*[A-Z]{2}\s*\))?"
_DATE_LINK = r"(?:\s*,?\s*(?i:il\s+giorno|il|in\s+data(?:\s+del)?|del|lì|li|data)?\s*:?\s*)"
_BORN = r"(?i:\bnat[oa](?:/[ao])?|(?<![\w.])n\.)"
_PATTERNS = (
    # nato/a a|in <Città> (PR), il <data>
    re.compile(rf"{_BORN}\s+(?i:a|ad|in)\s+(?P<city>{CITY}){_PROV}(?:{_DATE_LINK}(?P<date>{DATE}))?"),
    # nato/a il <data> a <Città>
    re.compile(rf"(?i:\bnat[oa](?:/[ao])?)\s+(?i:il(?:\s+giorno)?|in\s+data)\s*(?P<date>{DATE})"
               rf"(?:\s*,?\s*(?i:a|ad|in)\s+(?P<city>{CITY}))?"),
    # data di nascita: <data>
    re.compile(rf"(?i:\bdata\s+(?:di\s+)?nascita|\bdt\.?\s+nascita|\bdate\s+of\s+birth|\bborn(?:\s+on)?|\bDOB)"
               rf"\s*(?:[:\-]\s*)?(?i:il\s+)?(?P<date>{DATE})"),
    # luogo/comune di nascita: <Città> [, <data>]
    re.compile(rf"(?i:\b(?:luogo|comune|citt[àa]|localit[àa]|paese|stato)\s+(?:e\s+data\s+)?di\s+nascita"
               rf"|\bplace\s+of\s+birth)\s*[:\-]?\s*(?P<city>{CITY}){_PROV}(?:\s*[,\-]\s*(?P<date>{DATE}))?"),
)
_CF = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{6}[0-9LMNPQRSTUVlmnpqrstuv]{2}[A-Za-z][0-9LMNPQRSTUVlmnpqrstuv]{2}"
                 r"[A-Za-z][0-9LMNPQRSTUVlmnpqrstuv]{3}[A-Za-z](?![A-Za-z0-9])")
_ANY_DATE = re.compile(rf"(?<![0-9])(?:{DATE})")
_CF_MONTHS = "ABCDEHLMPRST"
_OMOCODIA = str.maketrans("LMNPQRSTUV", "0123456789")


def _cf_birth(cf: str) -> tuple[int, int, int] | None:
    """Why: a CF encodes the holder's birth date, a precise signal no context word gives.
    What: (yy, month, day) decoded from a valid CF (omocodia and female +40 handled).
    Test: _cf_birth("RSSMRA80A01H501U") == (80, 1, 1).
    """
    cf = cf.upper()
    if not is_valid_codice_fiscale(cf):
        return None
    yy, day = int(cf[6:8].translate(_OMOCODIA)), int(cf[9:11].translate(_OMOCODIA))
    return yy, _CF_MONTHS.index(cf[8]) + 1, day - 40 if day > 40 else day


def detect_birth(text: str) -> list[PiiEntity]:
    """Why/What: see module docstring. Test: see module docstring."""
    found: list[PiiEntity] = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if m.groupdict().get("city"):
                found.append(entity(text, m.start("city"), m.end("city"), "CITY_BORN"))
            if m.groupdict().get("date") and parse_date(m["date"]):
                found.append(entity(text, m.start("date"), m.end("date"), "DATE_BORN"))
    births = {b for m in _CF.finditer(text) if (b := _cf_birth(m.group()))}
    if births:
        for m in _ANY_DATE.finditer(text):
            d = parse_date(m.group())
            if d and (d.year % 100, d.month, d.day) in births:
                found.append(entity(text, m.start(), m.end(), "DATE_BORN"))
    return found
