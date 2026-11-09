"""Zero-retention document endpoints: preview, redact, pseudonymize.

Documents are processed entirely in memory. Content, filenames and mappings are
never stored or logged; only metadata (size, format, counts, timings) is
recorded. Every failure returns an error and never the original document,
independent of PII_FAILURE_MODE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.anonymization.anonymizer import PiiAnonymizer
from app.audit.audit_service import AuditService
from app.config import settings
from app.database import get_db
from app.documents.admission import AdmissionSlot, DocumentAdmission
from app.documents.chunking import detection_executor
from app.documents.models import IMAGE_FORMATS, MEDIA_TYPES, DocumentError, DocumentFormat, DocumentLimits, JoinedText
from app.documents.ocr_client import get_ocr_client
from app.documents.ocr_layout import Covers, FaceStyle
from app.documents.service import (
    MAX_USER_ENTITIES,
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
from app.routers._anonymize_logic import detect_protected_entities, get_anonymizer, with_protection_level
from app.surrogates.policy_service import PolicyService
from app.usage.service import UsageService

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)


class Operation:
    PREVIEW = "preview"
    REDACT = "redact"
    PSEUDONYMIZE = "pseudonymize"


_FORM_FIELDS = {
    "file": {"type": "string", "format": "binary", "description": "PDF, DOCX, UTF-8/cp1252 text file, or a JPEG/PNG/WebP "
                                                                   "image (redact/preview only; needs OCR)."},
    "domain": {"type": "string", "description": "Domain policy preset, e.g. hr_payroll, tax_accounting."},
    "context_type": {"type": "string", "description": "Context type (used when `domain` is absent; default generic)."},
    "language": {"type": "string", "description": "Detection language (default: engine default, usually it)."},
    "protection_level": {"type": "string", "enum": ["balanced", "maximum"], "default": "balanced",
                         "description": "balanced (default) or maximum: lower thresholds, recall-first rules."},
    "entities": {"type": "string", "description": "redact/pseudonymize only: JSON array of {start,end,type} "
                                                   "from /preview, edited by the user. Replaces detection."},
    "face_style": {"type": "string", "enum": ["black", "pixelate", "blur"], "default": "black",
                   "description": "redact only, images and scanned pages: how faces are hidden. black (default) is "
                                  "the safest; pixelate/blur keep at most 8x8 noisy, quantized colour cells per face "
                                  "(irreversible). Everything else is always painted black."},
    "review_keep": {"type": "string", "description": "redact only, images and scanned pages, review_default=cover: "
                                                     "JSON array of `needs_review` ids (from /preview) to leave "
                                                     "un-redacted. Default: every needs_review region is painted."},
    "review_default": {"type": "string", "enum": ["cover", "visible"], "default": "cover",
                       "description": "redact only: `cover` (default, legacy) paints every needs_review region not in "
                                      "review_keep; `visible` leaves them all visible except the ids in review_cover."},
    "review_cover": {"type": "string", "description": "redact only, review_default=visible: JSON array of "
                                                      "`needs_review` ids the user chose to cover."},
    "cover_boxes": {"type": "string", "description": "redact only, PDFs and images: JSON array (max 200) of user-drawn "
                                                     "areas {page (1-based), bbox: [x0, y0, x1, y1] fractions of the "
                                                     "displayed page} painted black in the output pixels."},
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
        ocr_enabled=settings.ocr_enabled,
        ocr_dpi=settings.ocr_dpi,
        image_max_pixels=settings.document_image_max_pixels,
        ocr_image_engine=settings.ocr_image_engine,
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


def check_pseudonymizable(document_format: str) -> None:
    if document_format == DocumentFormat.PDF:
        raise DocumentError(422, "PSEUDONYMIZE_NOT_SUPPORTED_FOR_PDF",
                            "PDF supports redact only; use DOCX or TXT for pseudonymization.")
    if document_format in IMAGE_FORMATS:
        raise DocumentError(422, "PSEUDONYMIZE_NOT_SUPPORTED_FOR_IMAGE",
                            "Images support redact only: text drawn in pixels cannot be replaced by tokens.")


def check_text_length(chars: int, max_chars: int | None = None) -> None:
    """Why: detection runs at ~1.1k chars/s, so an over-long document would only fail at the
    timeout after burning a slot for the full deadline; refusing it right after extraction
    answers in about a second and charges nothing.
    What: raises 422 DOCUMENT_TOO_LONG with max_chars, chars and estimated_max_pages when
    chars exceeds `max_chars` (jobs: PII_DOCUMENT_JOB_MAX_TEXT_CHARS), else PII_DOCUMENT_MAX_TEXT_CHARS.
    Test: set the limit to 1000, post 1001 chars of text -> 422 with estimated_max_pages == 0.
    """
    max_chars = max_chars or settings.document_max_text_chars
    if chars > max_chars:
        raise DocumentError(422, "DOCUMENT_TOO_LONG",
                            f"The document has {chars} characters of text; the limit is {max_chars}. "
                            "Split it into smaller parts.",
                            extra={"max_chars": max_chars, "chars": chars,
                                   "estimated_max_pages": max_chars // CHARS_PER_PAGE})


def ocr_pending(doc) -> list[int]:
    return list(getattr(doc, "ocr_pending", []))


def check_ocr_pages(doc, max_pages: int) -> None:
    """Why: OCR costs seconds per page; refuse over-long scans before spending any of it.
    What: 422 OCR_TOO_MANY_PAGES (with max_pages, ocr_pages) when the document has more
    scanned pages than `max_pages` (sync: PII_OCR_MAX_PAGES, jobs: PII_OCR_JOB_MAX_PAGES).
    Test: limit 1, a 2-page scan -> 422 and the OCR service is never called.
    """
    pending = len(ocr_pending(doc))
    if pending > max_pages:
        raise DocumentError(422, "OCR_TOO_MANY_PAGES",
                            f"The PDF has {pending} scanned pages; at most {max_pages} can be OCR'd. Split it.",
                            extra={"max_pages": max_pages, "ocr_pages": pending})


def run_ocr(doc, deadline: float, progress=None, should_stop=None) -> None:
    """Blocking (call in a thread): OCR the document's scanned pages with the process client."""
    client = get_ocr_client()
    if client is None:  # load_document only defers pages when OCR is enabled
        raise DocumentError(503, "OCR_UNAVAILABLE", "OCR is not configured; no document was returned.")
    doc.run_ocr(client, deadline, settings.ocr_concurrency, progress, should_stop)


