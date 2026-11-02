"""Scanned PDFs through the OCR service: sync endpoints and in-memory jobs.

Scans are synthetic: Italian text drawn into a bitmap at known word boxes, embedded as the
only content of a PDF page (no text layer). A fake OCR service (httpx.MockTransport) answers
with those boxes scaled to the image it receives, plus one low-confidence and one
unrecognized-ink region. Pixel sampling on the output proves what was blacked out.
`test_real_ocr_service_*` run only when PII_OCR_TEST_URL points at a real ocr container.
"""

from __future__ import annotations

import io
import logging
import os
import re

import httpx
import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw, ImageFont, ImageStat
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.config import settings
from app.documents import ocr_client as ocr_module
from app.documents.ocr_client import OcrClient, OcrResult, OcrWord, parse_result
from app.documents.ocr_layout import ScannedPage, to_device
from app.routers import documents as documents_module
from tests.unit import test_documents as base
from tests.unit.test_document_jobs import _create, _get, _render, _wait, jobs  # noqa: F401  (fixture reuse)
from tests.unit.test_documents import FISCAL, PERSON, _post, env  # noqa: F401  (fixture reuse)

IBAN = "IT60X0542811101000000123456"
KEY = "test-internal-key"
SCAN_DPI = 150
SCAN_SIZE = (round(A4[0] / 72 * SCAN_DPI), round(A4[1] / 72 * SCAN_DPI))  # 1240 x 1754
LINES = ["Contratto di lavoro subordinato", f"Dipendente: {PERSON}", f"Codice fiscale: {FISCAL}",
         f"IBAN: {IBAN}", "Mansione: impiegato amministrativo"]
LOW_CONF = (800, 1300, 1100, 1360)  # a smudged word the OCR could not read confidently
INK = (150, 1500, 600, 1580)  # a signature: ink without any text
FONT = ImageFont.load_default(size=36)


def _layout() -> tuple[Image.Image, list[tuple[str, tuple[int, int, int, int], int]]]:
    """Upright scan bitmap + its words as (text, box, line)."""
    image = Image.new("L", SCAN_SIZE, 255)
    draw = ImageDraw.Draw(image)
    words = []
    for line, text in enumerate(LINES):
        x, y = 120, 200 + line * 90
        for token in text.split(" "):
            box = draw.textbbox((x, y), token, font=FONT)
            draw.text((x, y), token, font=FONT, fill=0)
            words.append((token, box, line))
            x = box[2] + draw.textlength(" ", font=FONT)
    draw.rectangle(LOW_CONF, fill=150)
    draw.line((INK[0], INK[3] - 10, INK[2], INK[1] + 10), fill=0, width=8)
    return image, words


SCAN, WORDS = _layout()


def make_scan_pdf(pages: int = 1, rotation: int = 0, text_first_page: bool = False) -> bytes:
    """Scanned pages displayed upright for any /Rotate (stored image counter-rotated)."""
    out = io.BytesIO()
    frame = A4 if rotation % 180 == 0 else (A4[1], A4[0])
    pdf = canvas.Canvas(out, pagesize=frame)
    if text_first_page:
        pdf.setFont("Helvetica", 14)
        pdf.drawString(72, 700, f"Dipendente: {PERSON}")
        pdf.showPage()
    stored = SCAN.rotate(rotation, expand=True) if rotation else SCAN
    for _ in range(pages):
        pdf.setPageSize(frame)
        pdf.setPageRotation(rotation)
        pdf.drawImage(ImageReader(stored.convert("RGB")), 0, 0, *frame)
        pdf.showPage()
    pdf.save()
    return out.getvalue()


