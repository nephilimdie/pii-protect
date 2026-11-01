"""Photos and screenshots (JPEG, PNG, WebP): OCR -> detection -> opaque boxes; no metadata out.

The image is decoded from the upload bytes whenever it is needed (validation, OCR, render), so
a job waiting for review holds only the compressed payload. Every decode yields the same
clean frame: EXIF orientation applied, colours converted to sRGB, transparency flattened onto
white (pixels hidden behind alpha are what the OCR would miss), and a fresh RGB image that
carries no EXIF/GPS, XMP, ICC, comments or text chunks. Only those pixels are ever encoded.
"""

from __future__ import annotations

import io

import logging

from PIL import Image, ImageCms, ImageOps

from app.documents.chunking import DetectionCancelled
from app.documents.models import DocumentError, DocumentFormat, DocumentLimits, SegmentEdit
from app.documents.ocr_client import OcrClient
from app.documents.ocr_layout import ScannedPage, ScannedPages, paint

# PIL logs every parsed EXIF tag (GPS included) at DEBUG: never let that reach the engine's logs.
logging.getLogger("PIL").setLevel(max(logging.getLogger("PIL").level, logging.INFO))
_PIL_FORMAT = {DocumentFormat.PNG: "PNG", DocumentFormat.JPEG: "JPEG", DocumentFormat.WEBP: "WEBP"}
_ENCODE = {DocumentFormat.PNG: {"compress_level": 6}, DocumentFormat.JPEG: {"quality": 92},
           DocumentFormat.WEBP: {"quality": 92, "method": 4}}
_OCR_DPI_RANGE = (100, 600)  # accepted by the OCR service
_METADATA_KEYS = ("exif", "xmp", "XML:com.adobe.xmp", "icc_profile", "comment", "photoshop")
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif", b"avis"}
_SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
_UNSUPPORTED = DocumentError(
    415, "IMAGE_FORMAT_UNSUPPORTED",
    "Supported images: JPEG, PNG and WebP. HEIC/HEIF, AVIF, GIF, TIFF, BMP and JPEG 2000/XL are not; "
    "convert the image to JPEG or PNG.",
)
_NO_OCR = DocumentError(422, "IMAGE_OCR_NOT_ENABLED", "Images need OCR, which is not enabled on this engine.")
_INVALID = DocumentError(422, "INVALID_DOCUMENT", "The image could not be decoded (corrupted or truncated).")


def sniff_image(payload: bytes) -> str | None:
    """Why: magic bytes, not the filename, decide the parser; known-but-unsupported image types
    must get a clear 415 instead of falling through to the text handler.
    What: returns DocumentFormat.PNG/JPEG/WEBP, None for non-images; raises 415
    IMAGE_FORMAT_UNSUPPORTED for HEIC/HEIF/AVIF, GIF, TIFF, BMP, JPEG 2000 and JPEG XL.
    Test: b"\\x89PNG\\r\\n\\x1a\\n..." -> "png"; an ISO-BMFF header with brand "heic" -> 415.
    """
    head = payload[:32]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return DocumentFormat.PNG
    if head.startswith(b"\xff\xd8\xff"):
        return DocumentFormat.JPEG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return DocumentFormat.WEBP
    unsupported = (
        (head[4:8] == b"ftyp" and head[8:12] in _HEIF_BRANDS)
        or head.startswith((b"GIF87a", b"GIF89a", b"II*\x00", b"MM\x00*", b"\xff\x0a", b"\x00\x00\x00\x0cjP  ",
                            b"\x00\x00\x00\x0cJXL "))
        or (head.startswith(b"BM") and len(head) >= 18 and int.from_bytes(head[14:18], "little") in {12, 40, 52, 56, 108, 124})
    )
    if unsupported:
        raise _UNSUPPORTED
    return None


def _to_srgb(image: Image.Image) -> Image.Image:
    """Upright-frame pixels as 8-bit sRGB RGB: ICC converted (best effort), 16-bit scaled, alpha flattened."""
    icc = image.info.get("icc_profile")
    if icc and image.mode in ("RGB", "RGBA", "CMYK"):
        try:
            image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(icc)), _SRGB,
                                              outputMode="RGBA" if image.mode == "RGBA" else "RGB")
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass  # unreadable profile: keep the raw values (the profile itself is dropped anyway)
    if image.mode.startswith("I"):  # 16-bit greyscale PNG
        image = image.convert("I").point(lambda v: v / 256).convert("L")
    if "A" in image.mode or "transparency" in image.info:
        rgba = image.convert("RGBA")
        image = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image.alpha_composite(rgba)
    return image.convert("RGB")


