"""Shared types for the in-memory document service.

Nothing in this package touches the filesystem or the database: payloads are
bytes in, bytes out, and content never reaches a log line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

SEGMENT_SEPARATOR = "\n\n"
REDACTION_MARK = "█" * 5  # fixed width, so the mark leaks neither length nor type


class DocumentFormat:
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


MEDIA_TYPES = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentFormat.TXT: "text/plain; charset=utf-8",
}


class DocumentError(Exception):
    """Why: input problems must map to clear 4xx answers without leaking content.
    What: carries an HTTP status, a stable error code and a fixed human message.
    Test: raise DocumentError(413, "DOCUMENT_TOO_LARGE", "...") and assert .status == 413.
    """

    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


@dataclass(frozen=True)
class SegmentEdit:
    """One replacement inside one segment (segment-local offsets)."""

    segment: int
    start: int
    end: int
    replacement: str


@dataclass(frozen=True)
class DocumentLimits:
    max_bytes: int
    max_pages: int
    pdf_dpi: int
    max_pixels: int  # per rendered PDF page
    pdf_min_dpi: int = 50
    docx_max_uncompressed_bytes: int = 100_000_000
    docx_max_ratio: int = 100
    docx_max_entries: int = 1_000


class LoadedDocument(Protocol):
    """Why: one contract lets the service treat TXT/DOCX/PDF uniformly (Open/Closed).
    What: exposes text segments and renders a new document from segment edits.
    Test: load a handler, render([]) and assert the output re-loads to the same segments.
    """

    format: str
    SANITIZED: tuple[str, ...]  # what the output is guaranteed not to carry over
    segments: list[str]
    pages: int | None
    warnings: list[str]

    def page_of(self, segment: int) -> int | None: ...

    def render(self, edits: list[SegmentEdit]) -> bytes: ...


@dataclass
class JoinedText:
    """Why: detection runs once on the whole document so context spans paragraphs/pages.
    What: joins segments with SEGMENT_SEPARATOR and maps global spans back to segment-local edits.
    Test: JoinedText(["ab", "cd"]).split(1, 6) == [(0, 1, 2), (1, 0, 2)].
    """

    segments: list[str]
    text: str = field(init=False)
    offsets: list[int] = field(init=False)

    def __post_init__(self) -> None:
        self.offsets = []
        cursor = 0
        for segment in self.segments:
            self.offsets.append(cursor)
            cursor += len(segment) + len(SEGMENT_SEPARATOR)
        self.text = SEGMENT_SEPARATOR.join(self.segments)

    def segment_at(self, position: int) -> int:
        index = 0
        for i, offset in enumerate(self.offsets):
            if offset > position:
                break
            index = i
        return index

    def split(self, start: int, end: int) -> list[tuple[int, int, int]]:
        pieces = []
        for index, offset in enumerate(self.offsets):
            seg_end = offset + len(self.segments[index])
            lo, hi = max(start, offset), min(end, seg_end)
            if lo < hi:
                pieces.append((index, lo - offset, hi - offset))
        return pieces

    def edits(self, spans: list[tuple[int, int, str]]) -> list[SegmentEdit]:
        """Replacement goes on the first piece of a span; later pieces are emptied."""
        out = []
        for start, end, replacement in spans:
            for n, (segment, lo, hi) in enumerate(self.split(start, end)):
                out.append(SegmentEdit(segment, lo, hi, replacement if n == 0 else ""))
        return out
