"""Visual PII pipeline for ``POST /v1/visual-pii``: faces, QR/barcodes and plates on one page."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol

from PIL import Image

from app.config import Settings
from app.detectors import Hit
from app.detectors.plates import find_plates
from app.engines import Engine, remaining
from app.errors import ErrorCode, OcrError
from app.imageops import to_gray
from app.inputs import PageImage
from app.schemas import VisualBox, VisualResponse

DETECTORS = ("face", "code", "plate")


class Detector(Protocol):
    """Why: dependency inversion; tests inject fakes. What: boxes for one RGB image + health."""

    def detect(self, image: Image.Image) -> list[Hit]: ...

    def ready(self) -> dict[str, object]: ...


def parse_detectors(raw: str | None) -> tuple[str, ...]:
    """Why: the parameter is untrusted. What: comma list -> ordered unique subset of DETECTORS
    (default: all). Test: "plate,face" -> ("face", "plate"); "face,eyes" -> INVALID_PARAMETER.
    """
    wanted = {part.strip() for part in (raw or ",".join(DETECTORS)).split(",") if part.strip()}
    if not wanted or not wanted <= set(DETECTORS):
        raise OcrError(422, ErrorCode.INVALID_PARAMETER, f"detectors must be a comma list of {list(DETECTORS)}.")
    return tuple(name for name in DETECTORS if name in wanted)


class VisualPipeline:
    """Why: keeps detector policy out of the HTTP layer; detectors/engines are injected.
    What: ``run(page, wanted, deadline)`` runs the requested detectors on a <= visual_max_side
    copy of the page and maps every box to the page frame (integer envelope, clamped). A missing
    detector is a 503 NOT_READY (never a silent skip: fail closed).
    Test: with a fake face detector returning one Hit, the response has one FACE box.
    """

    def __init__(self, settings: Settings, detectors: Mapping[str, Detector], engines: Mapping[str, Engine]) -> None:
        self._s, self._detectors, self._engines = settings, detectors, engines

    def _need(self, mapping: Mapping[str, object], name: str) -> object:
        found = mapping.get(name)
        if found is None:
            raise OcrError(503, ErrorCode.NOT_READY, f"The {name} detector is not available.")
        return found

    def run(self, page: PageImage, wanted: tuple[str, ...], deadline: float) -> VisualResponse:
        image = page.image if page.image.mode == "RGB" else page.image.convert("RGB")
        factor = min(1.0, self._s.visual_max_side / max(image.size))
        if factor < 1.0:
            image = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))),
                                 Image.Resampling.BILINEAR)
        scale = page.scale / factor
        hits: list[Hit] = []
        for name in wanted:
            remaining(deadline)
            if name == "plate":
                engine = self._need(self._engines, "rapidocr")
                words = engine.recognize(to_gray(image), "ita", page.dpi, deadline)  # type: ignore[attr-defined]
                hits += find_plates(words, self._s.plate_review_conf)
            else:
                hits += self._need(self._detectors, name).detect(image)  # type: ignore[attr-defined]
        boxes = []
        for hit in hits:
            x0, y0, x1, y1 = (max(0, math.floor(hit.bbox[0] * scale)), max(0, math.floor(hit.bbox[1] * scale)),
                              min(page.width, math.ceil(hit.bbox[2] * scale)), min(page.height, math.ceil(hit.bbox[3] * scale)))
            if x1 > x0 and y1 > y0:
                boxes.append(VisualBox(type=hit.type, bbox=(x0, y0, x1, y1), score=round(min(1.0, max(0.0, hit.score)), 3),  # type: ignore[arg-type]
                                       needs_review=hit.needs_review))
        return VisualResponse(width=page.width, height=page.height, boxes=boxes)
