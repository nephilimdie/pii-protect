"""OCR engine adapters share one output shape so the pipeline can compare and merge them."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from app.errors import ErrorCode, OcrError


@dataclass(frozen=True)
class RawWord:
    """Why: engines differ (TSV vs ONNX tensors); the pipeline needs one neutral word record.
    What: text, confidence 0-100, float box in the engine's input pixels, line/block keys.
    Test: ``RawWord("a", 90.0, (0, 0, 1, 1), 0, 0).conf == 90.0``.
    """

    text: str
    conf: float
    bbox: tuple[float, float, float, float]
    line: int
    block: int


class Engine(Protocol):
    """Why: dependency inversion; tests inject fakes, the pipeline never imports a concrete engine.
    What: ``recognize`` returns words for one grayscale page image; ``ready`` reports health.
    Test: a class with these two methods type-checks as an Engine.
    """

    name: str

    def recognize(self, gray: Image.Image, lang: str, dpi: int, deadline: float) -> list[RawWord]: ...

    def ready(self) -> dict[str, object]: ...


def remaining(deadline: float) -> float:
    """Why: every engine call must honour the request deadline (fail closed with 504).
    What: seconds left before ``deadline`` (monotonic); raises OCR_TIMEOUT when none remain.
    Test: ``remaining(time.monotonic() - 1)`` raises OcrError with status 504.
    """
    left = deadline - time.monotonic()
    if left <= 0:
        raise OcrError(504, ErrorCode.TIMEOUT, "OCR did not finish within the request deadline.")
    return left
