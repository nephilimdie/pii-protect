"""Supplement OCR detection for numbered fields on Italian driving licences."""

from __future__ import annotations

import re

from app.detection.entities import PiiEntity
from app.documents.models import JoinedText

_TITLE = re.compile(r"\bPATENTE\s+DI\s+GUIDA\b", re.IGNORECASE)
_MARKER = re.compile(r"^\s*(1|2|3|5|6)\s*[.:]\s*(.*)$", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b")
_NAME = re.compile(r"^[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý' -]{1,59}$", re.IGNORECASE)
_LICENSE = re.compile(r"^[A-Z0-9]{8,20}$", re.IGNORECASE)
_FISCAL_CODE = re.compile(r"^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$", re.IGNORECASE)


def supplement_identity_fields(doc: object, joined: JoinedText, detected: list[PiiEntity]) -> list[PiiEntity]:
    """Cover OCR-readable ID fields even when a general-purpose NER misses their context.

    This rule applies only to scanned pages clearly headed as an Italian driving licence.
    It never replaces the uncertainty regions for unreadable ink.
    """
    scanned = getattr(doc, "scanned", {})
    extra: list[PiiEntity] = []
    for page_index, page in scanned.items():
        if page_index >= len(joined.offsets) or not _TITLE.search(page.text[:160]):
            continue
        lines = list(re.finditer(r"[^\n]+", page.text))
        fields: dict[str, tuple[str, int]] = {}
        for index, line in enumerate(lines):
            match = _MARKER.match(line.group())
            if match is None:
                continue
            value = match.group(2).strip()
            start = line.start() + match.start(2)
            if not value and index + 1 < len(lines) and _MARKER.match(lines[index + 1].group()) is None:
                following = lines[index + 1]
                value = following.group().strip()
                start = following.start() + len(following.group()) - len(following.group().lstrip())
            if value:
                fields[match.group(1)] = value, start
        if len(fields) < 3 or not {"1", "2", "3"}.issubset(fields):
            continue

        candidates: list[tuple[str, int, str]] = []
        for number in ("1", "2"):
            value, start = fields[number]
            if _NAME.fullmatch(value):
                candidates.append((value, start, "PERSON"))
        value, start = fields["3"]
        if date := _DATE.search(value):
            candidates.append((date.group(), start + date.start(), "DATE_OF_BIRTH"))
            place = value[date.end():].strip()
            if place and len(place) <= 50:
                candidates.append((place, start + len(value) - len(place), "LOCATION"))
        if "5" in fields:
            value, start = fields["5"]
            if _LICENSE.fullmatch(value):
                candidates.append((value, start, "DRIVER_LICENSE"))
        if "6" in fields:
            value, start = fields["6"]
            if _FISCAL_CODE.fullmatch(value):
                candidates.append((value, start, "FISCAL_CODE"))
        for value, start, pii_type in candidates:
            first = joined.offsets[page_index] + start
            last = first + len(value)
            if any(first < entity.end and last > entity.start for entity in (*detected, *extra)):
                continue
            extra.append(PiiEntity(first, last, pii_type, value, 0.95, "document_layout"))
    return detected + extra
