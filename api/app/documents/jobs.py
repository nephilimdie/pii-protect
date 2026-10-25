"""In-memory document jobs: one uploaded document analysed in the background, reviewed, rendered once.

Nothing is persisted: a job lives only in this process's RAM and is deleted as soon as its
file has been delivered, when it fails (a content-free tombstone keeps only status + error
code so polling sees `failed`), when it is cancelled, or when it is abandoned for
PII_DOCUMENT_JOB_TTL_SECONDS. A restart therefore forgets every job (404 JOB_NOT_FOUND).
"""

from __future__ import annotations

import asyncio
import bisect
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.detection.entities import PiiEntity
from app.documents.models import DocumentError, JoinedText, LoadedDocument


class JobStatus:
    QUEUED = "queued"
    ANALYZING = "analyzing"
    READY = "ready"
    RENDERING = "rendering"
    FAILED = "failed"
    EXPIRED = "expired"


LIVE = frozenset({JobStatus.QUEUED, JobStatus.ANALYZING, JobStatus.READY, JobStatus.RENDERING})
Owner = tuple[str | None, str, str]  # (tenant id, API key id, X-Pii-User-Id)


@dataclass(eq=False)
class DocumentJob:
    """One job. Content fields (doc, joined, entities, policy) are dropped on any terminal state."""

    id: str
    owner: Owner
    bytes: int
    expires_at: float
    format: str | None = None
    status: str = JobStatus.QUEUED
    pages_total: int = 0
    pages_done: int = 0
    chars_total: int = 0
    chars_done: int = 0
    error: dict[str, str] | None = None
    doc: LoadedDocument | None = None
    joined: JoinedText | None = None
    entities: list[PiiEntity] | None = None
    policy: dict | None = None
    language: str = "it"
    context: str = "generic"
    cancelled: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {"job_id": self.id, "status": self.status, "pages_done": self.pages_done,
                "pages_total": self.pages_total, "chars_done": self.chars_done,
                "chars_total": self.chars_total, "error": self.error}

    def progress(self, chars_done: int, covered_end: int) -> None:
        """Window-pool callback: chars analysed so far; pages fully covered by finished windows."""
        self.chars_done = min(chars_done, self.chars_total)
        if self.joined is None or self.doc is None or not self.pages_total:
            return
        if covered_end >= self.chars_total:
            self.pages_done = self.pages_total
        else:
            page = self.doc.page_of(self.joined.segment_at(covered_end)) or 1
            self.pages_done = max(self.pages_done, page - 1)

    def drop_content(self) -> None:
        self.cancelled.set()  # stops pending detection windows
        self.doc = self.joined = self.entities = self.policy = None
        self.bytes = 0


def _busy(message: str, retry_after: int) -> DocumentError:
    return DocumentError(503, "ENGINE_BUSY", message, {"Retry-After": str(retry_after)})


