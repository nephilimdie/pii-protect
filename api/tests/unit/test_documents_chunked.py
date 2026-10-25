"""Memory-bounded document processing: windowed detection, streamed PDFs, DOCX zip
inspection and admission control. All inputs are synthetic and built in memory."""

from __future__ import annotations

import asyncio
import io
import json
import re
import time
import zipfile

import pypdfium2 as pdfium
import pytest
from docx import Document
from reportlab.pdfgen import canvas

from app.config import settings
from app.detection.entities import PiiEntity
from app.documents import docx_handler, pdf_handler
from app.documents.admission import DocumentAdmission
from app.documents.chunking import detect_in_windows, merge_windows, windows
from app.documents.models import DocumentError, DocumentLimits
from app.documents.pdf_handler import plan_page
from app.documents.pdf_writer import EOF_MARKER
from app.routers import documents as documents_module
from tests.unit.test_documents import PERSON, _post, env, make_docx, make_pdf  # noqa: F401  (fixture reuse)

NAMES = ("Mario Rossi", "Giulia Bianchi", "Luca Verdi")


def _regex_detect(text: str) -> list[PiiEntity]:
    return [PiiEntity(m.start(), m.end(), "PERSON", m.group(), 0.9, "fake")
            for name in NAMES for m in re.finditer(name, text)]


# ── windows + merge ──────────────────────────────────────────────────────────

def test_windows_cover_text_with_bounded_overlapping_windows():
    text = "Parola qualsiasi. " * 2_000
    spans = windows(text, 4_000, 300)
    assert spans[0][0] == 0 and spans[-1][1] == len(text) and len(spans) > 5
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 - s1 <= 4_000 and s2 < e1 and e1 - s2 >= 200  # real overlap, never a gap
        assert text[e1 - 1] == " " and text[s2 - 1] == " "  # cuts at word boundaries
    assert windows("breve", 4_000, 300) == [(0, 5)]


def test_entity_on_every_window_boundary_is_detected_once_and_whole():
    filler = "testo neutro " * 40
    text = "".join(f"{filler}{NAMES[i % 3]} " for i in range(60))
    expected = sorted((e.start, e.end) for e in _regex_detect(text))
    calls = []

    def detect(chunk):
        calls.append(len(chunk))
        return _regex_detect(chunk)

    found = detect_in_windows(detect, text, 700, 120)
    assert len(calls) > 30 and max(calls) <= 700
    assert [(e.start, e.end) for e in found] == expected
    assert all(text[e.start:e.end] == e.text for e in found)


def test_fragments_cut_by_a_window_edge_are_unioned():
    text = "aaaa Mario Rossi bbbb"
    left = ((0, 11), [PiiEntity(5, 11, "PERSON", "Mario ", 0.6, "x")])  # touches A's end
    right = ((10, 21), [PiiEntity(10, 16, "PERSON", " Rossi", 0.7, "x")])  # touches B's start
    merged = merge_windows(text, [left, right])
    assert [(e.start, e.end, e.text) for e in merged] == [(5, 16, "Mario Rossi")]


def test_whole_span_beats_cut_fragment_and_duplicates_collapse():
    text = "x" * 50
    a = ((0, 30), [PiiEntity(20, 30, "PERSON", "", 0.99, "x"), PiiEntity(5, 9, "EMAIL", "", 0.9, "x")])
    b = ((15, 50), [PiiEntity(20, 34, "PERSON", "", 0.5, "x"), PiiEntity(40, 44, "PHONE", "", 0.9, "x")])
    merged = merge_windows(text, [a, b])
    assert [(e.start, e.end, e.pii_type) for e in merged] == [(5, 9, "EMAIL"), (20, 34, "PERSON"), (40, 44, "PHONE")]


def test_long_document_pseudonyms_are_globally_consistent(env, monkeypatch):
    monkeypatch.setattr(settings, "document_detection_window_chars", 600)
    monkeypatch.setattr(settings, "document_detection_window_overlap", 100)
    text = "".join(f"Paragrafo {i}: il dipendente {PERSON} ha firmato. " + "riempitivo " * 30 for i in range(40))
    r = _post(env, "pseudonymize", text.encode())
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        body = archive.read("pseudonymized.txt").decode()
        mapping = json.loads(archive.read("mapping.json"))["entities"]
    assert env.anonymizer.calls > 10  # really windowed
    assert PERSON not in body and body.count("[PERSON_1]") == 40
    assert mapping == [{"token": "[PERSON_1]", "type": "PERSON", "original": PERSON}]


