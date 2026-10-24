from __future__ import annotations

from app.documents.models import DocumentError, DocumentFormat, SegmentEdit

_BOMS = (("utf-8-sig", b"\xef\xbb\xbf"), ("utf-16", b"\xff\xfe"), ("utf-16", b"\xfe\xff"))


def decode_text(payload: bytes) -> str:
    """Why: Italian users drop UTF-8 and legacy Windows (cp1252) text files alike.
    What: decodes BOM-marked UTF-8/16, then UTF-8, then cp1252; rejects binaries (NUL bytes) with 415.
    Test: "è".encode("cp1252") decodes to "è"; b"\\x00\\x01" raises DocumentError(415).
    """
    for encoding, bom in _BOMS:
        if payload.startswith(bom):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                break
    if b"\x00" in payload:
        raise DocumentError(415, "UNSUPPORTED_DOCUMENT_TYPE", "Only PDF, DOCX and plain-text files are supported.")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("cp1252", errors="replace")


class TxtDocument:
    """Why: plain text is the simplest LoadedDocument and the reference for edit semantics.
    What: one segment holding the decoded text; renders UTF-8 with edits applied right-to-left.
    Test: TxtDocument(b"ciao Mario").render([SegmentEdit(0, 5, 10, "[PERSON_1]")]) == b"ciao [PERSON_1]".
    """

    format = DocumentFormat.TXT
    SANITIZED: tuple[str, ...] = ()
    pages = None

    def __init__(self, payload: bytes) -> None:
        self.segments = [decode_text(payload)]
        self.warnings: list[str] = []

    def page_of(self, segment: int) -> int | None:
        return None

    def render(self, edits: list[SegmentEdit]) -> bytes:
        text = self.segments[0]
        for edit in sorted(edits, key=lambda e: e.start, reverse=True):
            text = text[:edit.start] + edit.replacement + text[edit.end:]
        return text.encode("utf-8")
