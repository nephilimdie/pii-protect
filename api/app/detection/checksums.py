"""Checksum validators for structured identifiers.

Why: shape-only regexes for codice fiscale, partita IVA and IBAN also match
random codes; a checksum gate keeps precision high without dropping recall.
What: pure functions returning True only for values whose check digit/char is
correct, plus a VALIDATORS registry that regex patterns opt into via the
``VALIDATE:<name>`` flag (see regex_layer._compile).
Test: tests/unit/test_checksums.py asserts known-valid synthetic values pass
and single-character corruptions fail.
"""

from __future__ import annotations

import re
from typing import Callable

# fmt: off
_CF_ODD = {
    '0': 1,  '1': 0,  '2': 5,  '3': 7,  '4': 9,  '5': 13, '6': 15, '7': 17, '8': 19, '9': 21,
    'A': 1,  'B': 0,  'C': 5,  'D': 7,  'E': 9,  'F': 13, 'G': 15, 'H': 17, 'I': 19, 'J': 21,
    'K': 2,  'L': 4,  'M': 18, 'N': 20, 'O': 11, 'P': 3,  'Q': 6,  'R': 8,  'S': 12, 'T': 14,
    'U': 16, 'V': 10, 'W': 22, 'X': 25, 'Y': 24, 'Z': 23,
}
# fmt: on
_CF_OMOCODIA = "LMNPQRSTUV"  # letter that replaces digit 0..9 in homocode CFs
_CF_SHAPE = re.compile(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-EHLMPR-T][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]")
_IBAN_SHAPE = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}")
# SEPA-area lengths; countries not listed are length-checked only by the shape.
_IBAN_LENGTHS = {
    "IT": 27, "SM": 27, "VA": 22, "DE": 22, "FR": 27, "ES": 24, "PT": 25, "AT": 20,
    "BE": 16, "NL": 18, "LU": 20, "CH": 21, "GB": 22, "IE": 22, "MT": 31, "SI": 19,
}


def _even_value(char: str) -> int:
    return int(char) if char.isdigit() else ord(char) - ord("A")


def cf_check_char(first15: str) -> str:
    """Why: single source of truth for the CF control character (detection + surrogates).
    What: returns the 16th character for the given first 15 uppercase chars.
    Test: cf_check_char("RSSMRA80A01H501") == "U".
    """
    total = sum(_CF_ODD[c] if i % 2 == 0 else _even_value(c) for i, c in enumerate(first15))
    return chr(ord("A") + total % 26)


def is_valid_codice_fiscale(value: str) -> bool:
    """Why: rejects 16-char codes that only look like a CF (incl. homocode variants).
    What: checks shape, plausible birth day (1-31 or 41-71) and the control character.
    Test: "RSSMRA80A01H501U" -> True; "RSSMRA80A01H501A" -> False.
    """
    cf = value.strip().upper()
    if not _CF_SHAPE.fullmatch(cf):
        return False
    day = int("".join(str(_CF_OMOCODIA.index(c)) if c in _CF_OMOCODIA else c for c in cf[9:11]))
    if not (1 <= day <= 31 or 41 <= day <= 71):
        return False
    return cf_check_char(cf[:15]) == cf[15]


def is_valid_partita_iva(value: str) -> bool:
    """Why: an 11-digit run is ambiguous (protocols, phone+prefix); the check digit is not.
    What: strips an optional IT prefix/spaces, applies the Luhn-like P.IVA algorithm.
    Test: "01234567897" -> True; "01234567890" -> False; "00000000000" -> False.
    """
    digits = re.sub(r"\s", "", value.strip().upper()).removeprefix("IT")
    if not re.fullmatch(r"\d{11}", digits) or digits == "0" * 11:
        return False
    total = 0
    for i, char in enumerate(digits[:10]):
        n = int(char)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return (10 - total % 10) % 10 == int(digits[10])


def is_valid_iban(value: str) -> bool:
    """Why: the generic spaced-IBAN regex is broad; ISO 13616 mod-97 makes it precise.
    What: normalises spaces/case, checks shape + known country length + mod 97 == 1.
    Test: "IT60 X054 2811 1010 0000 0123 456" -> True; last digit changed -> False.
    """
    iban = re.sub(r"\s", "", value).upper()
    if not _IBAN_SHAPE.fullmatch(iban):
        return False
    if _IBAN_LENGTHS.get(iban[:2], len(iban)) != len(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


VALIDATORS: dict[str, Callable[[str], bool]] = {
    "codice_fiscale": is_valid_codice_fiscale,
    "partita_iva": is_valid_partita_iva,
    "iban": is_valid_iban,
}