# ── PDF: page plan + streaming ───────────────────────────────────────────────

LIMITS = DocumentLimits(max_bytes=10**8, max_pages=10, pdf_dpi=200, max_pixels=16_000_000, pdf_min_dpi=50)


def test_page_plan_scales_huge_pages_into_the_pixel_budget():
    a4 = plan_page(595.0, 842.0, 0, LIMITS)
    assert a4.scale == pytest.approx(200 / 72) and a4.frame == (595.0, 842.0)
    huge = plan_page(5000.0, 5000.0, 90, LIMITS)
    assert (5000 * huge.scale) ** 2 <= 16_000_000 * 1.0001 and huge.scale * 72 == pytest.approx(57.6)
    with pytest.raises(DocumentError) as exc:
        plan_page(14_400.0, 14_400.0, 0, LIMITS)
    assert (exc.value.status, exc.value.code) == (422, "PDF_PAGE_TOO_LARGE")


def _pdf(size, text=f"Dipendente: {PERSON}", color=None) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=size)
    if color:
        pdf.setFillColorRGB(*color)
        pdf.rect(20, 20, 100, 100, fill=1)
        pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 40)
    pdf.drawString(72, size[1] / 2, text)
    pdf.showPage()
    pdf.save()
    return out.getvalue()


def test_huge_page_is_rendered_within_budget_and_keeps_its_size(env):
    r = _post(env, "redact", _pdf((5000, 5000)))
    assert r.status_code == 200, r.text
    out = pdfium.PdfDocument(r.content)
    try:
        assert out[0].get_size() == pytest.approx((5000, 5000))
        image = next(out[0].get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,)))
        width, height = image.get_px_size()
        assert width * height <= settings.document_pdf_max_page_pixels
    finally:
        out.close()


def test_page_beyond_minimum_dpi_is_rejected_before_any_output(env):
    r = _post(env, "redact", _pdf((14_400, 14_400)))
    assert r.status_code == 422 and r.json()["error"] == "PDF_PAGE_TOO_LARGE"


def test_streamed_pdf_is_complete_and_image_only(env):
    r = _post(env, "redact", make_pdf(pages=3))
    assert r.status_code == 200
    assert r.headers["x-pseudora-pages"] == "3" and "content-length" not in r.headers
    assert r.content.rstrip().endswith(EOF_MARKER)
    out = pdfium.PdfDocument(r.content)
    try:
        assert len(out) == 3 and sum(out[i].get_textpage().count_chars() for i in range(3)) == 0
    finally:
        out.close()


@pytest.mark.parametrize("color,filter_name", [(None, b"/FlateDecode"), ((0.9, 0.1, 0.1), b"/DCTDecode")])
def test_gray_pages_are_lossless_and_colour_pages_jpeg(env, color, filter_name):
    r = _post(env, "redact", _pdf((595, 842), color=color))
    assert r.status_code == 200
    assert filter_name in r.content and r.content.count(b"/Subtype /Image") == 1


def _slots_free(admission: DocumentAdmission, expected: int) -> bool:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if admission._semaphore._value == expected:
            return True
        time.sleep(0.02)
    return False


@pytest.mark.parametrize("failure", ["render", "deadline"])
def test_mid_stream_failure_aborts_without_trailer_and_frees_the_slot(env, monkeypatch, failure):
    admission = DocumentAdmission(1, 0.1, 0)
    env.client.app.dependency_overrides[documents_module.get_document_admission] = lambda: admission
    real = pdf_handler.PdfDocument._render_page
    rendered = []

    def flaky(self, source, index, plan, edits):
        rendered.append(index)
        if index == 1:
            if failure == "render":
                raise RuntimeError(f"pdfium crashed near {PERSON}")
            monkeypatch.setattr(time, "monotonic", lambda: float("inf"))
        return real(self, source, index, plan, edits)

    monkeypatch.setattr(pdf_handler.PdfDocument, "_render_page", flaky)
    received = bytearray()
    with pytest.raises(Exception) as exc:
        with env.client.stream("POST", "/v1/documents/redact", files={"file": ("d", make_pdf(pages=3))}) as r:
            assert r.status_code == 200  # headers were already sent
            for chunk in r.iter_bytes():
                received.extend(chunk)
    assert type(exc.value).__name__ == "_StreamAborted" and PERSON not in str(exc.value)
    assert EOF_MARKER not in received and 2 not in rendered
    monkeypatch.undo()
    assert _slots_free(admission, 1)


