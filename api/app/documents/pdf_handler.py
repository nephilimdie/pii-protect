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
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image, ImageChops

from app.documents.chunking import DetectionCancelled
from app.documents.models import DocumentError, DocumentFormat, DocumentLimits, SegmentEdit
from app.documents.ocr_client import OcrClient
from app.documents.ocr_layout import Covers, FaceStyle, ScannedPage, ScannedPages, cover_pixels, paint
from app.documents.pdf_writer import ImagePdfWriter, PageImage
from app.documents.redaction_style import Run, label_for, paint_area, paint_pills

# PDFium is not thread-safe: every call into it goes through this lock. It is taken
# per page (not per document) so concurrent jobs interleave instead of queueing.
PDFIUM_LOCK = threading.Lock()
_BOX_PAD_PX = 2
_JPEG_QUALITY = 85
_FLATE_LEVEL = 6
_GRAY_PROBE_REDUCE = 4  # colour check on a 1/16 thumbnail: cheap, and only decides the encoding
_NO_TEXT_LAYER = DocumentError(
    422, "PDF_NO_TEXT_LAYER",
    "This PDF has pages without a text layer (scanned image) and OCR is not enabled on this engine.",
)
_OCR_NO_TEXT = DocumentError(422, "OCR_NO_TEXT_FOUND", "No text could be recognized in this scanned PDF.")
_OCR_DPI_RANGE = (100, 600)  # accepted by the OCR service
# Displayed (rotated) bitmap -> unrotated /MediaBox frame, for each page /Rotate.
_UNROTATE = {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_270}
_SHOW = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}  # inverse


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


def _is_gray(image) -> bool:
    red, green, blue = image.reduce(_GRAY_PROBE_REDUCE).split()
    return ImageChops.difference(red, green).getbbox() is None and ImageChops.difference(green, blue).getbbox() is None


def _encode(image, lossless: bool = False) -> PageImage:
    """Lossless Flate for grayscale pages (crisp text, ~half the JPEG size) and, with ``lossless``,
    for colour too (a text page with covers), JPEG for other colour pages."""
    if _is_gray(image):
        gray = image.convert("L")
        return PageImage(zlib.compress(gray.tobytes(), _FLATE_LEVEL), gray.width, gray.height, "DeviceGray", "FlateDecode")
    if lossless:
        rgb = image.convert("RGB")
        return PageImage(zlib.compress(rgb.tobytes(), _FLATE_LEVEL), rgb.width, rgb.height, "DeviceRGB", "FlateDecode")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return PageImage(buffer.getvalue(), image.width, image.height, "DeviceRGB", "DCTDecode")


