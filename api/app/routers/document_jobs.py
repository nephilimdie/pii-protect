"""In-memory document jobs: upload once, poll progress, review entities, render one file.

POST /v1/documents/jobs -> 202 {job_id, status, format, pages_total}; GET /{id} -> progress;
GET /{id}/entities -> the /preview payload; POST /{id}/render -> the file (job deleted right
after delivery); DELETE /{id} -> 204. Jobs are scoped to tenant + API key + X-Pii-User-Id
(anything else -> 404 JOB_NOT_FOUND) and live only in this process's memory
(app.documents.jobs). Content, filenames and terms are never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.anonymization.anonymizer import PiiAnonymizer
from app.config import settings
from app.database import get_db
from app.documents.admission import DocumentAdmission
from app.documents.chunking import DetectionCancelled
from app.documents.jobs import DocumentJob, DocumentJobStore, JobStatus, Owner, corrected_entities
from app.documents.models import DocumentError, JoinedText
from app.documents.service import MAX_USER_ENTITIES, UserEntity, load_document, parse_user_entities
from app.documents.upload import read_document_upload
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.identity.tenant import get_tenant_id
from app.routers import documents as docs
from app.routers._anonymize_logic import detect_protected_entities, get_anonymizer, with_protection_level

router = APIRouter(prefix="/documents/jobs", tags=["Document jobs"])
logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()  # strong references to running analyses
_NOT_FOUND = ("JOB_NOT_FOUND", "No such document job (it may have been delivered, deleted or expired).")
_TERM_TYPE = r"^[A-Z][A-Z0-9_]*$"


@lru_cache(maxsize=1)
def get_document_job_store() -> DocumentJobStore:
    """Process-wide job store (FastAPI dependency; override in tests)."""
    return DocumentJobStore(settings.document_max_jobs, settings.document_max_job_bytes_total,
                            settings.document_job_ttl_seconds, settings.document_max_concurrent_jobs)


def session_factory():
    """DB session for work that outlives the request (usage + audit when an analysis ends)."""
    from app.database import AsyncSessionLocal
    return AsyncSessionLocal()


def _owner(request: Request, api_key: ApiKey, tenant_id: str | None) -> Owner:
    user = request.headers.get("x-pii-user-id", "")
    if len(user) > 128:
        raise docs._error(422, "INVALID_USER_ID", "X-Pii-User-Id must be at most 128 characters.")
    return tenant_id, str(api_key.id), user


def _job(store: DocumentJobStore, job_id: str, owner: Owner) -> DocumentJob:
    job = store.get(job_id, owner)
    if job is None:
        raise docs._error(404, *_NOT_FOUND)
    return job


def _not_ready(job: DocumentJob) -> HTTPException:
    return docs._error(409, "JOB_NOT_READY", f"The job is {job.status}; entities and rendering need `ready`.")


class IncludeTerm(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    type: str = Field(min_length=1, max_length=64, pattern=_TERM_TYPE)


class RenderRequest(BaseModel):
    mode: Literal["redact", "pseudonymize"]
    exclude: list[int] = Field(default_factory=list, max_length=MAX_USER_ENTITIES)
    include_terms: list[IncludeTerm] = Field(default_factory=list, max_length=500)
    entities: list[UserEntity] | None = Field(default=None, max_length=MAX_USER_ENTITIES)
    review_keep: list[int] = Field(default_factory=list, max_length=MAX_USER_ENTITIES)  # needs_review ids left visible
    face_style: Literal["black", "pixelate", "blur"] = "black"  # faces on images/scans; black is the safest


async def _finish_analysis(api_key: ApiKey, tenant_id: str | None, job_id: str, policy: dict, chars: int,
                           entities: list, started: float, error_code: str | None) -> None:
    try:
        async with session_factory() as db:
            await docs._record_usage(docs.UsageService(db), api_key, tenant_id, policy, started, chars, entities,
                                     "error" if error_code else "ok", error_code)
            if error_code is None:
                await docs.AuditService(db).log(
                    api_key_id=api_key.id, action="document_job_analyze", context_id=job_id,
                    pii_types_found=sorted({e.pii_type for e in entities}), char_count=chars, tenant_id=tenant_id)
    except Exception:
        logger.warning("document job usage/audit record failed")


def _set_ocr_progress(job: DocumentJob):
    def progress(done: int) -> None:
        job.ocr_pages_done = done
    return progress


async def _ocr(job: DocumentJob, doc, deadline: float) -> str:
    """OCR the scanned pages (progress in ocr_pages_done), then fix the text and its limits."""
    await asyncio.to_thread(docs.run_ocr, doc, deadline, _set_ocr_progress(job), job.cancelled.is_set)
    if job.cancelled.is_set():
        raise DetectionCancelled()
    joined = JoinedText(doc.segments)
    docs.check_text_length(len(joined.text), settings.document_job_max_text_chars)
    job.joined, job.chars_total = joined, len(joined.text)
    return joined.text


async def _analyze(store: DocumentJobStore, job: DocumentJob, anonymizer: PiiAnonymizer, text: str,
                   policy: dict, api_key: ApiKey, tenant_id: str | None) -> None:
    """Why: OCR + detection of a long document take minutes; they run detached from any request.
    What: waits for an analysis slot (`queued`), OCRs scanned PDF pages, detects in parallel
    windows with progress (`analyzing`), stops before the next page/window once the job is
    cancelled/expired, and ends `ready` with the entities or as a content-free `failed` tombstone.
    Test: see tests/unit/test_document_jobs.py (lifecycle, cancel, failure) and test_documents_ocr.py.
    """
    started, error_code = time.perf_counter(), None
    entities: list = []
    deadline = time.monotonic() + settings.document_job_ttl_seconds
    try:
        async with store.analysis_slot():
            if job.cancelled.is_set():
                return
            job.status = JobStatus.ANALYZING
            doc = job.doc
            if doc is not None and docs.ocr_pending(doc):
                text = await _ocr(job, doc, deadline)
            entities = await detect_protected_entities(
                anonymizer, policy, text, str(uuid.uuid4()), job.context, job.language,
                window=docs.detection_window(deadline),
                executor=docs.window_executor(), progress=job.progress, should_stop=job.cancelled.is_set)
    except DetectionCancelled:
        logger.info("document job cancelled during analysis")
        return
    except DocumentError as exc:  # OCR failure (fail closed) or over-long OCR text
        error_code = exc.code
        store.fail(job, exc.code, exc.message)
    except HTTPException as exc:  # policy refusal, e.g. 422 PII_BLOCKED
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        error_code = str(detail.get("error", "PII_PROCESSING_FAILED"))
        store.fail(job, error_code, str(detail.get("message", "The document could not be processed.")))
    except TimeoutError:
        error_code = "DOCUMENT_PROCESSING_TIMEOUT"
        store.fail(job, error_code, "Document analysis exceeded the time limit.")
    except Exception as exc:
        error_code = "PII_PROCESSING_FAILED"
        logger.warning("document job analysis failed closed: %s", type(exc).__name__)
        store.fail(job, error_code, "The document could not be safely processed.")
    else:
        if job.cancelled.is_set():
            return
        job.entities = sorted(entities, key=lambda e: e.start)
        job.chars_done, job.pages_done, job.status = job.chars_total, job.pages_total, JobStatus.READY
        logger.info("document job ready format=%s pages=%s chars=%d entities=%d duration_ms=%d", job.format,
                    job.pages_total, job.chars_total, len(entities), int((time.perf_counter() - started) * 1000))
    await _finish_analysis(api_key, tenant_id, job.id, policy, len(text), entities, started, error_code)


@router.post("", status_code=202, summary="Upload a document and start an in-memory analysis job",
             openapi_extra=docs._OPENAPI_FORM)
async def create_document_job(
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
    tenant_id: str | None = Depends(get_tenant_id),
    admission: DocumentAdmission = Depends(docs.get_document_admission),
    store: DocumentJobStore = Depends(get_document_job_store),
) -> JSONResponse:
    owner = _owner(request, api_key, tenant_id)
    job = None
    try:
        store.check_owner(owner)
        slot = await admission.acquire()  # bounds uploads + extraction in memory, like the sync endpoints
        try:
            upload = await read_document_upload(request, settings.document_upload_max_bytes)
            job = store.reserve(owner, len(upload.payload))
            doc = await asyncio.to_thread(load_document, upload.payload, docs._limits())
            joined = JoinedText(doc.segments)
            docs.check_text_length(len(joined.text), settings.document_job_max_text_chars)
            scanned = len(docs.ocr_pending(doc))
            docs.check_ocr_pages(doc, settings.ocr_job_max_pages)
            await docs.UsageService(db).ensure_within_limits(api_key, len(joined.text) + scanned * docs.CHARS_PER_PAGE)
            domain = upload.fields.get("domain") or None
            context_type = upload.fields.get("context_type") or (None if domain else "generic")
            policy = await docs.PolicyService(db, tenant_id=tenant_id).resolve(context_type=context_type, domain=domain)
            policy = with_protection_level(policy, upload.fields.get("protection_level"))
        finally:
            slot.release()
    except Exception as exc:
        if job is not None:
            store.delete(job)
        if isinstance(exc, DocumentError):
            raise docs._error(exc.status, exc.code, exc.message, exc.headers, exc.extra) from None
        if isinstance(exc, HTTPException):
            raise
        logger.warning("document job upload failed closed: %s", type(exc).__name__)
        raise docs._error(503, "PII_PROCESSING_FAILED", "The document could not be safely processed.") from None
    job.doc, job.joined, job.policy, job.format = doc, joined, policy, doc.format
    job.pages_total, job.chars_total, job.ocr_pages_total = doc.pages or 0, len(joined.text), scanned
    job.bytes = len(upload.payload) + 2 * len(joined.text)  # payload (PDF source) + segments + joined text
    job.language = upload.fields.get("language") or getattr(request.app.state, "default_language", "it")
    job.context = domain or context_type or "generic"
    task = asyncio.get_running_loop().create_task(
        _analyze(store, job, anonymizer, joined.text, policy, api_key, tenant_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    logger.info("document job created format=%s bytes=%d pages=%s chars=%d", job.format, len(upload.payload),
                doc.pages, job.chars_total)
    return JSONResponse({"job_id": job.id, "status": job.status, "format": job.format,
                         "pages_total": job.pages_total}, status_code=202, headers={"Cache-Control": "no-store"})


@router.get("/{job_id}", summary="Document job status and progress")
async def get_document_job(job_id: str, request: Request, api_key: ApiKey = Depends(require_service),
                           tenant_id: str | None = Depends(get_tenant_id),
                           store: DocumentJobStore = Depends(get_document_job_store)) -> JSONResponse:
    job = _job(store, job_id, _owner(request, api_key, tenant_id))
    return JSONResponse(job.public(), headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/entities", summary="Detected entities of a ready job (the /preview payload)")
async def get_document_job_entities(job_id: str, request: Request, api_key: ApiKey = Depends(require_service),
                                    tenant_id: str | None = Depends(get_tenant_id),
                                    store: DocumentJobStore = Depends(get_document_job_store)) -> Response:
    job = _job(store, job_id, _owner(request, api_key, tenant_id))
    doc, joined, entities, policy = job.doc, job.joined, job.entities, job.policy
    if job.status != JobStatus.READY or doc is None or joined is None or entities is None or policy is None:
        raise _not_ready(job)
    return docs.document_headers(JSONResponse(docs.preview_payload(doc, joined, entities, policy)), doc, entities)


async def _render_request(request: Request) -> RenderRequest:
    try:
        return RenderRequest.model_validate_json(await request.body())
    except ValidationError:  # the error text would echo terms: fixed message only
        raise DocumentError(422, "INVALID_RENDER_REQUEST",
                            "Send JSON {mode: redact|pseudonymize, exclude: [ids], include_terms: [{text, type}]}.") from None


@router.post("/{job_id}/render", summary="Render the reviewed document once; the job is deleted after delivery")
async def render_document_job(
    job_id: str,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    tenant_id: str | None = Depends(get_tenant_id),
    store: DocumentJobStore = Depends(get_document_job_store),
) -> Response:
    job = _job(store, job_id, _owner(request, api_key, tenant_id))
    doc, joined, detected, policy = job.doc, job.joined, job.entities, job.policy
    try:
        body = await _render_request(request)
        if job.status != JobStatus.READY or doc is None or joined is None or detected is None or policy is None:
            raise _not_ready(job)
        if body.mode == docs.Operation.PSEUDONYMIZE:
            docs.check_pseudonymizable(doc.format)
        if body.entities is not None:
            if body.exclude or body.include_terms:
                raise DocumentError(422, "INVALID_RENDER_REQUEST", "`entities` replaces `exclude`/`include_terms`.")
            entities = parse_user_entities(json.dumps([e.model_dump() for e in body.entities]), joined.text)
        else:
            entities = corrected_entities(joined.text, detected, body.exclude,
                                          [(t.text, t.type) for t in body.include_terms])
        review_count = len(doc.review_boxes()) if getattr(doc, "scanned", None) else 0
        if any(index < 0 or index >= review_count for index in body.review_keep):
            raise DocumentError(422, "INVALID_RENDER_REQUEST", "`review_keep` contains an unknown needs_review id.")
    except DocumentError as exc:
        raise docs._error(exc.status, exc.code, exc.message, exc.headers, exc.extra) from None
    job.status = JobStatus.RENDERING
    started = time.perf_counter()

    def delivered(completed: bool) -> None:
        if completed:
            logger.info("document job %s delivered format=%s entities=%d duration_ms=%d", body.mode, doc.format,
                        len(entities), int((time.perf_counter() - started) * 1000))

    try:
        response = await docs.render_document(body.mode, doc, joined, entities, policy,
                                              time.monotonic() + settings.document_timeout_seconds,
                                              lambda: store.delete(job), delivered, frozenset(body.review_keep),
                                              body.face_style)
    except Exception as exc:
        store.delete(job)
        logger.warning("document job render failed closed: %s", type(exc).__name__)
        raise docs._error(503, "PII_PROCESSING_FAILED",
                          "The document could not be safely rendered; no document was returned.") from None
    if not isinstance(response, StreamingResponse):
        store.delete(job)  # the file is fully in the response: nothing of the job is needed any more
        delivered(True)
    try:
        await docs.AuditService(db, ip_anonymization=getattr(request.app.state, "ip_anonymization_enabled", True)).log(
            api_key_id=api_key.id, action=f"document_job_{body.mode}", context_id=job.id,
            pii_types_found=sorted({e.pii_type for e in entities}), char_count=len(joined.text), tenant_id=tenant_id,
            ip=request.client.host if request.client else None)
    except Exception:
        logger.warning("document job audit log failed")
    return response


@router.delete("/{job_id}", status_code=204, summary="Cancel a document job and delete it from memory")
async def delete_document_job(job_id: str, request: Request, api_key: ApiKey = Depends(require_service),
                              tenant_id: str | None = Depends(get_tenant_id),
                              store: DocumentJobStore = Depends(get_document_job_store)) -> Response:
    store.delete(_job(store, job_id, _owner(request, api_key, tenant_id)))
    return Response(status_code=204)
