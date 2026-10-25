"""Admission control for heavy document jobs (per worker process).

Text endpoints are not affected. A document job holds one slot from before the
upload is buffered until its response body is fully sent (streamed PDFs
included), so at most `slots` documents are in memory per worker.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable

from app.documents.models import DocumentError

_POLL_SECONDS = 0.05


def current_rss_bytes() -> int | None:
    """Resident set size of this process (Linux /proc); None where unavailable."""
    try:
        with open("/proc/self/statm", "rb") as statm:
            return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None


class AdmissionSlot:
    """One acquired job slot; release() is idempotent and safe from any thread."""

    def __init__(self, semaphore: threading.Semaphore) -> None:
        self._semaphore = semaphore
        self._lock = threading.Lock()
        self._held = True

    def release(self) -> None:
        with self._lock:
            if self._held:
                self._held = False
                self._semaphore.release()


class DocumentAdmission:
    """Why: N concurrent 200-page documents must not exhaust worker memory; excess load must
    get a fast, retryable 503 instead of queueing until the client times out.
    What: a process-wide semaphore with a short async acquire timeout plus an optional RSS
    ceiling; refusals raise DocumentError(503, "ENGINE_BUSY") with a Retry-After hint.
    Test: DocumentAdmission(1, 0.1, 0): first acquire() succeeds, a second raises 503
    ENGINE_BUSY until the first slot is released.
    """

    def __init__(self, slots: int, acquire_timeout: float, max_rss_bytes: int,
                 rss: Callable[[], int | None] = current_rss_bytes) -> None:
        self._semaphore = threading.Semaphore(slots)
        self._timeout = acquire_timeout
        self._max_rss = max_rss_bytes
        self._rss = rss
        self.retry_after_seconds = max(1, int(acquire_timeout) + 1)

    def _busy(self, message: str) -> DocumentError:
        return DocumentError(503, "ENGINE_BUSY", message, {"Retry-After": str(self.retry_after_seconds)})

    async def acquire(self) -> AdmissionSlot:
        if self._max_rss and (rss := self._rss()) is not None and rss > self._max_rss:
            raise self._busy("The engine is low on memory; retry the document later.")
        deadline = time.monotonic() + self._timeout
        while not self._semaphore.acquire(blocking=False):
            if time.monotonic() >= deadline:
                raise self._busy("Too many documents are being processed; retry later.")
            await asyncio.sleep(_POLL_SECONDS)
        return AdmissionSlot(self._semaphore)
