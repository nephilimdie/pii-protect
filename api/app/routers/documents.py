"""Zero-retention document endpoints: preview, redact, pseudonymize.

Documents are processed entirely in memory. Content, filenames and mappings are
never stored or logged; only metadata (size, format, counts, timings) is
recorded. Every failure returns an error and never the original document,
independent of PII_FAILURE_MODE.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.anonymization.anonymizer import PiiAnonymizer
from app.audit.audit_service import AuditService
from app.config import settings
from app.database import get_db
from app.documents.admission import AdmissionSlot, DocumentAdmission
from app.documents.models import MEDIA_TYPES, DocumentError, DocumentFormat, DocumentLimits, JoinedText
from app.documents.service import (
    load_document,
    parse_user_entities,
    pseudonymization_edits,
    redaction_edits,
    zip_pseudonymized,
)
from app.documents.upload import read_document_upload
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.identity.tenant import get_tenant_id
from app.routers._anonymize_logic import detect_protected_entities, get_anonymizer
from app.surrogates.policy_service import PolicyService
from app.usage.service import UsageService

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)


class Operation:
    PREVIEW = "preview"
    REDACT = "redact"
    PSEUDONYMIZE = "pseudonymize"


_FORM_FIELDS = {
    "file": {"type": "string", "format": "binary", "description": "PDF, DOCX or UTF-8/cp1252 text file."},
    "domain": {"type": "string", "description": "Domain policy preset, e.g. hr_payroll, tax_accounting."},
    "context_type": {"type": "string", "description": "Context type (used when `domain` is absent; default generic)."},
    "language": {"type": "string", "description": "Detection language (default: engine default, usually it)."},
    "entities": {"type": "string", "description": "redact/pseudonymize only: JSON array of {start,end,type} "
                                                   "from /preview, edited by the user. Replaces detection."},
}
_OPENAPI_FORM = {"requestBody": {"required": True, "content": {"multipart/form-data": {
    "schema": {"type": "object", "required": ["file"], "properties": _FORM_FIELDS}}}}}


def _limits() -> DocumentLimits:
    return DocumentLimits(
        max_bytes=settings.document_upload_max_bytes,
        max_pages=settings.document_upload_max_pages,
        pdf_dpi=settings.document_pdf_dpi,
        max_pixels=settings.document_pdf_max_page_pixels,
        pdf_min_dpi=settings.document_pdf_min_dpi,
        docx_max_uncompressed_bytes=settings.document_docx_max_uncompressed_bytes,
        docx_max_ratio=settings.document_docx_max_ratio,
        docx_max_entries=settings.document_docx_max_entries,
    )


@lru_cache(maxsize=1)
def get_document_admission() -> DocumentAdmission:
    """Process-wide admission control for document jobs (FastAPI dependency; override in tests)."""
    return DocumentAdmission(settings.document_max_concurrent_jobs, settings.document_busy_timeout_seconds,
                             settings.document_max_rss_mb * 1024 * 1024)


# Dense A4 text page (11 pt, single spacing) is ~2,200 extracted characters; used only to turn
# PII_DOCUMENT_MAX_TEXT_CHARS into a page estimate users understand (DOCUMENT_TOO_LONG).
CHARS_PER_PAGE = 2_200


def _error(status: int, code: str, message: str, headers: dict[str, str] | None = None,
           extra: dict[str, int] | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, "message": message, "safe": False,
                                                     **(extra or {})}, headers=headers)


def _check_text_length(chars: int) -> None:
    """Why: detection runs at ~1.1k chars/s, so an over-long document would only fail at the
    timeout after burning a slot for the full deadline; refusing it right after extraction
    answers in about a second and charges nothing.
    What: raises 422 DOCUMENT_TOO_LONG with max_chars, chars and estimated_max_pages when
    chars exceeds PII_DOCUMENT_MAX_TEXT_CHARS.
    Test: set the limit to 1000, post 1001 chars of text -> 422 with estimated_max_pages == 0.
    """
    max_chars = settings.document_max_text_chars
    if chars > max_chars:
        raise DocumentError(422, "DOCUMENT_TOO_LONG",
                            f"The document has {chars} characters of text; the limit is {max_chars}. "
                            "Split it into smaller parts.",
                            extra={"max_chars": max_chars, "chars": chars,
                                   "estimated_max_pages": max_chars // CHARS_PER_PAGE})


class _StreamAborted(Exception):
    """Content-free error raised to the ASGI server so it drops the connection mid-body."""


def _stream_pdf(doc, edits, deadline: float, slot: AdmissionSlot, done) -> StreamingResponse:
    """Why: a 200-page redaction must not be assembled in memory, yet a failure after the headers
    are sent can no longer change the status code.
    What: renders and sends one page at a time; on any failure the body stops before the PDF
    trailer and the connection is aborted (truncated chunked transfer, no `%%EOF`). The admission
    slot is released only after PDFium resources are closed.
    Test: make page 2 of 3 fail; the client sees a transport error and the received bytes do
    not end with `%%EOF`.
    """
    pages = doc.render_stream(edits, deadline)
    step_lock = threading.Lock()  # close() must never race a next() still running in a thread

    def step():
        with step_lock:
            return next(pages, None)

    def finish(completed: bool) -> None:
        try:
            with step_lock:
                pages.close()  # no-op once exhausted; otherwise closes the PDFium source
        finally:
            slot.release()
            done(completed)

    async def body():
        completed = False
        try:
            while (chunk := await asyncio.to_thread(step)) is not None:
                yield chunk
            completed = True
        except Exception as exc:
            logger.warning("document redact stream aborted: %s", type(exc).__name__)
            raise _StreamAborted() from None
        if completed:
            finish(True)

    return _SlotStreamingResponse(finish, body(), media_type=MEDIA_TYPES[DocumentFormat.PDF], headers={
        "Content-Disposition": 'attachment; filename="redacted.pdf"'})


class _SlotStreamingResponse(StreamingResponse):
    """Runs `finish(False)` once the ASGI call ends however it ends (never iterated, client gone,
    render failure); in a worker thread, because a page may still be rendering. Idempotent."""

    def __init__(self, finish, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._finish = finish

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            asyncio.get_running_loop().run_in_executor(None, self._finish, False)


async def _record_usage(usage: UsageService, api_key: ApiKey, tenant_id: str | None, policy: dict | None,
                        started: float, chars: int, entities: list, status: str, error_code: str | None) -> None:
    try:
        await usage.record(
            api_key_id=api_key.id, request_id=uuid.uuid4(),
            policy_id=(policy or {}).get("policy_id"), policy_version=(policy or {}).get("policy_version"),
            policy_hash=(policy or {}).get("policy_hash"), chars_in=chars, chars_out=chars if status == "ok" else 0,
            entities_count=len(entities), entity_types_summary=sorted({e.pii_type for e in entities}),
            latency_ms=int((time.perf_counter() - started) * 1000), status=status, error_code=error_code,
            tenant_id=tenant_id,
        )
    except Exception:
        logger.warning("document usage record failed")


async def _process(op: str, request: Request, fields: dict[str, str], payload: bytes, api_key: ApiKey,
                   db: AsyncSession, anonymizer: PiiAnonymizer, tenant_id: str | None,
                   usage: UsageService, state: dict, slot: AdmissionSlot) -> Response:
    doc = await asyncio.to_thread(load_document, payload, _limits())
    state["format"], state["pages"] = doc.format, doc.pages
    if op == Operation.PSEUDONYMIZE and doc.format == DocumentFormat.PDF:
        raise DocumentError(422, "PSEUDONYMIZE_NOT_SUPPORTED_FOR_PDF",
                            "PDF supports redact only; use DOCX or TXT for pseudonymization.")
    joined = JoinedText(doc.segments)
    _check_text_length(len(joined.text))
    state["chars"] = len(joined.text)
    await usage.ensure_within_limits(api_key, len(joined.text))

    domain = fields.get("domain") or None
    context_type = fields.get("context_type") or (None if domain else "generic")
    policy = await PolicyService(db, tenant_id=tenant_id).resolve(context_type=context_type, domain=domain)
    state["policy"] = policy
    if op != Operation.PREVIEW and "entities" in fields:
        entities = parse_user_entities(fields["entities"], joined.text)
    else:
        language = fields.get("language") or getattr(request.app.state, "default_language", "it")
        entities = await detect_protected_entities(
            anonymizer, policy, joined.text, str(uuid.uuid4()), domain or context_type or "generic", language,
            window=(settings.document_detection_window_chars, settings.document_detection_window_overlap,
                    state["deadline"]))
    entities = sorted(entities, key=lambda e: e.start)
    state["entities"] = entities
    types = sorted({e.pii_type for e in entities})
    sanitized = list(doc.SANITIZED)

    if op == Operation.PREVIEW:
        response: Response = JSONResponse({
            "format": doc.format, "pages": doc.pages, "text": joined.text,
            "entity_count": len(entities), "pii_types_found": types,
            "entities": [{"start": e.start, "end": e.end, "type": e.pii_type, "text": e.text,
                          "confidence": round(e.score, 4), "page": doc.page_of(joined.segment_at(e.start))}
                         for e in entities],
            "policy": {"id": policy["policy_id"], "version": policy["policy_version"], "hash": policy["policy_hash"]},
            "warnings": doc.warnings, "sanitized": sanitized,
        })
    elif op == Operation.REDACT and doc.format == DocumentFormat.PDF:
        response = _stream_pdf(doc, redaction_edits(joined, entities), state["deadline"], slot, state["stream_done"])
        state["streaming"] = True
    elif op == Operation.REDACT:
        content = await asyncio.to_thread(doc.render, redaction_edits(joined, entities))
        response = Response(content, media_type=MEDIA_TYPES[doc.format],
                            headers={"Content-Disposition": f'attachment; filename="redacted.{doc.format}"'})
    else:
        edits, mapping = pseudonymization_edits(joined, entities, policy["remove_types"])
        content = await asyncio.to_thread(doc.render, edits)
        archive = zip_pseudonymized(content, f"pseudonymized.{doc.format}", mapping)
        response = Response(archive, media_type="application/zip",
                            headers={"Content-Disposition": 'attachment; filename="pseudonymized.zip"'})
    response.headers.update({
        "Cache-Control": "no-store",
        "X-Pii-Document-Format": doc.format,
        "X-Pii-Entity-Count": str(len(entities)),
        "X-Pii-Types": ",".join(types),
        "X-Pii-Warnings": ",".join(doc.warnings),
        "X-Pii-Sanitized": ",".join(sanitized),
    })
    if doc.pages is not None:
        response.headers["X-Pseudora-Pages"] = str(doc.pages)
    return response


async def _handle(op: str, request: Request, api_key: ApiKey, db: AsyncSession,
                  anonymizer: PiiAnonymizer, tenant_id: str | None, admission: DocumentAdmission) -> Response:
    started = time.perf_counter()
    usage = UsageService(db)
    request_id = getattr(request.state, "request_id", None)

    def log_ok(completed: bool = True) -> None:
        if completed:
            logger.info(
                "document %s ok format=%s bytes=%d pages=%s entities=%d duration_ms=%d",
                op, state["format"], state["bytes"], state["pages"], len(state["entities"]),
                int((time.perf_counter() - started) * 1000), extra={"request_id": request_id},
            )

    state: dict = {"chars": 0, "bytes": 0, "entities": [], "policy": None, "format": None, "pages": None,
                   "deadline": time.monotonic() + settings.document_timeout_seconds, "stream_done": log_ok}
    error_code: str | None = None
    try:
        slot = await admission.acquire()
    except DocumentError as exc:
        raise _error(exc.status, exc.code, exc.message, exc.headers) from None
    try:
        upload = await read_document_upload(request, settings.document_upload_max_bytes)
        state["bytes"] = len(upload.payload)
        response = await asyncio.wait_for(
            _process(op, request, upload.fields, upload.payload, api_key, db, anonymizer, tenant_id, usage, state,
                     slot),
            timeout=settings.document_timeout_seconds,
        )
    except DocumentError as exc:
        raise _error(exc.status, exc.code, exc.message, exc.headers, exc.extra) from None
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        error_code = "DOCUMENT_PROCESSING_TIMEOUT"
        raise _error(504, error_code, "Document processing exceeded the time limit; no document was returned.") from None
    except Exception as exc:
        error_code = "PII_PROCESSING_FAILED"
        logger.warning("document %s failed closed: %s", op, type(exc).__name__, extra={"request_id": request_id})
        raise _error(503, error_code, "The document could not be safely processed; no document was returned.") from None
    finally:
        if not state.get("streaming"):
            slot.release()  # a streamed PDF releases its slot when the body is finished
        if error_code is not None and state["chars"]:
            await _record_usage(usage, api_key, tenant_id, state["policy"], started, state["chars"], [], "error", error_code)
    entities = state["entities"]
    await _record_usage(usage, api_key, tenant_id, state["policy"], started, state["chars"], entities, "ok", None)
    try:
        await AuditService(db, ip_anonymization=getattr(request.app.state, "ip_anonymization_enabled", True)).log(
            api_key_id=api_key.id, action=f"document_{op}", context_id=request_id,
            pii_types_found=sorted({e.pii_type for e in entities}), char_count=state["chars"], tenant_id=tenant_id,
            ip=request.client.host if request.client else None,
        )
    except Exception:
        logger.warning("document audit log failed")
    if not state.get("streaming"):
        log_ok()
    return response


def _endpoint(op: str, summary: str):
    async def endpoint(
        request: Request,
        api_key: ApiKey = Depends(require_service),
        db: AsyncSession = Depends(get_db),
        anonymizer: PiiAnonymizer = Depends(get_anonymizer),
        tenant_id: str | None = Depends(get_tenant_id),
        admission: DocumentAdmission = Depends(get_document_admission),
    ) -> Response:
        return await _handle(op, request, api_key, db, anonymizer, tenant_id, admission)

    endpoint.__name__ = f"document_{op}"
    router.add_api_route(f"/{op}", endpoint, methods=["POST"], summary=summary, openapi_extra=_OPENAPI_FORM)


_endpoint(Operation.PREVIEW, "Detect entities in a document without returning a document")
_endpoint(Operation.REDACT, "Irreversibly redact a PDF, DOCX or TXT document")
_endpoint(Operation.PSEUDONYMIZE, "Pseudonymize a DOCX or TXT document; returns a ZIP with mapping.json")