class FakeOcr:
    """The OCR service contract, answering with the known layout scaled to the received image."""

    def __init__(self) -> None:
        self.calls, self.fail_with, self.busy_times, self.keys, self.dpis = 0, None, 0, [], []
        self.response: dict | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.keys.append(request.headers.get("x-internal-key"))
        if self.fail_with is not None:
            raise self.fail_with
        if self.busy_times:
            self.busy_times -= 1
            return httpx.Response(503, json={"error": "BUSY", "message": "busy"}, headers={"Retry-After": "2"})
        body = request.content
        image = Image.open(io.BytesIO(body[body.index(b"\x89PNG"):]))
        self.dpis.append(re.search(rb'name="dpi"\r\n\r\n(\d+)', body).group(1).decode())
        if self.response is not None:
            return httpx.Response(200, json=self.response)
        f = image.width / SCAN_SIZE[0]

        def scale(box):
            return [min(round(v * f), image.width if i % 2 == 0 else image.height) for i, v in enumerate(box)]

        words = [{"text": t, "conf": 93.0, "bbox": scale(b), "line_id": line, "block_id": 0} for t, b, line in WORDS]
        lines = [{"id": n, "bbox": [0, 0, 1, 1], "text": text} for n, text in enumerate(LINES)]
        return httpx.Response(200, json={"pages": [{
            "index": 0, "width": image.width, "height": image.height, "dpi": 300, "engine": "tesseract",
            "words": words, "lines": lines, "low_conf_regions": [scale(LOW_CONF)],
            "ink_without_text_regions": [scale(INK)]}]})


@pytest.fixture
def ocr(env, monkeypatch):  # noqa: F811
    fake = FakeOcr()
    sleeps: list[float] = []
    client = OcrClient("http://ocr:8090", KEY, 30, 3, 10, transport=httpx.MockTransport(fake), sleep=sleeps.append)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(documents_module, "get_ocr_client", lambda: client)
    monkeypatch.setitem(base._PATTERNS, IBAN, "IBAN")
    env.ocr, env.sleeps = fake, sleeps
    return env


def _pages(payload: bytes, scale: float = SCAN_DPI / 72):
    pdf = pdfium.PdfDocument(payload)
    try:
        out = []
        for i in range(len(pdf)):
            page = pdf[i]
            out.append((page.get_rotation(), page.get_textpage().count_chars(),
                        page.render(scale=scale).to_pil().convert("L")))
        return out
    finally:
        pdf.close()


def _mean(image: Image.Image, box) -> float:
    f = image.width / SCAN_SIZE[0]
    return ImageStat.Stat(image.crop(tuple(round(v * f) for v in box))).mean[0]


def _word(token: str):
    return next(box for text, box, _ in WORDS if text == token)


def _assert_scan_redacted(image: Image.Image, review_kept: tuple[int, ...] = ()) -> None:
    for token in ("Mario", "Rossi", FISCAL, IBAN):
        assert _mean(image, _word(token)) < 20, token  # solid black box over each PII word
    for token in ("Contratto", "Dipendente:", "fiscale:", "IBAN:", "Mansione:"):
        assert _mean(image, _word(token)) > 120, token  # surrounding text still readable
    for n, region in enumerate((LOW_CONF, INK)):
        assert (_mean(image, region) > 120) if n in review_kept else (_mean(image, region) < 20), n


# ── units ────────────────────────────────────────────────────────────────────

def _result(words, low=(), ink=(), order=None):
    return OcrResult(1000, 1000, [OcrWord(t, 90, b, line, block) for t, b, line, block in words],
                     order if order is not None else sorted({w[2] for w in words}), list(low), list(ink))


def test_scanned_page_text_offsets_and_line_boxes():
    page = ScannedPage.from_ocr(_result([
        ("Mario", (10, 10, 60, 30), 0, 0), ("Rossi", (70, 12, 120, 32), 0, 0),
        ("Via", (10, 50, 40, 70), 1, 0), ("Roma", (10, 120, 60, 140), 2, 1)], low=[(1, 1, 2, 2)]))
    assert page.text == "Mario Rossi\nVia\n\nRoma"
    assert page.boxes(0, 11) == [(10, 10, 120, 32)]
    assert page.boxes(6, 8) == [(70, 12, 120, 32)]  # partial word -> whole word
    assert page.boxes(6, 15) == [(70, 12, 120, 32), (10, 50, 40, 70)]  # one box per line segment
    assert page.review == (("low_confidence", (1, 1, 2, 2)),)
    assert page.normalized((100, 250, 500, 1000)) == [0.1, 0.25, 0.5, 1.0]