class DocumentJobStore:
    """Why: long documents outlive one HTTP request, but must never touch disk or a database
    and must not pile up in memory.
    What: a per-process dict of jobs with admission limits (1 live job per owner -> 409
    JOB_ALREADY_ACTIVE; at most `max_jobs` live jobs and `max_bytes` held -> 503 ENGINE_BUSY),
    TTL expiry, owner-scoped lookup and a semaphore bounding concurrent analyses.
    Test: DocumentJobStore(1, 10**6, 60).reserve(owner, 10) twice for the same owner -> 409;
    for another owner -> 503; get() with another owner -> None.
    """

    def __init__(self, max_jobs: int, max_bytes: int, ttl_seconds: float, max_analyses: int = 2,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._max_jobs, self._max_bytes, self._ttl, self._clock = max_jobs, max_bytes, ttl_seconds, clock
        self._jobs: dict[str, DocumentJob] = {}
        self._lock = threading.Lock()
        self._max_analyses = max_analyses
        self._analyses: asyncio.Semaphore | None = None
        self._sweeper: asyncio.Task | None = None
        self.retry_after_seconds = 30

    def analysis_slot(self) -> asyncio.Semaphore:
        """Bounds jobs analysing at once (each blocks one loop-executor thread); others stay `queued`."""
        if self._analyses is None:
            self._analyses = asyncio.Semaphore(self._max_analyses)
        return self._analyses

    def _live(self) -> list[DocumentJob]:
        return [job for job in self._jobs.values() if job.status in LIVE]

    def sweep(self) -> None:
        """Expire live jobs past their TTL (content dropped, `expired` tombstone kept one more TTL)."""
        now = self._clock()
        with self._lock:
            for job in list(self._jobs.values()):
                if now < job.expires_at:
                    continue
                if job.status in LIVE:
                    job.drop_content()
                    job.status, job.expires_at = JobStatus.EXPIRED, now + self._ttl
                    job.error = {"error": "JOB_EXPIRED", "message": "The job was not completed in time."}
                else:
                    del self._jobs[job.id]

    def check_owner(self, owner: Owner) -> None:
        self.sweep()
        if any(job.owner == owner for job in self._live()):
            raise DocumentError(409, "JOB_ALREADY_ACTIVE",
                                "Another document job of this user is still active; finish or delete it first.")

    def reserve(self, owner: Owner, size: int) -> DocumentJob:
        """Atomically checks the limits and registers a queued job holding `size` bytes."""
        self.sweep()
        with self._lock:
            live = self._live()
            if any(job.owner == owner for job in live):
                raise DocumentError(409, "JOB_ALREADY_ACTIVE",
                                    "Another document job of this user is still active; finish or delete it first.")
            if len(live) >= self._max_jobs:
                raise _busy("Too many document jobs are in progress; retry later.", self.retry_after_seconds)
            if sum(job.bytes for job in live) + size > self._max_bytes:
                raise _busy("The engine holds too many documents; retry later.", self.retry_after_seconds)
            job = DocumentJob(id=secrets.token_urlsafe(24), owner=owner, bytes=size,
                              expires_at=self._clock() + self._ttl)
            self._jobs[job.id] = job
        self._ensure_sweeper()
        return job

    def get(self, job_id: str, owner: Owner) -> DocumentJob | None:
        self.sweep()
        job = self._jobs.get(job_id)
        return job if job is not None and job.owner == owner else None

    def fail(self, job: DocumentJob, code: str, message: str) -> None:
        with self._lock:
            if job.status not in LIVE or self._jobs.get(job.id) is not job:
                return  # already expired or deleted
            job.drop_content()
            job.status, job.error, job.expires_at = JobStatus.FAILED, {"error": code, "message": message}, \
                self._clock() + self._ttl

    def delete(self, job: DocumentJob) -> None:
        """Idempotent: drops content, stops detection and forgets the id (later calls -> 404)."""
        with self._lock:
            job.drop_content()
            if self._jobs.get(job.id) is job:
                del self._jobs[job.id]

    def __len__(self) -> int:
        return len(self._jobs)

    def _ensure_sweeper(self) -> None:
        """Expires abandoned jobs even when nobody polls; ends once the store is empty."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._sweeper is not None and not self._sweeper.done():
            return

        async def run() -> None:
            while self._jobs:
                await asyncio.sleep(min(30.0, max(0.05, self._ttl / 10)))
                self.sweep()

        self._sweeper = loop.create_task(run())


def corrected_entities(text: str, detected: list[PiiEntity], exclude: list[int],
                       include_terms: list[tuple[str, str]]) -> list[PiiEntity]:
    """Why: the review step unticks detected entities and adds terms the detector missed; the
    file must contain exactly that selection (same rules as the cloud UI's addTerm).
    What: drops detected entities whose index is in `exclude`, then adds every
    case-insensitive occurrence of each (text, type) term that overlaps no kept/added span.
    Raises 422 INVALID_ENTITIES for an unknown index.
    Test: text "Anna e anna", detected [] and term ("anna", "PERSON") -> two PERSON entities.
    """
    if any(index < 0 or index >= len(detected) for index in exclude):
        raise DocumentError(422, "INVALID_ENTITIES", "`exclude` contains an unknown entity id.")
    dropped = set(exclude)
    chosen = [entity for index, entity in enumerate(detected) if index not in dropped]
    spans = sorted((e.start, e.end) for e in chosen)
    for term, pii_type in include_terms:
        for match in re.finditer(re.escape(term), text, re.IGNORECASE):
            start, end = match.span()
            at = bisect.bisect_left(spans, (start, end))
            if (at and spans[at - 1][1] > start) or (at < len(spans) and spans[at][0] < end):
                continue
            spans.insert(at, (start, end))
            chosen.append(PiiEntity(start, end, pii_type, match.group(), 1.0, "user"))
    return sorted(chosen, key=lambda e: e.start)