class _StreamAborted(Exception):
    """Content-free error raised to the ASGI server so it drops the connection mid-body."""


def _stream_pdf(doc, edits, deadline: float, release, done, keep_review: frozenset[int] = frozenset(),
                face_style: str = FaceStyle.BLACK, covers: Covers | None = None) -> StreamingResponse:
    """Why: a 200-page redaction must not be assembled in memory, yet a failure after the headers
    are sent can no longer change the status code.
    What: renders and sends one page at a time; on any failure the body stops before the PDF
    trailer and the connection is aborted (truncated chunked transfer, no `%%EOF`). `release`
    (admission slot, or the job deletion) runs only after PDFium resources are closed.
    Test: make page 2 of 3 fail; the client sees a transport error and the received bytes do
    not end with `%%EOF`.
    """
    pages = doc.render_stream(edits, deadline, keep_review, face_style, covers)
    step_lock = threading.Lock()  # close() must never race a next() still running in a thread

    def step():
        with step_lock:
            return next(pages, None)

    def finish(completed: bool) -> None:
        try:
            with step_lock:
                pages.close()  # no-op once exhausted; otherwise closes the PDFium source
        finally:
            release()
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

    return _FinishStreamingResponse(finish, body(), media_type=MEDIA_TYPES[DocumentFormat.PDF], headers={
        "Content-Disposition": 'attachment; filename="redacted.pdf"'})