class PdfDocument(ScannedPages):
    """Why: a "black boxes on the original" PDF must not keep any hidden text layer, and a
    200-page job must not hold 200 rendered pages in memory.
    What: extracts one text segment per page (index-exact with PDFium char boxes) and validates
    every page's render plan up front; render_stream() then renders one page at a time, paints
    black boxes over edited spans into the bitmap and emits an image-only PDF incrementally.
    Pages without text but with drawn content fail closed (422) unless OCR is enabled: then
    they are listed in `ocr_pending`, run_ocr() fills their segments from the OCR service and
    their output is the re-rendered scan with boxes over OCR word boxes and review regions.
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
        self.ocr_pending: list[int] = []  # 0-based scanned pages still to OCR
        self.scanned: dict[int, ScannedPage] = {}
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
                        self.segments.append(self._extract(page, index))
                        self._plans.append(plan_page(*page.get_size(), page.get_rotation(), limits))
                    finally:
                        page.close()
            finally:
                pdf.close()
        if not "".join(self.segments).strip() and not self.ocr_pending:
            raise _NO_TEXT_LAYER
        self.warnings = sorted(set(self.warnings))

    @staticmethod
    def _open(payload: bytes):
        try:
            return pdfium.PdfDocument(payload)
        except pdfium.PdfiumError as exc:
            raise DocumentError(422, "INVALID_DOCUMENT",
                                "The PDF could not be opened (corrupted or password-protected).") from exc

    def _extract(self, page, index: int) -> str:
        textpage = page.get_textpage()
        try:
            text = "".join(_char(textpage, i) for i in range(textpage.count_chars()))
        finally:
            textpage.close()
        has_images = any(True for _ in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,)))
        if not text.strip() and pdfium_c.FPDFPage_CountObjects(page.raw) > 0:
            if not self._limits.ocr_enabled:
                raise _NO_TEXT_LAYER
            self.ocr_pending.append(index)
            return ""
        if has_images:
            self.warnings.append("pdf_images_not_inspected")
        if pdfium_c.FPDFPage_GetAnnotCount(page.raw) > 0:
            self.warnings.append("pdf_annotations_and_form_fields_removed")
        return text

    def page_of(self, segment: int) -> int | None:
        return segment + 1

    def run_ocr(self, client: OcrClient, deadline: float, concurrency: int = 1,
                progress=None, should_stop=None) -> None:
        """Why: scanned pages have no text to detect on; OCR is the slow part (seconds per page).
        What: renders each pending page in its displayed orientation at the OCR DPI, OCRs up to
        `concurrency` pages at once and replaces its segment with the OCR text. `progress(done)`
        runs after each page; `should_stop()` aborts (DetectionCancelled). Any page failure
        aborts the whole document (fail closed). Raises 422 OCR_NO_TEXT_FOUND if nothing was read.
        Test: a fake OcrClient returning "Mario Rossi" for page 1 -> segments[0] == "Mario Rossi".
        """
        pending, done = list(self.ocr_pending), 0
        with PDFIUM_LOCK:
            source = self._open(self._payload)

        def one(index: int) -> tuple[int, ScannedPage]:
            if should_stop and should_stop():
                raise DetectionCancelled()
            if time.monotonic() > deadline:
                raise DocumentError(504, "OCR_TIMEOUT", "OCR of the scanned pages exceeded the time limit.")
            image, dpi = self._ocr_image(source, index)
            result = client.recognize(image, dpi, deadline, scan=True)
            return index, ScannedPage.from_ocr(result, list(result.visual))

        try:
            with ThreadPoolExecutor(max(1, min(concurrency, len(pending))), thread_name_prefix="pii-ocr") as pool:
                futures = [pool.submit(one, index) for index in pending]
                try:
                    for future in as_completed(futures):
                        index, page = future.result()
                        self.scanned[index], self.segments[index] = page, page.text
                        done += 1
                        if progress:
                            progress(done)
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
        finally:
            with PDFIUM_LOCK:
                source.close()
        self.ocr_pending = []
        if pending and "pdf_ocr_applied" not in self.warnings:
            self.warnings = sorted({*self.warnings, "pdf_ocr_applied"})
        if not "".join(self.segments).strip() and not self.visual_types():
            raise _OCR_NO_TEXT

    def _ocr_image(self, source, index: int) -> tuple[Image.Image, int]:
        frame = self._plans[index].frame
        scale = self._limits.ocr_dpi / 72
        pixels = frame[0] * frame[1] * scale * scale
        if pixels > self._limits.max_pixels:
            scale *= (self._limits.max_pixels / pixels) ** 0.5
        dpi = min(max(round(scale * 72), _OCR_DPI_RANGE[0]), _OCR_DPI_RANGE[1])
        with PDFIUM_LOCK:
            page = source[index]
            try:
                # colour: stamps are told by hue (red/blue/violet); the OCR service greys it itself
                bitmap = page.render(scale=scale, may_draw_forms=False, draw_annots=False, rev_byteorder=True)
                try:
                    image = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
        return image, dpi

    def render(self, edits: list[SegmentEdit], keep_review: frozenset[int] = frozenset(),
               face_style: str = FaceStyle.BLACK, cover: Covers | None = None,
               keep_visual: frozenset[int] = frozenset()) -> bytes:
        return b"".join(self.render_stream(edits, None, keep_review, face_style, cover, keep_visual))

    def render_stream(self, edits: list[SegmentEdit], deadline: float | None = None,
                      keep_review: frozenset[int] = frozenset(), face_style: str = FaceStyle.BLACK,
                      cover: Covers | None = None, keep_visual: frozenset[int] = frozenset()) -> Iterator[bytes]:
        """Yields the output PDF in pieces (header, one chunk per page, trailer ending in %%EOF).
        Any failure raises before the trailer, so an incomplete body never ends in %%EOF.
        `keep_review`: ids of review_boxes() left visible; `cover`: user-drawn areas painted opaque
        (fractions of the displayed page, any page)."""
        cover = cover or {}
        if self.ocr_pending:
            raise RuntimeError("scanned pages were not OCR'd")  # never render an unreviewed scan
        by_page: dict[int, list[SegmentEdit]] = defaultdict(list)
        for edit in edits:
            by_page[edit.segment].append(edit)
        review = self.review_by_page(keep_review)
        visual = self.visual_keep_by_page(keep_visual)
        writer = ImagePdfWriter()
        yield writer.start()
        with PDFIUM_LOCK:
            source = self._open(self._payload)
        try:
            for index, plan in enumerate(self._plans):
                if deadline is not None and time.monotonic() > deadline:
                    raise PdfRenderTimeout()
                if index in self.scanned:
                    image = self._render_scanned(source, index, plan, by_page.get(index, []), review.get(index, []),
                                                 face_style, cover.get(index, ()), visual.get(index, frozenset()))
                else:
                    image = self._render_page(source, index, plan, by_page.get(index, []), cover.get(index, ()))
                yield writer.add_page(image, plan.frame, plan.rotation)
            yield writer.finish()
        finally:
            with PDFIUM_LOCK:
                source.close()

    def _render_page(self, source, index: int, plan: _PagePlan, edits: list[SegmentEdit], cover=()) -> PageImage:
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
                turned = plan.rotation in (90, 270)  # covers are laid out on the DISPLAYED page
                runs, shown_words, vertical = self._runs(
                    page, edits, *((bitmap.height, bitmap.width) if turned else (bitmap.width, bitmap.height)))
            finally:
                page.close()
        try:
            image = bitmap.to_pil().convert("RGB")  # PIL/zlib only: runs outside the PDFium lock
        finally:
            with PDFIUM_LOCK:
                bitmap.close()
        if not runs and not cover:
            return _encode(image)
        lossless = _is_gray(image)  # a text page stays crisp: lossless colour instead of JPEG
        shown = image.transpose(_SHOW[plan.rotation]) if plan.rotation in _SHOW else image
        for box in cover_pixels(cover, shown.width, shown.height):  # fractions of the displayed page
            paint_area(shown, box)
        if vertical:  # text runs top-bottom: lay the pills out on the transposed page
            shown = shown.transpose(Image.Transpose.TRANSPOSE)
        paint_pills(shown, runs, shown_words)
        if vertical:
            shown = shown.transpose(Image.Transpose.TRANSPOSE)
        return _encode(shown.transpose(_UNROTATE[plan.rotation]) if plan.rotation in _UNROTATE else shown, lossless)

    def _render_scanned(self, source, index: int, plan: _PagePlan, edits: list[SegmentEdit],
                        review: list, face_style: str = "black", cover=(),
                        keep_visual: frozenset[int] = frozenset()) -> PageImage:
        """Scanned page: render as displayed (the frame OCR saw), paint entity and review boxes,
        rotate back into the /MediaBox frame. Only pixels leave: no OCR text is written."""
        with PDFIUM_LOCK:
            page = source[index]
            try:
                bitmap = page.render(scale=plan.scale, may_draw_forms=False, draw_annots=False, rev_byteorder=True)
                try:
                    image = bitmap.to_pil().convert("RGB")  # a copy, independent of the bitmap buffer
                finally:
                    bitmap.close()
            finally:
                page.close()
        paint(image, self.scanned[index], edits, review, face_style, cover, keep_visual)
        if plan.rotation in _UNROTATE:
            image = image.transpose(_UNROTATE[plan.rotation])
        return _encode(image)

    @staticmethod
    def _runs(page, edits: list[SegmentEdit], width: int,
              height: int) -> tuple[list[Run], list[tuple[int, int, int, int]], bool]:
        """(one padded Run per text line of each edit, boxes of the visible words, vertical) in pixels
        of the displayed page (``width`` x ``height``); the words let covers grow into free room first.
        When the page's text runs top-bottom (median step between glyphs is vertical) every box is
        given transposed (x <-> y), so lines still run along x for the pill layout."""
        if not edits:
            return [], [], False
        textpage = page.get_textpage()
        x, y = ctypes.c_int(), ctypes.c_int()
        device = (width, height)  # PDFium maps to the displayed page; width/height may be transposed below

        def to_device(px: float, py: float) -> tuple[int, int]:
            pdfium_c.FPDF_PageToDevice(page.raw, 0, 0, *device, 0, px, py, ctypes.byref(x), ctypes.byref(y))
            return x.value, y.value

        def box(index: int) -> tuple[int, int, int, int]:
            left, bottom, right, top = textpage.get_charbox(index, loose=True)
            (x1, y1), (x2, y2) = to_device(left, top), to_device(right, bottom)
            if vertical:
                (x1, y1), (x2, y2) = (y1, x1), (y2, x2)
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

        runs, shown, vertical = [], [], False
        try:
            count = textpage.count_chars()
            centres = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in
                       (box(i) for i in range(min(count, 400)) if not _char(textpage, i).isspace())]
            steps = [(abs(q[0] - p[0]), abs(q[1] - p[1])) for p, q in zip(centres, centres[1:])]
            if steps:
                mid = len(steps) // 2
                vertical = sorted(dy for _, dy in steps)[mid] > sorted(dx for dx, _ in steps)[mid]
            if vertical:
                width, height = height, width
            for edit in edits:
                boxes = [box(i) for i in range(edit.start, edit.end) if not _char(textpage, i).isspace()]
                for left, top, right, bottom in _line_boxes(boxes):
                    x0, y0 = max(0, int(left) - _BOX_PAD_PX), max(0, int(top) - _BOX_PAD_PX)
                    x1, y1 = min(width, int(right) + 1 + _BOX_PAD_PX), min(height, int(bottom) + 1 + _BOX_PAD_PX)
                    if x1 > x0 and y1 > y0:
                        tag = "" if vertical else label_for(edit.label)  # no mirrored tags on transposed pages
                        runs.append(Run(x0, y0, x1, y1, bottom - top, tag))
            hidden = {i for edit in edits for i in range(edit.start, edit.end)}
            word: list[tuple[int, int, int, int]] = []
            for i in range(count + 1):
                visible = i < count and i not in hidden and not _char(textpage, i).isspace()
                if visible:
                    word.append(box(i))
                elif word:
                    shown.extend(tuple(int(v) for v in line) for line in _line_boxes(word))
                    word = []
        finally:
            textpage.close()
        return runs, shown, vertical
