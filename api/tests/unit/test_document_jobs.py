"""In-memory document jobs (/v1/documents/jobs): lifecycle, deletion after delivery, cancel,
TTL, isolation, limits, restart, failures, zero retention, parallel == sequential windows.
All documents are synthetic; detection is the deterministic fake of test_documents."""

from __future__ import annotations

import builtins
import contextlib
import io
import json
import logging
import os
import re
import tempfile
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.detection.entities import PiiEntity
from app.documents import chunking, pdf_handler
from app.documents.jobs import DocumentJobStore, corrected_entities
from app.documents.pdf_writer import EOF_MARKER
from app.identity.tenant import get_tenant_id
from app.routers import document_jobs as jobs_module
from tests.unit.test_documents import (  # noqa: F401  (fixture reuse)
    EMAIL, FISCAL, PERSON, SAMPLE_PII, SECRET_FILENAME, TXT, env, make_docx, make_pdf)

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
STATUSES = {"queued", "analyzing", "ready", "rendering", "failed", "expired"}


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def jobs(env, monkeypatch):
    env.clock = Clock()
    env.store = DocumentJobStore(max_jobs=20, max_bytes=10**9, ttl_seconds=900, max_analyses=2, clock=env.clock)
    app = env.client.app
    app.include_router(jobs_module.router, prefix="/v1")
    app.dependency_overrides[jobs_module.get_document_job_store] = lambda: env.store

    @contextlib.asynccontextmanager
    async def no_db():
        yield None

    monkeypatch.setattr(jobs_module, "session_factory", no_db)
    with TestClient(app) as client:  # one event loop for the client's lifetime: analyses keep running
        env.jobs = client
        yield env


def _create(env, payload, user="u1", filename="documento", **fields):
    return env.jobs.post("/v1/documents/jobs", files={"file": (filename, payload)}, data=fields,
                         headers={"X-Pii-User-Id": user})


def _get(env, path, user="u1"):
    return env.jobs.get(f"/v1/documents/jobs/{path}", headers={"X-Pii-User-Id": user})


def _render(env, job_id, user="u1", **body):
    return env.jobs.post(f"/v1/documents/jobs/{job_id}/render", json={"mode": "redact", **body},
                         headers={"X-Pii-User-Id": user})


def _wait(env, job_id, until=("ready", "failed"), user="u1", timeout=10.0):
    deadline = time.monotonic() + timeout
    while True:
        status = _get(env, job_id, user).json()
        if status["status"] in until or time.monotonic() > deadline:
            return status
        time.sleep(0.01)


def _ready_job(env, payload=TXT, user="u1"):
    created = _create(env, payload, user=user, domain="hr_payroll")
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    assert _wait(env, job_id, user=user)["status"] == "ready"
    return job_id


# ── lifecycle ────────────────────────────────────────────────────────────────

def test_txt_job_lifecycle_and_delete_after_delivery(jobs):
    created = _create(jobs, TXT, domain="hr_payroll")
    assert created.status_code == 202
    body = created.json()
    assert set(body) == {"job_id", "status", "format", "pages_total"}
    assert ID_PATTERN.match(body["job_id"]) and body["status"] in STATUSES
    assert body["format"] == "txt" and body["pages_total"] == 0
    status = _wait(jobs, body["job_id"])
    assert set(status) == {"job_id", "status", "pages_done", "pages_total", "chars_done", "chars_total", "error"}
    assert status["status"] == "ready" and status["error"] is None
    assert status["chars_done"] == status["chars_total"] == len(TXT.decode())

    preview = _get(jobs, f"{body['job_id']}/entities")
    assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
    entities = preview.json()["entities"]
    assert [e["id"] for e in entities] == list(range(len(entities))) and {e["text"] for e in entities} == {
        PERSON, FISCAL, EMAIL}

    rendered = _render(jobs, body["job_id"])
    assert rendered.status_code == 200
    assert not any(v in rendered.content.decode() for v in SAMPLE_PII)
    for path in (body["job_id"], f"{body['job_id']}/entities"):
        gone = _get(jobs, path)
        assert gone.status_code == 404 and gone.json()["error"] == "JOB_NOT_FOUND"  # flat error shape
    assert _render(jobs, body["job_id"]).status_code == 404 and len(jobs.store) == 0