class _FinishStreamingResponse(StreamingResponse):
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
    face_style = parse_face_style(fields.get("face_style"))  # before any work: a bad value costs nothing
    redact = op == Operation.REDACT
    keep_review = parse_review_keep(fields.get("review_keep")) if redact else frozenset()
    review_cover = parse_json_field(fields.get("review_cover") if redact else None, _IDS, "INVALID_REVIEW_COVER",
                                    "`review_cover` must be a JSON array of needs_review ids.")
    cover_boxes = parse_json_field(fields.get("cover_boxes") if redact else None, _COVER_BOXES, "INVALID_COVER_BOXES",
                                   "`cover_boxes` must be a JSON array of {page, bbox: [x0, y0, x1, y1]} fractions.")
    review_default = (fields.get("review_default") if redact else None) or "cover"
    if review_default not in REVIEW_DEFAULTS:
        raise DocumentError(422, "INVALID_REVIEW_DEFAULT", "`review_default` must be cover or visible.")
    doc = await asyncio.to_thread(load_document, payload, _limits())
    state["format"], state["pages"] = doc.format, doc.pages
    if op == Operation.PSEUDONYMIZE:
        check_pseudonymizable(doc.format)
    if ocr_pending(doc):
        check_ocr_pages(doc, settings.ocr_max_pages)
        await asyncio.to_thread(run_ocr, doc, state["deadline"])
    joined = JoinedText(doc.segments)
    check_text_length(len(joined.text))
    state["chars"] = len(joined.text)
    await usage.ensure_within_limits(api_key, len(joined.text))

    domain = fields.get("domain") or None
    context_type = fields.get("context_type") or (None if domain else "generic")
    policy = await PolicyService(db, tenant_id=tenant_id).resolve(context_type=context_type, domain=domain)
    policy = with_protection_level(policy, fields.get("protection_level"))
    state["policy"] = policy
    if op != Operation.PREVIEW and "entities" in fields:
        entities = parse_user_entities(fields["entities"], joined.text)
    else:
        language = fields.get("language") or getattr(request.app.state, "default_language", "it")
        entities = await detect_protected_entities(
            anonymizer, policy, joined.text, str(uuid.uuid4()), domain or context_type or "generic", language,
            window=detection_window(state["deadline"]), executor=window_executor())
    entities = sorted(entities, key=lambda e: e.start)
    state["entities"] = entities
    if op == Operation.PREVIEW:
        return document_headers(JSONResponse(preview_payload(doc, joined, entities, policy)), doc, entities)
    keep_review, covers = review_plan(doc, keep_review, review_default, review_cover, cover_boxes)
    response = await render_document(op, doc, joined, entities, policy, state["deadline"], slot.release,
                                     state["stream_done"], keep_review, face_style, covers)
    state["streaming"] = isinstance(response, StreamingResponse)
    return response


def parse_face_style(raw: str | None) -> str:
    """Why: the field is untrusted and decides how faces are hidden. What: black (default),
    pixelate or blur; anything else is a 422. Test: None -> "black"; "sepia" -> 422."""
    try:
        return FaceStyle(raw or FaceStyle.BLACK).value
    except ValueError:
        raise DocumentError(422, "INVALID_FACE_STYLE", "`face_style` must be black, pixelate or blur.") from None


def parse_review_keep(raw: str | None) -> frozenset[int]:
    """Why: a client that reviewed the doubtful regions of a sync /preview (e.g. the desktop app's
    screenshot review) needs the same choice the job render offers, and the field is untrusted.
    What: JSON array of non-negative ints -> frozenset; absent/empty -> nothing kept (all painted);
    anything else is a 422 INVALID_REVIEW_KEEP before any work. Ids are checked against the
    OCR'd needs_review regions later (unknown id -> 422).
    Test: None -> frozenset(); "[1, 0]" -> {0, 1}; "[-1]", "[true]", "{}", "x" -> 422.
    """
    if not raw:
        return frozenset()
    try:
        items = json.loads(raw)
    except ValueError:
        items = None
    if (not isinstance(items, list) or len(items) > MAX_USER_ENTITIES
            or any(type(i) is not int or i < 0 for i in items)):
        raise DocumentError(422, "INVALID_REVIEW_KEEP", "`review_keep` must be a JSON array of needs_review ids.")
    return frozenset(items)


