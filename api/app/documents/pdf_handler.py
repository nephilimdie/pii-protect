from __future__ import annotations

import ctypes
import io
import threading
import time
import zlib
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import ImageChops

from app.documents.models import DocumentError, DocumentFormat, DocumentLimits, SegmentEdit
from app.documents.pdf_writer import ImagePdfWriter, PageImage

# PDFium is not thread-safe: every call into it goes through this lock. It is taken
# per page (not per document) so concurrent jobs interleave instead of queueing.
PDFIUM_LOCK = threading.Lock()
_BOX_PAD_PX = 2
_BLACK = (0, 0, 0, 255)
_JPEG_QUALITY = 85
_FLATE_LEVEL = 6
_GRAY_PROBE_REDUCE = 4  # colour check on a 1/16 thumbnail: cheap, and only decides the encoding
_NO_TEXT_LAYER = DocumentError(
    422, "PDF_NO_TEXT_LAYER",
    "This PDF has pages without a text layer (scanned image). OCR is not supported yet.",
)


class PdfRenderTimeout(Exception):
    """Raised mid-stream when the document deadline passes (the stream is aborted)."""


@dataclass(frozen=True)
class _PagePlan:
    rotation: int
    frame: tuple[float, float]  # unrotated page size in points
    scale: float


def _char(textpage, index: int) -> str:
    code = pdfium_c.FPDFText_GetUnicode(textpage.raw, index)
    char = chr(code) if 0 < code < 0x110000 else " "
    return char if char in "\n\t" or char.isprintable() else " "


def _line_boxes(boxes: list[tuple[float, float, float, float]]) -> list[list[float]]:
    """Merge consecutive char boxes that share a text line into one rectangle."""
    lines: list[list[float]] = []
    for left, top, right, bottom in boxes:
        last = lines[-1] if lines else None
        if last and top < last[3] and bottom > last[1]:
            last[0], last[1] = min(last[0], left), min(last[1], top)
            last[2], last[3] = max(last[2], right), max(last[3], bottom)
        else:
            lines.append([left, top, right, bottom])
    return lines


def plan_page(width_pt: float, height_pt: float, rotation: int, limits: DocumentLimits) -> _PagePlan:
    """Why: a single huge page (e.g. 5000x5000 pt) at the default DPI would need a ~200 MP bitmap.
    What: renders at the configured DPI unless that exceeds the per-page pixel budget, in which
    case the DPI is lowered to fit; pages that would drop below the minimum DPI are rejected (422).
    Test: A4 at 200 DPI keeps scale 200/72; 5000x5000 pt with a 16 MP budget gets ~57.6 DPI;
    14400x14400 pt raises PDF_PAGE_TOO_LARGE.
    """
    scale = limits.pdf_dpi / 72
    pixels = width_pt * height_pt * scale * scale
    if pixels > limits.max_pixels:
        scale *= (limits.max_pixels / pixels) ** 0.5
    if scale * 72 < limits.pdf_min_dpi:
        raise DocumentError(422, "PDF_PAGE_TOO_LARGE",
                            "A PDF page is too large to render legibly within the pixel budget.")
    # The rotated (displayed) size is reported by PDFium; the new page uses the unrotated frame.
    frame = (height_pt, width_pt) if rotation % 180 else (width_pt, height_pt)
    return _PagePlan(rotation, frame, scale)


def _encode(image) -> PageImage:
    """Lossless Flate for grayscale pages (crisp text, ~half the JPEG size), JPEG for colour."""
    probe = image.reduce(_GRAY_PROBE_REDUCE)
    red, green, blue = probe.split()
    if ImageChops.difference(red, green).getbbox() is None and ImageChops.difference(green, blue).getbbox() is None:
        gray = image.convert("L")
        return PageImage(zlib.compress(gray.tobytes(), _FLATE_LEVEL), gray.width, gray.height, "DeviceGray", "FlateDecode")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return PageImage(buffer.getvalue(), image.width, image.height, "DeviceRGB", "DCTDecode")


