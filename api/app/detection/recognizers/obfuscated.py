"""Spaced, dotted, lowercase and OCR-damaged codice fiscale / IBAN / P.IVA / phone numbers.

Why: values split by spaces or dashes (64% recall) and OCR-damaged values (71%) slipped past
shape-exact regexes. Normalising first and validating the checksum keeps precision.
What: tolerant shapes allow separators and case changes; the separator-free value is repaired
for common OCR confusions (O/0, I/l/1, S/5, B/8, Z/2, G/6) at positions whose class is known,
and emitted only if the CF / IBAN / P.IVA checksum passes. The span covers the original
characters, separators included. Phones are accepted by digit count after normalisation, and
OCR-repaired phones only behind a phone cue.
Test: "MNCPLA 72R43 A944X" and "PCASLO6lH10D205U" (valid after repair) -> FISCAL_CODE;
a random 16-char code with a wrong check character -> nothing.
"""
from __future__ import annotations

import re

from app.detection.checksums import is_valid_codice_fiscale, is_valid_iban, is_valid_partita_iva
from app.detection.entities import PiiEntity
from app.detection.recognizers.common import entity

_SEP = r"[ .\-]?"
_A = r"[A-Za-z0-9]"
# 16 alphanumerics with optional single separators between them (word-bounded)
_CF_LOOSE = re.compile(rf"(?<![A-Za-z0-9])(?=[A-Za-z]{{2}})(?:{_A}{_SEP}){{15}}{_A}(?![A-Za-z0-9])")
_IBAN_LOOSE = re.compile(rf"(?<![A-Za-z0-9])[A-Za-z]{{2}}[0-9OoIl]{{2}}(?:{_SEP}{_A}){{11,30}}(?![A-Za-z0-9])")
_PIVA_LOOSE = re.compile(rf"(?i:\bp\.?\s?iva|\bpartita\s+iva|\bvat)\s*(?:n\.?\s*)?:?\s*(?:IT\s?)?(?P<v>\d(?:{_SEP}\d){{10}})(?!\d)")
_PHONE_LOOSE = re.compile(
    r"(?<![\w+])(?:(?:\+|00)\s?39[\s.\-]?)?(?:\(\s?\d{2,4}\s?\)|\d)[\dOoIlSs]?(?:[\s./\-]?[\dOoIlSs]){5,10}(?![\w])"
)
_PHONE_CUE = re.compile(r"(?i)(?:\btel(?:efono|\.)?|\bcell(?:ulare|\.)?|\bmobile|\bphone|\bnumero|\bchiam\w*|\bwhatsapp|\bfax)\b[^\n]{0,20}$")
_SEPARATORS = re.compile(r"[\s.\-]")
_DATE_SHAPE = re.compile(r"\d{1,2}[./\-]\d{1,2}[./\-](?:\d{2}|\d{4})")
_TO_LETTER = str.maketrans("0125486", "OIZSABG")
_TO_DIGIT = str.maketrans("OoIlBZGDSs", "0011826055")
# CF positions holding letters; the others hold digits or omocodia letters
_CF_LETTER_POS = frozenset({0, 1, 2, 3, 4, 5, 8, 11, 15})
_OMOCODIA = frozenset("LMNPQRSTUV")


def _repair_cf(raw: str) -> str | None:
    """Why: OCR swaps letters and digits; the CF layout tells which one each position needs.
    What: uppercase, digits->letters at letter positions, non-omocodia letters->digits at digit
    positions; then tries S->5 on digit positions one at a time (S is also omocodia for 6).
    Test: _repair_cf("PCASLO6lH10D205U") == "PCASLO61H10D205U" (valid CF).
    """
    chars = list(raw.upper())
    for i, c in enumerate(chars):
        if i in _CF_LETTER_POS:
            chars[i] = c.translate(_TO_LETTER)
        elif c not in _OMOCODIA:
            chars[i] = c.translate(_TO_DIGIT)
    candidate = "".join(chars)
    if is_valid_codice_fiscale(candidate):
        return candidate
    for i, c in enumerate(chars):
        if i not in _CF_LETTER_POS and c == "S":
            alt = candidate[:i] + "5" + candidate[i + 1:]
            if is_valid_codice_fiscale(alt):
                return alt
    return None


def _repair_iban(raw: str) -> bool:
    value = raw.upper()
    if is_valid_iban(value):
        return True
    # check digits and (for IT) ABI/CAB are numeric: repair O/I/l there only
    head = value[:2] + value[2:4].translate(_TO_DIGIT)
    body = value[4:]
    if head.startswith("IT") and len(body) == 23:
        body = body[0] + body[1:11].translate(_TO_DIGIT) + body[11:]
    return is_valid_iban(head + body)


def detect_obfuscated(text: str) -> list[PiiEntity]:
    """Why/What: see module docstring. Test: see module docstring."""
    found: list[PiiEntity] = []
    for m in _CF_LOOSE.finditer(text):
        compact = _SEPARATORS.sub("", m.group())
        if len(compact) == 16 and _repair_cf(compact):
            found.append(entity(text, m.start(), m.end(), "FISCAL_CODE"))
    for m in _IBAN_LOOSE.finditer(text):
        compact = _SEPARATORS.sub("", m.group())
        # the loose shape may run into a following word: shrink to the longest valid prefix
        for end in range(len(compact), 14, -1):
            if _repair_iban(compact[:end]):
                # map the compact length back onto the original span
                seen, stop = 0, m.start()
                for stop in range(m.start(), m.end()):
                    seen += not _SEPARATORS.fullmatch(text[stop])
                    if seen == end:
                        break
                found.append(entity(text, m.start(), stop + 1, "IBAN"))
                break
    for m in _PIVA_LOOSE.finditer(text):
        if is_valid_partita_iva(_SEPARATORS.sub("", m["v"])):
            found.append(entity(text, m.start("v"), m.end("v"), "VAT_NUMBER"))
    for m in _PHONE_LOOSE.finditer(text):
        raw = m.group()
        if _DATE_SHAPE.fullmatch(raw):
            continue
        digits = re.sub(r"\D", "", raw.translate(_TO_DIGIT))
        repaired = digits != re.sub(r"\D", "", raw)
        compact = raw.replace(" ", "")
        national = digits[4:] if compact.startswith("0039") else digits[2:] if compact.startswith("+39") else digits
        plausible = (national.startswith("3") and 9 <= len(national) <= 10) or (
            national.startswith("0") and 6 <= len(national) <= 11)
        if plausible and (not repaired or _PHONE_CUE.search(text[max(0, m.start() - 40):m.start()])):
            found.append(entity(text, m.start(), m.end(), "PHONE"))
    return found