class ImageDocument(ScannedPages):
    """Why: photos and screenshots of chats, e-mails or IDs carry PII as pixels, and their EXIF
    (GPS, device, timestamps) is PII too; the output must contain neither.
    What: one-page document whose single segment is the OCR text (``run_ocr``); preview boxes
    and needs_review regions have the scanned-PDF shape (page 1, page fractions); ``render``
    paints entity + not-kept review boxes on the clean frame and re-encodes it in the input
    format (PNG lossless, JPEG/WebP quality 92) with no metadata. Redact only.
    Test: a JPEG with EXIF orientation 6 and GPS -> output upright, ``getexif()`` empty, the
    pixels under the detected words black.
    """

    pages = 1
    SANITIZED = ("metadata", "exif_gps", "xmp", "icc_profile", "comments", "alpha_channel")

    def __init__(self, payload: bytes, image_format: str, limits: DocumentLimits) -> None:
        if not limits.ocr_enabled:
            raise _NO_OCR
        self.format = image_format
        self._payload, self._limits = payload, limits
        self.segments = [""]
        self.scanned: dict[int, ScannedPage] = {}
        self.warnings: list[str] = []
        self._decode(validate=True)  # fail fast (format, size, frames, decodability), then drop the bitmap
        self.ocr_pending = [0]

    def page_of(self, segment: int) -> int | None:
        return 1

    def _decode(self, validate: bool = False) -> Image.Image:
        try:
            with Image.open(io.BytesIO(self._payload), formats=[_PIL_FORMAT[self.format]]) as source:
                pixels = source.width * source.height
                if pixels > self._limits.image_max_pixels:
                    raise DocumentError(413, "IMAGE_PIXEL_LIMIT_EXCEEDED",
                                        f"The image has {pixels} pixels; at most {self._limits.image_max_pixels} "
                                        "are accepted.", extra={"max_pixels": self._limits.image_max_pixels,
                                                                "pixels": pixels})
                if getattr(source, "n_frames", 1) > 1:
                    raise DocumentError(422, "IMAGE_ANIMATED_UNSUPPORTED",
                                        "Animated or multi-frame images are not supported; send a single frame.")
                if validate and (any(key in source.info for key in _METADATA_KEYS) or getattr(source, "text", None)):
                    self.warnings = ["image_metadata_removed"]
                clean = _to_srgb(ImageOps.exif_transpose(source))
        except DocumentError:
            raise
        except Image.DecompressionBombError:
            raise DocumentError(413, "IMAGE_PIXEL_LIMIT_EXCEEDED", "The image has too many pixels.") from None
        except (OSError, ValueError, SyntaxError, EOFError):
            raise _INVALID from None
        # A fresh image: nothing of the source's info (EXIF, XMP, ICC, text chunks) can follow.
        return Image.frombytes("RGB", clean.size, clean.tobytes())

    def run_ocr(self, client: OcrClient, deadline: float, concurrency: int = 1,
                progress=None, should_stop=None) -> None:
        """Why: the image has no text until OCR reads it. What: OCRs the clean frame (greyscale,
        downscaled to the per-page pixel budget; boxes map back by ratio) with PII_OCR_IMAGE_ENGINE
        (default rapidocr: `auto` keeps Tesseract on noisy/tilted photos whenever its confidence looks
        fine, while it misreads IBANs and e-mails) and fills the segment.
        Raises 422 OCR_NO_TEXT_FOUND when nothing was read; any OCR failure propagates (fail closed).
        Test: a fake OcrClient returning "Mario Rossi" -> segments == ["Mario Rossi"].
        """
        if should_stop and should_stop():
            raise DetectionCancelled()
        work = self._decode().convert("L")
        factor = min(1.0, (self._limits.max_pixels / (work.width * work.height)) ** 0.5)
        if factor < 1.0:
            work = work.resize((max(1, int(work.width * factor)), max(1, int(work.height * factor))),
                               Image.Resampling.LANCZOS)
        dpi = min(max(round(self._limits.ocr_dpi * factor), _OCR_DPI_RANGE[0]), _OCR_DPI_RANGE[1])
        page = ScannedPage.from_ocr(client.recognize(work, dpi, deadline, self._limits.ocr_image_engine))
        self.scanned[0], self.segments[0], self.ocr_pending = page, page.text, []
        self.warnings = sorted({*self.warnings, "image_ocr_applied"})
        if progress:
            progress(1)
        if not page.text.strip():
            raise DocumentError(422, "OCR_NO_TEXT_FOUND", "No text could be recognized in this image.")

    def render(self, edits: list[SegmentEdit], keep_review: frozenset[int] = frozenset()) -> bytes:
        if self.ocr_pending:
            raise RuntimeError("image was not OCR'd")  # never return an unreviewed image
        image = self._decode()
        paint(image, self.scanned[0], edits, self.review_by_page(keep_review).get(0, []))
        buffer = io.BytesIO()
        image.save(buffer, format=_PIL_FORMAT[self.format], **_ENCODE[self.format])
        return buffer.getvalue()
