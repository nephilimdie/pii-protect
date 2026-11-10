"""Redaction cover style (redaction_style.py): geometry that hides length, opacity, line separation.

Synthetic fixtures only (fake names and numbers). `test_real_ocr_*` need PII_OCR_TEST_URL (CI starts
the OCR container); the flattened-PDF test uses pdftotext when installed, PDFium's text layer always.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import time

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.documents.image_handler import ImageDocument
from app.documents.models import DocumentFormat, DocumentLimits, SegmentEdit
from app.documents.ocr_client import OcrClient
from app.documents.ocr_layout import ScannedPage, glyph_band, paint
from app.documents.pdf_handler import PdfDocument
from app.documents.redaction_style import (
    BUCKET,
    Run,
    bucket_width,
    cover_share,
    label_for,
    paint_area,
    pill_boxes,
    same_lines,
    visible_ink,
)
from tests.unit import test_documents_ocr as scan_tests

REAL_URL = os.environ.get("PII_OCR_TEST_URL")
LIMITS = DocumentLimits(max_bytes=50_000_000, max_pages=5, pdf_dpi=150, max_pixels=12_000_000, ocr_enabled=True)
FONT = ImageFont.load_default(28)


def _text_image(lines: list[str], size=(1000, 400), pitch=44) -> tuple[Image.Image, list[tuple[str, tuple]]]:
    """White page with ``lines`` drawn at a known pitch; returns per-word ink boxes (fake OCR boxes,
    deliberately loose: +-30% of the glyph height, like detector-based OCR)."""
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    words = []
    for n, line in enumerate(lines):
        x, y = 40, 30 + n * pitch
        for word in line.split():
            left, t, r, b = draw.textbbox((x, y), word, font=FONT)
            draw.text((x, y), word, font=FONT, fill="black")
            loose = round(0.3 * (b - t))
            words.append((word, (left - 4, t - loose, r + 4, b + loose), n))
            x = r + 14
    return image, words


def _fit(words, size) -> ScannedPage:
    result = scan_tests._result([(w, box, line, 0) for w, box, line in words])
    return ScannedPage.from_ocr(result.__class__(**{**result.__dict__, "width": size[0], "height": size[1]}))


def _edit(page: ScannedPage, token: str, label: str = "PERSON") -> SegmentEdit:
    start = page.text.index(token)
    return SegmentEdit(0, start, start + len(token), "x", label)


# ── geometry: length is hidden ───────────────────────────────────────────────

def test_bucket_width_same_bucket_identical_and_never_smaller():
    glyph = 20.0  # unit = BUCKET * 20
    unit = BUCKET * glyph
    a, b = bucket_width(unit * 0.2, glyph), bucket_width(unit * 0.99, glyph)
    assert a == b >= unit  # 1 vs ~5 characters: the same width
    assert bucket_width(unit * 1.01, glyph) > b  # next bucket
    for needed in range(1, 400):
        assert bucket_width(needed, glyph) >= needed  # never narrower than the text
        assert bucket_width(needed, glyph) == bucket_width(needed, glyph)  # deterministic


def test_different_char_counts_in_one_bucket_render_identical_pill_widths():
    """2 vs 4 glyphs (~16 px each on a 30 px line) fall in one bucket: identical cover widths, and
    the cover's start is the text's start (only the end, i.e. the length, is hidden)."""
    covers = [pill_boxes([Run(200, 10, 200 + chars * 16, 40, 30.0)], 2000, 2000)[0][0] for chars in (2, 3, 4)]
    assert len({box[2] - box[0] for box in covers}) == 1
    assert all(box[2] >= 200 + 4 * 16 for box in covers)


def test_pill_widths_quantized_for_every_length():
    """Runs of 1..60 px on a 20 px line: only a handful of distinct widths, each >= its run + caps."""
    seen = set()
    for length in range(1, 61):
        [(box, radius, _, _)] = pill_boxes([Run(100, 10, 100 + length, 34, 20.0)], 1000, 1000)
        assert box[0] <= 100 and box[2] >= 100 + length
        seen.add(box[2] - box[0])
    assert len(seen) <= 3


def test_runs_of_one_line_share_one_height_and_lines_never_merge():
    runs = same_lines([Run(10, 100, 50, 124, 20.0), Run(80, 98, 120, 128, 20.0), Run(10, 160, 60, 184, 20.0)])
    first = [r for r in runs if r.y0 < 150]
    assert {(r.y0, r.y1) for r in first} == {(98, 128)}  # normalized per line
    boxes = pill_boxes(runs, 1000, 1000)
    assert all(b[3] <= 150 or b[1] >= 150 for b, *_ in boxes)  # no cover spans two lines


def test_pill_clipped_to_image_grows_leftwards_and_never_past_edges():
    [(box, *_)] = pill_boxes([Run(960, 10, 998, 30, 20.0)], 1000, 1000)
    assert 0 <= box[0] <= 960 and box[2] == 1000


def test_labels_are_types_only():
    assert label_for("PERSON") == "NOME" and label_for("FISCAL_CODE") == "CF" and label_for("IBAN") == "IBAN"
    assert label_for("UNKNOWN_TYPE") == ""


# ── pixels: opaque, tight, nothing outside ───────────────────────────────────

def test_glyph_band_drops_only_empty_rows():
    gray = np.full((100, 200), 255, dtype=np.int16)
    gray[40:60, 20:180] = 0
    assert glyph_band(gray, (10, 20, 190, 80)) == (39, 61)
    assert glyph_band(np.full((100, 200), 255, dtype=np.int16), (10, 20, 190, 80)) == (20, 80)  # nothing: whole box
    gray[20, 50] = 0  # ink touching the top edge keeps that edge
    assert glyph_band(gray, (10, 20, 190, 80))[0] == 20


def test_no_glyph_pixel_of_a_redacted_word_survives_and_covers_hug_lines():
    lines = ["Cliente Ugolino Brambilla via Gelsi", "CF BRMGFR79C14E648T nato Lodi", "Telefono 3478129034 fine"]
    image, words = _text_image(lines)
    original = image.copy()
    page = _fit(words, image.size)
    edits = [_edit(page, "Ugolino Brambilla"), _edit(page, "BRMGFR79C14E648T", "FISCAL_CODE"),
             _edit(page, "3478129034", "PHONE")]
    paint(image, page, edits, [])
    hidden = {"Ugolino", "Brambilla", "BRMGFR79C14E648T", "3478129034"}
    for word, box, _ in words:
        if word in hidden:
            assert visible_ink(image, box) == 0.0, word  # every glyph pixel is under a cover
            assert visible_ink(original, box) > 0.01, word  # (there was ink to hide)
        elif word in ("Cliente", "via", "nato", "fine", "Telefono"):
            assert visible_ink(image, box) > 0.01, word  # neighbours stay readable
    covered = np.asarray(image, dtype=np.int16)
    blue = covered[..., 2] - np.maximum(covered[..., 0], covered[..., 1]) >= 8
    rows = np.flatnonzero(blue.any(axis=1))
    groups = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
    assert len(groups) == 3  # one band of covers per text line, with paper between lines
    for group in groups:
        assert group[-1] - group[0] + 1 < 44  # shorter than the line pitch


def test_area_cover_is_opaque_over_the_whole_box_and_rounded_outside():
    image = Image.new("RGB", (300, 200), (0, 0, 0))
    paint_area(image, (50, 40, 250, 160), "FIRMA")
    assert cover_share(image, (50, 40, 250, 160)) == 1.0


# ── real OCR: the output reads none of the hidden tokens ────────────────────

SECRETS = ("BRAMBILLA", "BRMGFR79C14E648T", "3478129034")


def _ocr_text(client: OcrClient, payload: bytes, fmt: str) -> str:
    doc = ImageDocument(payload, fmt, LIMITS)
    doc.run_ocr(client, time.monotonic() + 120)
    return doc, doc.segments[0]


@pytest.mark.skipif(not REAL_URL, reason="PII_OCR_TEST_URL not set (no OCR container)")
def test_real_ocr_reads_none_of_the_redacted_tokens():
    client = OcrClient(REAL_URL, os.environ.get("PII_OCR_TEST_KEY", "ci-key"), 120, 3, 10)
    image, _ = _text_image(["Cognome BRAMBILLA Gianni", "Codice BRMGFR79C14E648T", "Telefono 3478129034 ok"],
                           size=(1100, 260), pitch=60)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    doc, text = _ocr_text(client, buffer.getvalue(), DocumentFormat.PNG)
    edits = []
    for secret in SECRETS:
        match = re.search(r"\s*".join(map(re.escape, secret)), text)
        assert match, secret  # the OCR read it before
        edits.append(SegmentEdit(0, match.start(), match.end(), "x", "PERSON"))
    out = doc.render(edits)
    _, after = _ocr_text(client, out, DocumentFormat.PNG)
    squashed = re.sub(r"\s+", "", after)
    for secret in SECRETS:
        assert secret not in squashed and secret[:6] not in squashed, secret
    assert "Cognome" in after and "Gianni" in after  # the rest still reads (a tight neighbour may lose a letter)


# ── flattened PDF: no hidden text anywhere ──────────────────────────────────

def test_flattened_pdf_has_no_text_and_covers_every_redacted_word():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 760, "Spett.le ufficio, sono Ugolino Brambilla, codice BRMGFR79C14E648T.")
    pdf.drawString(72, 744, "Telefono 3478129034, saluti.")
    pdf.save()
    doc = PdfDocument(buffer.getvalue(), LIMITS)
    text = doc.segments[0]
    secrets = (("Ugolino Brambilla", "PERSON"), ("BRMGFR79C14E648T", "FISCAL_CODE"), ("3478129034", "PHONE"))
    edits = [SegmentEdit(0, text.index(s), text.index(s) + len(s), "x", t) for s, t in secrets]
    out = doc.render(edits)
    rendered = pdfium.PdfDocument(out)
    try:
        assert rendered[0].get_textpage().count_chars() == 0
        page = rendered[0].render(scale=150 / 72).to_pil().convert("RGB")
    finally:
        rendered.close()
    if shutil.which("pdftotext"):
        extracted = subprocess.run(["pdftotext", "-", "-"], input=out, capture_output=True, check=True).stdout
        assert extracted.strip() == b""
    source = pdfium.PdfDocument(buffer.getvalue())
    try:
        textpage = source[0].get_textpage()
        scale = 150 / 72
        height = source[0].get_height()
        for start, end in ((e.start, e.end) for e in edits):
            for i in range(start, end):
                left, bottom, right, top = textpage.get_charbox(i, loose=False)
                if right > left:
                    box = (int(left * scale), int((height - top) * scale), int(right * scale) + 1,
                           int((height - bottom) * scale) + 1)
                    assert visible_ink(page, box) == 0.0, (i, box)
    finally:
        source.close()