def test_to_device_scales_and_pads():
    assert to_device((10, 10, 20, 30), 0.5, 0.5, 100, 100, True) == (2, 2, 13, 18)
    assert to_device((0, 0, 100, 100), 1, 1, 50, 50, True) == (0, 0, 50, 50)  # clipped
    assert to_device((100, 100, 200, 200), 1, 1, 500, 500, True) == (85, 85, 215, 215)  # 15% of 100 px


@pytest.mark.parametrize("page", [
    {"width": 9, "height": 10},
    {"width": 10, "height": 10, "words": [{"text": "a", "bbox": [0, 0, 11, 1], "line_id": 0}]},
    {"width": 10, "height": 10, "words": [{"text": "a", "bbox": [0, 0, 1.5, 1], "line_id": 0}]},
    {"width": 10, "height": 10, "low_conf_regions": [[5, 5, 1, 1]]},
])
def test_parse_result_rejects_inconsistent_answers(page):
    with pytest.raises((ValueError, KeyError, TypeError)):
        parse_result({"pages": [page]}, 10, 10)
    with pytest.raises(ValueError):
        parse_result({"pages": [page, page]}, 10, 10)


def test_ocr_disabled_keeps_rejecting_scans(env):  # noqa: F811
    assert ocr_module.get_ocr_client.__wrapped__() is None  # default PII_OCR_ENABLED=false
    r = _post(env, "redact", make_scan_pdf())
    assert r.status_code == 422 and r.json()["error"] == "PDF_NO_TEXT_LAYER"


# ── sync endpoints ───────────────────────────────────────────────────────────

def test_scanned_pdf_redact_end_to_end(ocr):
    r = _post(ocr, "redact", make_scan_pdf(pages=2), domain="hr_payroll")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and "pdf_ocr_applied" in r.headers["x-pii-warnings"]
    pages = _pages(r.content)
    assert len(pages) == 2 and all(chars == 0 for _, chars, _ in pages)  # rasterized, no text layer
    for _, _, image in pages:
        _assert_scan_redacted(image)
    assert ocr.ocr.calls == 2 and set(ocr.ocr.keys) == {KEY} and set(ocr.ocr.dpis) == {"300"}
    assert r.headers["x-pii-entity-count"] == "6"


def test_scanned_pdf_preview_has_boxes_and_needs_review(ocr):
    r = _post(ocr, "preview", make_scan_pdf())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ocr_pages"] == [1] and "Codice fiscale: " + FISCAL in body["text"]
    found = {e["text"]: e for e in body["entities"]}
    assert set(found) == {PERSON, FISCAL, IBAN}
    left, top = _word("Mario")[:2]
    right, bottom = _word("Rossi")[2:]
    [box] = found[PERSON]["boxes"]
    assert box["page"] == 1 and found[PERSON]["page"] == 1
    expected = [left / SCAN_SIZE[0], top / SCAN_SIZE[1], right / SCAN_SIZE[0], bottom / SCAN_SIZE[1]]
    assert box["bbox"] == pytest.approx(expected, abs=0.002)
    assert [(b["id"], b["page"], b["reason"]) for b in body["needs_review"]] == [
        (0, 1, "low_confidence"), (1, 1, "unrecognized_ink")]
    assert body["needs_review"][1]["bbox"] == pytest.approx(
        [INK[0] / SCAN_SIZE[0], INK[1] / SCAN_SIZE[1], INK[2] / SCAN_SIZE[0], INK[3] / SCAN_SIZE[1]], abs=0.002)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_scanned_pdf_rotation_and_size_preserved(ocr, rotation):
    source = make_scan_pdf(rotation=rotation)
    r = _post(ocr, "redact", source)
    assert r.status_code == 200, r.text
    [(out_rotation, chars, image)] = _pages(r.content)
    src = pdfium.PdfDocument(source)
    out = pdfium.PdfDocument(r.content)
    try:
        assert out[0].get_size() == pytest.approx(src[0].get_size(), abs=0.01)
    finally:
        src.close()
        out.close()
    assert out_rotation == rotation and chars == 0
    _assert_scan_redacted(image)  # displayed upright, boxes where the words are