class PdfDocument:
    """Why: a "black boxes on the original" PDF must not keep any hidden text layer, and a
    200-page job must not hold 200 rendered pages in memory.
    What: extracts one text segment per page (index-exact with PDFium char boxes) and validates
    every page's render plan up front; render_stream() then renders one page at a time, paints
    black boxes over edited spans into the bitmap and emits an image-only PDF incrementally.
    Pages without text but with drawn content fail closed (no OCR).
    Test: render a reportlab PDF with a name at known coordinates; assert the output has
    zero text chars and the pixel at the name's centre is black.
    """

    format = DocumentFormat.PDF
    # The output is a new image-only PDF: nothing from the source structure survives.
    SANITIZED = ("text_layer", "metadata", "annotations", "form_fields", "attachments", "scripts")

    def __init__(self, payload: bytes, limits: DocumentLimits) -> None:
        self._payload = payload
        self._limits = limits
        self.warnings: list[str] = []
        self.segments: list[str] = []
        self._plans: list[_PagePlan] = []
        with PDFIUM_LOCK:
            pdf = self._open(payload)
            try:
                self.pages = len(pdf)
                if self.pages > limits.max_pages:
                    raise DocumentError(413, "DOCUMENT_PAGE_LIMIT_EXCEEDED",
                                        f"The PDF has more than {limits.max_pages} pages.")
                for index in range(self.pages):
                    page = pdf[index]
                    try:
                        self.segments.append(self._extract(page))
                        self._plans.append(plan_page(*page.get_size(), page.get_rotation(), limits))
                    finally:
                        page.close()
            finally:
                pdf.close()
        if not "".join(self.segments).strip():
            raise _NO_TEXT_LAYER
        self.warnings = sorted(set(self.warnings))

    @staticmethod
    def _open(payload: bytes):
        try:
            return pdfium.PdfDocument(payload)
        except pdfium.PdfiumError as exc:
            raise DocumentError(422, "INVALID_DOCUMENT",
                                "The PDF could not be opened (corrupted or password-protected).") from exc

    def _extract(self, page) -> str:
        textpage = page.get_textpage()
        try:
            text = "".join(_char(textpage, i) for i in range(textpage.count_chars()))
        finally:
            textpage.close()
        has_images = any(True for _ in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,)))
        if not text.strip() and pdfium_c.FPDFPage_CountObjects(page.raw) > 0:
            raise _NO_TEXT_LAYER
        if has_images:
            self.warnings.append("pdf_images_not_inspected")
        if pdfium_c.FPDFPage_GetAnnotCount(page.raw) > 0:
            self.warnings.append("pdf_annotations_and_form_fields_removed")
        return text

    def page_of(self, segment: int) -> int | None:
        return segment + 1

    def render(self, edits: list[SegmentEdit]) -> bytes:
        return b"".join(self.render_stream(edits))

    def render_stream(self, edits: list[SegmentEdit], deadline: float | None = None) -> Iterator[bytes]:
        """Yields the output PDF in pieces (header, one chunk per page, trailer ending in %%EOF).
        Any failure raises before the trailer, so an incomplete body never ends in %%EOF."""
        by_page: dict[int, list[SegmentEdit]] = defaultdict(list)
        for edit in edits:
            by_page[edit.segment].append(edit)
        writer = ImagePdfWriter()
        yield writer.start()
        with PDFIUM_LOCK:
            source = self._open(self._payload)
        try:
            for index, plan in enumerate(self._plans):
                if deadline is not None and time.monotonic() > deadline:
                    raise PdfRenderTimeout()
                yield writer.add_page(self._render_page(source, index, plan, by_page.get(index, [])),
                                      plan.frame, plan.rotation)
            yield writer.finish()
        finally:
            with PDFIUM_LOCK:
                source.close()

    def _render_page(self, source, index: int, plan: _PagePlan, edits: list[SegmentEdit]) -> PageImage:
        # Render in the unrotated (/MediaBox) frame and re-apply /Rotate on the new page,
        # so both the displayed orientation and the page's rotation attribute survive.
        undo = (360 - plan.rotation) % 360
        with PDFIUM_LOCK:
            page = source[index]
            try:
                # Annotations and form widgets are not part of the text layer, so they are
                # never drawn: anything we cannot inspect must not reach the output.
                bitmap = page.render(scale=plan.scale, rotation=undo, may_draw_forms=False,
                                     draw_annots=False, rev_byteorder=True)
                for left, top, right, bottom in self._boxes(page, edits, bitmap.width, bitmap.height, undo // 90):
                    left, top = max(0, left), max(0, top)
                    right, bottom = min(bitmap.width, right), min(bitmap.height, bottom)
                    if right > left and bottom > top:
                        bitmap.fill_rect(_BLACK, left, top, right - left, bottom - top)
            finally:
                page.close()
        try:
            return _encode(bitmap.to_pil())  # PIL/zlib only: runs outside the PDFium lock
        finally:
            with PDFIUM_LOCK:
                bitmap.close()

    @staticmethod
    def _boxes(page, edits: list[SegmentEdit], width: int, height: int, rotate: int) -> list[tuple[int, int, int, int]]:
        if not edits:
            return []
        textpage = page.get_textpage()
        x, y = ctypes.c_int(), ctypes.c_int()

        def to_device(px: float, py: float) -> tuple[int, int]:
            pdfium_c.FPDF_PageToDevice(page.raw, 0, 0, width, height, rotate, px, py, ctypes.byref(x), ctypes.byref(y))
            return x.value, y.value

        rects = []
        try:
            for edit in edits:
                boxes = []
                for index in range(edit.start, edit.end):
                    if _char(textpage, index).isspace():
                        continue
                    left, bottom, right, top = textpage.get_charbox(index, loose=True)
                    (x1, y1), (x2, y2) = to_device(left, top), to_device(right, bottom)
                    boxes.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
                for left, top, right, bottom in _line_boxes(boxes):
                    rects.append((int(left) - _BOX_PAD_PX, int(top) - _BOX_PAD_PX,
                                  int(right) + _BOX_PAD_PX, int(bottom) + _BOX_PAD_PX))
        finally:
            textpage.close()
        return rects
