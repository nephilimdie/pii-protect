"""Client for the internal OCR service (ocr-service/, ``POST /v1/ocr`` and ``/v1/visual-pii``).

One rendered page per request. Every failure is a content-free DocumentError, so callers
fail closed (no document is ever returned without OCR). Page bytes, OCR text and the
internal key never reach a log line.
"""

from __future__ import annotations

import io
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

import httpx
from PIL import Image

from app.config import settings
from app.documents.models import DocumentError

logger = logging.getLogger(__name__)
BBox = tuple[int, int, int, int]
T = TypeVar("T")
_PNG_LEVEL = 1  # fast: the page travels over a local network, encoding time matters more than size
_CONNECT_BACKOFF = 0.5


@dataclass(frozen=True)
class OcrWord:
    text: str
    conf: float
    bbox: BBox
    line_id: int
    block_id: int


@dataclass(frozen=True)
class OcrResult:
    """One OCR'd page; boxes are pixels of the image that was sent (top-left origin)."""

    width: int
    height: int
    words: list[OcrWord]
    line_order: list[int]
    low_conf_regions: list[BBox]
    ink_regions: list[BBox]
    skew: float = 0.0  # degrees the service straightened the text by (pads boxes on tilted photos)


VISUAL_TYPES = {"FACE": "FACE", "QR_CODE": "BARCODE", "BARCODE": "BARCODE", "LICENSE_PLATE": "LICENSE_PLATE"}


@dataclass(frozen=True)
class VisualHit:
    """A face, QR/barcode or plate found as pixels; ``bbox`` in pixels of the image that was sent."""

    type: str  # FACE | BARCODE (QR codes included) | LICENSE_PLATE
    bbox: BBox
    score: float
    needs_review: bool


def _unavailable(code: str = "OCR_UNAVAILABLE", retry_after: int | None = None) -> DocumentError:
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return DocumentError(503, code, "Scanned pages could not be OCR'd right now; no document was returned.", headers)


def _bbox(raw: object, width: int, height: int) -> BBox:
    if not isinstance(raw, list) or len(raw) != 4 or not all(isinstance(v, int) for v in raw):
        raise ValueError("bbox")
    x0, y0, x1, y1 = raw
    if not (0 <= x0 <= x1 <= width and 0 <= y0 <= y1 <= height):
        raise ValueError("bbox range")
    return x0, y0, x1, y1


