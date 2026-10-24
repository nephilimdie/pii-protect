"""Multipart upload parsing that is guaranteed to stay in memory.

Starlette spools uploaded files to a SpooledTemporaryFile that rolls over to
disk after 1 MB. Document requests must never touch disk, so the stream is
capped at the upload limit and the spool threshold is set above that cap:
rollover is impossible, and is still checked (fail closed) after parsing.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.documents.models import DocumentError

FORM_OVERHEAD_BYTES = 2 * 1024 * 1024  # boundaries, headers and the `entities` JSON field
_MAX_FIELD_BYTES = FORM_OVERHEAD_BYTES
_MAX_FIELDS = 8


@dataclass(frozen=True)
class DocumentUpload:
    payload: bytes
    fields: dict[str, str]


class _InMemoryMultiPartParser(MultiPartParser):
    def __init__(self, *args, spool_max_size: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.spool_max_size = spool_max_size


def _too_large(max_bytes: int) -> DocumentError:
    return DocumentError(413, "DOCUMENT_TOO_LARGE", f"The file exceeds {max_bytes} bytes.")


async def read_document_upload(request: Request, max_bytes: int) -> DocumentUpload:
    """Why: zero retention — the upload must never be written to a temp file.
    What: parses multipart/form-data with exactly one `file` part into memory; enforces the
    byte limit while streaming (413) and rejects malformed forms (400/415/422).
    Test: post a 2 MB file (above Starlette's 1 MB spool) and assert no file is opened for writing.
    """
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise DocumentError(415, "MULTIPART_REQUIRED", "Send the document as multipart/form-data in a `file` field.")
    stream_limit = max_bytes + FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > stream_limit:
        raise _too_large(max_bytes)

    async def limited_stream():
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > stream_limit:
                raise _too_large(max_bytes)
            yield chunk

    parser = _InMemoryMultiPartParser(
        request.headers, limited_stream(),
        max_files=1, max_fields=_MAX_FIELDS, max_part_size=_MAX_FIELD_BYTES,
        spool_max_size=stream_limit + 1,
    )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        raise DocumentError(400, "INVALID_MULTIPART", "The multipart form could not be parsed.") from exc
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise DocumentError(422, "FILE_REQUIRED", "A `file` part is required.")
    try:
        if getattr(upload.file, "_rolled", False):
            raise RuntimeError("upload spooled to disk")  # unreachable by construction; fail closed
        payload = await upload.read()
    finally:
        await upload.close()
    if len(payload) > max_bytes:
        raise _too_large(max_bytes)
    fields = {key: value for key, value in form.multi_items() if isinstance(value, str)}
    return DocumentUpload(payload=payload, fields=fields)