def test_mixed_pdf_text_and_scanned_pages(ocr):
    r = _post(ocr, "redact", make_scan_pdf(text_first_page=True))
    assert r.status_code == 200, r.text
    (_, chars1, text_page), (_, chars2, scan_page) = _pages(r.content)
    assert chars1 == chars2 == 0 and ocr.ocr.calls == 1  # only the scanned page is OCR'd
    _assert_scan_redacted(scan_page)
    preview = _post(ocr, "preview", make_scan_pdf(text_first_page=True)).json()
    assert [(e["page"], bool(e["boxes"])) for e in preview["entities"] if e["text"] == PERSON] == [
        (1, False), (2, True)]
    assert preview["ocr_pages"] == [2]


@pytest.mark.parametrize("error, status, code", [
    (httpx.ConnectError("refused"), 503, "OCR_UNAVAILABLE"),
    (httpx.ReadTimeout("slow"), 504, "OCR_TIMEOUT"),
])
def test_ocr_down_or_slow_fails_closed(ocr, error, status, code):
    ocr.ocr.fail_with = error
    for op in ("redact", "preview"):
        r = _post(ocr, op, make_scan_pdf())
        assert r.status_code == status and r.json()["error"] == code, r.text
        assert not r.content.startswith(b"%PDF") and r.headers["content-type"].startswith("application/json")


def test_ocr_busy_retries_with_retry_after_then_fails_closed(ocr):
    ocr.ocr.busy_times = 2
    assert _post(ocr, "redact", make_scan_pdf()).status_code == 200
    assert ocr.sleeps == [2.0, 2.0]
    ocr.ocr.busy_times, ocr.sleeps[:] = 99, []
    r = _post(ocr, "redact", make_scan_pdf())
    assert r.status_code == 503 and r.json()["error"] == "OCR_BUSY" and r.headers["retry-after"] == "2"
    assert len(ocr.sleeps) == 3  # bounded: max_retries


def test_ocr_retry_wait_never_exceeds_the_deadline():
    fake = FakeOcr()
    fake.busy_times, sleeps, now = 99, [], [0.0]
    client = OcrClient("http://ocr", KEY, 30, 5, 10, transport=httpx.MockTransport(fake),
                       sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)), clock=lambda: now[0])
    with pytest.raises(Exception) as caught:
        client.recognize(Image.new("L", (10, 10), 255), 300, deadline=3.0)
    assert caught.value.code == "OCR_TIMEOUT" and sum(sleeps) <= 3.0


def test_malformed_ocr_answer_fails_closed(ocr):
    ocr.ocr.response = {"pages": [{"width": 1, "height": 1}]}
    r = _post(ocr, "redact", make_scan_pdf())
    assert r.status_code == 503 and r.json()["error"] == "OCR_FAILED"


def test_ocr_page_limit_checked_before_any_ocr(ocr, monkeypatch):
    monkeypatch.setattr(settings, "ocr_max_pages", 1)
    r = _post(ocr, "redact", make_scan_pdf(pages=2))
    assert r.status_code == 422 and r.json().items() >= {"error": "OCR_TOO_MANY_PAGES", "max_pages": 1, "ocr_pages": 2}.items()
    assert ocr.ocr.calls == 0


def test_scanned_pdf_pseudonymize_not_supported(ocr):
    r = _post(ocr, "pseudonymize", make_scan_pdf())
    assert r.status_code == 422 and r.json()["error"] == "PSEUDONYMIZE_NOT_SUPPORTED_FOR_PDF"
    assert ocr.ocr.calls == 0


