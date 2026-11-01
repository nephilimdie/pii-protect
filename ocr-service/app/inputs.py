"""Decode an upload into page images, one at a time, entirely in memory."""
from __future__ import annotations

import io
import re
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.errors import ErrorCode, OcrError

_PDFIUM_LOCK = threading.Lock()  # PDFium is not thread-safe; rendering is short next to OCR
_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "TIFF", "WEBP", "BMP", "GIF"})
_PAGES_RE = re.compile(r"^\s*(\d{1,5})\s*(?:-\s*(\d{1,5})\s*)?$")


@dataclass(frozen=True)
class PageImage:
    """Why: the pipeline must report boxes in the caller's page frame even when it OCRs a
    downscaled copy. What: page index, image to OCR, reported size, effective DPI and the
    factor from OCR pixels to reported pixels.
    Test: a 4000 px image downscaled to 2000 px has ``scale == 2.0`` and ``width == 4000``.
    """

    index: int
    image: Image.Image
    width: int
    height: int
    dpi: int
    scale: float


@dataclass(frozen=True)
class Document:
    """Why: limits are validated for every page before any OCR work starts (fail fast, no
    partial work). What: page count + a lazy per-page loader so only one bitmap is alive.
    Test: ``len(doc.indexes)`` equals the requested page range length.
    """

    kind: str
    indexes: list[int]
    load: Callable[[int], PageImage]

    def pages(self) -> Iterator[PageImage]:
        """Why: bound memory to one page. What: yields pages in order. Test: yields len(indexes) pages."""
        for index in self.indexes:
            yield self.load(index)


def parse_pages(spec: str | None, total: int, max_pages: int) -> list[int]:
    """Why: callers send a page range so large PDFs can be OCR'd in bounded chunks.
    What: "N" or "N-M" (1-based, inclusive) -> 0-based indexes; no spec means all pages.
    More than ``max_pages`` pages is rejected, never truncated.
    Test: ("2-3", 5, 10) -> [1, 2]; (None, 30, 20) raises TOO_MANY_PAGES; ("4-2", 5, 10) raises.
    """
    if spec is None or not spec.strip():
        first, last = 1, total
    else:
        match = _PAGES_RE.match(spec)
        if not match:
            raise OcrError(422, ErrorCode.INVALID_PARAMETER, "pages must look like '3' or '2-5'.")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < first or last > total:
            raise OcrError(422, ErrorCode.INVALID_PARAMETER, f"pages is outside the document range 1-{total}.")
    if total == 0:
        raise OcrError(422, ErrorCode.INVALID_DOCUMENT, "The document has no pages.")
    if last - first + 1 > max_pages:
        raise OcrError(422, ErrorCode.TOO_MANY_PAGES,
                       f"At most {max_pages} pages per request; send a page range.")
    return list(range(first - 1, last))


def fit_scale(width: float, height: float, scale: float, max_pixels: int) -> float:
    """Why: one huge page must not allocate a 200 MP bitmap (same rule as the engine).
    What: lowers ``scale`` so width*height*scale^2 <= max_pixels.
    Test: (1000, 1000, 1.0, 250_000) -> 0.4975 (0.5 minus a rounding margin).
    """
    pixels = width * height * scale * scale
    return scale * (max_pixels / pixels) ** 0.5 * 0.995 if pixels > max_pixels else scale  # margin: renderers round up