def test_pdf_job_streams_redaction_and_is_deleted_after_the_stream(jobs):
    created = _create(jobs, make_pdf(pages=3))
    assert created.json()["format"] == "pdf" and created.json()["pages_total"] == 3
    job_id = created.json()["job_id"]
    status = _wait(jobs, job_id)
    assert status["pages_done"] == status["pages_total"] == 3
    rendered = _render(jobs, job_id)
    assert rendered.status_code == 200 and rendered.content.rstrip().endswith(EOF_MARKER)
    assert rendered.headers["x-pseudora-pages"] == "3"
    assert _get(jobs, job_id).status_code == 404 and len(jobs.store) == 0


def test_render_applies_exclude_and_include_terms(jobs):
    job_id = _ready_job(jobs)
    entities = _get(jobs, f"{job_id}/entities").json()["entities"]
    fiscal = next(e["id"] for e in entities if e["type"] == "FISCAL_CODE")
    r = _render(jobs, job_id, mode="pseudonymize", exclude=[fiscal],
                include_terms=[{"text": "busta paga", "type": "SECRET"}])
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        text = archive.read("pseudonymized.txt").decode()
        mapping = json.loads(archive.read("mapping.json"))["entities"]
    assert FISCAL in text and PERSON not in text and "busta paga" not in text
    assert {m["type"] for m in mapping} == {"PERSON", "EMAIL", "SECRET"}


def test_corrected_entities_add_every_free_occurrence_case_insensitively():
    text = "Anna e anna e ANNA Rossi"
    kept = [PiiEntity(13, 24, "PERSON", "ANNA Rossi", 0.9, "fake")]
    out = corrected_entities(text, kept, [], [("anna", "PERSON")])
    assert [(e.start, e.end) for e in out] == [(0, 4), (7, 11), (13, 24)]
    assert corrected_entities(text, kept, [0], []) == []


def test_invalid_render_requests_keep_the_job_and_do_not_echo_terms(jobs):
    job_id = _ready_job(jobs)
    bad = jobs.jobs.post(f"/v1/documents/jobs/{job_id}/render", json={"mode": "x", "include_terms": [
        {"text": PERSON, "type": "bad type"}]}, headers={"X-Pii-User-Id": "u1"})
    assert bad.status_code == 422 and bad.json()["error"] == "INVALID_RENDER_REQUEST" and PERSON not in bad.text
    assert _render(jobs, job_id, exclude=[999]).json()["error"] == "INVALID_ENTITIES"
    assert _get(jobs, job_id).json()["status"] == "ready"
    assert jobs.jobs.delete(f"/v1/documents/jobs/{job_id}", headers={"X-Pii-User-Id": "u1"}).status_code == 204
    pdf_job = _ready_job(jobs, make_pdf())
    refused = _render(jobs, pdf_job, mode="pseudonymize")
    assert refused.status_code == 422 and refused.json()["error"] == "PSEUDONYMIZE_NOT_SUPPORTED_FOR_PDF"
    assert _get(jobs, pdf_job).json()["status"] == "ready"


def test_render_with_full_entity_list_replaces_detection(jobs):
    job_id = _ready_job(jobs)
    text = _get(jobs, f"{job_id}/entities").json()["text"]
    start = text.index(PERSON)
    r = _render(jobs, job_id, entities=[{"start": start, "end": start + len(PERSON), "type": "PERSON"}])
    assert r.status_code == 200 and PERSON not in r.text and FISCAL in r.text and EMAIL in r.text


def test_entities_and_render_need_a_ready_job(jobs, monkeypatch):
    gate = threading.Event()
    real = jobs.anonymizer.detect_only

    def slow(*args, **kwargs):
        gate.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(jobs.anonymizer, "detect_only", slow)
    job_id = _create(jobs, TXT).json()["job_id"]
    assert _get(jobs, f"{job_id}/entities").json()["error"] == "JOB_NOT_READY"
    assert _render(jobs, job_id).status_code == 409
    gate.set()
    assert _wait(jobs, job_id)["status"] == "ready"