MAX_COVER_BOXES = 200
REVIEW_DEFAULTS = ("cover", "visible")


class CoverBox(BaseModel):
    """A user-drawn area to paint: 1-based page, [x0, y0, x1, y1] fractions of the displayed page."""

    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]

    @model_validator(mode="after")
    def _ordered(self) -> CoverBox:
        x0, y0, x1, y1 = self.bbox
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("bbox")
        return self


_COVER_BOXES = TypeAdapter(list[CoverBox])
_IDS = TypeAdapter(list[int])


def parse_json_field(raw: str | None, adapter: TypeAdapter, code: str, message: str):
    """Untrusted JSON form field -> validated value; absent/empty -> []; anything else 422 ``code``."""
    if not raw:
        return []
    try:
        return adapter.validate_json(raw)
    except ValidationError:
        raise DocumentError(422, code, message) from None


def review_plan(doc, keep: frozenset[int], default: str, cover_ids: list[int],
                boxes: list[CoverBox], code: str | None = None) -> tuple[frozenset[int], Covers]:
    """Why: whether doubtful regions are covered is the user's choice (founder decision 2026-11-09:
    shown by default in the new clients), and the areas they draw themselves must be real pixels
    in the output, never an overlay; legacy clients (no review_default) keep "all covered".
    What: -> (needs_review ids left visible, user areas by 0-based page). `cover`: ``keep`` as
    sent; `visible`: every id except ``cover_ids`` (``keep`` must then be empty). Unknown ids,
    pages out of range, >MAX_COVER_BOXES areas or areas on a DOCX/TXT -> 422 (``code``, default
    per field: INVALID_REVIEW_KEEP / INVALID_REVIEW_COVER / INVALID_COVER_BOXES).
    Test: 3 regions, visible + cover_ids [1] -> keep {0, 2}; a box on page 2 of a 1-page image -> 422.
    """
    count = len(doc.review_boxes()) if getattr(doc, "scanned", None) else 0
    if any(i < 0 or i >= count for i in keep) or (default == "visible" and keep):
        raise DocumentError(422, code or "INVALID_REVIEW_KEEP",
                            "`review_keep` contains an unknown needs_review id (or is sent with review_default=visible).")
    if len(cover_ids) > MAX_USER_ENTITIES or any(i < 0 or i >= count for i in cover_ids):
        raise DocumentError(422, code or "INVALID_REVIEW_COVER", "`review_cover` contains an unknown needs_review id.")
    paged = doc.format == DocumentFormat.PDF or doc.format in IMAGE_FORMATS
    if boxes and (not paged or len(boxes) > MAX_COVER_BOXES or any(b.page > (doc.pages or 0) for b in boxes)):
        raise DocumentError(422, code or "INVALID_COVER_BOXES",
                            f"`cover_boxes` takes at most {MAX_COVER_BOXES} areas on existing pages of a PDF or image.")
    covers: dict[int, list] = {}
    for box in boxes:
        covers.setdefault(box.page - 1, []).append(box.bbox)
    visible = frozenset(range(count)) - set(cover_ids) if default == "visible" else keep - set(cover_ids)
    return visible, covers


def detection_window(deadline: float) -> tuple[int, int, float]:
    return settings.document_detection_window_chars, settings.document_detection_window_overlap, deadline


def window_executor():
    """Shared window pool (PII_DOCUMENT_DETECTION_WORKERS) for sync documents and jobs."""
    return detection_executor(settings.document_detection_workers)


