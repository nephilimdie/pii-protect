"""Supplement OCR detection for labelled fields on driving licences."""

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
_US_TITLE = re.compile(r"\bDRIVER['’]?S\s*LICENSE\b", re.IGNORECASE)
_US_NUMBER = re.compile(r"^\d{2}(?:\s+\d{3}){2}$")
_US_STREET = re.compile(
    r"^\d{1,6}\s*[A-Z][A-Z .'-]*(?:STREET|ROAD|AVENUE|DRIVE|LANE|BOULEVARD|\bST\b|\bRD\b|\bAVE\b)$",
    re.IGNORECASE,
)
_US_CITY_ZIP = re.compile(r"^[A-Z][A-Z .'-]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?$", re.IGNORECASE)
_US_DD = re.compile(r"^\s*\d?\s*DD\s*:\s*(\d{8,20})\s*$", re.IGNORECASE)
_US_APT = re.compile(r"APT\.?\s*\d+[A-Z]?", re.IGNORECASE)


def _us_fields(text: str) -> list[tuple[str, int, str]]:
    if not _US_TITLE.search(text[:160]):
        return []
    lines = [match for match in re.finditer(r"[^\n]+", text) if match.group().strip()]
    candidates: list[tuple[str, int, str]] = []

    def add(match: re.Match[str], pii_type: str, group: int = 0) -> None:
        candidates.append((match.group(group), match.start(group), pii_type))

    for index, line in enumerate(lines):
        value = line.group().strip()
        if (_US_NUMBER.fullmatch(value) and any("DLN" in nearby.group().upper()
                                               for nearby in lines[max(0, index - 3):index + 4])):
            add(line, "DRIVER_LICENSE")
        if dd := _US_DD.fullmatch(value):
            candidates.append((dd.group(1), line.start() + dd.start(1), "DRIVER_LICENSE"))
            if index + 1 < len(lines) and re.fullmatch(r"\d{8,20}", lines[index + 1].group().strip()):
                add(lines[index + 1], "DRIVER_LICENSE")
        if _US_STREET.fullmatch(value):
            add(line, "LOCATION")
            for next_line in lines[index + 1:index + 3]:
                if _US_CITY_ZIP.fullmatch(next_line.group().strip()) or _US_APT.fullmatch(next_line.group().strip()):
                    add(next_line, "LOCATION")
        if _US_CITY_ZIP.fullmatch(value):
            add(line, "LOCATION")
        if value.upper() == "DOB:":
            for nearby in lines[max(0, index - 2):index + 3]:
                if _DATE.fullmatch(nearby.group().strip()):
                    add(nearby, "DATE_OF_BIRTH")
                    break
            for name in lines[index + 1:index + 3]:
                if _NAME.fullmatch(name.group().strip()):
                    add(name, "PERSON")
    return candidates


def supplement_identity_fields(doc: object, joined: JoinedText, detected: list[PiiEntity]) -> list[PiiEntity]:
    """Cover OCR-readable ID fields even when a general-purpose NER misses their context.

    This rule applies only to scanned pages clearly headed as a driving licence.
    It never replaces the uncertainty regions for unreadable ink.
    """
    scanned = getattr(doc, "scanned", {})
    extra: list[PiiEntity] = []
    normalized = list(detected)
    for page_index, page in scanned.items():
        if page_index >= len(joined.offsets):
            continue
        candidates = _us_fields(page.text)
        if not _TITLE.search(page.text[:160]):
            _merge_candidates(candidates, page_index, joined, normalized, extra)
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
        _merge_candidates(candidates, page_index, joined, normalized, extra)
    return normalized + extra


def _merge_candidates(candidates: list[tuple[str, int, str]], page_index: int, joined: JoinedText,
                      normalized: list[PiiEntity], extra: list[PiiEntity]) -> None:
    for value, start, pii_type in candidates:
        first = joined.offsets[page_index] + start
        last = first + len(value)
        exact = next((index for index, entity in enumerate(normalized)
                      if entity.start == first and entity.end == last), None)
        if exact is not None:
            if pii_type in {"DATE_OF_BIRTH", "DRIVER_LICENSE"}:
                original = normalized[exact]
                normalized[exact] = PiiEntity(first, last, pii_type, value, original.score, "document_layout")
            continue
        if any(first < entity.end and last > entity.start for entity in (*normalized, *extra)):
            continue
        extra.append(PiiEntity(first, last, pii_type, value, 0.95, "document_layout"))