def test_logs_never_contain_ocr_text_or_key(ocr, caplog):
    caplog.set_level(logging.DEBUG)
    _post(ocr, "redact", make_scan_pdf())
    ocr.ocr.fail_with = httpx.ConnectError(f"refused {PERSON}")
    _post(ocr, "redact", make_scan_pdf())
    for secret in (PERSON, FISCAL, IBAN, KEY):
        assert secret not in caplog.text


# ── jobs ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def ocr_jobs(ocr, jobs):  # noqa: F811
    return jobs


def test_scanned_job_lifecycle_with_review_keep(ocr_jobs):
    created = _create(ocr_jobs, make_scan_pdf(pages=2, text_first_page=True), domain="hr_payroll")
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    status = _wait(ocr_jobs, job_id)
    assert status["status"] == "ready", status
    assert status["ocr_pages_total"] == status["ocr_pages_done"] == 2 and status["pages_total"] == 3
    assert status["chars_total"] == status["chars_done"] > 0
    preview = _get(ocr_jobs, f"{job_id}/entities").json()
    assert preview["ocr_pages"] == [2, 3] and len(preview["needs_review"]) == 4
    bad = _render(ocr_jobs, job_id, review_keep=[4])
    assert bad.status_code == 422 and bad.json()["error"] == "INVALID_RENDER_REQUEST"
    assert _render(ocr_jobs, job_id, face_style="sepia").status_code == 422
    rendered = _render(ocr_jobs, job_id, review_keep=[1], face_style="blur")  # the user reviewed page 2's signature
    assert rendered.status_code == 200, rendered.text
    pages = _pages(rendered.content)
    assert len(pages) == 3 and all(chars == 0 for _, chars, _ in pages)
    _assert_scan_redacted(pages[1][2], review_kept=(1,))
    _assert_scan_redacted(pages[2][2])
    assert _get(ocr_jobs, job_id).status_code == 404 and len(ocr_jobs.store) == 0


def test_scanned_job_ocr_failure_leaves_failed_tombstone(ocr_jobs):
    ocr_jobs.ocr.fail_with = httpx.ConnectError("refused")
    job_id = _create(ocr_jobs, make_scan_pdf()).json()["job_id"]
    status = _wait(ocr_jobs, job_id)
    assert status["status"] == "failed" and status["error"]["error"] == "OCR_UNAVAILABLE"
    assert _get(ocr_jobs, f"{job_id}/entities").status_code == 409


def test_scanned_job_page_limit(ocr_jobs, monkeypatch):
    monkeypatch.setattr(settings, "ocr_job_max_pages", 1)
    r = _create(ocr_jobs, make_scan_pdf(pages=2))
    assert r.status_code == 422 and r.json()["error"] == "OCR_TOO_MANY_PAGES" and len(ocr_jobs.store) == 0


# ── real OCR container (CI: ci.yml starts ocr-service and sets PII_OCR_TEST_URL) ──

REAL_URL = os.environ.get("PII_OCR_TEST_URL")


@pytest.mark.skipif(not REAL_URL, reason="PII_OCR_TEST_URL not set (no OCR container)")
def test_real_ocr_service_redacts_synthetic_scan(env, monkeypatch):  # noqa: F811
    client = OcrClient(REAL_URL, os.environ.get("PII_OCR_TEST_KEY", "ci-key"), 120, 3, 10)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(documents_module, "get_ocr_client", lambda: client)
    monkeypatch.setitem(base._PATTERNS, IBAN, "IBAN")
    preview = _post(env, "preview", make_scan_pdf()).json()
    assert {PERSON, FISCAL, IBAN} <= {e["text"] for e in preview["entities"]}, preview.get("text")
    r = _post(env, "redact", make_scan_pdf())
    assert r.status_code == 200, r.text
    [(_, chars, image)] = _pages(r.content)
    assert chars == 0
    for token in ("Mario", "Rossi", FISCAL, IBAN):
        assert _mean(image, _word(token)) < 40, token