# ── cancel, failure, TTL, restart ────────────────────────────────────────────

def test_cancel_stops_detection_and_deletes_the_job(jobs, monkeypatch):
    monkeypatch.setattr(settings, "document_detection_window_chars", 300)
    monkeypatch.setattr(settings, "document_detection_window_overlap", 30)
    monkeypatch.setattr(settings, "document_max_text_chars", 10**7)
    started, gate = threading.Event(), threading.Event()
    real = jobs.anonymizer.detect_only

    def blocking(*args, **kwargs):
        started.set()
        gate.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(jobs.anonymizer, "detect_only", blocking)
    payload = (TXT.decode() + "\n") * 200
    job_id = _create(jobs, payload.encode()).json()["job_id"]
    assert started.wait(5)
    assert _get(jobs, job_id).json()["status"] == "analyzing"
    assert jobs.jobs.delete(f"/v1/documents/jobs/{job_id}", headers={"X-Pii-User-Id": "u1"}).status_code == 204
    gate.set()
    time.sleep(0.3)
    windows = len(chunking.windows(payload.rstrip("\n").replace("\r", ""), 300, 30))
    assert jobs.anonymizer.calls < windows / 2  # pending windows never ran
    assert _get(jobs, job_id).status_code == 404 and len(jobs.store) == 0


def test_analysis_failure_leaves_a_content_free_tombstone(jobs):
    jobs.anonymizer.fail = True
    job_id = _create(jobs, TXT).json()["job_id"]
    status = _wait(jobs, job_id)
    assert status["status"] == "failed" and status["error"]["error"] == "PII_PROCESSING_FAILED"
    job = jobs.store.get(job_id, (None, "key-1", "u1"))
    assert job.doc is None and job.joined is None and job.entities is None and job.bytes == 0
    assert _get(jobs, f"{job_id}/entities").status_code == 409
    jobs.anonymizer.fail = False
    assert _create(jobs, TXT).status_code == 202  # a failed job is not active


def test_abandoned_job_expires_after_ttl_and_then_disappears(jobs):
    job_id = _ready_job(jobs)
    jobs.clock.now += 901
    status = _get(jobs, job_id).json()
    assert status["status"] == "expired" and status["error"]["error"] == "JOB_EXPIRED"
    assert jobs.store.get(job_id, (None, "key-1", "u1")).doc is None
    assert _render(jobs, job_id).status_code == 409
    jobs.clock.now += 901
    assert _get(jobs, job_id).status_code == 404 and len(jobs.store) == 0


def test_jobs_do_not_survive_a_restart(jobs):
    job_id = _ready_job(jobs)
    jobs.store = DocumentJobStore(20, 10**9, 900)  # a new process starts with an empty store
    assert _get(jobs, job_id).status_code == 404


# ── isolation and limits ─────────────────────────────────────────────────────

def test_jobs_are_isolated_by_user_and_tenant(jobs):
    job_id = _ready_job(jobs)
    assert _get(jobs, job_id, user="u2").status_code == 404
    assert _get(jobs, f"{job_id}/entities", user="u2").status_code == 404
    assert _render(jobs, job_id, user="u2").status_code == 404
    assert jobs.jobs.delete(f"/v1/documents/jobs/{job_id}", headers={"X-Pii-User-Id": "u2"}).status_code == 404
    jobs.jobs.app.dependency_overrides[get_tenant_id] = lambda: "tenant-b"
    assert _get(jobs, job_id).status_code == 404
    jobs.jobs.app.dependency_overrides[get_tenant_id] = lambda: None
    assert _get(jobs, job_id).json()["status"] == "ready"


def test_one_active_job_per_user_and_global_limits(jobs):
    _ready_job(jobs)
    again = _create(jobs, TXT)
    assert again.status_code == 409 and again.json()["error"] == "JOB_ALREADY_ACTIVE"
    jobs.store._max_jobs = 1
    busy = _create(jobs, TXT, user="u2")
    assert busy.status_code == 503 and busy.json()["error"] == "ENGINE_BUSY" and busy.headers["retry-after"]
    jobs.store._max_jobs, jobs.store._max_bytes = 20, sum(j.bytes for j in jobs.store._jobs.values()) + len(TXT) - 1
    assert _create(jobs, TXT, user="u3").json()["error"] == "ENGINE_BUSY"
    assert len(jobs.store) == 1  # refused uploads left nothing behind