# ── DOCX zip inspection ──────────────────────────────────────────────────────

def _with_member(name: str, data: bytes, base: bytes | None = None) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(base or make_docx()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for info in src.infolist():
            if info.filename != name:
                archive.writestr(info, src.read(info.filename))
        archive.writestr(name, data)
    return out.getvalue()


def _bomb() -> bytes:
    body = b"<w:body>" + b" " * 30_000_000
    xml = zipfile.ZipFile(io.BytesIO(make_docx())).read("word/document.xml").replace(b"<w:body>", body, 1)
    return _with_member("word/document.xml", xml)


@pytest.fixture
def no_docx_parse(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("python-docx must not run on a rejected package")
    monkeypatch.setattr(docx_handler, "Document", refuse)


def test_zip_bomb_rejected_before_parsing(env, no_docx_parse):
    payload = _bomb()
    assert len(payload) < 200_000
    r = _post(env, "redact", payload)
    assert r.status_code == 413 and r.json()["error"] == "DOCX_COMPRESSION_RATIO_EXCEEDED"


def test_total_inflated_size_limit(env, no_docx_parse, monkeypatch):
    monkeypatch.setattr(settings, "document_docx_max_uncompressed_bytes", 1_000_000)
    monkeypatch.setattr(settings, "document_docx_max_ratio", 10_000)
    r = _post(env, "redact", _bomb())
    assert r.status_code == 413 and r.json()["error"] == "DOCUMENT_TOO_LARGE"


def test_too_many_parts(env, no_docx_parse, monkeypatch):
    monkeypatch.setattr(settings, "document_docx_max_entries", 10)
    r = _post(env, "redact", make_docx())
    assert r.status_code == 413 and r.json()["error"] == "DOCX_TOO_MANY_PARTS"


@pytest.mark.parametrize("name,data", [
    ("word/embeddings/sheet.xlsx", b"PK\x03\x04whatever"),
    ("word/embeddings/oleObject1.bin", b"PK\x03\x04disguised zip"),
])
def test_nested_archives_rejected(env, no_docx_parse, name, data):
    r = _post(env, "redact", _with_member(name, data))
    assert r.status_code == 422 and r.json()["error"] == "DOCX_NESTED_ARCHIVE"


def test_external_image_reference_rejected_but_hyperlinks_allowed(env):
    assert _post(env, "redact", make_docx()).status_code == 200  # make_docx carries an external hyperlink
    rels = (b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            b'package/2006/relationships"><Relationship Id="rId99" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/image" Target="https://tracker.example/p.png" '
            b'TargetMode="External"/></Relationships>')
    r = _post(env, "redact", _with_member("word/_rels/header9.xml.rels", rels))
    assert r.status_code == 422 and r.json()["error"] == "DOCX_EXTERNAL_REFERENCE"


# ── admission control ────────────────────────────────────────────────────────

def test_busy_engine_returns_503_with_retry_after(env):
    admission = DocumentAdmission(1, 0.1, 0)
    env.client.app.dependency_overrides[documents_module.get_document_admission] = lambda: admission
    held = asyncio.run(admission.acquire())
    r = _post(env, "redact", make_docx())
    assert r.status_code == 503 and r.json()["error"] == "ENGINE_BUSY"
    assert r.headers["retry-after"] == "1" and env.anonymizer.calls == 0
    held.release()
    assert _post(env, "redact", make_docx()).status_code == 200
    assert _slots_free(admission, 1)


def test_memory_guard_refuses_new_jobs(env):
    admission = DocumentAdmission(4, 0.1, 1024, rss=lambda: 4096)
    env.client.app.dependency_overrides[documents_module.get_document_admission] = lambda: admission
    r = _post(env, "preview", make_docx())
    assert r.status_code == 503 and r.json()["error"] == "ENGINE_BUSY"


def test_slot_is_released_after_errors(env):
    admission = DocumentAdmission(1, 0.1, 0)
    env.client.app.dependency_overrides[documents_module.get_document_admission] = lambda: admission
    env.anonymizer.fail = True
    for _ in range(3):
        assert _post(env, "redact", make_docx()).status_code == 503
    env.anonymizer.fail = False
    assert _post(env, "redact", b"").status_code == 422
    assert _post(env, "redact", make_pdf()).status_code == 200
    assert _slots_free(admission, 1)
