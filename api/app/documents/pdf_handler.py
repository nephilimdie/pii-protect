from __future__ import annotations

import ctypes
import io
import threading
from collections import defaultdict

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import ImageDraw

from app.documents.models import DocumentError, DocumentFormat, DocumentLimits, SegmentEdit

# PDFium is not thread-safe: every call into it goes through this lock.
PDFIUM_LOCK = threading.Lock()
_BOX_PAD_PX = 2
_JPEG_QUALITY = 85
_NO_TEXT_LAYER = DocumentError(
    422, "PDF_NO_TEXT_LAYER",
    "This PDF has pages without a text layer (scanned image). OCR is not supported yet.",
)


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


class PdfDocument:
    """Why: a "black boxes on the original" PDF must not keep any hidden text layer.
    What: extracts one text segment per page (index-exact with PDFium char boxes), then
    renders each page to an image, paints black boxes over edited spans and rebuilds an
    image-only PDF. Pages without text but with drawn content fail closed (no OCR).
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
        with PDFIUM_LOCK:
            pdf = self._open(payload)
            try:
                self.pages = len(pdf)
                if self.pages > limits.max_pages:
                    raise DocumentError(413, "DOCUMENT_PAGE_LIMIT_EXCEEDED",
                                        f"The PDF has more than {limits.max_pages} pages.")
                for index in range(self.pages):
                    self.segments.append(self._extract(pdf[index]))
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
        by_page: dict[int, list[SegmentEdit]] = defaultdict(list)
        for edit in edits:
            by_page[edit.segment].append(edit)
        with PDFIUM_LOCK:
            source = self._open(self._payload)
            output = pdfium.PdfDocument.new()
            try:
                for index in range(len(source)):
                    self._render_page(source[index], by_page.get(index, []), output)
                buffer = io.BytesIO()
                output.save(buffer)
            finally:
                output.close()
                source.close()
        return buffer.getvalue()

    def _render_page(self, page, edits: list[SegmentEdit], output) -> None:
        width_pt, height_pt = page.get_size()
        scale = self._limits.pdf_dpi / 72
        pixels = width_pt * height_pt * scale * scale
        if pixels > self._limits.max_pixels:
            scale *= (self._limits.max_pixels / pixels) ** 0.5
        # Annotations and form widgets are not part of the text layer, so they are
        # never drawn: anything we cannot inspect must not reach the output.
        bitmap = page.render(scale=scale, may_draw_forms=False, draw_annots=False)
        image = bitmap.to_pil().convert("RGB")
        draw = ImageDraw.Draw(image)
        for box in self._boxes(page, edits, image.width, image.height):
            draw.rectangle(box, fill="black")
        jpeg = io.BytesIO()
        image.save(jpeg, format="JPEG", quality=_JPEG_QUALITY)
        jpeg.seek(0)
        # The bitmap is the unrotated page; re-apply /Rotate so viewers show it as before.
        new_page = output.new_page(image.width / scale, image.height / scale)
        new_page.set_rotation(page.get_rotation())
        picture = pdfium.PdfImage.new(output)
        picture.load_jpeg(jpeg, inline=True)
        picture.set_matrix(pdfium.PdfMatrix().scale(image.width / scale, image.height / scale))
        new_page.insert_obj(picture)
        new_page.gen_content()
        new_page.close()

    @staticmethod
    def _boxes(page, edits: list[SegmentEdit], width: int, height: int) -> list[tuple[int, int, int, int]]:
        if not edits:
            return []
        textpage = page.get_textpage()
        x, y = ctypes.c_int(), ctypes.c_int()

        def to_device(px: float, py: float) -> tuple[int, int]:
            pdfium_c.FPDF_PageToDevice(page.raw, 0, 0, width, height, 0, px, py, ctypes.byref(x), ctypes.byref(y))
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
