"""Overlapping-window detection for long document text.

The detectors receive the whole input at once: spaCy/Presidio and the HF
token-classification pipeline hold per-token state for the full text, so
their memory grows with document length. Documents are therefore analysed in
overlapping windows aligned to paragraph/sentence/word boundaries, and the
per-window entities are merged back into one global, non-overlapping list.
Pseudonym numbering stays global because tokens are assigned afterwards on
the merged list (apply_replacements), never per window.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.detection.entities import PiiEntity

# Preferred cut points, best first; the search looks back at most this far from the target.
_BREAKS = ("\n\n", "\n", ". ", "; ", ", ", " ")
_ALIGN_LOOKBACK = 1_000


def _align_end(text: str, target: int, floor: int) -> int:
    """Last preferred break in (floor, target]; the cut falls just after it."""
    lo = max(floor, target - _ALIGN_LOOKBACK)
    for marker in _BREAKS:
        at = text.rfind(marker, lo, target)
        if at > floor:
            return at + len(marker)
    return target


def _align_start(text: str, target: int, ceiling: int) -> int:
    """First whitespace at/after target (so a window never starts mid-word)."""
    for at in range(target, ceiling):
        if text[at].isspace():
            return at + 1
    return target


def windows(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """Why: bound detector input size while giving every entity full context in some window.
    What: returns [start, end) windows of at most `size` chars covering `text`, consecutive
    windows overlapping by about `overlap` chars, cut at paragraph/sentence/word breaks.
    Test: windows("a " * 10_000, 4_000, 300) covers 0..20_000 with each window <= 4_000 and
    every start < previous end.
    """
    if len(text) <= size:
        return [(0, len(text))]
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        if start + size >= len(text):
            spans.append((start, len(text)))
            return spans
        end = _align_end(text, start + size, start + overlap * 2)
        spans.append((start, end))
        start = _align_start(text, end - overlap, end)


def _touches_cut(entity: PiiEntity, window: tuple[int, int], length: int) -> bool:
    start, end = window
    return (start > 0 and entity.start <= start) or (end < length and entity.end >= end)


def merge_windows(text: str, found: list[tuple[tuple[int, int], list[PiiEntity]]]) -> list[PiiEntity]:
    """Why: an entity in an overlap region is reported by two windows, and an entity cut by a
    window edge is reported truncated; the document must get each entity exactly once, whole.
    What: groups transitively overlapping spans; prefers spans that do not touch a window cut,
    then longer, then higher score; a group made only of cut fragments becomes their union.
    Test: "Mario Rossi" reported whole by window B and as "Mario" (touching A's end) by A
    -> one PERSON entity spanning "Mario Rossi".
    """
    candidates = [(e, _touches_cut(e, w, len(text))) for w, entities in found for e in entities]
    candidates.sort(key=lambda c: (c[0].start, -c[0].end))
    merged: list[PiiEntity] = []
    group: list[tuple[PiiEntity, bool]] = []
    group_end = -1
    for candidate in candidates + [(None, False)]:
        entity = candidate[0]
        if entity is not None and entity.start < group_end:
            group.append(candidate)
            group_end = max(group_end, entity.end)
            continue
        if group:
            merged.extend(_resolve(text, group))
        group = [candidate] if entity is not None else []
        group_end = entity.end if entity is not None else -1
    return sorted(merged, key=lambda e: e.start)


def _resolve(text: str, group: list[tuple[PiiEntity, bool]]) -> list[PiiEntity]:
    if all(cut for _, cut in group):
        longest = max((e for e, _ in group), key=lambda e: (e.end - e.start, e.score))
        start, end = min(e.start for e, _ in group), max(e.end for e, _ in group)
        return [PiiEntity(start, end, longest.pii_type, text[start:end], max(e.score for e, _ in group),
                          longest.source)]
    chosen: list[PiiEntity] = []
    for entity, _ in sorted(group, key=lambda c: (c[1], -(c[0].end - c[0].start), -c[0].score)):
        if all(entity.end <= kept.start or entity.start >= kept.end for kept in chosen):
            chosen.append(entity)
    return chosen


def detect_in_windows(detect: Callable[[str], list[PiiEntity]], text: str, size: int, overlap: int) -> list[PiiEntity]:
    """Why: one entry point so callers get identical results for short texts and bounded
    memory for long ones.
    What: runs `detect` on each window sequentially (one window's model input alive at a
    time), shifts offsets to document coordinates and merges across windows.
    Test: a fake detector over a 3-window text returns each planted name once, at the
    document offset of the name.
    """
    spans = windows(text, size, overlap)
    if len(spans) == 1:
        return detect(text)
    found = []
    for start, end in spans:
        entities = [replace(e, start=e.start + start, end=e.end + start) for e in detect(text[start:end])]
        found.append(((start, end), entities))
    return merge_windows(text, found)
