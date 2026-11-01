"""Italian licence plates found in OCR words (no licensed plate detector exists under our
licence rule, so plates are found as *text*): current format AA 000 AA, motorcycles AA 00000,
and the pre-1994 provincial format (MI 123456, ROMA A12345)."""
from __future__ import annotations

import re
from collections.abc import Iterable

from app.detectors import Hit
from app.engines import RawWord

_L = "A-HJ-NPR-TV-Z"  # letters used since 1994 (no I, O, Q, U)
_PROVINCES = (
    "AG AL AN AO AP AQ AR AT AV BA BG BI BL BN BO BR BS BT BZ CA CB CE CH CL CN CO CR CS CT CZ EN FC FE FG FI "
    "FM FR GE GO GR IM IS KR LC LE LI LO LT LU MB MC ME MI MN MO MS MT NA NO NU OR PA PC PD PE PG PI PN PO PR PT "
    "PU PV PZ RA RC RE RG RI RM RN RO SA SI SO SP SR SS SU SV TA TE TN TO TP TR TS TV UD VA VB VC VE VI VR VT VV "
    "ROMA"
)
_CURRENT = re.compile(rf"(?<![A-Z0-9])[{_L}]{{2}} ?[0-9]{{3}} ?[{_L}]{{2}}(?![A-Z0-9])")
_MOTO = re.compile(rf"(?<![A-Z0-9])[{_L}]{{2}} ?[0-9]{{5}}(?![A-Z0-9])")
_LEGACY = re.compile(rf"(?<![A-Z0-9])(?:{'|'.join(_PROVINCES.split())}) ?([0-9A-Z]{{5,6}})(?![A-Z0-9])")


def _legacy_ok(serial: str) -> bool:
    """Pre-1994 serials are digits with at most one letter (MI 123456, MI A12345, RM 12345B)."""
    return sum(c.isdigit() for c in serial) >= 4 and sum(c.isalpha() for c in serial) <= 1


_PATTERNS = ((_CURRENT, False, None), (_MOTO, True, None), (_LEGACY, True, _legacy_ok))  # (regex, review, check)


def find_plates(words: Iterable[RawWord], review_conf: float) -> list[Hit]:
    """Why: plates identify the owner (GDPR personal data); in photos they are read by OCR.
    What: joins each OCR line's words with single spaces, upper-cases it, matches the plate
    formats and returns the union box of the matched words as LICENSE_PLATE Hits. Motorcycle
    and pre-1994 formats (more false positives) and matches with a word below ``review_conf``
    are flagged needs_review. Limit: plates OCR cannot read (angle, glare, distance) are missed.
    Test: words "AB", "123", "CD" on one line -> one LICENSE_PLATE box over the three words.
    """
    lines: dict[int, list[RawWord]] = {}
    for word in words:
        lines.setdefault(word.line, []).append(word)
    hits: list[Hit] = []
    for members in lines.values():
        members.sort(key=lambda w: w.bbox[0])
        text, spans = "", []
        for word in members:
            if text:
                text += " "
            spans.append((len(text), len(text) + len(word.text), word))
            text += word.text
        upper = text.upper()
        taken: list[tuple[int, int]] = []
        for pattern, review, check in _PATTERNS:
            for match in pattern.finditer(upper):
                if (check and not check(match.group(1))) or any(match.start() < e and match.end() > s for s, e in taken):
                    continue
                taken.append(match.span())
                inside = [w for s, e, w in spans if s < match.end() and e > match.start()]
                box = (min(w.bbox[0] for w in inside), min(w.bbox[1] for w in inside),
                       max(w.bbox[2] for w in inside), max(w.bbox[3] for w in inside))
                conf = min(w.conf for w in inside)
                hits.append(Hit("LICENSE_PLATE", box, round(conf / 100, 3), review or conf < review_conf))
    return hits