def preview_payload(doc, joined: JoinedText, entities: list, policy: dict) -> dict:
    """Why: /preview and GET /jobs/{id}/entities must return the same payload the UI reviews.
    What: format, pages, text, entities (with `id` = list index, used by job render `exclude`), policy;
    for scanned PDF pages also each entity's `boxes`, the `needs_review` regions and `ocr_pages`.
    Test: two entities -> ids 0 and 1, each with its page (PDF) or null (DOCX/TXT).
    """
    boxes = getattr(doc, "entity_boxes", None)
    scanned = getattr(doc, "scanned", {})
    return {
        "format": doc.format, "pages": doc.pages, "text": joined.text,
        "entity_count": len(entities), "pii_types_found": found_types(doc, entities),
        "entities": [{"id": i, "start": e.start, "end": e.end, "type": e.pii_type, "text": e.text,
                      "confidence": round(e.score, 4), "page": doc.page_of(joined.segment_at(e.start)),
                      "boxes": boxes(joined.split(e.start, e.end)) if boxes else []}
                     for i, e in enumerate(entities)],
        "ocr_pages": [index + 1 for index in sorted(scanned)],
        "needs_review": doc.review_boxes() if scanned else [],
        "visual_entities": doc.visual_entities() if scanned else [],
        "policy": {"id": policy["policy_id"], "version": policy["policy_version"], "hash": policy["policy_hash"]},
        "warnings": doc.warnings, "sanitized": list(doc.SANITIZED),
    }


async def render_document(op: str, doc, joined: JoinedText, entities: list, policy: dict, deadline: float,
                          release, done, keep_review: frozenset[int] = frozenset(),
                          face_style: str = FaceStyle.BLACK, covers: Covers | None = None) -> Response:
    """Why: sync redact/pseudonymize and job render must produce byte-identical files.
    What: streamed PDF redaction (`release`/`done` run when the body ends) or an in-memory
    DOCX/TXT/image redaction (images keep the `keep_review` regions visible) / pseudonymization
    ZIP, with the X-Pii-* headers. `face_style` (black|pixelate|blur) applies to faces on images
    and scanned PDF pages; `covers` (user areas by 0-based page) to every PDF page and images.
    Test: covered by the redact/pseudonymize endpoint tests and the job render tests.
    """
    if op == Operation.REDACT and doc.format == DocumentFormat.PDF:
        response: Response = _stream_pdf(doc, redaction_edits(joined, entities), deadline, release, done, keep_review,
                                         face_style, covers)
    elif op == Operation.REDACT:
        # images: needs_review left visible + how faces are hidden + the user's own areas
        review = (keep_review, face_style, covers) if doc.format in IMAGE_FORMATS else ()
        content = await asyncio.to_thread(doc.render, redaction_edits(joined, entities), *review)
        response = Response(content, media_type=MEDIA_TYPES[doc.format],
                            headers={"Content-Disposition": f'attachment; filename="redacted.{doc.format}"'})
    else:
        edits, mapping = pseudonymization_edits(joined, entities, policy["remove_types"])
        content = await asyncio.to_thread(doc.render, edits)
        archive = zip_pseudonymized(content, f"pseudonymized.{doc.format}", mapping)
        response = Response(archive, media_type="application/zip",
                            headers={"Content-Disposition": 'attachment; filename="pseudonymized.zip"'})
    return document_headers(response, doc, entities)


def found_types(doc, entities: list) -> list[str]:
    """Text entity types plus visual ones (FACE, BARCODE, LICENSE_PLATE) on scanned pages/images."""
    visual = doc.visual_types() if getattr(doc, "scanned", None) else set()
    return sorted({e.pii_type for e in entities} | visual)


def document_headers(response: Response, doc, entities: list) -> Response:
    response.headers.update({
        "Cache-Control": "no-store",
        "X-Pii-Document-Format": doc.format,
        "X-Pii-Entity-Count": str(len(entities)),
        "X-Pii-Types": ",".join(found_types(doc, entities)),
        "X-Pii-Warnings": ",".join(doc.warnings),
        "X-Pii-Sanitized": ",".join(doc.SANITIZED),
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
