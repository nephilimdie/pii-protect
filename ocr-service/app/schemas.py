"""Response models for ``POST /v1/ocr`` (mirrors openapi.yaml)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BBox = tuple[int, int, int, int]


class Word(BaseModel):
    """Why: the engine redacts per word, so each word needs its pixel box and confidence.
    What: recognized token, confidence 0-100, ``[x0, y0, x1, y1]`` in page pixels.
    Test: ``Word(text="a", conf=90, bbox=(0, 0, 1, 1), line_id=0, block_id=0).bbox[2] == 1``.
    """

    text: str
    conf: float = Field(ge=0, le=100)
    bbox: BBox
    line_id: int
    block_id: int


class Line(BaseModel):
    """Why: PII often spans words (names, IBAN groups); lines give the engine reading order.
    What: line id, union box of its words and their space-joined text.
    Test: a line built from words "Mario" and "Rossi" has text "Mario Rossi".
    """

    id: int
    bbox: BBox
    text: str


class Page(BaseModel):
    """Why: fail-closed redaction needs both what was read and what could not be read.
    What: one page's words/lines plus low-confidence and unrecognized-ink regions.
    Test: a blank page yields empty words, lines and regions.
    """

    index: int
    width: int
    height: int
    dpi: int
    engine: str
    words: list[Word]
    lines: list[Line]
    low_conf_regions: list[BBox]
    ink_without_text_regions: list[BBox]
    skew: float = 0.0  # residual tilt (degrees, CCW) the text was straightened by; callers pad tilted boxes


class OcrResponse(BaseModel):
    """Why: a request either returns every requested page or fails (no partial results).
    What: the list of OCR'd pages in request order.
    Test: a 2-page PDF returns ``len(pages) == 2`` with indexes 0 and 1.
    """

    pages: list[Page]


class VisualBox(BaseModel):
    """Why: faces, codes and plates are PII without (readable) text; the caller paints boxes.
    What: detection type, ``[x0, y0, x1, y1]`` in image pixels (already grown to cover hair,
    quiet zones), score 0-1 and whether a human should check it (it is redacted either way).
    Test: ``VisualBox(type="FACE", bbox=(0, 0, 1, 1), score=0.9, needs_review=False).type == "FACE"``.
    """

    type: Literal["FACE", "QR_CODE", "BARCODE", "LICENSE_PLATE"]
    bbox: BBox
    score: float = Field(ge=0, le=1)
    needs_review: bool


class VisualResponse(BaseModel):
    """Why: one image (or one PDF page) per request keeps the call bounded and the frame clear.
    What: the analysed frame size (EXIF-upright, original resolution) and every detection.
    Test: a blank 400x300 PNG returns ``{"width": 400, "height": 300, "boxes": []}``.
    """

    width: int
    height: int
    boxes: list[VisualBox]
