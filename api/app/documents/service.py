"""Format-agnostic document operations: load, plan edits, package output (all in memory)."""

from __future__ import annotations

import io
import json
import zipfile

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.detection.entities import PiiEntity
from app.documents.models import (
    REDACTION_MARK,
    DocumentError,
    DocumentLimits,
    JoinedText,
    LoadedDocument,
    SegmentEdit,
)
from app.routers.replacements import apply_replacements

MAX_USER_ENTITIES = 20_000


def load_document(payload: bytes, limits: DocumentLimits) -> LoadedDocument:
    """Why: the client's filename and Content-Type are untrusted; magic bytes decide the parser.
    What: returns a PDF, DOCX or TXT LoadedDocument, or raises DocumentError (413/415/422).
    Test: b"%PDF-..." -> PdfDocument; legacy .doc magic -> 422 LEGACY_OR_ENCRYPTED_OFFICE_FILE.
    """
    if not payload:
        raise DocumentError(422, "EMPTY_DOCUMENT", "The uploaded file is empty.")
    if len(payload) > limits.max_bytes:
        raise DocumentError(413, "DOCUMENT_TOO_LARGE", f"The file exceeds {limits.max_bytes} bytes.")
    if b"%PDF-" in payload[:1024]:
        from app.documents.pdf_handler import PdfDocument
        return PdfDocument(payload, limits)
    if payload.startswith(b"PK\x03\x04"):
        from app.documents.docx_handler import DocxDocument
        return DocxDocument(payload, limits.max_bytes)
    if payload.startswith(b"\xd0\xcf\x11\xe0"):
        raise DocumentError(422, "LEGACY_OR_ENCRYPTED_OFFICE_FILE",
                            "Legacy .doc and password-protected Office files are not supported; save as DOCX.")
    from app.documents.txt_handler import TxtDocument
    return TxtDocument(payload)


class UserEntity(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    type: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")


_USER_ENTITIES = TypeAdapter(list[UserEntity])


def parse_user_entities(raw: str, text: str) -> list[PiiEntity]:
    """Why: the UI lets users add/remove entities after /preview; the corrected list must be safe to apply.
    What: validates JSON [{start,end,type}] against the extracted text (bounds, no overlaps) and
    returns PiiEntity objects whose text is taken from the document, never from the client.
    Test: overlapping spans -> 422 INVALID_ENTITIES; end beyond text length -> 422; valid -> sorted entities.
    """
    try:
        items = _USER_ENTITIES.validate_json(raw)
    except ValidationError as exc:
        raise DocumentError(422, "INVALID_ENTITIES", "`entities` must be a JSON array of {start, end, type}.") from exc
    if len(items) > MAX_USER_ENTITIES:
        raise DocumentError(422, "INVALID_ENTITIES", f"At most {MAX_USER_ENTITIES} entities are accepted.")
    items.sort(key=lambda item: item.start)
    previous_end = 0
    for item in items:
        if item.end <= item.start or item.end > len(text) or item.start < previous_end:
            raise DocumentError(422, "INVALID_ENTITIES",
                                "Entity offsets must be inside the document text and must not overlap.")
        previous_end = item.end
    return [PiiEntity(i.start, i.end, i.type, text[i.start:i.end], 1.0, "user") for i in items]


def redaction_edits(joined: JoinedText, entities: list[PiiEntity]) -> list[SegmentEdit]:
    return joined.edits([(e.start, e.end, REDACTION_MARK) for e in entities])


def pseudonymization_edits(
    joined: JoinedText, entities: list[PiiEntity], remove_types: set[str]
) -> tuple[list[SegmentEdit], list[dict[str, str]]]:
    """Why: tokens must match /v1/anonymize tag mode exactly ([PERSON_1] stable per value).
    What: reuses apply_replacements for token assignment; returns segment edits and the
    client-side mapping (token, type, original) in first-occurrence order, removed types excluded.
    Test: two "Mario Rossi" entities -> both edits carry [PERSON_1] and the mapping has one row.
    """
    _, mappings = apply_replacements(joined.text, sorted(entities, key=lambda e: e.start), "tag", None, remove_types)
    mappings.sort(key=lambda m: m.start)
    edits = joined.edits([(m.start, m.end, m.token) for m in mappings])
    seen: dict[str, dict[str, str]] = {}
    for m in mappings:
        if m.token and m.token not in seen:
            seen[m.token] = {"token": m.token, "type": m.pii_type, "original": m.original}
    return edits, list(seen.values())


def zip_pseudonymized(document: bytes, filename: str, mapping: list[dict[str, str]]) -> bytes:
    """Why: the mapping is returned to the user, never stored; one ZIP keeps document and key together.
    What: builds an in-memory ZIP with `filename` and `mapping.json`.
    Test: open the returned bytes with zipfile and assert both members and the mapping content.
    """
    manifest = {"format_version": 1, "document": filename, "entities": mapping}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, document)
        archive.writestr("mapping.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buffer.getvalue()