def parse_result(body: object, width: int, height: int) -> OcrResult:
    """Why: the OCR answer decides what gets blacked out; a malformed answer must never be
    trusted partially. What: validates the one-page response (sizes match the sent image,
    every box inside it) and returns an OcrResult; raises ValueError otherwise.
    Test: a response with 2 pages, a box outside the image or a non-int coordinate raises.
    """
    if not isinstance(body, dict) or not isinstance(body.get("pages"), list) or len(body["pages"]) != 1:
        raise ValueError("pages")
    page = body["pages"][0]
    if not isinstance(page, dict) or page.get("width") != width or page.get("height") != height:
        raise ValueError("size")
    words = []
    for raw in page.get("words", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
            raise ValueError("word")
        words.append(OcrWord(raw["text"], float(raw.get("conf", 0)), _bbox(raw.get("bbox"), width, height),
                             int(raw["line_id"]), int(raw.get("block_id", 0))))
    lines = [int(line["id"]) for line in page.get("lines", []) if isinstance(line, dict)]
    regions = [[_bbox(box, width, height) for box in page.get(key, [])]
               for key in ("low_conf_regions", "ink_without_text_regions")]
    skew = page.get("skew", 0.0)
    if not isinstance(skew, (int, float)) or not -45 <= skew <= 45:
        raise ValueError("skew")
    return OcrResult(width, height, words, lines, *regions, float(skew))


def parse_visual(body: object, width: int, height: int) -> list[VisualHit]:
    """Why: like OCR boxes, visual boxes decide what is blacked out: all-or-nothing validation.
    What: checks the frame matches the sent image and every box is inside it with a known type.
    Test: an unknown type, a box outside the image or a size mismatch raises ValueError.
    """
    if not isinstance(body, dict) or body.get("width") != width or body.get("height") != height:
        raise ValueError("size")
    hits = []
    for raw in body.get("boxes", []):
        if not isinstance(raw, dict) or raw.get("type") not in VISUAL_TYPES:
            raise ValueError("visual box")
        hits.append(VisualHit(VISUAL_TYPES[raw["type"]], _bbox(raw.get("bbox"), width, height),
                              float(raw.get("score", 0)), bool(raw.get("needs_review", True))))
    return hits


class OcrClient:
    """Why: the OCR service is a separate, CPU-bound container that answers 503 BUSY when its
    workers are full; the engine must wait politely, bounded by the document deadline.
    What: ``recognize(image, dpi, deadline, engine)`` posts one PNG page with X-Internal-Key
    (``engine`` overrides the client default for this page, e.g. rapidocr for photos);
    ``visual(image, dpi, deadline)`` finds faces/codes/plates (``[]`` when ``visual_detectors``
    is empty, i.e. PII_VISUAL_PII_ENABLED is off). Both honour
    503 Retry-After (capped) and retries connection errors with backoff, up to ``max_retries``;
    maps everything else to 503/504/422 DocumentErrors. Thread-safe (one pooled httpx client).
    Test: an httpx.MockTransport answering 503 twice then 200 -> one result and two sleeps.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float, max_retries: int, max_retry_after: float,
                 lang: str = "ita+eng", engine: str = "auto", visual_detectors: str = "",
                 transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self._client = httpx.Client(base_url=base_url, transport=transport, timeout=timeout, follow_redirects=False,
                                    trust_env=False)
        self._key, self._timeout, self._retries, self._cap = api_key, timeout, max_retries, max_retry_after
        self._fields = {"lang": lang, "engine": engine}
        self.visual_detectors = visual_detectors
        self._sleep, self._clock = sleep, clock

    def recognize(self, image: Image.Image, dpi: int, deadline: float, engine: str | None = None) -> OcrResult:
        data = {**self._fields, "dpi": str(dpi), **({"engine": engine} if engine else {})}
        return self._post("/v1/ocr", image, dpi, data, deadline,
                          lambda body: parse_result(body, image.width, image.height))

    def visual(self, image: Image.Image, dpi: int, deadline: float) -> list[VisualHit]:
        if not self.visual_detectors:
            return []
        return self._post("/v1/visual-pii", image, dpi, {"detectors": self.visual_detectors}, deadline,
                          lambda body: parse_visual(body, image.width, image.height))

    def _post(self, path: str, image: Image.Image, dpi: int, data: dict[str, str], deadline: float,
              parse: Callable[[object], T]) -> T:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", compress_level=_PNG_LEVEL, dpi=(dpi, dpi))
        files = {"file": ("page.png", buffer.getvalue(), "image/png")}
        for attempt in range(self._retries + 1):
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise DocumentError(504, "OCR_TIMEOUT", "OCR of the scanned pages exceeded the time limit.")
            wait: float | None = None
            try:
                response = self._client.post(path, files=files, data=data, headers={"X-Internal-Key": self._key},
                                             timeout=min(self._timeout, remaining))
            except httpx.TimeoutException:
                raise DocumentError(504, "OCR_TIMEOUT", "OCR of the scanned pages exceeded the time limit.") from None
            except httpx.TransportError as exc:
                logger.warning("ocr service unreachable: %s", type(exc).__name__)
                wait, busy = _CONNECT_BACKOFF * 2 ** attempt, None
            else:
                if response.status_code == 200:
                    try:
                        return parse(response.json())
                    except (ValueError, KeyError, TypeError) as exc:
                        logger.warning("ocr response rejected: %s", type(exc).__name__)
                        raise _unavailable("OCR_FAILED") from None
                busy = response.status_code == 503 and _code(response) == "BUSY"
                if not busy:
                    raise _status_error(response)
                wait = _retry_after(response)
            if attempt == self._retries:
                raise _unavailable("OCR_BUSY", math.ceil(wait)) if busy else _unavailable()
            self._sleep(max(0.0, min(wait, self._cap, deadline - self._clock())))
        raise _unavailable()  # pragma: no cover (loop always returns or raises)


def _code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("error", "")) if isinstance(body, dict) else ""


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "")
    return float(value) if value.isdigit() else 1.0


def _status_error(response: httpx.Response) -> DocumentError:
    """4xx about the page itself -> 422; auth/config or server failures -> 503 (logged, content-free)."""
    code = _code(response)
    logger.warning("ocr service refused page: status=%d error=%s", response.status_code, code or "-")
    if response.status_code in (413, 422) and code in {"PAGE_TOO_LARGE", "FILE_TOO_LARGE", "INVALID_DOCUMENT"}:
        return DocumentError(422, "OCR_PAGE_REJECTED", "A scanned page could not be OCR'd (too large or unreadable).")
    if code == "OCR_TIMEOUT":
        return DocumentError(504, "OCR_TIMEOUT", "OCR of the scanned pages exceeded the time limit.")
    return _unavailable("OCR_FAILED" if response.status_code == 500 else "OCR_UNAVAILABLE")


@lru_cache(maxsize=1)
def get_ocr_client() -> OcrClient | None:
    """Process-wide client, or None when PII_OCR_ENABLED is false (override in tests)."""
    if not settings.ocr_enabled:
        return None
    return OcrClient(settings.ocr_url, settings.ocr_internal_api_key, settings.ocr_timeout_seconds,
                     settings.ocr_max_retries, settings.ocr_max_retry_after_seconds, settings.ocr_lang,
                     visual_detectors=settings.visual_pii_detectors if settings.visual_pii_enabled else "")