def _open_pdf(data: bytes, settings: Settings, dpi: int, pages: str | None) -> Document:
    """Why/What: renders PDF pages with PDFium at ``dpi``, lowered per page to the pixel budget;
    pages that would fall below ``min_dpi`` are rejected up front.
    Test: an A4 page at 300 DPI renders 2480x3508; a 5 m wide page raises PAGE_TOO_LARGE.
    """
    try:
        with _PDFIUM_LOCK:
            pdf = pdfium.PdfDocument(data)
            total = len(pdf)
    except pdfium.PdfiumError as exc:
        raise OcrError(422, ErrorCode.INVALID_DOCUMENT, "The PDF could not be opened (corrupt or encrypted).") from exc
    indexes = parse_pages(pages, total, settings.max_pages)
    plans: dict[int, float] = {}
    with _PDFIUM_LOCK:
        for index in indexes:
            width_pt, height_pt = pdf[index].get_size()
            scale = fit_scale(width_pt, height_pt, dpi / 72, settings.max_page_pixels)
            if scale * 72 < settings.min_dpi:
                raise OcrError(422, ErrorCode.PAGE_TOO_LARGE, "A PDF page is too large to OCR legibly within the pixel budget.")
            plans[index] = scale

    def load(index: int) -> PageImage:
        scale = plans[index]
        with _PDFIUM_LOCK:
            page = pdf[index]
            bitmap = page.render(scale=scale, grayscale=True, draw_annots=True)
            image = bitmap.to_pil().copy()
            bitmap.close()
            page.close()
        return PageImage(index, image, image.width, image.height, round(scale * 72), 1.0)

    return Document("pdf", indexes, load)


def _open_image(data: bytes, settings: Settings, dpi: int, pages: str | None) -> Document:
    """Why/What: decodes PNG/JPEG/TIFF/WebP/BMP/GIF (multi-frame -> pages), applies EXIF
    orientation (boxes refer to the upright image) and downscales above the pixel budget.
    Test: a JPEG with EXIF orientation 6 reports width/height swapped vs the stored pixels.
    """
    try:
        source = Image.open(io.BytesIO(data))
        source_format = source.format
        frames = getattr(source, "n_frames", 1)
    except Image.DecompressionBombError as exc:
        raise OcrError(422, ErrorCode.PAGE_TOO_LARGE, "The image exceeds the maximum pixel count.") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise OcrError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Send a PDF or a PNG/JPEG/TIFF/WebP/BMP/GIF image.") from exc
    if source_format not in _IMAGE_FORMATS:
        raise OcrError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Send a PDF or a PNG/JPEG/TIFF/WebP/BMP/GIF image.")
    if source.width * source.height > settings.max_input_pixels:
        raise OcrError(422, ErrorCode.PAGE_TOO_LARGE, "The image exceeds the maximum pixel count.")
    indexes = parse_pages(pages, frames, settings.max_pages)
    meta_dpi = source.info.get("dpi")
    effective_dpi = dpi
    if isinstance(meta_dpi, tuple) and meta_dpi and 50 <= float(meta_dpi[0]) <= 1200:
        effective_dpi = round(float(meta_dpi[0]))

    def load(index: int) -> PageImage:
        try:
            source.seek(index)
            frame = ImageOps.exif_transpose(source)
            frame.load()
        except (OSError, ValueError, SyntaxError) as exc:
            raise OcrError(422, ErrorCode.INVALID_DOCUMENT, "The image could not be decoded.") from exc
        width, height = frame.size
        factor = fit_scale(width, height, 1.0, settings.max_page_pixels)
        if factor < 1.0:
            frame = frame.resize((max(1, round(width * factor)), max(1, round(height * factor))), Image.Resampling.LANCZOS)
        return PageImage(index, frame, width, height, max(1, round(effective_dpi * factor)), width / frame.width)

    return Document("image", indexes, load)


def open_document(data: bytes, settings: Settings, dpi: int, pages: str | None) -> Document:
    """Why: the media type is decided by content (magic bytes), never by filename/header.
    What: PDF when the payload starts with ``%PDF-`` (after optional whitespace), else image.
    Test: b"%PDF-1.7..." routes to the PDF decoder; random bytes raise UNSUPPORTED_MEDIA_TYPE.
    """
    if not data:
        raise OcrError(422, ErrorCode.INVALID_DOCUMENT, "The uploaded file is empty.")
    if data[:1024].lstrip().startswith(b"%PDF-"):
        return _open_pdf(data, settings, dpi, pages)
    return _open_image(data, settings, dpi, pages)
