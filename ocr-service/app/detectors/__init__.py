"""Visual PII detectors (faces, QR/barcodes, licence plates) behind one output shape."""
from __future__ import annotations

from dataclasses import dataclass

BBoxF = tuple[float, float, float, float]


@dataclass(frozen=True)
class Hit:
    """Why: detectors differ (ONNX tensors, zxing symbols, OCR words); the API needs one record.
    What: type (FACE, QR_CODE, BARCODE, LICENSE_PLATE), float box in input pixels, score 0-1,
    and whether a human should look at it (it is redacted either way).
    Test: ``Hit("FACE", (0, 0, 1, 1), 0.9, False).score == 0.9``.
    """

    type: str
    bbox: BBoxF
    score: float
    needs_review: bool


def iou(a: BBoxF, b: BBoxF) -> float:
    """Why: overlapping detections of one object must collapse into one box.
    What: intersection over union of two boxes. Test: identical boxes -> 1.0; disjoint -> 0.0.
    """
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def nms(hits: list[Hit], threshold: float = 0.3) -> list[Hit]:
    """Why: tiles and scales find the same face several times. What: greedy NMS by score; the
    best-scoring box (and its review flag) wins, weaker duplicates are dropped.
    Test: two 0.9-IoU boxes -> one, the higher score.
    """
    kept: list[Hit] = []
    for hit in sorted(hits, key=lambda h: h.score, reverse=True):
        if all(iou(hit.bbox, other.bbox) <= threshold for other in kept):
            kept.append(hit)
    return kept


def grow(box: BBoxF, fx: float, fy: float, width: int, height: int) -> BBoxF:
    """Why: detector boxes are tight (YuNet stops at the hairline, zxing at the modules); the
    redaction must also hide hair/ears and the code's quiet zone. What: expands by ``fx``/``fy``
    of the box size on each side, clamped to the image. Test: (10,10,20,20), 0.1 -> (9,9,21,21).
    """
    dx, dy = (box[2] - box[0]) * fx, (box[3] - box[1]) * fy
    return max(0.0, box[0] - dx), max(0.0, box[1] - dy), min(float(width), box[2] + dx), min(float(height), box[3] + dy)