def test_sync_endpoints_still_work_alongside_jobs(jobs):
    _ready_job(jobs)
    r = jobs.jobs.post("/v1/documents/redact", files={"file": ("d", TXT)})
    assert r.status_code == 200 and PERSON not in r.text


# ── zero retention ───────────────────────────────────────────────────────────

def test_mid_stream_failure_deletes_the_job(jobs, monkeypatch):
    job_id = _ready_job(jobs, make_pdf(pages=3))
    real = pdf_handler.PdfDocument._render_page

    def flaky(self, source, index, plan, edits):
        if index == 1:
            raise RuntimeError(f"pdfium crashed near {PERSON}")
        return real(self, source, index, plan, edits)

    monkeypatch.setattr(pdf_handler.PdfDocument, "_render_page", flaky)
    received = bytearray()
    with pytest.raises(Exception):
        with jobs.jobs.stream("POST", f"/v1/documents/jobs/{job_id}/render", json={"mode": "redact"},
                              headers={"X-Pii-User-Id": "u1"}) as r:
            for chunk in r.iter_bytes():
                received.extend(chunk)
    assert EOF_MARKER not in received
    time.sleep(0.1)
    assert _get(jobs, job_id).status_code == 404 and len(jobs.store) == 0


def test_jobs_write_no_temp_files(jobs, monkeypatch, tmp_path):
    opened = []
    real_open, real_os_open = builtins.open, os.open

    def watch_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            opened.append(str(path))
        return real_os_open(path, flags, *args, **kwargs)

    def watch_open(file, mode="r", *args, **kwargs):
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            opened.append(str(file))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(os, "open", watch_os_open)
    monkeypatch.setattr(builtins, "open", watch_open)
    for payload, mode, user in [(make_pdf(pages=2), "redact", "a"), (make_docx(), "pseudonymize", "b")]:
        job_id = _ready_job(jobs, payload, user=user)
        assert _render(jobs, job_id, user=user, mode=mode).status_code == 200
    assert opened == [] and list(tmp_path.iterdir()) == []


def test_job_logs_contain_no_content_or_filenames(jobs, caplog):
    caplog.set_level(logging.DEBUG)
    job_id = _ready_job(jobs, make_docx())
    _get(jobs, f"{job_id}/entities")
    _render(jobs, job_id, include_terms=[{"text": "Milano", "type": "ADDRESS"}])
    jobs.anonymizer.fail = True
    _wait(jobs, _create(jobs, TXT, filename=SECRET_FILENAME).json()["job_id"])
    logged = "\n".join(f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records)
    assert "document job ready" in logged and "analysis failed closed: RuntimeError" in logged
    for value in (*SAMPLE_PII, SECRET_FILENAME, "contratto_mario", "Milano"):
        assert value not in logged


# ── parallel windows ─────────────────────────────────────────────────────────

def test_parallel_windows_equal_sequential_and_report_progress():
    names = ("Mario Rossi", "Giulia Bianchi", "Luca Verdi")
    text = "".join(f"{'testo neutro ' * 37}{names[i % 3]} " for i in range(80))

    def detect(chunk):
        time.sleep(0.001 * (len(chunk) % 7))  # windows finish out of order
        return [PiiEntity(m.start(), m.end(), "PERSON", m.group(), 0.9, "fake")
                for name in names for m in re.finditer(name, chunk)]

    seen = []
    sequential = chunking.detect_in_windows(detect, text, 700, 120)
    parallel = chunking.detect_in_windows(detect, text, 700, 120, executor=chunking.detection_executor(4),
                                          progress=lambda chars, covered: seen.append((chars, covered)))
    assert parallel == sequential and len(sequential) == 80
    assert [c for c, _ in seen] == sorted(c for c, _ in seen) and seen[-1] == (len(text), len(text))
    with pytest.raises(chunking.DetectionCancelled):
        chunking.detect_in_windows(detect, text, 700, 120, executor=chunking.detection_executor(4),
                                   should_stop=lambda: True)
